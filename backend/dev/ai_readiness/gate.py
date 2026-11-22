"""Check the backend's AI readiness without importing application code."""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path

from contracts import METHOD_PATH, operations
from forbidden_name import find_path_code, match_lines, redact_path, tracked_findings
from source import (
    FUNCTIONS,
    assignments,
    declaration_targets,
    imports,
    mapping,
    qualified,
    resolve,
    scope_nodes,
    sql_calls,
    stable_bindings,
    string,
    walk,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guvenlik"))
from endpoints import definitions, frappe_names, is_whitelist  # noqa: E402

PROVIDERS = {
    "anthropic",
    "azure.ai.openai",
    "cohere",
    "genai",
    "google.genai",
    "google.generativeai",
    "groq",
    "huggingface_hub",
    "langchain",
    "litellm",
    "llama_index",
    "mistralai",
    "ollama",
    "openai",
    "replicate",
    "together",
    "transformers",
    "vertexai",
}
MODEL = re.compile(
    r"(?<![\w-])(?:gpt|claude|gemini|llama|mistral|mixtral|deepseek|qwen)"
    r"(?:[0-9][a-z0-9_.:-]*|[-_:](?=[a-z0-9_.:-]*[0-9])[a-z0-9][a-z0-9_.:-]*"
    r"|[-_](?:[a-z0-9]+[-_])*(?:sonnet|haiku|opus|latest)\b)"
    r"|(?<![\w-])command-r(?:-plus)?(?![\w-])"
    r"""|(?<![\w-])o[134](?:-mini|-preview|-pro)(?![\w-])|(?<=['"])o[134](?=['"])""",
    re.IGNORECASE,
)
LAYOUT_FIELDS = {"Section Break", "Column Break", "Tab Break"}
MODEL_ASSETS = {
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".sql",
    ".toml",
}


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


def source_files(directory, emit):
    def unreadable(error):
        emit(Path(error.filename), 1, "input", "Could not list source directory.")

    if directory.is_symlink():
        emit(directory, 1, "input", "Cannot inspect symbolic link.")
        return
    for current, folders, files in os.walk(directory, onerror=unreadable):
        base = Path(current)
        folders[:] = sorted(name for name in folders if not name.startswith(".") and name != "node_modules")
        for name in [*folders, *sorted(files)]:
            path = base / name
            if path.is_symlink():
                emit(path, 1, "input", "Cannot inspect symbolic link.")
            elif name in files and path.is_file():
                yield path


def matches(name, prefix):
    return name == prefix or name.startswith(prefix + ".")


def test_module(module):
    return any(part in {"test", "tests"} or part.startswith("test_") for part in module.split("."))


def imported_aliases(nodes, package):
    aliases = {}
    for item in nodes:
        for alias, name in imports(item, package):
            if not isinstance(item, ast.Import) or "." not in name or alias != name.split(".")[0]:
                aliases[alias] = name
    return aliases


def test_classes(sources):
    bases = {
        "unittest.TestCase",
        "unittest.IsolatedAsyncioTestCase",
        "frappe.tests.utils.FrappeTestCase",
        "frappe.tests.FrappeTestCase",
        "frappe.tests.IntegrationTestCase",
        "frappe.tests.UnitTestCase",
    }
    classes = {}
    for module, (_, _, tree, _, _, package) in sources.items():
        aliases = imported_aliases(scope_nodes(tree.body), package)
        for item in tree.body:
            if isinstance(item, ast.ClassDef):
                parents = set()
                for base in item.bases:
                    name = qualified(base, aliases)
                    if isinstance(base, ast.Name) and name == base.id:
                        name = f"{module}.{name}"
                    parents.add(name)
                classes[f"{module}.{item.name}"] = (module, item, parents)
    tests = {}
    while new := {
        name: (module, item)
        for name, (module, item, parents) in classes.items()
        if name not in bases and parents & bases
    }:
        bases.update(new)
        for module, item in new.values():
            tests.setdefault(module, set()).add(item)
    return tests


def model_checks(path, source, emit, excluded=(), tree=None):
    intervals = [(item.lineno, item.end_lineno) for item in excluded]
    for line, text in enumerate(source.splitlines(), 1):
        if any(first <= line <= last for first, last in intervals):
            continue
        if MODEL.search(text):
            emit(path, line, "model", "Keep model names in the registry.")
    if tree is not None:
        for item in walk(tree, excluded):
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                if MODEL.search(f'"{item.value}"'):
                    emit(path, item.lineno, "model", "Keep model names in the registry.")


def whitelist_checks(tree, bindings, module, path, emit):
    modules, decorators, _ = frappe_names(tree)

    def whitelisted(node):
        return any(is_whitelist(dec, modules | {"frappe"}, decorators) for dec in node.decorator_list)

    exposed = {}
    functions = dict(definitions(tree))
    for name, fn in list(functions.items()):
        if whitelisted(fn):
            exposed[f"{module}.{name}"] = path, fn.lineno
        nested = [
            item
            for item in ast.walk(fn)
            if item is not fn and isinstance(item, FUNCTIONS) and whitelisted(item)
        ]
        if nested:
            returned = {
                item.value.id
                for item in scope_nodes(fn.body)
                if isinstance(item, ast.Return) and isinstance(item.value, ast.Name)
            }
            exports = [
                (export, value)
                for export, value in bindings.items()
                if any(item.name in returned for item in nested)
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == name
            ]
            for export, value in exports:
                exposed[f"{module}.{export}"] = path, value.lineno
                functions[export] = fn
            if not exports:
                for item in nested:
                    emit(
                        path,
                        item.lineno,
                        "endpoint",
                        "Cannot resolve nested whitelisted function to a module export.",
                    )
    for name, value in bindings.items():
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Call)
            and is_whitelist(value.func, modules | {"frappe"}, decorators)
        ):
            exposed[f"{module}.{name}"] = path, value.lineno
    if test_module(module):
        for name, (_, line) in exposed.items():
            emit(path, line, "test-endpoint", f"Test function is whitelisted: {name}.")
    return functions, exposed


