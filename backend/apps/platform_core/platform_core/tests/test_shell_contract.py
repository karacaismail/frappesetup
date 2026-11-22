"""Exercise projection shapes in the normal Frappe test runner."""

import json
import os
import unittest
from pathlib import Path

from platform_core.kabuk.bootstrap import project_sidebar
from platform_core.kabuk.serialization import project_meta

SCHEMA_FILE = Path(__file__).with_name("shell_contract_components.json")
JSON_TYPES = {
	"array": (list,),
	"object": (dict,),
	"string": (str,),
	"integer": (int,),
	"number": (int, float),
	"boolean": (bool,),
	"null": (type(None),),
}


SCHEMA_KEYWORDS = {
	"$ref",
	"type",
	"enum",
	"description",
	"minimum",
	"not",
	"required",
	"properties",
	"additionalProperties",
	"items",
	"uniqueItems",
	"allOf",
}


def matches(value, schema, components):
	if unknown := schema.keys() - SCHEMA_KEYWORDS:
		raise ValueError(f"Unsupported projection test schema keywords: {sorted(unknown)}")
	if "$ref" in schema:
		return matches(value, components[schema["$ref"].rsplit("/", 1)[1]], components)
	if kinds := schema.get("type"):
		kinds = [kinds] if isinstance(kinds, str) else kinds
		if not any(type(value) in JSON_TYPES[kind] for kind in kinds):
			return False
	if "enum" in schema and value not in schema["enum"]:
		return False
	if "minimum" in schema and value < schema["minimum"]:
		return False
	if "not" in schema and matches(value, schema["not"], components):
		return False
	if isinstance(value, dict):
		if set(schema.get("required", [])) - value.keys():
			return False
		properties = schema.get("properties", {})
		additional = schema.get("additionalProperties", True)
		for key, item in value.items():
			if key in properties and not matches(item, properties[key], components):
				return False
			if key not in properties and (
				additional is False
				or (isinstance(additional, dict) and not matches(item, additional, components))
			):
				return False
	if isinstance(value, list):
		if "items" in schema and not all(matches(item, schema["items"], components) for item in value):
			return False
		if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(
			value
		):
			return False
	for rule in schema.get("allOf", []):
		branch = "then" if matches(value, rule["if"], components) else "else"
		if not matches(value, rule.get(branch, {}), components):
			return False
	return True


class TestShellProjectionContract(unittest.TestCase):
	def test_projection_snapshot_matches_openapi(self):
		contract_path = os.environ.get("SHELL_TEST_OPENAPI")
		if not contract_path:
			self.skipTest("Canonical contract is mounted by the repository test runner.")
		contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
		schemas = contract["components"]["schemas"]
		snapshot = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
		self.assertEqual(snapshot, {name: schemas[name] for name in snapshot})

	def check(self, component, payload):
		components = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
		self.assertTrue(matches(payload, components[component], components), (component, payload))

	def test_field_condition_and_choices_match_the_contract(self):
		raw = {
			"name": "Sample",
			"fields": [
				{
					"fieldname": "choice",
					"fieldtype": "Select",
					"options": "Draft",
					"depends_on": "eval:doc.choice === 'Draft'",
					"read_only_depends_on": "eval:unsupported(doc.choice)",
				}
			],
		}
		field = project_meta(raw, {"choice"}, {"choice"})["fields"][0]
		# The Frappe metadata service adds these catalog and locale properties.
		field.update(
			component="select", sensitivity="standard", choices=[{"value": "Draft", "label": "Draft"}]
		)
		self.check("Field", field)
		self.assertIs(field["read_only"], True)

	def test_sidebar_with_no_module_and_report_matches_the_contract(self):
		source = {
			"name": "Example",
			"label": "Example",
			"module": None,
			"workspaces": [],
			"items": [
				{
					"key": "list",
					"type": "Link",
					"link_type": "DocType",
					"link_to": "Sample",
					"report": {"report_type": "Script Report", "ref_doctype": "Sample"},
				}
			],
		}
		self.check("SidebarData", project_sidebar(source))
