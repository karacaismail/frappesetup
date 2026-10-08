"""Frappe uygulama değişiklik planları: dosya içerikleri, özetler ve diff üretir; hiçbir şey yazmaz.

Şablonlar frappe/frappe boilerplate'ından türetilmiştir (version-15 b0b5b99, version-16 6b450a1:
frappe/utils/boilerplate.py, frappe/core/doctype/doctype/boilerplate/*._py). hooks.py yalnız ilgili
anahtar yoksa sona yeni atama eklenerek değiştirilir; anahtar zaten varsa dosya yeniden yazılmaz,
insanın birleştireceği parça döndürülür (yorum ve biçim kaybı olmasın diye).
"""
from __future__ import annotations

import ast
import datetime as _dt
import difflib
import json
import keyword
import pprint
import re
import sys

from .app_static import OFFICIAL_MODULES, classname, is_official, locate_app, parse_hooks, scrub
from .errors import KitError, ValidationError, WorkspaceError
from .schema import validate
from .util import sha256_hex
from .workspace import split_relative

MAX_PLAN_BYTES = 256 * 1024
_APP = {"type": "string", "pattern": r"[a-z][a-z0-9_]{1,63}"}
_TITLE = {"type": "string", "minLength": 1, "maxLength": 80, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ._()&'-]{0,79}"}
_DOCTYPE = {"type": "string", "minLength": 2, "maxLength": 61, "pattern": r"[A-Z][A-Za-z0-9 ]{1,60}"}
_MODULE = {"type": "string", "minLength": 1, "maxLength": 61, "pattern": r"[A-Za-z][A-Za-z0-9 ]{0,60}"}
_DOTTED = {"type": "string", "maxLength": 200, "pattern": r"[a-z_][a-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+"}
_VERSION = {"type": "string", "enum": ["v15", "v16"]}
_FIELDTYPES = ["Data", "Int", "Float", "Currency", "Percent", "Check", "Date", "Datetime", "Time", "Duration", "Link",
               "Dynamic Link", "Select", "Small Text", "Text", "Long Text", "Text Editor", "Markdown Editor", "Code",
               "JSON", "Attach", "Attach Image", "Phone", "Rating", "Color", "Read Only", "Table", "Table MultiSelect",
               "Section Break", "Column Break", "Tab Break", "HTML", "Signature", "Geolocation"]
_FIELD = {"type": "object", "additionalProperties": False, "required": ["fieldname", "fieldtype", "label"],
          "properties": {"fieldname": {"type": "string", "pattern": r"[a-z][a-z0-9_]{0,63}"},
                         "fieldtype": {"type": "string", "enum": _FIELDTYPES},
                         "label": {"type": "string", "minLength": 1, "maxLength": 140},
                         "options": {"type": "string", "maxLength": 1000},
                         "reqd": {"type": "boolean"}, "in_list_view": {"type": "boolean"},
                         "unique": {"type": "boolean"}, "read_only": {"type": "boolean"},
                         "default": {"type": "string", "maxLength": 140}}}
_PERM = {"type": "object", "additionalProperties": False, "required": ["role"],
         "properties": dict({"role": {"type": "string", "minLength": 1, "maxLength": 140}},
                            **{k: {"type": "boolean"} for k in ("read", "write", "create", "delete", "submit", "cancel",
                                                                 "amend", "report", "export", "share", "print",
                                                                 "email")})}
_EVENTS = ["before_validate", "validate", "before_insert", "after_insert", "before_save", "on_update", "before_submit",
           "on_submit", "before_cancel", "on_cancel", "on_trash", "after_delete", "on_change", "on_update_after_submit",
           "before_rename", "after_rename"]


def _obj(required, **props):
    return {"type": "object", "additionalProperties": False, "required": list(required), "properties": props}


# Üretilen Python/TOML dosyalarına giren serbest metin: denetim karakteri, tırnak ve ters bölü yok.
_PLAIN = r"[^\x00-\x1f\x7f\"\\]{1,300}"
# write_file: yalnız kaynak/metin dosyaları ve boyut sınırı (MAX_PLAN_BYTES içinde kalır).
WRITE_FILE_SUFFIXES = (".py", ".js", ".ts", ".vue", ".json", ".html", ".css", ".scss", ".md", ".txt", ".csv", ".po",
                       ".pot")
WRITE_FILE_MAX = 200 * 1024
KIND_SCHEMAS = {
    "new_app": _obj(["kind", "app_name", "app_title", "publisher", "email", "description", "license", "target_frappe"],
                    kind={"type": "string", "const": "new_app"}, app_name=_APP, app_title=_TITLE,
                    publisher={"type": "string", "minLength": 1, "maxLength": 140, "pattern": _PLAIN},
                    email={"type": "string", "maxLength": 140,
                           "pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"},
                    description={"type": "string", "minLength": 1, "maxLength": 300, "pattern": _PLAIN},
                    license={"type": "string", "pattern": r"[A-Za-z0-9.+-]{2,40}"}, target_frappe=_VERSION),
    "new_doctype": _obj(["kind", "module", "doctype", "fields"], kind={"type": "string", "const": "new_doctype"},
                        module=_MODULE, doctype=_DOCTYPE,
                        fields={"type": "array", "minItems": 1, "maxItems": 150, "items": _FIELD},
                        istable={"type": "boolean"}, naming_rule={"type": "string", "maxLength": 140},
                        permissions={"type": "array", "maxItems": 20, "items": _PERM}, target_frappe=_VERSION),
    "add_child_table": _obj(["kind", "module", "parent_doctype", "child_doctype", "table_fieldname", "label", "fields"],
                            kind={"type": "string", "const": "add_child_table"}, module=_MODULE,
                            parent_doctype=_DOCTYPE, child_doctype=_DOCTYPE,
                            table_fieldname={"type": "string", "pattern": r"[a-z][a-z0-9_]{0,63}"},
                            label={"type": "string", "minLength": 1, "maxLength": 140},
                            fields={"type": "array", "minItems": 1, "maxItems": 100, "items": _FIELD},
                            target_frappe=_VERSION),
    "add_patch": _obj(["kind", "patch_name", "description", "section"], kind={"type": "string", "const": "add_patch"},
                      patch_name={"type": "string", "pattern": r"[a-z][a-z0-9_]{2,80}"},
                      description={"type": "string", "minLength": 3, "maxLength": 200, "pattern": _PLAIN},
                      section={"type": "string", "enum": ["pre_model_sync", "post_model_sync"]},
                      folder={"type": "string", "pattern": r"v[0-9]{1,2}_[0-9]{1,2}"}),
    "add_fixture_filter": _obj(["kind", "doctype", "filters"], kind={"type": "string", "const": "add_fixture_filter"},
                               doctype={"type": "string", "enum": ["Custom Field", "Property Setter", "Role",
                                                                   "Custom DocPerm", "Workflow", "Workflow State",
                                                                   "Workflow Action Master", "Print Format",
                                                                   "Report", "Client Script"]},
                               filters={"type": "array", "minItems": 1, "maxItems": 10,
                                        "items": {"type": "array", "minItems": 3, "maxItems": 3,
                                                  "items": {"type": ["string", "array"], "maxLength": 140}}}),
    "add_doc_event": _obj(["kind", "doctype", "event", "handler"], kind={"type": "string", "const": "add_doc_event"},
                          doctype=_DOCTYPE, event={"type": "string", "enum": _EVENTS}, handler=_DOTTED),
    "extend_doctype_class": _obj(["kind", "doctype", "base_class", "mode", "target_frappe"],
                                 kind={"type": "string", "const": "extend_doctype_class"}, doctype=_DOCTYPE,
                                 base_class=_DOTTED, mode={"type": "string", "enum": ["extend", "override"]},
                                 target_frappe=_VERSION),
    "add_test": _obj(["kind", "doctype", "target_frappe"], kind={"type": "string", "const": "add_test"},
                     doctype=_DOCTYPE, target_frappe=_VERSION),
    "write_file": _obj(["kind", "path", "content", "purpose"], kind={"type": "string", "const": "write_file"},
                       path={"type": "string", "minLength": 1, "maxLength": 300,
                             "pattern": r"[A-Za-z0-9_][A-Za-z0-9_./-]*"},
                       content={"type": "string", "maxLength": WRITE_FILE_MAX},
                       purpose={"type": "string", "minLength": 3, "maxLength": 200, "pattern": _PLAIN},
                       expected_sha256={"type": ["string", "null"], "pattern": r"[0-9a-f]{64}"}),
}
# Kontrat kimliği → değişiklik türü (contracts/frappe-app-operations.json `params` bu şemalardır).
OPERATION_KINDS = {"app.scaffold": "new_app", "doctype.create": "new_doctype", "child_table.create": "add_child_table",
                   "patch.create": "add_patch", "fixtures.filter": "add_fixture_filter",
                   "hooks.doc_event": "add_doc_event", "hooks.extend_class": "extend_doctype_class",
                   "tests.scaffold": "add_test", "app_file.write": "write_file"}


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.000000")


def as_frappe_json(data) -> str:
    """Frappe dışa aktarımıyla aynı biçim: indent=1, sıralı anahtar."""
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False, separators=(",", ": ")) + "\n"


