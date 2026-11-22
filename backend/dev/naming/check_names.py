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
import unicodedata
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
TURKISH_WORD = re.compile(
    r"\b(?:acik|aciklamasi|alan|baslik|belge|cihaz|degisiklik|durum|esitleme|gecerli|"
    r"giris|getir|hesap|islem|izin|kapali|kaydi|kayit|kimlik|kullanici|onay|parola|"
    r"saglayici|secenek|tanim|uygulama|yapin|yok|yetki)\b",
    re.IGNORECASE,
)
COPY_KEYS = {"label", "description", "title"}
MARKDOWN_CODE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)
SOURCE_SKIP = {
    "tests",
    "test",
    "testdata",
    "test_data",
    "test-data",
    "__tests__",
    "fixtures",
    "locale",
    "translations",
    "__snapshots__",
}
PYTHON_COPY_CALLS = {"frappe._", "__", "frappe.throw", "frappe.msgprint", "msgprint"}
JSON_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
JS_STRING = r"""(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|`(?:\\.|[^`\\])*`)"""
JS_REGEX = (
    r"(?:(?<=[({=,:;!?])|(?<=return)|(?<=throw))\s*/(?![/*])"
    r"(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\[\r\n])+/[a-z]*"
)
JS_TOKENS = re.compile(
    rf"//[^\n]*|/\*[\s\S]*?\*/|{JS_REGEX}|{JS_STRING}|"
    r"(?P<call>(?<![\w$.])(?:__|frappe\._|frappe\.throw|(?:frappe\.)?msgprint)\s*\(\s*)"
)
CODE_TOKEN = re.compile(rf"//[^\n]*|/\*[\s\S]*?\*/|{JS_REGEX}|{JS_STRING}|(?P<identifier>[^\W\d]\w*)")
HTML_TAG = re.compile(rf"""<!--[\s\S]*?-->|</?[A-Za-z][\w:-]*(?:[^<>'"`]|{JS_STRING})*>""")
HTML_ATTRIBUTE = re.compile(r"""\s(?P<key>[\w:-]+)\s*=\s*(["'])(?P<name>.*?)\2""", re.DOTALL)
SCRIPT_SUFFIXES = {".js", ".jsx", ".mjs", ".ts", ".tsx"}
MARKUP_SUFFIXES = {".html", ".htm", ".ftl", ".jinja", ".jinja2", ".j2", ".vue", ".astro", ".jsx", ".tsx"}
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


def load_json(source: str):
    def object_from_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key.")
            result[key] = value
        return result

    def reject_constant(_constant):
        raise ValueError("Non-finite JSON number.")

    return json.loads(source, object_pairs_hook=object_from_pairs, parse_constant=reject_constant)


def glossary_fields(path: Path):
    """Read flat glossary entries without accepting ambiguous mapping keys."""
    if not path.is_file() or path.is_symlink():
        return
    entry_indent = None
    fields = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        content = line.lstrip(" \t")
        if not content or content.startswith("#"):
            continue
        indentation = line[: len(line) - len(content)]
        if "\t" in indentation:
            raise ValueError(f"{path}:{number}: YAML indentation must use spaces.")
        indent = len(indentation)
        item = re.match(r"^-( +|$)", content)
        if item and (entry_indent is None or indent < entry_indent):
            entry_indent = indent + len(item[0]) if item[0] != "-" else indent + 2
            fields.clear()
            content = content[item.end() :]
        elif entry_indent is not None and indent != entry_indent:
            continue
        match = re.fullmatch(r"""(["']?)([A-Za-z_][\w-]*)\1:\s*(.*?)\s*""", content)
        if not match:
            continue
        _, name, field_value = match.groups()
        if name in fields:
            raise ValueError(f"{path}:{number}: Duplicate YAML key {name!r}.")
        fields.add(name)
        yield name, field_value


def read_glossary(path: Path) -> tuple[set[str], set[str]]:
    doctype_names = set()
    avoid = set()
    for name, value in glossary_fields(path):
        if name == "doctype":
            doctype_names.add(value.strip("\"'"))
        elif name == "avoid":
            if not value.startswith("[") or not value.endswith("]"):
                raise ValueError(f"Expected an inline avoid list in {path.name}.")
            avoid.update(word.strip().strip("\"'") for word in value[1:-1].split(",") if word.strip())
    return doctype_names, avoid


def name_rules(entries: list[dict]) -> dict[str, list[dict]]:
    names: dict[str, list[dict]] = {}
    for entry in entries:
        if entry["type"] != "path":
            names.setdefault(entry["old"], []).append(entry)
    return names


