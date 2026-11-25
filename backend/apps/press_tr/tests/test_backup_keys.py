"""G-49: the Site validate hook rejects a malformed backup or Fernet key.

Press's own check (``Site.validate_encryption_key``) never runs: its condition
``key != "encryption_key" or key != "backup_encryption_key"`` is always true. press_tr checks the
key format on every Site validate instead.

The test needs no Frappe install: ``frappe`` is replaced with a stub, so it also runs outside the
Press container. Key values are built at run time; no fixed key is written here.
"""

import ast
import base64
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))


class ValidationFailed(Exception):
	pass


def fake_frappe():
	module = ModuleType("frappe")

	def throw(message, exc=None, title=None):
		raise ValidationFailed(message)

	module.throw = throw
	module._ = lambda text, context=None: text
	module.ValidationError = ValidationFailed
	return module


def valid_key():
	return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def site(*rows):
	return SimpleNamespace(
		name="fixture.example.test",
		configuration=[SimpleNamespace(key=key, value=value, type="Password") for key, value in rows],
	)


class BackupKeyFormatTest(unittest.TestCase):
	def setUp(self):
		self.frappe = fake_frappe()
		patcher = patch.dict(sys.modules, {"frappe": self.frappe})
		patcher.start()
		self.addCleanup(patcher.stop)
		sys.modules.pop("press_tr.backup_keys", None)
		from press_tr import backup_keys

		self.backup_keys = backup_keys

	def test_malformed_key_rejects_site(self):
		good = valid_key()
		malformed = {
			"short": good[:20],
			"no padding": good[:-1],
			"wrong alphabet": good[:10] + "+/" + good[12:],
			"31 bytes": base64.urlsafe_b64encode(os.urandom(31)).decode("ascii"),
			"33 bytes": base64.urlsafe_b64encode(os.urandom(33)).decode("ascii"),
			"space inside": good[:10] + " " + good[11:],
			"empty": "",
			"not text": 12345,
		}
		for field in ("backup_encryption_key", "encryption_key"):
			for label, value in malformed.items():
				with self.subTest(field=field, case=label):
					with self.assertRaises(ValidationFailed) as raised:
						self.backup_keys.validate_site_keys(site((field, value)), "validate")
					message = str(raised.exception)
					self.assertIn(field, message)
					if isinstance(value, str) and value:
						self.assertNotIn(value, message)

	def test_valid_key_keeps_site(self):
		doc = site(
			("backup_encryption_key", valid_key()),
			("encryption_key", valid_key()),
			("some_other_key", "anything"),
		)
		self.backup_keys.validate_site_keys(doc, "validate")

	def test_other_keys_and_masked_value_are_not_checked(self):
		doc = site(("some_other_key", "not-a-key"), ("backup_encryption_key", "*******"))
		self.backup_keys.validate_site_keys(doc, "validate")

	def test_check_writes_no_log(self):
		malformed = valid_key()[:-1]
		with self.assertNoLogs(level="DEBUG"):
			with self.assertRaises(ValidationFailed):
				self.backup_keys.validate_site_keys(
					site(("backup_encryption_key", malformed)), "validate"
				)

	def test_hook_runs_on_site_validate(self):
		hooks = ast.literal_eval(
			next(
				node.value
				for node in ast.parse((APP / "press_tr" / "hooks.py").read_text(encoding="utf-8")).body
				if isinstance(node, ast.Assign) and node.targets[0].id == "doc_events"
			)
		)
		self.assertEqual(hooks["Site"]["validate"], "press_tr.backup_keys.validate_site_keys")


if __name__ == "__main__":
	unittest.main()
