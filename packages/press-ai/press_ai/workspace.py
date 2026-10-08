"""Yapılandırılmış workspace içinde güvenli dosya erişimi.

Her yol göreli olmalı, `..`/mutlak yol/NUL/ters bölü içeremez ve `.git` bileşeni taşıyamaz. Dizinler
`O_NOFOLLOW | O_DIRECTORY` ile tek tek, üst dizinin tanıtıcısına göre (`dir_fd`) açılır; böylece sembolik
bağ ile workspace dışına çıkma, kontrol ile kullanım arasındaki dizin değişimi dahil, engellenir.
"""
from __future__ import annotations

import os
import stat
import uuid

from .errors import WorkspaceError
from .util import sha256_hex

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
MAX_READ = 2 * 1024 * 1024


def split_relative(path) -> list:
    if not isinstance(path, str) or not path or len(path) > 512:
        raise WorkspaceError("Path must be a non-empty relative string", code="invalid_path")
    if "\x00" in path or "\\" in path or path.startswith("/") or path.startswith("~"):
        raise WorkspaceError("Path must be relative to the workspace root", code="invalid_path")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts:
        raise WorkspaceError("Path points at the workspace root", code="invalid_path")
    for part in parts:
        # Büyük/küçük harfe duyarsız dosya sistemlerinde (APFS varsayılanı) .GIT de .git'tir.
        if part == ".." or part.casefold() == ".git":
            raise WorkspaceError("Path escapes the workspace or touches .git", code="invalid_path")
    return parts


