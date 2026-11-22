"""Servis ayarları. Ayarlar ve sırlar ortam değişkeninden okunur.

Sırlar depoya, günlüğe ve hata metnine yazılmaz.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from identity_sync.mapping import Tenant

PREFIX = "IDENTITY_SYNC_"
DEFAULT_ADMIN_SCOPE = "admin-api kc-admin-api"
MIN_DIGEST_KEY_LENGTH = 16
# The Keycloak event listener refuses a shorter secret too.
MIN_WEBHOOK_SECRET_LENGTH = 16
_TENANT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class ConfigError(Exception):
    """Ayar eksik ya da hatalı. Metin sır değeri taşımaz."""


@dataclass(frozen=True)
class Settings:
    keycloak_public_url: str
    realm: str
    client_id: str
    client_secret: str = field(repr=False)
    press_url: str = ""
    tenants: tuple[Tenant, ...] = ()
    webhook_secret: str = field(default="", repr=False)
    db_path: str = ":memory:"
    # Scope of the Admin API token (docs/sozlesmeler.md, section 2). The service account's
    # Keycloak roles reach only a token requested with this scope.
    admin_scope: str = DEFAULT_ADMIN_SCOPE
    # Secret key of the preview digests. Without a key, a digest would let a reader test
    # an e-mail guess offline.
    digest_key: str = field(default="", repr=False)
    http_timeout: float = 10.0
    keycloak_internal_url: str = ""
    host: str = "127.0.0.1"
    port: int = 8085
    service_audience: str = "identity-sync"
    # İş kilidini beklemenin en uzun süresi. Birim saniyedir.
    lock_timeout: float = 10.0
    # Keycloak realm'in iç kimliği. Keycloak olaylarındaki `realmId` bu değerdir, realm adı değildir.
    realm_id: str = ""
    # Yürütebilen istemciler: yalnız insan onayını denetleyen güvenilir servisler.
    execute_azp: frozenset[str] = frozenset()
    # Yalnız okuyabilen ve önizleyebilen istemciler. Yapay zekâ aracısı bu listeye girer.
    preview_azp: frozenset[str] = frozenset()
    # Service clients of platform_core sites. They may only call /v1/sessions/revoke.
    session_azp: frozenset[str] = frozenset()

    @property
    def staff_azp(self) -> frozenset[str]:
        """Clients of the preview and approval flow."""
        return self.execute_azp | self.preview_azp

    @property
    def known_azp(self) -> frozenset[str]:
        return self.execute_azp | self.preview_azp | self.session_azp

    @property
    def issuer(self) -> str:
        """Belirteçteki `iss` değeri. Her zaman tarayıcının gördüğü adresten üretilir."""
        return f"{self.keycloak_public_url.rstrip('/')}/realms/{self.realm}"

    @property
    def keycloak_base_url(self) -> str:
        """Servisin Keycloak'a ulaştığı adres."""
        return (self.keycloak_internal_url or self.keycloak_public_url).rstrip("/")

    @property
    def token_url(self) -> str:
        return f"{self.keycloak_base_url}/realms/{self.realm}/protocol/openid-connect/token"

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_base_url}/realms/{self.realm}/protocol/openid-connect/certs"


def _url(name: str, value: str) -> str:
    if not re.fullmatch(r"https?://[^\s/]+(/\S*)?", value):
        raise ConfigError(f"{name} must be an http or https URL")
    return value.rstrip("/")


def _tenants(raw: str) -> tuple[Tenant, ...]:
    name = f"{PREFIX}TENANTS"
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        raise ConfigError(f"{name} must be a JSON list") from None
    if not isinstance(rows, list):
        raise ConfigError(f"{name} must be a JSON list")
    tenants = []
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("name", "base_url", "organization")):
            raise ConfigError(f"{name} rows need name, base_url and organization")
        if not _TENANT_NAME.fullmatch(row["name"]):
            raise ConfigError(f"{name} has an invalid tenant name")
        tenants.append(Tenant(name=row["name"], base_url=_url(name, row["base_url"]), organization=row["organization"]))
    return tuple(tenants)


