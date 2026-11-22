"""Resolve the shared files used by the backend merge preview."""

import ast
import csv
import io
import json
import pprint
import re
import subprocess
from pathlib import Path

APP = "backend/apps/platform_core"
HOOKS = f"{APP}/platform_core/hooks.py"
TRANSLATIONS = f"{APP}/platform_core/translations/tr.csv"
MODULES = f"{APP}/platform_core/modules.txt"
DEPENDENCIES = f"{APP}/pyproject.toml"
MISSING = object()


class MergeError(Exception):
    pass


def git(worktree, *arguments, check=True):
    return subprocess.run(
        ["git", "-C", str(worktree), *arguments], check=check, capture_output=True, text=True
    )


def ordered_union(left, right):
    values = list(left)
    for value in right:
        if value not in values:
            values.append(value)
    return values


def hook_values(source):
    values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise MergeError("Hooks contain statements that require manual review.")
        name = node.targets[0].id
        if name in values:
            raise MergeError(f"Duplicate hook assignment: {name}")
        try:
            values[name] = ast.literal_eval(node.value)
        except ValueError as error:
            raise MergeError(f"Hook is not a literal: {name}") from error
    return values


def hook_union(base, left, right, location="hooks"):
    """Keep list entries from both sides, including events that use string shorthand."""
    if left is MISSING or right is MISSING:
        return right if left is MISSING else left
    if left == right:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        ancestor = base if isinstance(base, dict) else {}
        return {
            key: hook_union(
                ancestor.get(key, MISSING), left.get(key, MISSING), right.get(key, MISSING), f"{location}.{key}"
            )
            for key in ordered_union(left, right)
        }
    list_shorthand = location.startswith("hooks.doc_events.") or location in {"hooks.after_install", "hooks.after_migrate"}
    if isinstance(left, (str, list)) and isinstance(right, (str, list)) and (
        list_shorthand or isinstance(left, list) or isinstance(right, list)
    ):
        return ordered_union(left if isinstance(left, list) else [left], right if isinstance(right, list) else [right])
    if left == base:
        return right
    if right == base:
        return left
    raise MergeError(f"Conflicting hook values: {location}")


def verify_hook_lists(source, merged, location="hooks"):
    for key, value in source.items():
        result = merged.get(key)
        if isinstance(value, list):
            if not isinstance(result, list) or any(item not in result for item in value):
                raise MergeError(f"Hook list lost an entry: {location}.{key}")
        elif isinstance(value, dict):
            verify_hook_lists(value, result if isinstance(result, dict) else {}, f"{location}.{key}")


def translation_rows(content):
    rows = {}
    for row in csv.reader(io.StringIO(content)):
        if not row:
            continue
        if len(row) not in (2, 3):
            raise MergeError("Unexpected translation row format.")
        key = (row[0], row[2] if len(row) == 3 else "")
        if key in rows and rows[key][1] != row[1]:
            raise MergeError("A translation source and context have different values.")
        rows[key] = row
    return rows


def merge_translations(base, left, right):
    base, left, right = map(translation_rows, (base, left, right))
    merged = io.StringIO()
    writer = csv.writer(merged, lineterminator="\n")
    for key in ordered_union(left, right):
        ours, theirs, ancestor = left.get(key), right.get(key), base.get(key)
        if ours and theirs and ours[1] != theirs[1]:
            if ancestor and ours[1] == ancestor[1]:
                ours = theirs
            elif not ancestor or theirs[1] != ancestor[1]:
                raise MergeError("Both branches changed the same translation source and context.")
        writer.writerow(ours or theirs)
    return merged.getvalue()


def merge_dependencies(base, left, right):
    """Only the dependencies array has an automatic TOML resolution."""
    pattern = re.compile(r"(?m)^dependencies\s*=\s*(\[(?:[^\n]*\n)*?^\])")
    parsed = []
    for content in (base, left, right):
        match = pattern.search(content)
        if not match:
            raise MergeError("The dependency array cannot be located.")
        dependencies = ast.literal_eval(match[1])
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            raise MergeError("Unsupported dependency list.")
        parsed.append((pattern.sub("", content, count=1), dependencies))
    ancestor, ours, theirs = (item[0] for item in parsed)
    if ours == theirs or theirs == ancestor:
        template = left
    elif ours == ancestor:
        template = right
    else:
        raise MergeError("Both branches changed TOML outside the dependency array.")

    values = ordered_union(parsed[1][1], parsed[2][1])
    # Different constraints on the same dependency need a maintainer decision.
    names = {}
    for value in values:
        name = re.split(r"[\s[<>=!~;@]", value, maxsplit=1)[0].lower().replace("_", "-")
        if name in names and names[name] != value:
            raise MergeError(f"Different version constraints: {name}")
        names[name] = value
    replacement = "dependencies = [\n" + "".join(f"    {json.dumps(value)},\n" for value in values) + "]"
    return pattern.sub(lambda _match: replacement, template, count=1)


def resolve(worktree, filename):
    if filename not in (HOOKS, TRANSLATIONS, MODULES, DEPENDENCIES):
        raise MergeError("Manual resolution required.")
    stages = [git(worktree, "show", f":{stage}:{filename}", check=False) for stage in (1, 2, 3)]
    base, left, right = (result.stdout for result in stages)
    if stages[1].returncode or stages[2].returncode:
        raise MergeError("Manual resolution required for a file deletion.")
    if filename == HOOKS:
        values = hook_union(hook_values(base), hook_values(left), hook_values(right))
        for content in (left, right):
            verify_hook_lists(hook_values(content), values)
        merged = "".join(f"{key} = {pprint.pformat(value, sort_dicts=False)}\n" for key, value in values.items())
    elif filename == TRANSLATIONS:
        merged = merge_translations(base, left, right)
    elif filename == MODULES:
        merged = "\n".join(ordered_union(left.splitlines(), right.splitlines())) + "\n"
    else:
        merged = merge_dependencies(base, left, right)
    (Path(worktree) / filename).write_text(merged)
    git(worktree, "add", "--", filename)
