# Copyright (c) 2026, Platform and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from platform_core.identity import enterprise_membership


class PLTEnterpriseIdPException(Document):
	"""Immutable exception record of a corporate provider (G-160). See `enterprise_membership`."""

	def before_insert(self):
		enterprise_membership.before_insert(self)

	def validate(self):
		enterprise_membership.validate(self)

	def on_trash(self):
		enterprise_membership.on_trash(self)
