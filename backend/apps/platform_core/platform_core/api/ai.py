"""Endpoints of the AI access layer. The business rules live in the `platform_core.ai` module.

Contract: contracts/platform_core-yapay-zeka.openapi.yaml

The endpoints stay thin, so the permission checks live in the module, not in these functions.
The security gate's `frappe-missing-permission` rule looks for a check inside the function body.
Each suppression below names the function that does the check. `api/test_ai.py` proves every
endpoint refuses a guest and refuses another user's data.
"""

import frappe
from werkzeug.wrappers import Response

from platform_core.ai import access, agent_token, proposals, retention
from platform_core.ai import mcp as mcp_endpoint


# Checked in `mcp._check_principal` (identity type) and, per tool, by the tool's own permission check.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def mcp() -> Response:
	"""MCP endpoint. Requires a human session or an agent token."""
	return mcp_endpoint.handle()


# Checked in `access.require_human`: a human session with a CSRF token. The token acts only as that user.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def issue_agent_token() -> dict:
	"""Issue a short-lived agent token from a human session."""
	return agent_token.issue()


# Checked in `access.human_call`. The query in `store.proposals_of` is limited to the session user.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
def list_proposals(status: str | None = None, limit: int = 20, start: int = 0) -> dict:
	"""List the session user's write proposals page by page."""
	return proposals.list_for_human(status, limit, start)


# Checked in `proposals._own`: the proposal must belong to the session user.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
def get_proposal(proposal_id: str) -> dict:
	"""Return the preview, digest and status of a proposal."""
	return proposals.read_for_human(proposal_id)


# Checked in `proposals.approve`: human session, owner, digest, then the tool's permission again.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def approve_proposal(proposal_id: str, digest: str) -> dict:
	"""Approve the proposal and execute the action in this request. May be destructive."""
	return proposals.approve(proposal_id, digest)


# Checked in `proposals._own`: the proposal must belong to the session user.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def reject_proposal(proposal_id: str) -> dict:
	"""Reject a pending proposal."""
	return proposals.reject(proposal_id)


# Checked in `proposals._own`: the proposal must belong to the session user.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def resolve_proposal(proposal_id: str, outcome: str) -> dict:
	"""Close a proposal with an unknown result by a human decision."""
	return proposals.resolve(proposal_id, outcome)


# Checked in `retention.purge`: `frappe.only_for("System Manager")`.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def purge_logs(
	older_than_days: int = retention.MIN_DAYS, dry_run: bool = True, confirmation_token: str | None = None
) -> dict:
	"""Count records past retention, or delete them with the confirmation token of that count. Destructive."""
	return access.human_call(
		"call",
		"purge_logs",
		lambda: retention.purge_from_web(older_than_days, dry_run, confirmation_token),
	)
