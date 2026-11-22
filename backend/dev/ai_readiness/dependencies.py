"""Check application requirements against the Frappe 16 dependency contract."""

import ast
import re
from collections import defaultdict

import tomllib
from source import assignments

FRAPPE_VERSION = "16.56.0"


REQUIREMENT = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)(?:\[[a-zA-Z0-9_,. -]+\])?\s*(.*)$")
SPECIFIER = re.compile(r"(==|!=|~=|>=|<=|<|>)\s*([0-9]+(?:\.[0-9]+)*(?:\.\*)?)")


def parse_requirement(entry):
    match = REQUIREMENT.fullmatch(entry.strip())
    if match is None:
        return None, None
    name = re.sub(r"[-_.]+", "-", match[1]).lower()
    constraint = match[2].strip()
    if not constraint:
        return name, frozenset()
    constraints = []
    for part in constraint.split(","):
        version = SPECIFIER.fullmatch(part.strip())
        if version is None:
            return name, None
        operator, value = version.groups()
        if value.endswith(".*") and operator not in {"==", "!="} or operator == "~=" and "." not in value:
            return name, None
        constraints.append((operator, value))
    return name, frozenset(constraints)


def allows_pin(rule, pin):
    version = tuple(map(int, pin.split(".")))
    for operator, raw in rule:
        wildcard = raw.endswith(".*")
        target = tuple(map(int, raw.removesuffix(".*").split(".")))
        width = max(len(version), len(target))
        left = version + (0,) * (width - len(version))
        right = target + (0,) * (width - len(target))
        same = left[: len(target)] == target if wildcard else left == right
        allowed = {
            "==": same,
            "!=": not same,
            "~=": left >= right and left[: len(target) - 1] == target[:-1],
            ">=": left >= right,
            "<=": left <= right,
            "<": left < right,
            ">": left > right,
        }
        if not allowed[operator]:
            return False
    return True


def project_metadata(path):
    with path.open("rb") as stream:
        project = tomllib.load(stream).get("project", {})
    if not isinstance(project, dict):
        raise ValueError("Invalid project metadata.")
    return project


def requirements(project, *, optional):
    groups = project.get("optional-dependencies", {}) if optional else {}
    if not isinstance(groups, dict):
        raise ValueError("Expected a table of optional dependencies.")
    for entries in (project.get("dependencies", []), *groups.values()):
        if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
            raise ValueError("Expected dependency strings.")
        for entry in entries:
            yield parse_requirement(entry)


def declared_frappe_version(project, package):
    if "version" in project:
        return project["version"]
    init = package / "__init__.py"
    if not init.is_file():
        return None
    tree = ast.parse(init.read_text(encoding="utf-8"))
    return next(
        (
            value.value
            for statement in reversed(tree.body)
            for name, value in assignments(statement)
            if name == "__version__" and isinstance(value, ast.Constant)
        ),
        None,
    )


def frappe_pins(manifest, package):
    if not manifest.is_file():
        return None, set()
    project = project_metadata(manifest)
    if project.get("name") != "frappe" or declared_frappe_version(project, package) != FRAPPE_VERSION:
        return None, set()
    pins = defaultdict(set)
    skipped = set()
    for name, rule in requirements(project, optional=False):
        if rule is None:
            skipped.add(name)
            continue
        for operator, version in rule:
            if operator == "==" and not version.endswith(".*"):
                pins[name].add(version)
    return pins, skipped


def dependency_checks(paths, manifest, package, root, emit):
    checks = {"dependency_core": "not_run", "dependency_apps": "pass"}
    if not paths:
        return checks
    try:
        pins, skipped_core = frappe_pins(manifest, package)
    except (OSError, SyntaxError, ValueError):
        emit(root / "apps", 1, "dependency-input", "Could not read the Frappe dependency manifest.")
        checks["dependency_core"] = "fail"
        pins, skipped_core = None, set()
    if pins is not None:
        checks["dependency_core"] = "pass"

    app_rules = {}
    for path in sorted(paths):
        try:
            declared = list(requirements(project_metadata(path), optional=True))
        except (OSError, ValueError):
            emit(path, 1, "dependency-input", "Could not read project dependencies.")
            checks["dependency_apps"] = "fail"
            if pins is not None:
                checks["dependency_core"] = "fail"
            continue
        rules = defaultdict(set)
        skipped_app = {name for name, rule in declared if rule is None}
        if skipped_app and checks["dependency_apps"] == "pass":
            checks["dependency_apps"] = "not_run"
        if checks["dependency_core"] == "pass" and (
            skipped_app or any(name in skipped_core for name, _ in declared)
        ):
            checks["dependency_core"] = "not_run"
        for name, rule in declared:
            if rule is None:
                continue
            if name not in skipped_app:
                rules[name].add(rule)
            for version in sorted(pins.get(name, ())) if pins is not None else ():
                if not allows_pin(rule, version):
                    emit(path, 1, "dependency-frappe", f"{name} does not allow the Frappe pin {version}.")
                    checks["dependency_core"] = "fail"
        for name, rule in sorted(rules.items()):
            first_path, first_rule = app_rules.setdefault(name, (path, rule))
            if rule != first_rule:
                emit(
                    path,
                    1,
                    "dependency-rule",
                    f"{name} has a different dependency rule in {first_path.relative_to(root).as_posix()}.",
                )
                checks["dependency_apps"] = "fail"
    return checks