def name_words(spelling: str) -> set[str]:
    latin = unicodedata.normalize("NFKD", spelling.translate(str.maketrans({"ı": "i", "İ": "I"})))
    latin = "".join(letter for letter in latin if not unicodedata.combining(letter))
    latin = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", latin)
    latin = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", latin)
    return set(re.findall(r"[a-z]+", latin.lower()))


def turkish_roots(entries: list[dict], glossaries: list[Path]) -> set[str]:
    candidates = set()
    english_names = set()
    for entry in entries:
        english_names.update(name_words(entry["new"]))
        if entry["type"] in {"identifier", "module"} and re.fullmatch(r"[\w .-]+", entry["old"]):
            candidates.update(name_words(entry["old"]))
    for glossary in glossaries:
        for name, value in glossary_fields(glossary):
            if name == "term_tr":
                candidates.update(name_words(value))
            elif name == "code":
                english_names.update(name_words(value))
    return {
        candidate
        for candidate in candidates - english_names
        if len(candidate) >= 3 and candidate not in {"break", "hrms", "keycloak", "kid", "ttl", "var", "yz"}
    }


def has_turkish_root(spelling: str, roots: set[str]) -> bool:
    words = name_words(spelling)
    return bool(words & roots or any(TURKISH_WORD.fullmatch(word) for word in words))


def replacement(names: dict[str, list[dict]], name: str, path: str, kinds: set[str]) -> str:
    for entry in names.get(name, []):
        if entry["type"] in kinds and (
            not entry.get("paths") or any(fnmatchcase(path, scope) for scope in entry["paths"])
        ):
            return entry["new"]
    return name


def json_records(path: Path):
    content = load_json(path.read_text(encoding="utf-8"))
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


def check_python(path: Path, relative: str, avoid: set[str], names, roots, legacy: bool, emit) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as error:
        emit(path, "syntax", "Python source could not be parsed.", error.lineno or 1)
        return
    bindings = set(python_bindings(tree))
    attributes = {(node.attr, node.lineno) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    reserves_translation_name = relative.startswith("backend/apps/") or any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "frappe"
        or isinstance(node, ast.Import)
        and any(alias.name.split(".")[0] == "frappe" for alias in node.names)
        for node in ast.walk(tree)
    )
    for binding, line in sorted(bindings | attributes, key=lambda pair: (pair[1], pair[0])):
        attribute = (binding, line) not in bindings
        mapped = replacement(names, binding, relative, {"identifier"})
        if binding == "_" and (attribute or not reserves_translation_name):
            continue
        if binding == "_":
            emit(path, "translation-binding", "The name '_' is reserved for translation.", line)
        elif not legacy and mapped != binding:
            emit(path, "legacy-name", f"Replace the mapped legacy name {binding!r}.", line)
        elif not binding.isascii():
            emit(path, "python-name", f"Python name {binding!r} must use ASCII.", line)
        elif (not legacy or binding == mapped) and has_turkish_root(binding, roots):
            emit(path, "turkish-name", f"Use an English name in place of {binding!r}.", line)
        elif not attribute and (
            binding in avoid or binding in DISCOURAGED or TEMPORARY_SUFFIX.search(binding)
        ):
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


def check_doctype_copy(path: Path, record: dict, roots: set[str], emit) -> None:
    if record.get("doctype") != "DocType":
        return
    fields = [record, *(record.get("fields") or [])]
    for field in fields:
        if not isinstance(field, dict):
            continue
        for key in COPY_KEYS:
            copy_text = field.get(key)
            if isinstance(copy_text, str):
                prose = MARKDOWN_CODE.sub(" ", copy_text)
                if turkish_text(prose) or has_turkish_root(prose, roots):
                    fieldname = field.get("fieldname", record.get("name"))
                    emit(path, "doctype-copy", f"English source text required for {fieldname!r} {key}.")


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


def changed_files(root: Path, base: str) -> set[str]:
    outputs = []
    for args in (
        ("diff", "--name-only", "-z", "--diff-filter=ACMRTUXB", base, "--", "backend/"),
        ("ls-files", "--others", "--exclude-standard", "-z", "--", "backend/"),
    ):
        response = subprocess.run(
            ["git", "-C", str(root), *args], text=True, capture_output=True, check=False
        )
        if response.returncode:
            raise ValueError(f"Could not list changes from {base!r} in this Git worktree.")
        outputs.extend(response.stdout.split("\0"))
    return {name for name in outputs if name}


