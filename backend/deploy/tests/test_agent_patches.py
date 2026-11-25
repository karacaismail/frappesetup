"""G-5: the Agent patch sends offsite backups to an S3-compatible endpoint (Hetzner).

Press sends ``ENDPOINT_URL`` in the offsite auth (press/agent.py, _get_offsite_backup_config).
Unpatched Agent ignores it: boto3 goes to AWS and rclone's endpoint is fixed to amazonaws.com.
The patch adds ``agent/offsite_s3.py`` and routes every offsite S3 client through it.

The helper module is read from the patch itself and tested here; no Agent checkout is needed.
With ``AGENT_SOURCE=<Agent checkout at AGENT_COMMIT>`` the patch is also applied to the source.
Design: backend/docs/handoff/offsite-backup.md and backend/deploy/images/agent-patches/README.md.
Credentials in this file are fixture words, not real keys.
"""

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import sys
import textwrap
import types
import unittest
from unittest import mock
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
PATCHES = DEPLOY / "images" / "agent-patches"
PATCH = PATCHES / "0001-offsite-s3-endpoint.patch"
AGENT_COMMIT = "1956afb39613aafc88d821a9b1762ae397d4f588"
HETZNER = "https://fsn1.your-objectstorage.com"
FIXTURE_ID = "fixture-id"
FIXTURE_KEY = "fixture-secret"
GIT = shutil.which("git")


def load_module(name, source, path, **names):
    """Run source as a module from a temporary file. ``names`` are its preset globals."""
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / Path(path).name
        file.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        module.__dict__.update(names)
        spec.loader.exec_module(module)
    return module


def git(*arguments):
    """Run git with an absolute path and no shell. Output on stderr stays visible."""
    return subprocess.run(
        [GIT, *map(str, arguments)], stdout=subprocess.PIPE, text=True, check=True
    ).stdout


def patch_text():
    return PATCH.read_text(encoding="utf-8")


def file_diff(path):
    """The part of the patch that changes one file."""
    parts = re.split(r"^(?=diff --git )", patch_text(), flags=re.MULTILINE)
    return next(part for part in parts if part.startswith(f"diff --git a/{path} b/{path}"))


