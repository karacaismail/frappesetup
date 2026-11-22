"""Apply an explicit naming map to tracked backend files."""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import os
import re
import stat
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile

RULE_TYPES = {"path", "module", "identifier", "setting", "doctype", "reference"}
EXCLUDED = ("backend/dev/naming", "backend/docs/standartlar")
REDIRECTS = {"backend/PROJE-KAYDI.md", "backend/docs/sozlesmeler.md"}
GLOSSARY_APPS = {
    "press_tr": "backend/apps/press_tr",
    "hrms_tr": "backend/apps/hrms_tr",
    "mobile_test_app": "backend/dev/mobile_test_app",
}
COPY_KEYS = r"label|description|help_text|message|placeholder|title"
TECHNICAL = re.compile(r"[\w./:%@{}$?&=\\+*-]+")
QUOTED = r"""(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*')"""
JS_REGEX = r"(?<=[(=,:;!])\s*/(?![/*])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n])+/[a-z]*"


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
    original: bytes
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
        and not fnmatchcase(PurePosixPath(path).name, "messages_*.properties")
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


def literal_value(token: str) -> str:
    opening = re.match(r"""[rRbBuUfF]*("{1,3}|'{1,3})""", token)
    if opening is None:
        return token
    return token[opening.end() : -len(opening[1])]


def python_spans(source: str) -> list[tuple[int, int, str, bool]]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    spans = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            start = offsets[token.start[0] - 1] + token.start[1]
            end = offsets[token.end[0] - 1] + token.end[1]
            spans.append((start, end, literal_value(token.string), token.type == tokenize.COMMENT))
    return spans


def rewrite_source(source: str, rules: tuple[Rule, ...], path: str) -> str:
    if not rules:
        return source
    replacements, pattern = text_replacer(rules)
    suffix = PurePosixPath(path).suffix
    spans = []
    if suffix == ".py":
        spans = python_spans(source)
    elif suffix in {".js", ".ts", ".jsx", ".tsx", ".css", ".scss"}:
        for match in re.finditer(JS_REGEX + "|" + QUOTED + r"|/\*[\s\S]*?\*/|//[^\n]*", source):
            token = match[0].lstrip()
            spans.append((*match.span(), literal_value(token), token.startswith(("//", "/*"))))
    elif suffix in {".html", ".ftl", ".jinja", ".j2"}:
        comments = r"<!--[\s\S]*?-->|<#--[\s\S]*?-->"
        spans = [(*match.span(), "", True) for match in re.finditer(comments, source)]
    elif suffix == ".json":
        copies = rf'"(?:{COPY_KEYS})"\s*:\s*({QUOTED})'
        spans = [(*match.span(1), "", True) for match in re.finditer(copies, source)]
    elif suffix in {".yaml", ".yml"}:
        copies = rf"""(?im)^\s*["']?(?:{COPY_KEYS})["']?\s*:\s*({QUOTED}|[^\r\n]*)"""
        spans = [(*match.span(1), "", True) for match in re.finditer(copies, source)]
        blocks = rf"(?m)^(?P<indent>[ \t]*)(?:{COPY_KEYS}):[ \t]*[>|][+-]?(?:\r?\n(?P=indent)[ \t]+[^\r\n]*)+"
        spans.extend((*match.span(), "", True) for match in re.finditer(blocks, source))
    elif suffix in {".sh", ".toml"} or path.startswith("backend/dev/bin/"):
        for match in re.finditer(QUOTED + r"|(?<!\S)#[^\r\n]*", source):
            spans.append((*match.span(), literal_value(match[0]), match[0].startswith("#")))

    def replace(match: re.Match[str]) -> str:
        old = match[0]
        new = replacements.get(old, old)
        if old == new:
            return old
        for start, end, value, protected in spans:
            if match.start() >= end or match.end() <= start:
                continue
            if protected:
                return old
            if match.start() >= start and match.end() <= end:
                if match.span() == (start, end) or (
                    old == value
                    or TECHNICAL.fullmatch(value)
                    or (old.startswith("tab") and re.search(r"\b(?:FROM|JOIN|UPDATE|INTO)\b", value, re.I))
                ):
                    continue
                return old
        return new

    return pattern.sub(replace, source)


def rewrite_translation(source: str, rules: tuple[Rule, ...], suffix: str) -> str:
    keys = {rule.old: rule.new for rule in rules}
    if suffix == ".po":

        def update_msgid(match: re.Match[str]) -> str:
            key = json.loads(match[2]) + "".join(
                json.loads(chunk) for chunk in match[3].splitlines() if chunk
            )
            return f"{match[1]} " + json.dumps(keys[key], ensure_ascii=False) if key in keys else match[0]

        po_string = r'"(?:\\.|[^"\\\r\n])*"'
        pattern = rf"^(msgid(?:_plural)?) ({po_string})((?:\r?\n{po_string})*)(?=\r?$)"
        return re.sub(pattern, update_msgid, source, flags=re.M)
    first_cell = re.compile(r'("(?:[^"]|"")*"|[^,\r\n]*)(?=,)')
    stream = io.StringIO(source, newline="")
    output, start = [], 0
    for row in csv.reader(stream):
        end = stream.tell()
        original = source[start:end]
        start = end
        match = first_cell.match(original)
        if row and match and row[0] in keys:
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="\r\n").writerow([keys[row[0]]])
            original = buffer.getvalue()[:-2] + original[match.end() :]
        output.append(original)
    return "".join(output)


