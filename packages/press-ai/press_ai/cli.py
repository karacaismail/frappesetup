"""Komut satırı: MCP sunucusu (serve), insan onayı (approve/reject/resolve) ve yerel denetimler."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

from .config import Config
from .contract import Contract
from .errors import KitError
from .proposals import ProposalStore
from .redaction import Redactor

COVERAGE_START = "<!-- press-ai:coverage:start -->"
COVERAGE_END = "<!-- press-ai:coverage:end -->"
_STATUS_TR = {"implemented": "uygulandı", "read_only": "salt okuma", "planned": "planlı", "unsupported": "desteklenmez",
              "not_applicable": "uygulanamaz", "unknown": "bilinmiyor"}
_FAMILY_TR = {"release": "App, Source, Release Group", "build_deploy": "Candidate, build, deploy",
              "bench_site": "Bench ve site", "jobs_diagnostics": "İşler ve teşhis", "backups": "Yedek",
              "infrastructure": "Sunucu ve altyapı", "access": "Erişim ve ayarlar", "app_dev": "Uygulama geliştirme"}


def _load_config(path):
    return Config.load(path) if path else Config.empty()


def _print(data) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def safe_display(text) -> str:
    """Onay ekranına basılan her metin: denetim (C0/C1) ve biçim (bidi, sıfır genişlik) karakterleri kaçışlanır;
    görünen metin ile yazılacak metin aynı okunur."""
    out = []
    for ch in str(text):
        if ch in "\n\t":
            out.append(ch)
        elif unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs") or ch in "  ":
            out.append("\\u{:04x}".format(ord(ch)))
        else:
            out.append(ch)
    return "".join(out)


def _workspace_preview(config, record) -> list:
    """Yazılacak içerik önerideki istekten okunur; diff güncel dosyaya karşı yeniden üretilir (inceleyiciyle aynı yol)."""
    from . import app_tools
    return app_tools.render_changes(app_tools.workspace_for(config, record), record)


def core_banner(record) -> list:
    """Orijinal core değişikliği onay ekranında diff'ten önce ayrıca ve açıkça gösterilir."""
    core = record["preview"].get("core") if record.get("kind") == "workspace" else None
    if not core:
        return []
    lines = ["!" * 72, "ORIGINAL CORE CHANGE: refused by default. Approve only if you explicitly want this exact change."]
    lines += ["core app  : " + app for app in core.get("apps", [])]
    lines += ["core file : " + path for path in core.get("files", [])]
    lines += [core.get("warning", ""), "!" * 72]
    return lines


def _require_tty() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise KitError("This command must be run by a human in an interactive terminal", code="tty_required")


def cmd_serve(args) -> int:
    from .mcp_stdio import Server
    from .tools import Context, Toolbox
    config = _load_config(args.config)
    Server(Toolbox(Context(config))).serve()
    return 0


def _store(args) -> ProposalStore:
    config = _load_config(args.config)
    return ProposalStore(config.approval, redactor=Redactor())


def cmd_approve(args) -> int:
    _require_tty()
    config = _load_config(args.config)
    store = ProposalStore(config.approval, redactor=Redactor())
    status = store.status(args.proposal_id)
    if status["state"] != "pending":
        raise KitError("Proposal is {}; only pending proposals can be approved".format(status["state"]),
                       code="not_pending")
    record = store.load(args.proposal_id)
    show = lambda text: print(safe_display(text))  # noqa: E731
    show("=" * 72)
    show("press-ai proposal {}  ({})".format(record["id"], record["kind"]))
    show("operation : {}".format(record["operation"]))
    show("target    : {}".format(record["target"]))
    show("authority : {}".format(json.dumps(record["authority"], ensure_ascii=False)))
    show("expires   : {}".format(record["expires_at"]))
    for line in core_banner(record):
        show(line)
    show("params    :")
    show(json.dumps(record["params"], ensure_ascii=False, indent=2))
    if record["kind"] == "workspace":
        show("files and changes (generated from the content that will be written):")
        for line in _workspace_preview(config, record):
            show(line)
        for merge in record["preview"].get("manual_merge", []):
            show("manual merge needed in {}: {}".format(merge["file"], merge["instruction"]))
        for note in record["preview"].get("notes", []):
            show("note: " + note)
    else:
        show("request (sent exactly once):")
        show(json.dumps(record["request"], ensure_ascii=False, indent=2))
        show("preview   :")
        show(json.dumps(record["preview"], ensure_ascii=False, indent=2))
    show("-" * 72)
    show(config.approval.summary()["limitation"])
    print("Approving runs this exact request once. It does not approve retries or other targets.")
    digest12 = record["digest"][:12]
    if input("Type APPROVE {} to approve: ".format(digest12)).strip() != "APPROVE " + digest12:
        print("Not approved.")
        return 1
    if record["approval_level"] == "double":
        phrase = record["confirm_phrase"]
        if input("Second confirmation, type {}: ".format(phrase)).strip() != phrase:
            print("Not approved.")
            return 1
    approval = store.write_approval(args.proposal_id, record)
    print("Approved until {}. The agent may now execute it once.".format(approval["expires_at"]))
    return 0


def cmd_reject(args) -> int:
    _require_tty()
    _store(args).write_rejection(args.proposal_id, args.reason or "")
    print("Rejected.")
    return 0


def cmd_resolve(args) -> int:
    _require_tty()
    outcome = _store(args).resolve_outcome(args.proposal_id, args.note)
    print("Marked as resolved by a human: {}".format(outcome.get("state")))
    return 0


def cmd_proposals(args) -> int:
    _print(_store(args).list())
    return 0


