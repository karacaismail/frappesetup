"""Check the backend's AI readiness without importing application code."""

import argparse
import ast
import json
import re
import subprocess
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path

from contracts import operations
from forbidden_name import match_lines, redact_path, tracked_findings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guvenlik"))
from endpoints import definitions, frappe_names, is_whitelist  # noqa: E402

PROVIDERS = {
    "anthropic",
    "azure.ai.openai",
    "cohere",
    "google.genai",
    "google.generativeai",
    "groq",
    "langchain",
    "litellm",
    "mistralai",
    "ollama",
    "openai",
}
MODEL = re.compile(
    r"(?<![\w-])(?:gpt|claude|gemini|llama|mistral|mixtral|deepseek|qwen|command-r)"
    r"[-_:](?=[a-z0-9_.:-]*\d|(?:sonnet|haiku|opus|latest)\b)[a-z0-9][a-z0-9_.:-]*"
    r"|(?<![\w-])o[134](?:-mini|-preview|-pro)?(?![\w-])",
    re.IGNORECASE,
)
LAYOUT_FIELDS = {"Section Break", "Column Break", "Tab Break", "Fold", "Heading", "HTML"}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def module_name(path, root):
    parts = list(path.relative_to(root / "apps").with_suffix("").parts)
    if len(parts) > 1:
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    return ""


def import_names(node):
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.asname or alias.name.split(".")[0], alias.name
    elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
        for alias in node.names:
            yield alias.asname or alias.name, f"{node.module}.{alias.name}"


def sql_calls(node, aliases):
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            name = dotted(call.func)
            first, sep, rest = name.partition(".")
            if aliases.get(first, first) + sep + rest == "frappe.db.sql":
                yield call.lineno


def tool_references(node, keys):
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str) and not keys:
            if re.fullmatch(r"[\w]+(?:\.[\w]+)+", item.value):
                yield item.value
        if isinstance(item, ast.Dict) and keys:
            for key, value in zip(item.keys, item.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in keys
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    yield value.value


def doctype_checks(path, emit):
    source = path.read_text(encoding="utf-8")
    try:
        document = json.loads(source)
    except json.JSONDecodeError as error:
        emit(path, error.lineno, "input", "Invalid JSON file.")
        return
    if not isinstance(document, dict) or document.get("doctype") != "DocType":
        return
    if not has_text(document.get("description")):
        emit(path, 1, "doctype", "DocType description is missing.")
    fields = document.get("fields", [])
    if not isinstance(fields, list):
        emit(path, 1, "input", "DocType fields must be a list.")
        return
    for field in fields:
        if not isinstance(field, dict):
            emit(path, 1, "input", "DocType field must be an object.")
            continue
        if field.get("fieldtype") in LAYOUT_FIELDS or has_text(field.get("description")):
            continue
        fieldname = field.get("fieldname", "")
        key = re.search(r'"fieldname"\s*:\s*' + re.escape(json.dumps(fieldname)), source)
        line = source.count("\n", 0, key.start()) + 1 if key else 1
        emit(path, line, "doctype", f"Field {fieldname!r} needs a description.")


def ai_module_owners(root: Path) -> set[str]:
    """Resolve the owner of the public AI and MCP endpoints from repository policy."""
    dev = root / "dev"
    current = dev / "module-boundaries.json"
    policy = current if current.exists() else dev / "modul-sinirlari.json"
    if not policy.exists() and not (root / "apps/platform_core").exists():
        return set()
    data = json.loads(policy.read_text(encoding="utf-8"))
    owners = data.get("path_owners") if isinstance(data, dict) else None
    if not isinstance(owners, dict):
        raise ValueError("Module boundary policy has no path owners.")
    if (root / "apps/platform_core").exists() and not any(
        owners.get(endpoint) for endpoint in ("platform_core.api.ai", "platform_core.api.mcp")
    ):
        raise ValueError("Module boundary policy has no platform AI owner.")
    prefixes = {owner for endpoint, owner in owners.items() if endpoint.endswith((".api.ai", ".api.mcp"))}
    if any(not isinstance(prefix, str) or not prefix.strip() for prefix in prefixes):
        raise ValueError("Module boundary policy has an invalid AI owner.")
    return prefixes


def naming_findings(root: Path) -> list[Finding]:
    checker = root / "dev/naming/check_names.py"
    relative = checker.relative_to(root).as_posix()
    if not checker.exists():
        print("naming: not_run (checker unavailable)", file=sys.stderr)
        return []
    if not checker.is_file() or checker.resolve() != checker:
        return [Finding(relative, 1, "naming", "Naming checker must be a regular in-tree file.")]
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(checker), "--root", str(root.parent), "--json"],
            cwd=root.parent,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise ValueError("Naming checker returned an unexpected status.")
        records = json.loads(result.stdout)
        if not isinstance(records, list) or bool(records) != bool(result.returncode):
            raise ValueError("Naming checker returned inconsistent findings.")
        findings = []
        for record in records:
            path, line, rule, message = (record[key] for key in ("path", "line", "rule", "message"))
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
                or type(line) is not int
                or line < 1
                or not isinstance(rule, str)
                or not rule
                or not isinstance(message, str)
                or not message.strip()
            ):
                raise ValueError("Naming checker returned an invalid finding.")
            findings.append(Finding(path.removeprefix("backend/"), line, f"naming.{rule}", message))
        return findings
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired):
        return [Finding(relative, 1, "naming", "Naming checker could not complete.")]