def runtime_whitelist_checks(tree, bindings, path, emit):
    modules, decorators, _ = frappe_names(tree)
    documented = set(bindings.values())
    for item in ast.walk(tree):
        if (
            isinstance(item, ast.Call)
            and item not in documented
            and isinstance(item.func, ast.Call)
            and is_whitelist(item.func, modules | {"frappe"}, decorators)
        ):
            emit(path, item.lineno, "endpoint", "Cannot resolve runtime whitelist registration.")


def doctype_checks(path, emit):
    source = path.read_text(encoding="utf-8")
    try:
        document = json.loads(source)
    except json.JSONDecodeError as error:
        emit(path, error.lineno, "input", "Invalid JSON file.")
        return
    records = document if isinstance(document, list) else [document]
    for record in records:
        if not isinstance(record, dict):
            continue
        record_type = record.get("doctype")
        if record_type in ("Auto Repeat", "Auto Email Report"):
            emit(path, 1, "scheduler", f"Scheduled {record_type} is forbidden.")
        elif record_type == "Server Script" and record.get("script_type") == "Scheduler Event":
            emit(path, 1, "scheduler", "Scheduled Server Script is forbidden.")
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


def boundary_policy(root):
    """Resolve the owner of the public AI and MCP endpoints from repository policy."""
    dev = root / "dev"
    current = dev / "module-boundaries.json"
    policy = current if current.exists() else dev / "modul-sinirlari.json"
    if not policy.exists() and not (root / "apps/platform_core").exists():
        return policy, {}, set()
    data = json.loads(policy.read_text(encoding="utf-8"))
    owners = data.get("path_owners") if isinstance(data, dict) else None
    if not isinstance(owners, dict):
        raise ValueError("Module boundary policy has no path owners.")
    if (root / "apps/platform_core").exists() and not any(
        owners.get(endpoint) for endpoint in ("platform_core.api.ai", "platform_core.api.mcp")
    ):
        raise ValueError("Module boundary policy has no platform AI owner.")
    ai_paths = {
        endpoint: owner for endpoint, owner in owners.items() if endpoint.endswith((".api.ai", ".api.mcp"))
    }
    if any(not isinstance(prefix, str) or not METHOD_PATH.fullmatch(prefix) for prefix in ai_paths.values()):
        raise ValueError("Module boundary policy has an invalid AI owner.")
    providers = data.get("forbidden_imports", [])
    if not isinstance(providers, list) or any(not has_text(name) for name in providers):
        raise ValueError("Module boundary policy has invalid forbidden imports.")
    return policy, ai_paths, set(providers)


