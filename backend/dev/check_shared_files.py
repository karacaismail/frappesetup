"""Check the shared files that Git can merge silently: hooks.py and translation CSV files.

hooks.py: every top-level name is assigned once. A second assignment silently drops the
earlier value and Git does not report a conflict (backend/AGENTS.md). Extending a list with
`+=` stays allowed.

translations/*.csv: no conflict markers, three columns per record (source, translation,
context; O-23) and one record per source and context.
"""

import argparse
import ast
import csv
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CONFLICT_MARKERS = ("<<<<<<< ", "=======", ">>>>>>> ", "||||||| ")


def assigned_names(statement):
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        targets = [statement.target]
    else:
        return
    for target in targets:
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                yield node.id


def check_hooks(path, relative):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    except (SyntaxError, UnicodeDecodeError) as error:
        yield f"{relative}:{getattr(error, 'lineno', 1) or 1}: cannot parse hooks file"
        return
    first = {}
    for statement in tree.body:
        for name in assigned_names(statement):
            if name in first:
                yield (
                    f"{relative}:{statement.lineno}: {name} is assigned again "
                    f"(first on line {first[name]}); extend the existing value instead"
                )
            else:
                first[name] = statement.lineno


def check_csv(path, relative):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        yield f"{relative}:1: file is not UTF-8"
        return
    lines = text.splitlines()
    markers = [n for n, line in enumerate(lines, 1) if line.startswith(CONFLICT_MARKERS)]
    for number in markers:
        yield f"{relative}:{number}: merge conflict marker"
    if markers:
        return
    reader = csv.reader(lines)
    seen = {}
    try:
        for row in reader:
            number = reader.line_num
            if not row:
                continue
            if len(row) != 3:
                yield f"{relative}:{number}: expected 3 columns (source, translation, context), found {len(row)}"
                continue
            key = (row[0], row[2])
            if key in seen:
                yield f"{relative}:{number}: duplicate source and context (first on line {seen[key]})"
            else:
                seen[key] = number
    except csv.Error as error:
        yield f"{relative}:{reader.line_num}: {error}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=BACKEND, help="backend directory")
    root = parser.parse_args(argv).root.resolve()
    findings = []
    hooks = sorted(root.glob("apps/*/*/hooks.py"))
    catalogs = sorted(root.glob("apps/*/*/translations/*.csv"))
    for path in hooks:
        findings.extend(check_hooks(path, path.relative_to(root).as_posix()))
    for path in catalogs:
        findings.extend(check_csv(path, path.relative_to(root).as_posix()))
    for finding in findings:
        print(finding)
    print(f"shared files: {len(hooks)} hooks, {len(catalogs)} translation files, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
