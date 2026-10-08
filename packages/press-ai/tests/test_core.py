"""Çekirdek: şema, yapılandırma, kimlik bilgisi, maskeleme ve onay deposu."""
import json
import os
import stat
import unittest

import support  # noqa: F401  (sys.path)
from press_ai import credentials
from press_ai.config import Config
from press_ai.errors import ApprovalError, ConfigError, ValidationError
from press_ai.proposals import ProposalStore, digest_of
from press_ai.redaction import Redactor
from press_ai.schema import check_schema, validate
from support import Clock, TempHome, make_config


class SchemaTests(unittest.TestCase):
    SCHEMA = {"type": "object", "additionalProperties": False, "required": ["site"],
              "properties": {"site": {"type": "string", "pattern": r"[a-z.]+"}, "flag": {"type": "boolean"}}}

    def test_rejects_unknown_fields_such_as_confirm(self):
        with self.assertRaises(ValidationError):
            validate({"site": "a.b", "confirm": True}, self.SCHEMA)

    def test_types_are_strict(self):
        with self.assertRaises(ValidationError):
            validate({"site": "a.b", "flag": 1}, self.SCHEMA)
        with self.assertRaises(ValidationError):
            validate({"site": "A/../b"}, self.SCHEMA)

    def test_open_object_schemas_must_be_closed_when_fields_are_declared(self):
        with self.assertRaises(ValueError):
            check_schema({"type": "object", "properties": {"a": {"type": "string"}}})
        check_schema({"type": "object", "additionalProperties": True})


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.cleanup()

    def base(self, **press):
        data = {"base_url": "https://press.example.test", "principal": "team", "team": "team-alpha",
                "credentials": {"source": "file", "path": self.home.credentials()}}
        data.update(press)
        return {"press": data, "approval": {"state_dir": self.home.path("state")}}

    def test_requires_https_except_explicit_loopback(self):
        with self.assertRaises(ConfigError):
            Config(self.base(base_url="http://press.example.test"))
        with self.assertRaises(ConfigError):
            Config(self.base(base_url="http://127.0.0.1:8000"))
        Config(self.base(base_url="http://127.0.0.1:8000", allow_insecure_loopback=True))

    def test_rejects_url_with_credentials_or_path(self):
        for url in ("https://user:pw@press.example.test", "https://press.example.test/api", "https://x.test?a=1"):
            with self.assertRaises(ConfigError):
                Config(self.base(base_url=url))

    def test_team_principal_needs_team(self):
        with self.assertRaises(ConfigError):
            Config(self.base(team=None))

    def test_unknown_keys_are_rejected(self):
        data = self.base()
        data["press"]["confirm_all"] = True
        with self.assertRaises(ConfigError):
            Config(data)

    def test_state_dir_cannot_live_in_repository(self):
        repo_state = os.path.join(os.path.dirname(support.PACKAGE), "..", "state")
        data = self.base()
        data["approval"]["state_dir"] = os.path.abspath(repo_state)
        with self.assertRaises(ConfigError):
            Config(data)

    def test_operator_with_mutations_needs_team(self):
        with self.assertRaises(ConfigError):
            Config(self.base(principal="operator", team=None, enabled_mutations=["build.start"]))
        Config(self.base(principal="operator", team=None))  # yalnız okuma: takım isteğe bağlı

    def test_example_config_loads(self):
        path = os.path.join(support.PACKAGE, "config", "press-ai.example.json")
        with open(path) as handle:
            data = json.load(handle)
        data["workspace"]["root"] = self.home.workspace(copy_fixture=False)
        data["approval"]["state_dir"] = self.home.path("state")
        config = Config(data)
        self.assertEqual(config.press.enabled_mutations, [])
        self.assertFalse(config.workspace.allow_writes)
        with open(os.path.join(support.PACKAGE, "config", "mcp.example.json")) as handle:
            args = json.load(handle)["mcpServers"]["press-ai"]["args"]
        self.assertEqual(args[0], "-I")
        self.assertIn("serve", args)

    def test_summary_never_contains_secret(self):
        _, config = make_config(self.home, "https://press.example.test")
        text = json.dumps([config.press.summary(), config.approval.summary()])
        self.assertNotIn(support.SECRET, text)
        self.assertIn("speed bump", config.approval.summary()["limitation"])


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.cleanup()

    def test_file_must_be_private(self):
        path = self.home.credentials(mode=0o644)
        with self.assertRaises(ConfigError):
            credentials.load({"source": "file", "path": path})

    def test_file_symlink_rejected(self):
        real = self.home.credentials()
        link = self.home.path("link.json")
        os.symlink(real, link)
        with self.assertRaises(ConfigError):
            credentials.load({"source": "file", "path": link})

    def test_file_inside_forbidden_root_rejected(self):
        path = self.home.credentials()
        with self.assertRaises(ConfigError):
            credentials.load({"source": "file", "path": path}, forbidden_roots=[self.home.root])

    def test_repr_and_errors_hide_secret(self):
        creds = credentials.load({"source": "file", "path": self.home.credentials()})
        self.assertNotIn(support.SECRET, repr(creds))
        self.assertTrue(creds.authorization().startswith("token "))

    def test_env_source_reads_named_variables_only(self):
        os.environ["PRESS_AI_TEST_KEY"], os.environ["PRESS_AI_TEST_SECRET"] = "abcd1234", "efgh5678"
        try:
            creds = credentials.load(credentials.validate_spec(
                {"source": "env", "key_env": "PRESS_AI_TEST_KEY", "secret_env": "PRESS_AI_TEST_SECRET"}))
            self.assertEqual(creds.authorization(), "token abcd1234:efgh5678")
        finally:
            del os.environ["PRESS_AI_TEST_KEY"], os.environ["PRESS_AI_TEST_SECRET"]


