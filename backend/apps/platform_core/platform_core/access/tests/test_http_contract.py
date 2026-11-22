"""Check authentication responses over HTTP against the access contract."""

import http.client
import json
import time
from pathlib import Path
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import urlencode

import frappe
import yaml
from frappe.app import application
from jsonschema import Draft202012Validator
from werkzeug.serving import make_server

from platform_core.access.tests.base import ADMIN, DESK_ONLY, DOCTYPE, AccessRuleTestCase


class TestContractLookup(TestCase):
	def test_missing_contract_reports_the_searched_locations(self):
		with (
			patch.object(AccessRuleTestCase, "setUpClass") as fixture_setup,
			patch.object(Path, "is_file", return_value=False),
			self.assertRaisesRegex(
				AssertionError, "Access HTTP contract not found.*platform_core-access"
			) as failure,
		):
			TestGetAuthenticationContract.setUpClass()
		fixture_setup.assert_not_called()
		self.assertIn(str(Path(__file__).resolve().parents[5] / "contracts"), str(failure.exception))
		self.assertIn(
			str(Path(frappe.get_app_path("platform_core")).resolve().parents[2] / "contracts"),
			str(failure.exception),
		)


class TestGetAuthenticationContract(AccessRuleTestCase):
	@classmethod
	def setUpClass(cls):
		checkout = Path(__file__).resolve().parents[5] / "contracts"
		installed = Path(frappe.get_app_path("platform_core")).resolve().parents[2] / "contracts"
		contract = next(
			(
				folder / "platform_core-access.openapi.yaml"
				for folder in (checkout, installed)
				if (folder / "platform_core-access.openapi.yaml").is_file()
			),
			None,
		)
		if contract is None:
			raise AssertionError(
				"Access HTTP contract not found: expected platform_core-access.openapi.yaml "
				f"in {checkout} or {installed}."
			)
		cls.contract = yaml.safe_load(contract.read_text())
		super().setUpClass()
		cls.server = make_server("127.0.0.1", 0, application, threaded=True)
		cls.addClassCleanup(cls.server.server_close)
		worker = Thread(target=cls.server.serve_forever, daemon=True)
		worker.start()
		cls.addClassCleanup(worker.join, 10)
		cls.addClassCleanup(cls.server.shutdown)

	def request_get(self, path, query, sid=None):
		return self.request_http(path, query, sid)

	def request_http(self, path, query, sid=None, *, method="GET", csrf_token=None):
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
		headers = {"Host": self.site, "Accept": "application/json"}
		if sid is not None:
			headers["Cookie"] = f"sid={sid}"
		if csrf_token:
			headers["X-Frappe-CSRF-Token"] = csrf_token
		body = None
		url = f"/api/method{path}"
		if method == "GET":
			url += f"?{urlencode(query)}"
		else:
			headers["Content-Type"] = "application/x-www-form-urlencoded"
			body = urlencode(query)
		try:
			connection.request(method, url, body=body, headers=headers)
			response = connection.getresponse()
			return response.status, response.headers.get_content_type(), json.loads(response.read())
		finally:
			connection.close()

	def assert_session_expired_contract(self, path, method, response):
		status, content_type, payload = response
		self.assertEqual(status, 401)
		self.assertEqual(content_type, "application/json")
		self.assertEqual(payload["exc_type"], "SessionExpired")
		responses = self.contract["paths"][path][method.lower()]["responses"]
		self.assertIn("401", responses)
		definition = responses["401"]
		if "$ref" in definition:
			definition = self.contract["components"]["responses"][definition["$ref"].split("/")[-1]]
		Draft202012Validator(definition["content"]["application/json"]["schema"]).validate(payload)

	def test_missing_session_matches_both_post_contracts(self):
		for endpoint in ("set_field_level", "set_level_access"):
			path = f"/platform_core.api.access.{endpoint}"
			with self.subTest(path=path):
				response = self.request_http(path, {}, "missing-access-contract-session", method="POST")
				self.assertEqual(response[2]["session_expired"], 1)
				self.assert_session_expired_contract(path, "POST", response)

	def test_idle_session_matches_every_endpoint_contract(self):
		# O-25 expires real activity after one hour even when the Frappe session is fresh.
		for path, operations in self.contract["paths"].items():
			for method in ("GET", "POST"):
				if method.lower() not in operations:
					continue
				with self.subTest(path=path, method=method):
					client = self.login(ADMIN)
					sid = client.get_cookie("sid").value
					if method == "POST":
						# Opening the real panel creates the session's CSRF token, as in a browser.
						# Frappe skips persisting that token in test mode (sessions.py:211).
						with patch.object(frappe, "in_test", False):
							self.assertEqual(self.send(client, "GET", "/panel").status_code, 200)
					sessions = frappe.qb.DocType("Sessions")
					stored = (
						frappe.qb.from_(sessions)
						.select(sessions.sessiondata)
						.where(sessions.sid == sid)
						.run()
					)
					self.assertTrue(stored, "The idle test must start with a real, live session.")
					csrf_token = frappe.parse_json(stored[0][0]).get("csrf_token")
					if method == "POST":
						self.assertTrue(csrf_token, "The idle POST must carry the real session's CSRF token.")
					# Identity owns this key format in identity/session_policy.py::_session_key.
					# module-boundaries.json forbids importing identity here; update this fixture with its owner.
					# The 3600-second limit comes from O-25, not from the implementation.
					frappe.cache.set_value(
						f"kimlik_activity:sid:{sid}", int(time.time()) - 3601, expires_in_sec=3600
					)
					response = self.request_http(
						path, {"doctype": DOCTYPE}, sid, method=method, csrf_token=csrf_token
					)
					self.assertNotIn("session_expired", response[2])
					frappe.db.rollback()
					self.assertFalse(frappe.db.exists("Sessions", {"sid": sid}))
					self.assert_session_expired_contract(path, method, response)

	def test_guest_expired_session_and_unauthorized_user_match_get_contract(self):
		client = self.login(DESK_ONLY)
		unauthorized_sid = client.get_cookie("sid").value
		query = {"doctype": DOCTYPE}
		record = next(iter(self.records.values()))
		requests = {
			"/platform_core.api.access.explain_permission": {**query, "name": record},
			"/platform_core.api.access.get_access_summary": query,
			"/platform_core.access.link_search.search_link": {**query, "txt": ""},
			"/platform_core.access.link_search.search_widget": {**query, "txt": ""},
			"/platform_core.access.link_search.validate_link_and_fetch": {**query, "docname": record},
		}
		# Shared contract SZ-8: no session is 403; an expired session is 401.
		callers = (
			("guest", None, 403),
			("expired", "missing-access-contract-session", 401),
			("unauthorized", unauthorized_sid, 403),
		)
		for path, parameters in requests.items():
			for caller, sid, expected in callers:
				with self.subTest(path=path, caller=caller):
					status, content_type, payload = self.request_get(path, parameters, sid)
					self.assertEqual(status, expected)
					self.assertEqual(content_type, "application/json")
					responses = self.contract["paths"][path]["get"]["responses"]
					self.assertIn(str(status), responses)
					if expected == 401:
						self.assertEqual(payload["session_expired"], 1)
						self.assertEqual(payload["exc_type"], "SessionExpired")
						definition = responses["401"]
						if "$ref" in definition:
							definition = self.contract["components"]["responses"][
								definition["$ref"].split("/")[-1]
							]
						Draft202012Validator(definition["content"]["application/json"]["schema"]).validate(
							payload
						)
					for name in self.records.values():
						self.assertNotIn(name, json.dumps(payload))

	def test_missing_document_type_is_denied_without_disclosing_existence(self):
		# The access contract treats missing and unreadable document types alike.
		for user in (DESK_ONLY, ADMIN):
			sid = self.login(user).get_cookie("sid").value
			for doctype in ("", "Access Contract Missing DocType"):
				self.assertFalse(frappe.db.exists("DocType", doctype))
				for path, query in (
					("/platform_core.api.access.get_access_summary", {}),
					("/platform_core.api.access.explain_permission", {"name": "missing-record"}),
					("/platform_core.access.link_search.search_link", {"txt": ""}),
					("/platform_core.access.link_search.search_widget", {"txt": ""}),
					(
						"/platform_core.access.link_search.validate_link_and_fetch",
						{"docname": "missing-record"},
					),
				):
					with self.subTest(user=user, doctype=doctype, path=path):
						status, content_type, payload = self.request_get(
							path, {"doctype": doctype, **query}, sid
						)
						self.assertEqual(status, 403)
						self.assertEqual(content_type, "application/json")
						self.assertEqual(payload["exc_type"], "PermissionError")
						self.assertIn("403", self.contract["paths"][path]["get"]["responses"])
						self.assertNotIn("DoesNotExistError", json.dumps(payload))
