"""Check the OpenAPI structure and the browser callback contract."""

import unittest
from importlib.util import find_spec
from pathlib import Path

if find_spec("openapi_spec_validator") is None:
    raise unittest.SkipTest("Run with openapi-spec-validator==0.7.2")

from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "press_tr.openapi.yaml"


class PressOpenAPIContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.base_uri = read_from_filename(str(CONTRACT))

    def test_document_matches_openapi_31(self):
        validate(self.spec, base_uri=self.base_uri)

    def test_login_callback_documents_both_redirects(self):
        callback = self.spec["paths"]["/api/method/press_tr.api.auth.keycloak_callback"]["get"]
        location = callback["responses"]["302"]["headers"]["Location"]["schema"]
        self.assertCountEqual(
            location.get("enum", [location.get("const")]), ["/dashboard", "/account-deletion"]
        )

    def test_login_callback_documents_code_length_limit(self):
        callback = self.spec["paths"]["/api/method/press_tr.api.auth.keycloak_callback"]["get"]
        code = next(parameter for parameter in callback["parameters"] if parameter["name"] == "code")
        self.assertEqual(code["schema"].get("maxLength"), 2048)

    def test_identity_inventory_documents_private_service_pagination(self):
        path = self.spec["paths"]["/api/method/press_tr.api.identity.list_identities"]
        self.assertNotIn("post", path)
        operation = path["get"]
        self.assertEqual(operation["security"], [{"identitySync": []}])
        self.assertIn("403", operation["responses"])
        self.assertNotIn("requestBody", operation)
        self.assertTrue(all(parameter["in"] == "query" for parameter in operation["parameters"]))
        request = {parameter["name"]: parameter["schema"] for parameter in operation["parameters"]}
        self.assertCountEqual(request, ["start", "page_length"])
        self.assertEqual(request["start"]["default"], 0)
        self.assertEqual(request["start"]["maximum"], (1 << 64) - 1)
        self.assertEqual(request["page_length"]["default"], 500)
        self.assertEqual(request["page_length"]["maximum"], 500)
        response = operation["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
        page = response["message"]
        self.assertCountEqual(page["required"], ["identities", "has_next_page"])
        self.assertFalse(page["additionalProperties"])
        row = page["properties"]["identities"]["items"]
        self.assertCountEqual(row["required"], ["issuer", "subject", "enabled"])
        self.assertFalse(row["additionalProperties"])
