"""Frappe uygulamasının statik incelemesi: yapı (`app_inspect`) ve kurallar (`app_check`).

Kod hiçbir zaman içe aktarılmaz veya çalıştırılmaz; Python dosyaları `ast` ile, JSON dosyaları `json`
ile okunur. Sürüme bağlı kurallar hedef Frappe sürümü (v15/v16) verilmezse `unknown` döner.
Doğrulanmış sürüm gerçekleri (frappe/frappe version-15 b0b5b99, version-16 6b450a1):
- `override_doctype_class`: iki sürümde var; birden çok uygulamada son tanım kazanır; v16 özgün sınıfın
  alt sınıfı olmayı zorunlu kılar (frappe/model/base_document.py v15:89-96, v16:110-123).
- `extend_doctype_class`: yalnız v16 (mixin; base_document.py v16:180-207).
- patches.txt `[pre_model_sync]` / `[post_model_sync]` bölümleri (frappe/modules/patch_handler.py).
- Test tabanı: v15 `frappe.tests.utils.FrappeTestCase`, v16 `frappe.tests.IntegrationTestCase`.
"""
from __future__ import annotations

import ast
import json
import re
import sys

from .errors import WorkspaceError

OFFICIAL_MODULES = ("frappe", "erpnext", "hrms", "payments", "education", "lms", "crm", "helpdesk", "india_compliance",
                    "lending", "webshop", "builder", "insights", "raven", "wiki", "gameplan", "drive", "print_designer",
                    "press")


def min_python(spec) -> tuple | None:
    """`requires-python` değerinden en düşük sürüm (ör. ">=3.10,<3.15" → (3, 10)); okunamazsa None."""
    if not isinstance(spec, str):
        return None
    match = re.search(r">=\s*(\d+)\.(\d+)", spec) or re.search(r"~=\s*(\d+)\.(\d+)", spec)
    return (int(match.group(1)), int(match.group(2))) if match else None


def app_min_python(ws, info) -> tuple | None:
    if info.get("repo") and ws.exists(info["repo"] + "/pyproject.toml"):
        return min_python(_pyproject_summary(ws.read_text(info["repo"] + "/pyproject.toml")).get("requires_python"))
    return None


OFFICIAL_CASEFOLDED = frozenset(name.casefold() for name in OFFICIAL_MODULES)


def is_official(name) -> bool:
    """Harf duyarsız dosya sisteminde (APFS varsayılanı) `Erpnext` de `erpnext`tir."""
    return isinstance(name, str) and name.casefold() in OFFICIAL_CASEFOLDED


def parse_python(source: str, filename: str, target_min):
    """Kodu çalıştırmadan ayrıştırır. Dönüş: (ağaç | None, durum). Durum `ok`, `invalid` ya da `unknown`.

    Sunucu Python'u uygulamanın en düşük sürümüne yetişiyorsa ayrıştırma o sürümün dilbilgisiyle yapılır
    (`feature_version`): ör. `>=3.10` bildiren uygulamada 3.12'ye özgü `type X = ...` geçersizdir. Sunucu daha eskiyse
    (ör. 3.9 sunucu, 3.10+ hedef) sözdizimi hatası kesin değildir; sonuç `unknown` olur ve çağıran metin taramasına ve
    çift onaya düşer. Hedef bilinmiyorsa sunucunun dilbilgisiyle ayrıştırılır, hata yine `unknown` sayılır."""
    authoritative = target_min is not None and sys.version_info[:2] >= tuple(target_min)
    try:
        if authoritative:
            return ast.parse(source, filename=filename, feature_version=tuple(target_min)), "ok"
        return ast.parse(source, filename=filename), "ok"
    except SyntaxError as error:
        if authoritative:
            return None, "invalid: line {}: {}".format(error.lineno, error.msg)
        return None, "unknown"


_TEXT_EXT001 = re.compile(r"^(?:setattr\(\s*)?(?:{})(?:\.[A-Za-z_]\w*)+\s*(?:=(?!=)|,)".format(
    "|".join(OFFICIAL_MODULES)), re.M)
_TEXT_SEC002 = re.compile(r"frappe\.db\.sql\(\s*(?:f[\"']|[\"'][^\"'\n]*[\"']\s*(?:%|\.format\())")


