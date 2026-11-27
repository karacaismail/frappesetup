"""Shared helpers: canonical JSON, digest, time and bounded file operations."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import stat


def canonical_json(value) -> bytes:
    """Stable serialisation for the digest: sorted keys, separators without spaces, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def iso(moment: _dt.datetime) -> str:
    return moment.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> _dt.datetime:
    return _dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)


def parse_frappe_datetime(text) -> _dt.datetime | None:
    """Reads a Frappe `YYYY-MM-DD HH:MM:SS[.ffffff]` value as UTC; None if it is not recognised.

    The Press server time zone depends on its configuration; for this reason comparisons only compare
    times that come from the same source (see press_ops)."""
    if not isinstance(text, str) or not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return _dt.datetime.strptime(text[:26], fmt).replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    return None


def ensure_private_dir(path: str) -> str:
    """Creates a directory with mode 0700; refuses a symbolic link or a directory owned by another user."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise OSError("State path must be a real directory: " + path)
    if info.st_uid != os.getuid():
        raise OSError("State directory must be owned by the current user: " + path)
    if info.st_mode & 0o077:
        os.chmod(path, 0o700)
    return path


def write_private_file(path: str, data: bytes, exclusive: bool = True) -> None:
    """Writes a 0600 file; when `exclusive` is set it does not overwrite an existing file (O_EXCL)."""
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def read_limited(path: str, limit: int) -> bytes:
    """Reads at most `limit` bytes without following symbolic links; raises an error for a large file."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("File exceeds size limit: " + path)
    return data
