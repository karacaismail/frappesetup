"""Check Frappe application names without importing Frappe.

The glossary reader accepts the repository's YAML subset: plain or quoted
`doctype` scalars and inline `avoid` lists. Checks which need a live site belong
to the application integration tests.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from pathlib import Path

APP_PREFIXES = {"platform_core": "PLT", "press_tr": "PTR", "hrms_tr": "HRT"}
RECORD_KINDS = {"DocType", "Report", "Role", "Workspace", "Print Format"}
JSON_RECORD_FOLDERS = {"doctype", "report", "workspace", "print_format", "role", "fixtures", "custom"}
FIELD_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
RECORD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 _-]{0,60}")
MODULE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*(?: [A-Za-z][A-Za-z0-9]*)*")
TURKISH_LETTER = re.compile(r"[çÇğĞıİöÖşŞüÜ]")
DISCOURAGED = set(
    "data info item obj value result temp tmp stuff misc manager helper utils handler process".split()
)
TEMPORARY_SUFFIX = re.compile(r"_(?:new|old|v2|temp|final|backup|2)$")
BRANCH_FORMAT = re.compile(r"(?:feat|fix|chore|docs|refactor|test)/[a-z0-9]+(?:-[a-z0-9]+)*")
DEFAULT_MAP = Path(__file__).with_name("rename-map.json")
NAMED_BINDINGS = (
    ast.ExceptHandler,
    *(getattr(ast, name) for name in ("MatchAs", "MatchStar") if hasattr(ast, name)),
)
MAPPING_PATTERN = getattr(ast, "MatchMapping", ())


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str


def scrub(name: str) -> str:
    """Match Frappe 16's on-disk module and controller naming."""
    return name.replace(" ", "_").replace("-", "_").lower()


def git_output(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments], text=True, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else ""


def tree_files(root: Path) -> list[Path]:
    tracked = git_output(root, "ls-files", "-z", "--", "backend/")
    if tracked or git_output(root, "rev-parse", "--show-toplevel"):
        return [root / name for name in tracked.split("\0") if name]
    backend = root / "backend"
    return [path for path in backend.rglob("*") if path.is_file()]


def read_glossary(path: Path) -> tuple[set[str], set[str]]:
    if not path.is_file():
        return set(), set()
    doctype_names = set()
    avoid = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"(?:\s+|- )(doctype|avoid):\s*(.*?)\s*", line)
        if not match:
            continue
        name, value = match.groups()
        if name == "doctype":
            doctype_names.add(value.strip("\"'"))
        elif value.startswith("[") and value.endswith("]"):
            avoid.update(word.strip().strip("\"'") for word in value[1:-1].split(",") if word.strip())
        else:
            raise ValueError(f"Expected an inline avoid list in {path.name}.")
    return doctype_names, avoid


def name_rules(entries: list[dict]) -> dict[str, list[dict]]:
    names: dict[str, list[dict]] = {}
    for entry in entries:
        if entry["type"] != "path":
            names.setdefault(entry["old"], []).append(entry)
    return names


def replacement(names: dict[str, list[dict]], name: str, path: str, kinds: set[str]) -> str:
    for entry in names.get(name, []):
        if entry["type"] in kinds and (
            not entry.get("paths") or any(fnmatchcase(path, scope) for scope in entry["paths"])
        ):
            return entry["new"]
    return name


def json_records(path: Path):
    content = json.loads(path.read_text(encoding="utf-8"))
    records = content if isinstance(content, list) else [content]
    for record in records:
        if not isinstance(record, dict):
            continue
        yield record
        yield from (
            {"doctype": "Custom Field", **field}
            for field in record.get("custom_fields") or []
            if isinstance(field, dict)
        )


def python_bindings(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.id, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, NAMED_BINDINGS) and node.name:
            yield node.name, node.lineno
        elif isinstance(node, MAPPING_PATTERN) and node.rest:
            yield node.rest, node.lineno
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.asname and (
                    not isinstance(node, ast.ImportFrom) or node.module != "frappe" or alias.name != "_"
                ):
                    yield alias.asname, node.lineno


