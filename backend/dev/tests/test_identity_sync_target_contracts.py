"""The target replies identity-sync expects must match the target contracts (H-5).

identity-sync calls endpoints of Press and of the tenant sites. It accepts a write only when the
reply carries the fields of its `Target...Result` schema (contracts/identity_sync.openapi.yaml).
Each of those endpoints has its own contract: contracts/press_tr.openapi.yaml,
contracts/platform_core-identity.openapi.yaml and contracts/platform_core-mobile.openapi.yaml.

This test reads both sides. Every field the service requires in a target reply must be a required
field of the 200 reply in the target's contract. A field the target does not promise makes the
service record the step as `unknown` on every call. That happened in the final MVP test (H-5):
the tenant `anonymize_user` reply carried `user`, `enabled` and `status`, but no `anonymized`
and no `found`.
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
        merged = {"properties": {}, "required": []}
        for part in schema["allOf"]:
            part = resolve(spec, part)
            merged["properties"].update(part.get("properties", {}))
            merged["required"] += part.get("required", [])
        return merged
    return schema


def required_fields(spec, schema, prefix=""):
    """Every required field of a schema, nested objects included, as dotted paths."""
    schema = resolve(spec, schema)
    found = []
    for name in schema.get("required", []):
        path = f"{prefix}{name}"
        found.append(path)
        child = resolve(spec, schema.get("properties", {}).get(name))
        if isinstance(child, dict) and "items" in child:
            found += required_fields(spec, child["items"], f"{path}[].")
        elif child is not None:
            found += required_fields(spec, child, f"{path}.")
    return found


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
            expected = required_fields(service, service["components"]["schemas"][schema_name])
            for contract, path, *method in endpoints:
                spec = load(contract)
                schema = reply_schema(spec, path, method[0] if method else "post")
                promised = set(required_fields(spec, schema))
                with self.subTest(target=schema_name, contract=contract, path=path):
                    missing = [field for field in expected if field not in promised]
                    self.assertEqual(missing, [], f"{contract} {path} does not promise these reply fields")


if __name__ == "__main__":
    unittest.main()
