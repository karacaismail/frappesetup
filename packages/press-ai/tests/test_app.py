"""Uygulama geliştirme: workspace sınırı, statik kurallar, değişiklik planı ve onaylı uygulama."""
import ast
import json
import os
import shutil
import sys
import unittest
from unittest import mock

import support
from press_ai import app_static
from press_ai.errors import ApprovalError, KitError, ValidationError, WorkspaceError
from press_ai.tools import Context, Toolbox
from press_ai.workspace import Workspace
from support import Clock, TempHome, approve, make_config


class WorkspaceBoundary(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.root = self.home.workspace()
        self.ws = Workspace(self.root, allow_writes=True)
        os.makedirs(self.home.path("outside"))
        with open(self.home.path("outside", "secret.txt"), "w") as handle:
            handle.write("outside secret")

    def tearDown(self):
        self.home.cleanup()

    def test_rejects_traversal_absolute_and_git(self):
        for bad in ("../outside/secret.txt", "/etc/passwd", "clean_app/../../outside/secret.txt", "~/x",
                    "clean_app/.git/config", "a\\b", "a\x00b"):
            with self.assertRaises(WorkspaceError, msg=bad):
                self.ws.read_text(bad)

    def test_symlinked_directory_cannot_escape(self):
        os.symlink(self.home.path("outside"), os.path.join(self.root, "escape"))
        with self.assertRaises(WorkspaceError):
            self.ws.read_text("escape/secret.txt")
        with self.assertRaises(WorkspaceError):
            self.ws.apply([{"path": "escape/new.txt", "action": "create", "base_sha256": None, "content": "x"}])
        self.assertFalse(os.path.exists(self.home.path("outside", "new.txt")))

    def test_symlinked_file_is_not_read_or_replaced(self):
        os.symlink(self.home.path("outside", "secret.txt"), os.path.join(self.root, "clean_app", "link.txt"))
        with self.assertRaises(WorkspaceError):
            self.ws.read_text("clean_app/link.txt")
        self.assertNotIn("clean_app/link.txt", self.ws.walk("clean_app"))

    def test_apply_checks_base_hash_and_creation_conflicts(self):
        path = "clean_app/clean_app/modules.txt"
        with self.assertRaises(WorkspaceError):
            self.ws.apply([{"path": path, "action": "modify", "base_sha256": "0" * 64, "content": "x"}])
        with self.assertRaises(WorkspaceError):
            self.ws.apply([{"path": path, "action": "create", "base_sha256": None, "content": "x"}])
        written = self.ws.apply([{"path": "clean_app/new_dir/file.py", "action": "create", "base_sha256": None,
                                  "content": "x = 1\n"}])
        self.assertEqual(written[0]["action"], "create")
        self.assertEqual(self.ws.read_text("clean_app/new_dir/file.py"), "x = 1\n")

    def test_multi_file_apply_rolls_back_on_failure(self):
        a, c = "clean_app/clean_app/modules.txt", "clean_app/clean_app/patches.txt"
        original_a, original_c = self.ws.read_text(a), self.ws.read_text(c)
        files = [{"path": a, "action": "modify", "base_sha256": self.ws.sha256(a), "content": "Changed\n"},
                 {"path": "clean_app/created.py", "action": "create", "base_sha256": None, "content": "x = 1\n"},
                 {"path": c, "action": "modify", "base_sha256": self.ws.sha256(c), "content": "changed\n"}]
        real_replace = os.replace
        calls = []

        def failing_replace(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2:  # ikinci devreye alma (patches.txt) başarısız
                raise OSError(28, "No space left on device")
            return real_replace(*args, **kwargs)

        with mock.patch.object(os, "replace", failing_replace):
            with self.assertRaises(OSError):
                self.ws.apply(files)
        self.assertEqual(self.ws.read_text(a), original_a)
        self.assertEqual(self.ws.read_text(c), original_c)
        self.assertFalse(self.ws.exists("clean_app/created.py"))
        leftovers = [n for n in os.listdir(os.path.join(self.root, "clean_app/clean_app")) if n.startswith(".press-ai-")]
        self.assertEqual(leftovers, [])

    def test_failed_rollback_is_reported_as_partial(self):  # R3
        a, c = "clean_app/clean_app/modules.txt", "clean_app/clean_app/patches.txt"
        files = [{"path": a, "action": "modify", "base_sha256": self.ws.sha256(a), "content": "Changed\n"},
                 {"path": c, "action": "modify", "base_sha256": self.ws.sha256(c), "content": "changed\n"}]
        real_replace = os.replace
        calls = []

        def flaky_replace(*args, **kwargs):
            calls.append(args)
            if len(calls) >= 2:  # ikinci devreye alma ve geri alma başarısız
                raise OSError(5, "I/O error")
            return real_replace(*args, **kwargs)

        with mock.patch.object(os, "replace", flaky_replace):
            with self.assertRaises(WorkspaceError) as caught:
                self.ws.apply(files)
        self.assertEqual(caught.exception.code, "failed_partial")
        self.assertEqual([x["path"] for x in caught.exception.details["not_restored"]], [a])

    def test_git_is_blocked_case_insensitively(self):
        for bad in ("clean_app/.GIT/config", "clean_app/.Git/HEAD"):
            with self.assertRaises(WorkspaceError, msg=bad):
                self.ws.read_text(bad)

    def test_writes_disabled(self):
        ws = Workspace(self.root, allow_writes=False)
        with self.assertRaises(WorkspaceError) as caught:
            ws.apply([{"path": "clean_app/x.py", "action": "create", "base_sha256": None, "content": ""}])
        self.assertEqual(caught.exception.code, "writes_disabled")


class StaticChecks(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.ws = Workspace(self.home.workspace())

    def tearDown(self):
        self.home.cleanup()

    def rules(self, result):
        return {(f["rule"], f["severity"]) for f in result["findings"]}

    def test_inspect_reads_structure_without_executing(self):
        info = app_static.inspect(self.ws, "school_ext")
        self.assertEqual(info["app"], "school_ext")
        names = {d["name"] for d in info["doctypes"]}
        self.assertEqual(names, {"Student Record", "Student Subject", "Guardian Note"})
        record = [d for d in info["doctypes"] if d["name"] == "Student Record"][0]
        self.assertEqual({c["options"] for c in record["child_tables"]}, {"Student Subject", "Guardian Note"})
        self.assertEqual(info["hooks"]["required_apps"], ["erpnext"])
        self.assertEqual(info["pyproject"]["frappe_dependencies"]["frappe"], ">=15.0.0,<16.0.0")
        self.assertEqual([p["section"] for p in info["patches"]], ["pre_model_sync", "post_model_sync"])

    def test_check_finds_the_planted_problems(self):
        result = app_static.check(self.ws, "school_ext", "v15")
        rules = self.rules(result)
        expected = {("EXT001", "warning"), ("SEC001", "warning"), ("SEC002", "error"), ("SEC003", "error"),
                    ("SEC004", "info"), ("HOOK001", "error"), ("PERF001", "warning"), ("EXT002", "warning"),
                    ("EXT003", "info"), ("MIG003", "error"), ("MIG004", "warning"), ("FIX001", "warning"),
                    ("DOC003", "error"), ("DOC004", "error"), ("DOC006", "error"), ("DOC008", "warning"),
                    ("TST001", "warning")}
        self.assertTrue(expected <= rules, sorted(expected - rules))
        # Filtreli Property Setter fixture'ı uyarı üretmez; yalnız filtresiz Custom Field üretir.
        self.assertEqual(len([f for f in result["findings"] if f["rule"] == "FIX001"]), 1)
        # İki monkey patch ataması da (frappe.whitelist, erpnext utils) ayrı satırda raporlanır.
        self.assertEqual(len([f for f in result["findings"] if f["rule"] == "EXT001"]), 2)

    def test_version_rules_need_a_target(self):
        unknown = app_static.check(self.ws, "school_ext", None)
        self.assertEqual({r["result"] for r in unknown["version_rules"] if r["rule"] == "VER001"}, {"unknown"})
        v15 = app_static.check(self.ws, "school_ext", "v15")
        self.assertEqual([r["result"] for r in v15["version_rules"] if r["rule"] == "VER001"], ["error"])
        v16 = app_static.check(self.ws, "school_ext", "v16")
        self.assertEqual([r["result"] for r in v16["version_rules"] if r["rule"] == "VER001"], ["ok"])
        self.assertIn(("VER004", "error"), self.rules(v16))  # pyproject frappe <16 hedefi dışlar

    def test_clean_app_has_no_errors(self):
        result = app_static.check(self.ws, "clean_app", "v15")
        self.assertEqual([f for f in result["findings"] if f["severity"] == "error"], [])


class AppChangeFlow(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.root = self.home.workspace()
        _, self.config = make_config(self.home, workspace=self.root, allow_writes=True)
        self.ctx = Context(self.config, clock=Clock())
        self.tools = Toolbox(self.ctx)

    def tearDown(self):
        self.home.cleanup()

    def propose(self, app_path, change):
        return self.tools.call("app_propose_change", {"app_path": app_path, "change": change})

    def apply(self, proposal):
        approve(self.ctx, proposal["proposal_id"])
        return self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})

    def test_doctype_with_child_table_round_trip(self):
        doctype = self.propose("clean_app", {"kind": "new_doctype", "module": "Clean App", "doctype": "Lesson Plan",
                                             "fields": [{"fieldname": "title", "fieldtype": "Data", "label": "Title",
                                                         "reqd": True}],
                                             "permissions": [{"role": "System Manager", "read": True, "write": True,
                                                              "create": True}], "target_frappe": "v15"})
        self.assertEqual(doctype["state"], "pending")
        self.assertFalse(os.path.exists(os.path.join(self.root, "clean_app/clean_app/clean_app/doctype/lesson_plan")))
        self.assertEqual(self.apply(doctype)["state"], "succeeded")
        child = self.propose("clean_app", {"kind": "add_child_table", "module": "Clean App",
                                           "parent_doctype": "Lesson Plan", "child_doctype": "Lesson Step",
                                           "table_fieldname": "steps", "label": "Steps",
                                           "fields": [{"fieldname": "step", "fieldtype": "Data", "label": "Step"}]})
        self.assertIn("modify", {f["action"] for f in child["preview"]["files"]})
        self.assertEqual(self.apply(child)["state"], "succeeded")
        ws = Workspace(self.root)
        parent = json.loads(ws.read_text("clean_app/clean_app/clean_app/doctype/lesson_plan/lesson_plan.json"))
        self.assertEqual(parent["field_order"], ["title", "steps"])
        child_meta = json.loads(ws.read_text("clean_app/clean_app/clean_app/doctype/lesson_step/lesson_step.json"))
        self.assertEqual(child_meta["istable"], 1)
        self.assertEqual(child_meta["permissions"], [])
        test_file = ws.read_text("clean_app/clean_app/clean_app/doctype/lesson_plan/test_lesson_plan.py")
        self.assertIn("FrappeTestCase", test_file)
        result = app_static.check(ws, "clean_app", "v15")
        self.assertEqual([f for f in result["findings"] if f["severity"] == "error"], [])

    def test_hooks_are_appended_or_left_for_manual_merge(self):
        event = self.propose("clean_app", {"kind": "add_doc_event", "doctype": "Course Plan", "event": "validate",
                                           "handler": "clean_app.events.course_plan.validate"})
        self.assertEqual(event["preview"]["manual_merge"], [])
        self.apply(event)
        hooks = app_static.parse_hooks(Workspace(self.root).read_text("clean_app/clean_app/hooks.py"))["values"]
        self.assertEqual(hooks["doc_events"], {"Course Plan": {"validate": "clean_app.events.course_plan.validate"}})
        ast.parse(Workspace(self.root).read_text("clean_app/clean_app/events/course_plan.py"))
        second = self.propose("clean_app", {"kind": "add_doc_event", "doctype": "Course Plan", "event": "on_update",
                                            "handler": "clean_app.events.course_plan.on_update"})
        self.assertEqual(len(second["preview"]["manual_merge"]), 1)
        self.assertNotIn("clean_app/clean_app/hooks.py", [f["path"] for f in second["preview"]["files"]])

    def test_handler_must_live_in_a_module(self):
        with self.assertRaises(ValidationError):  # clean_app.validate → paketin yanına clean_app.py üretirdi
            self.propose("clean_app", {"kind": "add_doc_event", "doctype": "Course Plan", "event": "validate",
                                       "handler": "clean_app.validate"})

    def test_extend_is_v16_only_and_override_calls_super(self):
        with self.assertRaises(ValidationError):
            self.propose("clean_app", {"kind": "extend_doctype_class", "doctype": "Sales Invoice",
                                       "base_class": "erpnext.accounts.doctype.sales_invoice.sales_invoice.SalesInvoice",
                                       "mode": "extend", "target_frappe": "v15"})
        override = self.propose("clean_app", {"kind": "extend_doctype_class", "doctype": "Sales Invoice",
                                              "base_class": "erpnext.accounts.doctype.sales_invoice.sales_invoice."
                                                            "SalesInvoice", "mode": "override",
                                              "target_frappe": "v15"})
        body = [f for f in self.ctx.store.load(override["proposal_id"])["request"]["files"]
                if f["path"].endswith("sales_invoice.py")][0]["content"]
        self.assertIn("super().validate()", body)

    def test_patch_goes_into_the_requested_section(self):
        proposal = self.propose("clean_app", {"kind": "add_patch", "patch_name": "backfill_titles",
                                              "description": "Backfill titles", "section": "pre_model_sync"})
        self.apply(proposal)
        text = Workspace(self.root).read_text("clean_app/clean_app/patches.txt")
        pre, post = text.split("[post_model_sync]")
        self.assertIn("clean_app.patches.backfill_titles", pre)
        self.assertNotIn("clean_app.patches.backfill_titles", post)

    def test_new_app_requires_a_license_choice(self):
        base = {"kind": "new_app", "app_name": "kids_club", "app_title": "Kids Club", "publisher": "Example",
                "email": "dev@example.test", "description": "Example", "target_frappe": "v16"}
        with self.assertRaises(ValidationError):
            self.propose("kids_club", base)
        proposal = self.propose("kids_club", dict(base, license="MIT"))
        paths = {f["path"] for f in proposal["preview"]["files"]}
        self.assertIn("kids_club/kids_club/hooks.py", paths)
        record = self.ctx.store.load(proposal["proposal_id"])
        pyproject = [f for f in record["request"]["files"] if f["path"] == "kids_club/pyproject.toml"][0]["content"]
        self.assertIn('requires-python = ">=3.14"', pyproject)

    def test_apply_refuses_changed_files_without_consuming_approval(self):
        proposal = self.propose("clean_app", {"kind": "add_patch", "patch_name": "noop_patch",
                                              "description": "No-op", "section": "post_model_sync"})
        approve(self.ctx, proposal["proposal_id"])
        with open(os.path.join(self.root, "clean_app/clean_app/patches.txt"), "a") as handle:
            handle.write("clean_app.patches.someone_else\n")
        with self.assertRaises(WorkspaceError) as caught:
            self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(caught.exception.code, "conflict")
        self.assertEqual(self.ctx.store.status(proposal["proposal_id"])["state"], "approved")

    def test_apply_without_approval_or_with_writes_disabled(self):
        proposal = self.propose("clean_app", {"kind": "add_patch", "patch_name": "other_patch",
                                              "description": "Other", "section": "post_model_sync"})
        with self.assertRaises(ApprovalError):
            self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})
        approve(self.ctx, proposal["proposal_id"])
        _, readonly = make_config(self.home, workspace=self.root, allow_writes=False)
        with self.assertRaises(WorkspaceError) as caught:
            Toolbox(Context(readonly, clock=Clock())).call("app_apply", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(caught.exception.code, "writes_disabled")

    def test_generated_files_cannot_be_injected(self):
        base = {"kind": "new_app", "app_name": "kids_club", "app_title": "Kids Club", "email": "dev@example.test",
                "license": "MIT", "target_frappe": "v15", "description": "ok"}
        for publisher in ('x"\nimport os\n#', "a\\b", "line\nbreak"):
            with self.assertRaises(ValidationError):
                self.propose("kids_club", dict(base, publisher=publisher))
        with self.assertRaises(ValidationError):
            self.propose("kids_club", dict(base, publisher="Example", email='a"@b.co'))
        proposal = self.propose("kids_club", dict(base, publisher="O'Neil & Co"))
        files = {f["path"]: f["content"] for f in self.ctx.store.load(proposal["proposal_id"])["request"]["files"]}
        hooks = app_static.parse_hooks(files["kids_club/kids_club/hooks.py"])["values"]
        self.assertEqual(hooks["app_publisher"], "O'Neil & Co")

    def test_paths_outside_workspace_are_refused_at_proposal_time(self):
        for app_path in ("../evil", "clean_app/../../evil", "/tmp/evil"):
            with self.assertRaises((WorkspaceError, ValidationError)):
                self.propose(app_path, {"kind": "new_app", "app_name": "evil", "app_title": "Evil",
                                        "publisher": "x", "email": "dev@example.test", "description": "x",
                                        "license": "MIT", "target_frappe": "v15"})

    def test_existing_test_file_is_not_overwritten(self):
        with self.assertRaises(WorkspaceError):
            self.propose("clean_app", {"kind": "add_test", "doctype": "Course Plan", "target_frappe": "v15"})

    def test_official_parent_cannot_get_a_child_table_by_json_edit(self):
        with self.assertRaises(ValidationError):
            self.propose("clean_app", {"kind": "add_child_table", "module": "Clean App", "parent_doctype": "Sales Invoice",
                                       "child_doctype": "Invoice Note", "table_fieldname": "notes", "label": "Notes",
                                       "fields": [{"fieldname": "note", "fieldtype": "Data", "label": "Note"}]})


class WriteFileFlow(unittest.TestCase):
    """Gerçek iş mantığı: tek dosya, önizleme/diff/hash → insan onayı → atomik yazım. Kod çalıştırılmaz."""

    LOGIC = ("import frappe\nfrom frappe import _\n\n\ndef validate(doc, method=None):\n"
             "\tif doc.title and len(doc.title) > 140:\n\t\tfrappe.throw(_(\"Title is too long\"))\n")

    def setUp(self):
        self.home = TempHome()
        self.root = self.home.workspace()
        _, self.config = make_config(self.home, workspace=self.root, allow_writes=True)
        self.clock = Clock()
        self.ctx = Context(self.config, clock=self.clock)
        self.tools = Toolbox(self.ctx)

    def tearDown(self):
        self.home.cleanup()

    def propose(self, path, content, app_path="clean_app", **extra):
        change = dict({"kind": "write_file", "path": path, "content": content, "purpose": "Course plan rules"}, **extra)
        return self.tools.call("app_propose_change", {"app_path": app_path, "change": change})

    def test_new_file_with_real_logic_round_trip(self):
        proposal = self.propose("clean_app/events/course_plan.py", self.LOGIC, expected_sha256=None)
        self.assertEqual(proposal["operation"], "app_file.write")
        self.assertIn("+\t\tfrappe.throw", proposal["preview"]["diff"])
        self.assertIn("never runs or imports", " ".join(proposal["preview"]["notes"]))
        approve(self.ctx, proposal["proposal_id"])
        self.assertEqual(self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})["state"], "succeeded")
        self.assertEqual(Workspace(self.root).read_text("clean_app/clean_app/events/course_plan.py"), self.LOGIC)
        with self.assertRaises(ApprovalError):  # tek kullanım
            self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})

    def test_update_requires_unchanged_base(self):
        path = "clean_app/clean_app/clean_app/doctype/course_plan/course_plan.py"
        ws = Workspace(self.root)
        current = ws.sha256(path)
        with self.assertRaises(WorkspaceError):
            self.propose("clean_app/clean_app/doctype/course_plan/course_plan.py", self.LOGIC, expected_sha256="0" * 64)
        updated = ws.read_text(path).replace("\tpass\n", "\tdef validate(self):\n\t\tself.title = (self.title or '').strip()\n")
        proposal = self.propose("clean_app/clean_app/doctype/course_plan/course_plan.py", updated,
                                expected_sha256=current)
        approve(self.ctx, proposal["proposal_id"])
        with open(os.path.join(self.root, path), "a") as handle:
            handle.write("# edited after the proposal\n")
        with self.assertRaises(WorkspaceError) as caught:
            self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(caught.exception.code, "conflict")

    def test_core_change_warns_first_then_needs_explicit_repeat_and_core_approval(self):
        from press_ai.cli import core_banner
        rel, body = "erpnext/accounts/utils.py", "def get_balance_on(account=None):\n\treturn 1\n"
        base = self.read(rel, app_path="erpnext")[rel]["sha256"]  # core okunabilir
        first = self.propose(rel, body, app_path="erpnext", expected_sha256=base)
        self.assertEqual(first["state"], "core_warning")
        self.assertIsNone(first["proposal_id"])
        self.assertEqual(first["core"]["apps"], ["erpnext"])
        self.assertEqual(first["core"]["files"], ["erpnext/erpnext/accounts/utils.py"])
        self.assertIn("refused by default", first["warning"])
        self.assertIn("+\treturn 1", first["preview"]["diff"])
        self.assertEqual(self.ctx.store.list(), [])  # uyarı öneri değildir
        # Başka bir değişiklik kendi uyarısını alır; ilk uyarıyı tüketmez.
        other = self.propose(rel, body.replace("1", "2"), app_path="erpnext", expected_sha256=base)
        self.assertEqual(other["state"], "core_warning")
        second = self.propose(rel, body, app_path="erpnext", expected_sha256=base)  # kullanıcı aynısını açıkça yineler
        self.assertEqual(second["state"], "pending")
        self.assertEqual(second["approval_level"], "double")
        record = self.ctx.store.load(second["proposal_id"])
        self.assertEqual(record["confirm_phrase"], "CORE erpnext")
        banner = "\n".join(core_banner(record))
        self.assertIn("ORIGINAL CORE CHANGE", banner)
        self.assertIn("core file : erpnext/erpnext/accounts/utils.py", banner)
        # Uyarı tek kullanımlıktır: bir sonraki aynı istek yeniden uyarı alır.
        self.assertEqual(self.propose(rel, body, app_path="erpnext", expected_sha256=base)["state"], "core_warning")
        self.assertIn("return 0", Workspace(self.root).read_text("erpnext/erpnext/accounts/utils.py"))
        approve(self.ctx, second["proposal_id"])
        self.assertEqual(self.tools.call("app_apply", {"proposal_id": second["proposal_id"]})["state"], "succeeded")
        self.assertEqual(Workspace(self.root).read_text("erpnext/erpnext/accounts/utils.py"), body)
        # Tipli türler de aynı akıştan geçer.
        patch = {"kind": "add_patch", "patch_name": "core_fix", "description": "Core fix", "section": "post_model_sync"}
        call = lambda: self.tools.call("app_propose_change", {"app_path": "erpnext", "change": patch})  # noqa: E731
        self.assertEqual(call()["state"], "core_warning")
        self.assertEqual(self.ctx.store.load(call()["proposal_id"])["confirm_phrase"], "CORE erpnext")
        # Özel uygulamadan resmi uygulama dosyasına göreli yol yok (şema veya workspace sınırı reddeder).
        for path in ("../erpnext/erpnext/hooks.py", "clean_app/../../erpnext/erpnext/hooks.py"):
            with self.assertRaises((WorkspaceError, ValidationError), msg=path):
                self.propose(path, "app_name = 'x'\n")
        self.assertEqual(core_banner(self.ctx.store.load(
            self.propose("clean_app/events/plain.py", self.LOGIC, expected_sha256=None)["proposal_id"])), [])

    def test_official_checkout_with_another_directory_name_is_core(self):  # C2
        shutil.copytree(os.path.join(self.root, "erpnext"), os.path.join(self.root, "erpnext-15"))
        warned = self.propose("requirements.txt", "frappe\n", app_path="erpnext-15", expected_sha256=None)
        self.assertEqual((warned["state"], warned["core"]["apps"]), ("core_warning", ["erpnext"]))
        self.assertEqual(warned["core"]["files"], ["erpnext-15/requirements.txt"])

    def test_core_repeat_matches_typed_changes_that_write_timestamps(self):  # C3
        change = {"kind": "new_doctype", "module": "Accounts", "doctype": "Ledger Note", "target_frappe": "v15",
                  "fields": [{"fieldname": "note", "fieldtype": "Data", "label": "Note"}],
                  "permissions": [{"role": "Accounts Manager", "read": True}]}
        call = lambda: self.tools.call("app_propose_change", {"app_path": "erpnext", "change": change})  # noqa: E731
        with mock.patch("press_ai.app_changes._now", return_value="2026-10-08 12:00:00.000000"):
            self.assertEqual(call()["state"], "core_warning")
        with mock.patch("press_ai.app_changes._now", return_value="2026-10-08 12:00:07.000000"):
            repeated = call()  # kullanıcı birkaç saniye sonra aynısını yineler; zaman damgası farklı
        self.assertEqual((repeated["state"], repeated["approval_level"]), ("pending", "double"))

    def test_corrupt_core_warning_record_is_reissued_not_locked(self):  # C4
        rel, body = "erpnext/accounts/utils.py", "def get_balance_on(account=None):\n\treturn 3\n"
        base = self.read(rel, app_path="erpnext")[rel]["sha256"]
        call = lambda: self.propose(rel, body, app_path="erpnext", expected_sha256=base)  # noqa: E731
        self.assertEqual(call()["state"], "core_warning")
        folder = os.path.join(self.config.approval.state_dir, "core_warnings")
        [name] = os.listdir(folder)
        for garbage in (b"", b"[]", b"{not json"):
            with open(os.path.join(folder, name), "wb") as handle:
                handle.write(garbage)
            self.assertEqual(call()["state"], "core_warning", garbage)  # bozuk kayıt tekrar sayılmaz
        self.assertEqual(call()["state"], "pending")
        os.unlink(os.path.join(folder, name)) if os.path.exists(os.path.join(folder, name)) else None
        self.assertEqual(call()["state"], "core_warning")
        os.replace(os.path.join(folder, name), os.path.join(folder, name + ".real"))
        os.symlink(os.path.join(folder, name + ".real"), os.path.join(folder, name))
        with self.assertRaises(ApprovalError):  # sembolik bağ tahrifattır
            call()

    def test_unparsed_files_still_refuse_guest_permission_bypass_and_formatted_sql(self):  # C1
        head = ("import frappe\n\n\ndef kind(value):\n\tmatch value:\n\t\tcase 1:\n\t\t\treturn 'one'\n"
                "\treturn 'other'\n\n\n")
        guest = head + ("@frappe.whitelist(allow_guest=True)\ndef sign_up(email):\n"
                        "\tdoc = frappe.get_doc({'doctype': 'Lead', 'email_id': email})\n"
                        "\tdoc.insert(ignore_permissions=True)\n")
        concat = head + "def run(x):\n\treturn frappe.db.sql(\"select name from tabLead where email_id='\" + x + \"'\")\n"
        triple = head + "def run(x):\n\treturn frappe.db.sql(\"\"\"select name from tabLead where email_id='%s'\"\"\" % x)\n"
        for name, code in (("guest.py", guest), ("concat.py", concat), ("triple.py", triple)):
            with self.assertRaises(ValidationError, msg=name):  # 3.9'da metin taraması, 3.10+'da ağaç
                self.propose("clean_app/" + name, code, expected_sha256=None)
        safe = head + "def run(x):\n\treturn frappe.db.sql(\"\"\"select name from tabLead where email_id=%s\"\"\", (x,))\n"
        self.assertEqual(self.propose("clean_app/safe.py", safe, expected_sha256=None)["state"], "pending")

    def test_apply_refuses_core_paths_without_core_approval(self):
        proposal = self.propose("clean_app/vendor/frappe/x.py", "x = 1\n", expected_sha256=None)
        self.assertEqual(proposal["approval_level"], "single")
        approve(self.ctx, proposal["proposal_id"])
        os.makedirs(os.path.join(self.root, "clean_app/clean_app/vendor/frappe"))
        with open(os.path.join(self.root, "clean_app/clean_app/vendor/frappe/hooks.py"), "w") as handle:
            handle.write("app_name = 'frappe'\n")  # yol öneriden sonra resmi uygulama içine düştü
        with self.assertRaises(ApprovalError) as caught:
            self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(caught.exception.code, "core_not_approved")
        self.assertEqual(self.ctx.store.status(proposal["proposal_id"])["state"], "approved")  # tüketilmedi

    def test_denied_paths_and_types(self):
        for path in ("clean_app/.env", ".git/config", ".github/workflows/x.yml", "clean_app/site_config.json",
                     "clean_app/credentials.json", "clean_app/id_rsa", "clean_app/run.sh", "clean_app/lib.so",
                     "clean_app/keys/server.pem", "sites/common_site_config.json", "node_modules/x/index.js"):
            with self.assertRaises((WorkspaceError, ValidationError), msg=path):
                self.propose(path, "x = 1\n")

    def test_code_is_parsed_not_executed_and_unsafe_code_is_refused(self):
        marker = os.path.join(self.home.root, "executed.txt")
        payload = "open({!r}, 'w').write('ran')\n".format(marker)
        self.propose("clean_app/payload.py", payload)  # sözdizimi geçerli; yalnız öneri
        self.assertFalse(os.path.exists(marker))
        # clean_app requires-python >=3.10: sözdizimi hatası yalnız sunucu Python'u hedefe yetişiyorsa kesindir.
        if sys.version_info[:2] >= (3, 10):
            with self.assertRaises(ValidationError):
                self.propose("clean_app/broken.py", "def broken(:\n")
        else:
            broken = self.propose("clean_app/broken.py", "def broken(:\n")
            self.assertEqual(broken["approval_level"], "double")
            self.assertTrue(any("UNCHECKED" in n for n in broken["preview"]["notes"]))
        # Özel koddaki resmi modül yaması (EXT001) normal yetkili akıştadır: core uyarısı/onayı ve engel yok, risk notu var.
        patcher = self.propose("clean_app/patcher.py", "import frappe\nfrappe.get_doc = None\n")
        self.assertEqual((patcher["state"], patcher["approval_level"]), ("pending", "single"))
        self.assertNotIn("core", patcher["preview"])
        self.assertTrue(any(note.startswith("Warning EXT001 line 2") for note in patcher["preview"]["notes"]))
        with self.assertRaises(ValidationError):  # biçimlenmiş SQL güvenlik kuralıdır, reddedilir
            self.propose("clean_app/report.py", "import frappe\n\ndef run(x):\n\treturn frappe.db.sql(f'select {x}')\n")
        with self.assertRaises(ValidationError):
            self.propose("clean_app/data.json", "{not json")
        with self.assertRaises(ValidationError):
            self.propose("clean_app/big.py", "x = 1\n" * 40000)

    def test_approval_screen_shows_the_content_that_will_be_written(self):
        from press_ai.cli import _workspace_preview, safe_display
        proposal = self.propose("clean_app/events/rules.py", self.LOGIC + "# ‮gnp.exe\n")
        record = self.ctx.store.load(proposal["proposal_id"])
        lines = _workspace_preview(self.config, record)
        self.assertTrue(any("frappe.throw" in line for line in lines))
        self.assertIn("\\u202e", safe_display("\n".join(lines)))
        self.assertNotIn("‮", safe_display("\n".join(lines)))
        record["request"]["files"][0]["content"] += "import os\n"  # içerik özetinden sapma
        with self.assertRaises(KitError):
            _workspace_preview(self.config, record)

    def read(self, *paths, app_path="clean_app"):
        """Ajanın yolu: içerik ve sha256 aynı okumadan (app_inspect files)."""
        out = self.tools.call("app_inspect", {"app_path": app_path, "files": list(paths)})
        return {f["path"]: f for f in out["files"]["untrusted_data"]}

    def test_identical_content_is_no_op(self):
        current = self.read("clean_app/modules.txt")["clean_app/modules.txt"]
        with self.assertRaises(KitError) as caught:
            self.propose("clean_app/modules.txt", current["content"], expected_sha256=current["sha256"])
        self.assertEqual(caught.exception.code, "no_op")

    def test_existing_file_needs_the_hash_from_the_same_read(self):  # N1
        rel = "clean_app/clean_app/doctype/course_plan/course_plan.py"
        with self.assertRaises(WorkspaceError) as caught:
            self.propose(rel, self.LOGIC)
        self.assertEqual(caught.exception.code, "conflict")
        current = self.read(rel)[rel]
        self.assertEqual(current["sha256"], Workspace(self.root).sha256("clean_app/" + rel))
        proposal = self.propose(rel, current["content"] + "\n# reviewed change\n", expected_sha256=current["sha256"])
        self.assertEqual(proposal["state"], "pending")
        for secret in ("clean_app/.env", "clean_app/site_config.json", ".git/config"):
            with self.assertRaises((WorkspaceError, ValidationError), msg=secret):
                self.read(secret)

    def test_syntax_is_judged_against_the_app_python(self):  # N2, R5
        # clean_app requires-python >=3.10. Sunucu yetişiyorsa 3.10 dilbilgisi (feature_version) kesindir;
        # 3.9 sunucuda sonuç UNCHECKED olur: metin taraması koşar ve çift onay gerekir.
        match_code = "def kind(value):\n\tmatch value:\n\t\tcase 1:\n\t\t\treturn 'one'\n\treturn 'other'\n"
        proposal = self.propose("clean_app/kinds.py", match_code, expected_sha256=None)
        if sys.version_info[:2] >= (3, 10):
            self.assertEqual(proposal["approval_level"], "single")
        else:
            self.assertEqual(proposal["approval_level"], "double")
            record = self.ctx.store.load(proposal["proposal_id"])
            self.assertEqual(record["confirm_phrase"], "UNCHECKED clean_app/clean_app/kinds.py")
        type_alias = "type Score = int\n"  # 3.12+; >=3.10 bildiren uygulamada geçersiz
        if sys.version_info[:2] >= (3, 10):
            with self.assertRaises(ValidationError):
                self.propose("clean_app/aliases.py", type_alias, expected_sha256=None)
        else:
            self.assertEqual(self.propose("clean_app/aliases.py", type_alias, expected_sha256=None)["approval_level"],
                             "double")
        # Ayrıştırılamayan dosyada da metin taraması koşar: özel koddaki resmi modül yaması uyarıdır, core akışı değil.
        sneaky = "import frappe\n" + match_code + "frappe.get_doc = None\n"
        warned = self.propose("clean_app/sneaky.py", sneaky, expected_sha256=None)
        self.assertEqual(warned["state"], "pending")
        self.assertNotIn("core", warned["preview"])
        self.assertTrue(any(note.startswith("Warning EXT001") for note in warned["preview"]["notes"]))
        self.assertEqual(warned["approval_level"], "single" if sys.version_info[:2] >= (3, 10) else "double")
        sql = match_code + "def run(x):\n\treturn frappe.db.sql(f'select {x}')\n"
        with self.assertRaises(ValidationError):
            self.propose("clean_app/sql.py", "import frappe\n" + sql, expected_sha256=None)

    def test_inspect_and_review_see_exact_text_not_masks(self):  # R4
        rel = "clean_app/settings_api.py"
        secret_like = ("import frappe\n\n\ndef client():\n\tsettings = frappe.get_single('Clean Settings')\n"
                       "\tpassword = settings.get_password(\"api_key\")\n\treturn password\n")
        with open(os.path.join(self.root, "clean_app", rel), "w") as handle:
            handle.write(secret_like)
        current = self.read(rel)[rel]
        self.assertEqual(current["content"], secret_like)
        self.assertTrue(current["contains_secret_like_text"])
        with self.assertRaises(ValidationError):  # maskeli okuma geri yazılamaz
            self.propose(rel, secret_like.replace('get_password("api_key")', "[REDACTED]"),
                         expected_sha256=current["sha256"])
        updated = secret_like.replace("return password", "return password or None")
        proposal = self.propose(rel, updated, expected_sha256=current["sha256"])
        detail = self.tools.call("proposal_get", {"proposal_id": proposal["proposal_id"], "detail": True})
        self.assertIn('get_password("api_key")', "\n".join(detail["detail"]["untrusted_data"]["changes"]))

    def test_case_variants_cannot_bypass_name_rules(self):  # R6
        with self.assertRaises((WorkspaceError, ValidationError)):
            self.propose("ERPNEXT/accounts/utils.py", "def get_balance_on(account=None):\n\treturn 1\n",
                         app_path="ERPNEXT", expected_sha256=None)
        rel = "clean_app/clean_app/doctype/course_plan/course_plan.json"
        current = self.read(rel)[rel]
        meta = json.loads(current["content"])
        meta["permissions"].append({"role": "Guest", "read": 1})
        with self.assertRaises(WorkspaceError) as caught:
            self.propose("clean_app/clean_app/DocType/course_plan/course_plan.json", json.dumps(meta, indent=1),
                         expected_sha256=current["sha256"])
        self.assertEqual(caught.exception.code, "case_mismatch")
        with self.assertRaises(WorkspaceError):
            self.read("clean_app/Clean_App/doctype/course_plan/course_plan.json")

    def test_reviewer_sees_params_request_and_live_diff(self):  # N3
        rel = "clean_app/clean_app/doctype/course_plan/course_plan.py"
        current = self.read(rel)[rel]
        new = current["content"].replace("\tpass\n", "\tdef validate(self):\n\t\tpass\n")
        proposal = self.propose(rel, new, expected_sha256=current["sha256"])
        plain = self.tools.call("proposal_get", {"proposal_id": proposal["proposal_id"]})
        self.assertNotIn("detail", plain)
        full = self.tools.call("proposal_get", {"proposal_id": proposal["proposal_id"], "detail": True})
        detail = full["detail"]["untrusted_data"]
        self.assertEqual(detail["digest"][:12], proposal["digest12"])
        self.assertIsNone(detail["params"]["change"]["content"])  # içerik kayıtta bir kez: request.files
        self.assertIn("def validate", detail["request"]["files"][0]["content"])
        changes = "\n".join(detail["changes"])
        self.assertIn(current["sha256"][:12], changes)
        self.assertIn("+\tdef validate(self):", changes)
        self.assertIn("data_notice", full["detail"])

    def test_custom_doctype_permissions_are_allowed_and_noted(self):  # N4 yerine: özel geliştirme yetkili
        rel = "clean_app/clean_app/doctype/course_plan/course_plan.json"
        current = self.read(rel)[rel]
        meta = json.loads(current["content"])
        changed = dict(meta, permissions=meta["permissions"] + [{"role": "Guest", "read": 1}])
        proposal = self.propose(rel, json.dumps(changed, indent=1), expected_sha256=current["sha256"])
        self.assertEqual((proposal["state"], proposal["approval_level"]), ("pending", "single"))
        notes = " ".join(proposal["preview"]["notes"])
        self.assertIn("permission rows change", notes)
        self.assertIn("Guest means visitors who are not logged in", notes)
        approve(self.ctx, proposal["proposal_id"])
        self.assertEqual(self.tools.call("app_apply", {"proposal_id": proposal["proposal_id"]})["state"], "succeeded")
        written = json.loads(Workspace(self.root).read_text("clean_app/" + rel))
        self.assertIn({"role": "Guest", "read": 1}, written["permissions"])
        fixture = self.propose("clean_app/fixtures/custom_docperm.json", "[]", expected_sha256=None)
        self.assertEqual(fixture["state"], "pending")
        self.assertIn("Permission or role fixture", " ".join(fixture["preview"]["notes"]))
        new_doc = {"doctype": "DocType", "name": "Room", "module": "Clean App", "fields": [],
                   "permissions": [{"role": "System Manager", "read": 1}]}
        room = self.propose("clean_app/clean_app/doctype/room/room.json", json.dumps(new_doc), expected_sha256=None)
        self.assertEqual(room["state"], "pending")
        self.assertIn("roles before: none; after: System Manager", " ".join(room["preview"]["notes"]))

    def test_large_file_fits_the_record(self):  # N5
        content = "".join("def f{0}(doc):\n\treturn doc.get('field_{0}') or \"value\"\n\n".format(i)
                          for i in range(4000))
        content = content[: 190 * 1024]
        content = content[: content.rfind("\n\n") + 2]
        self.assertGreater(len(content.encode("utf-8")), 180 * 1024)
        proposal = self.propose("clean_app/generated_rules.py", content, expected_sha256=None)
        self.assertEqual(proposal["state"], "pending")

    def test_press_checkout_is_core_and_warning_expires(self):  # N6
        first = self.propose("press/api/x.py", "x = 1\n", app_path="press", expected_sha256=None)
        self.assertEqual((first["state"], first["core"]["apps"]), ("core_warning", ["press"]))
        self.clock.advance(seconds=self.config.approval.proposal_ttl + 1)  # süresi geçen uyarı tekrar sayılmaz
        late = self.propose("press/api/x.py", "x = 1\n", app_path="press", expected_sha256=None)
        self.assertEqual(late["state"], "core_warning")
        now = self.propose("press/api/x.py", "x = 1\n", app_path="press", expected_sha256=None)
        self.assertEqual(self.ctx.store.load(now["proposal_id"])["confirm_phrase"], "CORE press")

if __name__ == "__main__":
    unittest.main()
