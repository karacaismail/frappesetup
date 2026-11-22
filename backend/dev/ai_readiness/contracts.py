"""Read the OpenAPI path and operation mappings used by the backend contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
METHOD_PATH = re.compile(r"(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*\Z")
METHOD_PREFIXES = ("/api/method/", "/api/v1/method/", "/api/v2/method/", "/method/")
FIELDS = ("summary", "description")
ORIGINAL = "x-frappe-original"
YAML_ENTRY = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s:]+):(?=\s|$)\s*(.*)""")
BLOCK_SCALAR = re.compile(r"[|>](?:[+-][1-9]?|[1-9][+-]?)?$")
NUMBER = re.compile(
    r"[+-]?(?:0x[0-9a-f]+|0o[0-7]+|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:e[+-]?[0-9]+)?|\.inf|\.nan)$",
    re.IGNORECASE,
)
WHITESPACE = re.compile(r"\s*")
JSON_DECODER = json.JSONDecoder()


class ContractError(ValueError):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(message)
        self.lineno = line


def method_path(route: str, line: int) -> str:
    for prefix in METHOD_PREFIXES:
        if route.startswith(prefix):
            target = route[len(prefix) :]
            if not METHOD_PATH.fullmatch(target):
                raise ContractError(line, "Invalid dotted Frappe method path.")
            return target
    target = route.removeprefix("/")
    if METHOD_PATH.fullmatch(target):
        return target
    return ""


def json_mapping(source: str, start: int) -> Iterator[tuple[str, int, int, object]]:
    """Yield JSON members with the offsets of their keys and values."""
    offset = start + 1
    while True:
        offset = WHITESPACE.match(source, offset).end()
        if source[offset] == "}":
            return
        key_offset = offset
        key, end_key = JSON_DECODER.raw_decode(source, offset)
        offset = source.index(":", end_key) + 1
        offset = WHITESPACE.match(source, offset).end()
        value, end_value = JSON_DECODER.raw_decode(source, offset)
        yield key, key_offset, offset, value
        offset = WHITESPACE.match(source, end_value).end()
        if source[offset] == "}":
            return
        offset += 1


def json_operations(source: str, start: int) -> Iterator[tuple[str, int, tuple[str, ...], tuple[str, ...]]]:
    document = json.loads(source)
    if not isinstance(document, dict):
        raise ContractError(1, "OpenAPI document must be an object.")
    for key, key_offset, paths_offset, paths in json_mapping(source, start):
        if key != "paths":
            continue
        if not isinstance(paths, dict):
            raise ContractError(source.count("\n", 0, key_offset) + 1, "Paths must be an object.")
        for route, route_offset, item_offset, item in json_mapping(source, paths_offset):
            line = source.count("\n", 0, route_offset) + 1
            target = method_path(route, line)
            if not target:
                continue
            if not isinstance(item, dict) or "$ref" in item:
                raise ContractError(line, "Frappe path item must be an inline object.")
            for method, key_offset, _, operation in json_mapping(source, item_offset):
                if method not in HTTP_METHODS:
                    continue
                line = source.count("\n", 0, key_offset) + 1
                if not isinstance(operation, dict) or "$ref" in operation:
                    raise ContractError(line, "Frappe operation must be an inline object.")
                missing = tuple(field for field in FIELDS if not nonempty(operation.get(field)))
                originals = original_methods(operation[ORIGINAL], line) if ORIGINAL in operation else ()
                yield target, line, missing, originals


def original_methods(value, line):
    entries = value if isinstance(value, list) else [value]
    if any(not isinstance(entry, str) or not METHOD_PATH.fullmatch(entry) for entry in entries):
        raise ContractError(line, "x-frappe-original must contain dotted Frappe methods.")
    return tuple(entries)


