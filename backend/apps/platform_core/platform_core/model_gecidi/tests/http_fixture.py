"""Seed and exercise a disposable Frappe site through its real HTTP server."""

import json
import unittest
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

import frappe
import frappe.app
import requests
from frappe.utils import add_to_date, now_datetime
from werkzeug.serving import WSGIRequestHandler, make_server

from platform_core.api.test_model import TestModelHTTP

TEST_SITE = "test-platform-core.localhost"
FIXTURE_PORT = 19091
FIRST_URL = f"http://127.0.0.1:{FIXTURE_PORT}/first"
SECOND_URL = f"http://127.0.0.1:{FIXTURE_PORT}/second"


class ProviderHandler(BaseHTTPRequestHandler):
	def log_message(self, _format, *_args):
		pass

	def do_POST(self):
		payload = self.rfile.read(int(self.headers["Content-Length"]))
		self.server.attempts.append(self.path)
		self.server.provider_payloads.append(payload)
		if self.server.stall_headers is not None:
			self._stall_headers(self.server.stall_headers)
			return
		if self.server.provider_gate is not None:
			self.server.provider_gate(self.path)
		status = self.server.provider_status.get(self.path)
		if status is not None and status != 200:
			response = {"error": "fixture provider failure"}
		elif self.path in {"/first/api/chat", "/second/api/chat"}:
			status, response = (
				200,
				{
					"message": {"role": "assistant", "content": "Fixture reply"},
					"prompt_eval_count": 4,
					"eval_count": 3,
				},
			)
		else:
			status, response = 404, {"error": "unknown fixture endpoint"}
		payload = json.dumps(response).encode()
		self.send_response(status)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(payload)))
		self.end_headers()
		try:
			self.wfile.write(payload)
		except (BrokenPipeError, ConnectionResetError):
			# A deadline test intentionally disconnects before the provider replies.
			pass

	def _stall_headers(self, release):
		"""Keep the socket active while leaving the HTTP headers incomplete."""
		try:
			self.wfile.write(b"HTTP/1.0 200 OK\r\n")
			while not release.wait(1):
				self.wfile.write(b"X-Fixture-Pulse: 1\r\n")
		except (BrokenPipeError, ConnectionResetError):
			pass


def _insert(doctype, **fields):
	return frappe.get_doc({"doctype": doctype, **fields}).insert().name


def _identities(suffix, password, role, auth, cleanup):
	users = {}
	roles = {"manager": "AI Manager", "system_manager": "System Manager", "authorized": role}
	for actor in ("manager", "regular", "authorized", "system_manager"):
		credentials = {"api_key": auth[actor][0], "api_secret": auth[actor][1]} if actor in auth else {}
		users[actor] = _insert(
			"User",
			email=f"gateway-{actor}-{suffix}@example.test",
			first_name=f"Gateway fixture {actor}",
			send_welcome_email=0,
			new_password=password,
			roles=[{"role": roles[actor]}] if actor in roles else [],
			**credentials,
		)
		cleanup.callback(frappe.delete_doc, "User", users[actor])
	return users


