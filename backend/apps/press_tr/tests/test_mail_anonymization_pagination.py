"""Verify keyset traversal when anonymization removes rows from its own filter."""

import unittest
from unittest.mock import patch

import frappe

from press_tr.kimlik import anonymization

OLD_ADDRESS = "old@example.test"
ANONYMOUS_ADDRESS = "deleted@invalid.example"


class MailAnonymizationPaginationTest(unittest.TestCase):
	def test_address_list_scan_keeps_later_matches_after_the_first_page_changes(self):
		names = [f"communication-{index:03d}" for index in range(101)]
		addresses = dict.fromkeys(names, f"{OLD_ADDRESS}, other@example.test")

		def matching_rows(doctype, filters, fields, **options):
			self.assertEqual(doctype, "Communication")
			self.assertEqual(fields, ["name", "cc"])
			self.assertEqual(filters["cc"], ["like", f"%{OLD_ADDRESS}%"])
			self.assertEqual(options.get("order_by"), "name asc")
			self.assertEqual(options.get("limit"), 100)
			after = filters.get("name", [">", ""])[1]
			matches = [
				frappe._dict(name=name, cc=address)
				for name, address in addresses.items()
				if name > after and OLD_ADDRESS in address
			]
			return matches[: options["limit"]]

		def update_row(doctype, name, changes, *, update_modified):
			self.assertFalse(update_modified)
			addresses[name] = changes["cc"]

		with patch.object(anonymization, "frappe") as framework:
			framework.get_all.side_effect = matching_rows
			framework.db.set_value.side_effect = update_row
			touched = anonymization.redact_address_lists(
				"Communication", "cc", OLD_ADDRESS, ANONYMOUS_ADDRESS, {"content": None}
			)

		self.assertEqual(framework.get_all.call_count, 2)
		self.assertEqual(framework.get_all.call_args.kwargs.get("filters", {}).get("name"), [">", names[99]])
		self.assertEqual(touched, set(names))
		self.assertEqual(set(addresses.values()), {f"{ANONYMOUS_ADDRESS}, other@example.test"})


if __name__ == "__main__":
	unittest.main()