def text_rule_scan(source: str) -> list:
    """Ayrıştırılamayan dosya için en iyi çaba metin taraması: modül düzeyinde resmi modüle atama ya da setattr
    (EXT001) ve biçimlenmiş SQL (SEC002). İçe aktarma takma adlarını görmez; bu yüzden çift onay eşlik eder."""
    found = []
    for rule, pattern in (("EXT001", _TEXT_EXT001), ("SEC002", _TEXT_SEC002)):
        for match in pattern.finditer(source):
            found.append({"rule": rule, "severity": "error", "line": source.count("\n", 0, match.start()) + 1,
                          "message": "text scan: " + match.group(0).strip()[:80]})
    return found
RESERVED_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield",
                   "parenttype", "doctype", "_user_tags", "_comments", "_assign", "_liked_by", "_seen"}
LIFECYCLE = {"validate", "before_validate", "before_save", "after_save", "on_update", "before_insert", "after_insert",
             "on_submit", "before_submit", "on_cancel", "before_cancel", "on_trash", "after_delete", "on_change",
             "before_rename", "after_rename", "on_update_after_submit", "autoname", "before_naming"}
_FIELDNAME = re.compile(r"[a-z][a-z0-9_]{0,139}")
_TABLE_TYPES = ("Table", "Table MultiSelect")


def scrub(text: str) -> str:
    return text.replace(" ", "_").replace("-", "_").lower()


def classname(doctype: str) -> str:
    return doctype.replace(" ", "").replace("-", "")


# -- yapı ----------------------------------------------------------------------------------------
def locate_app(ws, app_path: str) -> dict:
    """`app_path` uygulama deposu kökü (pyproject.toml/setup.py ve iç paket) ya da iç paketin kendisi olabilir."""
    if ws.exists(app_path + "/hooks.py"):
        package = app_path
        repo = app_path.rsplit("/", 1)[0] if "/" in app_path else None
        name = app_path.rsplit("/", 1)[-1]
    else:
        candidates = []
        for rel in ws.walk(app_path, max_files=20000):
            parts = rel[len(app_path) + 1:].split("/")
            if len(parts) == 2 and parts[1] == "hooks.py":
                candidates.append(parts[0])
        if len(candidates) != 1:
            raise WorkspaceError("Expected exactly one package with hooks.py under " + app_path,
                                 code="not_an_app", details={"candidates": candidates})
        name = candidates[0]
        package = app_path + "/" + name
        repo = app_path
    return {"name": name, "package": package, "repo": repo}


def parse_hooks(source: str) -> dict:
    """hooks.py'deki üst düzey sabit atamaları döndürür; sabit olmayan değerler işaretlenir."""
    tree = ast.parse(source)
    hooks = {}
    lines = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            try:
                hooks[key] = ast.literal_eval(node.value)
            except ValueError:
                hooks[key] = "<non-literal>"
            lines[key] = node.lineno
    return {"values": hooks, "lines": lines}


def _patches(text: str) -> list:
    section = "pre_model_sync"
    entries = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        entries.append({"line": number, "section": section, "entry": line.split()[0], "raw": line})
    return entries


def _doctype_files(files: list, package: str) -> list:
    out = []
    for rel in files:
        parts = rel[len(package) + 1:].split("/")
        if len(parts) == 4 and parts[1] == "doctype" and parts[3] == parts[2] + ".json":
            out.append({"module_dir": parts[0], "folder": parts[2], "path": rel})
    return out