_DENIED_DIRS = {"sites", "env", "logs", "node_modules", "__pycache__"}
_DENIED_NAME = re.compile(
    r"(?i)(site_config\.json|common_site_config\.json|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|credentials?([._-].*)?\.json|"
    r"secrets?([._-].*)?|.*\.(pem|key|p12|pfx|crt|sqlite3?|db|sql|sql\.gz|pyc|so|dylib|exe|sh))")
def check_readable_path(path: str) -> list:
    """Okuma için de gizli (.git, .env), çalışma zamanı dizini ve secret/config/ikili dosya yolu kapalıdır.
    Resmi uygulama kodu okunabilir (genişletme için hedef kodun görülmesi gerekir)."""
    parts = split_relative(path)
    for part in parts:
        if part.startswith(".") or part.casefold() in _DENIED_DIRS:
            raise WorkspaceError("Path is not readable through press-ai: " + path, code="denied_path")
    if _DENIED_NAME.fullmatch(parts[-1]):
        raise WorkspaceError("File name looks like a secret, config, database or binary: " + path, code="denied_path")
    return parts


def official_owner(ws, path: str) -> str | None:
    """Yol resmi bir uygulamanın deposu/paketi içindeyse o dizini döndürür (hooks.py ile tanınır)."""
    parts = split_relative(path)
    root_name = ws.root.rstrip("/").rsplit("/", 1)[-1]
    if is_official(root_name) and (ws.exists("hooks.py") or ws.exists(root_name + "/hooks.py")):
        return "."
    for index, name in enumerate(parts[:-1]):
        if is_official(name):
            prefix = "/".join(parts[:index + 1])
            if ws.exists(prefix + "/hooks.py") or ws.exists(prefix + "/" + name + "/hooks.py"):
                return prefix
    return None