def yaml_original_methods(value, children, line):
    text = re.split(r"(?:^|\s)#", value, maxsplit=1)[0].strip()
    if children and not text:
        entries = []
        for child_line, child in children:
            child = child.strip()
            if not child.startswith("- "):
                raise ContractError(child_line, "Expected a list of original Frappe methods.")
            entries.append(re.split(r"(?:^|\s)#", child[2:], maxsplit=1)[0].strip())
    elif text.startswith("[") and text.endswith("]") and not children:
        entries = [entry.strip() for entry in text[1:-1].split(",")]
        if entries[-1] == "":
            entries.pop()
    elif not children:
        entries = [text]
    else:
        raise ContractError(line, "Expected original Frappe methods.")
    return original_methods([entry.strip("\"'") for entry in entries], line)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def yaml_entries(lines: list[tuple[int, str]]) -> Iterator[tuple[str, str, int, list[tuple[int, str]]]]:
    """Read the immediate members of a block mapping, preserving child source lines."""
    if not lines:
        return
    indent = len(lines[0][1]) - len(lines[0][1].lstrip(" "))
    offset = 0
    while offset < len(lines):
        line, text = lines[offset]
        entry = YAML_ENTRY.fullmatch(text[indent:])
        if entry is None or text[:indent] != " " * indent:
            raise ContractError(line, "Expected an OpenAPI YAML block mapping.")
        key, value = entry.groups()
        if key.startswith('"'):
            key = json.loads(key)
        elif key.startswith("'"):
            key = key[1:-1].replace("''", "'")
        offset += 1
        end = offset
        while end < len(lines) and (
            lines[end][1].startswith(" " * (indent + 1))
            or (
                not value
                and lines[end][1][indent:].startswith("- ")
                and lines[end][1][:indent] == " " * indent
            )
        ):
            end += 1
        yield key, value, line, lines[offset:end]
        offset = end


def yaml_block(value: str, line: int) -> None:
    cleaned = value.split("#", 1)[0].strip()
    if cleaned not in {"", "{}"}:
        raise ContractError(line, "Expected an inline OpenAPI YAML block mapping.")


def yaml_text(value: str, children: list[tuple[int, str]], line: int) -> bool:
    if value.startswith(('"', "'")):
        quoted = re.match(r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')(?:\s+#.*)?$""", value)
        if quoted is None:
            raise ContractError(line, "Unsupported quoted OpenAPI text.")
        scalar = quoted[1]
        if scalar.startswith('"'):
            return nonempty(json.loads(scalar))
        return nonempty(scalar[1:-1].replace("''", "'"))
    cleaned = re.split(r"(?:^|\s)#", value, maxsplit=1)[0].strip()
    if BLOCK_SCALAR.fullmatch(cleaned):
        return bool(children)
    if not cleaned or cleaned.lower() in {"null", "~", "true", "false"}:
        return False
    if cleaned[0] in "[{&*!" or NUMBER.fullmatch(cleaned):
        return False
    return True


def yaml_operations(source: str) -> Iterator[tuple[str, int, tuple[str, ...], tuple[str, ...]]]:
    lines = [
        (number, line.rstrip())
        for number, line in enumerate(source.splitlines(), 1)
        if line.strip() and not line.lstrip().startswith("#") and line not in {"---", "..."}
    ]
    for key, value, line, children in yaml_entries(lines):
        if key != "paths":
            continue
        yaml_block(value, line)
        for route, value, line, methods in yaml_entries(children):
            if route.startswith("x-"):
                continue
            if not route.startswith("/"):
                raise ContractError(line, "OpenAPI path must begin with a slash.")
            target = method_path(route, line)
            if not target:
                continue
            yaml_block(value, line)
            for method, value, line, properties in yaml_entries(methods):
                if method in {"$ref", "<<"}:
                    raise ContractError(line, "Referenced Frappe path items are unsupported.")
                if method not in HTTP_METHODS:
                    continue
                yaml_block(value, line)
                found = set()
                originals = ()
                for field, value, field_line, children in yaml_entries(properties):
                    if field in {"$ref", "<<"}:
                        raise ContractError(field_line, "Referenced Frappe operations are unsupported.")
                    if field in FIELDS and yaml_text(value, children, field_line):
                        found.add(field)
                    if field == ORIGINAL:
                        originals = yaml_original_methods(value, children, field_line)
                yield target, line, tuple(field for field in FIELDS if field not in found), originals


def operations(path: Path) -> Iterator[tuple[str, int, tuple[str, ...], tuple[str, ...]]]:
    """Yield the dotted method, its operation line, and missing documentation fields."""
    source = path.read_text(encoding="utf-8-sig")
    if source.lstrip().startswith("{"):
        start = len(source) - len(source.lstrip())
        yield from json_operations(source, start)
    else:
        yield from yaml_operations(source)
