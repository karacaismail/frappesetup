"""List Frappe endpoints and require two neighboring authorization test definitions."""

import argparse
import ast
import sys
import tokenize
from pathlib import Path
from typing import Iterator, Optional, Union


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
Function = Union[ast.FunctionDef, ast.AsyncFunctionDef]
REQUIRED_TESTS = ("guest_denied", "foreign_data_denied")


def read_tree(path: Path) -> ast.Module:
    with tokenize.open(path) as source:
        return ast.parse(source.read(), filename=str(path))


def frappe_names(tree: ast.Module) -> tuple[set[str], set[str], set[str]]:
    modules = set()
    decorators = set()
    limiters = set()
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            modules.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name == "frappe"
            )
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.module == "frappe"
            and statement.level == 0
        ):
            decorators.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name == "whitelist"
            )
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.module == "frappe.rate_limiter"
            and statement.level == 0
        ):
            limiters.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name == "rate_limit"
            )
    return modules, decorators, limiters


def is_whitelist(decorator: ast.expr, modules: set[str], decorators: set[str]) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id in decorators
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "whitelist"
        and isinstance(target.value, ast.Name)
        and target.value.id in modules
    )


def definitions(
    tree: ast.AST, prefix: str = ""
) -> Iterator[tuple[str, Function]]:
    if isinstance(tree, FUNCTIONS):
        yield prefix + tree.name, tree
        return
    if isinstance(tree, ast.ClassDef):
        prefix += f"{tree.name}."
    for child in ast.iter_child_nodes(tree):
        yield from definitions(child, prefix)


def guest_access(decorator: ast.expr) -> Optional[bool]:
    if not isinstance(decorator, ast.Call):
        return None
    positional = decorator.args
    if any(isinstance(arg, ast.Starred) for arg in positional):
        return None
    if any(keyword.arg is None for keyword in decorator.keywords):
        return None
    value = next(
        (keyword.value for keyword in decorator.keywords if keyword.arg == "allow_guest"),
        positional[0] if positional else ast.Constant(False),
    )
    if isinstance(value, ast.Constant) and isinstance(value.value, bool):
        return value.value
    return None


def method_list(decorator: ast.expr) -> str:
    if not isinstance(decorator, ast.Call):
        return "belirsiz"
    value = next(
        (keyword.value for keyword in decorator.keywords if keyword.arg == "methods"),
        decorator.args[2] if len(decorator.args) > 2 else None,
    )
    if value is None:
        return "yazılmamış"
    if isinstance(value, (ast.List, ast.Tuple)) and all(
        isinstance(item, ast.Constant) and isinstance(item.value, str)
        for item in value.elts
    ):
        return ", ".join(item.value for item in value.elts) or "boş"
    return "belirsiz"


def has_rate_limit(
    decorators: list[ast.expr], modules: set[str], limiters: set[str]
) -> bool:
    recognized = limiters | {f"{module}.rate_limiter.rate_limit" for module in modules}
    return any(
        isinstance(decorator, ast.Call) and ast.unparse(decorator.func) in recognized
        for decorator in decorators
    )


def test_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        name.rsplit(".", 1)[-1]
        for name, _ in definitions(read_tree(path))
    }


def inventory(apps: Path) -> tuple[list[str], list[str], list[str]]:
    routes = []
    guest_routes = []
    errors = []
    if not apps.is_dir():
        return routes, guest_routes, [f"Uygulama klasörü bulunamadı. {apps}"]

    for path in sorted(apps.rglob("*.py")):
        relative = path.relative_to(apps)
        if (
            len(relative.parts) < 3
            or path.name.startswith("test_")
            or any(part.startswith(".") for part in relative.parts)
        ):
            continue
        try:
            tree = read_tree(path)
            modules, decorators, limiters = frappe_names(tree)
            imports = relative.with_suffix("").parts[1:]
            module = ".".join(imports[:-1] if path.name == "__init__.py" else imports)
            test_path = path.with_name(f"test_{path.name}")
            covered = None
            for name, statement in definitions(tree):
                for index, decorator in enumerate(statement.decorator_list):
                    if not is_whitelist(decorator, modules, decorators):
                        continue
                    route = f"{module}.{name}"
                    if "." not in name:
                        route = f"/api/method/{route}"
                    guest = guest_access(decorator)
                    access = {True: "misafir", False: "oturum", None: "belirsiz"}[guest]
                    methods = method_list(decorator)
                    entry = f"{route} [{methods}] [{access}]"
                    routes.append(entry)
                    if guest is True:
                        guest_routes.append(entry)
                        if not has_rate_limit(statement.decorator_list[index + 1:], modules, limiters):
                            errors.append(f"{relative}:{statement.lineno} rate_limit uç kaydının altında olmalı.")
                    if guest is None:
                        errors.append(f"{relative}:{statement.lineno} allow_guest belirsiz.")
                    if methods in {"belirsiz", "boş", "yazılmamış"}:
                        errors.append(f"{relative}:{statement.lineno} methods açık ve dolu olmalı.")
                    if covered is None:
                        covered = test_names(test_path)
                    for suffix in REQUIRED_TESTS:
                        expected = f"test_{name.replace('.', '_')}_{suffix}"
                        if expected not in covered:
                            test_file = test_path.relative_to(apps)
                            errors.append(f"{route} için {test_file} dosyasında {expected} eksik.")
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append(f"{relative} okunamadı. {error}")

    return routes, guest_routes, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Frappe uçlarını ve yetki testi adlarını denetler.")
    parser.add_argument("backend", type=Path, help="Backend klasörü")
    args = parser.parse_args()
    routes, guest_routes, errors = inventory(args.backend / "apps")
    for heading, entries in (("Tüm uçlar", routes), ("Misafire açık uçlar", guest_routes)):
        print(f"{heading} ({len(entries)})")
        for entry in sorted(entries):
            print(f"  {entry}")
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
