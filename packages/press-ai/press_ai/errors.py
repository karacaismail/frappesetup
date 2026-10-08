"""Araç hataları: her hata makinece okunur bir `code` ve gizli değer içermeyen ayrıntı taşır."""
from __future__ import annotations


class KitError(Exception):
    """Araç çağrısının isteyerek reddedildiği veya tamamlanamadığı durum."""

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
    """Press yanıtı hata döndürdü; `kind` permission/validation/not_found/server/protocol olabilir."""

    code = "press_error"

    def __init__(self, message: str, kind: str, http_status: int | None = None, details: dict | None = None):
        details = dict(details or {})
        details.update({"kind": kind, "http_status": http_status})
        super().__init__(message, code="press_" + kind, details=details)
        self.kind = kind
        self.http_status = http_status


class PressTimeout(KitError):
    """İstek süresinde yanıt alınamadı: uzak işlemin sonucu bilinmez (unknown)."""

    code = "timeout_unknown_outcome"


class WorkspaceError(KitError):
    code = "workspace"
