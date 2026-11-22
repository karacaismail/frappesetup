"""Komut satırı. Her komut elle başlatılır. Zamanlanmış iş yoktur (Proje kaydı D-6).

Komutlar sonucu JSON olarak yazar. Her komutun bir HTTP ucu da vardır.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from identity_sync.app import App, build_app
from identity_sync.auth import build_verifier, reject_all
from identity_sync.config import ConfigError, load_settings
from identity_sync.httpjson import HttpError, TransportError
from identity_sync.pipeline import PreviewChanged, replay_report
from identity_sync.store import Busy

EXIT_OK, EXIT_FOUND, EXIT_ERROR = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="identity_sync", description="Keycloak user sync service.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Start the HTTP server.")
    reconcile = commands.add_parser(
        "reconcile",
        help="Compare Keycloak, Press and tenant users. Reports by default; exit 1 on differences.",
    )
    reconcile.add_argument("--dry-run", action="store_true", help="Only report. This is the default.")
    reconcile.add_argument("--execute", action="store_true", help="Run the previewed repair. Needs the two options below.")
    reconcile.add_argument("--preview-digest", help="The preview_digest of the report a human approved.")
    reconcile.add_argument("--approval-id", help="The id of that approval. It works once.")
    commands.add_parser("dead-letters", help="List failed events that wait in the queue.")
    replay = commands.add_parser("replay-dead-letters", help="Process the waiting failed events once.")
    replay.add_argument("--dry-run", action="store_true", help="Show the planned actions without running them.")
    replay.add_argument(
        "--include-unknown",
        action="store_true",
        help="Also re-run events whose outcome is unknown. Check the target first: this repeats the write.",
    )
    args_check = parser.parse_args

    def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
        args = args_check(argv)
        if args.command == "reconcile" and args.execute:
            if args.dry_run or not args.preview_digest or not args.approval_id:
                parser.error("reconcile --execute needs --preview-digest and --approval-id, and no --dry-run")
        return args

    parser.parse_args = parse  # type: ignore[method-assign]
    return parser


def _print(body: object) -> None:
    json.dump(body, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def configure_logging(stream: TextIO | None = None) -> None:
    """Servisin günlüğünü açar. İşlem günlüğü INFO düzeyindedir.

    Ayar yapılmazsa Python yalnız uyarıları yazar ve işlem günlüğü kaybolur.
    """
    logger = logging.getLogger("identity_sync")
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _serve(app: App) -> int:
    from identity_sync.server import make_server

    configure_logging()
    verifier = build_verifier(app.settings)
    if verifier is reject_all:
        print("warning: service tokens cannot be verified; protected endpoints reject every request", file=sys.stderr)
    httpd = make_server(app, verifier, host=app.settings.host, port=app.settings.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return EXIT_OK


def _reconcile(args: argparse.Namespace, app: App) -> int:
    if not args.execute:
        report = app.reconcile_plan().report()
        _print(report)
        return EXIT_FOUND if report["count"] else EXIT_OK
    # The repair follows the same rule as the HTTP endpoint: one approval, bound to one preview.
    if not app.store.claim_approval(args.approval_id, args.preview_digest, "reconcile"):
        print("approval was already used; get a new preview and a new approval", file=sys.stderr)
        return EXIT_ERROR
    try:
        result = app.reconcile_execute(args.preview_digest)
    except PreviewChanged:
        print("preview changed; nothing was written. Run reconcile again and get a new approval", file=sys.stderr)
        return EXIT_ERROR
    _print(result)
    return EXIT_OK if all(item["status"] == "done" for item in result["results"]) else EXIT_FOUND


def _run(args: argparse.Namespace, app: App) -> int:
    if args.command == "serve":
        return _serve(app)
    if args.command == "reconcile":
        return _reconcile(args, app)
    if args.command == "dead-letters":
        _print({"dead_letters": [letter.to_dict() for letter in app.store.dead_letters()]})
        return EXIT_OK
    results = app.processor.replay_dead_letters(dry_run=args.dry_run, include_unknown=args.include_unknown)
    _print({"results": replay_report(results)})
    wanted = "preview" if args.dry_run else "processed"
    return EXIT_OK if all(result.status == wanted for _id, result in results) else EXIT_FOUND


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings(os.environ if env is None else env)
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return EXIT_ERROR
    app = build_app(settings)
    try:
        return _run(args, app)
    except (HttpError, TransportError) as error:
        print(f"upstream error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except Busy:
        print("busy: another process is working on an event; try again", file=sys.stderr)
        return EXIT_ERROR
    finally:
        app.close()
