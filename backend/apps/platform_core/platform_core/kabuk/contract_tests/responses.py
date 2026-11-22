"""Validate actual Frappe responses against the shell OpenAPI document."""

import http.client
import os
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from jsonschema import Draft202012Validator

if __package__:
	from .contract_json import parse_json
else:
	from contract_json import parse_json

CONTRACT = Path("backend/contracts/platform_core-kabuk.openapi.yaml")
SNAPSHOT = Path(__file__).resolve().parents[2] / "tests" / "shell_contract_components.json"
BOOTSTRAP = "/api/method/platform_core.api.shell.get_bootstrap"
METADATA = "/api/method/platform_core.api.meta.get_doctype"
POLICY_CHECK = "/api/method/platform_core.api.meta.validate_mobile_policy"
NATIVE_METADATA = "/api/v2/doctype/{doctype}/meta"
PROBE = "/api/method/frappe.auth.get_logged_user"
DOCTYPE = "Kabuk Test Record"


class TestShellResponses(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.contract = parse_json(CONTRACT.read_text(encoding="utf-8"))
		cls.target = urlsplit(os.environ["PANEL_TEST_URL"])
		if cls.target.scheme != "http" or cls.target.hostname != "127.0.0.1":
			raise ValueError("Use the dedicated test site on HTTP loopback.")
		status, headers, _ = cls.request(
			"/api/method/login",
			method="POST",
			form={"usr": os.environ["PANEL_TEST_USERNAME"], "pwd": os.environ["PANEL_TEST_PASSWORD"]},
		)
		if status != 200:
			raise RuntimeError(f"Test login returned HTTP {status}.")
		cookies = SimpleCookie()
		for value in headers.get_all("Set-Cookie", []):
			cookies.load(value)
		cls.sid = cookies["sid"].value

	@classmethod
	def request(cls, path, *, sid=None, headers=None, method="GET", form=None):
		connection = http.client.HTTPConnection(cls.target.hostname, cls.target.port, timeout=10)
		request_headers = {"Host": "test-kabuk.localhost", "Accept": "application/json"}
		if sid:
			request_headers["Cookie"] = "sid=" + sid
		if form:
			request_headers["Content-Type"] = "application/x-www-form-urlencoded"
		request_headers.update(headers or {})
		try:
			connection.request(method, path, body=urlencode(form) if form else None, headers=request_headers)
			response = connection.getresponse()
			return response.status, response.headers, response.read()
		finally:
			connection.close()

	def validate(self, path, expected, result):
		status, headers, body = result
		self.assertEqual(status, expected)
		response = self.contract["paths"][path]["get"]["responses"][str(status)]
		for header, definition in response.get("headers", {}).items():
			self.assertIn(header, headers)
			Draft202012Validator(definition["schema"]).validate(headers[header])
		if status == 304:
			self.assertFalse(body)
			self.assertNotIn("content", response)
			return
		self.assertEqual(headers.get_content_type(), "application/json")
		media = response["content"]["application/json"]
		validator = Draft202012Validator(
			{
				"$ref": "#/response",
				"response": media["schema"],
				"components": self.contract["components"],
			}
		)
		validator.validate(parse_json(body))
		self.assertIn("example", media)
		validator.validate(media["example"])

	def test_actual_200_304_401_and_403_match_the_contract(self):
		for path in (BOOTSTRAP, METADATA):
			with self.subTest(path=path):
				route = path + "?" + urlencode({"doctype": DOCTYPE}) if path == METADATA else path
				ok = self.request(route, sid=self.sid)
				self.validate(path, 200, ok)
				payload = parse_json(ok[2])["message"]
				if path == METADATA:
					choice = next(
						field
						for field in payload["schema"]["fields"]
						if field["fieldname"] == "contract_choice"
					)
					self.assertEqual(choice["depends_on"]["op"], "eq")
					self.assertTrue(choice["choices"])
					self.assertIn("read_only_depends_on", choice["unsupported_conditions"])
				else:
					self.assertTrue(any(sidebar["data"]["items"] for sidebar in payload["sidebars"]))
				conditional = self.request(route, sid=self.sid, headers={"If-None-Match": ok[1]["ETag"]})
				self.validate(path, 304, conditional)
				self.assertEqual(conditional[1]["ETag"], ok[1]["ETag"])
				self.validate(path, 401, self.request(route, sid="missing-shell-contract-session"))
				self.validate(path, 403, self.request(route))
				separator = "&" if "?" in route else "?"
				self.validate(path, 417, self.request(route + separator + "unknown=sample", sid=self.sid))
		self.validate(PROBE, 200, self.request(PROBE, sid=self.sid))
		self.validate(PROBE, 401, self.request(PROBE, sid="missing-shell-contract-session"))
		self.validate(PROBE, 403, self.request(PROBE))

	def test_rate_limit_response_matches_the_contract(self):
		# The synthetic account starts with its own bucket on the isolated site.
		for _ in range(121):
			result = self.request(BOOTSTRAP, sid=self.sid)
			if result[0] == 429:
				self.validate(BOOTSTRAP, 429, result)
				return
			self.assertEqual(result[0], 200)
		self.fail("The shell bootstrap rate limit did not respond with HTTP 429.")

	def test_policy_check_rejects_unsupported_query_parameters(self):
		result = self.request(POLICY_CHECK + "?unexpected=sample", sid=self.sid)
		self.validate(POLICY_CHECK, 417, result)

	def test_policy_check_expired_session_matches_the_contract(self):
		result = self.request(POLICY_CHECK, sid="missing-shell-contract-session")
		self.validate(POLICY_CHECK, 401, result)
		self.assertEqual(parse_json(result[2])["session_expired"], 1)

	def test_native_missing_doctype_matches_the_contract_for_a_system_user(self):
		existing = NATIVE_METADATA.format(doctype="ToDo")
		self.assertEqual(self.request(existing, sid=self.sid)[0], 200)
		route = NATIVE_METADATA.format(doctype=quote("Shell Missing Native DocType"))
		result = self.request(route, sid=self.sid)
		self.validate(NATIVE_METADATA, 404, result)
		self.assertEqual([error["type"] for error in parse_json(result[2])["errors"]], ["DoesNotExistError"])

	def test_official_projection_snapshot_matches_openapi(self):
		snapshot = parse_json(SNAPSHOT.read_text(encoding="utf-8"))
		schemas = self.contract["components"]["schemas"]
		self.assertEqual(snapshot, {key: schemas[key] for key in snapshot})


class TestContractParsing(unittest.TestCase):
	def test_duplicate_keys_are_rejected(self):
		with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
			parse_json('{"nested": {"field": 1, "field": 2}}')

	def test_nonfinite_numbers_are_rejected(self):
		for constant in ("NaN", "Infinity", "-Infinity", "1e309", "-1e309"):
			with self.subTest(constant=constant), self.assertRaisesRegex(ValueError, "Nonfinite JSON number"):
				parse_json(f'{{"field": {constant}}}')

	def test_truncated_schemas_require_safe_shapes(self):
		contract = parse_json(CONTRACT.read_bytes())
		for path, schema_name in ((BOOTSTRAP, "Bootstrap"), (METADATA, "Meta")):
			with self.subTest(schema=schema_name):
				validator = Draft202012Validator(
					{
						"$ref": f"#/components/schemas/{schema_name}",
						"components": contract["components"],
					}
				)
				success = contract["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]
				payload = {**success["example"]["message"], "truncated": True}
				self.assertFalse(validator.is_valid(payload))
				if schema_name == "Bootstrap":
					payload.update(workspaces=[], sidebars=[], installed_apps=[])
					payload["user"] = {**payload["user"], "roles": []}
				else:
					payload["schema"] = {
						**payload["schema"],
						"fields": [],
						"title_field": None,
						"search_fields": "",
						"sort_field": None,
					}
					payload.update(child_tables={}, mobile_cache_allowed=False)
				validator.validate(payload)


if __name__ == "__main__":
	unittest.main()