def rewrite(data: bytes, rules: tuple[Rule, ...], path: str) -> bytes:
    suffix = PurePosixPath(path).suffix
    if not rules or b"\0" in data or suffix in {".md", ".rst"}:
        return data
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    translation = {"translations", "locale"}.intersection(PurePosixPath(path).parts)
    if translation and suffix in {".csv", ".po"}:
        return rewrite_translation(source, rules, suffix).encode("utf-8")
    return rewrite_source(source, rules, path).encode("utf-8")


def function_names(node: ast.AST) -> set[str]:
    names = set()
    pending = list(ast.iter_child_nodes(node))
    while pending:
        child = pending.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.arg):
            names.add(child.arg)
        pending.extend(ast.iter_child_nodes(child))
    return names


def check_python_names(path: str, before: bytes, after: bytes, rules: tuple[Rule, ...]) -> None:
    if not path.endswith(".py") or before == after:
        return
    old_tree = ast.parse(before, filename=path)
    new_tree = ast.parse(after, filename=path)
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    old_functions = [node for node in ast.walk(old_tree) if isinstance(node, function_types)]
    new_functions = [node for node in ast.walk(new_tree) if isinstance(node, function_types)]
    for old, new in zip(old_functions, new_functions):
        old_names = function_names(old)
        new_names = function_names(new)
        for rule in rules:
            if {rule.old, rule.new} <= old_names and rule.old not in new_names and rule.new in new_names:
                raise ValueError(f"Name collision in {path}:{old.lineno}: {rule.old} -> {rule.new}")


def tracked_paths(root: Path) -> list[tuple[str, bool]]:
    records = git(root, "ls-files", "-z", "--stage", "--", "backend/").split(b"\0")
    paths = []
    for record in filter(None, records):
        metadata, name = record.split(b"\t", 1)
        mode, _, stage = metadata.split()
        path = os.fsdecode(name)
        if not included(path):
            continue
        if stage != b"0":
            raise ValueError(f"Unmerged tracked file: {path}")
        paths.append((path, mode.startswith(b"100")))
    return paths


def destination(path: str, path_rules: tuple[Rule, ...]) -> str:
    for rule in path_rules:
        if under(path, rule.old):
            return rule.new + path[len(rule.old) :]
    return path


def redirect_content(source: str, target: str) -> bytes:
    link = os.path.relpath(target, start=PurePosixPath(source).parent)
    return f"[Yeni dosyayı açın.]({link})\n".encode()


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
    for source, regular in tracked_paths(root):
        target = destination(source, path_rules)
        if not included(target) or destination(target, path_rules) != target:
            raise ValueError(f"Invalid final path: {source} -> {target}")
        if source != target:
            if not regular:
                raise ValueError(f"Path rule matches a symbolic link or submodule: {source}")
            check_ancestors(root, target)
            if os.path.lexists(root / target):
                source_file = root / source
                if (
                    source in REDIRECTS
                    and source_file.is_file()
                    and not source_file.is_symlink()
                    and source_file.read_bytes() == redirect_content(source, target)
                    and (root / target).is_file()
                    and not (root / target).is_symlink()
                ):
                    continue
                raise ValueError(f"Destination already exists: {target}")
        # Detect collisions on case-insensitive worktrees before moving anything.
        other = destinations.setdefault(target.casefold(), source)
        if other != source and (source != target or destination(other, path_rules) != other):
            raise ValueError(f"Conflicting destinations: {other} and {source} -> {target}")

        if not regular:
            continue
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
        updated = rewrite(data, scoped_rules, source)
        check_python_names(source, data, updated, scoped_rules)
        if data != updated and rewrite(updated, scoped_rules, target) != updated:
            raise ValueError(f"Text rules would change {target} again on the next run.")
        if source != target or updated != data:
            changes.append(Change(source, target, data, updated if updated != data else None))
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


def check_unchanged(root: Path, path: str, original: bytes) -> None:
    check_ancestors(root, path)
    file_path = root / path
    if file_path.is_symlink() or not file_path.is_file() or file_path.read_bytes() != original:
        raise ValueError(f"File changed after planning: {path}")


def check_settings(paths: list[Path], rules: tuple[Rule, ...]) -> int:
    settings = {rule.old for rule in rules if rule.type == "setting" and rule.old.isidentifier()}
    remaining = 0
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            keys = set(json.loads(source))
        else:
            keys = set(re.findall(r"(?m)^\s*(?:export\s+)?([A-Za-z_][\w]*)\s*=", source))
        for key in sorted(settings & keys):
            print(f"Legacy setting key in {path}: {key}")
            remaining += 1
    return int(bool(remaining))


