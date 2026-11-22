"""Check how Press reads internal Keycloak session mappings."""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from press_tr.press_identity import sessions


class SessionMappingPaginationTest(unittest.TestCase):
	def test_local_logout_reads_ordered_pages_without_loading_unmatched_documents(self):
		names = [f"mapping-{index:03d}" for index in range(101)]
		with ExitStack() as stack:
			framework = stack.enter_context(patch.object(sessions, "frappe"))
			framework.session.user = "reader@example.test"
			framework.session.sid = "current-press-session"
			framework.db.get_value.return_value = "identity-link"
			framework.get_all.side_effect = [names[:100], names[100:]]
			decrypt = stack.enter_context(patch("frappe.utils.password.get_decrypted_password"))
			decrypt.side_effect = lambda doctype, name, fieldname: (
				"current-press-session" if name == names[-1] else "another-press-session"
			)

			sessions.remove_mapping()

			self.assertEqual(framework.get_all.call_count, 2)
			first, second = [call.kwargs for call in framework.get_all.call_args_list]
			self.assertEqual(first["limit"], 100)
			self.assertEqual(first["order_by"], "name asc")
			self.assertEqual(second["filters"], {"identity_link": "identity-link", "name": [">", names[99]]})
			framework.get_doc.assert_not_called()
			framework.delete_doc.assert_called_once_with(
				"PTR Keycloak Session", names[-1], ignore_permissions=True
			)
			self.assertEqual(decrypt.call_count, 101)


if __name__ == "__main__":
	unittest.main()