def check_canonical_case(ws, path: str) -> None:
    """Var olan her yol bileşeni diskteki adla birebir yazılmalı. Harf duyarsız dosya sisteminde `Erpnext/ERPNEXT`
    ya da `DocType/...` gerçek dizine çözülür; adlara dayanan korumalar böylece atlatılamaz."""
    parts = split_relative(path)
    for index, name in enumerate(parts):
        entries = ws.entries(parts[:index])
        if entries is None or name in entries:
            if entries is None:
                return
            continue
        if any(entry.casefold() == name.casefold() for entry in entries):
            raise WorkspaceError("Path case differs from the name on disk: " + path, code="case_mismatch")
        return  # bu bileşen yok: yeni dosya/dizin


def core_app_name(ws, owner: str) -> str:
    return ws.root.rstrip("/").rsplit("/", 1)[-1] if owner == "." else owner.rsplit("/", 1)[-1]


def check_mutation_path(ws, path: str) -> str | None:
    """Her app mutasyonunda mutlak sınır: workspace içi, diskteki adla birebir, gizli/secret/state/çalışma zamanı yolu
    değil. Dönüş: yol orijinal core (resmi uygulama) içindeyse o uygulamanın adı, değilse None. Core yolu burada
    reddedilmez; çağıran onu varsayılan-ret akışına sokar (önce uyarı, aynı isteğin açık tekrarı, CORE onayı)."""
    check_canonical_case(ws, path)
    parts = split_relative(path)
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part.startswith(".") and not (last and part == ".gitkeep"):
            raise WorkspaceError("Hidden paths (.git, .env, .github, ...) are not writable: " + path, code="denied_path")
        if part.casefold() in _DENIED_DIRS:
            raise WorkspaceError("Path is inside a bench runtime or cache directory: " + path, code="denied_path")
    if _DENIED_NAME.fullmatch(parts[-1]):
        raise WorkspaceError("File name looks like a secret, config, database or binary: " + path, code="denied_path")
    owner = official_owner(ws, path)
    return core_app_name(ws, owner) if owner else None


class Plan:
    def __init__(self, ws):
        self.ws = ws
        self.files = []
        self.manual = []
        self.followups = []
        self.notes = []
        self.unchecked = []
        self.core_files = []

    def _core(self, path, app):
        if app and all(f["path"] != path for f in self.core_files):
            self.core_files.append({"path": path, "app": app})

    def create(self, path, content):
        app = check_mutation_path(self.ws, path)  # Öneri aşamasında da workspace dışı ve yasak yol reddedilir.
        if self.ws.exists(path):
            raise WorkspaceError("Refusing to overwrite existing file " + path, code="conflict")
        if any(f["path"] == path for f in self.files):
            return
        self.files.append({"path": path, "action": "create", "base_sha256": None, "content": content,
                           "sha256": sha256_hex(content.encode("utf-8"))})
        self._core(path, app)

    def create_if_missing(self, path, content):
        if not self.ws.exists(path):
            self.create(path, content)

    def modify(self, path, new_content):
        app = check_mutation_path(self.ws, path)
        old = self.ws.read_text(path)
        if old == new_content:
            return
        self.files.append({"path": path, "action": "modify", "base_sha256": sha256_hex(old.encode("utf-8")),
                           "content": new_content, "sha256": sha256_hex(new_content.encode("utf-8")),
                           "_old": old})
        self._core(path, app)

    def core(self) -> dict | None:
        """Orijinal core dosyalarına dokunan değişikliğin özeti; özel uygulama dosyaları hiçbir zaman core değildir."""
        if not self.core_files:
            return None
        return {"apps": sorted({f["app"] for f in self.core_files}), "files": [f["path"] for f in self.core_files]}

    def result(self) -> dict:
        diff = []
        for f in self.files:
            old = f.pop("_old", "") if f["action"] == "modify" else ""
            diff.extend(difflib.unified_diff(old.splitlines(True), f["content"].splitlines(True),
                                             "a/" + f["path"] if old else "/dev/null", "b/" + f["path"]))
        size = sum(len(f["content"].encode("utf-8")) for f in self.files)
        if size > MAX_PLAN_BYTES:
            raise KitError("Plan is too large to review ({} bytes); split the change".format(size),
                           code="proposal_too_large")
        return {"files": self.files, "diff": "".join(diff), "manual_merge": self.manual,
                "human_commands": self.followups, "notes": self.notes, "unchecked": self.unchecked,
                "core": self.core()}


def _hooks_append(plan, package, key, value_source, snippet_note):
    """hooks.py'ye `key = ...` ekler; anahtar varsa birleştirme parçasını insana bırakır."""
    path = package + "/hooks.py"
    text = plan.ws.read_text(path)
    hooks = parse_hooks(text)
    if key in hooks["values"]:
        plan.manual.append({"file": path, "line": hooks["lines"].get(key),
                            "instruction": "`{}` already exists; merge this entry by hand ({})".format(key, snippet_note),
                            "snippet": value_source})
        return
    plan.modify(path, text.rstrip("\n") + "\n\n" + "{} = {}\n".format(key, value_source))


