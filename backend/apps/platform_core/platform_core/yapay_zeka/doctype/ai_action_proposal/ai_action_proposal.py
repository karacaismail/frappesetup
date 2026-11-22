"""AI Action Proposal: a write proposal that waits for human approval (G-86)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr

from platform_core.yapay_zeka.errors import CONTEXT

# What the human approves and who may approve it. These never change after the proposal is opened.
FROZEN_FIELDS = (
	"user",
	"principal",
	"session_id",
	"tool",
	"tool_class",
	"target_doctype",
	"target_name",
	"target_key",
	"target_modified",
	"args_json",
	"preview_json",
	"digest",
	"preview_digest",
)
# A proposal in one of these states is decided. Its state does not change again.
DECIDED_STATES = ("rejected", "expired", "consumed")


class AIActionProposal(Document):
	def validate(self) -> None:
		"""Keep the single-use rule on every write path, not only in the layer's own functions."""
		before = self.get_doc_before_save()
		if self.is_new() or before is None:
			return
		changed = [field for field in FROZEN_FIELDS if cstr(before.get(field)) != cstr(self.get(field))]
		if changed or (before.status in DECIDED_STATES and self.status != before.status):
			frappe.throw(
				_("A proposal cannot change after it is opened or decided.", context=CONTEXT),
				frappe.PermissionError,
			)
