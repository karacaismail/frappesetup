"""Validate model-gateway examples against the published OpenAPI schemas."""

import sys
import unittest
from importlib.util import find_spec
from pathlib import Path

if any(find_spec(module) is None for module in ("jsonschema", "referencing", "yaml")):
    raise unittest.SkipTest("Install backend/dev/requirements-contract-tests.txt for contract tests")

from jsonschema.exceptions import ValidationError  # noqa: E402

APP_PATH = Path(__file__).resolve().parents[2] / "apps" / "platform_core"
sys.path.insert(0, str(APP_PATH))

from platform_core.model_gecidi.tests.contract_validation import GatewayContract  # noqa: E402


class GatewayContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = GatewayContract()

    def test_declarations_include_schema_valid_examples(self):
        for path, definition in self.contract.spec["paths"].items():
            for status in definition["post"]["responses"]:
                with self.subTest(path=path, status=status):
                    media, _ = self.contract.response(path, "post", status)
                    examples = (
                        [media["example"]]
                        if "example" in media
                        else [example["value"] for example in media.get("examples", {}).values()]
                    )
                    self.assertTrue(examples)
                    for example in examples:
                        self.contract.validate_response(path, "post", status, example)

    def test_native_frappe_errors_have_examples(self):
        path = "/api/method/platform_core.api.model.complete"
        for status, expected in (("401", "SessionExpired"), ("403", "PermissionError")):
            with self.subTest(status=status):
                media, _ = self.contract.response(path, "post", status)
                payloads = [entry["value"] for entry in media.get("examples", {}).values()]
                self.assertIn({"exc_type": expected}, payloads)

    def test_permission_denial_uses_the_native_frappe_envelope(self):
        path = "/api/method/platform_core.api.model.complete"
        with self.assertRaises(ValidationError):
            self.contract.validate_response(path, "post", 403, {"message": {"error": "permission_denied"}})

    def test_retention_preview_declares_the_exact_batch_and_token(self):
        path = "/api/method/platform_core.api.model.purge_usage"
        media, _ = self.contract.response(path, "post", 200)
        self.assertIn("preview_token", media["schema"]["properties"]["message"]["required"])
        self.assertIn("targets", media["schema"]["properties"]["message"]["required"])

    def test_reconciliation_accepts_exact_decimal_text_and_currency(self):
        for amount, currency in [("0", "USD"), ("999999999999.123456789", "EUR")]:
            self.contract.validate_completion_cost({"log": "sample", "cost": amount, "currency": currency})
        for amount, currency in [(0.125, "USD"), ("1e-3", "USD"), ("0.0000000001", "USD"), ("1", "usd")]:
            with self.assertRaises(ValidationError):
                self.contract.validate_completion_cost(
                    {"log": "sample", "cost": amount, "currency": currency}
                )
        with self.assertRaises(ValidationError):
            self.contract.validate_completion_cost({"log": "sample", "cost": "0.5"})