def _seed(suffix, credential, role, cleanup):
	def insert(doctype, **fields):
		name = _insert(doctype, **fields)
		cleanup.callback(frappe.delete_doc, doctype, name)
		return name

	provider = insert("AI Provider", provider_name=f"Local {suffix}", adapter="ollama")
	accounts = [
		insert("AI Account", provider=provider, account_name=f"{position} account {suffix}", currency="USD")
		for position in ("First", "Second")
	]
	model_id = f"fixture-model-{suffix}"
	model = insert("AI Model", provider=provider, model_id=model_id, context_size=4096, cost_currency="USD")
	apis = [
		insert(
			"AI API",
			account=account,
			api_name=f"API {index} {suffix}",
			base_url=url,
			auth_type="none",
			allowed_models=json.dumps([model_id]),
			priority=index,
		)
		for index, (account, url) in enumerate(zip(accounts, (FIRST_URL, SECOND_URL), strict=True), 1)
	]
	route = insert(
		"AI Route",
		route_name=f"Local route {suffix}",
		selection_mode="priority",
		targets=[{"model": model, "api": api} for api in apis],
		data_policy="local_only",
	)
	role_route = insert(
		"AI Route",
		route_name=f"Role route {suffix}",
		selection_mode="priority",
		targets=[{"model": model, "api": apis[1]}],
		data_policy="local_only",
		required_role=role,
	)
	locked_provider = insert("AI Provider", provider_name=f"Credential {suffix}", adapter="openai")
	locked_account = insert("AI Account", provider=locked_provider, account_name=f"Private account {suffix}")

	def credential_api(display):
		return insert(
			"AI API",
			account=locked_account,
			api_name=f"{display} API {suffix}",
			base_url="https://fixture.example.test",
			auth_type="api_key",
			api_key=credential,
		)

	credential_read_api = credential_api("Private")
	editable_api = credential_api("Editable")
	clearable_api = credential_api("Clearable")

	for api in apis:
		cleanup.callback(_remove_usage, api)
	return {
		"first_account": accounts[0],
		"second_account": accounts[1],
		"model": model,
		"first_api": apis[0],
		"second_api": apis[1],
		"route": route,
		"role_route": role_route,
		"credential_api": credential_read_api,
		"editable_api": editable_api,
		"clearable_api": clearable_api,
		"credential": credential,
	}


def _remove_usage(api):
	for name in frappe.get_all("AI Usage Log", filters={"api": api}, pluck="name"):
		frappe.delete_doc("AI Usage Log", name)


def _session(base, user=None, password=None):
	session = requests.Session()
	session.trust_env = False
	session.headers["Host"] = TEST_SITE
	if user:
		login = session.post(
			base + "/api/method/login",
			json={"usr": user, "pwd": password},
			timeout=15,
			allow_redirects=False,
		)
		sid = session.cookies.get("sid")
		if login.status_code != 200 or not sid or sid == "Guest":
			session.close()
			raise RuntimeError(f"Fixture login failed (HTTP {login.status_code})")
		data = frappe.cache.hget("session", sid)
		if data and (csrf := data.get("data", {}).get("csrf_token")):
			session.headers["X-Frappe-CSRF-Token"] = csrf
	return session


def _oauth_session(base, user, cleanup):
	client = _insert(
		"OAuth Client",
		app_name=f"Gateway fixture {uuid4().hex[:12]}",
		default_redirect_uri="https://fixture.example.test/callback",
		redirect_uris="https://fixture.example.test/callback",
		scopes="all",
		grant_type="Authorization Code",
		response_type="Code",
	)
	cleanup.callback(frappe.delete_doc, "OAuth Client", client)
	token = _insert(
		"OAuth Bearer Token",
		client=client,
		user=user,
		scopes="all",
		access_token=uuid4().hex,
		expiration_time=add_to_date(now_datetime(), minutes=10),
		expires_in=600,
		status="Active",
	)
	cleanup.callback(frappe.delete_doc, "OAuth Bearer Token", token)
	frappe.db.commit()
	session = _session(base)
	session.headers["Authorization"] = f"Bearer {token}"
	return session


class QuietRequestHandler(WSGIRequestHandler):
	def log(self, _type, _message, *_args):
		pass


@contextmanager
def _fixture_webserver(wrap_app=None):
	"""Test the real WSGI entry point without a development-server policy bypass."""

	application = frappe.app.application
	if wrap_app is not None:
		application = wrap_app(application)
	with (
		patch.object(frappe.app, "_sites_path", frappe.local.sites_path),
		make_server(
			"127.0.0.1",
			0,
			application,
			threaded=True,
			request_handler=QuietRequestHandler,
		) as web,
	):
		thread = Thread(target=web.serve_forever, daemon=True)
		thread.start()
		try:
			yield f"http://127.0.0.1:{web.server_port}"
		finally:
			web.shutdown()
			thread.join()


