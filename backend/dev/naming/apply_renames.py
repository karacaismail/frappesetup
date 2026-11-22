"""Apply an explicit naming map to tracked backend files."""

from __future__ import annotations

import argparse
import ast
import csv
import errno
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
COPY_KEYS = r"label|description|summary|help_text|message|placeholder|title"
TECHNICAL = re.compile(r"[\w./:%@{}$?&=\\+*-]+")
QUOTED = r"""(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*')"""
JS_REGEX = r"(?<=[(=,:;!])\s*/(?![/*])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n])+/[a-z]*"
SCOPED_MODULE_REFERENCE = re.compile(r"`[\w./-]+`|[A-Za-z_]\w*(?:\\?\.[A-Za-z_]\w*)+")


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


def bare_module(rule: Rule) -> bool:
    return rule.type == "module" and rule.old.isidentifier()


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


def load_json(path: Path):
    # Keep the command standalone when invoked with Python's isolated mode.
    def object_from_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{path}: Duplicate JSON key.")
            result[key] = value
        return result

    def reject_constant(_constant):
        raise ValueError(f"{path}: Non-finite JSON number.")

    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=object_from_pairs, parse_constant=reject_constant
    )


def load_rules(map_path: Path) -> tuple[Rule, ...]:
    entries = load_json(map_path)
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
        if token.type in (tokenize.COMMENT, tokenize.STRING, tokenize.FSTRING_MIDDLE):
            start = offsets[token.start[0] - 1] + token.start[1]
            end = offsets[token.end[0] - 1] + token.end[1]
            spans.append((start, end, literal_value(token.string), token.type != tokenize.STRING))
    return spans


def rewrite_source(source: str, rules: tuple[Rule, ...], path: str) -> str:
    if not rules:
        return source
    replacements, pattern = text_replacer(rules)
    identifier_names = {rule.old for rule in rules if rule.type == "identifier"}
    bare_modules = {rule.old for rule in rules if bare_module(rule)} - identifier_names
    exact_fstrings = {rule.old for rule in rules if rule.paths and ('f"' in rule.old or "f'" in rule.old)}
    suffix = PurePosixPath(path).suffix
    scoped_module_references = {
        rule.old
        for rule in rules
        if rule.type == "module"
        and rule.paths
        and SCOPED_MODULE_REFERENCE.fullmatch(rule.old)
        and SCOPED_MODULE_REFERENCE.fullmatch(rule.new)
    }
    spans = []
    if suffix == ".py":
        spans = python_spans(source)
    elif suffix in {".js", ".ts", ".jsx", ".tsx", ".css", ".scss"}:
        template = r"`(?:\\.|[^`\\])*`"
        for match in re.finditer(
            JS_REGEX + "|" + QUOTED + "|" + template + r"|/\*[\s\S]*?\*/|//[^\n]*", source
        ):
            token = match[0].lstrip()
            if token.startswith("`"):
                start = match.start()
                for expression in re.finditer(r"(?<!\\)\$\{[^{}]*\}", token):
                    spans.append((start, match.start() + expression.start() + 2, "", True))
                    start = match.start() + expression.end() - 1
                spans.append((start, match.end(), "", True))
            else:
                spans.append((*match.span(), literal_value(token), token.startswith(("//", "/*"))))
    elif suffix in {".html", ".ftl", ".jinja", ".j2"}:
        comments = r"<!--[\s\S]*?-->|<#--[\s\S]*?-->"
        spans = [(*match.span(), "", True) for match in re.finditer(comments, source)]
        markup = r"""(?:<(?:"[^"]*"|'[^']*'|[^>'"])*>|\$\{[^}]*\}|\{\{.*?\}\}|\{%.*?%\})"""
        cursor = 0
        for tag in re.finditer(markup, source, re.DOTALL):
            spans.append((cursor, tag.start(), "", True))
            cursor = tag.end()
        spans.append((cursor, len(source), "", True))
    elif suffix == ".json":
        copies = rf'"(?:{COPY_KEYS})"\s*:\s*({QUOTED})'
        spans = [(*match.span(1), "", True) for match in re.finditer(copies, source)]
    elif suffix in {".yaml", ".yml"}:
        copies = rf"""(?im)^\s*["']?(?:{COPY_KEYS})["']?\s*:\s*({QUOTED}|[^\r\n]*)"""
        spans = [(*match.span(1), "", True) for match in re.finditer(copies, source)]
        blocks = (
            rf"""(?m)^(?P<indent>[ \t]*)(?P<quote>["']?)(?:{COPY_KEYS})(?P=quote):[ \t]*[>|]"""
            r"(?:[1-9][+-]?|[+-][1-9]?)?[ \t]*(?:#[^\r\n]*)?"
            r"(?:\r?\n(?:[ \t]*(?=\r?$)|(?P=indent)[ \t]+[^\r\n]*))+"
        )
        spans.extend((*match.span(), "", True) for match in re.finditer(blocks, source))
    elif suffix in {".sh", ".toml"} or path.startswith("backend/dev/bin/"):
        for match in re.finditer(QUOTED + r"|(?<!\S)#[^\r\n]*", source):
            spans.append((*match.span(), literal_value(match[0]), match[0].startswith("#")))

    def replace(match: re.Match[str]) -> str:
        old = match[0]
        new = replacements.get(old, old)
        if old == new:
            return old
        path_segment = (
            source[match.start() - 1 : match.start()] == "/" or source[match.end() : match.end() + 1] == "/"
        )
        matched_literal = False
        for start, end, value, protected in spans:
            if match.start() >= end or match.end() <= start:
                continue
            if (
                suffix in {".py", ".yaml", ".yml"}
                and old in scoped_module_references
                and start <= match.start() <= match.end() <= end
            ):
                return new
            if protected:
                if old in exact_fstrings and match.start() <= start and match.end() >= end:
                    continue
                return old
            if match.start() >= start and match.end() <= end:
                if old == value:
                    matched_literal = True
                if match.span() == (start, end) or (
                    old == value
                    or TECHNICAL.fullmatch(value)
                    or (old.startswith("tab") and re.search(r"\b(?:FROM|JOIN|UPDATE|INTO)\b", value, re.I))
                ):
                    continue
                return old
        if old in bare_modules and not (path_segment or matched_literal):
            if path.endswith("/modules.txt"):
                prefix = source[: match.start()].rpartition("\n")[2]
                line_suffix = source[match.end() :].partition("\n")[0]
                if not (prefix.strip() or line_suffix.strip()):
                    return new
            if re.fullmatch(rf"""["']{re.escape(old)}["']""", source[match.start() - 1 : match.end() + 1]):
                return new
            return old
        return new

    return pattern.sub(replace, source)