def web_names(source: str, suffix: str):
    if suffix in SCRIPT_SUFFIXES:
        for match in CODE_TOKEN.finditer(source):
            if token := match["identifier"]:
                yield token, source.count("\n", 0, match.start()) + 1
    if suffix in MARKUP_SUFFIXES:
        for tag in HTML_TAG.finditer(source):
            if tag[0].startswith("<!--"):
                continue
            for attribute in HTML_ATTRIBUTE.finditer(tag[0]):
                if attribute["key"].lower() not in {"id", "class", "classname"}:
                    continue
                if any(symbol in attribute["name"] for symbol in ("{", "<", "$", "%")):
                    continue
                for html_name in attribute["name"].split():
                    yield html_name, source.count("\n", 0, tag.start() + attribute.start("name")) + 1


def check_web(path, relative, roots, names, legacy, emit):
    source = path.read_text(encoding="utf-8")
    for spelling, line in set(web_names(source, path.suffix)):
        mapped = replacement(names, spelling, relative, {"identifier", "reference"})
        if not legacy and mapped != spelling:
            emit(path, "legacy-name", f"Replace the mapped legacy name {spelling!r}.", line)
        elif not spelling.isascii() or mapped == spelling and has_turkish_root(spelling, roots):
            emit(path, "turkish-name", f"Use an English ASCII name in place of {spelling!r}.", line)


def scan(
    root: Path, *, legacy: bool = False, map_path: Path = DEFAULT_MAP, selected: set[str] | None = None
) -> list[Finding]:
    """Return sorted violations. Legacy mode recognizes mapped pre-transition names."""
    root = normalized_root(root)
    backend = root / "backend"
    if not backend.is_dir():
        return []
    findings = []

    def emit(path, rule, message, line=1):
        relative = path.relative_to(root).as_posix()
        if selected is None or relative in selected:
            findings.append(Finding(relative, line, rule, message))

    entries = load_json(map_path.read_text(encoding="utf-8"))
    names = name_rules(entries)
    files = tree_files(root)
    if selected is not None:
        files = sorted(
            set(files) | {root / name for name in selected},
            key=lambda path: (path.relative_to(root).as_posix() in selected, path),
        )
    glossaries = [path for path in files if path.name == "glossary.yaml"]
    roots = turkish_roots(entries, glossaries)
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
        if selected is not None and relative.as_posix() not in selected:
            continue
        if not path.is_file() or path.is_symlink() or relative.parts[:3] == ("backend", "dev", "naming"):
            continue
        if path.suffix in SCRIPT_SUFFIXES | MARKUP_SUFFIXES:
            check_web(path, relative.as_posix(), roots, names, legacy, emit)
        elif path.suffix == ".py" and relative.parts[:2] != ("backend", "apps"):
            check_python(path, relative.as_posix(), set(), names, roots, legacy, emit)

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
        for path in sources:
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix == ".py":
                if selected is None or relative in selected:
                    check_python(path, relative, avoid, names, roots, legacy, emit)
            elif path.suffix == ".json" and JSON_RECORD_FOLDERS.intersection(path.relative_to(app).parts):
                try:
                    records = list(json_records(path))
                except ValueError:
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
                    if selected is None or relative in selected:
                        check_doctype_copy(path, record, roots, emit)
    if selected is None:
        check_branch(root, entries, emit)
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule, finding.message))


def turkish_text(value: str) -> bool:
    value = MARKDOWN_CODE.sub(" ", value)
    value = re.sub(r"\{[\w.]+\}", "", value)
    return bool(TURKISH_LETTER.search(value) or TURKISH_WORD.search(value))


def json_source_text(source: str, keys: set[str], *, doctype: bool):
    document = load_json(source)
    if doctype and (not isinstance(document, dict) or document.get("doctype") != "DocType"):
        return
    positions = iter(
        match.start()
        for match in JSON_STRING.finditer(source)
        if source[match.end() :].lstrip().startswith(":")
    )

    def walk(node):
        if isinstance(node, list):
            for element in node:
                yield from walk(element)
        elif isinstance(node, dict):
            for key, field in node.items():
                line = source.count("\n", 0, next(positions)) + 1
                if isinstance(field, str):
                    if key in keys:
                        yield line, key, field
                    elif doctype and key == "options" and node.get("fieldtype") == "Select":
                        for option in field.splitlines():
                            yield line, "Select option", option
                yield from walk(field)

    yield from walk(document)


