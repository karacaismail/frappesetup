"""Verify Frappe config precedence inside a disposable bench container."""

import json
import subprocess
from pathlib import Path

SITES = Path("sites")
SITE_NAMES = ("g38-alpha.localhost", "g38-beta.localhost")


def bench(*args: str) -> str:
    return subprocess.check_output(["bench", *args], text=True)


def verify() -> None:
    for site in SITE_NAMES:
        site_dir = SITES / site
        site_dir.mkdir()
        (site_dir / "site_config.json").write_text(json.dumps({"db_name": site}))

    bench("version")
    for port in (2525, 2526):
        bench("set-config", "-gp", "mail_port", str(port))
        common = json.loads((SITES / "common_site_config.json").read_text())
        if common.get("mail_port") != port or "db_name" in common:
            raise AssertionError("Shared config must contain the mail port and no site database name")
        for site in SITE_NAMES:
            config = json.loads(bench("--site", site, "show-config", "--format", "json"))[site]
            if config.get("mail_port") != port or config.get("db_name") != site:
                raise AssertionError(f"{site}: unexpected effective configuration")
            local = json.loads((SITES / site / "site_config.json").read_text())
            if local != {"db_name": site}:
                raise AssertionError(f"{site}: shared update changed site configuration")
        print(f"Both existing sites: mail_port={port}; separate db_name values preserved")


if __name__ == "__main__":
    verify()
