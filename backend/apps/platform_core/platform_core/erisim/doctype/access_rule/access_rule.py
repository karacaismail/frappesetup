"""“Access Rule” kaydı: bir kayıt türünü bir rol için daraltan kural."""

import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.erisim import rules


class AccessRule(Document):
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

	def warn_about_roles_without_rule(self):
		"""Kurallı türde kuralı olmayan rol erişimi kaybeder. Uyarı kaydı durdurmaz."""
		if not self.is_active:
			return
		# Rol listesi sistem verisidir (G-3 istisnası).
		covered = set(
			frappe.get_all(
				rules.RULE_DOCTYPE,
				filters={
					"document_type": self.document_type,
					"is_active": 1,
					"name": ("!=", self.name or ""),
				},
				pluck="role",
			)
		)
		covered.add(self.role)
		with_permission = set(frappe.permissions.get_doctype_roles(self.document_type))
		uncovered = sorted(with_permission - covered - {"Administrator"})
		if uncovered:
			frappe.msgprint(
				_("Roles without an active Access Rule have no access to {0}: {1}").format(
					frappe.bold(self.document_type), ", ".join(uncovered)
				),
				title=_("Access Rule"),
				indicator="orange",
			)

	def on_update(self):
		rules.clear_cache()

	def on_trash(self):
		rules.clear_cache()

	def after_rename(self, old, new, merge=False):
		rules.clear_cache()
