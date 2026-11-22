"""MCP identity acceptance (decision 0017), with real signed tokens and no external calls."""

import http.client
import json
import socket
import ssl
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Event, Thread
from threading import enumerate as enumerate_threads
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from platform_core.identity import api, mcp_introspection, mcp_tokens
from platform_core.identity.exceptions import KeycloakKeysUnavailable, ServiceTokenRejected
from platform_core.identity.tests import helpers

RESOURCE = "https://tenant.example.test/api/method/platform_core.api.ai.mcp"
ISSUER = "https://identity.example.test/realms/platform"
CLIENT = "mcp-client"
SUBJECT = "sample-subject"
SID = "11111111-1111-4111-8111-111111111111"
ACCOUNT = "sample-user@example.test"
INTROSPECTION_URL = ISSUER + "/protocol/openid-connect/token/introspect"


class TestMcpIdentity(TestCase):
	def setUp(self):
		self.conf = {
			"mcp_oauth_enabled": 1,
			"mcp_oauth_resource": RESOURCE,
			"mcp_oauth_client_ids": [CLIENT],
			"mcp_oauth_introspection_secret": "test-only",
			"keycloak_public_url": "https://identity.example.test",
			"keycloak_realm": "platform",
			"kimlik_deletion_hmac_key": "synthetic",
		}
		self.db = Mock()
		self.db.exists.return_value = False
		self.db.get_value.side_effect = [ACCOUNT, 1]
		self.enterContext(patch.object(frappe, "conf", self.conf))
		self.enterContext(patch.object(frappe, "db", self.db))
		self.enterContext(patch.object(frappe, "_", side_effect=lambda message, **kwargs: message))
		self.set_user = self.enterContext(patch.object(frappe, "set_user"))
		self.enterContext(helpers.jwks_patch())
		self.transport = self.enterContext(patch.object(mcp_tokens, "fetch_introspection"))
		self.transport.return_value = json.dumps(
			{"active": True, "client_id": CLIENT, "sub": SUBJECT, "sid": SID, "username": "sample-user"}
		).encode()

	def claims(self, **overrides):
		now = int(time.time())
		return helpers.access_payload(
			**{
				"iss": ISSUER,
				"sub": SUBJECT,
				"aud": RESOURCE,
				"azp": CLIENT,
				"mcp_resource": RESOURCE,
				"scope": "openid mcp",
				"sid": SID,
				"iat": now - 1,
				"exp": now + 299,
				**overrides,
			},
		)

	def check_rejected(self, claims=None, *, token=None, reason=None):
		if token is None:
			token = helpers.key().sign(claims or self.claims())
		with self.assertRaises(ServiceTokenRejected) as denied:
			api.verify_mcp_token(token)
		self.assertEqual(denied.exception.http_status_code, 401)
		self.assertEqual(str(denied.exception), "MCP token rejected.")
		if reason is not None:
			self.assertEqual(denied.exception.reason, reason)

	def test_config_needs_explicit_switch_and_safe_complete_settings(self):
		self.assertEqual(api.mcp_oauth_config(), {"resource": RESOURCE, "issuer": ISSUER})
		for field, value in (
			("mcp_oauth_enabled", 0),
			("mcp_oauth_enabled", "false"),
			("mcp_oauth_resource", RESOURCE.replace("https:", "http:")),
			("mcp_oauth_resource", RESOURCE + "?wrong=yes"),
			("mcp_oauth_resource", RESOURCE.replace("tenant.", 'tenant."')),
			(
				"mcp_oauth_resource",
				RESOURCE.replace("tenant.example.test", "evil.example.test@tenant.example.test"),
			),
			("keycloak_public_url", "https://identity.example.test#"),
			("keycloak_internal_url", "http://identity.example.test"),
			("mcp_oauth_client_ids", []),
			("mcp_oauth_introspection_secret", ""),
		):
			with self.subTest(field=field, value=value), patch.dict(self.conf, {field: value}):
				self.assertIsNone(api.mcp_oauth_config())
				self.check_rejected()

	def test_valid_signed_token_resolves_live_identity_without_setting_user(self):
		claims = self.claims()
		result = api.verify_mcp_token(helpers.key().sign(claims))
		self.assertEqual(
			result,
			{
				"account": ACCOUNT,
				"issuer": ISSUER,
				"subject": SUBJECT,
				"session_id": SID,
				"resource": RESOURCE,
				"client_id": CLIENT,
				"issued_at": claims["iat"],
				"expires_at": claims["exp"],
				"scopes": ["openid", "mcp"],
			},
		)
		self.set_user.assert_not_called()
		self.assertEqual(self.transport.call_args.args[0], INTROSPECTION_URL)
		self.assertEqual(self.transport.call_args.kwargs["max_bytes"], 64 * 1024)
		self.assertEqual(
			self.db.get_value.call_args_list[0].args,
			("PLT Identity Link", {"issuer": ISSUER, "subject": SUBJECT}, "user"),
		)

	def test_rejects_bad_signature_algorithm_and_authority_claims_before_introspection(self):
		wrong_key = helpers.Key()
		self.check_rejected(token=wrong_key.sign(self.claims(), kid=helpers.key().kid))
		self.check_rejected(token=helpers.key().sign(self.claims(), alg="none"))
		for changes in (
			{"iss": "https://wrong.example.test/realms/platform"},
			{"aud": RESOURCE + "/wrong"},
			{"aud": [RESOURCE, RESOURCE + "/another-site"]},
			{"azp": "another-client"},
			{"scope": "openid mobile"},
			{"scope": "openid\tmcp"},
			{"scope": "mcp offline_access"},
			{"sid": None},
			{"sid": SID + "\n"},
			{"sub": None},
			{"typ": "ID"},
		):
			with self.subTest(changes=changes):
				self.check_rejected(self.claims(**changes))
		self.assertEqual(self.transport.call_count, 0)

	def test_rejects_non_integer_expiry_and_invalid_lifetimes(self):
		now = int(time.time())
		for changes in (
			{"exp": now + 99.5},
			{"iat": now - 1.5},
			{"iat": True},
			{"iat": None},
			{"iat": now + 30},
			{"iat": now - 3, "exp": now + 300},
		):
			with self.subTest(changes=changes):
				self.check_rejected(self.claims(**changes))
		self.check_rejected(self.claims(iat=now - 100, exp=now - 1), reason="expired")
		self.assertEqual(self.transport.call_count, 0)

	def test_rejects_inherited_or_incorrect_request_resource_even_with_matching_audience(self):
		for claim in (None, RESOURCE + "/wrong", [RESOURCE]):
			with self.subTest(claim=claim):
				self.db.get_value.side_effect = [ACCOUNT, 1]
				self.check_rejected(self.claims(mcp_resource=claim))
		self.assertEqual(self.transport.call_count, 0)

	def test_rejects_deleted_disabled_unlinked_and_builtin_accounts(self):
		for deleted, values in (
			(True, [ACCOUNT, 1]),
			(False, [ACCOUNT, 0]),
			(False, [None]),
			(False, ["Administrator", 1]),
			(False, ["Guest", 1]),
		):
			with self.subTest(deleted=deleted, values=values):
				self.db.exists.return_value = deleted
				self.db.get_value.side_effect = values
				self.check_rejected()
		self.assertEqual(self.transport.call_count, 0)

	def test_checks_session_on_each_request_and_rejects_after_logout(self):
		token = helpers.key().sign(self.claims())
		self.db.get_value.side_effect = [ACCOUNT, 1] * 2
		self.assertEqual(api.verify_mcp_token(token)["account"], ACCOUNT)
		self.transport.return_value = b'{"active":false}'
		self.check_rejected(token=token)
		self.assertEqual(self.transport.call_count, 2)

	def test_rejects_introspection_of_wrong_session_subject_client_or_service_account(self):
		active = {"active": True, "client_id": CLIENT, "sub": SUBJECT, "sid": SID, "username": "sample-user"}
		for field, value in (
			("sid", "wrong-sid"),
			("sub", "wrong-subject"),
			("client_id", "other-client"),
			("username", "service-account-mcp-client"),
			("username", None),
		):
			with self.subTest(field=field):
				self.db.get_value.side_effect = [ACCOUNT, 1]
				self.transport.return_value = json.dumps({**active, field: value}).encode()
				self.check_rejected()

	def test_provider_outage_has_fixed_status_and_message(self):
		token = helpers.key().sign(self.claims())
		for body in (b"invalid", b"{}", b"[" * 10_000):
			with self.subTest():
				self.db.get_value.side_effect = [ACCOUNT, 1]
				self.transport.return_value = body
				with self.assertRaises(KeycloakKeysUnavailable) as unavailable:
					api.verify_mcp_token(token)
				self.assertEqual(unavailable.exception.http_status_code, 503)
				self.assertTrue(unavailable.exception.skip_error_log)
				self.assertEqual(str(unavailable.exception), "MCP identity provider unavailable.")
		self.db.get_value.side_effect = [ACCOUNT, 1]
		self.transport.side_effect = TimeoutError("simulated")
		with self.assertRaises(KeycloakKeysUnavailable):
			api.verify_mcp_token(token)
		with helpers.jwks_unavailable_patch(), self.assertRaises(KeycloakKeysUnavailable):
			api.verify_mcp_token(token)


