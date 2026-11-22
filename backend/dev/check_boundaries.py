"""Static architecture checks. This is a code-review gate, not a security sandbox."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def matches(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def owner(name: str, policy: dict) -> str | None:
    overrides = policy.get("path_owners", {})
    for prefix in sorted(overrides, key=len, reverse=True):
        if matches(name, prefix):
            return overrides[prefix]
    for prefix in sorted(policy["modules"], key=len, reverse=True):
        if matches(name, prefix):
            return prefix
    return None


def source_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[0] == "apps" and len(parts) >= 3:
        parts = parts[2:]
    elif parts[0] in {"identity", "libs"}:
        parts = parts[1:]
        if len(parts) > 1 and parts[0] == parts[1]:
            parts = parts[1:]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else ""
    return ""


def literal(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def doctype_arg(node: ast.Call) -> str | None:
    value = next((kw.value for kw in node.keywords if kw.arg == "doctype"), None)
    if value is None and node.args:
        value = node.args[0]
    if isinstance(value, ast.Dict):
        value = next((v for k, v in zip(value.keys, value.values) if literal(k) == "doctype"), None)
    return literal(value)


class SourceCheck(ast.NodeVisitor):
    def __init__(self, path: Path, root: Path, policy: dict, doctypes: dict, graph: dict):
        self.path, self.root, self.policy = path, root, policy
        self.module = source_name(path, root)
        self.source = owner(self.module, policy)
        self.package = self.module if path.name == "__init__.py" else self.module.rpartition(".")[0]
        self.doctypes, self.graph = doctypes, graph
        self.aliases: dict[str, str] = {}
        self.documents: dict[str, str] = {}
        self.errors: list[str] = []

    def error(self, node: ast.AST, code: str, message: str) -> None:
        self.errors.append(
            f"{self.path.relative_to(self.root)}:{getattr(node, 'lineno', 1)} {code} {message}"
        )

    def resolve(self, node: ast.AST) -> str:
        name = dotted(node)
        first, dot, rest = name.partition(".")
        return self.aliases.get(first, first) + (dot + rest if dot else "")

    def dependency(self, name: str, node: ast.AST) -> None:
        if any(matches(name, p) for p in self.policy["forbidden_imports"]):
            self.error(node, "PROVIDER", f"Provider library is forbidden: {name}")
        target = owner(name, self.policy)
        if not self.source or not target or target == self.source:
            return
        self.graph[self.source].add(target)
        if target not in self.policy["modules"][self.source]:
            self.error(node, "IMPORT", f"{self.source} cannot depend on {target}")
            return
        # A public module exports functions. Importing internals below it is forbidden.
        public = self.policy.get("public_paths", {}).get(target, [])
        if not any(
            name == p
            or (
                not isinstance(node, ast.Import)
                and name.rpartition(".")[0] == p
                and not name.endswith(".*")
                and not name.rsplit(".", 1)[-1].startswith("_")
            )
            for p in public
        ):
            self.error(node, "PUBLIC", f"Use a declared public function of {target}: {name}")

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self.dependency(item.name, node)
            self.aliases[item.asname or item.name.split(".")[0]] = (
                item.name if item.asname else item.name.split(".")[0]
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level:
            parts = self.package.split(".")
            base = parts[: len(parts) - node.level + 1]
            module = ".".join(base + ([module] if module else []))
        for item in node.names:
            name = f"{module}.{item.name}" if module else item.name
            self.dependency(name, node)
            self.aliases[item.asname or item.name] = name

    def document_type(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.documents.get(node.id)
        if isinstance(node, ast.Call) and self.resolve(node.func) in {
            "frappe.get_doc",
            "frappe.new_doc",
            "frappe.get_cached_doc",
            "frappe.get_last_doc",
        }:
            return doctype_arg(node)
        return None

    def assign(self, targets: list[ast.expr], value: ast.expr) -> None:
        doctype = self.document_type(value)
        resolved = self.resolve(value)
        for target in targets:
            if isinstance(target, ast.Name):
                self.documents.pop(target.id, None)
                self.aliases.pop(target.id, None)
                if doctype:
                    self.documents[target.id] = doctype
                if resolved:
                    self.aliases[target.id] = resolved

    def visit_Assign(self, node: ast.Assign) -> None:
        self.assign(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.assign([node.target], node.value)
        self.generic_visit(node)

    def foreign_write(self, node: ast.Call, doctype: str | None) -> None:
        target = self.doctypes.get(doctype)
        if target and self.source and target != self.source:
            self.error(node, "WRITE", f"{self.source} cannot write {doctype} owned by {target}")

    def visit_Call(self, node: ast.Call) -> None:
        name = self.resolve(node.func)
        if name in {"importlib.import_module", "__import__", "frappe.get_attr"}:
            value = literal(node.args[0]) if node.args else None
            if value:
                self.dependency(value, node)
        self.dependency(name, node)
        if name in {
            "frappe.db.set_value",
            "frappe.db.set_single_value",
            "frappe.db.delete",
            "frappe.db.bulk_update",
            "frappe.db.truncate",
            "frappe.set_value",
            "frappe.delete_doc",
            "frappe.rename_doc",
            "frappe.delete_doc_if_exists",
        }:
            self.foreign_write(node, doctype_arg(node))
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "save",
            "insert",
            "db_set",
            "db_update",
            "db_insert",
            "delete",
            "submit",
            "cancel",
        }:
            self.foreign_write(node, self.document_type(node.func.value))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        aliases, documents = self.aliases.copy(), self.documents.copy()
        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            self.aliases.pop(arg.arg, None)
            self.documents.pop(arg.arg, None)
        self.generic_visit(node)
        self.aliases, self.documents = aliases, documents

    visit_AsyncFunctionDef = visit_FunctionDef


def cycles(graph: dict) -> list[str]:
    found, finished, active = [], set(), []

    def visit(node: str) -> None:
        if node in active:
            found.append("CYCLE " + " -> ".join(active[active.index(node) :] + [node]))
            return
        if node in finished:
            return
        active.append(node)
        for target in sorted(graph[node]):
            visit(target)
        active.pop()
        finished.add(node)

    for node in graph:
        visit(node)
    return found


def check(root: Path, policy: dict) -> list[str]:
    """Inspect backend apps, libraries and identity services without executing them."""
    graph = {module: set() for module in policy["modules"]}
    errors, doctypes = [], {}
    paths = []
    for folder in ("apps", "identity", "libs"):
        directory = root / folder
        if directory.exists():
            paths.extend(
                p
                for p in directory.rglob("*")
                if p.is_file()
                and not any(
                    part.startswith(".") or part in {"node_modules", "__pycache__"}
                    for part in p.relative_to(directory).parts
                )
            )
    for path in sorted(paths):
        if path.suffix == ".json" and "doctype" in path.parts:
            try:
                data = json.loads(path.read_text())
                module = owner(source_name(path, root), policy)
                if isinstance(data, dict) and data.get("name") and module:
                    doctypes[data["name"]] = module
            except (ValueError, OSError) as exc:
                errors.append(f"{path.relative_to(root)}:1 JSON {exc}")
    for path in sorted(paths):
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except (SyntaxError, UnicodeError, OSError) as exc:
            errors.append(f"{path.relative_to(root)}:{getattr(exc, 'lineno', 1)} SYNTAX {exc}")
            continue
        visitor = SourceCheck(path, root, policy, doctypes, graph)
        visitor.visit(tree)
        errors.extend(visitor.errors)
    return sorted(set(errors)) + cycles(graph)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--policy", type=Path, default=Path(__file__).with_name("modul-sinirlari.json"))
    args = parser.parse_args()
    try:
        violations = check(args.root.resolve(), json.loads(args.policy.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    for violation in violations:
        print(violation)
    print(f"Module boundaries: {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
