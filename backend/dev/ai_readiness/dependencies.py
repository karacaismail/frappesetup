"""Check application requirements against the Frappe 16 dependency contract."""

import ast
from collections import defaultdict

import tomllib
from source import assignments

FRAPPE_VERSION = "16.56.0"


def requirement_tools():
    try:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
    except ModuleNotFoundError as error:
        if error.name != "packaging":
            raise
        # Bare development Python may have only the copy distributed with pip.
        from pip._vendor.packaging.requirements import Requirement
        from pip._vendor.packaging.utils import canonicalize_name

    return Requirement, canonicalize_name


def project_metadata(path):
    with path.open("rb") as stream:
        project = tomllib.load(stream).get("project", {})
    if not isinstance(project, dict):
        raise ValueError("Invalid project metadata.")
    return project


def requirements(project, parse, *, optional):
    groups = project.get("optional-dependencies", {}) if optional else {}
    if not isinstance(groups, dict):
        raise ValueError("Expected a table of optional dependencies.")
    for entries in (project.get("dependencies", []), *groups.values()):
        if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
            raise ValueError("Expected dependency strings.")
        for entry in entries:
            yield parse(entry)


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


def frappe_pins(manifest, package, parse, canonicalize):
    if not manifest.is_file():
        return None
    project = project_metadata(manifest)
    if project.get("name") != "frappe" or declared_frappe_version(project, package) != FRAPPE_VERSION:
        return None
    pins = defaultdict(set)
    for requirement in requirements(project, parse, optional=False):
        for part in requirement.specifier:
            if part.operator == "==" and not part.version.endswith(".*"):
                pins[canonicalize(requirement.name)].add(part.version)
    return pins


def dependency_checks(paths, manifest, package, root, emit):
    checks = {"dependency_core": "not_run", "dependency_apps": "pass"}
    if not paths:
        return checks

    try:
        parse, canonicalize = requirement_tools()
    except ImportError:
        emit(paths[0], 1, "dependency-input", "Cannot parse dependencies without Python packaging support.")
        checks["dependency_apps"] = "fail"
        return checks

    try:
        pins = frappe_pins(manifest, package, parse, canonicalize)
    except (OSError, SyntaxError, ValueError):
        emit(root / "apps", 1, "dependency-input", "Could not read the Frappe dependency manifest.")
        checks["dependency_core"] = "fail"
        pins = None
    if pins is not None:
        checks["dependency_core"] = "pass"

    app_rules = {}
    for path in sorted(paths):
        try:
            declared = list(requirements(project_metadata(path), parse, optional=True))
        except (OSError, ValueError):
            emit(path, 1, "dependency-input", "Could not read project dependencies.")
            checks["dependency_apps"] = "fail"
            if pins is not None:
                checks["dependency_core"] = "fail"
            continue
        rules = defaultdict(set)
        for requirement in declared:
            name = canonicalize(requirement.name)
            rules[name].add((requirement.specifier, requirement.url))
            for version in sorted(pins.get(name, ())) if pins is not None else ():
                if requirement.url or not requirement.specifier.contains(version, prereleases=True):
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
