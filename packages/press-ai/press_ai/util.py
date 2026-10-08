"""Ortak yardımcılar: kanonik JSON, özet, zaman ve sınırlı dosya işlemleri."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import stat


def canonical_json(value) -> bytes:
    """Özet için kararlı serileştirme: sıralı anahtar, boşluksuz ayraç, UTF-8."""
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
    """Frappe `YYYY-MM-DD HH:MM:SS[.ffffff]` değerini UTC kabul ederek okur; tanınmazsa None.

    Press sunucu saat dilimi yapılandırmaya bağlıdır; karşılaştırmalarda bu nedenle yalnız aynı
    kaynaktan gelen zamanlar birbiriyle kıyaslanır (bkz. press_ops)."""
    if not isinstance(text, str) or not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return _dt.datetime.strptime(text[:26], fmt).replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    return None


def ensure_private_dir(path: str) -> str:
    """Dizini 0700 oluşturur; sembolik bağ veya başka kullanıcıya ait dizini reddeder."""
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
    """0600 dosya yazar; `exclusive` iken var olan dosyanın üzerine yazmaz (O_EXCL)."""
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def read_limited(path: str, limit: int) -> bytes:
    """Sembolik bağı izlemeden en fazla `limit` bayt okur; büyük dosyada hata verir."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("File exceeds size limit: " + path)
    return data
