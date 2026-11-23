"""G-37 contract tests with synthetic backups and no network access."""

import importlib.util
import http.client
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "backup_export.py"
spec = importlib.util.spec_from_file_location("backup_export", SOURCE)
backup_export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backup_export
spec.loader.exec_module(backup_export)


class BackupPolicyTests(unittest.TestCase):
    def test_plan_includes_completion_and_retry_budget(self):
        backup_export.check_plan(20, 2, 2)
        for values in [
            (24, 1, 0),
            (23, 0, 2),
            (0, 0, 0),
            (True, 1, 1),
            (float("nan"), 1, 1),
        ]:
            with (
                self.subTest(values=values),
                self.assertRaises(backup_export.ExportError),
            ):
                backup_export.check_plan(*values)

    def test_observed_recovery_point_must_be_successful_offsite_and_recent(self):
        now = datetime(2026, 11, 23, tzinfo=UTC)
        backup_export.check_recovery_point(now - timedelta(hours=24), now, True, True)
        for delta, success, offsite in [
            (timedelta(hours=24, seconds=1), True, True),
            (timedelta(seconds=-1), True, True),
            (timedelta(hours=1), False, True),
            (timedelta(hours=1), True, False),
        ]:
            with (
                self.subTest(delta=delta),
                self.assertRaises(backup_export.ExportError),
            ):
                backup_export.check_recovery_point(now - delta, now, success, offsite)

    def test_naive_times_are_rejected(self):
        with self.assertRaises(backup_export.ExportError):
            backup_export.check_recovery_point(
                datetime(2026, 1, 1), datetime.now(UTC), True, True
            )

    def test_retention_uses_six_calendar_months_and_preserves_time(self):
        self.assertEqual(
            backup_export.retention_until(datetime(2026, 8, 31, 9, 30, tzinfo=UTC)),
            datetime(2027, 2, 28, 9, 30, tzinfo=UTC),
        )
        self.assertEqual(
            backup_export.retention_until(datetime(2027, 8, 31, tzinfo=UTC)),
            datetime(2028, 2, 29, tzinfo=UTC),
        )

    def test_policy_cli_rejects_stale_evidence_without_printing_its_content(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            evidence.write_text(
                json.dumps(
                    {
                        "interval_hours": 20,
                        "completion_hours": 2,
                        "retry_hours": 2,
                        "data_time": "2000-01-01T00:00:00+00:00",
                        "backup_success": True,
                        "offsite_complete": True,
                        "private_note": "never-print-this",
                    }
                )
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SOURCE),
                    "policy",
                    "--evidence",
                    str(evidence),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("never-print-this", result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)


class BackupExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credential = self.root / "credential"
        self.credential.write_text("synthetic-key:synthetic-secret")
        self.credential.chmod(0o600)
        self.passphrase = self.root / "passphrase"
        self.passphrase.write_text("synthetic-passphrase")
        self.passphrase.chmod(0o600)
        self.requests = []
        self.payload = b"\x8csynthetic encrypted bytes"
        self.client = backup_export.BackupClient(
            "https://press.example.test",
            ["https://storage.example.test"],
            self.credential,
            opener=self,
        )
        self.verifier = patch.object(backup_export, "verify_encrypted_backup")
        self.verify = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def open(self, request, timeout):
        self.requests.append(request)
        if (
            "/site.backups?" in request.full_url
            or "/press.api.site.backups?" in request.full_url
        ):
            record = {
                "name": "backup-1",
                "status": "Success",
                "offsite": 1,
                "with_files": 1,
            }
            for part in ["database", "public", "private"]:
                record[part + "_size"] = str(len(self.payload))
                record["remote_" + part + "_file"] = part + "-remote"
            return io.BytesIO(json.dumps({"message": [record]}).encode())
        if request.full_url.startswith("https://press.example.test/"):
            return io.BytesIO(
                json.dumps(
                    {"message": "https://storage.example.test/file?signature=private"}
                ).encode()
            )
        return io.BytesIO(self.payload)

    def export(self, **kwargs):
        return self.client.export(
            "tenant.example.test",
            "backup-1",
            self.root / "result",
            self.passphrase,
            **kwargs,
        )

    def test_three_parts_download_without_forwarding_press_auth(self):
        result = self.export()
        self.assertEqual(set(result), {"database.gpg", "public.gpg", "private.gpg"})
        self.assertEqual(self.verify.call_count, 3)
        for request in self.requests:
            if request.full_url.startswith("https://storage.example.test/"):
                self.assertIsNone(request.get_header("Authorization"))
            else:
                self.assertTrue(
                    request.get_header("Authorization").startswith("token ")
                )
                self.assertNotIn("file=config", request.full_url)
        for name, metadata in result.items():
            self.assertEqual((self.root / "result" / name).read_bytes(), self.payload)
            self.assertEqual(metadata["bytes"], len(self.payload))
            self.assertEqual(len(metadata["sha256"]), 64)
            self.assertEqual(
                (self.root / "result" / name).stat().st_mode & 0o777, 0o600
            )
        self.assertEqual((self.root / "result").stat().st_mode & 0o777, 0o700)

    def test_unencrypted_or_wrong_key_leaves_no_download(self):
        self.verify.side_effect = backup_export.ExportError(
            "Encryption verification failed"
        )
        with self.assertRaises(backup_export.ExportError):
            self.export()
        self.assertFalse((self.root / "result").exists())

    def test_size_limit_is_enforced_while_streaming(self):
        with self.assertRaises(backup_export.ExportError):
            self.export(max_bytes=4)
        self.assertFalse((self.root / "result").exists())

    def test_existing_output_is_preserved(self):
        (self.root / "result").mkdir()
        (self.root / "result" / "keep").write_text("keep")
        with self.assertRaises(backup_export.ExportError):
            self.export()
        self.assertEqual((self.root / "result" / "keep").read_text(), "keep")

    def test_storage_origin_and_https_are_enforced_before_network(self):
        for url in [
            "http://storage.example.test/file",
            "https://evil.example.test/file",
            "https://user:secret@storage.example.test/file",
            "https://storage.example.test:444/file",
            "https://storage.example.test/file#fragment",
        ]:
            with (
                self.subTest(url=url),
                patch.object(self.client, "get_link", return_value=url),
            ):
                with self.assertRaises(backup_export.ExportError):
                    self.export()
        self.assertTrue(
            all(
                request.full_url.startswith("https://press.example.test/")
                for request in self.requests
            )
        )

    def test_press_denial_is_not_leaked_or_retried(self):
        import urllib.error

        with patch.object(
            self,
            "open",
            side_effect=urllib.error.HTTPError(
                "https://press.example.test/?secret", 403, "private message", {}, None
            ),
        ):
            with self.assertRaisesRegex(
                backup_export.ExportError, "Press request failed"
            ) as raised:
                self.export()
        self.assertNotIn("secret", str(raised.exception))
        self.assertFalse((self.root / "result").exists())

    def test_malformed_http_response_is_sanitized_for_press_and_storage(self):
        for destination in ["press", "storage"]:
            original_open = self.open

            def broken_open(request, timeout):
                if ("press.example.test" in request.full_url) == (
                    destination == "press"
                ):
                    raise http.client.IncompleteRead(b"private-response-content", 100)
                return original_open(request, timeout)

            with (
                self.subTest(destination=destination),
                patch.object(self, "open", side_effect=broken_open),
            ):
                with self.assertRaises(backup_export.ExportError) as raised:
                    self.export()
                self.assertNotIn("private-response-content", str(raised.exception))
            self.assertFalse((self.root / "result").exists())

    def test_actual_storage_bytes_cannot_exceed_declared_size(self):
        with patch.object(
            self.client, "get_sizes", return_value={p: 2 for p in backup_export.PARTS}
        ):
            with self.assertRaises(backup_export.ExportError):
                self.export(max_bytes=1024)
        self.assertFalse((self.root / "result").exists())

    def test_verification_timeout_is_configurable_and_positive(self):
        self.export(verification_timeout=900)
        self.assertEqual(self.verify.call_args.kwargs["timeout"], 900)
        with self.assertRaisesRegex(backup_export.ExportError, "timeout"):
            self.export(verification_timeout=0)

    def test_blank_links_and_wrong_sizes_fail_closed(self):
        with patch.object(self.client, "get_link", return_value=None):
            with self.assertRaises(backup_export.ExportError):
                self.export()
        with patch.object(
            self.client,
            "get_sizes",
            return_value={p: 999 for p in ["database", "public", "private"]},
        ):
            with self.assertRaises(backup_export.ExportError):
                self.export()
        self.assertFalse((self.root / "result").exists())

    def test_failed_or_missing_backup_metadata_is_rejected(self):
        for message in [
            [],
            [{"name": "backup-1", "status": "Failure"}],
            [{"name": "another-backup", "status": "Success"}],
        ]:
            with (
                self.subTest(message=message),
                patch.object(self.client, "api", return_value=message),
            ):
                with self.assertRaises(backup_export.ExportError):
                    self.export()

    def test_plain_gzip_is_rejected_even_if_verifier_is_misconfigured(self):
        for payload in [b"\x1f\x8bnot-encrypted", b"synthetic.tar\x00" * 64]:
            self.payload = payload
            with self.assertRaises(backup_export.ExportError):
                self.export()
        self.verify.assert_not_called()

    def test_secret_permissions_and_symlinks_are_rejected(self):
        self.credential.chmod(0o644)
        with self.assertRaises(backup_export.ExportError):
            backup_export.read_secret(self.credential)
        link = self.root / "link"
        link.symlink_to(self.passphrase)
        with self.assertRaises(backup_export.ExportError):
            backup_export.read_secret(link)

    def test_redirect_handler_never_follows_storage_or_press_redirects(self):
        handler = backup_export.NoRedirect()
        self.assertIsNone(
            handler.redirect_request(
                None, None, 302, "redirect", {}, "https://evil.test"
            )
        )

    def test_gpg_requires_integrity_status_and_hides_passphrase(self):
        self.verifier.stop()
        path = self.root / "sample.gpg"
        path.write_bytes(b"\x8csynthetic")

        def gpg_result(status):
            def run(command, **kwargs):
                kwargs["stdout"].write(status)
                return subprocess.CompletedProcess(command, 0)

            return run

        for status in [b"", b"[GNUPG:] DECRYPTION_OKAY\n", b"[GNUPG:] GOODMDC\n"]:
            with patch.object(subprocess, "run", side_effect=gpg_result(status)):
                with self.assertRaises(backup_export.ExportError):
                    backup_export.verify_encrypted_backup(path, b"synthetic-passphrase")
        with patch.object(
            subprocess,
            "run",
            side_effect=gpg_result(b"[GNUPG:] DECRYPTION_OKAY\n[GNUPG:] GOODMDC\n"),
        ) as run:
            backup_export.verify_encrypted_backup(path, b"synthetic-passphrase")
        self.assertNotIn("synthetic-passphrase", " ".join(run.call_args.args[0]))
        self.assertEqual(run.call_args.kwargs["input"], b"synthetic-passphrase\n")
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
