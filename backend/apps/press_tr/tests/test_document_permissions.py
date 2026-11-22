"""Keep the temporary permission bypass scoped to the authorized save."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from press_tr.kimlik import accounts


class DocumentPermissionTest(TestCase):
	def test_account_save_restores_permissions_even_if_it_fails(self):
		class SaveError(Exception):
			pass

		for fails in (False, True):
			with self.subTest(fails=fails):
				doc = Mock(enabled=1, flags=SimpleNamespace(ignore_permissions=False))

				def save(*, ignore_permissions):
					doc.flags.ignore_permissions = ignore_permissions
					if fails:
						raise SaveError

				doc.save.side_effect = save
				with patch.object(accounts, "frappe") as framework:
					framework.get_doc.return_value = doc
					if fails:
						with self.assertRaises(SaveError):
							accounts.disable_user("customer@example.test")
					else:
						accounts.disable_user("customer@example.test")

				self.assertFalse(doc.flags.ignore_permissions)