def rewrite_translation(source: str, rules: tuple[Rule, ...], path: str, suffix: str) -> str:
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
    cell = re.compile(r'"(?:[^"]|"")*"|[^,\r\n]*')
    stream = io.StringIO(source, newline="")
    reader = csv.reader(stream)
    output, start = [], 0
    original_keys = {}
    for row in reader:
        if len(row) in {2, 3}:
            context = row[2] if len(row) == 3 else ""
            previous_key = (row[0], context)
            updated_key = (keys.get(row[0], row[0]), keys.get(context, context))
            if original_keys.setdefault(updated_key, previous_key) != previous_key:
                raise ValueError(f"Translation key collision in {path}:{reader.line_num}")
        end = stream.tell()
        original = source[start:end]
        start = end
        offsets = []
        cursor = 0
        for index, field in enumerate(row):
            match = cell.match(original, cursor)
            if not match:
                break
            if index in {0, 2} and field in keys:
                buffer = io.StringIO()
                csv.writer(buffer, lineterminator="\r\n").writerow([keys[field]])
                offsets.append((match.start(), match.end(), buffer.getvalue()[:-2]))
            cursor = match.end() + 1
        for left, right, replacement in reversed(offsets):
            original = original[:left] + replacement + original[right:]
        output.append(original)
    return "".join(output)


def rewrite(data: bytes, rules: tuple[Rule, ...], path: str) -> bytes:
    suffix = PurePosixPath(path).suffix
    if not rules or b"\0" in data or suffix in {".md", ".rst", ".properties"}:
        return data
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Cannot rename non-UTF-8 source: {path}") from error
    translation = {"translations", "locale"}.intersection(PurePosixPath(path).parts)
    if translation and suffix in {".csv", ".po"}:
        return rewrite_translation(source, rules, path, suffix).encode("utf-8")
    return rewrite_source(source, rules, path).encode("utf-8")


def scope_names(node: ast.AST) -> set[tuple[str, str]]:
    names = set()
    pending = list(ast.iter_child_nodes(node))
    while pending:
        child = pending.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(("binding", child.name))
            continue
        if isinstance(child, ast.Lambda):
            continue
        if isinstance(child, ast.Name):
            names.add(("binding", child.id))
        elif isinstance(child, ast.arg):
            names.add(("binding", child.arg))
        elif isinstance(child, ast.Attribute):
            names.add(("attribute", child.attr))
        pending.extend(ast.iter_child_nodes(child))
    return names


