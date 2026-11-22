"""Resolve the static Python forms used by the readiness checks."""

import ast
from importlib.util import resolve_name

FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted(node.value)
        return f"{parent}.{node.attr}" if parent else ""
    return ""


def assignments(node):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                yield target.id, node.value
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
        yield node.target.id, node.value


def imports(node, package):
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.asname or alias.name.split(".")[0], alias.name
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level:
            try:
                module = resolve_name("." * node.level + module, package)
            except ImportError:
                return
        for alias in node.names:
            yield alias.asname or alias.name, f"{module}.{alias.name}"


def qualified(node, aliases):
    first, sep, rest = dotted(node).partition(".")
    return aliases.get(first, first) + sep + rest


def resolve(node, names, seen=frozenset()):
    if isinstance(node, ast.Name) and node.id in names and node.id not in seen:
        return resolve(names[node.id], names, seen | {node.id})
    return node


def string(node, names, seen=frozenset()):
    if isinstance(node, ast.Name):
        if node.id in names and node.id not in seen:
            return string(names[node.id], names, seen | {node.id})
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = string(node.left, names, seen)
        right = string(node.right, names, seen)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.FormattedValue) and part.conversion == -1 and part.format_spec is None:
                part = part.value
            value = string(part, names, seen)
            if value is None:
                return None
            parts.append(value)
        return "".join(parts)
    return None


def mapping(node, names, seen=frozenset()):
    if isinstance(node, ast.Name):
        if node.id in seen or node.id not in names:
            return None
        return mapping(names[node.id], names, seen | {node.id})
    if not isinstance(node, ast.Dict):
        return None
    entries = {}
    for key, value in zip(node.keys, node.values):
        if key is None:
            base = mapping(value, names, seen)
            if base is None:
                return None
            entries.update(base)
        else:
            name = string(key, names)
            if name is not None:
                entries[name] = value
    return entries


def walk(node, excluded=frozenset()):
    if node not in excluded:
        yield node
        for child in ast.iter_child_nodes(node):
            yield from walk(child, excluded)


def sql_calls(nodes, aliases):
    aliases = aliases.copy()
    for item in nodes:
        for target, value in assignments(item):
            name = qualified(value, aliases)
            if name in {"frappe.db", "frappe.local.db"}:
                aliases[target] = name
        if not isinstance(item, ast.Call):
            continue
        name = qualified(item.func, aliases)
        if name in {"getattr", "builtins.getattr"} and len(item.args) >= 2:
            name = qualified(item.args[0], aliases) + "." + (string(item.args[1], {}) or "")
        owner, _, method = name.rpartition(".")
        if owner in {"frappe.db", "frappe.local.db"} and method in {"sql", "sql_list", "multisql", "sql_ddl"}:
            yield item.lineno


def declaration_targets(fn, module_names, method_pattern):
    body = list(walk(fn))
    names = module_names | dict(pair for item in body for pair in assignments(item))
    for statement in body:
        if not isinstance(statement, ast.Return):
            continue
        result = resolve(statement.value, names)
        declarations = result.elts if isinstance(result, (ast.List, ast.Tuple)) and result.elts else [result]
        for declaration in declarations:
            entries = mapping(declaration, names)
            if not entries or "handler" not in entries:
                yield statement.lineno, None
                continue
            for key in ("handler", "preview", "prepare"):
                if key in entries:
                    target = string(entries[key], names)
                    yield entries[key].lineno, target if target and method_pattern.fullmatch(target) else None
    if not any(isinstance(item, ast.Return) for item in body):
        yield fn.lineno, None