def helper_module():
    added = [
        line[1:]
        for line in file_diff("agent/offsite_s3.py").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return load_module("offsite_s3", "\n".join(added) + "\n", "agent/offsite_s3.py")


PATCHED_FILES = ("agent/site.py", "agent/database_server.py", "agent/snapshot_recovery.py")


def patched_paths():
    return re.findall(r"^diff --git a/(\S+) b/", patch_text(), flags=re.MULTILINE)


def auth(**extra):
    return {"ACCESS_KEY": FIXTURE_ID, "SECRET_KEY": FIXTURE_KEY, **extra}


class AgentPatchFileTest(unittest.TestCase):
    def test_patch_names_agent_commit_and_removal_condition(self):
        self.assertTrue(PATCH.is_file(), "G-5 Agent patch is missing")
        header = patch_text().split("diff --git", 1)[0]
        self.assertIn(f"Agent commit: {AGENT_COMMIT}", header)
        self.assertIn("Remove when:", header)
        readme = (PATCHES / "README.md").read_text(encoding="utf-8")
        self.assertIn(AGENT_COMMIT, readme)
        self.assertIn(PATCH.name, readme)

    def test_header_names_every_patched_file(self):
        header = patch_text().split("diff --git", 1)[0]
        for path in patched_paths():
            with self.subTest(path=path):
                self.assertIn(path, header)

    def test_every_offsite_client_uses_the_helper(self):
        for path, uses in (
            ("agent/site.py", ("boto3_client_kwargs", "rclone_s3_flags")),
            ("agent/database_server.py", ("boto3_client_kwargs",)),
            ("agent/snapshot_recovery.py", ("boto3_client_kwargs",)),
        ):
            diff = file_diff(path)
            added = "\n".join(l for l in diff.splitlines() if l.startswith("+"))
            for name in uses:
                with self.subTest(path=path, helper=name):
                    self.assertIn(f"offsite_s3.{name}(", added)

    def test_patch_has_no_credentials(self):
        text = patch_text()
        self.assertNotRegex(text, r"AKIA[0-9A-Z]{16}")
        self.assertNotRegex(text, r"(?i)(secret|access)_?key\s*[:=]\s*['\"][A-Za-z0-9/+]{16,}")


class OffsiteHelperTest(unittest.TestCase):
    def setUp(self):
        self.helper = helper_module()

    def test_boto3_uses_endpoint_when_press_sends_one(self):
        kwargs = self.helper.boto3_client_kwargs(auth(REGION="fsn1", ENDPOINT_URL=HETZNER))
        self.assertEqual(kwargs["endpoint_url"], HETZNER)
        self.assertEqual(kwargs["region_name"], "fsn1")
        self.assertEqual(kwargs["aws_access_key_id"], FIXTURE_ID)
        self.assertEqual(kwargs["aws_secret_access_key"], FIXTURE_KEY)

    def test_boto3_without_endpoint_stays_as_before(self):
        self.assertNotIn("endpoint_url", self.helper.boto3_client_kwargs(auth(REGION="eu-central-1")))
        for empty in (None, ""):
            kwargs = self.helper.boto3_client_kwargs(auth(ENDPOINT_URL=empty))
            self.assertNotIn("endpoint_url", kwargs)
            self.assertNotIn("region_name", kwargs)

    def test_rclone_uses_other_provider_and_endpoint(self):
        for label in ("AWS S3", "S3 Compatible", None):
            with self.subTest(provider=label):
                flags = self.helper.rclone_s3_flags(
                    auth(REGION="fsn1", PROVIDER=label, ENDPOINT_URL=HETZNER)
                )
                self.assertEqual(flags[flags.index("--s3-provider") + 1], "Other")
                self.assertEqual(flags[flags.index("--s3-endpoint") + 1], HETZNER)
                self.assertEqual(flags[flags.index("--s3-region") + 1], "fsn1")
                self.assertIn("--s3-env-auth=true", flags)

    def test_rclone_aws_without_endpoint_stays_as_before(self):
        flags = self.helper.rclone_s3_flags(auth(REGION="eu-central-1", PROVIDER="AWS S3"))
        self.assertEqual(
            flags,
            [
                "--s3-provider", "AWS",
                "--s3-region", "eu-central-1",
                "--s3-endpoint", "s3.eu-central-1.amazonaws.com",
                "--s3-env-auth=true",
            ],
        )

    def test_rclone_refuses_missing_endpoint_or_unknown_provider(self):
        for bad in (
            auth(REGION="fsn1", PROVIDER="S3 Compatible"),
            auth(REGION="fsn1", PROVIDER="Unknown"),
            auth(PROVIDER="AWS S3"),
        ):
            with self.subTest(auth=bad.get("PROVIDER")):
                with self.assertRaises(KeyError):
                    self.helper.rclone_s3_flags(bad)

    def test_endpoint_must_be_https(self):
        for bad in ("http://fsn1.your-objectstorage.com", "fsn1.your-objectstorage.com"):
            with self.subTest(endpoint=bad):
                with self.assertRaises(KeyError):
                    self.helper.boto3_client_kwargs(auth(ENDPOINT_URL=bad))
                with self.assertRaises(KeyError):
                    self.helper.rclone_s3_flags(auth(REGION="fsn1", ENDPOINT_URL=bad))

    def test_credentials_never_reach_rclone_flags(self):
        flags = self.helper.rclone_s3_flags(auth(REGION="fsn1", ENDPOINT_URL=HETZNER))
        joined = " ".join(flags)
        self.assertNotIn(FIXTURE_ID, joined)
        self.assertNotIn(FIXTURE_KEY, joined)


@unittest.skipUnless(os.environ.get("AGENT_SOURCE"), "set AGENT_SOURCE to an Agent checkout")
class AgentPatchAppliesTest(unittest.TestCase):
    def test_patch_applies_to_pinned_agent(self):
        self.assertIsNotNone(GIT, "git is required")
        source = Path(os.environ["AGENT_SOURCE"])
        head = git("-C", source, "rev-parse", "HEAD").strip()
        self.assertEqual(head, AGENT_COMMIT)
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "agent"
            shutil.copytree(source, copy, ignore=shutil.ignore_patterns(".git"))
            git("init", "-q", copy)
            git("-C", copy, "apply", "--check", PATCH)
            git("-C", copy, "apply", PATCH)
            for path in PATCHED_FILES:
                text = (copy / path).read_text(encoding="utf-8")
                with self.subTest(path=path):
                    compile(text, path, "exec")
            for path in sorted((copy / "agent").rglob("*.py")):
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=str(path.relative_to(copy))):
                    self.assertNotIn('aws_secret_access_key=auth["SECRET_KEY"]', text)
            self.assertNotIn("amazonaws.com", (copy / "agent/site.py").read_text(encoding="utf-8"))
            self.snapshot_upload = snapshot_upload_function(copy)
            self.check_snapshot_upload()

    def check_snapshot_upload(self):
        for extra, endpoint in (
            ({"REGION": "fsn1", "ENDPOINT_URL": HETZNER}, HETZNER),
            ({"REGION": "eu-central-1"}, None),
            ({}, None),
        ):
            with self.subTest(snapshot_auth=sorted(extra)):
                service, kwargs, uploads = run_snapshot_upload(self.snapshot_upload, auth(**extra))
                self.assertEqual(service, "s3")
                self.assertEqual(kwargs.get("endpoint_url"), endpoint)
                self.assertEqual(kwargs.get("region_name"), extra.get("REGION"))
                self.assertEqual(uploads, [("bucket", "prefix/site.sql.gz")])


def snapshot_upload_function(copy):
    """upload_backup_files_to_s3 from the patched snapshot_recovery.py, without Agent's imports."""
    path = copy / "agent/snapshot_recovery.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "upload_backup_files_to_s3"
    )
    # The segment starts at "def", so the decorators stay out.
    source = textwrap.dedent(ast.get_source_segment(text, function, padded=True)) + "\n"
    module = load_module(
        "snapshot_recovery_upload", source, path.name, os=os, offsite_s3=helper_module()
    )
    return module.upload_backup_files_to_s3


def run_snapshot_upload(upload, snapshot_auth):
    calls, uploads = [], []

    class FakeClient:
        def upload_fileobj(self, data, bucket, key):
            uploads.append((bucket, key))

    def client(service, **kwargs):
        calls.append((service, kwargs))
        return FakeClient()

    with tempfile.TemporaryDirectory() as folder:
        backup = Path(folder) / "site.sql.gz"
        backup.write_bytes(b"fixture")
        files = {"database": {"file": str(backup), "path": str(backup)}}
        offsite = {"bucket": "bucket", "auth": snapshot_auth, "path": "prefix"}
        with mock.patch.dict(sys.modules, {"boto3": types.SimpleNamespace(client=client)}):
            upload(None, files, offsite)
    [(service, kwargs)] = calls
    return service, kwargs, uploads


if __name__ == "__main__":
    unittest.main()