def check_modules(root: Path, rules: tuple[Rule, ...]) -> int:
    module_rules = [rule for rule in rules if rule.type == "module"]
    aliases = []
    for rule in module_rules:
        if "." in rule.old and rule.old.startswith(("platform_core.", "press_tr.")):
            aliases.extend(
                (
                    Rule(rule.old.replace(".", r"\."), rule.new.replace(".", r"\."), "module", rule.paths),
                    Rule(rule.old.replace(".", "/"), rule.new.replace(".", "/"), "module", rule.paths),
                )
            )
    legacy = tuple(dict.fromkeys(module_rules + aliases))
    path_rules = tuple(
        sorted((rule for rule in rules if rule.type == "path"), key=lambda rule: -len(rule.old))
    )
    findings = 0
    for path, regular in tracked_paths(root):
        absolute = root / path
        if not regular or not absolute.is_file() or absolute.is_symlink():
            continue
        if PurePosixPath(path).suffix not in {".py", ".json", ".yaml", ".yml", ".js", ".ts"} and (
            PurePosixPath(path).name != "modules.txt"
        ):
            continue
        scopes = scopes_for(path, path, path_rules)
        selected = tuple(
            rule
            for rule in legacy
            if not rule.paths
            or any(fnmatchcase(scope, pattern) for scope in scopes for pattern in rule.paths)
        )
        data = absolute.read_bytes()
        if rewrite(data, selected, path) != data:
            print(f"Legacy module reference: {path}")
            findings += 1
    return int(bool(findings))


def glossary_additions(root: Path) -> dict[str, bytes]:
    additions = {}
    for app, app_path in GLOSSARY_APPS.items():
        if not (root / app_path / "pyproject.toml").is_file():
            continue
        target = f"{app_path}/docs/glossary.yaml"
        check_ancestors(root, target)
        target_path = root / target
        if os.path.lexists(target_path):
            if target_path.is_symlink() or not target_path.is_file():
                raise ValueError(f"Invalid glossary target: {target}")
            continue
        reference = Path(__file__).with_name("glossaries") / app / "docs/glossary.yaml"
        additions[target] = reference.read_bytes()
    return additions


def report_untracked(root: Path, rules: tuple[Rule, ...]) -> None:
    paths = git(root, "ls-files", "-z", "--others", "--directory", "--", "backend/").split(b"\0")
    old_paths = tuple(rule.old for rule in rules if rule.type == "path")
    for path in filter(None, paths):
        relative_path = os.fsdecode(path).rstrip("/")
        if any(under(relative_path, old) for old in old_paths):
            print(f"left untracked {relative_path}")


def run(root: Path, changes: list[Change], additions: dict[str, bytes], dry_run: bool) -> None:
    for change in changes:
        if change.source != change.target:
            print(f"move {change.source} -> {change.target}")
            if not dry_run:
                check_unchanged(root, change.source, change.original)
                check_ancestors(root, change.target)
                if os.path.lexists(root / change.target):
                    raise ValueError(f"Destination appeared after planning: {change.target}")
                (root / change.target).parent.mkdir(parents=True, exist_ok=True)
                git(root, "mv", "--", change.source, change.target)
                if change.source in REDIRECTS:
                    with (root / change.source).open("xb") as redirect:
                        redirect.write(redirect_content(change.source, change.target))
                    git(root, "add", "--", change.source)
        if change.content is not None:
            print(f"edit {change.target}")
            if not dry_run:
                check_unchanged(root, change.target, change.original)
                replace_content(root / change.target, change.content)
    for path, content in additions.items():
        print(f"add {path}")
        if not dry_run:
            check_ancestors(root, path)
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            with (root / path).open("xb") as glossary:
                glossary.write(content)
            git(root, "add", "--", path)
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
    parser.add_argument("--check-modules", action="store_true", help="Only report old module references.")
    parser.add_argument("--dry-run", action="store_true", help="List changes without writing files.")
    parser.add_argument(
        "--check-settings",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="Only report old keys in the given environment or site config files.",
    )
    args = parser.parse_args()
    try:
        root = Path(os.fsdecode(git(args.repo, "rev-parse", "--show-toplevel").rstrip(b"\n")))
        rules = load_rules(args.map)
        if args.check_settings:
            return check_settings(args.check_settings, rules)
        if args.check_modules:
            return check_modules(root, rules)
        additions = (
            glossary_additions(root)
            if args.map.resolve() == Path(__file__).with_name("rename-map.json").resolve()
            else {}
        )
        changes = build_plan(root, rules)
        if args.dry_run:
            report_untracked(root, rules)
        run(root, changes, additions, args.dry_run)
    except (OSError, ValueError, SyntaxError, tokenize.TokenError, csv.Error) as error:
        print(f"Naming update stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
