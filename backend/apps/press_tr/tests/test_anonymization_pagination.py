"""Check that account anonymization reads large record sets in named pages."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from press_tr.kimlik import anonymization


class AnonymizationPaginationTest(TestCase):
	def test_personal_files_are_read_in_stable_pages(self):
		user = "person@example.test"
		names = [f"file-{index:03}" for index in range(101)]
		attached = {"is_folder": 0, "attached_to_doctype": "User", "attached_to_name": user}

		def get_all(doctype, filters, *, fields=None, order_by=None, limit=None, pluck=None):
			self.assertEqual(doctype, "File")
			self.assertEqual((order_by, limit), ("name asc", 100))
			self.assertIsNone(pluck)
			self.assertIn("name", fields)
			if filters == attached:
				selected = names[:100]
			elif filters == {**attached, "name": [">", names[99]]}:
				selected = names[100:]
			else:
				self.assertEqual(
					filters,
					{
						"is_folder": 0,
						"owner": user,
						"attached_to_doctype": ["is", "not set"],
						"attached_to_name": ["is", "not set"],
					},
				)
				selected = []
			return [SimpleNamespace(name=name) for name in selected]

		with patch.object(anonymization.frappe, "get_all", side_effect=get_all) as query:
			self.assertEqual(anonymization.get_personal_files(user, None), set(names))
			self.assertEqual(query.call_count, 3)
