"""GILT step 2b: the bootstrap carries the user's locale formats and the enabled languages."""

import json
from unittest.mock import patch

import frappe
from frappe.locale import get_date_format, get_first_day_of_the_week, get_time_format
from frappe.tests import IntegrationTestCase

from platform_core.shell.bootstrap import compact_bootstrap, get_bootstrap
from platform_core.shell.cache import bump_permission_version
from platform_core.tests.test_shell_contract import SCHEMA_FILE, matches

DISABLED_SAMPLE = "de"


def _clear_language_caches():
	frappe.cache.delete_value("languages_with_name")
	frappe.client_cache.delete_value("languages")


class TestBootstrapLocale(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.components = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
		bump_permission_version()

	def test_formatting_takes_date_time_and_week_from_the_user_language(self):
		# Frappe 16 reads these from the Language record first, then System Settings (frappe/locale.py).
		previous = frappe.db.get_value("Language", "tr", "date_format")
		frappe.db.set_value("Language", "tr", "date_format", "dd.mm.yyyy")
		self.addCleanup(frappe.db.set_value, "Language", "tr", "date_format", previous)
		with patch.object(frappe.local, "lang", "tr"):
			payload = get_bootstrap(frappe.session.user)
			formatting = payload["formatting"]
			self.assertEqual(formatting["date_format"], "dd.mm.yyyy")
			self.assertEqual(formatting["date_format"], get_date_format("tr"))
			self.assertEqual(formatting["time_format"], get_time_format("tr"))
			self.assertEqual(formatting["first_day_of_the_week"], get_first_day_of_the_week("tr"))
		self.assertTrue(matches(formatting, self.components["Formatting"], self.components), formatting)

	def test_languages_list_only_enabled_records(self):
		self.assertTrue(
			frappe.db.exists("Language", DISABLED_SAMPLE), "The sample language record must exist."
		)
		frappe.db.set_value("Language", DISABLED_SAMPLE, "enabled", 0)
		_clear_language_caches()
		self.addCleanup(_clear_language_caches)
		self.addCleanup(frappe.db.set_value, "Language", DISABLED_SAMPLE, "enabled", 1)
		languages = get_bootstrap(frappe.session.user)["languages"]
		enabled = frappe.get_all("Language", fields=["name", "language_name"], filters={"enabled": 1})
		self.assertEqual(
			sorted((row["code"], row["name"]) for row in languages),
			sorted((row.name, row.language_name) for row in enabled),
		)
		codes = [row["code"] for row in languages]
		self.assertNotIn(DISABLED_SAMPLE, codes)
		self.assertIn("tr", codes)
		self.assertIn("en", codes)
		for row in languages:
			self.assertTrue(matches(row, self.components["Language"], self.components), row)

	def test_compact_bootstrap_keeps_formatting_and_languages(self):
		payload = get_bootstrap(frappe.session.user)
		summary = compact_bootstrap(payload)
		self.assertEqual(summary["formatting"], payload["formatting"])
		self.assertEqual(summary["languages"], payload["languages"])
