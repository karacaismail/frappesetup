"""Validate actual Frappe responses against the shell OpenAPI document."""

import http.client
import json
import os
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from jsonschema import Draft202012Validator

CONTRACT = Path("backend/contracts/platform_core-kabuk.openapi.yaml")
BOOTSTRAP = "/api/method/platform_core.api.shell.get_bootstrap"
METADATA = "/api/method/platform_core.api.meta.get_doctype"
PROBE = "/api/method/frappe.auth.get_logged_user"
DOCTYPE = "Kabuk Test Record"


class TestShellResponses(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
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
		validator.validate(json.loads(body))
		self.assertIn("example", media)
		validator.validate(media["example"])

	def test_actual_200_304_401_and_403_match_the_contract(self):
		for path in (BOOTSTRAP, METADATA):
			with self.subTest(path=path):
				route = path + "?" + urlencode({"doctype": DOCTYPE}) if path == METADATA else path
				ok = self.request(route, sid=self.sid)
				self.validate(path, 200, ok)
				conditional = self.request(route, sid=self.sid, headers={"If-None-Match": ok[1]["ETag"]})
				self.validate(path, 304, conditional)
				self.assertEqual(conditional[1]["ETag"], ok[1]["ETag"])
				self.validate(path, 401, self.request(route, sid="missing-shell-contract-session"))
				self.validate(path, 403, self.request(route))
		self.validate(PROBE, 200, self.request(PROBE, sid=self.sid))
		self.validate(PROBE, 401, self.request(PROBE, sid="missing-shell-contract-session"))
		self.validate(PROBE, 403, self.request(PROBE))


if __name__ == "__main__":
	unittest.main()
