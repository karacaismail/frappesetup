"""Check the G-39 fixture shipped with Press TR."""

import io
import json
import os
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "press_tr"
FIXTURE = APP / "fixtures" / "site_config_key.json"
PASSWORD_KEYS = {"mail_password", "encryption_key", "backup_encryption_key", "keycloak_client_secret"}
INTERNAL_KEYS = {"host_name", "server_script_enabled", "plan_limit"}


class SiteConfigKeysTest(unittest.TestCase):
	def test_fixture_declares_only_config_metadata(self):
		rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
		self.assertEqual(len(rows), len(PASSWORD_KEYS | INTERNAL_KEYS))
		self.assertEqual({row["key"] for row in rows}, PASSWORD_KEYS | INTERNAL_KEYS)
		for row in rows:
			with self.subTest(key=row["key"]):
				self.assertEqual(set(row), {"doctype", "name", "key", "type", "internal"})
				self.assertEqual(row["doctype"], "Site Config Key")
				self.assertEqual(row["name"], row["key"])

		self.assertEqual({row["key"] for row in rows if row["type"] == "Password"}, PASSWORD_KEYS)
		self.assertEqual({row["key"] for row in rows if row["internal"]}, INTERNAL_KEYS)

	def test_fixture_export_is_limited_to_the_seven_keys(self):
		fixtures = runpy.run_path(str(APP / "hooks.py"))["fixtures"]
		rule = next(rule for rule in fixtures if rule["dt"] == "Site Config Key")
		[(field, operator, keys)] = rule["filters"]
		self.assertEqual((field, operator), ("key", "in"))
		self.assertCountEqual(keys, PASSWORD_KEYS | INTERNAL_KEYS)

	def test_seed_metadata_does_not_emit_a_configured_password(self):
		fake_password = "synthetic-g39-value-for-log-test"
		stdout = io.StringIO()
		stderr = io.StringIO()
		with (
			patch.dict(os.environ, {"mail_password": fake_password}),
			redirect_stdout(stdout),
			redirect_stderr(stderr),
			self.assertNoLogs(level="DEBUG"),
		):
			payload = FIXTURE.read_text(encoding="utf-8")
			json.loads(payload)
			runpy.run_path(str(APP / "hooks.py"))

		self.assertNotIn(fake_password, payload)
		self.assertNotIn(fake_password, stdout.getvalue())
		self.assertNotIn(fake_password, stderr.getvalue())

	@unittest.skipUnless(find_spec("press"), "Requires the Press bench")
	def test_press_panel_lists_only_public_fixture_keys(self):
		from press.api import site

		rows = json.loads(FIXTURE.read_text(encoding="utf-8"))

		def get_all(doctype, filters, fields, *, order_by):
			self.assertEqual(doctype, "Site Config Key")
			self.assertIn("key", fields)
			return [
				{field: row.get(field) for field in fields}
				for row in rows
				if all(row.get(field) == value for field, value in filters.items())
			]

		with patch.object(site.frappe, "get_all", side_effect=get_all):
			result = site.get_site_config_standard_keys()

		self.assertEqual({row["key"] for row in result}, PASSWORD_KEYS)
