"""Validate help responses against the published consumer contract (AJA-1038)."""

import os
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from platform_core.shell.help_content import resolve_component_help
from platform_core.shell.test_help_content import resolve, topic
from platform_core.shell.test_help_links import LINKS, component

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = Path(os.environ.get("PLT_HELP_TEST_OPENAPI", ROOT / "contracts/platform_core-help.openapi.yaml"))


class HelpContractTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.contract = yaml.safe_load(CONTRACT.read_text())

	def validate_response(self, method, answer):
		schema = self.contract["paths"][f"/platform_core.api.help.{method}"]["get"]["responses"]["200"][
			"content"
		]["application/json"]["schema"]
		Draft202012Validator({"components": self.contract["components"], **schema}).validate(
			{"message": answer}
		)

	def test_field_topic_description_none_and_unavailable_match_contract(self):
		for answer in (
			resolve([topic("tenant", "Tenant", **LINKS)]),
			resolve([]),
			resolve([], description=""),
			resolve([], readable=False),
		):
			self.validate_response(
				"get_field_help", {"doctype": "Sales Invoice", "fieldname": "due_date", **answer}
			)

	def test_component_topic_and_empty_result_match_contract(self):
		for topics in ([component("tenant", **LINKS)], []):
			answer = resolve_component_help(
				component_id="invoice-editor", topics=topics, language="tr", versions={}, roles=[]
			)
			self.validate_response("get_component_help", answer)