def naming_findings(root: Path) -> list[Finding]:
    checker = root / "dev/naming/check_names.py"
    relative = checker.relative_to(root).as_posix()
    if not checker.exists() and not checker.is_symlink():
        return None
    if not checker.is_file() or checker.resolve() != checker:
        return [Finding(relative, 1, "naming", "Naming checker must be a regular in-tree file.")]
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(checker), "--root", str(root.parent), "--json"],
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


def hook_checks(path, tree, bindings, emit):
    if "scheduler_events" in bindings or any(
        isinstance(item, ast.Name)
        and isinstance(item.ctx, ast.Store)
        and item.id == "scheduler_events"
        or any(alias == "scheduler_events" for alias, _ in imports(item, "hooks"))
        for item in ast.walk(tree)
    ):
        emit(path, 1, "scheduler", "Scheduler registration is forbidden.")

    registrations = {}
    if "ai_tools" in bindings:
        value = resolve(bindings["ai_tools"], bindings)
        entries = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        for entry in entries:
            name = string(entry, bindings)
            if name and METHOD_PATH.fullmatch(name):
                registrations[name] = path, entry.lineno
            else:
                emit(path, entry.lineno, "sql", "Cannot resolve AI tool hook.")
    overrides = {}
    if "override_whitelisted_methods" in bindings:
        value = bindings["override_whitelisted_methods"]
        entries = mapping(value, bindings)
        if entries is None:
            emit(path, value.lineno, "endpoint", "Cannot resolve whitelist overrides.")
        for public, entry in (entries or {}).items():
            entries = entry.elts if isinstance(entry, (ast.List, ast.Tuple)) else [entry]
            for target in entries:
                name = string(target, bindings)
                if name and METHOD_PATH.fullmatch(name) and METHOD_PATH.fullmatch(public):
                    overrides[public] = name, path, target.lineno
                else:
                    emit(path, target.lineno, "endpoint", "Cannot resolve whitelist override target.")
    return registrations, overrides


def provider_checks(path, tree, package, aliases, bindings, providers, emit):
    for item in ast.walk(tree):
        names = [name for _, name in imports(item, package)]
        if isinstance(item, ast.Call) and qualified(item.func, aliases) in {
            "__import__",
            "builtins.__import__",
            "importlib.import_module",
            "frappe.get_attr",
            "frappe.get_module",
        }:
            argument = (
                item.args[0]
                if item.args
                else next((keyword.value for keyword in item.keywords if keyword.arg == "name"), None)
            )
            name = string(argument, bindings)
            if name:
                names.append(name)
        for name in names:
            if any(matches(name, provider) or name.startswith(provider + "_") for provider in providers):
                emit(path, item.lineno, "provider", f"Provider import is forbidden: {name}.")


