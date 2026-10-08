"""Araç girdileri için küçük JSON Schema doğrulayıcısı.

Desteklenen anahtarlar bu paketin şemalarında kullanılanlarla sınırlıdır: type, properties, required,
additionalProperties (yalnız false), items, enum, const, minLength, maxLength, pattern, minItems,
maxItems, minimum, maximum. Tanınmayan anahtar bir programlama hatasıdır ve reddedilir; böylece
yanlışlıkla gevşek bir şema sessizce kabul edilmez.
"""
from __future__ import annotations

import re

from .errors import ValidationError

_KNOWN = {
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "minimum", "maximum",
    "description", "default", "title",
}
_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected = _TYPES.get(name)
    if expected is None:
        raise ValueError("Unsupported schema type: " + name)
    if expected is dict or expected is list:
        return isinstance(value, expected)
    return type(value) is expected


def check_schema(schema: dict, where: str = "$") -> None:
    """Şemanın yalnız desteklenen anahtarları kullandığını ve nesnelerin kapalı olduğunu doğrular."""
    if not isinstance(schema, dict):
        raise ValueError(where + ": schema must be an object")
    unknown = set(schema) - _KNOWN
    if unknown:
        raise ValueError(where + ": unsupported schema keys " + ", ".join(sorted(unknown)))
    types = schema.get("type")
    names = types if isinstance(types, list) else [types] if types else []
    if "object" in names:
        # Serbest nesne yalnız `properties` tanımlamayan, içi ayrıca işleme özgü şemayla doğrulanan
        # zarf alanlarında kullanılır (ör. press_read.params); tanımlı alanlı nesneler kapalıdır.
        open_envelope = "properties" not in schema and schema.get("additionalProperties") is True
        if schema.get("additionalProperties") is not False and not open_envelope:
            raise ValueError(where + ": object schemas must set additionalProperties to false")
        for key, sub in schema.get("properties", {}).items():
            check_schema(sub, where + "." + key)
        missing = set(schema.get("required", [])) - set(schema.get("properties", {}))
        if missing:
            raise ValueError(where + ": required keys without properties " + ", ".join(sorted(missing)))
    if "array" in names and "items" in schema:
        check_schema(schema["items"], where + "[]")


def validate(value, schema: dict, where: str = "params") -> None:
    """Değeri şemaya göre doğrular; ilk uyumsuzlukta ValidationError yükseltir."""
    types = schema.get("type")
    if types is not None:
        names = types if isinstance(types, list) else [types]
        if not any(_is_type(value, name) for name in names):
            raise ValidationError(where + ": expected " + " or ".join(names))
    if "const" in schema and value != schema["const"]:
        raise ValidationError(where + ": unexpected value")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(where + ": must be one of " + ", ".join(map(str, schema["enum"])))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValidationError(where + ": too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValidationError(where + ": too long")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValidationError(where + ": invalid format")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(where + ": below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(where + ": above maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValidationError(where + ": too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValidationError(where + ": too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], "{}[{}]".format(where, index))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise ValidationError(where + ": missing " + key)
        extra = set(value) - set(properties)
        if extra and schema.get("additionalProperties") is False:
            raise ValidationError(where + ": unexpected fields " + ", ".join(sorted(extra)))
        for key, sub in properties.items():
            if key in value:
                validate(value[key], sub, where + "." + key)
