"""Uygulama geliştirme araçları: inceleme, kural denetimi, değişiklik önerisi ve onaylı uygulama."""
from __future__ import annotations

import copy
import difflib

from . import app_changes, app_static
from .errors import ApprovalError, KitError, WorkspaceError
from .proposals import approval_command
from .redaction import envelope_exact
from .util import canonical_json, sha256_hex

_KIND_TO_OPERATION = {kind: op for op, kind in app_changes.OPERATION_KINDS.items()}
CORE_WARNING = ("Original core code is refused by default. A bench update or a Press build from the app's own "
                "repository and branch replaces local core edits or conflicts with them; they are not in your custom "
                "app's history and every upgrade must re-apply them by hand. Prefer an extension from a custom app "
                "(hooks, doc_events, extend/override_doctype_class, patches, fixtures).")


def core_phrase(core: dict, unchecked: list) -> str:
    """İkinci onay ifadesi: değişen orijinal core uygulama(lar)ını açıkça adlandırır."""
    return " ".join(["CORE"] + (["UNCHECKED"] if unchecked else []) + [",".join(core["apps"])])


def app_inspect(ctx, args):
    ws = ctx.workspace()
    result = app_static.inspect(ws, args["app_path"])
    if args.get("files"):
        # İçerik ve sha256 aynı okumadan gelir: write_file'ın expected_sha256 değeri buradan alınır.
        # Desen maskelemesi yapılmaz: ajan bu içerikle tam dosya önerir; maskelenmiş metin geri yazılırsa dosya bozulur.
        files = []
        for rel in args["files"]:
            full = args["app_path"].rstrip("/") + "/" + rel
            app_changes.check_readable_path(full)
            app_changes.check_canonical_case(ws, full)
            data = ws.read_bytes(full, app_changes.WRITE_FILE_MAX)
            text = data.decode("utf-8", errors="replace")
            entry = {"path": rel, "sha256": sha256_hex(data), "bytes": len(data), "content": text}
            if ctx.redactor.looks_secret(text):
                entry["contains_secret_like_text"] = True
                entry["note"] = ("Text that looks like a credential is returned unmasked so edits stay exact; "
                                 "do not copy it elsewhere.")
            files.append(entry)
        result["files"] = envelope_exact(files, ctx.redactor)
    return result


def app_check(ctx, args):
    contract = ctx.contract
    return app_static.check(ctx.workspace(), args["app_path"], args.get("target_frappe"), contract.extension_points)


def render_changes(ws, record) -> list:
    """Onay ekranı ve inceleyici için: yazılacak içerik önerideki istekten okunur, diff güncel dosyaya karşı yeniden
    üretilir ve her dosyanın sha256'sı içerikle doğrulanır. `ws` None ise yeni içerik tümüyle gösterilir."""
    lines = []
    for item in record["request"]["files"]:
        if sha256_hex(item["content"].encode("utf-8")) != item["sha256"]:
            raise KitError("Proposal content does not match its file hash", code="state_tampered")
        lines.append("== {} {}  base {}  new {}".format(item["action"], item["path"],
                                                         (item.get("base_sha256") or "none")[:12], item["sha256"][:12]))
        current = ""
        if item["action"] == "modify":
            if ws is None:
                lines.append("(workspace not available here: full new content follows)")
            else:
                current = ws.read_text(item["path"])
                if sha256_hex(current.encode("utf-8")) != item.get("base_sha256"):
                    lines.append("(the file changed since the proposal; app_apply will refuse it)")
        lines.extend(difflib.unified_diff(current.splitlines(), item["content"].splitlines(),
                                          "a/" + item["path"] if current else "/dev/null", "b/" + item["path"],
                                          lineterm=""))
    return lines


def workspace_for(ctx_or_config, record):
    """Önerinin workspace'i bu yapılandırmadakiyle aynıysa onu döndürür, değilse None."""
    from .workspace import Workspace
    config = getattr(ctx_or_config, "config", ctx_or_config)
    if config.workspace and config.workspace.root == (record.get("authority") or {}).get("workspace_root"):
        return Workspace(config.workspace.root)
    return None


