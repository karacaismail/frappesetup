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


class TestFrappeResponses(unittest.TestCase):
    """Match responses that Frappe 16 sends before or around the HRMS TR code."""

    @classmethod
    def setUpClass(cls):
        cls.contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
        cls.schemas = cls.contract["components"]["schemas"]

    def validator(self, schema):
        return Draft202012Validator({**schema, "components": self.contract["components"]})

    def test_list_items_hold_only_requested_fields(self):
        # frappe/api/v1.py document_list passes ``fields`` to frappe.get_list unchanged.
        list_schema = self.schemas["LeaveApplicationListResponse"]
        self.validator(list_schema).validate({"data": [{"modified": "2026-11-23 11:42:51.896988"}]})

    def test_single_record_still_requires_name(self):
        record_schema = self.schemas["LeaveApplicationResponse"]
        self.assertFalse(self.validator(record_schema).is_valid({"data": {"modified": "2026-11-23"}}))

    def test_denied_routes_document_rejected_credentials(self):
        # Frappe checks the sid cookie and the Authorization header before it routes the request.
        for path in (
            "/method/hrms_tr.hrms_endpoints.deny_legacy_leave_query",
            "/v2/document/Attendance%20Request/{name}/method/get_attendance_warnings/",
        ):
            for method in ("get", "post"):
                with self.subTest(path=path, method=method):
                    self.assertIn("401", self.contract["paths"][path][method]["responses"])

    def test_attendance_warning_route_documents_unmatched_names(self):
        # frappe/api/v2.py uses <path:name>. Werkzeug does not match a name with a line break.
        route = "/v2/document/Attendance%20Request/{name}/method/get_attendance_warnings/"
        for method in ("get", "post"):
            with self.subTest(method=method):
                self.assertEqual(
                    self.contract["paths"][route][method]["responses"]["404"],
                    {"$ref": "#/components/responses/NotFoundV2"},
                )


class TestLeaveRequestContextContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    def test_context_is_get_only_and_accepts_only_leave_type(self):
        route = self.contract["paths"]["/method/hrms_tr.api.get_leave_request_context"]
        self.assertEqual(set(route), {"get"})
        (parameter,) = route["get"]["parameters"]
        self.assertEqual((parameter["name"], parameter["in"]), ("leave_type", "query"))
        self.assertFalse(parameter["required"])
        self.assertNotIn("default", parameter["schema"])
        self.assertEqual(parameter["schema"]["maxLength"], 140)

    def test_leave_type_source_accepts_explicit_type_and_allocation(self):
        schema = self.contract["components"]["schemas"]["LeaveRequestContextResponse"]
        source = schema["properties"]["message"]["properties"]["sources"]["properties"]["leave_type"]
        self.assertEqual(set(source["enum"]), {"Leave Type", "Leave Allocation", None})

    def test_context_accepts_absent_data_and_real_zero(self):
        route = self.contract["paths"]["/method/hrms_tr.api.get_leave_request_context"]["get"]
        response = route["responses"]["200"]["content"]["application/json"]
        validator = Draft202012Validator({**response["schema"], "components": self.contract["components"]})
        validator.validate(response["example"])
        fields = ("employee", "employee_name", "leave_type", "leave_balance")
        validator.validate({"message": {**dict.fromkeys(fields), "sources": dict.fromkeys(fields)}})
        example = response["example"]["message"].copy()
        example["leave_balance"] = 0
        validator.validate({"message": example})
        self.assertEqual(set(example["sources"]), set(fields))
        self.assertEqual(example["employee_name"], "Örnek Kişi 1")

    def test_existing_balance_routes_remain_denied(self):
        operation = self.contract["paths"]["/method/hrms_tr.hrms_endpoints.deny_legacy_leave_query"]["get"]
        for path in [
            "hrms.hr.doctype.leave_application.leave_application.get_leave_details",
            "hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on",
            "hrms.api.get_leave_balance_map",
        ]:
            self.assertIn(path, operation["x-frappe-original"])