def inspect(ws, app_path: str) -> dict:
    app = locate_app(ws, app_path)
    package = app["package"]
    files = ws.walk(package, max_files=20000)
    hooks = parse_hooks(ws.read_text(package + "/hooks.py"))
    modules = [m.strip() for m in ws.read_text(package + "/modules.txt").splitlines() if m.strip()] \
        if ws.exists(package + "/modules.txt") else []
    patches = _patches(ws.read_text(package + "/patches.txt")) if ws.exists(package + "/patches.txt") else []
    doctypes = []
    for item in _doctype_files(files, package):
        try:
            meta = json.loads(ws.read_text(item["path"]))
        except ValueError:
            doctypes.append({"path": item["path"], "error": "invalid JSON"})
            continue
        fields = [f for f in meta.get("fields", []) if isinstance(f, dict)]
        doctypes.append({
            "name": meta.get("name"), "module": meta.get("module"), "path": item["path"],
            "istable": bool(meta.get("istable")), "issingle": bool(meta.get("issingle")),
            "is_submittable": bool(meta.get("is_submittable")), "autoname": meta.get("autoname"),
            "fields": len(fields),
            "child_tables": [{"fieldname": f.get("fieldname"), "options": f.get("options")}
                             for f in fields if f.get("fieldtype") in _TABLE_TYPES],
            "links": sorted({f.get("options") for f in fields if f.get("fieldtype") == "Link" and f.get("options")}),
            "permissions": [p.get("role") for p in meta.get("permissions", []) if isinstance(p, dict)],
        })
    pyproject = ws.read_text(app["repo"] + "/pyproject.toml") if app["repo"] and ws.exists(
        app["repo"] + "/pyproject.toml") else None
    values = hooks["values"]
    return {
        "app": app["name"], "package_path": package, "repo_path": app["repo"],
        "hooks": {key: values.get(key) for key in ("app_name", "app_title", "app_publisher", "app_license",
                                                   "required_apps") if key in values},
        "hook_keys": sorted(values),
        "extension_hooks": {key: values[key] for key in ("doc_events", "override_doctype_class",
                                                         "extend_doctype_class", "override_whitelisted_methods",
                                                         "fixtures", "scheduler_events", "permission_query_conditions",
                                                         "has_permission") if key in values},
        "modules": modules,
        "patches": patches,
        "doctypes": doctypes,
        "tests": [f for f in files if f.rsplit("/", 1)[-1].startswith("test_") and f.endswith(".py")],
        "pyproject": _pyproject_summary(pyproject) if pyproject else None,
        "files_scanned": len(files),
    }


