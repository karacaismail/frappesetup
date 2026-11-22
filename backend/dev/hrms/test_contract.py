"""Check that the published approval inputs match the application."""

import unittest
from pathlib import Path

import yaml
from hrms_tr.ai_tools import ApprovalArguments, declarations
from hrms_tr.leave import LeaveName, LeaveVersion
from pydantic import TypeAdapter

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "hrms_tr.openapi.yaml"


class TestApprovalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    def test_ai_tool_metadata_matches_declaration(self):
        (declaration,) = declarations()
        tool = self.contract["x-ai-tool"]
        self.assertEqual(tool["name"], f"hrms_tr_{declaration['name']}")
        for key in ("kind", "roles", "destructive", "versioned"):
            with self.subTest(key=key):
                self.assertEqual(tool[key], declaration[key])

    def test_ai_tool_arguments_match_pydantic_schema(self):
        documented = self.contract["x-ai-tool"]["arguments"]
        runtime = ApprovalArguments.model_json_schema()
        for key in ("type", "additionalProperties", "required"):
            with self.subTest(key=key):
                self.assertEqual(documented[key], runtime[key])
        self.assertEqual(runtime["required"], ["name"])
        self.assertEqual(set(documented["properties"]), set(runtime["properties"]))
        for name, schema in runtime["properties"].items():
            with self.subTest(argument=name):
                self.assertEqual(
                    {
                        key: value
                        for key, value in documented["properties"][name].items()
                        if key != "description"
                    },
                    {
                        key: value
                        for key, value in schema.items()
                        if key not in {"description", "title"}
                    },
                )

    def test_human_approval_matches_field_constraints(self):
        documented = self.contract["components"]["schemas"]["ApproveLeaveRequest"]
        self.assertEqual(documented["required"], ["name", "version"])
        self.assertEqual(set(documented["properties"]), {"name", "version"})
        for name, field_type in (("name", LeaveName), ("version", LeaveVersion)):
            with self.subTest(argument=name):
                runtime = TypeAdapter(field_type).json_schema()
                property_schema = documented["properties"][name]
                self.assertEqual(
                    {
                        key: property_schema[key]
                        for key in ("type", "minLength", "maxLength")
                    },
                    runtime,
                )


if __name__ == "__main__":
    unittest.main()
