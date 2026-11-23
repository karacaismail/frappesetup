"""G-5: the Agent patch sends offsite backups to an S3-compatible endpoint (Hetzner).

Press sends ``ENDPOINT_URL`` in the offsite auth (press/agent.py, _get_offsite_backup_config).
Unpatched Agent ignores it: boto3 goes to AWS and rclone's endpoint is fixed to amazonaws.com.
The patch adds ``agent/offsite_s3.py`` and routes every offsite S3 client through it.

The helper module is read from the patch itself and tested here; no Agent checkout is needed.
With ``AGENT_SOURCE=<Agent checkout at AGENT_COMMIT>`` the patch is also applied to the source.
Design: backend/docs/handoff/offsite-backup.md and backend/deploy/images/agent-patches/README.md.
Credentials in this file are fixture words, not real keys.
"""

import os
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
PATCHES = DEPLOY / "images" / "agent-patches"
PATCH = PATCHES / "0001-offsite-s3-endpoint.patch"
AGENT_COMMIT = "1956afb39613aafc88d821a9b1762ae397d4f588"
HETZNER = "https://fsn1.your-objectstorage.com"


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
    module = types.ModuleType("offsite_s3")
    exec(compile("\n".join(added) + "\n", "agent/offsite_s3.py", "exec"), module.__dict__)
    return module


def auth(**extra):
    return {"ACCESS_KEY": "fixture-id", "SECRET_KEY": "fixture-secret", **extra}


class AgentPatchFileTest(unittest.TestCase):
    def test_patch_names_agent_commit_and_removal_condition(self):
        self.assertTrue(PATCH.is_file(), "G-5 Agent patch is missing")
        header = patch_text().split("diff --git", 1)[0]
        self.assertIn(f"Agent commit: {AGENT_COMMIT}", header)
        self.assertIn("Remove when:", header)
        readme = (PATCHES / "README.md").read_text(encoding="utf-8")
        self.assertIn(AGENT_COMMIT, readme)
        self.assertIn(PATCH.name, readme)

    def test_every_offsite_client_uses_the_helper(self):
        for path, uses in (
            ("agent/site.py", ("boto3_client_kwargs", "rclone_s3_flags")),
            ("agent/database_server.py", ("boto3_client_kwargs",)),
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
        self.assertEqual(kwargs["aws_access_key_id"], "fixture-id")
        self.assertEqual(kwargs["aws_secret_access_key"], "fixture-secret")

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
        self.assertNotIn("fixture-id", joined)
        self.assertNotIn("fixture-secret", joined)


@unittest.skipUnless(os.environ.get("AGENT_SOURCE"), "set AGENT_SOURCE to an Agent checkout")
class AgentPatchAppliesTest(unittest.TestCase):
    def test_patch_applies_to_pinned_agent(self):
        source = Path(os.environ["AGENT_SOURCE"])
        head = subprocess.run(
            ["git", "-C", source, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        self.assertEqual(head, AGENT_COMMIT)
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "agent"
            shutil.copytree(source, copy, ignore=shutil.ignore_patterns(".git"))
            subprocess.run(["git", "init", "-q", copy], check=True)
            subprocess.run(["git", "-C", copy, "apply", "--check", PATCH], check=True)
            subprocess.run(["git", "-C", copy, "apply", PATCH], check=True)
            for path in ("agent/site.py", "agent/database_server.py"):
                text = (copy / path).read_text(encoding="utf-8")
                with self.subTest(path=path):
                    self.assertNotIn('aws_secret_access_key=auth["SECRET_KEY"]', text)
                    compile(text, path, "exec")
            self.assertNotIn("amazonaws.com", (copy / "agent/site.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
