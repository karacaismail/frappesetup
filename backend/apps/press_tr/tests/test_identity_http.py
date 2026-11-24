"""Exercise identity HTTP routes with an ephemeral local OIDC issuer."""

import base64
import hashlib
import hmac
import json
import re
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import frappe
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from test_auth_http import PressHttpClient

from press_tr.api.test___init__ import LogoutAccessTests
from press_tr.api.test_account import AccountAccessTests
from press_tr.api.test_auth import AuthAccessTests
from press_tr.api.test_identity import IdentityAccessTests
from press_tr.api.test_maintenance import MaintenanceAccessTests

ISSUER = "http://keycloak.example.test/realms/platform"
KID = uuid4().hex
ACCOUNT_ROUTE = "/api/method/press.api.account.get"
DELETION_ROUTE = "/api/method/press_tr.api.account.request_deletion"
IDENTITY_INVENTORY_ROUTE = "/api/method/press_tr.api.identity.list_identities"
RECOVERY_ROUTE = "/api/method/press_tr.api.account.request_recovery"
RECOVERY_RESOURCE = "/api/resource/PTR%20Recovery%20Review"


class IdentityHttpTest(
	LogoutAccessTests,
	AccountAccessTests,
	AuthAccessTests,
	IdentityAccessTests,
	MaintenanceAccessTests,
	PressHttpClient,
	unittest.TestCase,
):
	token_issuer = ISSUER

	@classmethod
	def setUpClass(cls):
		cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
		jwk.update(kid=KID, alg="RS256", use="sig")
		jwks = json.dumps({"keys": [jwk]}).encode()

		cls.codes = {}
		cls.service_tokens = {}
		cls.deletion_requests = []
		cls.deletion_delays = {}
		cls.deletion_statuses = {}

		class IssuerHandler(BaseHTTPRequestHandler):
			def do_GET(self):
				if self.path != "/realms/platform/protocol/openid-connect/certs":
					self.send_error(404)
					return
				self.send_json(jwks)

			def do_POST(self):
				body = self.rfile.read(int(self.headers["Content-Length"])).decode()
				if self.path == "/v1/account-deletions":
					token = self.headers.get("Authorization", "").removeprefix("Bearer ")
					if token not in cls.service_tokens:
						self.send_error(403)
						return
					request = json.loads(body)
					cls.deletion_requests.append(request)
					try:
						status = cls.deletion_statuses.get(request["subject"], "accepted")
						self.send_json(
							json.dumps({"status": status}).encode(),
							delay=cls.deletion_delays.get(request["subject"], 0),
						)
					except BrokenPipeError:
						pass  # Press may have stopped waiting for the delayed response.
					return
				if self.path != "/realms/platform/protocol/openid-connect/token":
					self.send_error(404)
					return
				values = parse_qs(body)
				if values.get("grant_type") == ["client_credentials"]:
					expected = base64.b64encode(b"press-service:press-test-fixture").decode()
					if self.headers.get("Authorization") != f"Basic {expected}" or values.get("scope") != [
						"aud-identity-sync"
					]:
						self.send_error(403)
						return
					self.send_json(json.dumps({"access_token": next(iter(cls.service_tokens))}).encode())
					return
				code = values.get("code", [""])[0]
				fixture = cls.codes.pop(code, None)
				verifier = values.get("code_verifier", [""])[0]
				challenge = (
					base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
				)
				if not fixture or fixture[0] != challenge:
					self.send_error(400)
					return
				self.send_json(json.dumps({"id_token": fixture[1]}).encode())

			def send_json(self, body, *, delay=0):
				self.send_response(200)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
				self.wfile.flush()
				if delay:
					time.sleep(delay)
				self.wfile.write(body)

		cls.server = ThreadingHTTPServer(("127.0.0.1", 3205), IssuerHandler)
		worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
		worker.start()
		cls.addClassCleanup(cls.server.server_close)
		cls.addClassCleanup(cls.server.shutdown)

	def token(self, audience="press", authorized_party="identity-sync", **claims):
		fields = {
			"iss": ISSUER,
			"sub": "service-account",
			"aud": audience,
			"azp": authorized_party,
			"iat": int(time.time()),
			"exp": int(time.time()) + 120,
		}
		return jwt.encode(
			{name: value for name, value in (fields | claims).items() if value is not None},
			self.key,
			algorithm="RS256",
			headers={"kid": KID},
		)

	def call(self, method, body, token=None, extra_headers=None):
		headers = {"Content-Type": "application/json", **(extra_headers or {})}
		if token:
			headers["Authorization"] = f"Bearer {token}"
		status, _headers, response = self.exchange(
			"POST", f"/api/method/press_tr.api.identity.{method}", headers, json.dumps(body)
		)
		return status, json.loads(response) if response.startswith(b"{") else response.decode()

	def test_press_guest_post_respects_frappe_request_body_limit(self):
		path = "/api/method/press_tr.api.auth.get_login_url"
		headers = {"Content-Type": "application/json"}
		body = b"{}".ljust(32768)
		self.assertEqual(self.exchange("POST", path, headers, body)[0], 200)
		self.assertEqual(self.exchange("POST", path, headers, body + b" ")[0], 413)

	def test_account_deletion_requires_reauthentication(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, response_headers, payload = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		self.assertIn("no-store", response_headers["Cache-Control"])
		self.assertEqual(self.exchange("GET", "/account-deletion")[0], 403)
		self.assertEqual(self.exchange("POST", DELETION_ROUTE, body='{"confirm": true}')[0], 403)
		self.assertIn(b"cannot be undone", payload)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', payload).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		self.assertEqual(self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": true}')[0], 403)
		self.assertEqual(self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": "false"}')[0], 403)
		status, _headers, payload = self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": false}')
		self.assertEqual(status, 200)
		query = parse_qs(urlsplit(json.loads(payload)["message"]["url"]).query)
		self.assertEqual(query["prompt"], ["login"])
		self.assertEqual(query["max_age"], ["0"])
		self.assertEqual(query["code_challenge_method"], ["S256"])

	def reauthenticate_deletion(self):
		subject = uuid4().hex
		email = f"{subject}@example.test"
		session = self.sign_in(subject, email, uuid4().hex)
		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		self.assertIn(self.exchange("POST", DELETION_ROUTE, session, '{"confirm": true}')[0], {400, 403})
		status, response_headers, payload = self.exchange(
			"POST", DELETION_ROUTE, headers, '{"confirm": false}'
		)
		self.assertEqual(status, 200)
		query = parse_qs(urlsplit(json.loads(payload)["message"]["url"]).query)
		cookies = SimpleCookie()
		for cookie in response_headers.get_all("Set-Cookie"):
			cookies.load(cookie)
		callback_session = {
			"Cookie": f"{session['Cookie']}; press_tr_login={cookies['press_tr_login'].value}"
		}
		auth_time = int(time.time())
		code = uuid4().hex
		self.codes[code] = (
			query["code_challenge"][0],
			self.token(
				authorized_party="press",
				sub=subject,
				email=email,
				sid=uuid4().hex,
				nonce=query["nonce"][0],
				auth_time=auth_time,
			),
		)
		callback = "/api/method/press_tr.api.auth.keycloak_callback?" + urlencode(
			{"state": query["state"][0], "code": code}
		)
		status, result_headers, payload = self.exchange("GET", callback, callback_session)
		self.assertEqual(status, 302)
		self.assertEqual(result_headers["Location"], "/account-deletion")
		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		self.assertIn(b"Confirm account deletion", page)

		service_token = self.token(audience="identity-sync", authorized_party="press-service")
		self.service_tokens[service_token] = True
		return subject, session, headers, auth_time

	def test_account_deletion_waits_for_slow_service_and_sends_only_verified_identity(self):
		subject, _session, headers, auth_time = self.reauthenticate_deletion()
		self.deletion_delays[subject] = 11
		status, _headers, payload = self.exchange(
			"POST", DELETION_ROUTE, headers, '{"confirm": true}', timeout=20
		)
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(payload)["message"], {"submitted": True})
		self.assertEqual(
			self.deletion_requests[-1],
			{
				"issuer": ISSUER,
				"subject": subject,
				"reauthenticated_at": auth_time,
			},
		)
		self.assertEqual(self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": true}')[0], 403)

	def test_account_deletion_timeout_refresh_and_retry(self):
		subject, session, headers, _auth_time = self.reauthenticate_deletion()
		self.deletion_delays[subject] = 16
		status, _headers, payload = self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": true}', timeout=25)
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(payload)["message"], {"pending": True})

		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		self.assertIn(b'id="account-deletion-status">Account deletion is in progress.', page)
		self.assertEqual(sum(request["subject"] == subject for request in self.deletion_requests), 1)

		self.deletion_delays[subject] = 0
		self.deletion_statuses[subject] = "unknown"
		status, _headers, payload = self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": true}')
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(payload)["message"], {"pending": True})
		requests = [request for request in self.deletion_requests if request["subject"] == subject]
		self.assertEqual(len(requests), 2)
		self.assertEqual(requests[0], requests[1])

		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		self.assertIn(b"Last status known to Press.", page)
		self.assertIn(b'id="account-deletion-status">Account deletion is in progress.', page)
		self.assertEqual(sum(request["subject"] == subject for request in self.deletion_requests), 2)

		self.deletion_statuses[subject] = "processed"
		status, _headers, payload = self.exchange("POST", DELETION_ROUTE, headers, '{"confirm": true}')
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(payload)["message"], {"submitted": True})

		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		self.assertIn(b'role="status">Your deletion request was submitted.', page)

	def test_reauthentication_links_the_new_keycloak_session(self):
		subject = uuid4().hex
		email = f"{subject}@example.test"
		original_sid, reauthenticated_sid = uuid4().hex, uuid4().hex
		session = self.sign_in(subject, email, original_sid)
		status, _headers, page = self.exchange("GET", "/account-deletion", session)
		self.assertEqual(status, 200)
		csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
		headers = {**session, "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/json"}
		status, response_headers, payload = self.exchange(
			"POST", DELETION_ROUTE, headers, '{"confirm": false}'
		)
		self.assertEqual(status, 200)
		query = parse_qs(urlsplit(json.loads(payload)["message"]["url"]).query)
		cookies = SimpleCookie()
		for cookie in response_headers.get_all("Set-Cookie"):
			cookies.load(cookie)
		callback_session = {
			"Cookie": f"{session['Cookie']}; press_tr_login={cookies['press_tr_login'].value}"
		}
		code = uuid4().hex
		self.codes[code] = (
			query["code_challenge"][0],
			self.token(
				authorized_party="press",
				sub=subject,
				sid=reauthenticated_sid,
				nonce=query["nonce"][0],
				auth_time=int(time.time()),
			),
		)
		callback = "/api/method/press_tr.api.auth.keycloak_callback?" + urlencode(
			{"state": query["state"][0], "code": code}
		)
		self.assertEqual(self.exchange("GET", callback, callback_session)[0], 302)
		logout = self.token(
			authorized_party="press",
			sub=subject,
			sid=reauthenticated_sid,
			jti=uuid4().hex,
			events={"http://schemas.openid.net/event/backchannel-logout": {}},
		)
		self.assertEqual(self.post_logout(logout), 200)
		self.assertIn(self.exchange("GET", ACCOUNT_ROUTE, session)[0], {401, 403})

	def test_service_rejects_wrong_credentials(self):
		for method in ("ensure_team", "remove_team_member"):
			for token, headers in (
				(None, {}),
				(self.token(audience="site-tenant1"), {}),
				(self.token(authorized_party="press-service"), {}),
			):
				with self.subTest(method=method, headers=headers):
					status, _payload = self.call(
						method,
						{"issuer": ISSUER, "subject": "example", "organization_id": "example"},
						token,
						headers,
					)
					self.assertEqual(status, 403)
			for extra in ({"cmd": "ping"}, {"team": "legacy"}):
				with self.subTest(method=method, extra=extra):
					body = {"issuer": ISSUER, "subject": "example", "organization_id": "example", **extra}
					status, _payload = self.call(method, body, self.token())
					self.assertEqual(status, 403)

	def identity_inventory(self, query, token=None, extra_headers=None):
		headers = dict(extra_headers or {})
		if token:
			headers["Authorization"] = f"Bearer {token}"
		path = IDENTITY_INVENTORY_ROUTE + (f"?{urlencode(query)}" if query else "")
		status, response_headers, response = self.exchange("GET", path, headers)
		if status == 200:
			self.assertIn("no-store", response_headers["Cache-Control"])
		return status, json.loads(response) if response.startswith(b"{") else response.decode()

	def collect_identity_pages(self, token, *, start=0):
		rows = []
		while True:
			status, response = self.identity_inventory({"start": start}, token)
			self.assertEqual(status, 200)
			page = response["message"]
			rows.extend(page["identities"])
			if not page["has_next_page"]:
				return rows
			self.assertTrue(page["identities"])
			start += len(page["identities"])

	def test_list_identities_returns_only_current_issuer_and_public_row_fields(self):
		prefix = f"zz-inventory-{uuid4().hex}"
		open_subject, closed_subject = f"{prefix}-1", f"{prefix}-3"
		tombstone_subject = f"{prefix}-2"
		other_issuer_subject = f"{prefix}-2b"
		for subject in (open_subject, closed_subject, tombstone_subject, other_issuer_subject):
			self.sign_in(subject, f"{subject}@example.test", uuid4().hex)

		frappe.init("press.localhost")
		frappe.connect()
		try:
			frappe.db.set_value("User", f"{closed_subject}@example.test", "enabled", 0)
			frappe.db.set_value(
				"PTR Identity Link",
				{"issuer": ISSUER, "subject": tombstone_subject},
				"issuer",
				"urn:press-tr:deleted-identity",
			)
			frappe.db.set_value(
				"PTR Identity Link",
				{"issuer": ISSUER, "subject": other_issuer_subject},
				"issuer",
				ISSUER.upper(),
			)
			frappe.db.commit()
		finally:
			frappe.destroy()

		token = self.token()
		rows = self.collect_identity_pages(token)
		subjects = [row["subject"] for row in rows]
		self.assertEqual(subjects, sorted(subjects))
		self.assertNotIn(tombstone_subject, subjects)
		self.assertNotIn(other_issuer_subject, subjects)
		self.assertTrue(all(set(row) == {"issuer", "subject", "enabled"} for row in rows))
		start = subjects.index(open_subject)
		status, first = self.identity_inventory({"start": start, "page_length": 1}, token)
		self.assertEqual(status, 200)
		self.assertEqual(
			first,
			{
				"message": {
					"identities": [{"issuer": ISSUER, "subject": open_subject, "enabled": True}],
					"has_next_page": True,
				},
			},
		)
		next_rows = self.collect_identity_pages(token, start=start + 1)
		self.assertEqual(
			next(row for row in next_rows if row["subject"] == closed_subject),
			{"issuer": ISSUER, "subject": closed_subject, "enabled": False},
		)
		status, final = self.identity_inventory({"start": len(subjects)}, token)
		self.assertEqual(status, 200)
		self.assertEqual(final, {"message": {"identities": [], "has_next_page": False}})
		status, distant = self.identity_inventory({"start": (1 << 64) - 1}, token)
		self.assertEqual(status, 200)
		self.assertEqual(distant, final)

	def test_list_identities_default_page_is_bounded_at_500(self):
		prefix = f"inventory-cap-{uuid4().hex}"
		fixtures = [f"{prefix}-{index:03d}" for index in range(501)]
		frappe.init("press.localhost")
		frappe.connect()
		try:
			frappe.db.bulk_insert(
				"PTR Identity Link",
				fields=["name", "issuer", "subject", "user"],
				values=[(name, ISSUER, name, f"{name}@example.test") for name in fixtures],
			)
			frappe.db.commit()
			token = self.token()
			status, first = self.identity_inventory({}, token)
			self.assertEqual(status, 200)
			self.assertEqual(len(first["message"]["identities"]), 500)
			self.assertTrue(first["message"]["has_next_page"])
			rows = first["message"]["identities"] + self.collect_identity_pages(token, start=500)
			self.assertEqual(
				[row for row in rows if row["subject"].startswith(prefix)],
				[{"issuer": ISSUER, "subject": fixture, "enabled": False} for fixture in fixtures],
			)
		finally:
			frappe.db.delete("PTR Identity Link", {"name": ["in", fixtures]})
			frappe.db.commit()
			frappe.destroy()

	def test_list_identities_rejects_untrusted_callers_and_parameters(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		signed_input, signature = self.token().rsplit(".", 1)
		bad_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
		for name, token, headers in (
			("missing", None, {}),
			("malformed", "not-a-token", {}),
			("bad_signature", f"{signed_input}.{bad_signature}", {}),
			("wrong_audience", self.token(audience="site-tenant1"), {}),
			("wrong_client", self.token(authorized_party="press-service"), {}),
			("wrong_issuer", self.token(iss="https://other.example.test"), {}),
			("expired", self.token(exp=int(time.time()) - 120), {}),
			("human_session", self.token(), session),
		):
			with self.subTest(caller=name):
				status, payload = self.identity_inventory({}, token, headers)
				self.assertEqual(status, 403)
				self.assertNotIn("message", payload if isinstance(payload, dict) else {})
		self.assertEqual(self.identity_inventory({"issuer": ISSUER}, self.token())[0], 403)
		self.assertEqual(self.identity_inventory({"cursor": "legacy"}, self.token())[0], 403)
		self.assertEqual(self.identity_inventory({"limit": 2}, self.token())[0], 403)
		self.assertIn(self.call("list_identities", {}, self.token())[0], {401, 403, 405})
		headers = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}
		status, _headers, _body = self.exchange(
			"GET", IDENTITY_INVENTORY_ROUTE, headers, json.dumps({"start": 1})
		)
		self.assertEqual(status, 403)
		for body in (
			{"start": True},
			{"start": -1},
			{"start": "2.0"},
			{"start": 1 << 64},
			{"page_length": True},
			{"page_length": 0},
			{"page_length": 501},
		):
			with self.subTest(body=body):
				self.assertEqual(self.identity_inventory(body, self.token())[0], 400)

	def test_first_binding_requires_verified_email_and_rejects_conflicts(self):
		subject = uuid4().hex
		body = {
			"issuer": ISSUER,
			"subject": subject,
			"email": f"{subject}@example.test",
			"organization_id": uuid4().hex,
			"email_verified": False,
		}
		token = self.token()
		self.assertEqual(self.call("ensure_team", body, token)[0], 403)
		verified = {**body, "email_verified": True}
		self.assertEqual(self.call("ensure_team", verified, token)[0], 200)
		self.assertEqual(self.call("ensure_team", {**verified, "subject": uuid4().hex}, token)[0], 403)

	def test_system_user_email_is_not_bound(self):
		subject = uuid4().hex
		body = {
			"issuer": ISSUER,
			"subject": subject,
			"email": "desk-user@example.test",
			"organization_id": uuid4().hex,
			"email_verified": True,
		}
		self.assertEqual(self.call("ensure_team", body, self.token())[0], 403)

	def test_rejects_expired_and_unsigned_service_tokens(self):
		body = {"issuer": ISSUER, "subject": "example", "organization_id": "example"}
		expired = self.token(exp=int(time.time()) - 120)
		unsigned = jwt.encode({"iss": ISSUER, "aud": "press", "azp": "identity-sync"}, None, algorithm="none")
		for token in (expired, unsigned):
			self.assertEqual(self.call("remove_team_member", body, token)[0], 403)

	def test_verified_service_request_with_guest_cookie(self):
		subject = uuid4().hex
		payload = {
			"issuer": ISSUER,
			"subject": subject,
			"email": f"{subject}@example.test",
			"organization_id": uuid4().hex,
			"email_verified": True,
		}
		status, _payload = self.call("ensure_team", payload, self.token(), {"Cookie": "sid=Guest"})
		self.assertEqual(status, 200)

	def test_team_and_membership_requests_are_repeatable(self):
		token = self.token()
		owner = uuid4().hex
		members = [uuid4().hex for _iteration in range(2)]
		organization_id = uuid4().hex

		def ensure(subject, **options):
			status, result = self.call(
				"ensure_team",
				{
					"issuer": ISSUER,
					"subject": subject,
					"email": f"{subject}@example.test",
					"organization_id": organization_id,
					"email_verified": True,
					**options,
				},
				token,
			)
			self.assertEqual(status, 200)
			return result["message"]

		with ThreadPoolExecutor(max_workers=2) as pool:
			first = pool.submit(ensure, owner, organization_name="Example Organization")
			same = pool.submit(ensure, owner, organization_name="Example Organization")
			team_results = [first.result(), same.result()]
		team = team_results[0]["team"]
		self.assertEqual(team_results[1]["team"], team)
		self.assertEqual(sum(result["created"] for result in team_results), 1)
		self.assertEqual(ensure(owner), {"team": team, "created": False})
		unmapped = {"issuer": ISSUER, "subject": owner, "organization_id": uuid4().hex}
		status, result = self.call("remove_team_member", unmapped, token)
		self.assertEqual(status, 200)
		self.assertEqual(result["message"], {"team": None, "member": False})
		with ThreadPoolExecutor(max_workers=len(members)) as pool:
			futures = [pool.submit(ensure, member) for member in members]
			memberships = [future.result() for future in futures]
		owner_cookie = self.sign_in(owner, f"{owner}@example.test", uuid4().hex)
		status, _headers, payload = self.exchange("GET", ACCOUNT_ROUTE, owner_cookie)
		self.assertEqual(status, 200)
		team_data = json.loads(payload)["message"]["team"]
		self.assertEqual(team_data["team_title"], "Example Organization")
		self.assertFalse(team_data["free_account"])
		stored_members = {user["email"] for user in json.loads(payload)["message"]["team_members"]}
		self.assertEqual(stored_members, {f"{subject}@example.test" for subject in [owner, *members]})
		first_member = self.sign_in(members[0], f"{members[0]}@example.test", uuid4().hex)
		status, _headers, payload = self.exchange("GET", ACCOUNT_ROUTE, first_member)
		self.assertEqual(status, 200)
		self.assertEqual([row["name"] for row in json.loads(payload)["message"]["teams"]], [team])
		for member, membership in zip(members, memberships, strict=True):
			self.assertEqual(ensure(member), membership)
			body = {"issuer": ISSUER, "subject": member, "organization_id": organization_id}
			for _iteration in range(2):
				status, result = self.call("remove_team_member", body, token)
				self.assertEqual(status, 200)
				self.assertEqual(result["message"], {"team": team, "member": False})
		member = members[1]
		member_cookie = self.sign_in(member, f"{member}@example.test", uuid4().hex)
		status, _headers, payload = self.exchange("GET", ACCOUNT_ROUTE, member_cookie)
		self.assertEqual(status, 200)
		self.assertNotIn(team, {row["name"] for row in json.loads(payload)["message"]["teams"]})

	def test_remove_team_member_requires_exactly_one_selector(self):
		body = {"issuer": ISSUER, "subject": uuid4().hex}
		token = self.token()
		for selectors in (
			{},
			{"organization_id": ""},
			{"organization_id": "   "},
			{"organization_id": 123},
			{"all_organizations": False},
			{"all_organizations": "true"},
			{"all_organizations": None},
			{"organization_id": "organization", "all_organizations": True},
			{"organization_id": "organization", "all_organizations": False},
			{"organization_id": None, "all_organizations": True},
		):
			with self.subTest(selectors=selectors):
				status, _payload = self.call("remove_team_member", body | selectors, token)
				self.assertEqual(status, 400)

	def test_remove_all_organizations_keeps_the_personal_team(self):
		member = uuid4().hex
		email = f"{member}@example.test"
		self.sign_in(member, email, uuid4().hex)
		token = self.token()
		organization_teams = []

		for _iteration in range(2):
			organization = uuid4().hex
			owner = uuid4().hex
			for subject in (owner, member):
				body = {
					"issuer": ISSUER,
					"subject": subject,
					"email": f"{subject}@example.test",
					"email_verified": True,
					"organization_id": organization,
				}
				status, result = self.call("ensure_team", body, token)
				self.assertEqual(status, 200)
			organization_teams.append(result["message"]["team"])

		body = {"issuer": ISSUER, "subject": member, "all_organizations": True}
		for _iteration in range(2):
			status, result = self.call("remove_team_member", body, token)
			self.assertEqual(status, 200)
			self.assertEqual(result["message"], {"team": None, "member": False})

		frappe.init("press.localhost")
		frappe.connect()
		try:
			self.assertFalse(frappe.db.get_value("User", email, "enabled"))
			teams = frappe.get_all(
				"Team Member", filters={"user": email, "parenttype": "Team"}, pluck="parent"
			)
			self.assertEqual(len(teams), 1)
			self.assertNotIn(teams[0], organization_teams)
			self.assertFalse(frappe.db.get_value("Team", teams[0], "custom_ptr_keycloak_org_id"))
		finally:
			frappe.destroy()

	def test_disabling_linked_user_revokes_api_key(self):
		from frappe.utils.password import set_encrypted_password

		subject = uuid4().hex
		email = f"{subject}@example.test"
		self.sign_in(subject, email, uuid4().hex)
		key, secret = uuid4().hex, uuid4().hex
		frappe.init("press.localhost")
		frappe.connect()
		try:
			frappe.db.set_value("User", email, "api_key", key)
			set_encrypted_password("User", email, secret, "api_secret")
			frappe.db.commit()
		finally:
			frappe.destroy()

		headers = {"Authorization": f"token {key}:{secret}"}
		self.assertEqual(self.exchange("GET", ACCOUNT_ROUTE, headers)[0], 200)
		body = {"issuer": ISSUER, "subject": subject}
		for _iteration in range(2):
			status, result = self.call("remove_team_member", body | {"all_organizations": True}, self.token())
			self.assertEqual(status, 200)
			self.assertEqual(result["message"], {"team": None, "member": False})
		self.assertIn(self.exchange("GET", ACCOUNT_ROUTE, headers)[0], {401, 403})
		frappe.init("press.localhost")
		frappe.connect()
		try:
			self.assertFalse(frappe.db.get_value("User", email, "api_key"))
			self.assertFalse(
				frappe.db.exists("__Auth", {"doctype": "User", "name": email, "fieldname": "api_secret"})
			)
		finally:
			frappe.destroy()

	def test_anonymize_user_preserves_linked_records_on_retry(self):
		from frappe.utils.password import set_encrypted_password

		subject = uuid4().hex
		email = f"{subject}@example.test"
		session = self.sign_in(subject, email, uuid4().hex)
		key, secret = uuid4().hex, uuid4().hex
		body = {"issuer": ISSUER, "subject": subject}
		frappe.init("press.localhost")
		frappe.connect()
		try:
			team = frappe.db.get_value("Team", {"user": email}, "name")
			self.assertTrue(team)
			invoice_name = f"anonymization-fixture-{subject}"
			# Persist a representative invoice without running Press billing hooks.
			frappe.get_doc({"doctype": "Invoice", "name": invoice_name, "team": team}).db_insert()
			frappe.db.set_value(
				"Invoice",
				invoice_name,
				{"owner": email, "modified_by": email, "customer_email": email},
				update_modified=False,
			)
			frappe.db.set_value("Team", team, {"billing_name": "Private", "phone_number": "5550100"})
			activity = frappe.get_doc(
				{
					"doctype": "Activity Log",
					"name": f"privacy-{subject}",
					"user": email,
					"full_name": "Private",
					"subject": "Private logged in",
					"ip_address": "198.18.0.1",
				}
			)
			activity.db_insert()
			activity_names = [activity.name]
			self.assertEqual(frappe.db.get_value("Invoice", invoice_name, "owner"), email)
			frappe.db.set_value("User", email, {"api_key": key, "phone": "5550100", "first_name": "Private"})
			set_encrypted_password("User", email, secret, "api_secret")
			contact = frappe.get_doc(
				{
					"doctype": "Contact",
					"user": email,
					"first_name": f"Private {subject}",
					"email_ids": [{"email_id": email, "is_primary": 1}],
					"phone_nos": [{"phone": "5550100", "is_primary_phone": 1}],
				}
			).insert(ignore_permissions=True)
			secondary = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": f"Secondary {subject}",
					"email_ids": [
						{"email_id": f"secondary-{subject}@example.test", "is_primary": 1},
						{"email_id": email},
					],
				}
			).insert(ignore_permissions=True)
			address = frappe.get_doc(
				{
					"doctype": "Address",
					"address_title": f"Private {subject}",
					"address_type": "Billing",
					"address_line1": "Private street",
					"city": "Fixture city",
					"country": frappe.db.get_value("Country", {}, "name"),
					"links": [{"link_doctype": "Contact", "link_name": contact.name}],
				}
			).insert(ignore_permissions=True)
			for _iteration in range(125):
				row = frappe.get_doc(
					{
						"doctype": "Activity Log",
						"user": email,
						"full_name": "Private",
					}
				)
				row.db_insert()
				activity_names.append(row.name)
			frappe.db.set_value(
				"Activity Log",
				{"name": ["in", activity_names]},
				{"owner": email, "modified_by": email},
				update_modified=False,
			)
			frappe.db.set_value("Team", team, {"owner": email, "modified_by": email}, update_modified=False)
			self.assertEqual(
				frappe.db.count(
					"Activity Log", {"name": ["in", activity_names], "owner": email, "modified_by": email}
				),
				126,
			)
			from frappe.utils.file_manager import save_file

			profile_file = save_file(
				f"privacy-{subject}.txt", b"private fixture", "User", email, is_private=1
			)
			attachment_note = frappe.get_doc("User", email).add_comment("Attachment", profile_file.file_name)
			public_file = save_file(f"public-{subject}.txt", subject.encode(), None, None, is_private=0)
			frappe.db.set_value("File", public_file.name, "owner", email, update_modified=False)
			shared_file = save_file(
				f"shared-{subject}.txt", f"shared-{subject}".encode(), "Team", team, is_private=0
			)
			frappe.db.set_value("File", shared_file.name, "owner", email, update_modified=False)
			version = frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": "User",
					"docname": email,
					"data": json.dumps({"changed": [["first_name", "Private", "Other"]]}),
				}
			)
			version.db_insert()
			communication = frappe.get_doc(
				{
					"doctype": "Communication",
					"sender": "sender@example.test",
					"recipients": f"Private <{email}>, other@example.test",
					"cc": f"Private <{email}>",
					"bcc": f"other@example.test, {email}",
					"content": "Hello Private",
					"text_content": "Hello Private in plain text",
					"reference_doctype": "User",
					"reference_name": email,
				}
			)
			communication.db_insert()
			comment = frappe.get_doc(
				{
					"doctype": "Comment",
					"comment_type": "Comment",
					"reference_doctype": "User",
					"reference_name": email,
					"content": "Existing comment",
				}
			)
			comment.db_insert()
			queue = frappe.get_doc(
				{
					"doctype": "Email Queue",
					"message": f"To: {email}\n\nHello Private",
					"show_as_cc": f"Private <{email}>, other@example.test",
					"status": "Not Sent",
				}
			)
			queue.db_insert()
			recipient = queue.append("recipients", {"recipient": email})
			recipient.db_insert()
			other_queue = frappe.get_doc({"doctype": "Email Queue", "message": "Unrelated message"})
			other_queue.db_insert()
			other_queue.append("recipients", {"recipient": f"other-{email}"}).db_insert()
			frappe.db.commit()
		finally:
			frappe.destroy()

		self.assertEqual(self.call("anonymize_user", body, self.token(), session)[0], 403)
		for _iteration in range(2):
			started = time.monotonic()
			status, result = self.call("anonymize_user", body, self.token())
			print(
				f"Account anonymization HTTP execution with 126 activity records: {time.monotonic() - started:.3f}s"
			)
			self.assertEqual(status, 200)
			self.assertEqual(result["message"], {"anonymized": True, "found": True})

		self.assertEqual(self.exchange("GET", ACCOUNT_ROUTE, session)[0], 403)
		self.assertIn(
			self.exchange("GET", ACCOUNT_ROUTE, {"Authorization": f"token {key}:{secret}"})[0], {401, 403}
		)
		self.sign_in(subject, email, uuid4().hex, expected_status=403)
		frappe.init("press.localhost")
		frappe.connect()
		try:
			self.assertFalse(frappe.db.exists("PTR Identity Link", body))
			self.assertFalse(frappe.db.get_value("Team", team, "enabled"))
			self.assertEqual(
				frappe.db.get_value("Team", team, ["billing_name", "phone_number"]), (None, None)
			)
			self.assertEqual(
				frappe.db.get_value("Activity Log", activity.name, ["full_name", "subject", "ip_address"]),
				("Deleted", "Account activity", None),
			)
			user = frappe.db.get_value("Team", team, "user")
			self.assertNotEqual(user, email)
			self.assertTrue(user.endswith("@invalid.example"))
			secret_key = frappe.conf.press_anonymization_hmac_key or frappe.conf.encryption_key
			expected_digest = hmac.new(
				secret_key.encode(), json.dumps([ISSUER, subject], separators=(",", ":")).encode(), "sha256"
			).hexdigest()
			self.assertEqual(
				frappe.db.get_value("PTR Identity Link", {"user": user}, "subject"), expected_digest
			)
			self.assertEqual(frappe.db.get_value("Team", team, "user"), user)
			self.assertEqual(
				frappe.db.get_value(
					"Invoice", invoice_name, ["team", "owner", "modified_by", "customer_email"]
				),
				(team, email, email, email),
			)
			with self.subTest(finding="E-1"):
				for doctype, name in (("Team", team), ("Activity Log", activity.name)):
					with self.subTest(doctype=doctype):
						self.assertEqual(
							frappe.db.get_value(doctype, name, ["owner", "modified_by"]), (user, user)
						)
				self.assertEqual(
					frappe.db.count(
						"Activity Log", {"name": ["in", activity_names], "owner": user, "modified_by": user}
					),
					126,
				)
			with self.subTest(finding="K-1"):
				for doctype, name in (("Comment", comment.name), ("Communication", communication.name)):
					self.assertEqual(frappe.db.get_value(doctype, name, "reference_name"), user)
					self.assertFalse(
						frappe.db.exists(doctype, {"reference_doctype": "User", "reference_name": email})
					)
			with self.subTest(finding="K-2"):
				self.assertFalse(frappe.db.exists("File", public_file.name))
				self.assertFalse(public_file.exists_on_disk())
				self.assertTrue(frappe.db.exists("File", shared_file.name))
				self.assertTrue(shared_file.exists_on_disk())
			with self.subTest(finding="K-2 retained file data"):
				self.assertFalse(
					frappe.db.exists(
						"Deleted Document",
						{
							"deleted_doctype": "File",
							"deleted_name": ["in", [profile_file.name, public_file.name]],
						},
					)
				)
				self.assertFalse(frappe.db.exists("Comment", attachment_note.name))
			with self.subTest(finding="Email queue redaction"):
				self.assertFalse(frappe.db.get_value("Email Queue", queue.name, "message"))
				self.assertEqual(
					frappe.db.get_value("Email Queue", queue.name, ["show_as_cc", "status"]),
					(f"{user}, other@example.test", "Error"),
				)
				self.assertEqual(
					frappe.db.get_value("Email Queue Recipient", recipient.name, "recipient"), user
				)
				self.assertEqual(
					frappe.db.get_value("Email Queue", other_queue.name, "message"), "Unrelated message"
				)
			with self.subTest(finding="Communication redaction"):
				self.assertEqual(
					frappe.db.get_value(
						"Communication", communication.name, ["cc", "bcc", "content", "text_content"]
					),
					(user, f"other@example.test, {user}", None, None),
				)
			self.assertFalse(frappe.db.exists("User", email))
			doc = frappe.get_doc("User", user)
			self.assertEqual(doc.email, user)
			self.assertEqual(doc.first_name, "Deleted")
			self.assertFalse(doc.phone)
			self.assertFalse(doc.enabled)
			self.assertFalse(doc.api_key)
			self.assertFalse(frappe.db.exists("Contact", contact.name))
			self.assertFalse(frappe.db.exists("Contact", secondary.name))
			self.assertFalse(frappe.db.exists("Address", address.name))
			self.assertFalse(frappe.db.exists("File", profile_file.name))
			self.assertFalse(frappe.db.exists("Version", version.name))
			self.assertEqual(
				frappe.db.get_value("Communication", communication.name, "recipients"),
				f"{user}, other@example.test",
			)
			contacts = frappe.get_all("Contact", filters={"user": user}, pluck="name")
			self.assertTrue(contacts)
			for name in contacts:
				profile = frappe.get_doc("Contact", name)
				self.assertEqual(profile.first_name, "Deleted")
				self.assertFalse(profile.email_ids)
				self.assertFalse(profile.phone_nos)
			self.assertFalse(
				frappe.db.exists(
					"__Auth", {"doctype": "User", "fieldname": "api_secret", "name": ("in", [email, user])}
				)
			)
		finally:
			frappe.destroy()

	def test_anonymize_unknown_identity_is_a_noop(self):
		body = {"issuer": ISSUER, "subject": uuid4().hex}
		self.assertEqual(
			self.call("anonymize_user", body, self.token()),
			(200, {"message": {"anonymized": True, "found": False}}),
		)

	def test_anonymize_requires_identity_sync_token(self):
		body = {"issuer": ISSUER, "subject": uuid4().hex}
		for token in (
			None,
			self.token(authorized_party="press-service"),
			self.token(audience="site-tenant1"),
			self.token(exp=int(time.time()) - 300),
		):
			with self.subTest(token_present=token is not None):
				self.assertEqual(self.call("anonymize_user", body, token)[0], 403)

	def test_anonymize_rejects_extra_fields(self):
		body = {"issuer": ISSUER, "subject": uuid4().hex, "extra": True}
		self.assertEqual(self.call("anonymize_user", body, self.token())[0], 403)

	def test_bulk_remove_disables_owner_and_preserves_team_ownership(self):
		owner, other_owner = uuid4().hex, uuid4().hex
		first_org, second_org = uuid4().hex, uuid4().hex
		token = self.token()
		teams = []
		for subject, organization in (
			(owner, first_org),
			(other_owner, second_org),
			(owner, second_org),
			(other_owner, first_org),
		):
			status, result = self.call(
				"ensure_team",
				{
					"issuer": ISSUER,
					"subject": subject,
					"email": f"{subject}@example.test",
					"email_verified": True,
					"organization_id": organization,
				},
				token,
			)
			self.assertEqual(status, 200)
			teams.append(result["message"]["team"])

		body = {"issuer": ISSUER, "subject": owner, "all_organizations": True}
		self.assertEqual(self.call("remove_team_member", body, token)[0], 200)
		self.assertEqual(self.call("remove_team_member", body | {"subject": other_owner}, token)[0], 200)
		email = f"{owner}@example.test"
		frappe.init("press.localhost")
		frappe.connect()
		try:
			self.assertFalse(frappe.db.get_value("User", email, "enabled"))
			self.assertFalse(frappe.db.get_value("User", f"{other_owner}@example.test", "enabled"))
			self.assertEqual(frappe.db.get_value("Team", teams[0], "user"), email)
			self.assertFalse(
				frappe.db.exists(
					"Team Member",
					{
						"parent": ["in", teams],
						"parenttype": "Team",
						"user": email,
					},
				)
			)
		finally:
			frappe.destroy()

	def test_press_website_user_cannot_open_frappe_desk(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		self.assertEqual(self.exchange("GET", ACCOUNT_ROUTE, session)[0], 200)

		status, headers, _body = self.exchange("GET", "/app", session)
		self.assertIn(status, {301, 302, 307, 308})
		self.assertEqual(urlsplit(headers["Location"]).path, "/desk")
		for path in ("/desk", "/desk/build"):
			with self.subTest(path=path):
				self.assertEqual(self.exchange("GET", path, session)[0], 403)

	def test_signed_in_user_cannot_call_local_login_or_team_invitation(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _headers, payload = self.exchange("GET", ACCOUNT_ROUTE, session)
		self.assertEqual(status, 200)
		team = json.loads(payload)["message"]["team"]["name"]
		self.assertEqual(
			self.exchange("GET", "/api/method/press.api.account.send_login_link", session)[0], 403
		)
		arguments = urlencode({"dt": "Team", "dn": team, "method": "invite_team_member"})
		status, _headers, _body = self.exchange(
			"GET", f"/api/method/press.api.client.run_doc_method?{arguments}", session
		)
		self.assertEqual(status, 403)

	def test_ensure_team_adds_member_when_recorded_owner_is_disabled(self):
		owner, member, organization = uuid4().hex, uuid4().hex, uuid4().hex
		token = self.token()

		def ensure(subject):
			return self.call(
				"ensure_team",
				{
					"issuer": ISSUER,
					"subject": subject,
					"email": f"{subject}@example.test",
					"email_verified": True,
					"organization_id": organization,
				},
				token,
			)

		status, result = ensure(owner)
		self.assertEqual(status, 200)
		team = result["message"]["team"]
		body = {"issuer": ISSUER, "subject": owner, "all_organizations": True}
		self.assertEqual(self.call("remove_team_member", body, token)[0], 200)
		for _iteration in range(2):
			status, result = ensure(member)
			self.assertEqual(status, 200)
			self.assertEqual(result["message"], {"team": team, "created": False, "owner_disabled": True})
		session = self.sign_in(member, f"{member}@example.test", uuid4().hex)
		status, _headers, payload = self.exchange("GET", ACCOUNT_ROUTE, session)
		self.assertEqual(status, 200)
		self.assertIn(team, {row["name"] for row in json.loads(payload)["message"]["teams"]})

	def start_login(self):
		status, headers, payload = self.exchange("POST", "/api/method/press_tr.api.auth.get_login_url")
		self.assertEqual(status, 200)
		query = parse_qs(urlsplit(json.loads(payload)["message"]["url"]).query)
		cookies = SimpleCookie()
		for header in headers.get_all("Set-Cookie"):
			cookies.load(header)
		browser = cookies["press_tr_login"].value
		return query, {"Cookie": f"press_tr_login={browser}"}

	def sign_in(self, subject, email, keycloak_sid, expected_status=302, *, other_browser=None, **overrides):
		query, state_cookie = self.start_login()
		state, nonce, challenge = (query[key][0] for key in ("state", "nonce", "code_challenge"))
		code = uuid4().hex
		self.codes[code] = (
			challenge,
			self.token(
				authorized_party="press",
				**{
					"sub": subject,
					"email": email,
					"email_verified": True,
					"sid": keycloak_sid,
					"nonce": nonce,
					**overrides,
				},
			),
		)
		callback = "/api/method/press_tr.api.auth.keycloak_callback?" + urlencode(
			{"state": state, "code": code}
		)
		if other_browser is not None:
			self.assertNotEqual(state_cookie, other_browser)
			status, _headers, _body = self.exchange("GET", callback, other_browser)
			self.assertEqual(status, 403)
			self.assertIn(code, self.codes)
		status, headers, _body = self.exchange("GET", callback, state_cookie)
		self.assertEqual(status, expected_status)
		if expected_status != 302:
			return None
		self.assertEqual(headers["Location"], "/dashboard")
		cookies = SimpleCookie()
		for value in headers.get_all("Set-Cookie"):
			cookies.load(value)
		sid = cookies["sid"].value
		self.assertNotEqual(sid, "Guest")
		status, _headers, _body = self.exchange("GET", callback, state_cookie)
		self.assertEqual(status, 403)

		return {"Cookie": f"sid={sid}"}

	def test_callback_validates_nonce_and_audience(self):
		for claims in ({"nonce": "wrong"}, {"audience": "wrong"}):
			subject = uuid4().hex
			self.sign_in(subject, f"{subject}@example.test", uuid4().hex, 403, **claims)

	def post_logout(self, token, prefix="/api/method/"):
		return self.exchange(
			"POST",
			prefix + "press_tr.api.keycloak_backchannel_logout",
			{"Content-Type": "application/x-www-form-urlencoded"},
			urlencode({"logout_token": token}),
		)[0]

	def test_logout_token_requires_events_and_accepts_both_selectors(self):
		event = {"http://schemas.openid.net/event/backchannel-logout": {}}
		subject, keycloak_sid = uuid4().hex, uuid4().hex
		common = {"sub": subject, "sid": keycloak_sid}
		with_nonce = self.token(
			authorized_party="press", **common, events=event, nonce="unexpected", jti=uuid4().hex
		)
		without_events = self.token(authorized_party="press", **common, jti=uuid4().hex)
		self.assertEqual(self.post_logout(with_nonce), 403)
		self.assertEqual(self.post_logout(without_events), 403)
		for claims in ({"sid": keycloak_sid, "sub": None}, {"sub": subject}):
			session = self.sign_in(subject, f"{subject}@example.test", keycloak_sid)
			token = self.token(authorized_party="press", **claims, events=event, jti=uuid4().hex)
			self.assertEqual(self.post_logout(token), 200)
			self.assertIn(self.exchange("GET", ACCOUNT_ROUTE, session)[0], {401, 403})

	def test_only_rejected_logout_tokens_reach_rate_limit(self):
		subject, sid = uuid4().hex, uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", sid)
		valid = self.token(
			authorized_party="press",
			sub=None,
			sid=sid,
			jti=uuid4().hex,
			events={"http://schemas.openid.net/event/backchannel-logout": {}},
		)
		for _iteration in range(120):
			self.assertEqual(self.post_logout("invalid-fixture"), 403)
		self.assertEqual(self.post_logout("invalid-fixture", "/api/v2/method/"), 429)
		# Seed the old shared ceiling without sending 1,200 requests.
		frappe.init("press.localhost")
		frappe.connect()
		try:
			limit_key = (
				frappe.cache.make_key(f"rl:press_tr.api.keycloak_backchannel_logout:{self.request_ip}")
				+ b":60"
			)
			frappe.cache.setex(limit_key, 60, 1200)
			self.assertEqual(self.post_logout(valid, "/api/v2/method/"), 200)
			self.assertEqual(int(frappe.cache.get(limit_key)), 1200)
			self.assertEqual(self.exchange("GET", ACCOUNT_ROUTE, session)[0], 403)
		finally:
			frappe.cache.delete(limit_key)
			frappe.destroy()
		self.assertEqual(self.request("POST", "/api/v2/method/press_tr.api.auth.get_login_url")[0], 200)

	def test_callback_and_backchannel_logout(self):
		subject = uuid4().hex
		keycloak_sid = uuid4().hex
		session_cookie = self.sign_in(subject, f"{subject}@example.test", keycloak_sid)
		status, _headers, _body = self.exchange("GET", ACCOUNT_ROUTE, session_cookie)
		self.assertEqual(status, 200)

		token = self.token(
			authorized_party="press",
			sub=subject,
			sid=keycloak_sid,
			jti=uuid4().hex,
			events={"http://schemas.openid.net/event/backchannel-logout": {}},
		)
		for _iteration in range(2):
			status, _headers, _body = self.exchange(
				"POST",
				"/api/method/press_tr.api.keycloak_backchannel_logout",
				{"Content-Type": "application/x-www-form-urlencoded"},
				urlencode({"logout_token": token}),
			)
			self.assertEqual(status, 200)

		status, _headers, _body = self.exchange("GET", ACCOUNT_ROUTE, session_cookie)
		self.assertIn(status, {401, 403})

	def request_recovery(self, email):
		status, _headers, body = self.exchange(
			"POST", RECOVERY_ROUTE, {"Content-Type": "application/json"}, json.dumps({"email": email})
		)
		return status, body

	def open_recovery_reviews(self, email):
		frappe.init("press.localhost")
		frappe.connect()
		try:
			link = frappe.db.get_value("PTR Identity Link", {"user": email}, "name")
			return frappe.get_all("PTR Recovery Review", {"identity_link": link, "status": "Open"}, pluck="name")
		finally:
			frappe.destroy()

	def test_guest_recovery_request_is_open_rate_limited_and_answers_the_same(self):
		# G-163: a person who lost their key cannot sign in, so the request works without a session.
		subject = uuid4().hex
		email = f"{subject}@example.test"
		self.sign_in(subject, email, uuid4().hex)
		known = self.request_recovery(email)
		unknown = self.request_recovery(f"nobody-{uuid4().hex}@example.test")
		self.assertEqual(known[0], 200)
		self.assertEqual(json.loads(known[1])["message"], {"received": True})
		# The answer does not show whether an account exists.
		self.assertEqual(unknown, known)
		self.assertEqual(len(self.open_recovery_reviews(email)), 1)
		# A repeated request does not stack open reviews.
		self.assertEqual(self.request_recovery(email), known)
		self.assertEqual(len(self.open_recovery_reviews(email)), 1)
		# The limit is 5 requests an hour from one address.
		for _iteration in range(2):
			self.assertEqual(self.request_recovery(f"nobody-{uuid4().hex}@example.test")[0], 200)
		self.assertEqual(self.request_recovery(email)[0], 429)

	def recovery_reviewer(self):
		from frappe.utils.password import set_encrypted_password

		email = f"reviewer-{uuid4().hex}@example.test"
		key, secret = uuid4().hex, uuid4().hex
		frappe.init("press.localhost")
		frappe.connect()
		try:
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Reviewer",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "System Manager"}],
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value("User", email, "api_key", key)
			set_encrypted_password("User", email, secret, "api_secret")
			frappe.db.commit()
		finally:
			frappe.destroy()
		return {"Authorization": f"token {key}:{secret}", "Content-Type": "application/json"}

	def test_recovery_decision_compares_dates_by_value(self):
		# AJA-410: the stored date sent back in Frappe form or in ISO form with "T" is the same moment.
		reviewer = self.recovery_reviewer()
		for form in ("frappe", "iso", "changed"):
			with self.subTest(form=form):
				subject = uuid4().hex
				email = f"{subject}@example.test"
				self.sign_in(subject, email, uuid4().hex)
				self.assertEqual(self.request_recovery(email)[0], 200)
				(name,) = self.open_recovery_reviews(email)
				status, _headers, body = self.exchange("GET", f"{RECOVERY_RESOURCE}/{name}", reviewer)
				self.assertEqual(status, 200)
				requested_at = json.loads(body)["data"]["requested_at"]
				value = {
					"frappe": requested_at,
					"iso": requested_at.replace(" ", "T"),
					"changed": "2000-01-01T00:00:00",
				}[form]
				decision = {
					"status": "Approved",
					"review_note": "Identity confirmed by phone call.",
					"requested_at": value,
				}
				status, _headers, _body = self.exchange(
					"PUT", f"{RECOVERY_RESOURCE}/{name}", reviewer, json.dumps(decision)
				)
				self.assertEqual(status, 403 if form == "changed" else 200)