def tool_sql_checks(targets, functions, sources, emit):
    pending = []
    for target, (hook, line) in targets.items():
        if target not in functions:
            emit(hook, line, "sql", f"Cannot inspect registered AI tool {target}.")
        else:
            pending.append(target)
    visited = set()
    referenced = set()
    while pending:
        target = pending.pop()
        if target in visited:
            continue
        visited.add(target)
        module, fn = functions[target]
        referenced.add(module)
        path, _, tree, _, _, package = sources[module]
        module_aliases = imported_aliases(scope_nodes(tree.body), package)
        local_nodes = list(scope_nodes(fn.body))
        local_aliases = imported_aliases(local_nodes, package)
        outer_aliases = module_aliases.copy()
        for item in tree.body:
            for name, value in assignments(item):
                owner = qualified(value, outer_aliases)
                if owner in {"frappe.db", "frappe.local.db"}:
                    outer_aliases[name] = owner
        for sql_line in sql_calls(walk(fn), outer_aliases | local_aliases):
            emit(path, sql_line, "sql", "Raw SQL is forbidden in AI tools.")
        app = module.partition(".")[0]
        for item in local_nodes:
            if not isinstance(item, ast.Call):
                continue
            name = qualified(item.func, module_aliases | local_aliases)
            if isinstance(item.func, ast.Name) and name == item.func.id:
                name = f"{module}.{name}"
            if name in functions and name.partition(".")[0] == app and name not in visited:
                pending.append(name)
    return referenced


def scan(root, commit_base=None):
    findings = set()
    functions = {}
    endpoints = {}
    sources = {}
    registered = {}
    overrides = {}
    referenced = set()
    providers = PROVIDERS

    def emit(path, line, rule, message):
        findings.add(Finding(path.relative_to(root).as_posix(), line, rule, message))

    try:
        policy, ai_paths, additional = boundary_policy(root)
        providers = providers | additional
    except (OSError, TypeError, ValueError):
        ai_paths = {}
        emit(root / "dev", 1, "input", "Could not resolve the AI module from boundary policy.")

    if not (root / "apps").is_dir():
        emit(root / "apps", 1, "input", "Backend apps directory is missing.")
    for path in source_files(root / "apps", emit):
        try:
            if path.suffix == ".json":
                doctype_checks(path, emit)
            if path.suffix in MODEL_ASSETS:
                model_checks(path, path.read_text(encoding="utf-8"), emit)
            if path.suffix != ".py":
                continue
            with tokenize.open(path) as stream:
                source = stream.read()
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError, ValueError) as error:
            emit(path, getattr(error, "lineno", None) or 1, "input", "Could not read or parse source.")
            continue

        module = module_name(path, root)
        package = module if path.stem == "__init__" else module.rpartition(".")[0]
        aliases = imported_aliases(ast.walk(tree), package)
        bindings = dict(pair for item in tree.body for pair in assignments(item))
        local, exposed = whitelist_checks(tree, bindings, module, path, emit)
        endpoints.update(exposed)
        if exposed:
            referenced.add(module)
        functions.update((f"{module}.{name}", (module, fn)) for name, fn in local.items())
        provider_checks(path, tree, package, aliases, bindings, providers, emit)
        sources[module] = path, source, tree, aliases, bindings, package
        if path.name == "hooks.py":
            hook_tools, hook_overrides = hook_checks(path, tree, bindings, emit)
            registered.update(hook_tools)
            overrides.update(hook_overrides)
            referenced.update(
                item.value
                for item in ast.walk(tree)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )

    for public, (target, path, line) in overrides.items():
        if target not in endpoints:
            emit(path, line, "endpoint", f"No whitelisted override target for {public}.")

    targets = dict(registered)
    for name, (hook, line) in registered.items():
        if name not in functions:
            continue
        module, fn = functions[name]
        path, _, tree, _, _, _ = sources[module]
        module_names = stable_bindings(tree.body)
        for target_line, target in declaration_targets(fn, module_names, METHOD_PATH):
            if target is None:
                emit(path, target_line, "sql", "Cannot resolve AI tool declaration target.")
            else:
                targets[target] = hook, line

    referenced.update(tool_sql_checks(targets, functions, sources, emit))

    for owner in set(ai_paths.values()):
        if not any(matches(module, owner) for module in sources):
            emit(policy, 1, "input", f"No Python source found for AI owner {owner}.")
    scopes = ai_paths.keys() | set(ai_paths.values())
    # Follow static imports transitively from production modules and exposed test modules.
    dependencies = {
        module: {name for item in ast.walk(tree) for _, name in imports(item, package)}
        for module, (_, _, tree, _, _, package) in sources.items()
    }
    production = {module for module in sources if not test_module(module)}
    for module in production:
        referenced.update(dependencies[module])
    while pending := {
        module for module in sources.keys() - production if any(matches(name, module) for name in referenced)
    }:
        production.update(pending)
        referenced.update(name for module in pending for name in dependencies[module])

    tests = test_classes(sources)
    for module, (path, source, tree, aliases, bindings, _) in sources.items():
        excluded = tests.get(module, set()) if module not in production else set()
        if module in production:
            runtime_whitelist_checks(tree, bindings, path, emit)
        model_checks(path, source, emit, excluded, tree)
        if any(matches(module, scope) for scope in scopes):
            for line in sql_calls(walk(tree, excluded), aliases):
                emit(path, line, "sql", "Raw SQL is forbidden in AI tools.")

    contracted = set()
    originals_by_target = {}
    for path in (
        source_files(root / "contracts", emit)
        if (root / "contracts").exists() or (root / "contracts").is_symlink()
        else ()
    ):
        if path.suffix not in {".yaml", ".yml", ".json"} or path.parent != root / "contracts":
            continue
        try:
            for name, line, missing, originals in operations(path):
                if name not in endpoints and (name.startswith("frappe.") or name in overrides):
                    continue
                contracted.add(name)
                originals_by_target.setdefault(name, set()).update(originals)
                if name not in endpoints:
                    emit(path, line, "endpoint", f"No whitelisted function for {name}.")
                for field in missing:
                    emit(path, line, "endpoint", f"{name} needs a non-empty {field}.")
        except (OSError, UnicodeError, ValueError) as error:
            emit(path, getattr(error, "lineno", 1), "endpoint", str(error))
    for name, (path, line) in endpoints.items():
        if name not in contracted:
            emit(path, line, "endpoint", f"Missing OpenAPI operation for {name}.")

    for public, (target, path, line) in overrides.items():
        if target in endpoints and public not in originals_by_target.get(target, set()):
            emit(path, line, "endpoint", f"Missing x-frappe-original for {public} on {target}.")

    for path, line, message in tracked_findings(root, commit_base):
        findings.add(Finding(path, line, "forbidden-name", message))
    naming = naming_findings(root)
    if naming:
        findings.update(naming)
    return sorted(findings), {"naming": "not_run" if naming is None else "fail" if naming else "pass"}


