"""Tool errors: each error carries a machine-readable `code` and detail without secret values."""
from __future__ import annotations


class KitError(Exception):
    """A tool call was deliberately refused or could not be completed."""

    code = "error"

    def __init__(self, message: str, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        if code:
            self.code = code
        self.details = details or {}

    def as_dict(self) -> dict:
        return {"error": self.code, "message": str(self), "details": self.details}


class ConfigError(KitError):
    code = "not_configured"


class ValidationError(KitError):
    code = "invalid_params"


class ContractError(KitError):
    code = "contract"


class ApprovalError(KitError):
    code = "approval_required"


class PreconditionError(KitError):
    code = "precondition_failed"


class PressError(KitError):
    """Press returned an error; `kind` may be permission/validation/not_found/server/protocol."""

    code = "press_error"

    def __init__(self, message: str, kind: str, http_status: int | None = None, details: dict | None = None):
        details = dict(details or {})
        details.update({"kind": kind, "http_status": http_status})
        super().__init__(message, code="press_" + kind, details=details)
        self.kind = kind
        self.http_status = http_status


class PressTimeout(KitError):
    """No response within the request time: the outcome of the remote operation is unknown."""

    code = "timeout_unknown_outcome"


class WorkspaceError(KitError):
    code = "workspace"
