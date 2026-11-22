"""Apply an explicit naming map to tracked backend files."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile

RULE_TYPES = {"path", "module", "identifier", "setting", "doctype", "reference"}
EXCLUDED = ("backend/docs/standartlar", "backend/dev/naming")


@dataclass(frozen=True)
class Rule:
    old: str
    new: str
    type: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class Change:
    source: str
    target: str
    content: bytes | None


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def under(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


def included(path: str) -> bool:
    return (
        path.startswith("backend/")
        and not any(under(path, parent) for parent in EXCLUDED)
        and not {"translations", "locale"}.intersection(PurePosixPath(path).parts)
        and PurePosixPath(path).name != "glossary.yaml"
    )


def load_rules(map_path: Path) -> tuple[Rule, ...]:
    entries = json.loads(map_path.read_bytes())
    if not isinstance(entries, list):
        raise ValueError("The naming map must contain a list of rules.")
    rules = []
    path_sources = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"old", "new", "type", "paths"}:
            raise ValueError(f"Invalid naming rule: {entry!r}")
        old, new, kind = (entry.get(key) for key in ("old", "new", "type"))
        if not all(isinstance(value, str) and value for value in (old, new, kind)):
            raise ValueError(f"Each rule needs a nonempty old, new and type: {entry!r}")
        if kind not in RULE_TYPES or old == new or "\0" in old + new:
            raise ValueError(f"Invalid naming rule: {entry!r}")
        paths = entry.get("paths", [])
        if not isinstance(paths, list) or not all(isinstance(path, str) and path for path in paths):
            raise ValueError(f"Invalid path scope: {entry!r}")
        if kind == "path":
            if paths or old in path_sources or under(new, old):
                raise ValueError(f"Invalid or duplicate path rule: {entry!r}")
            for path in (old, new):
                if not included(path) or any(
                    part.casefold() in {".", "..", "", ".git"} for part in path.split("/")
                ):
                    raise ValueError(f"Path rule leaves the tracked backend scope: {path!r}")
            path_sources.add(old)
        rules.append(Rule(old, new, kind, tuple(paths)))
    return tuple(rules)


@lru_cache(maxsize=256)
def text_replacer(rules: tuple[Rule, ...]) -> tuple[dict[str, str], re.Pattern[str]]:
    replacements = {}
    for rule in rules:
        if replacements.setdefault(rule.old, rule.new) != rule.new:
            raise ValueError(f"Conflicting text rules for {rule.old!r}")
    protected = set(replacements.values())
    chained = protected.intersection(replacements)
    if chained:
        raise ValueError(f"Chained text rules: {', '.join(sorted(chained))}")
    names = sorted(replacements.keys() | protected, key=lambda name: (-len(name), name))
    alternatives = "|".join(re.escape(name) for name in names)
    return replacements, re.compile(r"(?<![\w-])(?:" + alternatives + r")(?![\w-])")


def rewrite(data: bytes, rules: tuple[Rule, ...]) -> bytes:
    if not rules or b"\0" in data:
        return data
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    replacements, pattern = text_replacer(rules)
    return pattern.sub(lambda match: replacements.get(match[0], match[0]), source).encode("utf-8")


def tracked_paths(root: Path) -> list[str]:
    records = git(root, "ls-files", "-z", "--stage", "--", "backend/").split(b"\0")
    paths = []
    for record in filter(None, records):
        metadata, name = record.split(b"\t", 1)
        mode, _, stage = metadata.split()
        path = os.fsdecode(name)
        if stage != b"0" and included(path):
            raise ValueError(f"Unmerged tracked file: {path}")
        if mode.startswith(b"100") and included(path):
            paths.append(path)
    return paths


def destination(path: str, path_rules: tuple[Rule, ...]) -> str:
    for rule in path_rules:
        if under(path, rule.old):
            return rule.new + path[len(rule.old) :]
    return path


def check_ancestors(root: Path, path: str) -> None:
    parent = root
    for segment in PurePosixPath(path).parts[:-1]:
        parent /= segment
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(f"Unsafe parent for {path}: {parent.relative_to(root)}")


def scopes_for(source: str, target: str, path_rules: tuple[Rule, ...]) -> set[str]:
    aliases = {source, target}
    for rule in path_rules:
        if under(target, rule.new):
            alias = rule.old + target[len(rule.new) :]
            if destination(alias, path_rules) == target:
                aliases.add(alias)
    return aliases


def build_plan(root: Path, rules: tuple[Rule, ...]) -> list[Change]:
    path_rules = tuple(
        sorted(
            (rule for rule in rules if rule.type == "path"),
            key=lambda rule: -len(rule.old),
        )
    )
    changes = []
    destinations = {}
    paths = tracked_paths(root)
    for source in paths:
        target = destination(source, path_rules)
        if not included(target) or destination(target, path_rules) != target:
            raise ValueError(f"Invalid final path: {source} -> {target}")
        if source != target:
            check_ancestors(root, target)
            if os.path.lexists(root / target):
                raise ValueError(f"Destination already exists: {target}")
        # Detect collisions on case-insensitive worktrees before moving anything.
        other = destinations.setdefault(target.casefold(), source)
        if other != source and (source != target or destination(other, path_rules) != other):
            raise ValueError(f"Conflicting destinations: {other} and {source} -> {target}")

        check_ancestors(root, source)
        file_path = root / source
        if file_path.is_symlink():
            raise ValueError(f"Tracked regular file replaced by a symlink: {source}")
        if not file_path.exists():
            if source != target:
                raise ValueError(f"Missing move source: {source}")
            continue
        if not file_path.is_file():
            raise ValueError(f"Tracked path is no longer a regular file: {source}")

        scopes = scopes_for(source, target, path_rules)
        scoped_rules = tuple(
            rule
            for rule in rules
            if not rule.paths or any(fnmatchcase(path, scope) for path in scopes for scope in rule.paths)
        )
        data = file_path.read_bytes()
        updated = rewrite(data, scoped_rules)
        if data != updated and rewrite(updated, scoped_rules) != updated:
            raise ValueError(f"Text rules would change {target} again on the next run.")
        if source != target or updated != data:
            changes.append(Change(source, target, updated if updated != data else None))
    for change in changes:
        for parent in PurePosixPath(change.target).parents:
            if parent.as_posix().casefold() in destinations:
                raise ValueError(f"Planned file would block parent directory for {change.target}: {parent}")
    return changes


def replace_content(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(data)
            file.close()
            temporary.chmod(mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def run(root: Path, changes: list[Change], dry_run: bool) -> None:
    for change in changes:
        if change.source != change.target:
            print(f"move {change.source} -> {change.target}")
            if not dry_run:
                (root / change.target).parent.mkdir(parents=True, exist_ok=True)
                git(root, "mv", "--", change.source, change.target)
        if change.content is not None:
            print(f"edit {change.target}")
            if not dry_run:
                replace_content(root / change.target, change.content)
    print(f"{len(changes)} tracked file(s) {'would change' if dry_run else 'changed'}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Git worktree to inspect.")
    parser.add_argument(
        "--map",
        type=Path,
        default=Path(__file__).with_name("rename-map.json"),
        help="JSON file containing the reviewed renaming rules.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List changes without writing files.")
    args = parser.parse_args()
    try:
        root = Path(os.fsdecode(git(args.repo, "rev-parse", "--show-toplevel").rstrip(b"\n")))
        run(root, build_plan(root, load_rules(args.map)), args.dry_run)
    except (OSError, ValueError) as error:
        print(f"Naming update stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