def python_source_text(source: str, path: Path):
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
            name = f"{function.value.id}.{function.attr}"
        elif isinstance(function, ast.Name):
            name = function.id
        else:
            continue
        if name not in PYTHON_COPY_CALLS:
            continue
        message = (
            node.args[0]
            if node.args
            else next((keyword.value for keyword in node.keywords if keyword.arg in {"msg", "message"}), None)
        )
        if isinstance(message, ast.Constant) and isinstance(message.value, str):
            yield message.lineno, name, message.value
        elif isinstance(message, ast.JoinedStr):
            value = "".join(
                part.value if isinstance(part, ast.Constant) else "{…}" for part in message.values
            )
            yield message.lineno, name, value


def js_source_text(source: str):
    for match in JS_TOKENS.finditer(source):
        if not match["call"]:
            continue
        literal = re.compile(JS_STRING).match(source, match.end())
        if literal:
            value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda item: chr(int(item[1], 16)), literal[0][1:-1])
            value = re.sub(r"\$\{[^}]*\}", "{…}", value)
            yield source.count("\n", 0, literal.start()) + 1, match["call"].partition("(")[0].strip(), value


def yaml_source_text(source: str):
    lines = source.splitlines()
    key_pattern = re.compile(r"""^( *)(?:- +)?["']?(summary|description)["']?:\s*(.*)$""")
    consumed = 0
    for index, line in enumerate(lines):
        if index < consumed:
            continue
        heading = key_pattern.match(line)
        if not heading:
            continue
        indent, key, value = heading.groups()
        position = index + 1
        if value.startswith(("|", ">")):
            chunks = []
            for offset, following in enumerate(lines[index + 1 :], start=index + 2):
                if not following.strip():
                    continue
                if len(following) - len(following.lstrip()) <= len(indent):
                    break
                if position == index + 1 and turkish_text(following):
                    position = offset
                chunks.append(following.strip())
                consumed = offset
            value = " ".join(chunks)
        else:
            token = re.match(JS_STRING, value) if value.startswith(("'", '"')) else None
            value = token[0][1:-1] if token else re.split(r"\s+#", value, maxsplit=1)[0]
        yield position, key, value


def scan_source_text(root: Path, selected: set[str] | None = None) -> list[Finding]:
    root = normalized_root(root)
    findings = []
    paths = tree_files(root) if selected is None else sorted(root / name for name in selected)
    for path in paths:
        relative = path.relative_to(root)
        if path.is_symlink() or not path.is_file() or SOURCE_SKIP.intersection(relative.parts):
            continue
        if path.stem.startswith("test_") or path.stem.endswith(("_test", ".test", ".spec", "_fixture")):
            continue
        contract = len(relative.parts) > 2 and relative.parts[1] == "contracts"
        if path.suffix == ".json" and ("doctype" in relative.parts or contract):
            keys = {"summary", "description"} if contract else COPY_KEYS
            texts = json_source_text(path.read_text(encoding="utf-8"), keys, doctype=not contract)
        elif path.suffix in {".yaml", ".yml"} and contract:
            texts = yaml_source_text(path.read_text(encoding="utf-8"))
        elif path.suffix == ".py":
            texts = python_source_text(path.read_text(encoding="utf-8"), path)
        elif path.suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs"}:
            texts = js_source_text(path.read_text(encoding="utf-8"))
        else:
            continue
        for line, field, value in texts:
            if turkish_text(value):
                example = " ".join(value.split())
                if len(example) > 100:
                    example = example[:97] + "..."
                findings.append(Finding(relative.as_posix(), line, "source-text", f"{field}: {example}"))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.message))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--legacy", action="store_true", help="Recognize explicitly mapped legacy names.")
    mode.add_argument("--source-text", action="store_true", help="Find Turkish in visible source text.")
    mode.add_argument(
        "--transition",
        action="store_true",
        help="Fail only for mapped legacy names; show other findings as warnings.",
    )
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--changed-files",
        nargs="?",
        const="HEAD",
        metavar="BASE",
        help="Only report changed backend files relative to BASE (default: HEAD).",
    )
    arguments = parser.parse_args()
    try:
        selection = (
            changed_files(normalized_root(arguments.root), arguments.changed_files)
            if arguments.changed_files
            else None
        )
        if arguments.source_text:
            findings = scan_source_text(arguments.root, selection)
        else:
            findings = scan(
                arguments.root, legacy=arguments.legacy, map_path=arguments.map, selected=selection
            )
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(2, f"Naming check could not finish: {error}\n")
    if arguments.json:
        print(json.dumps([asdict(finding) for finding in findings]))
    else:
        for finding in findings:
            level = ""
            if arguments.transition:
                level = "Error: " if finding.rule == "legacy-name" else "Warning: "
            print(f"{level}{finding.path}:{finding.line} [{finding.rule}] {finding.message}")
    if arguments.transition:
        return int(any(finding.rule == "legacy-name" for finding in findings))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
