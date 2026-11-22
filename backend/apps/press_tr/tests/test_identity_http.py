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

import frappe
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
			{name: value for name, value in (fields | claims).items() if value is not None},
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
			):
				with self.subTest(method=method, headers=headers):
					status, _ = self.call(
						method,
						{"issuer": ISSUER, "subject": "example", "organization_id": "example"},
						token,
						headers,
					)
					self.assertEqual(status, 403)
			for extra in ({"cmd": "ping"}, {"team": "legacy"}):
				with self.subTest(method=method, extra=extra):
					body = {"issuer": ISSUER, "subject": "example", "organization_id": "example", **extra}
					status, _ = self.call(method, body, self.token())
					self.assertEqual(status, 403)

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
		status, result = self.call("ensure_team", payload, self.token(), {"Cookie": "sid=Guest"})
		self.assertEqual(status, 200, result)

	def test_team_and_membership_requests_are_repeatable(self):
		token = self.token()
		owner = uuid4().hex
		members = [uuid4().hex for _ in range(2)]
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
			self.assertEqual(status, 200, result)
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
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, owner_cookie)
		self.assertEqual(status, 200)
		team_data = json.loads(payload)["message"]["team"]
		self.assertEqual(team_data["team_title"], "Example Organization")
		self.assertFalse(team_data["free_account"])
		stored_members = {user["email"] for user in json.loads(payload)["message"]["team_members"]}
		self.assertEqual(stored_members, {f"{subject}@example.test" for subject in [owner, *members]})
		first_member = self.sign_in(members[0], f"{members[0]}@example.test", uuid4().hex)
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, first_member)
		self.assertEqual(status, 200)
		self.assertEqual([row["name"] for row in json.loads(payload)["message"]["teams"]], [team])
		for member, membership in zip(members, memberships, strict=True):
			self.assertEqual(ensure(member), membership)
			body = {"issuer": ISSUER, "subject": member, "organization_id": organization_id}
			for _ in range(2):
				status, result = self.call("remove_team_member", body, token)
				self.assertEqual(status, 200, result)
				self.assertEqual(result["message"], {"team": team, "member": False})
		member = members[1]
		member_cookie = self.sign_in(member, f"{member}@example.test", uuid4().hex)
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, member_cookie)
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
				status, result = self.call("remove_team_member", body | selectors, token)
				self.assertEqual(status, 400, result)

	def test_remove_all_organizations_keeps_the_personal_team(self):
		member = uuid4().hex
		email = f"{member}@example.test"
		self.sign_in(member, email, uuid4().hex)
		token = self.token()
		organization_teams = []

		for _ in range(2):
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
				self.assertEqual(status, 200, result)
			organization_teams.append(result["message"]["team"])

		body = {"issuer": ISSUER, "subject": member, "all_organizations": True}
		for _ in range(2):
			status, result = self.call("remove_team_member", body, token)
			self.assertEqual(status, 200, result)
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
			self.assertFalse(frappe.db.get_value("Team", teams[0], "keycloak_org_id"))
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
		for _ in range(2):
			status, result = self.call("remove_team_member", body | {"all_organizations": True}, self.token())
			self.assertEqual(status, 200, result)
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
			frappe.db.set_value("Invoice", invoice_name, "owner", email)
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
			frappe.db.commit()
		finally:
			frappe.destroy()

		for _ in range(2):
			status, result = self.call("anonymize_user", body, self.token())
			self.assertEqual(status, 200, result)
			self.assertEqual(result["message"], {"anonymized": True})

		self.assertEqual(self.exchange("GET", ACCOUNT_ROUTE, session)[0], 403)
		frappe.init("press.localhost")
		frappe.connect()
		try:
			user = frappe.db.get_value("Press Identity Link", body, "user")
			self.assertNotEqual(user, email)
			self.assertTrue(user.endswith("@invalid.example"))
			self.assertEqual(frappe.db.get_value("Team", team, "user"), user)
			self.assertEqual(frappe.db.get_value("Invoice", invoice_name, ["team", "owner"]), (team, user))
			self.assertFalse(
				any(
					email in (content or "")
					for content in frappe.get_all(
						"Comment", {"reference_name": user, "comment_type": "Edit"}, pluck="content"
					)
				)
			)
			self.assertFalse(frappe.db.exists("User", email))
			doc = frappe.get_doc("User", user)
			self.assertEqual(doc.email, user)
			self.assertEqual(doc.first_name, "Deleted")
			self.assertFalse(doc.phone)
			self.assertFalse(doc.enabled)
			self.assertFalse(doc.api_key)
			self.assertFalse(frappe.db.exists("Contact", contact.name))
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
			(200, {"message": {"anonymized": True}}),
		)

	def test_anonymize_requires_identity_sync_token(self):
		body = {"issuer": ISSUER, "subject": uuid4().hex}
		for token in (
			None,
			self.token(authorized_party="press-service"),
			self.token(audience="site-kiraci1"),
		):
			with self.subTest(token_present=token is not None):
				self.assertEqual(self.call("anonymize_user", body, token)[0], 403)

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
			self.assertEqual(status, 200, result)
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

	def test_signed_in_user_cannot_call_local_login_or_team_invitation(self):
		subject = uuid4().hex
		session = self.sign_in(subject, f"{subject}@example.test", uuid4().hex)
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, session)
		self.assertEqual(status, 200)
		team = json.loads(payload)["message"]["team"]["name"]
		self.assertEqual(
			self.exchange("GET", "/api/method/press.api.account.send_login_link", session)[0], 403
		)
		arguments = urlencode({"dt": "Team", "dn": team, "method": "invite_team_member"})
		status, _, _ = self.exchange(
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
		self.assertEqual(status, 200, result)
		team = result["message"]["team"]
		body = {"issuer": ISSUER, "subject": owner, "all_organizations": True}
		self.assertEqual(self.call("remove_team_member", body, token)[0], 200)
		for _ in range(2):
			status, result = ensure(member)
			self.assertEqual(status, 200, result)
			self.assertEqual(result["message"], {"team": team, "created": False, "owner_disabled": True})
		session = self.sign_in(member, f"{member}@example.test", uuid4().hex)
		status, _, payload = self.exchange("GET", ACCOUNT_ROUTE, session)
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
			status, _, _ = self.exchange("GET", callback, other_browser)
			self.assertEqual(status, 403)
			self.assertIn(code, self.codes)
		status, headers, payload = self.exchange("GET", callback, state_cookie)
		self.assertEqual(status, expected_status, payload)
		if expected_status != 302:
			return None
		self.assertEqual(headers["Location"], "/dashboard")
		cookies = SimpleCookie()
		for value in headers.get_all("Set-Cookie"):
			cookies.load(value)
		sid = cookies["sid"].value
		self.assertNotEqual(sid, "Guest")
		status, _, _ = self.exchange("GET", callback, state_cookie)
		self.assertEqual(status, 403)

		return {"Cookie": f"sid={sid}"}

	def test_callback_rejects_a_second_browser_without_consuming_the_first_login(self):
		_, other_browser = self.start_login()
		subject = uuid4().hex
		self.sign_in(subject, f"{subject}@example.test", uuid4().hex, other_browser=other_browser)

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
		common = {"sub": subject, "sid": keycloak_sid, "events": event}
		self.assertEqual(
			self.post_logout(self.token(authorized_party="press", **common, nonce="unexpected")), 403
		)
		self.assertEqual(
			self.post_logout(self.token(authorized_party="press", sub=subject, sid=keycloak_sid)), 403
		)
		for claims in ({"sid": keycloak_sid, "sub": None}, {"sub": subject}):
			session = self.sign_in(subject, f"{subject}@example.test", keycloak_sid)
			token = self.token(authorized_party="press", **claims, events=event)
			self.assertEqual(self.post_logout(token), 200)
			self.assertIn(self.exchange("GET", ACCOUNT_ROUTE, session)[0], {401, 403})

	def test_only_rejected_logout_tokens_reach_rate_limit(self):
		valid = self.token(
			authorized_party="press",
			sub=None,
			sid=uuid4().hex,
			events={"http://schemas.openid.net/event/backchannel-logout": {}},
		)
		for _ in range(120):
			self.assertEqual(self.post_logout("invalid-fixture"), 403)
		self.assertEqual(self.post_logout("invalid-fixture", "/api/v2/method/"), 429)
		self.assertEqual(self.post_logout(valid, "/api/v2/method/"), 200)
		self.assertEqual(self.request("POST", "/api/v2/method/press_tr.api.auth.get_login_url")[0], 200)

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
