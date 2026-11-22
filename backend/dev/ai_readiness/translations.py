"""Validate application CSV translations against optional Frappe source catalogs."""

import ast
import csv


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


def po_sources(path):
    fragments = []
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            field, _, value = line.strip().partition(" ")
            if field in {"msgid", "msgid_plural"}:
                if fragments:
                    yield "".join(fragments)
                fragments = [po_text(value.strip())]
            elif fragments and field.startswith('"'):
                fragments.append(po_text(line.strip()))
            elif fragments:
                yield "".join(fragments)
                fragments = []
    if fragments:
        yield "".join(fragments)


def core_sources(package, language):
    parent = language.replace("_", "-").partition("-")[0]
    variants = dict.fromkeys((language, language.replace("-", "_"), language.replace("_", "-"), parent))
    result = set()
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
                result.add(csv_source(row[0]))
        po_path = package / "locale" / f"{variant}.po"
        if po_path.is_file():
            found = True
            result.update(po_sources(po_path))
    result.discard("")
    return result if found else None


def check_csv(path, core, emit):
    keys = {}
    conflict = False
    try:
        for line, row in csv_rows(path):
            if len(row) != 3:
                emit(path, line, "translation-columns", f"Expected 3 translation columns. Found {len(row)}.")
                continue
            source, _, context = row
            source = csv_source(source)
            first = keys.setdefault((source, context), line)
            if first != line:
                emit(
                    path,
                    line,
                    "translation-duplicate",
                    f"Source and context are already used on line {first}.",
                )
            if not context and core is not None and source in core:
                emit(
                    path,
                    line,
                    "translation-core",
                    "Translation source also exists in Frappe core. Add context.",
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
                catalogs[language] = core_sources(frappe_package, language)
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
