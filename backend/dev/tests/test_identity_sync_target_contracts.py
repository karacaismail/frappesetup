"""The target replies identity-sync expects must match the target contracts (H-5).

identity-sync calls endpoints of Press and of the tenant sites. It accepts a write only when the
reply carries the fields of its `Target...Result` schema (contracts/identity_sync.openapi.yaml).
Each of those endpoints has its own contract: contracts/press_tr.openapi.yaml,
contracts/platform_core-identity.openapi.yaml and contracts/platform_core-mobile.openapi.yaml.

This test reads both sides. Every field the service requires in a target reply must be a required
field of the 200 reply in the target's contract, with a type the service accepts. A reply that may
take several shapes (`oneOf` or `anyOf`) is checked shape by shape: every shape must carry the fields.

A field the target does not promise leaves the step `unknown` on every call. That happened in the
final MVP test (H-5): the tenant `anonymize_user` reply carried `user`, `enabled` and `status`, but no
`anonymized` and no `found`. The deletion job then never finished. After a timeout the service
repeats the step and accepts only this reply (project record O-27 and O-43). It reads no identity list.
"""

import unittest
from importlib.util import find_spec
from pathlib import Path

if find_spec("yaml") is None:
    raise unittest.SkipTest("Install backend/dev/requirements-contract-tests.txt for contract tests")

import yaml  # noqa: E402

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SERVICE = "identity_sync.openapi.yaml"
PRESS = "press_tr.openapi.yaml"
TENANT_IDENTITY = "platform_core-identity.openapi.yaml"
TENANT_MOBILE = "platform_core-mobile.openapi.yaml"

# Target schema of identity-sync -> the target endpoints whose 200 reply it describes.
# The identity list is also the state query after an anonymize timeout (H-5).
TARGETS = {
    "TargetIdentityList": [
        (TENANT_IDENTITY, "/platform_core.api.identity.list_identities", "get"),
        (PRESS, "/api/method/press_tr.api.identity.list_identities", "get"),
    ],
    "TargetEnsureTeamResult": [(PRESS, "/api/method/press_tr.api.identity.ensure_team")],
    "TargetRemoveTeamMemberResult": [(PRESS, "/api/method/press_tr.api.identity.remove_team_member")],
    "TargetProvisionResult": [(TENANT_IDENTITY, "/platform_core.api.identity.provision")],
    "TargetSetEnabledResult": [(TENANT_IDENTITY, "/platform_core.api.identity.set_enabled")],
    "TargetChangeEmailResult": [(TENANT_IDENTITY, "/platform_core.api.identity.change_email")],
    "TargetRevokeUserInstallationsResult": [
        (TENANT_MOBILE, "/platform_core.api.mobile.revoke_user_installations")
    ],
    "TargetAnonymizeUserResult": [
        (TENANT_IDENTITY, "/platform_core.api.identity.anonymize_user"),
        (PRESS, "/api/method/press_tr.api.identity.anonymize_user"),
    ],
}


def load(name):
    return yaml.safe_load((CONTRACTS / name).read_text(encoding="utf-8"))


def resolve(spec, schema):
    """Follow local `$ref` links and merge `allOf` parts into one object schema."""
    while isinstance(schema, dict) and "$ref" in schema:
        node = spec
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        schema = node
    if isinstance(schema, dict) and "allOf" in schema:
        merged = {key: value for key, value in schema.items() if key != "allOf"}
        merged.setdefault("properties", {})
        merged.setdefault("required", [])
        for part in schema["allOf"]:
            part = resolve(spec, part)
            for key, value in part.items():
                if key == "properties":
                    merged["properties"].update(value)
                elif key == "required":
                    merged["required"] += value
                else:
                    merged.setdefault(key, value)
        return merged
    return schema


def required_fields(spec, schema, prefix=""):
    """Every required field of a schema, nested objects included, as dotted paths."""
    return list(required_schemas(spec, schema, prefix))


def required_schemas(spec, schema, prefix=""):
    """The required fields of a schema that has one shape, keyed by dotted path."""
    variants = reply_variants(spec, schema, prefix)
    if len(variants) != 1:
        raise AssertionError("the schema has several shapes; check them with reply_variants")
    return variants[0]


def _shapes(spec, schema):
    """The shapes a schema allows. `oneOf` and `anyOf` give one shape per part."""
    schema = resolve(spec, schema)
    if not isinstance(schema, dict):
        return [{}]
    for key in ("oneOf", "anyOf"):
        if key in schema:
            rest = {name: value for name, value in schema.items() if name != key}
            return [shape for part in schema[key] for shape in _shapes(spec, {"allOf": [rest, part]})]
    return [schema]


def reply_variants(spec, schema, prefix=""):
    """Every shape of a reply as a map from dotted path to the field's own schema.

    Only required fields are listed. A required field that has several shapes multiplies the result,
    so each map is one complete reply the target may send.
    """
    variants = []
    for shape in _shapes(spec, schema):
        maps = [{}]
        for name in shape.get("required", []):
            path = f"{prefix}{name}"
            child_maps = []
            for child in _shapes(spec, shape.get("properties", {}).get(name, {})):
                if "items" in child:
                    nested = reply_variants(spec, child["items"], f"{path}[].")
                elif child.get("required"):
                    nested = reply_variants(spec, child, f"{path}.")
                else:
                    nested = [{}]
                child_maps += [{path: child, **inner} for inner in nested]
            maps = [{**done, **more} for done in maps for more in child_maps]
        variants += maps
    return variants