def _py_literal(value) -> str:
    """hooks.py'ye yazılacak Python sabiti (dict/list/str); geri okunabilirliği parse_hooks ile sınanır."""
    text = pprint.pformat(value, indent=1, width=100, sort_dicts=False)
    if ast.literal_eval(text) != value:
        raise KitError("Could not render a hooks literal", code="internal")
    return text


def _controller(publisher: str, doctype: str) -> str:
    year = _dt.date.today().year
    return ("# Copyright (c) {year}, {publisher} and contributors\n"
            "# For license information, please see license.txt\n\n"
            "# import frappe\nfrom frappe.model.document import Document\n\n\n"
            "class {cls}(Document):\n\tpass\n").format(year=year, publisher=publisher, cls=classname(doctype))


def _test(publisher: str, doctype: str, target: str) -> str:
    year = _dt.date.today().year
    head = "# Copyright (c) {}, {} and Contributors\n# See license.txt\n\n# import frappe\n".format(year, publisher)
    if target == "v15":
        return head + ("from frappe.tests.utils import FrappeTestCase\n\n\n"
                       "class Test{}(FrappeTestCase):\n\tpass\n").format(classname(doctype))
    return head + ("from frappe.tests import IntegrationTestCase\n\n\n"
                   "EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. [\"User\"]\n"
                   "IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. [\"User\"]\n\n\n"
                   "class IntegrationTest{}(IntegrationTestCase):\n\tpass\n").format(classname(doctype))


def _doctype_json(module, doctype, fields, istable, naming_rule, permissions) -> dict:
    now = _now()
    meta = {
        "actions": [], "creation": now, "doctype": "DocType", "engine": "InnoDB",
        "field_order": [f["fieldname"] for f in fields],
        "fields": [dict({k: v for k, v in f.items() if k not in ("reqd", "in_list_view", "unique", "read_only")},
                        **{k: 1 for k in ("reqd", "in_list_view", "unique", "read_only") if f.get(k)}) for f in fields],
        "index_web_pages_for_search": 1, "links": [], "modified": now, "modified_by": "Administrator",
        "module": module, "name": doctype, "owner": "Administrator", "permissions": [],
        "sort_field": "modified", "sort_order": "DESC", "states": [],
    }
    if istable:
        meta.update(istable=1, editable_grid=1)
    else:
        meta["permissions"] = [dict({"role": p["role"]}, **{k: 1 for k, v in p.items() if k != "role" and v})
                               for p in permissions]
        if naming_rule:
            meta["autoname"] = naming_rule
    return meta


def _publisher(ws, package) -> str:
    """Yorum satırına girecek yayıncı adı: satır sonu ve denetim karakterleri temizlenir."""
    values = parse_hooks(ws.read_text(package + "/hooks.py"))["values"]
    publisher = values.get("app_publisher")
    if not isinstance(publisher, str) or not publisher.strip():
        return "the app publisher"
    return re.sub(r"[\x00-\x1f\x7f]+", " ", publisher).strip()[:140]


def _lit(text: str) -> str:
    """Python ve TOML için güvenli çift tırnaklı dize (JSON dize sözdizimi her ikisinde de geçerlidir)."""
    return json.dumps(text, ensure_ascii=False)


def _module_dir(ws, info, module) -> str:
    modules = [m.strip() for m in ws.read_text(info["package"] + "/modules.txt").splitlines() if m.strip()]
    if module not in modules:
        raise ValidationError("Module {!r} is not in modules.txt ({})".format(module, ", ".join(modules) or "empty"))
    return info["package"] + "/" + scrub(module)


def _existing_doctypes(ws, info) -> dict:
    found = {}
    for rel in ws.walk(info["package"], max_files=20000):
        parts = rel[len(info["package"]) + 1:].split("/")
        if len(parts) == 4 and parts[1] == "doctype" and parts[3] == parts[2] + ".json":
            try:
                found[json.loads(ws.read_text(rel)).get("name")] = rel
            except ValueError:
                continue
    return found


def _check_fields(fields, doctypes_in_app, child_ok=True):
    names = [f["fieldname"] for f in fields]
    if len(names) != len(set(names)):
        raise ValidationError("Duplicate fieldnames in the request")
    from .app_static import RESERVED_FIELDS
    reserved = sorted(set(names) & RESERVED_FIELDS)
    if reserved:
        raise ValidationError("Reserved fieldnames: " + ", ".join(reserved))
    for f in fields:
        if f["fieldtype"] in ("Link", "Dynamic Link", "Table", "Table MultiSelect", "Select") and not f.get("options"):
            raise ValidationError("{} needs options".format(f["fieldname"]))
        if f["fieldtype"] in ("Table", "Table MultiSelect") and not child_ok:
            raise ValidationError("Child tables cannot contain Table fields")