def check_python(path: Path, relative: str, avoid: set[str], names, legacy: bool, emit) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as error:
        emit(path, "syntax", "Python source could not be parsed.", error.lineno or 1)
        return
    for binding, line in sorted(set(python_bindings(tree)), key=lambda pair: (pair[1], pair[0])):
        if binding == "_":
            emit(path, "translation-binding", "The name '_' is reserved for translation.", line)
        elif not binding.isascii():
            emit(path, "python-name", f"Python name {binding!r} must use ASCII.", line)
        elif not legacy and replacement(names, binding, relative, {"identifier"}) != binding:
            emit(path, "legacy-name", f"Replace the mapped legacy name {binding!r}.", line)
        elif binding in avoid or binding in DISCOURAGED or TEMPORARY_SUFFIX.search(binding):
            emit(path, "discouraged-name", f"Use a descriptive name in place of {binding!r}.", line)


def check_record(path, record, prefix, modules, glossary, mapped_names, doctype_paths, emit):
    kind = record.get("doctype")
    name = record.get("name")
    if kind == "Role":
        name = record.get("role_name", name)
    if kind in RECORD_KINDS:
        if not isinstance(name, str) or not RECORD_NAME.fullmatch(name):
            emit(path, "record-name", f"{kind} name must use the supported ASCII format.")
        elif prefix and not mapped_names.get(name, name).startswith(prefix + " "):
            emit(path, "record-prefix", f"{kind} name {name!r} must start with {prefix!r}.")

    if kind == "DocType":
        module = record.get("module")
        if not isinstance(module, str) or module not in modules:
            emit(path, "module-match", "DocType module must match a line in modules.txt exactly.")
        if isinstance(name, str):
            scrubbed = scrub(name)
            previous = doctype_paths.setdefault(scrubbed, (name, path))
            if previous[1] != path:
                emit(path, "doctype-collision", f"DocType {name!r} collides with {previous[0]!r}.")
            if mapped_names.get(name, name) not in glossary:
                emit(path, "glossary", f"DocType {name!r} is missing from docs/glossary.yaml.")
        for field in record.get("fields") or []:
            if not isinstance(field, dict):
                continue
            fieldname = field.get("fieldname")
            if not isinstance(fieldname, str) or not FIELD_NAME.fullmatch(fieldname):
                emit(path, "field-name", f"Invalid DocType field name: {fieldname!r}.")
            source_text = (field.get(key) for key in ("label", "description"))
            if any(isinstance(text, str) and TURKISH_LETTER.search(text) for text in source_text):
                emit(path, "doctype-copy", f"English source text required for field {fieldname!r}.")
            check_select(path, field, emit)

    if kind == "Custom Field":
        fieldname = record.get("fieldname")
        expected = "custom_" + prefix.lower() + "_" if prefix else "custom_"
        canonical = mapped_names.get(fieldname, fieldname) if isinstance(fieldname, str) else None
        if not (
            isinstance(canonical, str) and FIELD_NAME.fullmatch(canonical) and canonical.startswith(expected)
        ):
            emit(path, "custom-field", f"Custom Field name must start with {expected!r}.")
        check_select(path, record, emit)

    states = []
    if kind == "Workflow State":
        states.append(record.get("workflow_state_name", name))
    elif kind == "Workflow":
        for state in record.get("states") or []:
            if isinstance(state, dict):
                states.append(state.get("state"))
        for transition in record.get("transitions") or []:
            if isinstance(transition, dict):
                states.extend((transition.get("state"), transition.get("next_state")))
    if any(not isinstance(state, str) or not RECORD_NAME.fullmatch(state) for state in states):
        emit(path, "workflow-state", "Workflow state names must use the supported ASCII format.")


def check_select(path, field, emit):
    if field.get("fieldtype") != "Select":
        return
    options = field.get("options") or ""
    if not isinstance(options, str) or any(not option.isascii() for option in options.splitlines()):
        emit(path, "select-name", "Select options must use ASCII.")


def normalized_root(root: Path) -> Path:
    root = root.resolve()
    return root.parent if root.name == "backend" and not (root / "backend").is_dir() else root


