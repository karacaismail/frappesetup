"""Exercise identity HTTP routes with an ephemeral local OIDC issuer."""

import base64
import hashlib
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from test_auth_http import PressHttpClient

ISSUER = "http://keycloak.example.test/realms/platform"
KID = uuid4().hex
ACCOUNT_ROUTE = "/api/method/press.api.account.get"


class IdentityHttpTest(PressHttpClient, unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
		jwk.update(kid=KID, alg="RS256", use="sig")
		jwks = json.dumps({"keys": [jwk]}).encode()

		cls.codes = {}

		class IssuerHandler(BaseHTTPRequestHandler):
			def do_GET(self):
				if self.path != "/realms/platform/protocol/openid-connect/certs":
					self.send_error(404)
					return
				self.send_json(jwks)

			def do_POST(self):
				if self.path != "/realms/platform/protocol/openid-connect/token":
					self.send_error(404)
					return
				values = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
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

			def send_json(self, body):
				self.send_response(200)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
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
			{**fields, **claims},
			self.key,
			algorithm="RS256",
			headers={"kid": KID},
		)

	def call(self, method, body, token=None, extra_headers=None):
		headers = {"Content-Type": "application/json", **(extra_headers or {})}
		if token:
			headers["Authorization"] = f"Bearer {token}"
		status, _, response = self.exchange(
			"POST", f"/api/method/press_tr.api.identity.{method}", headers, json.dumps(body)
		)
		return status, json.loads(response)

	def test_service_rejects_wrong_credentials(self):
		for method in ("ensure_team", "remove_team_member"):
			for token, headers in (
				(None, {}),
				(self.token(audience="site-kiraci1"), {}),
				(self.token(authorized_party="press-service"), {}),
				(self.token(), {"Cookie": "sid=Guest"}),
			):
				with self.subTest(method=method, headers=headers):
					status, _ = self.call(
						method, {"issuer": ISSUER, "subject": "example", "team": "example"}, token, headers
					)
					self.assertEqual(status, 403)
			for extra in ({"cmd": "ping"}, {"organization_id": "unmapped"}):
				with self.subTest(method=method, extra=extra):
					body = {"issuer": ISSUER, "subject": "example", "team": "example", **extra}
					status, _ = self.call(method, body, self.token())
					self.assertEqual(status, 403)

	def test_team_and_membership_requests_are_repeatable(self):
		token = self.token()
		owner = uuid4().hex
		members = [uuid4().hex for _ in range(2)]

		def ensure(subject, **options):
			status, result = self.call(
				"ensure_team",
				{
					"issuer": ISSUER,
					"subject": subject,
					"email": f"{subject}@example.test",
					"email_verified": True,
					**options,
				},
				token,
			)
			self.assertEqual(status, 200, result)
			return result["message"]

		with ThreadPoolExecutor(max_workers=2) as pool:
			first = pool.submit(ensure, owner)
			same = pool.submit(ensure, owner)
			personal_team = first.result()
			self.assertEqual(same.result(), personal_team)
		self.assertEqual(ensure(owner), personal_team)
		# Bind first so the concurrent requests contend on the same Team.
		for member in members:
			ensure(member)
		with ThreadPoolExecutor(max_workers=len(members)) as pool:
			futures = [pool.submit(ensure, member, team=personal_team["team"]) for member in members]
			memberships = [future.result() for future in futures]
		owner_cookie = self.sign_in(owner, f"{owner}@example.test", uuid4().hex)
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, owner_cookie)
		self.assertEqual(status, 200)
		stored_members = {user["email"] for user in json.loads(payload)["message"]["team_members"]}
		self.assertEqual(stored_members, {f"{subject}@example.test" for subject in [owner, *members]})
		for member, membership in zip(members, memberships, strict=True):
			self.assertEqual(ensure(member, team=personal_team["team"]), membership)
			body = {"issuer": ISSUER, "subject": member, "team": personal_team["team"]}
			for _ in range(2):
				status, result = self.call("remove_team_member", body, token)
				self.assertEqual(status, 200, result)
				self.assertEqual(result["message"], {"team": personal_team["team"], "member": False})
		member = members[0]
		member_cookie = self.sign_in(member, f"{member}@example.test", uuid4().hex)
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, member_cookie)
		self.assertEqual(status, 200)
		self.assertNotIn(
			personal_team["team"], {team["name"] for team in json.loads(payload)["message"]["teams"]}
		)

	def sign_in(self, subject, email, keycloak_sid):
		status, _, payload = self.exchange("POST", "/api/method/press_tr.api.auth.get_login_url")
		self.assertEqual(status, 200)
		query = parse_qs(urlsplit(json.loads(payload)["message"]["url"]).query)
		state, nonce, challenge = (query[key][0] for key in ("state", "nonce", "code_challenge"))
		code = uuid4().hex
		self.codes[code] = (
			challenge,
			self.token(
				authorized_party="press",
				sub=subject,
				email=email,
				email_verified=True,
				sid=keycloak_sid,
				nonce=nonce,
			),
		)
		callback = "/api/method/press_tr.api.auth.keycloak_callback?" + urlencode(
			{"state": state, "code": code}
		)
		state_cookie = {"Cookie": f"press_tr_login={state}"}
		status, headers, payload = self.exchange("GET", callback, state_cookie)
		self.assertEqual(status, 302, payload)
		self.assertEqual(headers["Location"], "/dashboard")
		cookies = SimpleCookie()
		for value in headers.get_all("Set-Cookie"):
			cookies.load(value)
		sid = cookies["sid"].value
		self.assertNotEqual(sid, "Guest")
		status, _, _ = self.exchange("GET", callback, state_cookie)
		self.assertEqual(status, 403)

		return {"Cookie": f"sid={sid}"}

	def test_callback_and_backchannel_logout(self):
		subject = uuid4().hex
		keycloak_sid = uuid4().hex
		session_cookie = self.sign_in(subject, f"{subject}@example.test", keycloak_sid)
		status, _, _ = self.exchange("GET", ACCOUNT_ROUTE, session_cookie)
		self.assertEqual(status, 200)

		token = self.token(
			authorized_party="press",
			sub=subject,
			sid=keycloak_sid,
			jti=uuid4().hex,
			events={"http://schemas.openid.net/event/backchannel-logout": {}},
		)
		for _ in range(2):
			status, _, payload = self.exchange(
				"POST",
				"/api/method/press_tr.api.keycloak_backchannel_logout",
				{"Content-Type": "application/x-www-form-urlencoded"},
				urlencode({"logout_token": token}),
			)
			self.assertEqual(status, 200, payload)

		status, _, _ = self.exchange("GET", ACCOUNT_ROUTE, session_cookie)
		self.assertIn(status, {401, 403})
