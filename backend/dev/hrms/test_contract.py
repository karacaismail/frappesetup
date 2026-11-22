"""Check published HRMS TR schemas, examples, and approval inputs."""

import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "hrms_tr.openapi.yaml"


class TestOpenApiExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    def operations(self):
        for path, path_item in self.contract["paths"].items():
            path_parameters = path_item.get("parameters", [])
            for method in (
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "head",
                "options",
                "trace",
            ):
                if method in path_item:
                    operation = path_item[method]
                    yield (
                        path,
                        method,
                        operation,
                        path_parameters + operation.get("parameters", []),
                    )

    def resolved(self, entry):
        if "$ref" not in entry:
            return entry
        reference = entry["$ref"]
        self.assertTrue(reference.startswith("#/"), reference)
        result = self.contract
        for key in reference[2:].split("/"):
            result = result[key.replace("~1", "/").replace("~0", "~")]
        return result

    def validate_example(self, entry):
        self.assertIn("example", entry)
        schema = {**entry["schema"], "components": self.contract["components"]}
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
            entry["example"]
        )

    def test_each_operation_has_a_request_example(self):
        for path, method, operation, parameters in self.operations():
            body = operation.get("requestBody")
            for parameter in parameters:
                with self.subTest(path=path, method=method, parameter=parameter["name"]):
                    self.validate_example(parameter.get("content", {}).get("application/json", parameter))
            if body:
                with self.subTest(path=path, method=method, request_body=True):
                    self.validate_example(self.resolved(body)["content"]["application/json"])
            if not parameters and not body:
                with self.subTest(path=path, method=method):
                    self.assertEqual(
                        operation.get("x-request-example"),
                        f"{method.upper()} /api{path}",
                    )

    def test_each_response_has_a_valid_example(self):
        for path, method, operation, _ in self.operations():
            for status, response in operation["responses"].items():
                with self.subTest(path=path, method=method, status=status):
                    content = self.resolved(response).get("content", {})
                    self.assertIn("application/json", content)
                    self.validate_example(content["application/json"])

    def test_schema_fields_have_descriptions(self):
        def properties(node, path=()):
            if isinstance(node, dict):
                for name, schema in node.get("properties", {}).items():
                    yield (*path, name), schema
                for name, child in node.items():
                    yield from properties(child, (*path, name))
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    yield from properties(child, (*path, str(index)))

        for path, schema in properties(self.contract):
            with self.subTest(field=".".join(path)):
                self.assertTrue(schema.get("description", "").strip())


class TestApprovalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    def test_ai_tool_metadata_matches_declaration(self):
        from hrms_tr.ai_tools import declarations

        (declaration,) = declarations()
        tool = self.contract["x-ai-tool"]
        self.assertEqual(tool["name"], f"hrt_{declaration['name']}")
        for key in ("kind", "roles", "destructive", "versioned"):
            with self.subTest(key=key):
                self.assertEqual(tool[key], declaration[key])

    def test_ai_tool_arguments_match_pydantic_schema(self):
        from hrms_tr.ai_tools import ApprovalArguments

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
                    {key: value for key, value in schema.items() if key not in {"description", "title"}},
                )

    def test_human_approval_matches_field_constraints(self):
        from hrms_tr.leave import LeaveName, LeaveVersion
        from pydantic import TypeAdapter

        documented = self.contract["components"]["schemas"]["ApproveLeaveRequest"]
        self.assertEqual(documented["required"], ["name", "version"])
        self.assertEqual(set(documented["properties"]), {"name", "version"})
        for name, field_type in (("name", LeaveName), ("version", LeaveVersion)):
            with self.subTest(argument=name):
                runtime = TypeAdapter(field_type).json_schema()
                property_schema = documented["properties"][name]
                self.assertEqual(
                    {key: property_schema[key] for key in ("type", "minLength", "maxLength")},
                    runtime,
                )


if __name__ == "__main__":
    unittest.main()
