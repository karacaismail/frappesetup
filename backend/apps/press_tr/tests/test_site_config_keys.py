"""Check the G-39 fixture shipped with Press TR."""

import json
import runpy
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "press_tr"
PASSWORD_KEYS = {"mail_password", "encryption_key", "backup_encryption_key", "keycloak_client_secret"}
INTERNAL_KEYS = {"host_name", "server_script_enabled", "plan_limit"}


class SiteConfigKeysTest(unittest.TestCase):
	def test_fixture_declares_only_config_metadata(self):
		rows = json.loads((APP / "fixtures" / "site_config_key.json").read_text(encoding="utf-8"))
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