def app_propose_change(ctx, args):
    ws = ctx.workspace()
    plan = app_changes.build_plan(ws, args["app_path"], args["change"])
    operation = _KIND_TO_OPERATION[plan["kind"]]
    request = {"files": [{key: f[key] for key in ("path", "action", "base_sha256", "content", "sha256")}
                         for f in plan["files"]]}
    # İçerik kayıtta yalnız request.files içinde tutulur; diff onayda ve incelemede içerikten yeniden üretilir.
    stored_params = copy.deepcopy({"app_path": args["app_path"], "change": args["change"]})
    if plan["kind"] == "write_file":
        stored_params["change"]["content"] = None
        stored_params["change"]["content_sha256"] = sha256_hex(args["change"]["content"].encode("utf-8"))
    files = [{key: f[key] for key in ("path", "action", "base_sha256", "sha256")} for f in plan["files"]]
    core = plan["core"]
    if core:
        # Orijinal core varsayılan olarak reddedilir: ilk istek yalnız uyarı döner. Aynı istek (aynı argümanlar ve aynı
        # dosya tabanları) uyarı süresi içinde açıkça tekrarlanırsa öneri oluşur; onu insan CORE ifadesiyle onaylar.
        # Üretilen içerik özete girmez: tipli türler zaman damgası yazar; içerik öneri özetinde zaten bağlıdır.
        bases = [{key: f[key] for key in ("path", "action", "base_sha256")} for f in plan["files"]]
        request_digest = sha256_hex(canonical_json({"workspace_root": ws.root, "operation": operation,
                                                    "app_path": args["app_path"], "change": args["change"],
                                                    "files": bases}))
        warning = ctx.store.core_gate(request_digest, core)
        if warning is not None:
            return {"proposal_id": None, "state": "core_warning", "operation": operation, "core": core,
                    "warning": CORE_WARNING, "warning_expires_at": warning["expires_at"],
                    "preview": {"files": files, "diff": plan["diff"], "notes": plan["notes"]},
                    "next": "Nothing was proposed or written. Show this warning to the user. Only if the user "
                            "explicitly asks for this same change again, call app_propose_change again with exactly "
                            "the same arguments before warning_expires_at; the proposal then needs the human's core "
                            "approval in a separate terminal."}
    stored_preview = {"manual_merge": plan["manual_merge"], "human_commands": plan["human_commands"],
                      "notes": plan["notes"], "files": files}
    # Çift onay: core değişikliği (CORE ...) ya da ayrıştırılamayan Python (UNCHECKED ...); ifade nedeni adlandırır.
    if core:
        level, phrase = "double", core_phrase(core, plan["unchecked"])
        stored_preview["core"] = dict(core, warning=CORE_WARNING)
    elif plan["unchecked"]:
        level, phrase = "double", "UNCHECKED " + plan["unchecked"][0]
    else:
        level, phrase = "single", None
    stored_preview["unchecked"] = plan["unchecked"]
    record = ctx.store.create("workspace", operation, {"workspace_root": ws.root}, args["app_path"], stored_params,
                              request, stored_preview, level, phrase)
    result = {"proposal_id": record["id"], "state": "pending", "digest12": record["digest"][:12],
              "operation": operation, "expires_at": record["expires_at"], "approval_level": level,
              "preview": dict(stored_preview, diff=plan["diff"]),
              "human_approval_command": approval_command(record["id"]),
              "note": "Nothing was written. A human approves this exact plan in a separate terminal."}
    if not ws.allow_writes:
        result["writes_enabled"] = False
        result["note"] += " workspace.allow_writes is false, so app_apply will refuse until a human enables it."
    return result


def app_apply(ctx, args):
    ws = ctx.workspace()
    record = ctx.store.require_approved(args["proposal_id"], "workspace")
    if record["authority"].get("workspace_root") != ws.root:
        raise ApprovalError("Proposal was made for a different workspace root", code="authority_changed")
    files = record["request"]["files"]
    if not ws.allow_writes:
        raise WorkspaceError("workspace.allow_writes is false; a human must enable writes in the config",
                             code="writes_disabled")
    core = record["preview"].get("core") or {}
    core_approved = bool(core) and record["approval_level"] == "double" and \
        (record.get("confirm_phrase") or "").startswith("CORE ")
    for item in files:  # Önce doğrula: onay yalnız taban hâlâ aynıysa tüketilir.
        app = app_changes.check_mutation_path(ws, item["path"])
        if app and not (core_approved and item["path"] in core.get("files", [])):
            raise ApprovalError("{} is original core code ({}) but this proposal was not approved as a core change; "
                                "propose it again".format(item["path"], app), code="core_not_approved")
        if sha256_hex(item["content"].encode("utf-8")) != item["sha256"]:
            raise ApprovalError("Proposal content does not match its file hash", code="state_tampered")
        current = ws.sha256(item["path"])
        expected = None if item["action"] == "create" else item["base_sha256"]
        if current != expected:
            raise WorkspaceError("File changed since the proposal: " + item["path"], code="conflict",
                                 details={"path": item["path"]})
    ctx.store.consume(record["id"])
    try:
        written = ws.apply(files)
        outcome = {"state": "succeeded", "written": written, "human_commands": record["preview"]["human_commands"]}
    except WorkspaceError as error:
        if error.code == "failed_partial":
            outcome = {"state": "failed_partial", "error": str(error), "not_restored": error.details["not_restored"],
                       "meaning": "Some files could not be rolled back; inspect them (git status/diff) before any "
                                  "new proposal."}
        else:
            outcome = {"state": "failed", "error": str(error), "meaning": "Every changed file was rolled back."}
    except OSError as error:
        outcome = {"state": "failed", "error": "{}: {}".format(type(error).__name__, error.strerror or error),
                   "meaning": "Every changed file was rolled back."}
    ctx.store.record_outcome(record["id"], outcome)
    return dict(outcome, proposal_id=record["id"], operation=record["operation"])


def implemented_schemas() -> dict:
    schemas = {op: app_changes.KIND_SCHEMAS[kind] for op, kind in app_changes.OPERATION_KINDS.items()}
    schemas["app.inspect"] = INSPECT_SCHEMA
    schemas["app.check"] = CHECK_SCHEMA
    return schemas


APP_PATH = {"type": "string", "minLength": 1, "maxLength": 512, "pattern": r"[A-Za-z0-9_.][A-Za-z0-9_./-]*"}
INSPECT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["app_path"],
                  "properties": {"app_path": APP_PATH,
                                 "files": {"type": "array", "maxItems": 20,
                                           "items": {"type": "string", "minLength": 1, "maxLength": 300,
                                                     "pattern": r"[A-Za-z0-9_][A-Za-z0-9_./-]*"}}}}
CHECK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["app_path"],
                "properties": {"app_path": APP_PATH, "target_frappe": {"type": "string", "enum": ["v15", "v16"]}}}
