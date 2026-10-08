"""Yapılandırma dosyasını yükler ve yetki sınırlarını doğrular.

Yapılandırma insan tarafından yazılır; MCP araçları onu değiştiremez. Bölümler isteğe bağlıdır:
`press` yoksa Press araçları, `workspace` yoksa uygulama araçları `not_configured` döner.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

from . import credentials as _credentials
from .errors import ConfigError

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONTRACTS_DIR = os.path.join(PACKAGE_ROOT, "contracts")
DEFAULT_STATE_DIR = "~/.local/state/press-ai"
_TEAM = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._@-]{0,139}")
_TOP_KEYS = {"press", "workspace", "approval", "references", "contracts_dir"}


def _repo_root() -> str:
    """Paketin içinde bulunduğu depo kökü (packages/press-ai → iki üst dizin); depo değilse paketin kendisi.

    Secret ve onay durumu bu kökün altına yazılamaz; paket başka yere kopyalandığında geniş bir üst
    dizin (ör. ev dizini) yanlışlıkla yasaklı sayılmasın diye kök yalnız bir depo işaretiyle kabul edilir."""
    candidate = os.path.dirname(os.path.dirname(PACKAGE_ROOT))
    if os.path.exists(os.path.join(candidate, ".git")):
        return candidate
    return PACKAGE_ROOT


def _inside(path: str, root: str) -> bool:
    try:
        real_root = os.path.realpath(root)
        return os.path.commonpath([os.path.realpath(path), real_root]) == real_root
    except ValueError:
        return False


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class PressConfig:
    def __init__(self, data: dict):
        allowed = {"base_url", "principal", "team", "credentials", "timeout_seconds", "enabled_mutations",
                   "allow_insecure_loopback"}
        unknown = set(data) - allowed
        if unknown:
            raise ConfigError("unknown press keys: " + ", ".join(sorted(unknown)))
        base = data.get("base_url")
        if not isinstance(base, str):
            raise ConfigError("press.base_url is required")
        parts = urlsplit(base)
        insecure_ok = data.get("allow_insecure_loopback") is True
        if parts.scheme == "http":
            if not (insecure_ok and parts.hostname and _loopback(parts.hostname)):
                raise ConfigError("press.base_url must use https (plain http only for loopback tests)")
        elif parts.scheme != "https":
            raise ConfigError("press.base_url must use https")
        if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
            raise ConfigError("press.base_url must be scheme://host[:port] without credentials or path")
        if not parts.hostname:
            raise ConfigError("press.base_url has no host")
        self.base_url = "{}://{}".format(parts.scheme, parts.netloc)
        self.host = parts.hostname
        principal = data.get("principal")
        if principal not in ("team", "operator"):
            raise ConfigError("press.principal must be team or operator")
        self.principal = principal
        team = data.get("team")
        if team is not None and (not isinstance(team, str) or not _TEAM.fullmatch(team)):
            raise ConfigError("press.team has an invalid format")
        if principal == "team" and not team:
            raise ConfigError("press.team is required for the team principal")
        self.team = team
        self.credentials_spec = _credentials.validate_spec(data.get("credentials"))
        timeout = data.get("timeout_seconds", 30)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 120:
            raise ConfigError("press.timeout_seconds must be between 1 and 120")
        self.timeout = float(timeout)
        enabled = data.get("enabled_mutations", [])
        if not isinstance(enabled, list) or not all(isinstance(x, str) for x in enabled):
            raise ConfigError("press.enabled_mutations must be a list of operation ids")
        self.enabled_mutations = list(dict.fromkeys(enabled))
        if principal == "operator" and self.enabled_mutations and not team:
            # System User @protected'ı atlar; sahiplik ön koşulları ancak bir takıma göre anlamlıdır.
            raise ConfigError("press.team is required when the operator principal has enabled mutations")

    def summary(self) -> dict:
        return {"base_host": self.host, "principal": self.principal, "team": self.team,
                "credentials_source": self.credentials_spec["source"], "timeout_seconds": self.timeout,
                "enabled_mutations": self.enabled_mutations}


class WorkspaceConfig:
    def __init__(self, data: dict):
        unknown = set(data) - {"root", "allow_writes"}
        if unknown:
            raise ConfigError("unknown workspace keys: " + ", ".join(sorted(unknown)))
        root = data.get("root")
        if not isinstance(root, str):
            raise ConfigError("workspace.root is required")
        root = os.path.expanduser(root)
        if not os.path.isabs(root) or not os.path.isdir(root) or os.path.islink(root):
            raise ConfigError("workspace.root must be an existing absolute directory (not a symlink)")
        real = os.path.realpath(root)
        home = os.path.realpath(os.path.expanduser("~"))
        if real in ("/", home) or os.path.dirname(real) == real:
            raise ConfigError("workspace.root is too broad; point it at a bench apps directory or one app")
        self.root = real
        self.allow_writes = data.get("allow_writes", False) is True

    def summary(self) -> dict:
        return {"root": self.root, "allow_writes": self.allow_writes}


class ApprovalConfig:
    def __init__(self, data: dict, forbidden_roots):
        unknown = set(data) - {"state_dir", "approver_uid", "approval_ttl_seconds", "proposal_ttl_seconds"}
        if unknown:
            raise ConfigError("unknown approval keys: " + ", ".join(sorted(unknown)))
        state = os.path.expanduser(data.get("state_dir", DEFAULT_STATE_DIR))
        if not os.path.isabs(state):
            raise ConfigError("approval.state_dir must be absolute")
        for root in forbidden_roots:
            if root and _inside(state, root):
                raise ConfigError("approval.state_dir must live outside the repository and workspace")
        self.state_dir = state
        if data.get("approver_uid") is not None:
            # Ayrı OS hesabıyla onay bu sürümde uygulanmadı ve test edilmedi; yarım bir sınır sunulmaz.
            raise ConfigError("approval.approver_uid is not supported: approvals run as the same OS user as the "
                              "server (a speed bump, not a security boundary)")
        self.approval_ttl = self._ttl(data, "approval_ttl_seconds", 900)
        self.proposal_ttl = self._ttl(data, "proposal_ttl_seconds", 3600)

    @staticmethod
    def _ttl(data, key, default):
        value = data.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or not 60 <= value <= 86400:
            raise ConfigError("approval." + key + " must be between 60 and 86400 seconds")
        return value

    mode = "same_os_account"

    def summary(self) -> dict:
        limitation = ("Approval runs as the same OS user as this server. It stops the model from approving "
                      "through MCP, but any process with this user's shell can run the approve CLI or edit the "
                      "state directory. It is a speed bump, not an OS or cryptographic boundary. A separate "
                      "approver account is not supported.")
        return {"mode": self.mode, "state_dir": self.state_dir, "approval_ttl_seconds": self.approval_ttl,
                "proposal_ttl_seconds": self.proposal_ttl, "limitation": limitation}


class Config:
    def __init__(self, data: dict, path: str | None = None):
        if not isinstance(data, dict):
            raise ConfigError("configuration must be a JSON object")
        unknown = set(data) - _TOP_KEYS
        if unknown:
            raise ConfigError("unknown configuration keys: " + ", ".join(sorted(unknown)))
        self.path = path
        self.press = PressConfig(data["press"]) if data.get("press") is not None else None
        self.workspace = WorkspaceConfig(data["workspace"]) if data.get("workspace") is not None else None
        self.forbidden_roots = [_repo_root()]
        if self.workspace:
            self.forbidden_roots.append(self.workspace.root)
        self.approval = ApprovalConfig(data.get("approval") or {}, self.forbidden_roots)
        refs = data.get("references") or {}
        if set(refs) - {"pressguide_sitemap"}:
            raise ConfigError("unknown references keys")
        sitemap = refs.get("pressguide_sitemap")
        if sitemap is not None:
            sitemap = os.path.expanduser(sitemap)
            if not os.path.isabs(sitemap):
                raise ConfigError("references.pressguide_sitemap must be absolute")
        self.sitemap_path = sitemap
        contracts = data.get("contracts_dir")
        self.contracts_dir = os.path.expanduser(contracts) if contracts else DEFAULT_CONTRACTS_DIR

    @classmethod
    def load(cls, path: str) -> "Config":
        path = os.path.abspath(os.path.expanduser(path))
        try:
            with open(path, "rb") as handle:
                raw = handle.read(65537)
        except OSError as error:
            raise ConfigError("cannot read configuration: " + error.strerror) from None
        if len(raw) > 65536:
            raise ConfigError("configuration file is too large")
        try:
            data = json.loads(raw)
        except ValueError:
            raise ConfigError("configuration is not valid JSON") from None
        return cls(data, path)

    @classmethod
    def empty(cls) -> "Config":
        return cls({})