class Workspace:
    def __init__(self, root: str, allow_writes: bool = False):
        self.root = os.path.realpath(root)
        self.allow_writes = allow_writes

    # -- güvenli gezinme --------------------------------------------------------------------------
    def _open_dir(self, parts, create: bool = False) -> int:
        """`parts` dizin bileşenlerini sembolik bağ izlemeden açar; tanıtıcıyı döndürür (çağıran kapatır)."""
        fd = os.open(self.root, _DIR_FLAGS)
        try:
            for part in parts:
                try:
                    next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise WorkspaceError("Directory not found: " + "/".join(parts), code="not_found")
                    os.mkdir(part, 0o755, dir_fd=fd)
                    next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
                except OSError as error:
                    raise WorkspaceError("Refusing to follow a symlink or non-directory at " + part,
                                         code="symlink_or_not_directory") from error
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _lstat(self, parts):
        fd = self._open_dir(parts[:-1])
        try:
            return os.lstat(parts[-1], dir_fd=fd) if hasattr(os, "lstat") else None
        except FileNotFoundError:
            return None
        finally:
            os.close(fd)

    def entries(self, parts) -> list | None:
        """Bir dizinin girdileri (diskteki adlarıyla); dizin yoksa None."""
        try:
            fd = self._open_dir(list(parts))
        except WorkspaceError as error:
            if error.code == "not_found":
                return None
            raise
        try:
            return os.listdir(fd)
        finally:
            os.close(fd)

    def exists(self, path: str) -> bool:
        """Geçersiz yol ve sembolik bağ hata olarak yükselir; yalnız 'bulunamadı' False döner."""
        parts = split_relative(path)
        try:
            return self._lstat(parts) is not None
        except WorkspaceError as error:
            if error.code == "not_found":
                return False
            raise

    def is_dir(self, path: str) -> bool:
        try:
            info = self._lstat(split_relative(path))
        except WorkspaceError:
            return False
        return bool(info) and stat.S_ISDIR(info.st_mode)

    def read_bytes(self, path: str, limit: int = MAX_READ) -> bytes:
        parts = split_relative(path)
        fd = self._open_dir(parts[:-1])
        try:
            try:
                file_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
            except FileNotFoundError:
                raise WorkspaceError("File not found: " + path, code="not_found") from None
            except OSError as error:
                raise WorkspaceError("Refusing to read a symlink: " + path, code="symlink_or_not_directory") from error
            with os.fdopen(file_fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise WorkspaceError("Not a regular file: " + path, code="invalid_path")
                data = handle.read(limit + 1)
        finally:
            os.close(fd)
        if len(data) > limit:
            raise WorkspaceError("File is larger than the read limit: " + path, code="too_large")
        return data

    def read_text(self, path: str, limit: int = MAX_READ) -> str:
        return self.read_bytes(path, limit).decode("utf-8", errors="replace")

    def sha256(self, path: str) -> str | None:
        try:
            return sha256_hex(self.read_bytes(path))
        except WorkspaceError as error:
            if error.code == "not_found":
                return None
            raise

    def walk(self, path: str, max_files: int = 5000) -> list:
        """Sembolik bağları atlayarak düzenli dosyaların göreli yollarını listeler."""
        base = split_relative(path)
        results = []
        stack = [base]
        while stack:
            parts = stack.pop()
            fd = self._open_dir(parts)
            try:
                for entry in sorted(os.listdir(fd)):
                    if entry in (".git", "node_modules", "__pycache__"):
                        continue
                    info = os.lstat(entry, dir_fd=fd)
                    if stat.S_ISLNK(info.st_mode):
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        stack.append(parts + [entry])
                    elif stat.S_ISREG(info.st_mode):
                        results.append("/".join(parts + [entry]))
                        if len(results) >= max_files:
                            raise WorkspaceError("Too many files under " + path, code="too_large")
            finally:
                os.close(fd)
        return sorted(results)

    # -- yazma ------------------------------------------------------------------------------------
    def apply(self, files: list) -> list:
        """Hepsi ya da hiçbiri: taban özetleri doğrulanır, tüm içerik geçici dosyalara yazılıp fsync edilir,
        değiştirilecek dosyaların sabit bağlantılı yedeği alınır; sonra sırayla devreye alınır. Herhangi bir
        adımda hata olursa devreye alınanlar ters sırayla geri alınır. Bu sırada açılan yeni boş dizinler kalabilir."""
        if not self.allow_writes:
            raise WorkspaceError("workspace.allow_writes is false; a human must enable writes in the config",
                                 code="writes_disabled")
        for item in files:
            current = self.sha256(item["path"])
            if item["action"] == "create" and current is not None:
                raise WorkspaceError("File already exists: " + item["path"], code="conflict")
            if item["action"] == "modify" and current != item.get("base_sha256"):
                raise WorkspaceError("File changed since the proposal: " + item["path"], code="conflict")
        staged = []
        committed = []
        try:
            for item in files:  # 1. aşama: geçici dosya + yedek
                parts = split_relative(item["path"])
                entry = {"item": item, "name": parts[-1], "fd": self._open_dir(parts[:-1], create=True),
                         "temp": ".press-ai-" + uuid.uuid4().hex[:10] + ".tmp", "backup": None}
                staged.append(entry)
                data = item["content"].encode("utf-8")
                file_fd = os.open(entry["temp"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                                  0o644, dir_fd=entry["fd"])
                with os.fdopen(file_fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                if item["action"] == "modify":
                    entry["backup"] = ".press-ai-" + uuid.uuid4().hex[:10] + ".bak"
                    os.link(entry["name"], entry["backup"], src_dir_fd=entry["fd"], dst_dir_fd=entry["fd"],
                            follow_symlinks=False)
            for entry in staged:  # 2. aşama: devreye alma
                if entry["item"]["action"] == "create":
                    try:
                        os.link(entry["temp"], entry["name"], src_dir_fd=entry["fd"], dst_dir_fd=entry["fd"],
                                follow_symlinks=False)
                    except FileExistsError:
                        raise WorkspaceError("File appeared during apply: " + entry["item"]["path"],
                                             code="conflict") from None
                else:
                    os.replace(entry["temp"], entry["name"], src_dir_fd=entry["fd"], dst_dir_fd=entry["fd"])
                committed.append(entry)
        except BaseException as error:
            not_restored = []
            for entry in reversed(committed):  # geri alma
                try:
                    if entry["item"]["action"] == "create":
                        os.unlink(entry["name"], dir_fd=entry["fd"])
                    else:
                        os.replace(entry["backup"], entry["name"], src_dir_fd=entry["fd"], dst_dir_fd=entry["fd"])
                        entry["backup"] = None
                except OSError as rollback_error:
                    not_restored.append({"path": entry["item"]["path"], "action": entry["item"]["action"],
                                         "error": type(rollback_error).__name__})
                    entry["backup"] = None  # yedek, elle kurtarma için yerinde kalsın
            if not_restored:
                raise WorkspaceError("Apply failed and some files could not be rolled back", code="failed_partial",
                                     details={"not_restored": not_restored, "cause": type(error).__name__}) from error
            raise
        finally:
            for entry in staged:
                for leftover in (entry["temp"], entry["backup"]):
                    if leftover:
                        try:
                            os.unlink(leftover, dir_fd=entry["fd"])
                        except FileNotFoundError:
                            pass
                os.close(entry["fd"])
        return [{"path": e["item"]["path"], "action": e["item"]["action"],
                 "sha256": sha256_hex(e["item"]["content"].encode("utf-8"))} for e in staged]