def supports_python():
    return sys.version_info >= (3, 14)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path-code", help="Locate a redacted path by its Git index slot.")
    parser.add_argument("--commit-base", help="Check commit messages after this revision through HEAD.")
    args = parser.parse_args()
    if not supports_python():
        print("ai-readiness requires Python 3.14 or newer.", file=sys.stderr)
        return 2
    root = args.root.resolve()
    if args.path_code:
        try:
            location = find_path_code(root, args.path_code)
        except (OSError, subprocess.CalledProcessError):
            location = None
        if location is None:
            print("No tracked path found for that code.", file=sys.stderr)
            return 1
        print(json.dumps(location))
        return 0
    raw_findings, checks = scan(root, args.commit_base)
    findings = [
        Finding(
            redact_path(finding.path),
            finding.line,
            finding.rule if next(match_lines([finding.rule]), None) is None else "redacted",
            finding.message if next(match_lines([finding.message]), None) is None else "Details redacted.",
        )
        for finding in raw_findings
    ]
    if args.json:
        print(json.dumps({"findings": [asdict(finding) for finding in findings], "checks": checks}))
    else:
        if checks["naming"] == "not_run":
            print("naming: not_run (checker unavailable)", file=sys.stderr)
        for finding in findings:
            print(f"{finding.path}:{finding.line} [{finding.rule}] {finding.message}")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