def _names(raw: str) -> frozenset[str]:
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def load_settings(env: Mapping[str, str]) -> Settings:
    """Ayarları ortamdan okur. Eksik ayarların adlarını tek hatada listeler."""
    required = (
        "KEYCLOAK_PUBLIC_URL",
        "CLIENT_SECRET",
        "PRESS_URL",
        "TENANTS",
        "WEBHOOK_SECRET",
        "DIGEST_KEY",
        "DB",
    )
    missing = [f"{PREFIX}{name}" for name in required if not env.get(f"{PREFIX}{name}")]
    if missing:
        raise ConfigError("missing settings: " + ", ".join(missing))

    def get(name: str, default: str = "") -> str:
        return env.get(f"{PREFIX}{name}", default)

    try:
        port = int(get("PORT", "8085"))
        timeout = float(get("HTTP_TIMEOUT", "10"))
        lock_timeout = float(get("LOCK_TIMEOUT", "10"))
    except ValueError:
        raise ConfigError(f"{PREFIX}PORT, {PREFIX}HTTP_TIMEOUT and {PREFIX}LOCK_TIMEOUT must be numbers") from None
    if not 0 < port < 65536 or timeout <= 0 or lock_timeout <= 0:
        raise ConfigError(f"{PREFIX}PORT, {PREFIX}HTTP_TIMEOUT or {PREFIX}LOCK_TIMEOUT is out of range")
    execute_azp, preview_azp = _names(get("EXECUTE_AZP")), _names(get("PREVIEW_AZP"))
    session_azp = _names(get("SESSION_AZP"))
    if execute_azp & preview_azp or session_azp & (execute_azp | preview_azp):
        # Each list grants a different right. A client in two lists would blur that line.
        raise ConfigError(
            f"a client can be in only one of {PREFIX}EXECUTE_AZP, {PREFIX}PREVIEW_AZP and {PREFIX}SESSION_AZP"
        )
    if len(get("WEBHOOK_SECRET")) < MIN_WEBHOOK_SECRET_LENGTH:
        raise ConfigError(f"{PREFIX}WEBHOOK_SECRET must be at least {MIN_WEBHOOK_SECRET_LENGTH} characters long")
    if len(get("DIGEST_KEY")) < MIN_DIGEST_KEY_LENGTH:
        raise ConfigError(f"{PREFIX}DIGEST_KEY must be at least {MIN_DIGEST_KEY_LENGTH} characters long")
    internal = get("KEYCLOAK_INTERNAL_URL")
    return Settings(
        keycloak_public_url=_url(f"{PREFIX}KEYCLOAK_PUBLIC_URL", get("KEYCLOAK_PUBLIC_URL")),
        keycloak_internal_url=_url(f"{PREFIX}KEYCLOAK_INTERNAL_URL", internal) if internal else "",
        realm=get("REALM", "platform"),
        client_id=get("CLIENT_ID", "identity-sync"),
        client_secret=get("CLIENT_SECRET"),
        admin_scope=get("ADMIN_SCOPE", DEFAULT_ADMIN_SCOPE),
        digest_key=get("DIGEST_KEY"),
        press_url=_url(f"{PREFIX}PRESS_URL", get("PRESS_URL")),
        tenants=_tenants(get("TENANTS")),
        webhook_secret=get("WEBHOOK_SECRET"),
        db_path=get("DB"),
        http_timeout=timeout,
        host=get("HOST", "127.0.0.1"),
        port=port,
        service_audience=get("AUDIENCE", "identity-sync"),
        realm_id=get("REALM_ID"),
        execute_azp=execute_azp,
        preview_azp=preview_azp,
        session_azp=session_azp,
        lock_timeout=lock_timeout,
    )
