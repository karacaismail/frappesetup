"""Endpoints of the AI access layer. The business rules live in the `platform_core.ai` module.

Contract: contracts/platform_core-ai.openapi.yaml

The endpoints stay thin, so the permission checks live in the module, not in these functions.
The security gate's `frappe-missing-permission` rule looks for a check inside the function body.
Each suppression below names the function that does the check. `api/test_ai.py` proves every
protected endpoint refuses guests and that discovery exposes only public metadata.
"""

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from platform_core.ai import access, agent_token, oauth, proposals, retention, revert
from platform_core.ai import mcp as mcp_endpoint


# Checked in `mcp._check_principal` (identity type) and, per tool, by the tool's own permission check.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=120, seconds=60, user_based=True)
def mcp() -> Response:
	"""MCP endpoint. Requires an accepted session or bearer credential."""
	return mcp_endpoint.handle()


# This public document discloses only validated discovery settings when OAuth is enabled.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=60, seconds=60)
def mcp_resource_metadata() -> Response:
	"""Return the OAuth protected resource metadata as bare JSON."""
	return oauth.resource_metadata()


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


# Checked in `proposals._own`: the source proposal must belong to the session user. The new
# proposal's preview checks the write permission on the record again.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def propose_revert(proposal_id: str) -> dict:
	"""Open a pending proposal that writes the old values of an applied proposal back."""
	return revert.propose(proposal_id)


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
