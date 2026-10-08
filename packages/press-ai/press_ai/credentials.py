"""Press kimlik bilgisini yükler; değer hiçbir araç çıktısına, loga veya repr'a girmez.

Desteklenen kaynaklar:
- `file`: kullanıcıya ait, 0600, sembolik bağ olmayan JSON dosyası `{"api_key": "...", "api_secret": "..."}`;
  repo veya workspace içinde olamaz.
- `keychain`: macOS `security find-generic-password -s <service> -a <account> -w`; saklanan değer `key:secret`.
- `env`: adı verilen iki ortam değişkeni. MCP istemci yapılandırmasına secret yazmayı teşvik ettiği için en zayıf yoldur.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess

from .errors import ConfigError

_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
_KEYCHAIN_TEXT = re.compile(r"[A-Za-z0-9._@:-]{1,128}")
_SECURITY = "/usr/bin/security"


class Credentials:
    __slots__ = ("_key", "_secret", "source")

    def __init__(self, key: str, secret: str, source: str):
        if not key or not secret or ":" in key or any(c.isspace() for c in key + secret):
            raise ConfigError("Press credentials are malformed (" + source + ")")
        self._key = key
        self._secret = secret
        self.source = source

    def authorization(self) -> str:
        return "token {}:{}".format(self._key, self._secret)

    def secret_values(self) -> list:
        return [self._key, self._secret, self._key + ":" + self._secret]

    def __repr__(self) -> str:
        return "Credentials(source={!r}, value=<redacted>)".format(self.source)


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False


def validate_spec(spec: dict) -> dict:
    """Yapılandırmadaki kaynak tanımını doğrular; secret okumaz."""
    if not isinstance(spec, dict):
        raise ConfigError("press.credentials must be an object")
    source = spec.get("source")
    if source == "file":
        if set(spec) != {"source", "path"} or not isinstance(spec["path"], str):
            raise ConfigError("file credentials need exactly {source, path}")
        path = os.path.expanduser(spec["path"])
        if not os.path.isabs(path):
            raise ConfigError("credential file path must be absolute")
        return {"source": "file", "path": path}
    if source == "keychain":
        if set(spec) != {"source", "service", "account"}:
            raise ConfigError("keychain credentials need exactly {source, service, account}")
        for key in ("service", "account"):
            if not isinstance(spec[key], str) or not _KEYCHAIN_TEXT.fullmatch(spec[key]):
                raise ConfigError("keychain " + key + " has an invalid format")
        return dict(spec)
    if source == "env":
        if set(spec) != {"source", "key_env", "secret_env"}:
            raise ConfigError("env credentials need exactly {source, key_env, secret_env}")
        for key in ("key_env", "secret_env"):
            if not isinstance(spec[key], str) or not _ENV_NAME.fullmatch(spec[key]):
                raise ConfigError("env variable name has an invalid format")
        return dict(spec)
    raise ConfigError("press.credentials.source must be file, keychain or env")


def load(spec: dict, forbidden_roots=()) -> Credentials:
    """Doğrulanmış kaynaktan kimlik bilgisini okur. Hata iletileri değer içermez."""
    source = spec["source"]
    if source == "file":
        path = spec["path"]
        for root in forbidden_roots:
            if root and _inside(path, root):
                raise ConfigError("credential file must live outside the repository and workspace")
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            raise ConfigError("credential file does not exist") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ConfigError("credential file must be a regular file, not a symlink")
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ConfigError("credential file must be owned by the current user with mode 0600")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(4097)
        if len(raw) > 4096:
            raise ConfigError("credential file is too large")
        try:
            data = json.loads(raw)
        except ValueError:
            raise ConfigError("credential file is not valid JSON") from None
        if not isinstance(data, dict) or set(data) != {"api_key", "api_secret"}:
            raise ConfigError("credential file must contain exactly api_key and api_secret")
        return Credentials(str(data["api_key"]), str(data["api_secret"]), "file")
    if source == "keychain":
        try:
            result = subprocess.run(
                [_SECURITY, "find-generic-password", "-s", spec["service"], "-a", spec["account"], "-w"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ConfigError("keychain lookup failed") from None
        value = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode != 0 or ":" not in value:
            raise ConfigError("keychain item not found or not in key:secret form")
        key, secret = value.split(":", 1)
        return Credentials(key, secret, "keychain")
    if source == "env":
        key = os.environ.get(spec["key_env"], "")
        secret = os.environ.get(spec["secret_env"], "")
        if not key or not secret:
            raise ConfigError("credential environment variables are not set")
        return Credentials(key, secret, "env")
    raise ConfigError("unknown credential source")
