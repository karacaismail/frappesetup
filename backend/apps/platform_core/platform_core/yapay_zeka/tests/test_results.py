"""Tool results follow the published result schemas (contract section `x-mcp-results`)."""

import frappe

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, YzTestCase

TYPES = {
	"object": dict,
	"array": list,
	"string": str,
	"boolean": bool,
	"integer": int,
	"null": type(None),
}


def problems(value, schema: dict, path: str = "result") -> list[str]:
	"""Check a value against the JSON Schema subset the result schemas use."""
	found = []
	kinds = schema.get("type")
	if kinds:
		kinds = [kinds] if isinstance(kinds, str) else kinds
		is_bool_as_int = isinstance(value, bool) and "boolean" not in kinds
		if is_bool_as_int or not isinstance(value, tuple(TYPES[kind] for kind in kinds)):
			return [f"{path}: expected {kinds}, got {type(value).__name__}"]
	if "enum" in schema and value not in schema["enum"]:
		found.append(f"{path}: {value!r} is not one of {schema['enum']}")
	if isinstance(value, dict):
		found += [f"{path}: missing {key}" for key in schema.get("required", []) if key not in value]
		for key, child in schema.get("properties", {}).items():
			if key in value:
				found += problems(value[key], child, f"{path}.{key}")
	if isinstance(value, list) and "items" in schema:
		for index, item in enumerate(value):
			found += problems(item, schema["items"], f"{path}[{index}]")
	return found


class TestResultSchemas(YzTestCase):
	def schemas(self, client) -> dict:
		tools = self.rpc(client, "tools/list").json["result"]["tools"]
		return {tool["name"]: tool.get("outputSchema") for tool in tools}

	def check(self, client, schemas: dict, tool: str, arguments: dict) -> dict:
		result = self.call_tool(client, tool, arguments)
		self.assertFalse(result["isError"], result)
		self.assertEqual(problems(result["structuredContent"], schemas[tool]), [], tool)
		return result["structuredContent"]

	def test_every_listed_built_in_tool_publishes_a_result_schema(self):
		schemas = self.schemas(self.login(MANAGER))

		self.assertGreaterEqual(len(schemas), 17)
		# Application tools carry their application's name in front. Their result shape is their own.
		built_in = {name: schema for name, schema in schemas.items() if not name.startswith("platform_core_")}
		self.assertGreaterEqual(len(built_in), 17)
		self.assertEqual([name for name, schema in built_in.items() if not schema], [])

	def test_read_tool_results_follow_their_schemas(self):
		self.open_report_gate()
		name = self.make_record(MANAGER, title="Shape", rows=[{"item": "one"}])
		client = self.login(MANAGER)
		schemas = self.schemas(client)

		self.check(client, schemas, "search_doctypes", {"query": "AI"})
		self.check(client, schemas, "get_doctype_schema", {"doctype": DOCTYPE})
		listed = self.check(
			client, schemas, "list_documents", {"doctype": DOCTYPE, "fields": ["name", "title"]}
		)
		read = self.check(client, schemas, "get_document", {"doctype": DOCTYPE, "name": name})
		self.check(
			client,
			schemas,
			"run_report",
			{"report": "Permitted Documents For User", "filters": {"user": MANAGER, "doctype": DOCTYPE}},
		)

		self.assertIn(name, [row["name"] for row in listed["documents"]])
		self.assertEqual(read["document"]["rows"][0]["item"], "one")

	def test_write_and_proposal_results_follow_their_schemas(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		manager = self.login(MANAGER)
		schemas = self.schemas(manager)
		target = {"doctype": DOCTYPE, "name": name}

		created = self.check(
			client, schemas, "create_document", {"doctype": DOCTYPE, "data": {"title": "New"}}
		)
		updated = self.check(client, schemas, "update_document", {**target, "data": {"title": "New"}})
		self.check(client, schemas, "delete_document", target)
		self.check(manager, schemas, "purge_action_log", {})
		pending = self.check(client, schemas, "get_proposal", {"proposal_id": updated["proposal_id"]})
		self.approve(client, created["proposal_id"])
		done = self.check(client, schemas, "get_proposal", {"proposal_id": created["proposal_id"]})
		self.addCleanup(self.drop_record, done["result_document"])

		self.assertEqual(
			(pending["status"], done["status"], done["result"]), ("pending", "consumed", "succeeded")
		)
		self.assertNotIn("digest", pending)

	def test_denied_call_returns_the_error_shape(self):
		client = self.login(USER_A)

		result = self.call_tool(client, "get_document", {"doctype": DOCTYPE, "name": "missing-record"})

		self.assertTrue(result["isError"])
		self.assertEqual(set(result["structuredContent"]), {"error"})
		self.assertEqual(set(result["structuredContent"]["error"]), {"code", "message"})

	def test_validator_rejects_a_wrong_shape(self):
		schema = {"type": "object", "required": ["documents"], "properties": {"documents": {"type": "array"}}}

		self.assertEqual(problems({"documents": []}, schema), [])
		self.assertTrue(problems({"rows": []}, schema))
		self.assertTrue(problems({"documents": "x"}, schema))
