"""G-49: check the format of a Site's backup and Fernet keys when the Site is saved.

Press keeps ``backup_encryption_key`` and ``encryption_key`` in the Site configuration table as
Password rows. Press has its own format check, ``Site.validate_encryption_key``, but it never runs:
its condition ``key != "encryption_key" or key != "backup_encryption_key"`` is always true. A
malformed key is then stored, and the site's backups or Password fields cannot be read later.

``validate_site_keys`` runs on every Site validate (``doc_events`` in hooks.py). A valid key is a
Fernet key: 32 random bytes in URL-safe base64, 44 characters with one ``=`` at the end. This is
the form ``Fernet.generate_key()`` and Frappe's ``encryption_key`` use.

The error message names the field only. The key value is never written to a message or a log.
"""

import base64
import binascii
import re

KEY_FIELDS = ("backup_encryption_key", "encryption_key")
# Press shows this mask instead of a Password value; it is not a new key.
MASK = "*******"
_FERNET_KEY = re.compile(r"[A-Za-z0-9_-]{43}=")


def is_valid_key(value):
	if not isinstance(value, str) or not _FERNET_KEY.fullmatch(value):
		return False
	try:
		return len(base64.urlsafe_b64decode(value)) == 32
	except (binascii.Error, ValueError):
		return False


def validate_site_keys(doc, method=None):
	for row in doc.configuration or ():
		if row.key not in KEY_FIELDS or row.value == MASK:
			continue
		if not is_valid_key(row.value):
			import frappe
			from frappe import _

			frappe.throw(
				_(
					"The {0} value is not a valid key. A valid key is 44 characters of URL-safe "
					"base64 and ends with one = sign. Copy the key again exactly.",
					context="press_tr",
				).format(row.key),
				frappe.ValidationError,
			)
