#!/usr/bin/env python3
"""Production setting lists and their check on the server (blocker E-4).

Each secret file on the server has one list in backend/deploy/settings/<name>.production.env.example.
A list line is KEY=<form of the value>. A comment line just above a key may carry a tag:
  # [isteğe bağlı] ...   the key may be absent (optional)
  # [sabit] ...          the server value must equal the listed value (fixed)
remote/apply runs "check-files" before it changes anything and "check-sites" before it stops the
running release. The check prints file paths and key names, never a value.
Design: backend/docs/dagitim/ortamlar.md. Python 3.9+, standard library only.

Usage:
  settings.py check-files <env> <lists folder> --etc <folder> --press 0|1 --offsite 0|1
  settings.py check-sites <lists folder> <probe json> [--first-install 0|1] <site>...
"""

import argparse
import json
import re
import stat
import sys
from collections import namedtuple
from pathlib import Path

Target = namedtuple("Target", "list_file kind path when")
Entry = namedtuple("Entry", "key value optional fixed")

# kind "env": a file read by docker compose (env_file). kind "site": site_config.json of a site,
# merged with common_site_config.json. when: "always", "press" (the release has a Press image) or
# "offsite" (environment rule ATONOTA_REQUIRE_OFFSITE_BACKUP=1; a present file is checked anyway).
LISTS = {
    "tenant": Target("tenant.production.env.example", "env", "{etc}/{env}/tenant.env", "always"),
    "tenant-db": Target("tenant-db.production.env.example", "env", "{etc}/{env}/tenant-db.env", "always"),
    "tenant-site": Target("tenant-site.production.env.example", "site", "sites/<site>/site_config.json", "always"),
    "keycloak": Target("keycloak.production.env.example", "env", "{etc}/{env}/keycloak.env", "always"),
    "keycloak-db": Target("keycloak-db.production.env.example", "env", "{etc}/{env}/keycloak-db.env", "always"),
    "identity-sync": Target(
        "identity-sync.production.env.example", "env", "{etc}/{env}/identity-sync.env", "always"),
    "press": Target("press.production.env.example", "env", "{etc}/{env}/press.env", "press"),
    "press-site": Target("press-site.production.env.example", "site", "sites/<site>/site_config.json", "press"),
    "offsite": Target("offsite.production.env.example", "env", "{etc}/{env}/offsite.env", "offsite"),
    "edge": Target("edge.production.env.example", "env", "{etc}/edge.env", "always"),
}
ENVIRONMENTS = ("alpha", "beta", "rc", "prod")
LIST_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PLACEHOLDER = re.compile(r"<[^<>]*>")


class SettingsError(ValueError):
    """A list file is malformed."""


def is_placeholder(value):
    return bool(PLACEHOLDER.fullmatch(value.strip()))


def parse_list(path):
    entries, optional, fixed = [], False, False
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            optional = fixed = False
            continue
        if line.startswith("#"):
            optional = optional or "[isteğe bağlı]" in line
            fixed = fixed or "[sabit]" in line
            continue
        key, separator, value = line.partition("=")
        if not separator or not LIST_KEY.fullmatch(key):
            raise SettingsError(f"{path}:{number}: expected KEY=<value>")
        entries.append(Entry(key, value, optional, fixed))
        optional = fixed = False
    return entries


def parse_env(path):
    """Keys and values of a docker compose env file. Quotes around a value are removed."""
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def compare(entries, present):
    """Problems of one file or site. present maps a key to its value, or to None (value unknown)."""
    problems = []
    for entry in entries:
        value = present.get(entry.key)
        if entry.key not in present or value == "":
            if not entry.optional:
                problems.append(f"{entry.key} (missing)")
        elif value is not None and is_placeholder(value):
            problems.append(f"{entry.key} (placeholder left)")
        elif value is not None and entry.fixed and value != entry.value:
            problems.append(f"{entry.key} (must be {entry.value})")
    return problems


def check_files(env, lists, etc, press=False, offsite_required=False):
    if env not in ENVIRONMENTS:
        raise SettingsError(f"unknown environment: {env}")
    problems = []
    for name, target in LISTS.items():
        if target.kind != "env":
            continue
        path = Path(target.path.format(etc=etc, env=env))
        if target.when == "press" and not press:
            continue
        if target.when == "offsite" and not offsite_required and not path.exists():
            continue
        if not path.is_file():
            problems.append(f"{path}: file is missing (list: {target.list_file})")
            continue
        # Files of one environment belong to its deploy user only. edge.env is shared by the server.
        if "{env}" in target.path and stat.S_IMODE(path.stat().st_mode) & 0o077:
            problems.append(f"{path}: permissions must be 0600")
        try:
            present = parse_env(path)
        except (OSError, UnicodeDecodeError) as error:
            problems.append(f"{path}: cannot read ({error.__class__.__name__})")
            continue
        for problem in compare(parse_list(Path(lists) / target.list_file), present):
            problems.append(f"{path}: {problem}")
    return problems


def check_sites(lists, probe, sites, first_install=False):
    """probe maps each existing site to the names of its non-empty settings (site-probe.py)."""
    entries = parse_list(Path(lists) / LISTS["tenant-site"].list_file)
    problems = []
    for site in sites:
        if site not in probe:
            if not first_install:
                problems.append(f"site {site} does not exist; create it with the first install steps")
            continue
        present = {key: None for key in probe[site]}
        for problem in compare(entries, present):
            problems.append(f"site {site}, site_config.json: {problem}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    files = commands.add_parser("check-files", help="check the secret files of one environment")
    files.add_argument("env", choices=ENVIRONMENTS)
    files.add_argument("lists")
    files.add_argument("--etc", default="/etc/atonota")
    files.add_argument("--press", choices=("0", "1"), required=True)
    files.add_argument("--offsite", choices=("0", "1"), required=True)
    sites = commands.add_parser("check-sites", help="check the site settings of the tenant sites")
    sites.add_argument("lists")
    sites.add_argument("probe")
    sites.add_argument("--first-install", choices=("0", "1"), default="0")
    sites.add_argument("sites", nargs="+")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "check-files":
            problems = check_files(arguments.env, arguments.lists, arguments.etc,
                                   press=arguments.press == "1", offsite_required=arguments.offsite == "1")
        else:
            probe = json.loads(Path(arguments.probe).read_text(encoding="utf-8"))
            if not isinstance(probe, dict) or not all(isinstance(keys, list) for keys in probe.values()):
                raise SettingsError("the site probe did not print a JSON object of key lists")
            problems = check_sites(arguments.lists, probe, arguments.sites,
                                   first_install=arguments.first_install == "1")
    except (SettingsError, OSError, json.JSONDecodeError) as error:
        print(f"settings: {error}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"settings: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