# -- üreticiler ----------------------------------------------------------------------------------
def _new_app(plan, ws, app_path, c):
    name = c["app_name"]
    if is_official(name) or keyword.iskeyword(name):
        raise ValidationError("App name collides with an official app or a Python keyword")
    if app_path.rstrip("/").rsplit("/", 1)[-1] != name:
        raise ValidationError("For new_app, app_path must end with the app name")
    if ws.exists(app_path):
        raise WorkspaceError(app_path + " already exists", code="conflict")
    pkg = app_path.rstrip("/") + "/" + name
    py = ">=3.10" if c["target_frappe"] == "v15" else ">=3.14"
    frappe_dep = "~=15.0.0" if c["target_frappe"] == "v15" else "~=16.0.0"
    plan.create(app_path + "/pyproject.toml", (
        '[project]\nname = {n}\nauthors = [\n    {{ name = {p}, email = {e}}}\n]\ndescription = {d}\n'
        'requires-python = "{py}"\nreadme = "README.md"\ndynamic = ["version"]\ndependencies = [\n'
        '    # "frappe{dep}" # Installed and managed by bench.\n]\n\n[build-system]\n'
        'requires = ["flit_core >=3.4,<4"]\nbuild-backend = "flit_core.buildapi"\n').format(
        n=_lit(name), p=_lit(c["publisher"]), e=_lit(c["email"]), d=_lit(c["description"]), py=py, dep=frappe_dep))
    plan.create(app_path + "/README.md", "### {}\n\n{}\n\n#### License\n\n{}\n".format(
        c["app_title"], c["description"], c["license"]))
    plan.create(app_path + "/license.txt", "SPDX-License-Identifier: {}\n".format(c["license"]))
    plan.create(pkg + "/__init__.py", '__version__ = "0.0.1"\n')
    plan.create(pkg + "/hooks.py", (
        'app_name = {n}\napp_title = {t}\napp_publisher = {p}\napp_description = {d}\n'
        'app_email = {e}\napp_license = {l}\n\n# Apps\n# ------------------\n\n# required_apps = []\n').format(
        n=_lit(name), t=_lit(c["app_title"]), p=_lit(c["publisher"]), d=_lit(c["description"]), e=_lit(c["email"]),
        l=_lit(c["license"])))
    plan.create(pkg + "/modules.txt", c["app_title"] + "\n")
    plan.create(pkg + "/patches.txt", "[pre_model_sync]\n# Patches added in this section will be executed before "
                                      "doctypes are migrated\n\n[post_model_sync]\n# Patches added in this section "
                                      "will be executed after doctypes are migrated\n")
    for sub in (scrub(c["app_title"]), "config", "templates", "templates/pages", "patches"):
        plan.create(pkg + "/" + sub + "/__init__.py", "")
    plan.create(pkg + "/public/.gitkeep", "")
    plan.notes.append("Mirrors the core files of `bench new-app` for {}; bench also writes CI, pre-commit, .gitignore "
                      "and the full license text. Prefer `bench new-app {}` where bench is available.".format(
                          c["target_frappe"], name))
    plan.notes.append("license.txt only carries the SPDX identifier you chose; add the full license text.")
    plan.followups += ["bench get-app {} (or keep it under apps/) and bench --site <site> install-app {}".format(
        app_path, name), "bench --site <site> migrate"]


def _new_doctype(plan, ws, info, c, target):
    existing = _existing_doctypes(ws, info)
    if c["doctype"] in existing:
        raise WorkspaceError("DocType {} already exists".format(c["doctype"]), code="conflict")
    _check_fields(c["fields"], existing, child_ok=not c.get("istable"))
    mdir = _module_dir(ws, info, c["module"])
    plan.create_if_missing(mdir + "/__init__.py", "")
    plan.create_if_missing(mdir + "/doctype/__init__.py", "")
    folder = mdir + "/doctype/" + scrub(c["doctype"])
    meta = _doctype_json(c["module"], c["doctype"], c["fields"], c.get("istable"), c.get("naming_rule"),
                         c.get("permissions") or [])
    publisher = _publisher(ws, info["package"])
    plan.create(folder + "/__init__.py", "")
    plan.create(folder + "/" + scrub(c["doctype"]) + ".json", as_frappe_json(meta))
    plan.create(folder + "/" + scrub(c["doctype"]) + ".py", _controller(publisher, c["doctype"]))
    plan.notes.append("Schema and an empty controller (pass) only; validation and business rules are not generated.")
    if not c.get("istable"):
        if target:
            plan.create(folder + "/test_" + scrub(c["doctype"]) + ".py", _test(publisher, c["doctype"], target))
        else:
            plan.notes.append("No target_frappe given: test file skipped (v15 and v16 use different test bases).")
        if not c.get("permissions"):
            plan.notes.append("No permission rules: only Administrator can use the DocType until roles are added.")
    for f in c["fields"]:
        if f["fieldtype"] in ("Table", "Table MultiSelect") and f["options"] not in existing:
            plan.notes.append("{} -> {} must be a child table (istable) in this or a required app".format(
                f["fieldname"], f["options"]))
    plan.followups += ["bench --site <site> migrate  # developer_mode on a development site",
                       "bench --site <site> run-tests --app {} --doctype \"{}\"".format(info["name"], c["doctype"])]


