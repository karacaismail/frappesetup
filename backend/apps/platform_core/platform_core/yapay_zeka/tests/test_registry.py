"""Araç kaydı: `ai_tools` kancası (G-105) ve kodun durağan denetimleri (B-10)."""

import re
from pathlib import Path
from unittest.mock import patch

import frappe

import platform_core
from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, USER_B, YzTestCase

HOOK = "platform_core.yapay_zeka.tests.sample_tools.declare"
APP_ROOT = Path(platform_core.__file__).parent
LAYER = APP_ROOT / "yapay_zeka"

PROVIDER_LIBRARIES = (
	"anthropic|openai|google\\.generativeai|google\\.genai|genai|vertexai|mistralai|cohere|ollama|groq|"
	"litellm|langchain\\w*|llama_index|together|replicate|huggingface_hub|transformers"
)
MODEL_NAMES = r"\b(claude-|gpt-\d|gemini-|mistral-|llama-?\d|command-r|o[134]-mini)"


def with_sample_tools():
	"""Örnek araçları kancaya ekler. Yama süreç genelindedir, istek iş parçacığını da kapsar."""
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		if hook == "ai_tools":
			return [HOOK]
		return original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


def python_files(root: Path, *, tests: bool):
	for path in sorted(root.rglob("*.py")):
		if tests or "tests" not in path.relative_to(root).parts:
			yield path


class TestAiToolsHook(YzTestCase):
	def tool_names(self, client) -> set[str]:
		return {tool["name"] for tool in self.rpc(client, "tools/list").json["result"]["tools"]}

	def test_valid_declarations_are_listed_and_invalid_ones_are_left_out(self):
		client = self.login(USER_A)

		with with_sample_tools():
			names = self.tool_names(client)

		self.assertIn("platform_core_count_records", names)
		self.assertIn("platform_core_set_title", names)
		for invalid in ("write_without_preview", "with_confirm_field", "loose_arguments", "Bad Name"):
			self.assertFalse([name for name in names if invalid in name], invalid)

	def test_role_limited_tool_is_hidden_and_denied(self):
		client = self.login(USER_A)
		manager = self.login(MANAGER)

		with with_sample_tools():
			names_user = self.tool_names(client)
			names_manager = self.tool_names(manager)
			denied = self.call_tool(client, "platform_core_manager_only", {})

		self.assertNotIn("platform_core_manager_only", names_user)
		self.assertIn("platform_core_manager_only", names_manager)
		self.assert_denied(denied, "role_required")
		self.assertEqual(self.last_log(tool="platform_core_manager_only").deny_reason, "role_required")

	def test_app_read_tool_runs_with_the_users_permissions(self):
		self.make_record(USER_A)
		self.make_record(USER_A)
		self.make_record(USER_B)
		client = self.login(USER_A)

		with with_sample_tools():
			result = self.call_tool(client, "platform_core_count_records", {})

		self.assertEqual(result["structuredContent"]["count"], 2)
		self.assertEqual(self.last_log(tool="platform_core_count_records").tool_class, "app")

	def test_app_write_tool_goes_through_preview_and_approval(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)

		with with_sample_tools():
			proposal = self.call_tool(client, "platform_core_set_title", {"name": name, "title": "Yeni"})[
				"structuredContent"
			]
			unchanged = frappe.db.get_value(DOCTYPE, name, "title")
			shown = self.human(client, "GET", "get_proposal", query={"proposal_id": proposal["proposal_id"]})
			outcome = self.approve(client, proposal["proposal_id"]).json["message"]

		self.assertEqual(proposal["status"], "approval_required")
		self.assertEqual(unchanged, "Eski")
		self.assertTrue(shown.json["message"]["destructive"])
		self.assertTrue(shown.json["message"]["billable"])
		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Yeni")

	def test_app_write_tool_is_denied_for_another_users_record(self):
		name = self.make_record(USER_A, title="Eski")
		client_b = self.login(USER_B)

		with with_sample_tools():
			result = self.call_tool(client_b, "platform_core_set_title", {"name": name, "title": "Yeni"})

		self.assert_denied(result, "permission")


