"""Real local OpenPGP verification; requires GnuPG, never contacts a service."""

import gzip
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "backup_export.py"
spec = importlib.util.spec_from_file_location("backup_export", SOURCE)
backup_export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backup_export
spec.loader.exec_module(backup_export)


@unittest.skipUnless(shutil.which("gpg"), "GnuPG is not installed in this runtime")
class RealEncryptionTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("frappe"), "Frappe is not installed in this runtime"
    )
    def test_frappe_backup_encryption_produces_supported_ciphertext(self):
        from frappe.utils import backups

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "synthetic-database.sql.gz"
            public = root / "synthetic-files.tar"
            private = root / "synthetic-private-files.tar"
            database.write_bytes(
                gzip.compress(b"CREATE TABLE synthetic (value INT);\n")
            )
            public.write_bytes(b"\x00" * 10240)
            private.write_bytes(b"\x00" * 10240)
            backup = SimpleNamespace(
                backup_path_db=str(database),
                backup_path_files=str(public),
                backup_path_private_files=str(private),
            )
            with patch.object(
                backups,
                "get_or_generate_backup_encryption_key",
                return_value="synthetic-key",
            ):
                backups.BackupGenerator.backup_encryption(backup)
            for path in [database, public, private]:
                backup_export.verify_encrypted_backup(path, b"synthetic-key")

    def test_encrypted_backup_wrong_key_tampering_and_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "gpg"
            home.mkdir(mode=0o700)
            clear = root / "synthetic.sql.gz"
            clear.write_bytes(gzip.compress(b"CREATE TABLE synthetic (value INT);\n"))
            encrypted = root / "synthetic.gpg"
            subprocess.run(
                [
                    "gpg",
                    "--no-options",
                    "--no-autostart",
                    "--no-symkey-cache",
                    "--s2k-count",
                    "65536",  # Synthetic fixture: avoid agent-based calibration.
                    "--homedir",
                    str(home),
                    "--batch",
                    "--no-tty",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase-fd",
                    "0",
                    "--symmetric",
                    "--output",
                    str(encrypted),
                    str(clear),
                ],
                input=b"synthetic-key\n",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
            backup_export.verify_encrypted_backup(encrypted, b"synthetic-key")
            with self.assertRaises(backup_export.ExportError):
                backup_export.verify_encrypted_backup(encrypted, b"wrong-key")
            with self.assertRaises(backup_export.ExportError):
                backup_export.verify_encrypted_backup(clear, b"synthetic-key")
            damaged = root / "damaged.gpg"
            data = bytearray(encrypted.read_bytes())
            data[-3] ^= 1
            damaged.write_bytes(data)
            with self.assertRaises(backup_export.ExportError):
                backup_export.verify_encrypted_backup(damaged, b"synthetic-key")


if __name__ == "__main__":
    unittest.main()