def _add_child_table(plan, ws, info, c, target):
    existing = _existing_doctypes(ws, info)
    parent_path = existing.get(c["parent_doctype"])
    if parent_path is None:
        raise ValidationError("Parent DocType {} is not defined in this app. Official DocTypes are extended with a "
                              "Custom Field fixture, not by editing their JSON.".format(c["parent_doctype"]))
    _new_doctype(plan, ws, info, {"module": c["module"], "doctype": c["child_doctype"], "fields": c["fields"],
                                  "istable": True}, target)
    meta = json.loads(ws.read_text(parent_path))
    if any(f.get("fieldname") == c["table_fieldname"] for f in meta.get("fields", [])):
        raise ValidationError("Parent already has a field named " + c["table_fieldname"])
    meta.setdefault("fields", []).append({"fieldname": c["table_fieldname"], "fieldtype": "Table",
                                         "label": c["label"], "options": c["child_doctype"]})
    meta.setdefault("field_order", []).append(c["table_fieldname"])
    meta["modified"] = _now()
    plan.modify(parent_path, as_frappe_json(meta))


def _add_patch(plan, ws, info, c, target):
    package = info["package"]
    folder = package + "/patches" + ("/" + c["folder"] if c.get("folder") else "")
    plan.create_if_missing(package + "/patches/__init__.py", "")
    if c.get("folder"):
        plan.create_if_missing(folder + "/__init__.py", "")
    path = folder + "/" + c["patch_name"] + ".py"
    plan.create(path, 'import frappe\n\n\ndef execute():\n\t"""{}"""\n\n\t# Write your patch here.\n\tpass\n'.format(
        c["description"].replace('"""', "'''")))
    dotted = info["name"] + ".patches." + ((c["folder"] + ".") if c.get("folder") else "") + c["patch_name"]
    patches_path = package + "/patches.txt"
    text = ws.read_text(patches_path) if ws.exists(patches_path) else ""
    if dotted in text.split():
        raise WorkspaceError("Patch already listed in patches.txt", code="conflict")
    if ws.exists(patches_path):
        plan.modify(patches_path, _insert_patch(text, dotted, c["section"]))
    else:
        plan.create(patches_path, "[{}]\n{}\n".format(c["section"], dotted))
    plan.notes.append("Patches run once per site during migrate; make execute() idempotent and safe on large tables.")
    plan.followups.append("bench --site <site> migrate")


def _insert_patch(text: str, dotted: str, section: str) -> str:
    lines = text.splitlines()
    header = "[{}]".format(section)
    if header not in [l.strip() for l in lines]:
        return text.rstrip("\n") + "\n\n{}\n{}\n".format(header, dotted)
    start = [l.strip() for l in lines].index(header)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip().startswith("[") and lines[index].strip().endswith("]"):
            end = index
            break
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, dotted)
    return "\n".join(lines) + "\n"


def _add_fixture_filter(plan, ws, info, c, target):
    entry = {"dt": c["doctype"], "filters": c["filters"]}
    _hooks_append(plan, info["package"], "fixtures", _py_literal([entry]), "add this dict to the fixtures list")
    plan.followups.append("bench --site <site> export-fixtures --app {}".format(info["name"]))
    plan.notes.append("Fixtures are re-imported on every migrate; keep filters narrow so other apps' records are "
                      "not exported.")


def _add_doc_event(plan, ws, info, c, target):
    handler = c["handler"]
    if handler.split(".")[0] != info["name"]:
        raise ValidationError("Handler must live in this app ({}.*)".format(info["name"]))
    if handler.count(".") < 2:
        # `app.func` paketin yanına app.py üretirdi; işleyici bir modülde olmalı: app.modul.func.
        raise ValidationError("Handler needs at least app.module.function (e.g. {}.events.sales_invoice.validate)".format(
            info["name"]))
    module, func = handler.rsplit(".", 1)
    parent = info["package"].rsplit("/", 1)[0] if "/" in info["package"] else ""
    rel = (parent + "/" if parent else "") + module.replace(".", "/") + ".py"
    if ws.exists(rel):
        source = ws.read_text(rel)
        if re.search(r"^def {}\(".format(re.escape(func)), source, re.M) is None:
            plan.modify(rel, source.rstrip("\n") + "\n\n\ndef {}(doc, method=None):\n\t\"\"\"{} {}.\"\"\"\n\tpass\n"
                        .format(func, c["doctype"], c["event"]))
    else:
        directory = rel.rsplit("/", 1)[0]
        package_dir = info["package"]
        if directory != package_dir:
            for step in directory[len(package_dir) + 1:].split("/"):
                package_dir += "/" + step
                plan.create_if_missing(package_dir + "/__init__.py", "")
        plan.create(rel, "import frappe\n\n\ndef {}(doc, method=None):\n\t\"\"\"{} {}.\"\"\"\n\tpass\n".format(
            func, c["doctype"], c["event"]))
    _hooks_append(plan, info["package"], "doc_events", _py_literal({c["doctype"]: {c["event"]: handler}}),
                  "add the event under doc_events")
    plan.notes.append("The handler is a stub (pass): it registers the hook only; the business logic is still to be "
                      "written and tested by the developer.")
    plan.notes.append("doc_events run inside the document transaction: raise frappe.ValidationError to stop a save, "
                      "avoid commits and slow external calls.")


