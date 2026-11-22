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
