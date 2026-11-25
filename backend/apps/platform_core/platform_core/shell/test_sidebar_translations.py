"""G-73: the Integrations menu names the Connected App link correctly in Turkish.

Frappe's own Turkish file (`frappe/locale/tr.po`) has a typo for "Connected App".
The fix lives in this app's `translations/tr.csv`, never in Frappe's file.
The panel reads menu labels from the shell bootstrap, so the test reads them there too.
"""

# The expected Turkish text below is test data. Ruff reads the Turkish dotless i as a typo.
# ruff: noqa: RUF001
import csv
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.translate import clear_cache, get_translations_from_apps

import platform_core
from platform_core.shell.bootstrap import get_bootstrap
from platform_core.shell.cache import bump_permission_version

CSV_PATH = Path(platform_core.__file__).parent / "translations" / "tr.csv"
SOURCE = "Connected App"
EXPECTED = "Bağlı Uygulamalar"
TYPO = "Bağlı Uyulamalar"


def integrations_labels() -> dict[str, str]:
	"""Turkish labels of the Integrations menu links, keyed by link target."""
	with patch.object(frappe.local, "lang", "tr"):
		sidebars = get_bootstrap(frappe.session.user)["sidebars"]
	integrations = next(sidebar for sidebar in sidebars if sidebar["name"] == "Integrations")
	return {
		item["link_to"]: item["label"]
		for item in integrations["data"]["items"]
		if item.get("type") == "Link" and item.get("link_to")
	}


class TestSidebarTranslations(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		clear_cache()
		bump_permission_version()
		self.addCleanup(clear_cache)

	def test_app_translation_file_carries_the_fix(self):
		with CSV_PATH.open(encoding="utf-8", newline="") as handle:
			rows = [row for row in csv.reader(handle) if row and row[0] == SOURCE]
		self.assertEqual(len(rows), 1, rows)
		_source, translation, *context = rows[0]
		self.assertEqual(translation, EXPECTED)
		# Frappe translates sidebar labels without a context, so the row must have none.
		self.assertFalse(any(context), context)

	def test_integrations_menu_shows_the_correct_name(self):
		labels = integrations_labels()
		self.assertEqual(labels.get(SOURCE), EXPECTED, labels)
		self.assertNotIn(TYPO, labels.values())

	def test_other_integrations_labels_keep_frappe_translations(self):
		labels = integrations_labels()
		sources = {
			row.link_to: row.label for row in frappe.get_doc("Sidebar", "Integrations").items if row.link_to
		}
		other_apps = [app for app in frappe.get_installed_apps() if app != "platform_core"]
		upstream = get_translations_from_apps("tr", other_apps)
		for link_to, label in labels.items():
			if link_to == SOURCE:
				continue
			source = sources[link_to]
			self.assertEqual(label, upstream.get(source, source), link_to)
