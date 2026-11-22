"""Seed and exercise a disposable Frappe site through its real HTTP server."""

import hashlib
import json
import secrets
import unittest
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import frappe
import requests

from platform_core.api.test_model import TestModelHTTP

TEST_SITE = "test-platform-core.localhost"
FIXTURE_PORT = 19091
FIRST_URL = f"http://127.0.0.1:{FIXTURE_PORT}/first"
SECOND_URL = f"http://127.0.0.1:{FIXTURE_PORT}/second"


class ProviderHandler(BaseHTTPRequestHandler):
	def log_message(self, _format, *_args):
		pass

	def do_POST(self):
		self.rfile.read(int(self.headers["Content-Length"]))
		self.server.attempts.append(self.path)
		if self.path == "/first/api/chat":
			status, response = 429, {"error": "fixture rate limit"}
		elif self.path == "/second/api/chat":
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
		self.wfile.write(payload)


def _insert(doctype, **fields):
	return frappe.get_doc({"doctype": doctype, **fields}).insert().name


def _identities(suffix, password, cleanup):
	users = {}
	for actor in ("manager", "regular"):
		users[actor] = _insert(
			"User",
			email=f"gateway-{actor}-{suffix}@example.test",
			first_name=f"Gateway fixture {actor}",
			send_welcome_email=0,
			new_password=password,
			roles=[{"role": "AI Manager"}] if actor == "manager" else [],
		)
		cleanup.callback(frappe.delete_doc, "User", users[actor])
	return users


def _seed(suffix, credential, cleanup):
	def insert(doctype, **fields):
		name = _insert(doctype, **fields)
		cleanup.callback(frappe.delete_doc, doctype, name)
		return name

	provider = insert("AI Provider", provider_name=f"Local {suffix}", adapter="ollama")
	accounts = [
		insert("AI Account", provider=provider, account_name=f"{position} account {suffix}")
		for position in ("First", "Second")
	]
	model_id = f"fixture-model-{suffix}"
	model = insert("AI Model", provider=provider, model_id=model_id, context_size=4096)
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
		targets=json.dumps([{"model": model, "api": api} for api in apis]),
		data_policy="local_only",
	)
	locked_provider = insert("AI Provider", provider_name=f"Credential {suffix}", adapter="openai")
	locked_account = insert("AI Account", provider=locked_provider, account_name=f"Private account {suffix}")
	credential_api = insert(
		"AI API",
		account=locked_account,
		api_name=f"Credential API {suffix}",
		base_url="https://fixture.example.test",
		auth_type="api_key",
		api_key=credential,
	)
	for api in apis:
		cleanup.callback(_remove_usage, api)
	return {
		"first_account": accounts[0],
		"second_account": accounts[1],
		"model": model,
		"first_api": apis[0],
		"second_api": apis[1],
		"route": route,
		"credential_api": credential_api,
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


def _agent_session(base, manager, user, cleanup):
	token = "fsat_" + secrets.token_urlsafe(32)
	key = "ai_agent_token:" + hashlib.sha256(token.encode()).hexdigest()
	counter_key = frappe.cache.make_key(key + ":calls")
	frappe.cache.set_value(
		key,
		{
			"user": user,
			"sid": manager.cookies["sid"],
			"audience": frappe.conf.get("ai_agent_audience") or "agent-service",
		},
		expires_in_sec=300,
	)
	frappe.cache.set(counter_key, 1, ex=300)
	cleanup.callback(frappe.cache.delete_value, key)
	cleanup.callback(frappe.cache.delete, counter_key)
	session = _session(base)
	session.headers["Authorization"] = f"Bearer {token}"
	return session


def run():
	"""Run via bench execute on an isolated test site's own web container."""
	if frappe.local.site != TEST_SITE or not frappe.conf.get("allow_tests"):
		raise RuntimeError("The HTTP fixture requires the isolated test site")
	if any(
		frappe.conf.get("model_gateway_endpoints", {}).get(url) != "local" for url in (FIRST_URL, SECOND_URL)
	):
		raise RuntimeError("Configure both loopback model gateway fixture endpoints first")

	base = f"http://127.0.0.1:{int(frappe.conf.webserver_port)}"
	suffix = uuid4().hex[:12]
	password = f"Fixture#{uuid4().hex}"
	credential = f"test-only-{uuid4().hex}"
	frappe.set_user("Administrator")
	try:
		with ExitStack() as cleanup:
			users = _identities(suffix, password, cleanup)
			fixture = _seed(suffix, credential, cleanup)
			frappe.db.commit()
			with ExitStack() as connections:
				server = connections.enter_context(
					ThreadingHTTPServer(("127.0.0.1", FIXTURE_PORT), ProviderHandler)
				)
				server.attempts = []
				thread = Thread(target=server.serve_forever, daemon=True)
				thread.start()
				connections.callback(thread.join)
				connections.callback(server.shutdown)
				fixture.update(
					base=base,
					attempts=server.attempts,
					sessions={"guest": connections.enter_context(_session(base))},
				)
				for actor, user in users.items():
					fixture["sessions"][actor] = connections.enter_context(_session(base, user, password))
				fixture["sessions"]["agent"] = connections.enter_context(
					_agent_session(base, fixture["sessions"]["manager"], users["manager"], cleanup)
				)
				TestModelHTTP.fixture = fixture
				try:
					suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestModelHTTP)
					result = unittest.TextTestRunner(verbosity=2).run(suite)
				finally:
					TestModelHTTP.fixture = None
	finally:
		frappe.db.commit()
	if not result.wasSuccessful():
		raise RuntimeError("Model gateway HTTP checks failed")