def _pyproject_summary(text: str) -> dict:
    """Python 3.9'da tomllib yok: yalnız gereken anahtarlar düz metinden okunur."""
    out = {}
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M)
    if match:
        out["requires_python"] = match.group(1)
    match = re.search(r"^\[tool\.bench\.frappe-dependencies\]\s*\n((?:[^\[\n].*\n?)*)", text, re.M)
    if match:
        deps = dict(re.findall(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([^"]+)"', match.group(1), re.M))
        out["frappe_dependencies"] = deps
    match = re.search(r'^name\s*=\s*"([^"]+)"', text, re.M)
    if match:
        out["name"] = match.group(1)
    return out


# -- kurallar ------------------------------------------------------------------------------------
class _Finder(ast.NodeVisitor):
    def __init__(self, path, findings, official_imports):
        self.path = path
        self.findings = findings
        self.official = official_imports
        self.function_stack = []

    def add(self, rule, severity, node, message):
        self.findings.append({"rule": rule, "severity": severity, "file": self.path,
                              "line": getattr(node, "lineno", None), "message": message})

    def _root(self, node):
        while isinstance(node, ast.Attribute):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    def visit_FunctionDef(self, node):
        guest = False
        whitelisted = False
        for dec in node.decorator_list:
            text = ast.dump(dec)
            if "whitelist" in text:
                whitelisted = True
                if "allow_guest" in text and "value=True" in text:
                    guest = True
        if guest:
            self.add("SEC001", "warning", node, "Guest-callable endpoint (allow_guest=True): validate every input "
                                                "and never touch documents without explicit checks.")
        self.function_stack.append({"name": node.name, "whitelisted": whitelisted, "guest": guest})
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and self._root(target) in self.official and not self.function_stack:
                self.add("EXT001", "error", node, "Module-level assignment to an official app attribute "
                                                  "(monkey patch). Use hooks (doc_events, extend/override class).")
            if (isinstance(target, ast.Attribute) and target.attr == "ignore_permissions"
                    and isinstance(node.value, ast.Constant) and node.value.value is True):
                self._permission_bypass(node)
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "setattr" and node.args and \
                self._root(node.args[0]) in self.official and not self.function_stack:
            self.add("EXT001", "error", node, "setattr on an official app module at import time (monkey patch).")
        for kw in node.keywords:
            if kw.arg == "ignore_permissions" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                self._permission_bypass(node)
        if isinstance(func, ast.Attribute) and func.attr == "sql" and self._root(func) == "frappe" and node.args:
            query = node.args[0]
            if isinstance(query, ast.JoinedStr) or (isinstance(query, ast.BinOp) and isinstance(query.op, (ast.Mod, ast.Add))) \
                    or (isinstance(query, ast.Call) and isinstance(query.func, ast.Attribute) and query.func.attr == "format"):
                self.add("SEC002", "error", node, "frappe.db.sql built with string formatting; pass values as "
                                                  "parameters (%s / %(name)s) instead.")
        self.generic_visit(node)

    def _permission_bypass(self, node):
        current = self.function_stack[-1] if self.function_stack else None
        if current and current["guest"]:
            self.add("SEC003", "error", node, "ignore_permissions inside a guest endpoint.")
        elif current and current["whitelisted"]:
            self.add("SEC003", "warning", node, "ignore_permissions inside a whitelisted method: confirm an explicit "
                                                "permission check runs first.")
        else:
            self.add("SEC004", "info", node, "ignore_permissions used; acceptable for system records only.")


def _imports(tree) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in OFFICIAL_MODULES:
                    names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in OFFICIAL_MODULES:
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
    return names | {"frappe"}


def _module_file(ws, package_parent: str, dotted: str) -> str | None:
    rel = package_parent + "/" + dotted.replace(".", "/") if package_parent else dotted.replace(".", "/")
    # Python'daki gibi paket (dizin/__init__.py) aynı adlı modül dosyasından önce gelir.
    for candidate in (rel + "/__init__.py", rel + ".py"):
        if ws.exists(candidate):
            return candidate
    return None


def _defines(ws, path: str, name: str):
    try:
        tree = ast.parse(ws.read_text(path))
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
    return None


def _resolve(ws, info, dotted: str):
    """`app.module.attr` yolunu bu uygulamada çözer; başka uygulamaya aitse None ('external')."""
    if not isinstance(dotted, str) or "." not in dotted:
        return "invalid", None
    if dotted.split(".")[0] != info["name"]:
        return "external", None
    module, attr = dotted.rsplit(".", 1)
    parent = info["package"].rsplit("/", 1)[0] if "/" in info["package"] else ""
    path = _module_file(ws, parent, module)
    if not path:
        return "missing_module", None
    node = _defines(ws, path, attr)
    return ("ok" if node else "missing_attr"), (path, node)


def check(ws, app_path: str, target: str | None, extension_points: dict | None = None) -> dict:
    info = locate_app(ws, app_path)
    data = inspect(ws, app_path)
    findings = []
    package = info["package"]
    hooks = parse_hooks(ws.read_text(package + "/hooks.py"))
    values, lines = hooks["values"], hooks["lines"]
    hooks_file = package + "/hooks.py"

    def add(rule, severity, message, file=hooks_file, line=None):
        findings.append({"rule": rule, "severity": severity, "file": file, "line": line, "message": message})

    # Python kaynakları (sözdizimi hedef Python'a göre yorumlanır; bkz. parse_python)
    target_python = app_min_python(ws, info)
    for rel in ws.walk(package, max_files=20000):
        if not rel.endswith(".py"):
            continue
        source = ws.read_text(rel)
        tree, status = parse_python(source, rel, target_python)
        if tree is None:
            if status == "unknown":
                add("PY002", "info", "Not parseable by the server's Python {}.{} (app requires {}); syntax unknown, "
                                     "only a text scan ran for this file".format(
                                         sys.version_info[0], sys.version_info[1],
                                         ">={}.{}".format(*target_python) if target_python else "an unknown version"),
                    rel)
                for found in text_rule_scan(source):
                    add(found["rule"], found["severity"], found["message"], rel, found["line"])
            else:
                add("PY001", "error", "Syntax error " + status[len("invalid: "):], rel)
            continue
        _Finder(rel, findings, _imports(tree)).visit(tree)

    # hooks: doc_events
    doc_events = values.get("doc_events")
    if isinstance(doc_events, dict):
        for doctype, events in doc_events.items():
            if doctype == "*":
                add("PERF001", "warning", "doc_events['*'] runs for every DocType write; scope it to the DocTypes you need.",
                    line=lines.get("doc_events"))
            for event, handlers in (events or {}).items() if isinstance(events, dict) else []:
                for handler in handlers if isinstance(handlers, list) else [handlers]:
                    state, _ = _resolve(ws, info, handler)
                    if state in ("missing_module", "missing_attr", "invalid"):
                        add("HOOK001", "error", "doc_events {}.{} handler {} not found in this app ({})".format(
                            doctype, event, handler, state), line=lines.get("doc_events"))
    # hooks: sınıf geçersiz kılma / genişletme
    for key in ("override_doctype_class", "extend_doctype_class"):
        mapping = values.get(key)
        if not isinstance(mapping, dict):
            continue
        for doctype, paths in mapping.items():
            for dotted in paths if isinstance(paths, list) else [paths]:
                state, found = _resolve(ws, info, dotted)
                if state != "ok":
                    if state != "external":
                        add("HOOK002", "error", "{} {} -> {} not found ({})".format(key, doctype, dotted, state),
                            line=lines.get(key))
                    continue
                path, node = found
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name in LIFECYCLE and \
                                "super" not in {n.func.id for n in ast.walk(item)
                                                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}:
                            add("EXT002", "warning", "{}.{} overrides a lifecycle hook without calling super(); the "
                                                     "official logic is skipped.".format(node.name, item.name),
                                path, item.lineno)
    if "override_doctype_class" in values:
        add("EXT003", "info", "override_doctype_class: when several apps override the same DocType only the last one "
                              "wins; prefer extend_doctype_class on v16 or doc_events.", line=lines.get(
                                  "override_doctype_class"))
    if "override_whitelisted_methods" in values:
        add("EXT004", "warning", "override_whitelisted_methods replaces a core/official endpoint; re-test it on "
                                 "every upgrade.", line=lines.get("override_whitelisted_methods"))
    # sürüme bağlı kurallar
    version_rules = []
    if "extend_doctype_class" in values:
        version_rules.append(_versioned("VER001", "extend_doctype_class", target, {"v15": False, "v16": True},
                                        lines.get("extend_doctype_class"), hooks_file))
    for test in data["tests"]:
        text = ws.read_text(test)
        if "FrappeTestCase" in text:
            version_rules.append(_versioned("VER002", "frappe.tests.utils.FrappeTestCase", target,
                                            {"v15": True, "v16": None}, None, test))
        if "IntegrationTestCase" in text:
            version_rules.append(_versioned("VER003", "frappe.tests.IntegrationTestCase", target,
                                            {"v15": None, "v16": True}, None, test))
    deps = (data.get("pyproject") or {}).get("frappe_dependencies") or {}
    if target and deps.get("frappe"):
        major = target[1:]
        spec = deps["frappe"]
        bounds = re.findall(r"(>=|<=|<|>|==|~=)\s*(\d+)", spec)
        excluded = any((op == "<" and int(num) <= int(major)) or (op == ">=" and int(num) > int(major))
                       for op, num in bounds)
        if excluded:
            add("VER004", "error", "pyproject frappe dependency {!r} excludes the target {}".format(spec, target),
                (info["repo"] or package) + "/pyproject.toml")
    # patches.txt
    listed = set()
    for entry in data["patches"]:
        listed.add(entry["entry"])
        if entry["section"] not in ("pre_model_sync", "post_model_sync"):
            add("MIG001", "error", "Unknown patches.txt section [{}]".format(entry["section"]),
                package + "/patches.txt", entry["line"])
        if entry["entry"].startswith("execute:"):
            add("MIG002", "warning", "Inline execute: patch; prefer a patch module with execute()",
                package + "/patches.txt", entry["line"])
            continue
        state, found = _resolve(ws, info, entry["entry"] + ".execute")
        if state not in ("ok", "external"):
            add("MIG003", "error", "patches.txt entry {} has no execute() ({})".format(entry["entry"], state),
                package + "/patches.txt", entry["line"])
    for rel in ws.walk(package, max_files=20000):
        parts = rel[len(package) + 1:].split("/")
        if "patches" in parts[:-1] and rel.endswith(".py") and not rel.endswith("__init__.py"):
            dotted = info["name"] + "." + rel[len(package) + 1:-3].replace("/", ".")
            if dotted not in listed:
                add("MIG004", "warning", "Patch module {} is not listed in patches.txt (it will never run)".format(
                    dotted), rel)
    # fixtures
    fixtures = values.get("fixtures")
    for item in fixtures if isinstance(fixtures, list) else []:
        name = item if isinstance(item, str) else item.get("dt") if isinstance(item, dict) else None
        has_filters = isinstance(item, dict) and bool(item.get("filters"))
        if name in ("Custom Field", "Property Setter", "Client Script", "Server Script") and not has_filters:
            add("FIX001", "warning", "fixtures exports every {} on the site, including other apps' records; add "
                                     "filters (e.g. module or name).".format(name), line=lines.get("fixtures"))
        if name == "Server Script":
            add("FIX002", "warning", "Server Script fixtures ship executable code outside version control review.",
                line=lines.get("fixtures"))
    # DocType JSON
    modules = set(data["modules"])
    by_name = {d.get("name"): d for d in data["doctypes"] if d.get("name")}
    for d in data["doctypes"]:
        _check_doctype(ws, d, modules, by_name, add)
    if data["doctypes"] and not data["tests"]:
        add("TST001", "warning", "No test_*.py files; DocType behaviour has no regression tests.", package)
    severities = {}
    for f in findings:
        severities[f["severity"]] = severities.get(f["severity"], 0) + 1
    return {"app": info["name"], "target_frappe": target or "unknown", "findings": findings,
            "version_rules": version_rules, "summary": severities,
            "not_checked": ["runtime behaviour (no code is executed)", "bench migrate / install on a real site",
                            "JavaScript and Vue sources", "translation completeness"],
            "extension_points_source": "contracts/frappe-extension-points.json" if extension_points else "builtin"}


def _versioned(rule, feature, target, support, line, file):
    if not target:
        return {"rule": rule, "feature": feature, "result": "unknown", "file": file, "line": line,
                "message": "Target Frappe version not given; compatibility is unknown."}
    supported = support.get(target)
    result = "unknown" if supported is None else ("ok" if supported else "error")
    message = {"ok": "{} is available on {}".format(feature, target),
               "error": "{} is not available on {}".format(feature, target),
               "unknown": "{} on {} was not verified".format(feature, target)}[result]
    return {"rule": rule, "feature": feature, "result": result, "file": file, "line": line, "message": message}


def _check_doctype(ws, d, modules, by_name, add):
    path = d.get("path")
    if d.get("error"):
        add("DOC000", "error", "DocType JSON is invalid", path)
        return
    meta = json.loads(ws.read_text(path))
    if modules and meta.get("module") not in modules:
        add("DOC001", "error", "module {!r} is not listed in modules.txt".format(meta.get("module")), path)
    seen = set()
    for field in [f for f in meta.get("fields", []) if isinstance(f, dict)]:
        name = field.get("fieldname")
        if field.get("fieldtype") in ("Section Break", "Column Break", "Tab Break") and not name:
            continue
        if not isinstance(name, str) or not _FIELDNAME.fullmatch(name):
            add("DOC002", "error", "invalid fieldname {!r}".format(name), path)
            continue
        if name in seen:
            add("DOC003", "error", "duplicate fieldname {}".format(name), path)
        seen.add(name)
        if name in RESERVED_FIELDS:
            add("DOC004", "error", "fieldname {} is reserved by Frappe".format(name), path)
        if field.get("fieldtype") in _TABLE_TYPES:
            child = by_name.get(field.get("options"))
            if child is None:
                add("DOC005", "info", "{} -> {} is not defined in this app (official or other app); confirm it is a "
                                      "child table".format(name, field.get("options")), path)
            elif not child.get("istable"):
                add("DOC006", "error", "{} -> {} is not a child table (istable)".format(name, field.get("options")), path)
    if meta.get("istable") and meta.get("permissions"):
        add("DOC007", "warning", "Child tables do not use their own permissions; they follow the parent.", path)
    if not meta.get("istable") and not meta.get("permissions"):
        add("DOC008", "warning", "No permission rules: only Administrator can use this DocType.", path)
