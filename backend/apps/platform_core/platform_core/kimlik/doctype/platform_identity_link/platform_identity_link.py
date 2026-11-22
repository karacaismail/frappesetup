# Copyright (c) 2026, Platform and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PlatformIdentityLink(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		issuer: DF.Data
		subject: DF.Data
		user: DF.Link
	# end: auto-generated types

	def validate(self):
		self.issuer = (self.issuer or "").strip()
		self.subject = (self.subject or "").strip()
		if not self.issuer or not self.subject:
			frappe.throw(
				_("Issuer and subject are required.", context="platform_core.kimlik"), frappe.MandatoryError
			)


def on_doctype_update():
	"""V-8: the `(issuer, subject)` pair is unique in the database."""
	frappe.db.add_unique("Platform Identity Link", ["issuer", "subject"])
