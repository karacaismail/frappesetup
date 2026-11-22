"""Check inline examples in every operation of the mobile OpenAPI contract."""

import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "platform_core-mobile.openapi.yaml"


class MobileContractExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    def resolve_response(self, response):
        if "$ref" not in response:
            return response
        name = response["$ref"].removeprefix("#/components/responses/")
        return self.contract["components"]["responses"][name]

    def check_media_examples(self, media):
        if "example" in media:
            examples = [media["example"]]
        else:
            examples = [example["value"] for example in media.get("examples", {}).values()]
        self.assertTrue(examples, "An inline JSON example is required")
        schema = {"components": self.contract["components"], **media["schema"]}
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        for example in examples:
            validator.validate(example)

    def test_each_operation_has_request_success_and_authentication_error_examples(self):
        self.assertTrue(self.contract["paths"])
        for path, methods in self.contract["paths"].items():
            for method, operation in methods.items():
                with self.subTest(method=method, path=path, example="request"):
                    self.check_media_examples(operation["requestBody"]["content"]["application/json"])
                with self.subTest(method=method, path=path, example="success"):
                    self.check_media_examples(
                        self.resolve_response(operation["responses"]["200"])["content"]["application/json"]
                    )
                with self.subTest(method=method, path=path, example="authorization"):
                    status = "403" if "identitySyncBearer" in operation.get("security", [{}])[0] else "401"
                    self.check_media_examples(
                        self.resolve_response(operation["responses"][status])["content"]["application/json"]
                    )
