"""Prepare only this Compose project's development and test sites."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

BENCH = Path("/home/frappe/frappe-bench")


def configure() -> None:
    path = BENCH / "sites/common_site_config.json"
    config = json.loads(path.read_text()) if path.exists() else {}
    config.update(
        db_host="kiraci-db",
        redis_cache="redis://kiraci-redis:6379/0",
        redis_queue="redis://kiraci-redis:6379/1",
        redis_socketio="redis://kiraci-redis:6379/1",
        socketio_port=int(os.environ["KIRACI_SOCKET_PORT"]),
        webserver_port=int(os.environ["KIRACI_WEB_PORT"]),
        pause_scheduler=True,
        disable_scheduler=True,
        server_script_enabled=False,
    )
    # Never enable tests across all sites.
    config.pop("allow_tests", None)
    path.write_text(json.dumps(config, indent=2) + "\n")
    apps_path = BENCH / "sites/apps.txt"
    apps = apps_path.read_text().splitlines()
    apps_path.write_text("\n".join(dict.fromkeys([a for a in apps if a] + ["platform_core"])) + "\n")


def prepare(site: str, apps: list[str]) -> None:
    import frappe
    from frappe.commands.site import new_site

    configure()
    os.chdir(BENCH / "sites")
    path = Path(site) / "site_config.json"
    if not path.exists():
        # Run the actual new-site command without placing secrets in process arguments.
        new_site.main(
            [site, "--db-type", "mariadb", "--db-host", "kiraci-db",
             "--mariadb-user-host-login-scope", "%",
             "--db-root-password", os.environ["MARIADB_ROOT_PASSWORD"],
             "--admin-password", os.environ["ADMIN_PASSWORD"]],
            standalone_mode=False,
        )
        frappe.destroy()
    config = json.loads(path.read_text())
    config.update(
        allow_tests=site.startswith("test-"),
        developer_mode=True,
        pause_scheduler=True,
        disable_scheduler=True,
        mute_emails=True,
        host_name=f"http://{site}:{os.environ['KIRACI_WEB_PORT']}",
    )
    path.write_text(json.dumps(config, indent=2) + "\n")
    path.chmod(0o600)
    os.chdir(BENCH)
    for app in apps:
        subprocess.run(["bench", "--site", site, "install-app", app], check=True)
    print(f"Prepared {site}; allow_tests={site.startswith('test-')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site")
    parser.add_argument("--app", action="append", default=[])
    args = parser.parse_args()
    if args.site != "kiraci1.localhost" and not re.fullmatch(r"test-[a-z0-9-]+\.localhost", args.site):
        parser.error("Only kiraci1.localhost and test-*.localhost are allowed")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*", app) for app in args.app):
        parser.error("Invalid app name")
    prepare(args.site, args.app)


if __name__ == "__main__":
    main()
