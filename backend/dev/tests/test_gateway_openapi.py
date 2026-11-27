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

from platform_core.model_gateway.tests.contract_validation import GatewayContract  # noqa: E402


class GatewayContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = GatewayContract()

    def test_each_operation_has_schema_valid_request_examples(self):
        for path, definition in self.contract.spec["paths"].items():
            with self.subTest(path=path):
                body = definition["post"].get("requestBody", {})
                media = body.get("content", {}).get("application/json", {})
                examples = (
                    [media["example"]]
                    if "example" in media
                    else [entry["value"] for entry in media.get("examples", {}).values()]
                )
                self.assertTrue(examples, "Missing request example")
                for example in examples:
                    self.contract.validate_request(path, "post", example)

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
        path = "/api/method/platform_core.api.model.resolve_usage"
        for amount, currency in [("0", "USD"), ("999999999999.123456789", "EUR")]:
            payload = {"log": "sample", "cost": amount, "currency": currency}
            self.contract.validate_request(path, "post", payload)
        for amount, currency in [(0.125, "USD"), ("1e-3", "USD"), ("0.0000000001", "USD"), ("1", "usd")]:
            with self.assertRaises(ValidationError):
                self.contract.validate_request(
                    path, "post", {"log": "sample", "cost": amount, "currency": currency}
                )
        with self.assertRaises(ValidationError):
            self.contract.validate_request(path, "post", {"log": "sample", "cost": "0.5"})

    def test_large_file_job_operations_are_published(self):
        # D-9: every large file command has an HTTP operation (G-156).
        for name in ("create_file_job", "file_job_status", "start_file_job", "retry_file_chunk"):
            path = f"/api/method/platform_core.api.model.{name}"
            with self.subTest(operation=name):
                self.assertIn(path, self.contract.spec["paths"])
                operation = self.contract.spec["paths"][path]["post"]
                self.assertEqual(operation["security"], [{"session": []}])
                for status in ("200", "400", "401", "403"):
                    self.assertIn(status, operation["responses"])

    def test_file_job_status_shows_the_plan_before_the_start(self):
        path = "/api/method/platform_core.api.model.file_job_status"
        plan = {
            "name": "fixture-job",
            "status": "planned",
            "failure_code": None,
            "chunk_count": 1,
            "estimated_cost": "0.25",
            "currency": "USD",
            "chunks": [
                {
                    "index": 0,
                    "first_page": 1,
                    "last_page": 2,
                    "byte_count": 900,
                    "status": "planned",
                    "failure_code": None,
                }
            ],
        }
        self.contract.validate_response(path, "post", 200, {"message": plan})
        unknown = {**plan, "estimated_cost": None, "currency": None}
        self.contract.validate_response(path, "post", 200, {"message": unknown})
        with self.assertRaises(ValidationError):
            self.contract.validate_response(path, "post", 200, {"message": {**plan, "estimated_cost": 0.25}})

    def test_file_job_denials_use_published_codes(self):
        cases = (
            ("start_file_job", "409", "job_not_planned"),
            ("retry_file_chunk", "404", "chunk_not_found"),
            ("retry_file_chunk", "409", "chunk_not_failed"),
            ("create_file_job", "400", "unsupported_file"),
        )
        for name, status, code in cases:
            with self.subTest(operation=name, code=code):
                path = f"/api/method/platform_core.api.model.{name}"
                self.contract.validate_response(path, "post", status, {"message": {"error": code}})