class TestStaticRules(YzTestCase):
	def test_no_model_provider_library_in_the_app(self):
		pattern = re.compile(rf"^\s*(?:import|from)\s+(?:{PROVIDER_LIBRARIES})\b", re.MULTILINE)
		offenders = [
			str(path) for path in python_files(APP_ROOT, tests=True) if pattern.search(path.read_text())
		]
		pyproject = (APP_ROOT.parent / "pyproject.toml").read_text()
		declared = re.findall(rf'"\s*(?:{PROVIDER_LIBRARIES})\s*[~=<>!"\[]', pyproject)

		self.assertEqual(offenders, [])
		self.assertEqual(declared, [])

	def test_no_model_name_in_the_layer(self):
		pattern = re.compile(MODEL_NAMES, re.IGNORECASE)
		files = [*python_files(LAYER, tests=True), APP_ROOT / "api" / "ai.py", *LAYER.rglob("*.json")]
		offenders = [
			str(path) for path in files if path != Path(__file__) and pattern.search(path.read_text())
		]

		self.assertEqual(offenders, [])

	def test_layer_code_does_not_bypass_permissions(self):
		rules = {
			r"ignore_permissions": {"store.py"},
			r"frappe\.get_all\(|frappe\.db\.get_all\(": {"store.py"},
			r"frappe\.db\.sql|frappe\.qb\b": {"agent_token.py"},
			r"frappe\.db\.(get_value|set_value|exists|delete)\(": {"store.py"},
			r"\b(eval|exec)\(|subprocess|os\.system|safe_exec|run_server_script": set(),
			r"frappe\.get_attr\(": {"registry.py"},
		}
		offenders = []
		for path in python_files(LAYER, tests=False):
			text = path.read_text()
			for pattern, allowed in rules.items():
				if re.search(pattern, text) and path.name not in allowed:
					offenders.append(f"{path.name}: {pattern}")

		self.assertEqual(offenders, [])

	def test_module_boundaries(self):
		imports = re.compile(r"^\s*(?:from|import)\s+platform_core\.(\w+)", re.MULTILINE)
		allowed = {"yapay_zeka", "model_gecidi"}
		outward = {
			f"{path.name}: {module}"
			for path in [*python_files(LAYER, tests=True), APP_ROOT / "api" / "ai.py"]
			for module in imports.findall(path.read_text())
			if module not in allowed
		}
		inward = [
			str(path)
			for path in python_files(APP_ROOT, tests=True)
			if LAYER not in path.parents
			and path != APP_ROOT / "api" / "ai.py"
			and re.search(r"platform_core\.yapay_zeka|from platform_core import yapay_zeka", path.read_text())
			and path.name != "hooks.py"
		]

		self.assertEqual(outward, set())
		self.assertEqual(inward, [])

	def test_hooks_are_registered(self):
		self.assertIn(
			"platform_core.yapay_zeka.agent_token.authenticate_request", frappe.get_hooks("auth_hooks")
		)
		self.assertIn("platform_core.yapay_zeka.setup.disable_builtin_mcp", frappe.get_hooks("after_migrate"))
		self.assertFalse(frappe.get_hooks("scheduler_events", app_name="platform_core"))

	def test_every_field_of_the_layer_doctypes_has_a_description(self):
		for doctype in ("AI Action Log", "AI Action Proposal"):
			for field in frappe.get_meta(doctype).fields:
				if field.fieldtype not in ("Section Break", "Column Break", "Tab Break"):
					self.assertTrue(field.description, f"{doctype}.{field.fieldname}")

	def test_log_is_append_only(self):
		log = frappe.get_all("AI Action Log", limit=1, pluck="name")
		if not log:
			client = self.login(USER_A)
			self.call_tool(client, "search_doctypes", {})
			log = frappe.get_all("AI Action Log", limit=1, pluck="name")
		doc = frappe.get_doc("AI Action Log", log[0])
		doc.decision = "allowed" if doc.decision == "denied" else "denied"

		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "AI Action Log", log[0], force=True)


class TestContract(YzTestCase):
	"""Sözleşmedeki araç şeması ile çalışan araç kaydı aynı olmalı (SZ-3)."""

	CONTRACT = APP_ROOT.parents[2] / "contracts" / "platform_core-yapay-zeka.openapi.yaml"

	def setUp(self):
		super().setUp()
		if not self.CONTRACT.exists():
			self.skipTest(f"Sözleşme dosyası bu ortamda yok: {self.CONTRACT}")
		import yaml

		self.contract = yaml.safe_load(self.CONTRACT.read_text())

	def test_tool_names_classes_and_arguments_match_the_contract(self):
		from platform_core.yapay_zeka import registry

		shared = self.contract["x-mcp-schemas"]
		declared = {}
		for tool in self.contract["x-mcp-tools"]:
			schema = tool["inputSchema"]
			if "$ref" in schema:
				schema = shared[schema["$ref"].rsplit("/", 1)[-1]]
			declared[tool["name"]] = (
				tool["class"],
				sorted(schema.get("properties", {})),
				sorted(schema.get("required", [])),
				bool(tool["annotations"].get("readOnlyHint")),
			)
		actual = {
			tool.name: (
				tool.tool_class,
				sorted(tool.input_schema["properties"]),
				sorted(tool.input_schema.get("required", [])),
				tool.kind == "read",
			)
			for tool in registry.builtin_tools()
		}

		self.assertEqual(actual, declared)

	def test_every_endpoint_of_the_contract_is_whitelisted_with_its_method(self):
		for path, operations in self.contract["paths"].items():
			function = frappe.get_attr(path.lstrip("/"))
			self.assertIn(function, frappe.whitelisted, path)
			allowed = [
				method.lower() for method in frappe.allowed_http_methods_for_whitelisted_func[function]
			]
			self.assertEqual(sorted(operations), sorted(allowed), path)
			for operation in operations.values():
				self.assertTrue(operation["summary"] and operation["description"], path)

	def test_deny_reasons_used_in_code_are_in_the_contract(self):
		declared = set(self.contract["components"]["schemas"]["DenyReason"]["enum"])
		used = set()
		for path in python_files(LAYER, tests=False):
			text = path.read_text()
			used |= set(re.findall(r'ToolDenied\(\s*"(\w+)"', text))
			used |= set(re.findall(r'deny_reason="(\w+)"', text))
			used |= set(re.findall(r'_den(?:y|ied)\(\w+, "(\w+)"', text))

		self.assertLessEqual(used, declared)
		self.assertGreater(len(used), 10)
