"""Manual G-37 policy checks and customer-owned encrypted backup downloads.

Uses existing Press APIs. Never creates backups, schedules jobs or restores data.
Python 3.11+ and GnuPG are required; there are no Python package dependencies.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PARTS = ("database", "public", "private")
MAX_JSON_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_BYTES = 20 * 1024**3
NETWORK_TIMEOUT = 30


class ExportError(Exception):
    """A safe error message containing no credentials or signed URLs."""


def check_plan(
    interval_hours: float, completion_hours: float, retry_hours: float
) -> None:
    """Reject plans whose worst-case recovery-point age exceeds 24 hours."""
    values = (interval_hours, completion_hours, retry_hours)
    if any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
        for value in values
    ):
        raise ExportError("Backup plan durations must be finite nonnegative numbers")
    if interval_hours <= 0 or sum(values) > 24:
        raise ExportError("Backup plan exceeds the 24-hour recovery-point limit")


def require_aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ExportError("An explicit timezone is required")


def check_recovery_point(
    data_time: datetime, now: datetime, backup_success: bool, offsite_complete: bool
) -> None:
    """Check the data timestamp, not the later upload-completion timestamp."""
    require_aware(data_time)
    require_aware(now)
    age = now.astimezone(timezone.utc) - data_time.astimezone(timezone.utc)
    if backup_success is not True or offsite_complete is not True:
        raise ExportError("A successful completed offsite backup is required")
    if age < timedelta(0) or age > timedelta(hours=24):
        raise ExportError("Recovery point is outside the 24-hour limit")


def retention_until(archived_at: datetime) -> datetime:
    """Return the six-calendar-month retention floor; never delete anything."""
    require_aware(archived_at)
    year, month_index = divmod(archived_at.year * 12 + archived_at.month - 1 + 6, 12)
    month = month_index + 1
    day = min(archived_at.day, calendar.monthrange(year, month)[1])
    return archived_at.replace(year=year, month=month, day=day)


def read_secret(path: Path) -> bytes:
    """Read a bounded private regular file without following a symlink."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & ~0o600
                or not metadata.st_mode & 0o400
            ):
                raise ExportError(
                    "Secret files must be owner-readable private regular files"
                )
            value = stream.read(4097)
    except OSError:
        raise ExportError("Secret file cannot be read safely") from None
    if len(value) > 4096:
        raise ExportError("Secret file is too large")
    value = value.rstrip(b"\r\n")
    if not value or b"\n" in value or b"\r" in value or b"\x00" in value:
        raise ExportError("Secret file must contain one nonempty line")
    return value


def https_origin(url: str) -> tuple[str, int]:
    """Validate the complete URL before reducing it to a comparable origin."""
    if (
        not isinstance(url, str)
        or not url
        or any(ord(char) <= 32 or ord(char) >= 127 for char in url)
    ):
        raise ExportError("A valid HTTPS address is required")
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError:
        raise ExportError("A valid HTTPS address is required") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "#" in url
        or "\\" in url
    ):
        raise ExportError(
            "Only HTTPS addresses without user information or fragments are allowed"
        )
    return parsed.hostname.lower(), port


def configured_origin(url: str) -> tuple[str, int]:
    origin = https_origin(url)
    parsed = urlsplit(url)
    if parsed.path not in ("", "/") or parsed.query:
        raise ExportError(
            "Configured addresses must be origins without paths or queries"
        )
    return origin


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require_encrypted_header(path: Path) -> None:
    """Require a binary OpenPGP key packet; GnuPG validates the whole message."""
    with path.open("rb") as stream:
        first = stream.read(1)
    if not first or not first[0] & 0x80:
        raise ExportError("Backup is not a binary encrypted OpenPGP message")
    tag = first[0] & 0x3F if first[0] & 0x40 else (first[0] >> 2) & 0x0F
    if tag not in (1, 3):
        raise ExportError("Backup does not begin with an encrypted session-key packet")


