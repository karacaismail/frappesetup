"""Deletion record for one identity (project record O-27).

Only the identity anonymization module writes these rows. The HMAC key comes
from the `kimlik_deletion_hmac_key` site setting.
"""

from frappe.model.document import Document


class PlatformIdentityDeletion(Document):
	pass