def _guide_ids(path):
    if not path:
        return None
    with open(path, "rb") as handle:
        return [s["id"] for s in json.loads(handle.read())["steps"]]


def _sitemap_ids(path):
    if not path:
        return None
    with open(path, "rb") as handle:
        return {n.get("id") for n in json.loads(handle.read())["nodes"]}


def cmd_check_contract(args) -> int:
    from .press_ops import MUTATIONS
    from .tools import implemented_schemas
    config = _load_config(args.config)
    contract = Contract(args.contracts or config.contracts_dir)
    errors = contract.validate(implemented_schemas(), _guide_ids(args.guide), _sitemap_ids(args.sitemap),
                               {op_id: m.preconditions for op_id, m in MUTATIONS.items()})
    _print({"errors": errors, "error_count": len(errors), "coverage": contract.coverage(),
            "checked": {"guide_order": bool(args.guide), "sitemap_ids": bool(args.sitemap)}})
    return 1 if errors else 0


def cmd_schemas(args) -> int:
    from .tools import implemented_schemas
    _print(implemented_schemas())
    return 0


def coverage_markdown(contract: Contract) -> str:
    cov = contract.coverage()
    statuses = ["implemented", "read_only", "planned", "unsupported", "not_applicable", "unknown"]
    lines = [COVERAGE_START, "",
             "| Aile | " + " | ".join(_STATUS_TR[s] for s in statuses) + " | Toplam |",
             "| --- | " + " | ".join("---" for _ in statuses) + " | --- |"]
    totals = {s: 0 for s in statuses}
    for family, row in cov["operations_by_family"].items():
        lines.append("| {} | {} | {} |".format(_FAMILY_TR.get(family, family), " | ".join(str(row.get(s, 0))
                                                                                      for s in statuses),
                                               sum(row.get(s, 0) for s in statuses)))
        for s in statuses:
            totals[s] += row.get(s, 0)
    lines.append("| **Toplam** | {} | **{}** |".format(" | ".join(str(totals[s]) for s in statuses),
                                                        sum(totals.values())))
    steps = cov["guide_steps_by_weakest_status"]
    lines += ["",
              "Kılavuzun {} adımı, adımdaki en zayıf işlemin statüsüne göre: {}. En az bir işlemi uygulanmış adım: {}. "
              "Canlı Press doğrulaması: `not_run`.".format(
                  cov["guide_steps_total"],
                  ", ".join("{} {}".format(steps.get(s, 0), _STATUS_TR[s]) for s in statuses if steps.get(s)),
                  cov["guide_steps_with_an_implemented_operation"]),
              "", COVERAGE_END]
    return "\n".join(lines)


def cmd_coverage_markdown(args) -> int:
    config = _load_config(args.config)
    block = coverage_markdown(Contract(config.contracts_dir))
    if not args.check:
        sys.stdout.write(block + "\n")
        return 0
    with open(args.check, encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(re.escape(COVERAGE_START) + r".*?" + re.escape(COVERAGE_END), text, re.S)
    if not match:
        print("coverage markers not found in " + args.check)
        return 1
    if match.group(0) != block:
        print("coverage block in {} is out of date; regenerate it with coverage-markdown".format(args.check))
        return 1
    print("coverage block is current")
    return 0


def cmd_call(args) -> int:
    from .tools import Context, Toolbox
    config = _load_config(args.config)
    try:
        arguments = json.loads(args.args or "{}")
    except ValueError:
        raise KitError("--args must be JSON", code="invalid_params") from None
    _print(Toolbox(Context(config)).call(args.tool, arguments))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="press-ai", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, fn, help_text, config=True):
        p = sub.add_parser(name, help=help_text)
        if config:
            p.add_argument("--config", help="path to the press-ai JSON config")
        p.set_defaults(fn=fn)
        return p

    add("serve", cmd_serve, "run the MCP server on stdio")
    p = add("approve", cmd_approve, "human: approve one pending proposal (interactive terminal)")
    p.add_argument("proposal_id")
    p = add("reject", cmd_reject, "human: reject one proposal (interactive terminal)")
    p.add_argument("proposal_id")
    p.add_argument("--reason")
    p = add("resolve", cmd_resolve, "human: mark an unknown outcome as inspected (interactive terminal)")
    p.add_argument("proposal_id")
    p.add_argument("--note", required=True)
    add("proposals", cmd_proposals, "list proposals and their state")
    p = add("check-contract", cmd_check_contract, "validate the operation contract against the runtime")
    p.add_argument("--contracts", help="contracts directory (default: package contracts/)")
    p.add_argument("--guide", help="pressguide src/data/guide.json for step order checks")
    p.add_argument("--sitemap", help="pressguide src/data/press-sitemap.json for UI node id checks")
    add("schemas", cmd_schemas, "print the runtime params schemas of implemented operations", config=False)
    p = add("coverage-markdown", cmd_coverage_markdown, "print or check the documentation coverage block")
    p.add_argument("--check", help="markdown file whose coverage block must match")
    p = add("call", cmd_call, "call one tool locally through the same dispatcher (no approval bypass)")
    p.add_argument("tool")
    p.add_argument("--args", help="tool arguments as JSON")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KitError as error:
        sys.stderr.write(json.dumps(error.as_dict(), ensure_ascii=False) + "\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted; nothing was approved.\n")
        return 130
    except EOFError:
        sys.stderr.write("No input; nothing was approved.\n")
        return 1
    except OSError as error:
        sys.stderr.write("press-ai: {}: {}\n".format(type(error).__name__, os.strerror(error.errno)
                                                      if error.errno else error))
        return 2