def verify_encrypted_backup(
    path: Path, passphrase: bytes, *, timeout: int = 300
) -> None:
    """Decrypt to the null device and require successful integrity verification."""
    require_encrypted_header(path)
    if type(timeout) is not int or timeout <= 0:
        raise ExportError("Verification timeout must be a positive number of seconds")
    with (
        tempfile.TemporaryDirectory(prefix="backup-gpg-") as home,
        tempfile.TemporaryFile() as status,
    ):
        command = [
            "gpg",
            "--no-options",
            "--no-autostart",
            "--homedir",
            home,
            "--batch",
            "--no-tty",
            "--no-symkey-cache",
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--status-fd",
            "1",
            "--output",
            os.devnull,
            "--decrypt",
            str(path),
        ]
        try:
            result = subprocess.run(
                command,
                input=passphrase + b"\n",
                stdout=status,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ExportError(
                "GnuPG verification exceeded the configured time limit"
            ) from None
        except OSError:
            raise ExportError("GnuPG verification could not complete") from None
        status.seek(0)
        output = status.read(65537)
        events = {
            line.split()[1]
            for line in output.splitlines()
            if line.startswith(b"[GNUPG:] ") and len(line.split()) > 1
        }
        failures = {
            b"BADMDC",
            b"DECRYPTION_FAILED",
            b"ERROR",
            b"FAILURE",
            b"NODATA",
            b"UNEXPECTED",
        }
        if (
            result.returncode != 0
            or len(output) > 65536
            or events & failures
            or not {b"DECRYPTION_OKAY", b"GOODMDC"}.issubset(events)
        ):
            raise ExportError("Backup decryption or integrity verification failed")


class BackupClient:
    """Press authentication stays on Press requests; storage receives no identity."""

    def __init__(
        self,
        press_url: str,
        storage_origins: list[str],
        credential_file: Path,
        *,
        opener=None,
    ):
        configured_origin(press_url)
        self.press_url = press_url.rstrip("/")
        self.storage_origins = {configured_origin(url) for url in storage_origins}
        if not self.storage_origins:
            raise ExportError("At least one storage origin is required")
        credential = read_secret(credential_file)
        if not re.fullmatch(rb"[A-Za-z0-9._-]+:[A-Za-z0-9._-]+", credential):
            raise ExportError("Press credential must contain an API key and secret")
        self.authorization = "token " + credential.decode("ascii")
        self.opener = opener if opener is not None else build_opener(NoRedirect())

    def api(self, method: str, parameters: dict[str, str]):
        url = (
            self.press_url
            + "/api/method/press.api.site."
            + method
            + "?"
            + urlencode(parameters)
        )
        request = Request(
            url,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        try:
            with self.opener.open(request, timeout=NETWORK_TIMEOUT) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise ExportError("Press response exceeds the size limit")
            data = json.loads(raw)
        except HTTPError as error:
            error.close()
            raise ExportError("Press request failed") from None
        except (URLError, OSError, ValueError, HTTPException):
            raise ExportError("Press request failed") from None
        if not isinstance(data, dict) or "message" not in data:
            raise ExportError("Press response has no result")
        return data["message"]

    def get_sizes(self, site: str, backup: str) -> dict[str, int]:
        records = self.api("backups", {"name": site})
        if not isinstance(records, list):
            raise ExportError("Press backup list is invalid")
        matches = [
            record
            for record in records
            if isinstance(record, dict) and record.get("name") == backup
        ]
        if len(matches) != 1:
            raise ExportError("Requested backup is not available")
        record = matches[0]
        if (
            record.get("status") != "Success"
            or record.get("offsite") != 1
            or record.get("with_files") != 1
        ):
            raise ExportError("A successful offsite backup with files is required")
        sizes = {}
        for part in PARTS:
            size = record.get(part + "_size")
            if (
                isinstance(size, bool)
                or not isinstance(size, (int, str))
                or not str(size).isascii()
                or not str(size).isdigit()
                or not 0 < int(size) <= DEFAULT_MAX_BYTES * 100
                or not record.get("remote_" + part + "_file")
            ):
                raise ExportError(
                    "Backup metadata is missing a file or a valid byte size"
                )
            sizes[part] = int(size)
        return sizes

    def get_link(self, site: str, backup: str, part: str) -> str:
        if part not in PARTS:
            raise ExportError(
                "Only database, public and private backup files may be downloaded"
            )
        return self.api(
            "get_backup_link", {"name": site, "backup": backup, "file": part}
        )

    def download(
        self, link: str, path: Path, expected_bytes: int, max_bytes: int
    ) -> dict[str, int | str]:
        if https_origin(link) not in self.storage_origins:
            raise ExportError("Storage origin is not allowed")
        if expected_bytes > max_bytes:
            raise ExportError("Backup exceeds the configured file size limit")
        digest = hashlib.sha256()
        size = 0
        request = Request(link, headers={"Accept-Encoding": "identity"})
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with (
                os.fdopen(fd, "wb") as output,
                self.opener.open(request, timeout=NETWORK_TIMEOUT) as response,
            ):
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes or size > expected_bytes:
                        raise ExportError("Backup exceeds its allowed byte size")
                    digest.update(chunk)
                    output.write(chunk)
        except HTTPError as error:
            error.close()
            raise ExportError("Storage download failed") from None
        except (URLError, OSError, HTTPException):
            raise ExportError("Storage download failed") from None
        if size != expected_bytes:
            raise ExportError("Downloaded backup size differs from Press metadata")
        require_encrypted_header(path)
        return {"bytes": size, "sha256": digest.hexdigest()}

    def export(
        self,
        site: str,
        backup: str,
        output: Path,
        passphrase_file: Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        verification_timeout: int = 300,
    ) -> dict[str, dict[str, int | str]]:
        """Publish all three verified ciphertexts, cleaning owned files on failure."""
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ExportError("File size limit must be a positive integer")
        if type(verification_timeout) is not int or verification_timeout <= 0:
            raise ExportError(
                "Verification timeout must be a positive number of seconds"
            )
        if any(
            not isinstance(value, str)
            or not 0 < len(value) <= 255
            or any(ord(char) < 32 or ord(char) > 126 for char in value)
            for value in (site, backup)
        ):
            raise ExportError("A valid site and backup identifier are required")
        passphrase = read_secret(passphrase_file)
        sizes = self.get_sizes(site, backup)
        try:
            output.mkdir(mode=0o700)
        except OSError:
            raise ExportError(
                "Output must be a new directory in an existing parent"
            ) from None
        published = []
        completed = False
        try:
            with tempfile.TemporaryDirectory(prefix=".partial-", dir=output) as staging:
                results = {}
                for part in PARTS:
                    path = Path(staging) / (part + ".gpg")
                    results[path.name] = self.download(
                        self.get_link(site, backup, part), path, sizes[part], max_bytes
                    )
                    verify_encrypted_backup(
                        path, passphrase, timeout=verification_timeout
                    )
                for name in results:
                    # link() never overwrites an existing path, even in a publication race.
                    os.link(Path(staging) / name, output / name)
                    published.append(output / name)
            completed = True
            return results
        finally:
            if not completed:
                for path in published:
                    path.unlink()
                output.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    policy = commands.add_parser(
        "policy", help="Check a plan and observed recovery-point evidence"
    )
    policy.add_argument("--evidence", type=Path, required=True)
    retention = commands.add_parser(
        "retention", help="Compute the six-calendar-month retention floor"
    )
    retention.add_argument("--archived-at", required=True)
    download = commands.add_parser(
        "download", help="Download and verify a customer's encrypted backup"
    )
    download.add_argument("--press-url", required=True)
    download.add_argument("--storage-origin", action="append", required=True)
    download.add_argument("--credential-file", type=Path, required=True)
    download.add_argument("--passphrase-file", type=Path, required=True)
    download.add_argument("--site", required=True)
    download.add_argument("--backup", required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    download.add_argument("--verification-timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        if args.command == "policy":
            with args.evidence.open("rb") as stream:
                evidence = json.loads(stream.read(MAX_JSON_BYTES + 1))
            check_plan(
                evidence["interval_hours"],
                evidence["completion_hours"],
                evidence["retry_hours"],
            )
            check_recovery_point(
                datetime.fromisoformat(evidence["data_time"]),
                datetime.now(timezone.utc),
                evidence["backup_success"],
                evidence["offsite_complete"],
            )
            result = {"policy": "pass", "maximum_recovery_point_age_hours": 24}
        elif args.command == "retention":
            result = {
                "retain_until": retention_until(
                    datetime.fromisoformat(args.archived_at)
                ).isoformat()
            }
        else:
            client = BackupClient(
                args.press_url, args.storage_origin, args.credential_file
            )
            result = client.export(
                args.site,
                args.backup,
                args.output,
                args.passphrase_file,
                max_bytes=args.max_bytes,
                verification_timeout=args.verification_timeout_seconds,
            )
        print(json.dumps(result, indent=2))
        return 0
    except ExportError as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, OverflowError, HTTPException):
        print(
            "Backup operation failed: invalid input or unavailable local file",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