def _extend_class(plan, ws, info, c, target):
    if c["mode"] == "extend" and target != "v16":
        raise ValidationError("extend_doctype_class exists only on Frappe v16 (frappe/model/base_document.py); on v15 "
                              "use mode=override with super() or doc_events")
    base_module, base_cls = c["base_class"].rsplit(".", 1)
    if base_cls != classname(c["doctype"]):
        plan.notes.append("Base class name {} differs from the DocType's controller class {}; verify the path.".format(
            base_cls, classname(c["doctype"])))
    module_rel = info["package"] + "/overrides"
    plan.create_if_missing(module_rel + "/__init__.py", "")
    file_rel = module_rel + "/" + scrub(c["doctype"]) + ".py"
    if c["mode"] == "override":
        cls = "Custom" + classname(c["doctype"])
        body = ("from {mod} import {base}\n\n\nclass {cls}({base}):\n\tdef validate(self):\n"
                "\t\tif hasattr(super(), \"validate\"):\n\t\t\tsuper().validate()\n"
                "\t\t# Extra validation for this app goes here.\n").format(mod=base_module, base=base_cls, cls=cls)
        key, value = "override_doctype_class", _py_literal({c["doctype"]: "{}.overrides.{}.{}".format(
            info["name"], scrub(c["doctype"]), cls)})
        plan.notes.append("override_doctype_class: if several apps override {} only the last installed app wins; "
                          "v16 rejects a class that is not a subclass of the original.".format(c["doctype"]))
    else:
        cls = classname(c["doctype"]) + "Extension"
        body = ("class {cls}:\n\t\"\"\"Mixin placed before the {dt} controller in the MRO (Frappe v16).\"\"\"\n\n"
                "\tdef validate(self):\n\t\tif hasattr(super(), \"validate\"):\n\t\t\tsuper().validate()\n"
                "\t\t# Extra validation for this app goes here.\n").format(cls=cls, dt=c["doctype"])
        key, value = "extend_doctype_class", _py_literal({c["doctype"]: ["{}.overrides.{}.{}".format(
            info["name"], scrub(c["doctype"]), cls)]})
    plan.create(file_rel, body)
    plan.notes.append("The class is a stub: validate() only calls super(); the extra behaviour is still to be written "
                      "and tested by the developer against the target app version.")
    _hooks_append(plan, info["package"], key, value, "add the mapping under " + key)
    plan.followups += ["bench --site <site> clear-cache", "bench --site <site> run-tests --app {}".format(info["name"])]


def _add_test(plan, ws, info, c, target):
    path = _existing_doctypes(ws, info).get(c["doctype"])
    if path is None:
        raise ValidationError("DocType {} is not defined in this app".format(c["doctype"]))
    folder = path.rsplit("/", 1)[0]
    plan.create(folder + "/test_" + scrub(c["doctype"]) + ".py", _test(_publisher(ws, info["package"]), c["doctype"],
                                                                       c["target_frappe"]))
    plan.followups.append("bench --site <site> run-tests --app {} --doctype \"{}\"".format(info["name"], c["doctype"]))


_BLOCKING_RULES = {"SEC002"}  # güvenlik; özel koddaki EXT001 normal uyarıdır (özel geliştirme yetkili)
_DOCTYPE_JSON = re.compile(r"(?:^|/)doctype/([^/]+)/\1\.json$", re.I)
_PERMISSION_FIXTURE = re.compile(r"(?i)(?:^|/)fixtures/[^/]*(docperm|role)[^/]*\.json$")


def _roles(perms) -> list:
    return sorted({str(p["role"]) for p in perms if isinstance(p, dict) and p.get("role")}) if isinstance(perms, list) \
        else []


def _note_permission_change(plan, ws, rel, content, current_sha):
    """Özel geliştirme yetkilidir: DocType izinleri ve izin/rol fixture'ları engellenmez. Onaylayan insan görsün diye
    önizlemeye not düşülür; Guest ve All rolleri kaydı herkese açar."""
    if _PERMISSION_FIXTURE.search(rel):
        plan.notes.append("Permission or role fixture {} is imported on migrate/install; review its rows before "
                          "approving.".format(rel))
        return
    if not _DOCTYPE_JSON.search(rel):
        return
    try:
        new = json.loads(content)
        old = json.loads(ws.read_text(rel)) if current_sha is not None else {}
    except ValueError:
        return  # JSON hatası ayrıca raporlanır
    new_perms = new.get("permissions") if isinstance(new, dict) else None
    old_perms = old.get("permissions") if isinstance(old, dict) else None
    if (new_perms or []) == (old_perms or []):
        return
    after = _roles(new_perms)
    text = "DocType permission rows change in {} (roles before: {}; after: {}).".format(
        rel, ", ".join(_roles(old_perms)) or "none", ", ".join(after) or "none")
    if any(role.casefold() == "guest" for role in after):
        text += " Guest means visitors who are not logged in."
    if any(role.casefold() == "all" for role in after):
        text += " All means every user account."
    plan.notes.append(text + " Custom development is allowed; review the rows before approving.")