class TestMcpIntrospectionDeadline(TestCase):
	def setUp(self):
		self.settings = mcp_tokens._Settings(
			resource=RESOURCE,
			issuer=ISSUER,
			jwks_url=ISSUER + "/protocol/openid-connect/certs",
			introspection_url=INTROSPECTION_URL,
			client_ids=frozenset({CLIENT}),
			introspection_secret="test-only",
		)
		self.enterContext(patch.object(frappe, "_", side_effect=lambda message, **kwargs: message))
		self.enterContext(patch.object(mcp_tokens, "_INTROSPECTION_TIMEOUT", 0.15, create=True))

	def check_timeout(self, settings=None):
		start = time.monotonic()
		with self.assertRaises(KeycloakKeysUnavailable) as unavailable:
			mcp_tokens._verify_live_session(
				"synthetic", settings or self.settings, subject=SUBJECT, session_id=SID, client_id=CLIENT
			)
		self.assertLess(time.monotonic() - start, 0.5)
		self.assertEqual(unavailable.exception.http_status_code, 503)
		self.assertEqual(str(unavailable.exception), "MCP identity provider unavailable.")
		self.assertTrue(unavailable.exception.skip_error_log)

	def test_deadline_covers_stalled_dns_without_late_connect(self):
		resolver_started = Event()
		unblock = Event()
		resolver_left = Event()
		self.addCleanup(unblock.set)

		def resolver(*args, **kwargs):
			resolver_started.set()
			unblock.wait(0.8)
			resolver_left.set()
			return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 9))]

		with (
			patch("socket.getaddrinfo", side_effect=resolver) as lookup,
			patch.object(socket.socket, "connect") as connect,
			patch.object(mcp_introspection, "_WORKERS", BoundedSemaphore(1)),
		):
			self.check_timeout()
			self.assertTrue(resolver_started.is_set())
			self.check_timeout()
			self.assertEqual(lookup.call_count, 1)
			unblock.set()
			self.assertTrue(resolver_left.wait(1))
			self.assertTrue(self.worker_finished())
			self.assertEqual(connect.call_count, 0)

	def worker_finished(self):
		deadline = time.monotonic() + 1
		while time.monotonic() < deadline:
			if not any(worker.name == "mcp-introspection" for worker in enumerate_threads()):
				return True
			time.sleep(0.005)
		return False

	def test_deadline_cuts_slow_tls_handshake_headers_and_body(self):
		for stage in ("handshake", "headers", "body"):
			with self.subTest(stage=stage), self.tls_server(stage) as (url, closed, _received):
				self.check_timeout(replace(self.settings, introspection_url=url))
				self.assertTrue(closed.wait(1))
				self.assertTrue(self.worker_finished())

	def test_https_uses_certificate_verification(self):
		with self.tls_server("valid", trust=False) as (url, _closed, received):
			with self.assertRaises(KeycloakKeysUnavailable):
				mcp_tokens._verify_live_session(
					"synthetic",
					replace(self.settings, introspection_url=url),
					subject=SUBJECT,
					session_id=SID,
					client_id=CLIENT,
				)
			self.assertFalse(received.is_set())
			self.assertTrue(self.worker_finished())

	def test_trusted_provider_returns_complete_json(self):
		with self.tls_server("valid") as (url, closed, received):
			mcp_tokens._verify_live_session(
				"synthetic",
				replace(self.settings, introspection_url=url),
				subject=SUBJECT,
				session_id=SID,
				client_id=CLIENT,
			)
			self.assertTrue(closed.wait(1))
			self.assertTrue(received.is_set())

	def test_redirect_is_refused_before_creating_another_connection(self):
		connect = socket.socket.connect
		addresses = []

		def record_connect(connection, address):
			addresses.append(address)
			return connect(connection, address)

		with self.tls_server("redirect") as (url, closed, received):
			with (
				patch.object(socket.socket, "connect", record_connect),
				self.assertRaises(KeycloakKeysUnavailable),
			):
				mcp_tokens._verify_live_session(
					"synthetic",
					replace(self.settings, introspection_url=url),
					subject=SUBJECT,
					session_id=SID,
					client_id=CLIENT,
				)
			self.assertTrue(closed.wait(1))
			self.assertTrue(received.is_set())
			self.assertEqual(len(addresses), 1)

	@contextmanager
	def tls_server(self, stage, *, trust=True):
		closed = Event()
		received = Event()
		with TemporaryDirectory() as directory:
			key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
			name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
			now = datetime.now(UTC)
			cert = (
				x509.CertificateBuilder()
				.subject_name(name)
				.issuer_name(name)
				.public_key(key.public_key())
				.serial_number(x509.random_serial_number())
				.not_valid_before(now - timedelta(days=1))
				.not_valid_after(now + timedelta(days=1))
				.add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address("127.0.0.1"))]), False)
				.sign(key, hashes.SHA256())
			)
			cert_path = Path(directory) / "cert.pem"
			cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
			key_path = Path(directory) / "key.pem"
			key_path.write_bytes(
				key.private_bytes(
					serialization.Encoding.PEM,
					serialization.PrivateFormat.PKCS8,
					serialization.NoEncryption(),
				)
			)
			server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
			server_context.load_cert_chain(cert_path, key_path)

			with socket.socket() as listener:
				listener.bind(("127.0.0.1", 0))
				listener.listen()
				listener.settimeout(1)
				worker = Thread(
					target=self.serve_tls,
					args=(listener, server_context, stage, closed, received),
					daemon=True,
				)
				port = listener.getsockname()[1]
				worker.start()
				try:
					with patch.dict("os.environ", {"SSL_CERT_FILE": str(cert_path) if trust else ""}):
						if trust:
							# Certificate and DNS setup should leave time for the response to begin.
							with patch.object(mcp_tokens, "_INTROSPECTION_TIMEOUT", 0.25, create=True):
								yield f"https://127.0.0.1:{port}/introspect", closed, received
						else:
							yield f"https://127.0.0.1:{port}/introspect", closed, received
				finally:
					worker.join(2)

	def serve_tls(self, listener, context, stage, closed, received):
		try:
			client, _address = listener.accept()
			if stage == "handshake":
				with client:
					client.settimeout(1)
					while client.recv(1024):
						pass
				closed.set()
				return
			with client, context.wrap_socket(client, server_side=True) as secure:
				secure.settimeout(1)
				with secure.makefile("rb") as request:
					request.readline()
					headers = http.client.parse_headers(request)
					request.read(int(headers["Content-Length"]))
				received.set()
				if stage == "valid":
					body = json.dumps(
						{
							"active": True,
							"sub": SUBJECT,
							"sid": SID,
							"client_id": CLIENT,
							"username": "sample-user",
						}
					).encode()
					secure.sendall(f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
					closed.set()
					return
				if stage == "redirect":
					secure.sendall(
						b"HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1:9/\r\nContent-Length: 0\r\n\r\n"
					)
					closed.set()
					return
				if stage == "body":
					# Connection: close hands ownership from HTTPConnection to HTTPResponse.
					secure.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n")
				for _step in range(16):
					secure.sendall(b"x" if stage == "body" else b"h")
					time.sleep(0.045)
		except (BrokenPipeError, ConnectionResetError, ssl.SSLEOFError):
			closed.set()
		except (TimeoutError, ssl.SSLError):
			pass
