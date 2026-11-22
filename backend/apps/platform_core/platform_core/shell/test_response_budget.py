"""Check the response budget against actual Frappe HTTP bytes."""

import json
from contextlib import contextmanager
from urllib.parse import urlencode

import frappe

from platform_core.shell.contract_tests.contract_json import parse_json
from platform_core.tests.shell_http_fixture import CHILD_DOCTYPE, DOCTYPE, READER, ShellHTTPFixture
from platform_core.tests.test_shell_contract import SCHEMA_FILE, matches

LIMIT = 262_144
BOOTSTRAP = "/api/method/platform_core.api.shell.get_bootstrap"
METADATA = "/api/method/platform_core.api.meta.get_doctype"
SIDEBAR = "Shell Review Links"


@contextmanager
def temporary_values(changes):
	originals = []
	try:
		for doctype, filters, field, value in changes:
			name, original = frappe.db.get_value(doctype, filters, ["name", field])
			originals.append((doctype, name, field, original))
			frappe.db.set_value(doctype, name, field, value, update_modified=False)
		frappe.db.commit()
		# Site cache clearing also removes browser session activity keys.
		frappe.clear_cache()
		yield
	finally:
		for doctype, name, field, original in originals:
			frappe.db.set_value(doctype, name, field, original, update_modified=False)
		frappe.db.commit()
		frappe.clear_cache()


class TestResponseBudgetHTTP(ShellHTTPFixture):
	def test_bootstrap_budget_includes_envelope_and_keeps_exact_boundary(self):
		def route_options(label):
			return [
				(
					"Sidebar Item",
					{"parent": SIDEBAR, "label": "Shell Safe Link"},
					"route_options",
					json.dumps({"label": label}),
				)
			]

		with temporary_values(route_options("")):
			status, _unused_headers, baseline = self.request(BOOTSTRAP, self.login(READER))
			self.assertEqual(status, 200)
		label = "x" * (LIMIT - len(baseline))
		for increment in (0, 1):
			with self.subTest(increment=increment), temporary_values(route_options(label + "x" * increment)):
				status, _unused_headers, body = self.request(BOOTSTRAP, self.login(READER))
				self.assertEqual(status, 200)
				self.assertLessEqual(len(body), LIMIT)
				if increment == 0:
					self.assertEqual(len(body), LIMIT)
				self.assertEqual(json.loads(body)["message"].get("truncated", False), bool(increment))

	def test_bootstrap_over_budget_preserves_identity_and_sets_flag(self):
		with temporary_values(
			[
				(
					"Sidebar Item",
					{"parent": SIDEBAR, "label": "Shell Safe Link"},
					"route_options",
					json.dumps({"label": "Ç" * 140_000}, ensure_ascii=False),
				)
			]
		):
			sid = self.login(READER)
			status, headers, body = self.request(BOOTSTRAP, sid)
			self.assertEqual(status, 200)
			self.assertLessEqual(len(body), LIMIT)
			payload = json.loads(body)["message"]
			self.assertIs(payload["truncated"], True)
			self.assertEqual(payload["user"]["name"], READER)
			self.assertTrue(payload["formatting"]["time_zone"])
			self.assertEqual(payload["sidebars"], [])
			self.assertEqual(payload["workspaces"], [])
			cached = self.request(BOOTSTRAP, sid, headers={"If-None-Match": headers["ETag"]})
			self.assertEqual((cached[0], cached[2]), (304, b""))
			for path, key in (
				(BOOTSTRAP.replace("/api/", "/api/v2/", 1), "data"),
				("/?" + urlencode({"cmd": BOOTSTRAP.rsplit("/", 1)[-1]}), "message"),
			):
				with self.subTest(path=path):
					status, response_headers, body = self.request(path, sid)
					self.assertEqual(status, 200)
					self.assertLessEqual(len(body), LIMIT)
					self.assertEqual(json.loads(body)[key], payload)
					self.assertEqual(response_headers["ETag"], headers["ETag"])
		status, _unused_headers, body = self.request(
			BOOTSTRAP, self.login(READER), headers={"If-None-Match": headers["ETag"]}
		)
		self.assertEqual(status, 200)
		self.assertIsNot(json.loads(body)["message"].get("truncated"), True)

	def test_metadata_over_budget_does_not_form_a_partial_schema(self):
		long_description = '"' * 50_000
		with temporary_values(
			[
				("DocField", {"parent": DOCTYPE, "fieldname": "title"}, "description", long_description),
				(
					"DocField",
					{"parent": CHILD_DOCTYPE, "fieldname": "entry"},
					"description",
					long_description,
				),
				(
					"Custom Field",
					{"dt": DOCTYPE, "fieldname": "contract_choice"},
					"description",
					long_description,
				),
			]
		):
			sid = self.login(READER)
			status, _unused_headers, body = self.metadata(sid)
			self.assertEqual(status, 200)
			self.assertLessEqual(len(body), LIMIT)
			payload = json.loads(body)["message"]
			self.assertIs(payload["truncated"], True)
			self.assertEqual(payload["schema"]["name"], DOCTYPE)
			self.assertEqual(payload["schema"]["fields"], [])
			self.assertEqual(payload["child_tables"], {})
			self.assertIs(payload["mobile_cache_allowed"], False)
			components = parse_json(SCHEMA_FILE.read_bytes())
			self.assertTrue(matches(payload, components["Meta"], components))
			path = METADATA.replace("/api/", "/api/v2/", 1) + "?" + urlencode({"doctype": DOCTYPE})
			status, _unused_headers, body = self.request(path, sid)
			self.assertEqual(status, 200)
			self.assertLessEqual(len(body), LIMIT)
			self.assertEqual(json.loads(body)["data"], payload)
