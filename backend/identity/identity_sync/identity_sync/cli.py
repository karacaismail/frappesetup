"""Komut satırı. Her komut elle başlatılır. Zamanlanmış iş yoktur (Proje kaydı D-6).

Komutlar sonucu JSON olarak yazar. Her komutun bir HTTP ucu da vardır.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence

from identity_sync.app import App, build_app
from identity_sync.auth import build_verifier, reject_all
from identity_sync.config import ConfigError, load_settings
from identity_sync.httpjson import HttpError, TransportError

EXIT_OK, EXIT_FOUND, EXIT_ERROR = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="identity_sync", description="Keycloak user sync service.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Start the HTTP server.")
    commands.add_parser("reconcile", help="Compare Keycloak, Press and tenant users. Reports only; exit 1 on differences.")
    commands.add_parser("dead-letters", help="List failed events that wait in the queue.")
    replay = commands.add_parser("replay-dead-letters", help="Process the waiting failed events once.")
    replay.add_argument("--dry-run", action="store_true", help="Show the planned actions without running them.")
    return parser


def _print(body: object) -> None:
    json.dump(body, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _serve(app: App) -> int:
    from identity_sync.server import make_server

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


def _run(command: str, dry_run: bool, app: App) -> int:
    if command == "serve":
        return _serve(app)
    if command == "reconcile":
        differences = [difference.to_dict() for difference in app.reconcile()]
        _print({"count": len(differences), "differences": differences})
        return EXIT_FOUND if differences else EXIT_OK
    if command == "dead-letters":
        _print({"dead_letters": [letter.to_dict() for letter in app.store.dead_letters()]})
        return EXIT_OK
    results = app.processor.replay_dead_letters(dry_run=dry_run)
    _print({"results": [{"event_id": event_id, **result.to_dict()} for event_id, result in results]})
    wanted = "preview" if dry_run else "processed"
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
        return _run(args.command, getattr(args, "dry_run", False), app)
    except (HttpError, TransportError) as error:
        print(f"upstream error: {error}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        app.close()