def variant_problems(expected, variant):
    """What one reply shape lacks: missing required fields and types the service would not accept."""
    problems = [f"missing {path}" for path in expected if path not in variant]
    problems += [f"type {path}" for path in type_mismatches(expected, variant)]
    return problems


_JSON_TYPES = {bool: "boolean", int: "integer", float: "number", str: "string", type(None): "null"}


def value_types(schema):
    """The JSON types a schema allows, or None when the schema does not say."""
    if "type" in schema:
        kinds = schema["type"]
        return frozenset([kinds] if isinstance(kinds, str) else kinds)
    values = [schema["const"]] if "const" in schema else schema.get("enum")
    if values is not None:
        return frozenset(_JSON_TYPES.get(type(value), "object") for value in values)
    return None


def type_mismatches(service_fields, target_fields):
    """Required fields whose target type the service would not accept.

    The service accepts a value only of its own types. A target that sends another type, or does
    not say which type it sends, fails. When the service fixes a value with `const`, the target
    must fix the same value. A field the target lacks is reported by the field check, not here.
    """
    wrong = []
    for path, wanted in service_fields.items():
        promised = target_fields.get(path)
        accepted = value_types(wanted)
        if promised is None or accepted is None:
            continue
        sent = value_types(promised)
        if sent is None or not sent <= accepted:
            wrong.append(path)
        elif "const" in wanted and promised.get("const", object()) != wanted["const"]:
            wrong.append(path)
    return wrong


def reply_schema(spec, path, method):
    """The JSON schema of the 200 reply of an endpoint."""
    response = resolve(spec, spec["paths"][path][method]["responses"]["200"])
    return response["content"]["application/json"]["schema"]


class IdentitySyncTargetContractTests(unittest.TestCase):
    def test_every_target_schema_is_checked(self):
        service = load(SERVICE)
        names = {name for name in service["components"]["schemas"] if name.startswith("Target")}
        self.assertEqual(names, set(TARGETS))

    def test_target_contracts_promise_every_field_the_service_requires(self):
        service = load(SERVICE)
        for schema_name, endpoints in TARGETS.items():
            expected = required_schemas(service, service["components"]["schemas"][schema_name])
            for contract, path, *method in endpoints:
                spec = load(contract)
                variants = reply_variants(spec, reply_schema(spec, path, method[0] if method else "post"))
                for number, variant in enumerate(variants, 1):
                    with self.subTest(target=schema_name, contract=contract, path=path, shape=number):
                        missing = [
                            problem
                            for problem in variant_problems(expected, variant)
                            if problem.startswith("missing")
                        ]
                        self.assertEqual(
                            missing, [], f"{contract} {path} shape {number} does not promise these fields"
                        )

    def test_target_contracts_promise_the_types_the_service_accepts(self):
        service = load(SERVICE)
        for schema_name, endpoints in TARGETS.items():
            expected = required_schemas(service, service["components"]["schemas"][schema_name])
            for contract, path, *method in endpoints:
                spec = load(contract)
                variants = reply_variants(spec, reply_schema(spec, path, method[0] if method else "post"))
                for number, variant in enumerate(variants, 1):
                    with self.subTest(target=schema_name, contract=contract, path=path, shape=number):
                        wrong = type_mismatches(expected, variant)
                        self.assertEqual(wrong, [], f"{contract} {path} shape {number} promises other types")

    def test_type_check_catches_a_text_value_for_a_boolean_field(self):
        service = {
            "found": {"type": "boolean"},
            "anonymized": {"type": "boolean"},
            "member": {"const": False},
        }
        target = {"found": {"type": "string"}, "anonymized": {"const": True}, "member": {"type": "boolean"}}
        self.assertEqual(type_mismatches(service, target), ["found", "member"])
        self.assertEqual(type_mismatches(service, {"found": {}}), ["found"])
        self.assertEqual(
            type_mismatches(service, {"found": {"type": "boolean"}, "member": {"const": False}}), []
        )

    def test_every_variant_of_a_one_of_reply_is_checked(self):
        # The tenant reply has two shapes: an anonymized account and an unknown identity.
        spec = {
            "components": {
                "schemas": {
                    "Done": {
                        "type": "object",
                        "required": ["anonymized", "found", "user"],
                        "properties": {
                            "anonymized": {"type": "boolean", "const": True},
                            "found": {"type": "boolean", "const": True},
                            "user": {"type": "string"},
                        },
                    },
                    "Unknown": {
                        "type": "object",
                        "required": ["anonymized"],
                        "properties": {"anonymized": {"type": "boolean"}, "found": {"type": "string"}},
                    },
                }
            }
        }
        reply = {
            "type": "object",
            "required": ["message"],
            "properties": {
                "message": {
                    "oneOf": [{"$ref": "#/components/schemas/Done"}, {"$ref": "#/components/schemas/Unknown"}]
                }
            },
        }
        variants = reply_variants(spec, reply)
        self.assertEqual(len(variants), 2)
        expected = {
            "message": {},
            "message.anonymized": {"type": "boolean"},
            "message.found": {"type": "boolean"},
        }
        problems = [variant_problems(expected, variant) for variant in variants]
        self.assertEqual(problems[0], [])
        self.assertEqual(problems[1], ["missing message.found"])


if __name__ == "__main__":
    unittest.main()
