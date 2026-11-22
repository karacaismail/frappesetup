"""List backend interfaces from source files without importing application code."""

import ast
import json
import re
import sys
import tokenize
from collections import defaultdict
from fnmatch import fnmatchcase
from pathlib import Path

from forbidden_name import redact_path
from hook_validation import node_names
from source import assignments, dotted, imports, mapping, resolve, scope_nodes, string

# Use the same module names and ownership overrides as the architecture checker.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_boundaries import owner, source_name  # noqa: E402

OWNER_HEADING = "## Klasörler ve sahipleri"
APP_METADATA = {
    "app_name",
    "app_title",
    "app_publisher",
    "app_description",
    "app_email",
    "app_license",
    "app_icon",
    "app_color",
    "app_version",
    "app_logo",
    "app_home",
}


def folder_owners(path, apps):
    if not path.is_file():
        return {}
    section = path.read_text(encoding="utf-8").partition(OWNER_HEADING)[2].split("\n## ", 1)[0]
    owners = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = line.strip("|").split("|")
        if len(cells) != 3:
            continue
        folders, contents, label = (cell.strip() for cell in cells)
        prefix = ""
        for pattern in re.findall(r"`([^`]+)`", folders):
            parts = pattern.split("/")
            if parts[0] == "apps" and len(parts) > 2:
                app = parts[1]
                prefix = f"apps/{app}/{app}/"
                if pattern == f"apps/{app}/" and "iskelet" in folders:
                    for name in re.findall(r"`([^`]+)`", contents):
                        owners[(prefix if name == "hooks.py" else pattern) + name] = label
                    continue
            elif parts[0] in apps:
                app = parts[0]
                prefix = f"apps/{app}/{app}/"
                pattern = f"apps/{app}/{pattern}"
            elif prefix and parts[0] not in {"dev", "identity", "libs", "docs", "contracts", "e2e"}:
                pattern = prefix + pattern
            owners[pattern] = label
    return owners


def folder_owner(path, owners):
    paths = (
        pattern
        for pattern in owners
        if path == pattern
        or (pattern.endswith("/") and path.startswith(pattern))
        or fnmatchcase(path, pattern)
    )
    match = max(paths, key=len, default="")
    return owners.get(match, "Belirtilmemiş")


def hook_values(node, bindings, key, seen=frozenset()):
    value = resolve(node, bindings)
    if value in seen:
        yield key, "Çözülemedi", node.lineno
        return
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        for entry in value.elts:
            yield from hook_values(entry, bindings, key, seen | {value})
    elif isinstance(value, ast.Dict) and (entries := mapping(value, bindings)) is not None:
        for label, entry in entries.items():
            yield from hook_values(entry, bindings, f"{key}[{label}]", seen | {value})
    else:
        text = string(value, bindings)
        if text is None:
            text = str(value.value) if isinstance(value, ast.Constant) else "Çözülemedi"
        yield key, text, node.lineno


def add_function_exports(sources, functions):
    candidates = {}
    for module, (_, _, package, tree, _) in sources.items():
        for index, node in enumerate(tree.body):
            if not isinstance(node, ast.ImportFrom):
                continue
            later_bindings = {
                name
                for item in scope_nodes(tree.body[index + 1 :])
                if not isinstance(item, ast.Name) or not isinstance(item.ctx, ast.Load)
                for name in node_names(item)
            }
            for alias, target in imports(node, package):
                if alias not in later_bindings:
                    candidates[f"{module}.{alias}"] = target, module
    while resolved := {
        name: module
        for name, (target, module) in candidates.items()
        if name not in functions and target in functions
    }:
        functions.update(resolved)


def function_imports(tree, package, functions, modules):
    attributes = {
        name for node in ast.walk(tree) if isinstance(node, ast.Attribute) and (name := dotted(node))
    }
    for node in ast.walk(tree):
        for alias, target in imports(node, package):
            if target in functions:
                yield target, node.lineno
            elif target in modules:
                # Unaliased dotted imports bind the first component of the module path.
                direct = isinstance(node, ast.Import) and any(
                    item.name == target and item.asname is None for item in node.names
                )
                prefix = target if direct else alias
                for name in attributes:
                    if name.startswith(prefix + "."):
                        method = target + name[len(prefix) :]
                        if method in functions:
                            yield method, node.lineno


def module_for(name, path, policy):
    bound = owner(name, policy)
    if bound:
        return bound
    parts = path.split("/")
    if parts[0] == "apps" and len(parts) >= 4:
        return ".".join(name.split(".")[: 2 if len(parts) > 4 else 1])
    return name.split(".")[0]