def check_python_names(path: str, before: bytes, after: bytes, rules: tuple[Rule, ...]) -> None:
    if not path.endswith(".py"):
        return
    old_tree = ast.parse(before, filename=path)
    new_tree = old_tree if before == after else ast.parse(after, filename=path)
    scope_types = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    old_scopes = [node for node in ast.walk(old_tree) if isinstance(node, scope_types)]
    new_scopes = [node for node in ast.walk(new_tree) if isinstance(node, scope_types)]
    identifier_rules = tuple(
        rule
        for rule in rules
        if rule.type == "identifier" and rule.old.isidentifier() and rule.new.isidentifier()
    )
    for before_scope, after_scope in zip(old_scopes, new_scopes):
        old_names = scope_names(before_scope)
        new_names = scope_names(after_scope)
        line = getattr(before_scope, "lineno", 1)
        for rule in identifier_rules:
            for category in ("binding", "attribute"):
                old, new = (category, rule.old), (category, rule.new)
                if old in old_names and new in old_names and old not in new_names and new in new_names:
                    raise ValueError(f"Name collision in {path}:{line}: {rule.old} -> {rule.new}")
                if old in old_names and old in new_names:
                    raise ValueError(f"Legacy Python name in {path}:{line}: {rule.old}")


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


def select_rules(rules: tuple[Rule, ...], paths: set[str], source: str) -> tuple[Rule, ...]:
    selected = []
    press_app = source.startswith("backend/apps/press_tr/")
    for rule in rules:
        if bare_module(rule):
            if rule.old.casefold() == "kimlik":
                preferred = {
                    "kimlik": ("press_identity", "identity"),
                    "Kimlik": ("Press Identity", "Identity"),
                }[rule.old][not press_app]
                if rule.new != preferred:
                    continue
            selected.append(rule)
        elif not rule.paths or any(fnmatchcase(path, scope) for path in paths for scope in rule.paths):
            selected.append(rule)
    return tuple(dict.fromkeys(selected))


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
        scoped_rules = select_rules(rules, scopes, source)
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


def legacy_module_pattern(rules: tuple[Rule, ...]) -> re.Pattern[str]:
    qualified = set()
    bare = set()
    for rule in rules:
        if rule.type != "module":
            continue
        if bare_module(rule):
            bare.add(rule.old)
        elif rule.old.startswith(("platform_core.", "press_tr.")):
            qualified.update((rule.old, rule.old.replace(".", r"\."), rule.old.replace(".", "/")))
        elif re.fullmatch(r"[A-Za-z ]+", rule.old):
            bare.add(rule.old)
    alternatives = []
    if qualified:
        names = "|".join(re.escape(name) for name in sorted(qualified, key=lambda name: (-len(name), name)))
        alternatives.append(rf"(?<![\w-])(?:{names})(?![\w-])")
    if bare:
        names = "|".join(re.escape(name) for name in sorted(bare))
        alternatives.append(rf"""(?<=["'])(?:{names})(?=["'])|(?<=/)(?:{names})(?=[/"'])""")
        alternatives.append(rf"""(?<=["'])(?:{names})(?=/)""")
    return re.compile("|".join(alternatives) or r"(?!)")


def check_modules(root: Path, rules: tuple[Rule, ...], allowlist: Path) -> int:
    allowed = set()
    if allowlist.is_file():
        entries = load_json(allowlist)
        allowed = {(entry["path"], entry["line_text"]) for entry in entries}
    pattern = legacy_module_pattern(rules)
    module_labels = {rule.old for rule in rules if rule.type == "module" and "." not in rule.old}
    findings = 0
    for path, regular in tracked_paths(root):
        absolute = root / path
        if not regular or not absolute.is_file() or absolute.is_symlink():
            continue
        if PurePosixPath(path).suffix not in {".py", ".json", ".yaml", ".yml", ".js", ".ts", ".sh"} and (
            PurePosixPath(path).name != "modules.txt" and not path.startswith("backend/dev/bin/")
        ):
            continue
        for number, line in enumerate(absolute.read_text(encoding="utf-8").splitlines(), 1):
            matches = [match[0] for match in pattern.finditer(line)]
            if absolute.name == "modules.txt" and line.strip() in module_labels:
                matches.append(line.strip())
            for name in matches:
                if (path, line.strip()) not in allowed:
                    print(f"Legacy module reference: {path}:{number}: {name}")
                    findings += 1
    return int(bool(findings))


