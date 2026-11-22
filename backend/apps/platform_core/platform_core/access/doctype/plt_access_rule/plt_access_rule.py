"""The “Access Rule” record: a rule that narrows a document type for a role."""

import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.access import rules


class PLTAccessRule(Document):
	def validate(self):
		self.validate_document_type()
		self.validate_scope()
		self.filters = rules.validate_filters(self.document_type, self.filters)
		if not any(self.get(f"allow_{operation}") for operation in rules.OPERATIONS):
			frappe.throw(_("Select at least one operation for the rule."))
		self.warn_about_roles_without_rule()

	def validate_document_type(self):
		meta = frappe.get_meta(self.document_type)
		if self.document_type in rules.PROTECTED_DOCTYPES:
			frappe.throw(_("Access Rules cannot govern {0}.").format(frappe.bold(self.document_type)))
		if meta.istable or meta.issingle or meta.is_virtual:
			frappe.throw(_("Access Rules cannot govern child tables, single or virtual document types."))

	def validate_scope(self):
		if self.scope not in rules.SCOPES:
			frappe.throw(_("Scope must be one of: {0}").format(", ".join(rules.SCOPES)))
		if self.scope == "all":
			self.match_field = None
			return
		if not self.match_field:
			frappe.throw(_("Match Field is required unless the scope is all."))
		kind = rules.match_kind(self.document_type, self.match_field)
		if kind not in rules.SCOPE_KINDS[self.scope]:
			frappe.throw(
				_("Match Field {0} must point to one of: {1}").format(
					frappe.bold(self.match_field), ", ".join(rules.SCOPE_KINDS[self.scope])
				)
			)

	def roles_without_rule(self) -> list[str]:
		"""Roles that may read the document type by role permission but have no active rule.

		The result describes the state after this rule is saved. It is empty when the document
		type would not be governed at all.
		"""
		# The role list is system data (exception to G-3).
		covered = set(
			frappe.get_all(
				rules.RULE_DOCTYPE,
				filters={
					"document_type": self.document_type,
					"is_active": 1,
					"name": ("!=", self.name or ""),
				},
				pluck="role",
				limit=0,  # every active rule of the type; the rule table is small
			)
		)
		if self.is_active:
			covered.add(self.role)
		if not covered:
			return []
		with_permission = set(frappe.permissions.get_doctype_roles(self.document_type))
		return sorted(with_permission - covered - {"Administrator"})

	def warn_about_roles_without_rule(self):
		"""In a governed document type a role without a rule loses access. The warning does not stop the save."""
		if not self.is_active:
			return
		uncovered = self.roles_without_rule()
		if uncovered:
			frappe.msgprint(
				_("Roles without an active Access Rule have no access to {0}: {1}").format(
					frappe.bold(self.document_type), ", ".join(uncovered)
				),
				title=_("PLT Access Rule"),
				indicator="orange",
			)

	def on_update(self):
		rules.clear_cache()

	def on_trash(self):
		rules.clear_cache()

	def after_rename(self, old, new, merge=False):
		rules.clear_cache()