def table_cell(value):
    return redact_path(value).replace("|", r"\|").replace("`", "&#96;").replace("\n", " ").replace("\r", " ")


def show_table(headers, rows):
    yield "| " + " | ".join(headers) + " |"
    yield "| " + " | ".join("---" for _ in headers) + " |"
    for row in sorted(rows):
        yield "| " + " | ".join(table_cell(value) for value in row) + " |"


def list_interfaces(root, source_files, whitelist_checks):
    policy_path = root / "dev/module-boundaries.json"
    if not policy_path.exists():
        policy_path = root / "dev/modul-sinirlari.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.is_file() else {}
    if not isinstance(policy, dict) or any(
        not isinstance(policy.get(key, {}), dict) for key in ("modules", "path_owners", "public_paths")
    ):
        raise ValueError("Invalid module boundary policy")
    policy.setdefault("modules", {})
    rows, sources, functions = defaultdict(set), {}, {}
    warnings = set()

    def warn(path, line, _rule, message):
        warnings.add((f"{path.relative_to(root).as_posix()}:{line}", message))

    for folder in ("apps", "identity", "libs"):
        directory = root / folder
        if not directory.exists():
            continue
        for path in source_files(directory, warn):
            if path.suffix != ".py":
                continue
            relative = path.relative_to(root).as_posix()
            name = source_name(path, root)
            package = name if path.stem == "__init__" else name.rpartition(".")[0]
            try:
                with tokenize.open(path) as stream:
                    tree = ast.parse(stream.read(), filename=relative)
            except (OSError, UnicodeError, SyntaxError, ValueError) as error:
                warn(path, getattr(error, "lineno", None) or 1, "input", "Python dosyası okunamadı.")
                continue
            bindings = dict(pair for item in tree.body for pair in assignments(item))
            group = module_for(name, relative, policy)
            sources[name] = relative, group, package, tree, bindings
            local, exposed = whitelist_checks(tree, bindings, name, path, warn)
            functions.update((f"{name}.{method}", name) for method in local if "." not in method)
            for method, (_, line) in exposed.items():
                rows[group].add(("Dışarıya açık yöntem", method, f"{relative}:{line}"))

    add_function_exports(sources, functions)
    apps = {path.split("/")[1] for path, *_ in sources.values() if path.startswith("apps/")}
    owners = folder_owners(root / "AGENTS.md", apps)
    module_paths = defaultdict(set)
    for relative, group, *_ in sources.values():
        module_paths[group].add(relative)

    internal_imports = set()
    public_paths = policy.get("public_paths", {})
    for name, (relative, group, package, tree, bindings) in sources.items():
        if name.endswith(".hooks"):
            for hook, value in bindings.items():
                if hook.startswith("_") or hook in APP_METADATA:
                    continue
                for key, text, line in hook_values(value, bindings, hook):
                    target = functions.get(text, text if text in sources else "")
                    target_group = sources[target][1] if target else group
                    kind = "Kayıt olayı" if hook == "doc_events" else "Kanca"
                    rows[target_group].add((kind, f"{key} = {text}", f"{relative}:{line}"))
        for method, line in function_imports(tree, package, functions, sources):
            target = functions[method]
            target_group = sources[target][1]
            if target_group == group:
                continue
            location = f"{relative}:{line}"
            rows[target_group].add(("İçe aktarılan işlev", method, location))
            if target not in public_paths.get(target_group, []) or method.rsplit(".", 1)[-1].startswith("_"):
                internal_imports.add((group, target_group, method, location))

    lines = ["# Modül arayüzleri", ""]
    for group in sorted(module_paths):
        labels = {folder_owner(path, owners) for path in module_paths[group]} - {"Belirtilmemiş"}
        label = ", ".join(sorted(labels)) or "Belirtilmemiş"
        lines.extend((f"## `{table_cell(group)}`", ""))
        entries = rows[group] or {("Kayıt yok", "", "")}
        lines.extend(show_table(("Tür", "Arayüz", "Kaynak", "Sahip"), ((*row, label) for row in entries)))
        lines.append("")
    lines.extend(("## İç işlev içe aktarma uyarıları", ""))
    if internal_imports:
        lines.append("Bu uyarılar komutun çıkış kodunu değiştirmez.")
        lines.append("")
        lines.extend(show_table(("Çağıran modül", "Hedef modül", "İşlev", "Kaynak"), internal_imports))
    else:
        lines.append("İç işlev içe aktarma uyarısı yok.")
    if warnings:
        lines.extend(("", "## Okuma uyarıları", ""))
        lines.extend(show_table(("Kaynak", "Uyarı"), warnings))
    return "\n".join(lines)