def check_branch(root: Path, entries: list[dict], emit) -> None:
    branch = git_output(root, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    if not branch or BRANCH_FORMAT.fullmatch(branch):
        return
    # Existing operational names and Pane jobs use their exact registered name.
    backend = root / "backend"
    registered = {"main", "backend", "e2e-preview", "standartlar-ve-kararlar", "site-hrms-tr-rename"}
    registered.update(
        path.stem for folder in ("docs/isler", "docs/tasks") for path in (backend / folder).glob("*.md")
    )
    registered.update(
        Path(entry["old"]).stem
        for entry in entries
        if entry["type"] == "path"
        and entry["old"].startswith("backend/docs/isler/")
        and (root / entry["new"]).is_file()
    )
    if branch not in registered and not re.fullmatch(r"_reserve/[0-9a-f]+", branch):
        emit(backend, "branch-name", "Branch name does not match the project naming pattern.")


def scan(root: Path, *, legacy: bool = False, map_path: Path = DEFAULT_MAP) -> list[Finding]:
    """Return sorted violations. Legacy mode recognizes mapped pre-transition names."""
    root = normalized_root(root)
    backend = root / "backend"
    if not backend.is_dir():
        return []
    findings = []

    def emit(path, rule, message, line=1):
        findings.append(Finding(path.relative_to(root).as_posix(), line, rule, message))

    entries = json.loads(map_path.read_text(encoding="utf-8"))
    names = name_rules(entries)
    files = tree_files(root)
    paths_by_fold = {}
    app_files = {}
    for path in files:
        relative = path.relative_to(root)
        canonical = relative.as_posix().casefold()
        previous = paths_by_fold.setdefault(canonical, path)
        if previous != path:
            emit(path, "path-collision", f"Case-insensitive collision with {previous.relative_to(root)}.")
        if relative.parts[:2] == ("backend", "apps") and len(relative.parts) > 3:
            app_files.setdefault(relative.parts[2], []).append(path)

    doctype_paths = {}
    for app_name, sources in app_files.items():
        app = backend / "apps" / app_name
        prefix = APP_PREFIXES.get(app_name)
        module_file = app / app_name / "modules.txt"
        module_lines = module_file.read_text(encoding="utf-8").splitlines() if module_file.is_file() else []
        modules = {line.strip() for line in module_lines if line.strip()}
        for module in sorted(modules):
            preferred = replacement(names, module, module_file.relative_to(root).as_posix(), {"module"})
            if not MODULE_NAME.fullmatch(preferred) or (not legacy and module != preferred):
                emit(module_file, "module-name", f"Invalid module name: {module!r}.")
        glossary_path = app / "docs/glossary.yaml"
        if legacy and not glossary_path.is_file():
            glossary_path = backend / "dev/naming/glossaries" / app_name / "docs/glossary.yaml"
        glossary, avoid = read_glossary(glossary_path)
        for path in sorted(sources):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix == ".py":
                check_python(path, relative, avoid, names, legacy, emit)
            elif path.suffix == ".json" and JSON_RECORD_FOLDERS.intersection(path.relative_to(app).parts):
                try:
                    records = list(json_records(path))
                except (UnicodeError, json.JSONDecodeError):
                    emit(path, "json", "Frappe metadata is not a readable JSON file.")
                    continue
                for record in records:
                    mapped_names = {}
                    if legacy:
                        for field in ("name", "role_name", "fieldname"):
                            value = record.get(field)
                            if isinstance(value, str):
                                mapped_names[value] = replacement(
                                    names,
                                    value,
                                    relative,
                                    {"doctype", "reference", "identifier"},
                                )
                    check_record(path, record, prefix, modules, glossary, mapped_names, doctype_paths, emit)
    check_branch(root, entries, emit)
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule, finding.message))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--legacy", action="store_true", help="Recognize explicitly mapped legacy names.")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        findings = scan(arguments.root, legacy=arguments.legacy, map_path=arguments.map)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Naming check could not finish: {error}\n")
    if arguments.json:
        print(json.dumps([asdict(finding) for finding in findings]))
    else:
        for finding in findings:
            print(f"{finding.path}:{finding.line} [{finding.rule}] {finding.message}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
