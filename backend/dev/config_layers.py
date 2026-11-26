"""Check the placement of known settings in a Frappe sites directory."""

import argparse
import json
import sys
from pathlib import Path

BENCH_KEYS = {
    "redis_cache",
    "redis_queue",
    "redis_socketio",
    "socketio_port",
    "webserver_port",
    "workers",
    "background_workers",
    "gunicorn_workers",
    "scheduler_tick_interval",
}
SITE_KEYS = {
    "allow_tests",
    "backup_encryption_key",
    "db_name",
    "db_password",
    "db_type",
    "db_user",
    "developer_mode",
    "encryption_key",
    "host_name",
    "keycloak_client_secret",
    "mute_emails",
    "plan_limit",
}


def check_file(path: Path, label: str, *, shared: bool) -> bool:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        print(f"{label}: cannot read a JSON object", file=sys.stderr)
        return False
    if not isinstance(config, dict):
        print(f"{label}: expected a JSON object", file=sys.stderr)
        return False

    valid = True
    for key in sorted(config):
        if key == "allow_cors":
            problem = "prohibited in both layers"
        elif shared and (key in SITE_KEYS or key.startswith("sk_")):
            problem = "belongs in site_config.json"
        elif not shared and (key in BENCH_KEYS or key.startswith("mail_")):
            problem = "belongs in common_site_config.json"
        else:
            continue
        print(f"{label}: {key} {problem}", file=sys.stderr)
        valid = False
    return valid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sites_dir", type=Path)
    root = parser.parse_args().sites_dir
    common = root / "common_site_config.json"
    results = [check_file(common, common.name, shared=True)]
    for path in sorted(root.glob("*/site_config.json")):
        results.append(check_file(path, path.relative_to(root).as_posix(), shared=False))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