def _write_file(plan, ws, info, c, target, app_path):
    """Geliştiricinin yazdığı tek kaynak dosyası: metin olarak alınır, ast/json ile yalnız sözdizimi denetlenir;
    kod çalıştırılmaz ve import edilmez. Gizli/secret/state yolu ve ikili dosya yazılmaz; orijinal core dosyası core
    akışına girer (varsayılan ret, uyarı, açık tekrar, CORE onayı). Özel koddaki resmi modül yaması (EXT001) normal
    yetkili akışta kalır; önizlemede risk uyarısı olur."""
    rel = app_path.rstrip("/") + "/" + c["path"]
    split_relative(c["path"])
    if not rel.endswith(WRITE_FILE_SUFFIXES):
        raise ValidationError("write_file accepts source and text files only: " + ", ".join(WRITE_FILE_SUFFIXES))
    content = c["content"]
    if "\x00" in content or len(content.encode("utf-8")) > WRITE_FILE_MAX:
        raise ValidationError("Content must be text without NUL and at most {} bytes".format(WRITE_FILE_MAX))
    check_mutation_path(ws, rel)
    current = ws.sha256(rel)
    if current is not None and "expected_sha256" not in c:
        # Eski bir okumaya dayanan tam içerik araya giren düzenlemeyi sessizce geri almasın.
        raise WorkspaceError("File exists: pass expected_sha256 from app_inspect files (content and hash come from "
                             "the same read): " + rel, code="conflict")
    expected = c.get("expected_sha256")
    if expected is None and current is not None:
        raise WorkspaceError("File exists but expected_sha256 is null (new file expected): " + rel, code="conflict")
    if expected is not None and expected != current:
        raise WorkspaceError("File changed since it was read (expected_sha256 differs): " + rel, code="conflict")
    _note_permission_change(plan, ws, rel, content, current)
    if "[REDACTED]" in content and (current is None or "[REDACTED]" not in ws.read_text(rel)):
        # Maskelenmiş bir okumanın geri yazılması dosyayı bozar; içerik app_inspect files ile birebir okunur.
        raise ValidationError("Content contains [REDACTED], which the current file does not: read the file again "
                              "with app_inspect files and send the exact text")
    findings = []
    syntax = "not_python"
    if rel.endswith(".py"):
        from .app_static import _Finder, _imports, app_min_python, parse_python, text_rule_scan
        target_python = app_min_python(ws, info)
        tree, syntax = parse_python(content, rel, target_python)
        if syntax.startswith("invalid"):
            raise ValidationError("Python syntax error " + syntax[len("invalid: "):])
        if tree is not None:
            _Finder(rel, findings, _imports(tree)).visit(tree)
        else:
            findings.extend(text_rule_scan(content))
            plan.unchecked.append(rel)
            plan.notes.append("UNCHECKED: the server's Python {}.{} cannot parse this file and the app requires {}; "
                              "only a best-effort text scan ran. Double approval is required; review the code by hand "
                              "and run the app's tests.".format(
                                  sys.version_info[0], sys.version_info[1],
                                  ">={}.{}".format(*target_python) if target_python else "an unknown version"))
        blocking = [f for f in findings if f["rule"] in _BLOCKING_RULES
                    or (f["rule"] == "SEC003" and f["severity"] == "error")]
        if blocking:
            raise ValidationError("Proposed code breaks safety rules: " + "; ".join(
                "{} line {}: {}".format(f["rule"], f["line"], f["message"]) for f in blocking))
        plan.notes += ["Warning EXT001 line {}: monkey patch of an official module. It changes official behaviour "
                       "for every site on the bench and can break silently on upgrade; prefer hooks, doc_events or "
                       "extend/override_doctype_class.".format(f["line"]) for f in findings if f["rule"] == "EXT001"]
    elif rel.endswith(".json"):
        try:
            json.loads(content)
        except ValueError as error:
            raise ValidationError("Invalid JSON: " + str(error)) from None
    if current is None:
        plan.create(rel, content)
    else:
        plan.modify(rel, content)
    if not plan.files:
        raise KitError("Content is identical to the current file", code="no_op")
    plan.notes.append("Purpose: " + c["purpose"])
    plan.notes.append("press-ai never runs or imports this code. Behaviour is unverified until the developer runs "
                      "app_check and the app's tests and reports their real output.")
    if findings:
        plan.notes.append("Static findings in the proposed file: " + "; ".join(
            "{} {} line {}".format(f["rule"], f["severity"], f["line"]) for f in findings))
    plan.followups += ["bench --site <site> run-tests --app {}".format(info["name"]),
                       "bench --site <site> migrate  # only if DocType JSON, patches or hooks changed"]


GENERATORS = {"new_doctype": _new_doctype, "add_child_table": _add_child_table, "add_patch": _add_patch,
              "add_fixture_filter": _add_fixture_filter, "add_doc_event": _add_doc_event,
              "extend_doctype_class": _extend_class, "add_test": _add_test}


def build_plan(ws, app_path: str, change: dict) -> dict:
    kind = change.get("kind") if isinstance(change, dict) else None
    schema = KIND_SCHEMAS.get(kind)
    if schema is None:
        raise ValidationError("change.kind must be one of " + ", ".join(sorted(KIND_SCHEMAS)))
    validate(change, schema, "change")
    split_relative(app_path)
    plan = Plan(ws)
    if kind == "new_app":
        _new_app(plan, ws, app_path, change)
        app_name = change["app_name"]
    else:
        info = locate_app(ws, app_path)
        check_canonical_case(ws, info["package"] + "/hooks.py")
        # Resmi uygulamadaki her dosya Plan'da core olarak işaretlenir; öneri yalnız uyarı ve açık tekrardan sonra oluşur.
        if kind == "write_file":
            _write_file(plan, ws, info, change, None, app_path)
        else:
            GENERATORS[kind](plan, ws, info, change, change.get("target_frappe"))
        app_name = info["name"]
    result = plan.result()
    if not result["files"]:
        raise KitError("Nothing to change", code="no_op", details={"manual_merge": result["manual_merge"]})
    result.update(kind=kind, app=app_name)
    return result