def scan(root):
    findings = set()
    functions = {}
    endpoints = {}
    sources = {}
    registered = {}

    def emit(path, line, rule, message):
        findings.add(Finding(path.relative_to(root).as_posix(), line, rule, message))

    try:
        ai_owners = ai_module_owners(root)
    except (OSError, TypeError, ValueError):
        ai_owners = set()
        emit(root / "dev", 1, "input", "Could not resolve the AI module from boundary policy.")

    if not (root / "apps").is_dir():
        emit(root / "apps", 1, "input", "Backend apps directory is missing.")
    for path in sorted((root / "apps").rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            if path.suffix == ".json":
                doctype_checks(path, emit)
            if path.suffix != ".py":
                continue
            with tokenize.open(path) as stream:
                tree = ast.parse(stream.read(), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as error:
            emit(path, getattr(error, "lineno", None) or 1, "input", "Could not read or parse source.")
            continue

        module = module_name(path, root)
        modules, decorators, _ = frappe_names(tree)
        aliases = {}
        for item in ast.walk(tree):
            for alias, name in import_names(item):
                aliases[alias] = name if alias != name.split(".")[0] or "." not in name else alias
                if any(name == provider or name.startswith(provider + ".") for provider in PROVIDERS):
                    emit(path, item.lineno, "provider", f"Provider import is forbidden: {name}.")
        sources[module] = path, aliases
        for name, fn in definitions(tree):
            qualified = f"{module}.{name}"
            functions[qualified] = module, fn
            if any(is_whitelist(dec, modules | {"frappe"}, decorators) for dec in fn.decorator_list):
                endpoints[qualified] = path, fn.lineno

        is_test = (
            any(part in {"test", "tests"} for part in path.relative_to(root / "apps").parts)
            or path.stem.startswith("test_")
            or path.stem.endswith("_test")
        )
        for item in ast.walk(tree):
            if (
                path.name == "hooks.py"
                and isinstance(item, ast.Name)
                and isinstance(item.ctx, ast.Store)
                and item.id == "scheduler_events"
            ):
                emit(path, item.lineno, "scheduler", "Scheduler registration is forbidden.")
            if (
                not is_test
                and isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and MODEL.search(item.value)
            ):
                emit(path, item.lineno, "model", "Keep model names in the registry.")
        if path.name == "hooks.py":
            for item in tree.body:
                if isinstance(item, ast.Assign) and any(dotted(t) == "ai_tools" for t in item.targets):
                    registered.update((name, (path, item.lineno)) for name in tool_references(item.value, ()))
                if isinstance(item, ast.AnnAssign) and dotted(item.target) == "ai_tools" and item.value:
                    registered.update((name, (path, item.lineno)) for name in tool_references(item.value, ()))

        if not is_test and any(module == owner or module.startswith(f"{owner}.") for owner in ai_owners):
            for line in sql_calls(tree, aliases):
                emit(path, line, "sql", "Raw SQL is forbidden in AI tools.")
    targets = dict(registered)
    for name, location in registered.items():
        if name in functions:
            _, fn = functions[name]
            targets.update((target, location) for target in tool_references(fn, ("handler", "preview")))
    for target, (hook, line) in targets.items():
        if target not in functions:
            emit(hook, line, "sql", f"Cannot inspect registered AI tool {target}.")
            continue
        module, fn = functions[target]
        path, aliases = sources[module]
        for sql_line in sql_calls(fn, aliases):
            emit(path, sql_line, "sql", "Raw SQL is forbidden in AI tools.")

    contracted = set()
    for path in sorted((root / "contracts").glob("*.yaml")):
        if path.is_symlink():
            continue
        try:
            for name, line, missing in operations(path):
                contracted.add(name)
                if name not in endpoints:
                    emit(path, line, "endpoint", f"No whitelisted function for {name}.")
                for field in missing:
                    emit(path, line, "endpoint", f"{name} needs a non-empty {field}.")
        except (OSError, UnicodeError, ValueError) as error:
            emit(path, getattr(error, "lineno", 1), "endpoint", str(error))
    for name, (path, line) in endpoints.items():
        if name not in contracted:
            emit(path, line, "endpoint", f"Missing OpenAPI operation for {name}.")

    for path, line, message in tracked_findings(root):
        findings.add(Finding(path, line, "forbidden-name", message))
    findings.update(naming_findings(root))
    return sorted(findings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = [
        Finding(
            redact_path(finding.path),
            finding.line,
            finding.rule if next(match_lines([finding.rule]), None) is None else "redacted",
            finding.message if next(match_lines([finding.message]), None) is None else "Details redacted.",
        )
        for finding in scan(args.root.resolve())
    ]
    if args.json:
        print(json.dumps([asdict(finding) for finding in findings]))
    else:
        for finding in findings:
            print(f"{finding.path}:{finding.line} [{finding.rule}] {finding.message}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
