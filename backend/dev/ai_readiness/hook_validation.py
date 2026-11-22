"""Validate the declaration form of statically inspected Frappe hooks."""

import ast

HOOK_RULES = {
    "ai_tools": "sql",
    "override_whitelisted_methods": "endpoint",
    "website_user_allowed_methods": "website-user",
}


def node_names(node):
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.alias):
        yield node.asname or node.name.split(".")[0]
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler)):
        yield node.name
    elif isinstance(node, ast.arg):
        yield node.arg
    elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
        yield node.name
    elif isinstance(node, ast.MatchMapping):
        yield node.rest
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        yield from node.names


def invalid_hook_uses(tree):
    first_assignments = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name) and target.id in HOOK_RULES:
            first_assignments.setdefault(target.id, target)

    valid_targets = set(first_assignments.values())
    findings = {
        (name, node.lineno)
        for node in ast.walk(tree)
        if node not in valid_targets
        for name in node_names(node)
        if name in HOOK_RULES
    }
    return sorted(findings, key=lambda finding: (finding[1], finding[0]))
