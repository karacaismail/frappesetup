"""AI Action Proposal: a write proposal that waits for human approval (G-86)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr

from platform_core.ai.errors import CONTEXT

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
	"risk_level",
	"source_proposal",
)
# Written once, when the action succeeds (AJA-1002). A revert proposal is built from them, so
# they never change after that.
WRITE_ONCE_FIELDS = ("revert_json", "applied_version")
# Who approved an R3 proposal and when (AJA-1003). Once written, these do not change.
APPROVAL_FIELDS = ("first_approved_at", "second_approver", "second_approved_at")
# A proposal in one of these states is decided. Its state does not change again.
DECIDED_STATES = ("rejected", "expired", "consumed")
AWAITING = "awaiting_second_approval"


class PLTAIActionProposal(Document):
	def validate(self) -> None:
		"""Keep the single-use rule on every write path, not only in the layer's own functions."""
		before = self.get_doc_before_save()
		if self.is_new() or before is None:
			return
		changed = [field for field in FROZEN_FIELDS if cstr(before.get(field)) != cstr(self.get(field))]
		changed += [
			field
			for field in (*WRITE_ONCE_FIELDS, *APPROVAL_FIELDS)
			if cstr(before.get(field)) and cstr(before.get(field)) != cstr(self.get(field))
		]
		# A first approval is never taken back. The owner rejects the proposal instead.
		back_to_pending = before.status == AWAITING and self.status == "pending"
		if (
			changed
			or back_to_pending
			or self._approval_out_of_step(before)
			or (before.status in DECIDED_STATES and self.status != before.status)
		):
			frappe.throw(
				_("A proposal cannot change after it is opened or decided.", context=CONTEXT),
				frappe.PermissionError,
			)

	def _approval_out_of_step(self, before) -> bool:
		"""An approval field may be written only at its own step (AJA-1003).

		The first approval moves a pending proposal to waiting. The second approver is written
		while the proposal waits, and is never the owner.
		"""
		first = not before.first_approved_at and self.first_approved_at
		if first and not (before.status == "pending" and self.status == AWAITING):
			return True
		second = (not before.second_approver and self.second_approver) or (
			not before.second_approved_at and self.second_approved_at
		)
		return bool(second and (before.status != AWAITING or self.second_approver == self.user))
