"""Identity policy for service embeddings of the local Press toolbox."""

import re

from .errors import ApprovalError, ConfigError

SERVICE_OPERATIONS = frozenset({
    "team.context", "release_group.list", "release_group.get", "release_group.dependencies",
    "app_source.branches", "deploy_candidate.list", "deploy_candidate.get", "build.get",
    "deploy.status", "bench.list", "agent_job.list", "agent_job.get", "error_log.list",
    "press.version", "server.list", "server.get", "press_settings.flags", "build.triage",
    "release_group.create", "release_group.add_app", "app_release.create",
    "deploy_candidate.create", "build.start", "deploy.start",
})
PRESS_TOOLS = frozenset({
    "kit_status", "press_read", "press_triage_build", "press_propose", "press_execute", "press_track",
})


def require_tool(ctx, name, arguments):
    """Check the configured service boundary before performing any HTTP request."""
    if name not in PRESS_TOOLS:
        raise ConfigError("This identity may use only Press operation tools", code="identity_scope")
    record = None
    if name in ("press_execute", "press_track"):
        record = ctx.store.load(arguments["proposal_id"])
        if record.get("kind") != "press":
            raise ConfigError("This identity may use only Press proposals", code="identity_scope")
        operation = record["operation"]
    elif name == "press_triage_build":
        operation = "build.triage"
    else:
        operation = arguments.get("operation")
    if ctx.config.press.identity == "service_account" and operation is not None:
        if operation not in SERVICE_OPERATIONS:
            raise ConfigError("Operation is not enabled for a service account", code="identity_scope")
    if name == "kit_status":
        return
    client = ctx.press()
    client.verify_identity()
    if record is not None and record["authority"] != client.authority():
        raise ApprovalError("Proposal belongs to another Press identity or target", code="authority_changed")


def audit(ctx, name, event, arguments):
    from . import press_ops

    press = ctx.config.press
    subject = press.subject
    if press.identity == "delegated" and ctx.delegated_bearer is not None:
        subject = ctx.delegated_bearer.subject
    entry = {"event": event, "tool": name, "identity": press.identity,
             "subject": subject, "base_url": press.base_url, "team": press.team}
    if isinstance(arguments, dict):
        operation = arguments.get("operation")
        if isinstance(operation, str):
            allowed = set(press_ops.READS) | set(press_ops.MUTATIONS)
            entry["operation"] = operation if operation in allowed else "unknown_operation"
        if name == "press_triage_build":
            entry["operation"] = "build.triage"
        proposal = arguments.get("proposal_id")
        if isinstance(proposal, str):
            entry["proposal_id"] = proposal if re.fullmatch(r"p-[0-9a-f]{20}", proposal) else "unknown_proposal"
    ctx.store.audit(entry, required=True)
