"""Sözleşme testlerinin araçları: küçük bir YAML okuyucu ve küçük bir şema denetleyici.

Python'un kendi kitaplığında YAML okuyucu ve JSON Schema denetleyici yoktur.
Servis yeni paket eklemez. Bu yüzden testler sözleşme dosyasının kullandığı kadarını okur.

Okuyucu şunları tanır: iç içe eşleme, liste, `|` ile başlayan çok satırlı metin,
`[a, b]` biçimli kısa liste, tırnaklı metin, sayı, `true`, `false` ve `null`.
Dosyaya başka bir YAML yapısı girerse okuyucu `ValueError` verir ve testler kırılır.
"""

from __future__ import annotations

import json
import re

_KEY = re.compile(r'^("(?:[^"\\]|\\.)*"|[^:"\[\]{}|#][^:]*?):(?: (.*))?$')
_INT = re.compile(r"^-?[0-9]+$")
_FLOAT = re.compile(r"^-?[0-9]+\.[0-9]+$")


def _scalar(text: str) -> object:
    text = text.strip()
    if text.startswith('"'):
        return json.loads(text)
    if text.startswith("["):
        return _flow_list(text)
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if _INT.fullmatch(text):
        return int(text)
    if _FLOAT.fullmatch(text):
        return float(text)
    if text[:1] in "{&*!>'%@`" or text == "|":
        raise ValueError(f"unsupported YAML scalar: {text!r}")
    return text


def _flow_list(text: str) -> list[object]:
    if not text.endswith("]"):
        raise ValueError(f"unsupported YAML flow list: {text!r}")
    inner = text[1:-1].strip()
    if not inner:
        return []
    items, current, quoted = [], "", False
    for char in inner:
        if char == '"':
            quoted = not quoted
        if char == "," and not quoted:
            items.append(current)
            current = ""
        else:
            current += char
    items.append(current)
    return [_scalar(item) for item in items]


class _Parser:
    def __init__(self, text: str) -> None:
        self.raw = text.splitlines()
        self.index = 0

    def _skip_blank(self) -> None:
        while self.index < len(self.raw) and (not self.raw[self.index].strip() or self.raw[self.index].lstrip().startswith("#")):
            self.index += 1

    def _peek(self) -> tuple[int, str] | None:
        self._skip_blank()
        if self.index >= len(self.raw):
            return None
        line = self.raw[self.index]
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise ValueError("tabs are not supported")
        return len(line) - len(line.lstrip(" ")), line.strip()

    def parse(self) -> object:
        first = self._peek()
        if first is None:
            return None
        value = self._block(first[0])
        if self._peek() is not None:
            raise ValueError(f"unexpected content at line {self.index + 1}")
        return value

    def _block(self, indent: int) -> object:
        line = self._peek()
        assert line is not None
        return self._sequence(indent) if line[1].startswith("- ") or line[1] == "-" else self._mapping(indent)

    def _value(self, text: str | None, indent: int) -> object:
        """Anahtardan sonraki değeri okur. `indent`, anahtarın girintisidir."""
        if text is None or text == "":
            following = self._peek()
            if following is None or following[0] < indent or (following[0] == indent and not following[1].startswith("- ")):
                return None
            if following[0] == indent:  # anahtarla aynı girintide liste
                return self._sequence(indent)
            return self._block(following[0])
        if text == "|":
            return self._literal(indent)
        return _scalar(text)

    def _literal(self, parent_indent: int) -> str:
        lines: list[str] = []
        block_indent: int | None = None
        while self.index < len(self.raw):
            line = self.raw[self.index]
            if line.strip():
                current = len(line) - len(line.lstrip(" "))
                if current <= parent_indent:
                    break
                if block_indent is None:
                    block_indent = current
                lines.append(line[block_indent:])
            else:
                lines.append("")
            self.index += 1
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines) + "\n"

    def _mapping(self, indent: int, first: str | None = None) -> dict[str, object]:
        result: dict[str, object] = {}
        while True:
            if first is not None:
                text, first = first, None
            else:
                line = self._peek()
                if line is None or line[0] != indent or line[1].startswith("- "):
                    if line is not None and line[0] > indent:
                        raise ValueError(f"unexpected indent at line {self.index + 1}")
                    return result
                text = line[1]
                self.index += 1
            match = _KEY.fullmatch(text)
            if match is None:
                raise ValueError(f"unsupported YAML line {self.index}: {text!r}")
            key = match.group(1)
            key = json.loads(key) if key.startswith('"') else key
            if key in result:
                raise ValueError(f"duplicate key {key!r} near line {self.index}")
            result[str(key)] = self._value(match.group(2), indent)

    def _sequence(self, indent: int) -> list[object]:
        result: list[object] = []
        while True:
            line = self._peek()
            if line is None or line[0] != indent or not line[1].startswith("- "):
                return result
            self.index += 1
            rest = line[1][2:].strip()
            if _KEY.fullmatch(rest) and not rest.startswith(('"', "[")):
                result.append(self._mapping(indent + 2, first=rest))
            elif rest.startswith('"') and _KEY.fullmatch(rest) and not rest.endswith('"'):
                result.append(self._mapping(indent + 2, first=rest))
            else:
                result.append(_scalar(rest))


def load_yaml(text: str) -> object:
    return _Parser(text).parse()


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value: object, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def schema_errors(value: object, schema: dict, root: dict, path: str = "$") -> list[str]:
    """Değeri şemaya göre denetler. Hataların listesini döner. Boş liste uygunluk demektir.

    Desteklenen anahtarlar sözleşme dosyasının kullandıklarıdır.
    """
    known = {
        "$ref", "type", "required", "properties", "additionalProperties", "enum", "const", "pattern",
        "minLength", "maxLength", "items", "maxItems", "minimum", "maximum", "default", "oneOf", "anyOf", "description", "examples",
    }
    unknown = set(schema) - known
    if unknown:
        raise ValueError(f"unsupported schema keyword: {sorted(unknown)}")
    if "$ref" in schema:
        target: object = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            # The contract is plain parsed YAML. The path inside a `$ref` is known to exist.
            target = target[part]  # type: ignore[index]
        return schema_errors(value, target, root, path)  # type: ignore[arg-type]
    errors: list[str] = []
    if "oneOf" in schema:
        matches = sum(1 for option in schema["oneOf"] if not schema_errors(value, option, root, path))
        if matches != 1:
            errors.append(f"{path}: matches {matches} of oneOf")
    if "anyOf" in schema and all(schema_errors(value, option, root, path) for option in schema["anyOf"]):
        errors.append(f"{path}: matches none of anyOf")
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, name) for name in names):
            return [*errors, f"{path}: expected {names}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: {value!r} is not {schema['const']!r}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: does not match pattern")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
            errors.append(f"{path}: bad length")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing {name}")
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                errors += schema_errors(item, properties[name], root, f"{path}.{name}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected {name}")
    if isinstance(value, list) and len(value) > schema.get("maxItems", len(value)):
        errors.append(f"{path}: more than {schema['maxItems']} items")
    if isinstance(value, int) and not isinstance(value, bool):
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            errors.append(f"{path}: out of range")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors += schema_errors(item, schema["items"], root, f"{path}[{index}]")
    return errors