# Sahte değer çalışma anında birleştirilir: depoda gerçek anahtar biçiminde dize durmaz.
FAKE_AWS_KEY_ID = "AKIA" + "ABCDEFGHIJKLMNOP"


class RedactionTests(unittest.TestCase):
    def test_masks_known_secret_shapes(self):
        r = Redactor(["supersecretvalue"])
        text = ("Authorization: token abcd1234ef:9876zyxw supersecretvalue https://u:p4ss@host.test/x "
                + FAKE_AWS_KEY_ID + " password=hunter2 \"api_secret\": \"xyz12345\"")
        out = r.text(text)
        for leaked in ("abcd1234ef", "9876zyxw", "supersecretvalue", "p4ss", FAKE_AWS_KEY_ID, "hunter2",
                       "xyz12345"):
            self.assertNotIn(leaked, out)

    def test_plain_words_survive(self):
        self.assertEqual(Redactor().text("token expiration was checked"), "token expiration was checked")

    def test_commit_hashes_survive(self):
        sha = "ebf3e2272dc386e9ceb5e064d6c911d7e2adb7c9"
        self.assertIn(sha, Redactor().text("built from " + sha))


class ProposalStoreTests(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        _, self.config = make_config(self.home)
        self.clock = Clock()
        self.store = ProposalStore(self.config.approval, self.clock, Redactor())

    def tearDown(self):
        self.home.cleanup()

    def proposal(self, level="single"):
        return self.store.create("press", "site.backup", {"base_host": "h"}, "s.example.test", {"site": "s"},
                                 {"transport": "method"}, {"impact": {}}, level,
                                 "MIGRATE s.example.test" if level == "double" else None)

    def test_state_files_are_private(self):
        record = self.proposal()
        path = os.path.join(self.home.path("state"), "proposals", record["id"] + ".json")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.home.path("state")).st_mode), 0o700)

    def test_requires_human_approval(self):
        record = self.proposal()
        with self.assertRaises(ApprovalError) as caught:
            self.store.require_approved(record["id"], "press")
        self.assertEqual(caught.exception.code, "approval_required")
        self.assertIn("approve", caught.exception.details["human_approval_command"])

    def test_approval_is_single_use(self):
        record = self.proposal()
        self.store.write_approval(record["id"], record)
        self.store.require_approved(record["id"], "press")
        self.store.consume(record["id"])
        with self.assertRaises(ApprovalError) as caught:
            self.store.require_approved(record["id"], "press")
        self.assertEqual(caught.exception.code, "already_consumed")
        with self.assertRaises(ApprovalError):
            self.store.consume(record["id"])

    def test_approval_expires(self):
        record = self.proposal()
        self.store.write_approval(record["id"], record)
        self.clock.advance(seconds=self.config.approval.approval_ttl + 1)
        with self.assertRaises(ApprovalError) as caught:
            self.store.require_approved(record["id"], "press")
        self.assertEqual(caught.exception.code, "approval_expired")

    def test_tampered_proposal_is_rejected(self):
        record = self.proposal()
        self.store.write_approval(record["id"], record)
        path = os.path.join(self.home.path("state"), "proposals", record["id"] + ".json")
        with open(path) as handle:
            data = json.load(handle)
        data["params"]["site"] = "other.example.test"
        with open(path, "w") as handle:
            json.dump(data, handle)
        with self.assertRaises(ApprovalError) as caught:
            self.store.require_approved(record["id"], "press")
        self.assertEqual(caught.exception.code, "state_tampered")

    def test_approval_for_other_digest_is_rejected(self):
        record = self.proposal()
        forged = dict(record, digest="0" * 64)
        self.store.write_approval(record["id"], forged)
        with self.assertRaises(ApprovalError) as caught:
            self.store.require_approved(record["id"], "press")
        self.assertEqual(caught.exception.code, "approval_mismatch")

    def test_wrong_kind_is_rejected(self):
        record = self.proposal()
        self.store.write_approval(record["id"], record)
        with self.assertRaises(ApprovalError):
            self.store.require_approved(record["id"], "workspace")

    def test_rejected_proposal_cannot_run(self):
        record = self.proposal()
        self.store.write_rejection(record["id"], "no")
        self.assertEqual(self.store.status(record["id"])["state"], "rejected")

    def test_invalid_ids_cannot_traverse(self):
        for bad in ("../x", "p-../../etc", "p-" + "g" * 20):
            with self.assertRaises(ApprovalError):
                self.store.status(bad)

    def test_separate_approver_mode_is_refused(self):
        with self.assertRaises(ConfigError) as caught:
            make_config(self.home, approver_uid=os.getuid() + 1)
        self.assertIn("not supported", str(caught.exception))
        self.assertIn("not an OS or cryptographic boundary", self.config.approval.summary()["limitation"])

    def test_approval_never_outlives_the_proposal(self):
        record = self.proposal()
        self.clock.advance(seconds=self.config.approval.proposal_ttl - 60)
        approval = self.store.write_approval(record["id"], record)
        self.assertEqual(approval["expires_at"], record["expires_at"])
        self.clock.advance(seconds=61)
        with self.assertRaises(ApprovalError):
            self.store.require_approved(record["id"], "press")

    def test_consumed_without_outcome_counts_as_unknown(self):
        # Süreç tüketimden sonra, sonuç yazılmadan öldüyse kör tekrar yine engellenir.
        record = self.proposal()
        self.store.write_approval(record["id"], record)
        self.store.consume(record["id"])
        self.assertEqual(self.store.outcome(record["id"])["state"], "unknown")
        self.assertEqual(self.store.status(record["id"])["outcome"]["phase"], "consumed_without_outcome")
        self.assertEqual(len(self.store.unresolved("site.backup", "s.example.test")), 1)

    def test_target_lock_is_exclusive_and_released_by_the_os(self):  # R2
        lock = self.store.acquire_target_lock("site.backup", "s.example.test", "p-" + "1" * 20)
        with self.assertRaises(ApprovalError) as caught:
            self.store.acquire_target_lock("site.backup", "s.example.test", "p-" + "2" * 20)
        self.assertEqual(caught.exception.code, "in_flight")
        other = self.store.acquire_target_lock("site.backup", "other.example.test", "p-" + "3" * 20)
        self.store.release_target_lock(other)
        self.store.release_target_lock(lock)
        # Kilit dosyası yerinde kalır ama tutan yoktur: dosya silinmeden yeniden alınır (PID'e dayanılmaz).
        again = self.store.acquire_target_lock("site.backup", "s.example.test", "p-" + "4" * 20)
        self.store.release_target_lock(again)
        locks = os.listdir(os.path.join(self.home.path("state"), "locks"))
        self.assertEqual(len(locks), 2)


if __name__ == "__main__":
    unittest.main()
