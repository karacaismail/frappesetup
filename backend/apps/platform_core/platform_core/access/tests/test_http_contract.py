"""Check GET authentication responses over HTTP against the access contract."""

import http.client
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import frappe
import yaml
from frappe.app import application
from jsonschema import Draft202012Validator
from werkzeug.serving import make_server

from platform_core.access.tests.base import ADMIN, DESK_ONLY, DOCTYPE, AccessRuleTestCase


class TestGetAuthenticationContract(AccessRuleTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		checkout = Path(__file__).resolve().parents[5] / "contracts"
		installed = Path(frappe.get_app_path("platform_core")).resolve().parents[2] / "contracts"
		contract = next(
			folder / "platform_core-access.openapi.yaml"
			for folder in (checkout, installed)
			if (folder / "platform_core-access.openapi.yaml").is_file()
		)
		cls.contract = yaml.safe_load(contract.read_text())
		cls.server = make_server("127.0.0.1", 0, application, threaded=True)
		cls.addClassCleanup(cls.server.server_close)
		worker = Thread(target=cls.server.serve_forever, daemon=True)
		worker.start()
		cls.addClassCleanup(worker.join, 10)
		cls.addClassCleanup(cls.server.shutdown)

	def request_get(self, path, query, sid=None):
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
		headers = {"Host": self.site, "Accept": "application/json"}
		if sid is not None:
			headers["Cookie"] = f"sid={sid}"
		try:
			connection.request("GET", f"/api/method{path}?{urlencode(query)}", headers=headers)
			response = connection.getresponse()
			return response.status, response.headers.get_content_type(), json.loads(response.read())
		finally:
			connection.close()

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