def report_docs(root: Path, rules: tuple[Rule, ...]) -> None:
    replacements, pattern = text_replacer(
        tuple(rule for rule in rules if not rule.paths and rule.old.casefold() != "kimlik")
    )
    modules = legacy_module_pattern(rules)
    bare_names = {rule.old for rule in rules if bare_module(rule)}
    code_or_link = re.compile(r"`([^`]+)`|\]\(([^)]+)\)")
    for path, regular in tracked_paths(root):
        absolute = root / path
        if not regular or not path.endswith(".md") or not absolute.is_file() or absolute.is_symlink():
            continue
        fenced = False
        for number, line in enumerate(absolute.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            segments = [line] if fenced else [match[1] or match[2] for match in code_or_link.finditer(line)]
            for segment in segments:
                names = {match[0] for match in modules.finditer(segment)}
                names.update(match[0] for match in pattern.finditer(segment) if match[0] in replacements)
                if segment.strip() in bare_names:
                    names.add(segment.strip())
                for name in sorted(names):
                    print(f"{path}:{number}: {name}")


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


def missing_redirects(root: Path, rules: tuple[Rule, ...]) -> dict[str, bytes]:
    tracked = dict(tracked_paths(root))
    redirects = {}
    for rule in rules:
        if rule.type != "path" or rule.old not in REDIRECTS or rule.old in tracked:
            continue
        if not tracked.get(rule.new) or not (root / rule.new).is_file():
            continue
        check_ancestors(root, rule.old)
        redirects[rule.old] = redirect_content(rule.old, rule.new)
    return redirects


def stage_addition(root: Path, path: str, content: bytes) -> None:
    check_ancestors(root, path)
    absolute = root / path
    absolute.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=absolute.parent) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fchmod(temporary.fileno(), 0o644)
        try:
            os.link(temporary.name, absolute)
        except FileExistsError:
            if absolute.is_symlink() or not absolute.is_file() or absolute.read_bytes() != content:
                raise ValueError(f"Addition would overwrite an existing file: {path}") from None
    git(root, "add", "--", path)


def report_untracked(root: Path, rules: tuple[Rule, ...]) -> None:
    paths = git(
        root, "ls-files", "-z", "--others", "--directory", "--no-empty-directory", "--", "backend/"
    ).split(b"\0")
    old_paths = tuple(rule.old for rule in rules if rule.type == "path")
    for path in filter(None, paths):
        relative_path = os.fsdecode(path).rstrip("/")
        if any(under(relative_path, old) for old in old_paths):
            print(f"left untracked {relative_path}")


def remove_empty_old_directories(root: Path, changes: list[Change], rules: tuple[Rule, ...]) -> None:
    old_paths = {rule.old for rule in rules if rule.type == "path"}
    parents = {
        parent
        for change in changes
        if change.source != change.target
        for parent in PurePosixPath(change.source).parents
        if any(under(parent.as_posix(), old) for old in old_paths)
    }
    for parent in sorted(parents, key=lambda path: (len(path.parts), str(path)), reverse=True):
        check_ancestors(root, parent.as_posix())
        path = root / parent
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            path.rmdir()
        except OSError as error:
            if error.errno not in {errno.ENOTEMPTY, errno.EEXIST, errno.ENOENT}:
                raise


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
                    stage_addition(root, change.source, redirect_content(change.source, change.target))
        if change.content is not None:
            print(f"edit {change.target}")
            if not dry_run:
                check_unchanged(root, change.target, change.original)
                replace_content(root / change.target, change.content)
    for path, content in additions.items():
        print(f"add {path}")
        if not dry_run:
            stage_addition(root, path, content)
    print(f"{len(changes)} tracked file(s) {'would change' if dry_run else 'changed'}.")


def main() -> int:
    if sys.version_info < (3, 12):
        print("Python 3.12 or newer is required. Run this command with Python 3.14.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Git worktree to inspect.")
    parser.add_argument(
        "--map",
        type=Path,
        default=Path(__file__).with_name("rename-map.json"),
        help="JSON file containing the reviewed renaming rules.",
    )
    parser.add_argument("--check-modules", action="store_true", help="Only report old module references.")
    parser.add_argument(
        "--report-docs", action="store_true", help="Only report old names in Markdown code and links."
    )
    parser.add_argument(
        "--module-allowlist",
        type=Path,
        default=Path(__file__).with_name("module-allowlist.json"),
    )
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
            return check_modules(root, rules, args.module_allowlist)
        if args.report_docs:
            report_docs(root, rules)
            return 0
        additions = (
            glossary_additions(root)
            if args.map.resolve() == Path(__file__).with_name("rename-map.json").resolve()
            else {}
        )
        additions.update(missing_redirects(root, rules))
        changes = build_plan(root, rules)
        if args.dry_run:
            report_untracked(root, rules)
        run(root, changes, additions, args.dry_run)
        if not args.dry_run:
            remove_empty_old_directories(root, changes, rules)
    except (OSError, ValueError, SyntaxError, tokenize.TokenError, csv.Error) as error:
        print(f"Naming update stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