@contextmanager
def _configured_fixture(wrap_app=None):
	if frappe.local.site != TEST_SITE or not frappe.conf.get("allow_tests"):
		raise RuntimeError("The HTTP fixture requires the isolated test site")
	if any(
		frappe.conf.get("model_gateway_endpoints", {}).get(url)
		!= {"kind": "local", "addresses": ["127.0.0.1"]}
		for url in (FIRST_URL, SECOND_URL)
	):
		raise RuntimeError("Configure both loopback model gateway fixture endpoints first")

	suffix = uuid4().hex[:12]
	password = f"Fixture#{uuid4().hex}"
	credential = f"test-only-{uuid4().hex}"
	auth = {actor: (uuid4().hex, uuid4().hex) for actor in ("authorized", "manager")}
	frappe.set_user("Administrator")
	try:
		with ExitStack() as cleanup:
			# Direct gateway RPC is exercised with a non-manager Desk user.
			role = _insert("Role", role_name=f"Gateway fixture caller {suffix}", desk_access=1)
			cleanup.callback(frappe.delete_doc, "Role", role)
			users = _identities(suffix, password, role, auth, cleanup)
			fixture = _seed(suffix, credential, role, cleanup)
			frappe.db.commit()
			with ExitStack() as connections:
				server = connections.enter_context(
					ThreadingHTTPServer(("127.0.0.1", FIXTURE_PORT), ProviderHandler)
				)
				server.attempts = []
				server.provider_status = {}
				server.provider_gate = None
				server.provider_payloads = []
				server.stall_headers = None
				thread = Thread(target=server.serve_forever, daemon=True)
				thread.start()
				connections.callback(thread.join)
				connections.callback(server.shutdown)
				base = connections.enter_context(_fixture_webserver(wrap_app))
				fixture.update(
					base=base,
					users=users,
					attempts=server.attempts,
					provider_status=server.provider_status,
					provider_payloads=server.provider_payloads,
					provider_url=SECOND_URL,
					provider_server=server,
					sessions={"guest": connections.enter_context(_session(base))},
				)
				for actor, user in users.items():
					fixture["sessions"][actor] = connections.enter_context(_session(base, user, password))
				fixture["sessions"]["oauth"] = connections.enter_context(
					_oauth_session(base, users["manager"], cleanup)
				)
				for actor, session_name in (("authorized", "api_key"), ("manager", "manager_key")):
					key, secret = auth[actor]
					session = connections.enter_context(_session(base))
					session.headers["Authorization"] = f"token {key}:{secret}"
					fixture["sessions"][session_name] = session
				yield fixture
	finally:
		frappe.db.commit()


def run():
	"""Run via bench execute on an isolated test site's own web container."""
	with _configured_fixture() as fixture:
		TestModelHTTP.fixture = fixture
		try:
			suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestModelHTTP)
			result = unittest.TextTestRunner(verbosity=2).run(suite)
		finally:
			TestModelHTTP.fixture = None
	if not result.wasSuccessful():
		raise RuntimeError("Model gateway HTTP checks failed")


def run_deadline():
	"""Measure a complete real Frappe HTTP request against a stalled loopback provider."""
	with _configured_fixture() as fixture:
		frappe.db.set_value(
			"AI Account", fixture["second_account"], {"has_monthly_budget": 1, "monthly_budget": 1}
		)
		frappe.db.set_value("AI Model", fixture["model"], {"prices_known": 1, "output_price": 1})
		frappe.db.commit()
		release = Event()
		fixture["provider_server"].stall_headers = release
		started = monotonic()
		try:
			response = fixture["sessions"]["manager"].post(
				fixture["base"] + "/api/method/platform_core.api.model.complete",
				json={
					"route": fixture["role_route"],
					"messages": [{"role": "user", "content": "Deadline fixture"}],
					"limit": 1380,
				},
				timeout=65,
			)
		finally:
			release.set()
		elapsed = monotonic() - started
		evidence = {
			"elapsed_seconds": round(elapsed, 3),
			"status": response.status_code,
			"error": response.json().get("message"),
			"provider_attempts": len(fixture["attempts"]),
		}
		print(json.dumps(evidence))
		if not (
			59 <= elapsed <= 60
			and response.status_code == 503
			and evidence["error"] == {"error": "provider_timeout"}
			and evidence["provider_attempts"] == 1
		):
			raise RuntimeError("Gateway deadline regression failed")
		return evidence
