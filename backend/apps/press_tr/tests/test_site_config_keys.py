"""Check the G-39 fixture shipped with Press TR."""

import io
import json
import logging
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace
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

	@unittest.skipUnless(find_spec("press"), "Requires the Press bench")
	def test_press_masks_configured_passwords_with_the_seed(self):
		import frappe
		from press.press.doctype.site_config.site_config import SiteConfig

		rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
		fake_password = "synthetic-g39-value-for-log-test"

		def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
			self.assertEqual(doctype, "Site Config Key")
			matches = []
			for row in rows:
				if all(
					row.get(field) in value[1] if isinstance(value, list) else row.get(field) == value
					for field, value in (filters or {}).items()
				):
					matches.append(row)
			if pluck:
				return [row[pluck] for row in matches]
			return [frappe._dict({field: row.get(field) for field in fields or ["name"]}) for row in matches]

		configs = [
			SimpleNamespace(key=key, value=fake_password, type="String") for key in sorted(PASSWORD_KEYS)
		]
		configs.append(SimpleNamespace(key="custom_public", value="visible", type="String"))
		stdout = io.StringIO()
		stderr = io.StringIO()
		log = io.StringIO()
		handler = logging.StreamHandler(log)
		root = logging.getLogger()
		level = root.level
		root.addHandler(handler)
		root.setLevel(logging.DEBUG)
		try:
			with (
				patch.object(frappe, "get_all", side_effect=get_all),
				patch.object(frappe, "db", SimpleNamespace(get_all=get_all)),
				redirect_stdout(stdout),
				redirect_stderr(stderr),
			):
				result = SiteConfig.format_config_for_list(configs)
		finally:
			root.removeHandler(handler)
			root.setLevel(level)

		values = {config.key: config.value for config in result}
		for key in PASSWORD_KEYS:
			with self.subTest(key=key):
				self.assertEqual(values[key], "*******")
		self.assertEqual(values["custom_public"], "visible")
		emitted = json.dumps([vars(config) for config in result])
		for text in (emitted, stdout.getvalue(), stderr.getvalue(), log.getvalue()):
			self.assertNotIn(fake_password, text)

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
