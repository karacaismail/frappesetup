"""Validate application CSV translations against optional Frappe source catalogs."""

import ast
import csv
import re


class TranslationCSVError(ValueError):
    def __init__(self, line):
        super().__init__("Invalid CSV record.")
        self.line = line


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        while True:
            line = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                return
            except csv.Error as error:
                raise TranslationCSVError(line) from error
            yield line, row


def csv_source(source):
    return source.replace(r"\n", "\n")


def po_text(value):
    if not value.startswith('"'):
        raise ValueError("Invalid gettext source string.")
    result = ast.literal_eval(value)
    if not isinstance(result, str):
        raise ValueError("Invalid gettext source string.")
    return result


def po_entry(fields, fuzzy):
    if not fuzzy and "msgctxt" not in fields and "msgid_plural" not in fields:
        source = "".join(fields.get("msgid", ()))
        translated = "".join(fields.get("msgstr", ()))
        if source and translated:
            return source, translated
    return None


def po_translations(path):
    fields = {}
    field = ""
    fuzzy = False
    with path.open(encoding="utf-8-sig") as stream:
        for raw in stream:
            line = raw.strip()
            words = line.split(maxsplit=1)
            token = words[0] if words else ""
            if token in {"msgctxt", "msgid"} and "msgid" in fields or token.startswith("#") or not token:
                if entry := po_entry(fields, fuzzy):
                    yield entry
                if fields or not token:
                    fuzzy = False
                fields, field = {}, ""
            if token == "#,":
                fuzzy = "fuzzy" in re.split(r"[,\s]+", line[2:])
            elif token in {"msgctxt", "msgid", "msgid_plural", "msgstr"}:
                field = token
                fields[field] = [po_text(words[1] if len(words) > 1 else "")]
            elif token.startswith('"') and field:
                fields[field].append(po_text(line))
            elif token:
                field = ""
    if entry := po_entry(fields, fuzzy):
        yield entry


def core_translations(package, language):
    parent = language.replace("_", "-").partition("-")[0]
    variants = dict.fromkeys((parent, language.replace("-", "_"), language.replace("_", "-"), language))
    result = {}
    found = False
    for variant in variants:
        csv_path = package / "translations" / f"{variant}.csv"
        if csv_path.is_file():
            found = True
            for _, row in csv_rows(csv_path):
                if not row:
                    continue
                if len(row) not in {2, 3}:
                    raise ValueError("Invalid Frappe translation record.")
                if row[0] and (len(row) == 2 or not row[2]):
                    result[csv_source(row[0])] = csv_source(row[1]).strip()
        po_path = package / "locale" / f"{variant}.po"
        if po_path.is_file():
            found = True
            result.update(po_translations(po_path))
    return result if found else None


def check_csv(path, core, emit):
    keys = {}
    conflict = False
    try:
        for line, row in csv_rows(path):
            if len(row) != 3:
                emit(path, line, "translation-columns", f"Expected 3 translation columns. Found {len(row)}.")
                continue
            source, translated, context = row
            source = csv_source(source)
            first = keys.setdefault((source, context), line)
            if first != line:
                emit(
                    path,
                    line,
                    "translation-duplicate",
                    f"Source and context are already used on line {first}.",
                )
            if (
                not context
                and core is not None
                and source in core
                and csv_source(translated).strip() != core[source]
            ):
                emit(
                    path,
                    line,
                    "translation-core",
                    "Translation differs from Frappe core for the same source. Add context.",
                )
                conflict = True
    except TranslationCSVError as error:
        emit(path, error.line, "translation-columns", "Invalid translation CSV record.")
    except (OSError, UnicodeError):
        emit(path, 1, "translation-columns", "Could not read translation CSV.")
    return conflict


def translation_checks(paths, frappe_package, emit):
    catalogs = {}
    failed = False
    for path in paths:
        language = path.stem
        if language not in catalogs:
            try:
                catalogs[language] = core_translations(frappe_package, language)
            except (OSError, SyntaxError, ValueError):
                catalogs[language] = None
                emit(path, 1, "translation-core", "Could not read the Frappe core translation catalog.")
                failed = True
        failed |= check_csv(path, catalogs[language], emit)
    if failed:
        return "fail"
    if not catalogs or any(catalog is None for catalog in catalogs.values()):
        return "not_run"
    return "pass"
