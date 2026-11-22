"""AI tools of the access rule engine, declared through the `ai_tools` hook (D-9).

The expected declaration format comes from the `x-ai-tools-hook` section of
`contracts/platform_core-yapay-zeka.openapi.yaml`. The AI layer is not merged yet, so the tests
call the declared functions the way that contract says the layer does: as the user, with the
validated arguments as keyword arguments.
"""

import re

import frappe
from pydantic import BaseModel, ValidationError

from platform_core.access.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	FREE_DOCTYPE,
	ROLE_EMPLOYEE,
	ROLE_NO_RULE,
	RULE_DOCTYPE,
	ErisimTestCase,
)

HOOK = "platform_core.access.ai_tools.declare"
NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
ALLOWED_KEYS = {
	"name",
	"description",
	"arguments",
	"kind",
	"roles",
	"destructive",
	"billable",
	"handler",
	"preview",
	"prepare",
	"versioned",
}
REQUIRED_KEYS = {"name", "description", "arguments", "kind", "handler"}
APPROVAL_FIELDS = {"confirm", "confirmed", "approve", "approved", "force"}
READ_TOOLS = {"list_access_rules", "explain_access"}
WRITE_TOOLS = {"propose_access_rule", "propose_access_rule_change"}
OWN_RULE = "Calisan kendi kaydi"


class AiToolsTestCase(ErisimTestCase):
	def declarations(self) -> dict[str, dict]:
		self.assertIn(HOOK, frappe.get_hooks("ai_tools") or [], "the ai_tools hook is not registered")
		return {declaration["name"]: declaration for declaration in frappe.get_attr(HOOK)()}

	def tool(self, tool_name: str) -> dict:
		declarations = self.declarations()
		self.assertIn(tool_name, declarations)
		return declarations[tool_name]

	def call(self, tool_name: str, user: str, part: str = "handler", /, **arguments):
		"""Validate the arguments with the declared model and call the function as the user."""
		declaration = self.tool(tool_name)
		model = frappe.get_attr(declaration["arguments"])
		validated = model(**arguments).model_dump()
		frappe.set_user(user)
		try:
			return frappe.get_attr(declaration[part])(**validated)
		finally:
			frappe.set_user("Administrator")

	def new_rule(self, **overrides) -> dict:
		return {
			"title": "AI proposed rule",
			"document_type": FREE_DOCTYPE,
			"role": ROLE_EMPLOYEE,
			"scope": "own",
			"match_field": "owner",
			"allow_read": True,
			**overrides,
		}


class TestDeclarations(AiToolsTestCase):
	def test_expected_tools_are_declared(self):
		self.assertEqual(set(self.declarations()), READ_TOOLS | WRITE_TOOLS)

	def test_declarations_follow_the_hook_contract(self):
		for name, declaration in self.declarations().items():
			with self.subTest(tool=name):
				self.assertLessEqual(set(declaration), ALLOWED_KEYS)
				self.assertLessEqual(REQUIRED_KEYS, set(declaration))
				self.assertRegex(name, NAME)
				self.assertIn(declaration["kind"], ("read", "write"))
				self.assertTrue(declaration["description"].isascii())
				self.assertTrue(callable(frappe.get_attr(declaration["handler"])))

	def test_argument_models_forbid_unknown_and_approval_fields(self):
		for name, declaration in self.declarations().items():
			with self.subTest(tool=name):
				model = frappe.get_attr(declaration["arguments"])
				self.assertTrue(issubclass(model, BaseModel))
				self.assertEqual(model.model_config.get("extra"), "forbid")
				self.assertFalse(APPROVAL_FIELDS & set(model.model_fields))
				for field in model.model_fields.values():
					self.assertTrue(field.description, f"{name}: every argument needs a description")

	def test_read_tools_are_not_write_tools(self):
		for name in READ_TOOLS:
			declaration = self.tool(name)
			self.assertEqual(declaration["kind"], "read")
			self.assertNotIn("preview", declaration)

	def test_write_tools_need_preview_and_are_destructive(self):
		for name in WRITE_TOOLS:
			declaration = self.tool(name)
			self.assertEqual(declaration["kind"], "write")
			self.assertIs(declaration.get("destructive"), True)
			self.assertTrue(callable(frappe.get_attr(declaration["preview"])))

	def test_tool_that_changes_a_saved_rule_is_versioned(self):
		self.assertIs(self.tool("propose_access_rule_change").get("versioned"), True)

	def test_no_tool_accepts_a_raw_condition(self):
		"""The model may only propose structured fields, never SQL text."""
		for name in WRITE_TOOLS:
			model = frappe.get_attr(self.tool(name)["arguments"])
			fields = set(model.model_fields)
			self.assertFalse({"condition", "conditions", "sql", "where", "query"} & fields)
			for extra in ("condition", "sql", "where"):
				arguments = {**self.new_rule(), "name": "AR-00001", extra: "1=1"}
				arguments = {key: value for key, value in arguments.items() if key in fields or key == extra}
				self.assertRaises(ValidationError, model, **arguments)


class TestListTool(AiToolsTestCase):
	def test_admin_lists_rules_of_a_document_type(self):
		result = self.call("list_access_rules", ADMIN, document_type=DOCTYPE)

		self.assertEqual(
			[(rule["title"], rule["role"], rule["scope"]) for rule in result["rules"]],
			[
				("Calisan kendi kaydi", "ER Calisan", "own"),
				("Yonetici ekibi", "ER Yonetici", "team"),
				("IK tum kayitlar", "ER HR", "all"),
			],
		)
		first = result["rules"][0]
		self.assertEqual(first["name"], self.rules[OWN_RULE])
		self.assertEqual(first["match_field"], "employee")
		self.assertEqual(first["operations"], ["read", "write", "create"])
		self.assertEqual(first["filters"], [])
		self.assertIs(first["is_active"], True)

	def test_inactive_rules_are_listed_only_on_request(self):
		frappe.db.set_value(RULE_DOCTYPE, self.rules[OWN_RULE], "is_active", 0)

		active = self.call("list_access_rules", ADMIN, document_type=DOCTYPE)
		everything = self.call("list_access_rules", ADMIN, document_type=DOCTYPE, include_inactive=True)

		self.assertNotIn(OWN_RULE, [rule["title"] for rule in active["rules"]])
		self.assertIn(OWN_RULE, [rule["title"] for rule in everything["rules"]])

	def test_user_without_rule_permission_cannot_list_rules(self):
		self.assertRaises(frappe.PermissionError, self.call, "list_access_rules", EMPLOYEE_1)

	def test_list_tool_is_limited_to_the_admin_role(self):
		self.assertEqual(self.tool("list_access_rules").get("roles"), ["System Manager"])


class TestExplainTool(AiToolsTestCase):
	def test_user_learns_own_access(self):
		result = self.call("explain_access", EMPLOYEE_1, doctype=DOCTYPE, name=self.records[EMPLOYEE_1])

		self.assertIs(result["allowed"], True)
		self.assertEqual(result["reason"], "allowed")

	def test_user_gets_no_detail_about_another_users_record(self):
		result = self.call("explain_access", EMPLOYEE_1, doctype=DOCTYPE, name=self.records[EMPLOYEE_2])

		self.assertIs(result["allowed"], False)
		self.assertEqual(result["reason"], "not_permitted_or_missing")
		self.assertEqual(result["rules"], [])

	def test_user_cannot_ask_about_another_user(self):
		self.assertRaises(
			frappe.PermissionError,
			self.call,
			"explain_access",
			EMPLOYEE_1,
			doctype=DOCTYPE,
			name=self.records[EMPLOYEE_1],
			user=EMPLOYEE_2,
		)

	def test_user_cannot_explain_a_document_type_they_cannot_read(self):
		self.assertRaises(
			frappe.PermissionError,
			self.call,
			"explain_access",
			EMPLOYEE_1,
			doctype=RULE_DOCTYPE,
			name=self.rules[OWN_RULE],
		)

	def test_admin_sees_which_rule_decided_for_another_user(self):
		result = self.call(
			"explain_access", ADMIN, doctype=DOCTYPE, name=self.records[EMPLOYEE_2], user=EMPLOYEE_1
		)

		self.assertIs(result["allowed"], False)
		self.assertEqual(result["reason"], "no_matching_rule")
		first = result["rules"][0]
		self.assertEqual((first["title"], first["applies"], first["matches"]), (OWN_RULE, True, False))

	def test_ptype_is_limited_to_known_operations(self):
		model = frappe.get_attr(self.tool("explain_access")["arguments"])

		self.assertRaises(ValidationError, model, doctype=DOCTYPE, name="x", ptype="drop")


class TestProposeRule(AiToolsTestCase):
	def drop_free_rules(self) -> None:
		frappe.set_user("Administrator")
		for name in frappe.get_all(RULE_DOCTYPE, filters={"document_type": FREE_DOCTYPE}, pluck="name"):
			frappe.delete_doc(RULE_DOCTYPE, name, force=True)

	def setUp(self):
		super().setUp()
		self.drop_free_rules()
		self.addCleanup(self.drop_free_rules)

	def free_rule_count(self) -> int:
		return frappe.db.count(RULE_DOCTYPE, {"document_type": FREE_DOCTYPE})

	def test_preview_describes_the_rule_and_writes_nothing(self):
		preview = self.call("propose_access_rule", ADMIN, "preview", **self.new_rule())

		self.assertEqual(self.free_rule_count(), 0)
		self.assertIn(FREE_DOCTYPE, preview["summary"])
		self.assertIn(ROLE_EMPLOYEE, preview["summary"])
		self.assertEqual(preview["target_doctype"], RULE_DOCTYPE)
		self.assertTrue(preview["target_version"])
		changes = {change["fieldname"]: change["new"] for change in preview["changes"]}
		self.assertEqual(changes["scope"], "own")
		self.assertEqual(changes["match_field"], "owner")
		self.assertEqual(changes["allow_read"], 1)

	def test_preview_text_follows_the_users_language(self):
		"""A human reads the preview before approving. It is visible text."""
		previous = frappe.local.lang
		self.addCleanup(setattr, frappe.local, "lang", previous)
		frappe.local.lang = "tr"

		preview = self.call("propose_access_rule", ADMIN, "preview", **self.new_rule())

		self.assertIn("oluştur", preview["summary"])
		self.assertIn(FREE_DOCTYPE, preview["summary"])
		self.assertIn("okuyamaz", preview["details"]["note"])

	def test_preview_warns_which_roles_lose_access(self):
		"""The first rule on a document type locks out every role without a rule."""
		preview = self.call("propose_access_rule", ADMIN, "preview", **self.new_rule())

		self.assertIs(preview["details"]["first_rule_on_document_type"], True)
		self.assertIn(ROLE_NO_RULE, preview["details"]["roles_without_access"])
		self.assertNotIn(ROLE_EMPLOYEE, preview["details"]["roles_without_access"])

	def test_handler_creates_the_rule_and_returns_its_name(self):
		result = self.call("propose_access_rule", ADMIN, **self.new_rule(filters=[]))

		rule = frappe.get_doc(RULE_DOCTYPE, result["name"])
		self.assertEqual(
			(rule.document_type, rule.role, rule.scope, rule.match_field, rule.allow_read, rule.allow_write),
			(FREE_DOCTYPE, ROLE_EMPLOYEE, "own", "owner", 1, 0),
		)

	def test_structured_filters_are_stored_as_rule_filters(self):
		filters = [{"field": "title", "operator": "!=", "value": "Hidden"}]

		result = self.call("propose_access_rule", ADMIN, **self.new_rule(filters=filters))

		stored = frappe.db.get_value(RULE_DOCTYPE, result["name"], "filters")
		self.assertEqual(frappe.parse_json(stored), [["title", "!=", "Hidden"]])

	def test_user_without_rule_permission_cannot_preview_or_create(self):
		for part in ("preview", "handler"):
			self.assertRaises(
				frappe.PermissionError, self.call, "propose_access_rule", EMPLOYEE_1, part, **self.new_rule()
			)
		self.assertEqual(self.free_rule_count(), 0)

	def test_preview_rejects_an_invalid_rule_with_a_validation_error(self):
		"""The contract maps `frappe.ValidationError` from a preview to `invalid_arguments`."""
		for overrides in (
			{"match_field": None},
			{"match_field": "no_such_field"},
			{"role": "AR No Such Role"},
			{"document_type": "AR No Such Type"},
			{"document_type": RULE_DOCTYPE, "scope": "all", "match_field": None},
			{"filters": [{"field": "1=1 or name", "operator": "=", "value": "x"}]},
			{"filters": [{"field": "title", "operator": "=", "value": "$user.password"}]},
			{"allow_read": False},
		):
			with self.subTest(overrides=overrides):
				self.assertRaises(
					frappe.ValidationError,
					self.call,
					"propose_access_rule",
					ADMIN,
					"preview",
					**self.new_rule(**overrides),
				)
		self.assertEqual(self.free_rule_count(), 0)

	def test_argument_model_rejects_unknown_scope_and_operator(self):
		model = frappe.get_attr(self.tool("propose_access_rule")["arguments"])

		self.assertRaises(ValidationError, model, **self.new_rule(scope="everything"))
		self.assertRaises(
			ValidationError,
			model,
			**self.new_rule(filters=[{"field": "title", "operator": "like", "value": "%"}]),
		)
		self.assertRaises(
			ValidationError,
			model,
			**self.new_rule(filters=[{"field": "title", "operator": "=", "value": "x", "sql": "1=1"}]),
		)

	def test_preview_version_changes_when_the_rule_set_changes(self):
		"""The layer compares `target_version` at approval. A new rule in between must change it."""
		before = self.call("propose_access_rule", ADMIN, "preview", **self.new_rule())
		self.call("propose_access_rule", ADMIN, **self.new_rule(title="Added in between", role="ER HR"))

		after = self.call("propose_access_rule", ADMIN, "preview", **self.new_rule())

		self.assertNotEqual(before["target_version"], after["target_version"])
		self.assertIs(after["details"]["first_rule_on_document_type"], False)


class TestProposeRuleChange(AiToolsTestCase):
	def restore(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		rule = frappe.get_doc(RULE_DOCTYPE, self.rules[OWN_RULE])
		rule.update({"is_active": 1, "scope": "own", "match_field": "employee", "allow_write": 1})
		rule.save()
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_preview_names_the_target_and_its_version(self):
		name = self.rules[OWN_RULE]

		preview = self.call("propose_access_rule_change", ADMIN, "preview", name=name, allow_write=False)

		self.assertEqual(preview["target_doctype"], RULE_DOCTYPE)
		self.assertEqual(preview["target_name"], name)
		self.assertEqual(preview["target_version"], str(frappe.db.get_value(RULE_DOCTYPE, name, "modified")))
		self.assertEqual(preview["changes"], [{"fieldname": "allow_write", "old": 1, "new": 0}])
		self.assertEqual(frappe.db.get_value(RULE_DOCTYPE, name, "allow_write"), 1)

	def test_preview_version_changes_after_the_rule_is_saved(self):
		name = self.rules[OWN_RULE]
		before = self.call("propose_access_rule_change", ADMIN, "preview", name=name, priority=11)
		self.addCleanup(self.restore)

		self.call("propose_access_rule_change", ADMIN, name=name, priority=12)
		after = self.call("propose_access_rule_change", ADMIN, "preview", name=name, priority=11)

		self.assertNotEqual(before["target_version"], after["target_version"])

	def test_preview_without_any_change_is_a_validation_error(self):
		self.assertRaises(
			frappe.ValidationError,
			self.call,
			"propose_access_rule_change",
			ADMIN,
			"preview",
			name=self.rules[OWN_RULE],
		)

	def test_preview_warns_when_deactivation_removes_a_roles_access(self):
		preview = self.call(
			"propose_access_rule_change", ADMIN, "preview", name=self.rules[OWN_RULE], is_active=False
		)

		self.assertIn(ROLE_EMPLOYEE, preview["details"]["roles_without_access"])

	def test_deactivation_takes_effect_on_the_next_request(self):
		employee = self.login(EMPLOYEE_1)
		own = self.records[EMPLOYEE_1]
		self.assertEqual(self.rest_get(employee, own).status_code, 200)
		self.addCleanup(self.restore)

		result = self.call("propose_access_rule_change", ADMIN, name=self.rules[OWN_RULE], is_active=False)

		self.assertEqual(result, {"name": self.rules[OWN_RULE]})
		self.assertEqual(self.rest_get(employee, own).status_code, 403)

	def test_invalid_change_is_rejected_in_preview_and_handler(self):
		for part in ("preview", "handler"):
			self.assertRaises(
				frappe.ValidationError,
				self.call,
				"propose_access_rule_change",
				ADMIN,
				part,
				name=self.rules[OWN_RULE],
				match_field="company",
			)
		self.assertEqual(frappe.db.get_value(RULE_DOCTYPE, self.rules[OWN_RULE], "match_field"), "employee")

	def test_user_without_rule_permission_cannot_preview_or_change(self):
		for part in ("preview", "handler"):
			self.assertRaises(
				frappe.PermissionError,
				self.call,
				"propose_access_rule_change",
				EMPLOYEE_1,
				part,
				name=self.rules[OWN_RULE],
				scope="all",
			)
		self.assertEqual(frappe.db.get_value(RULE_DOCTYPE, self.rules[OWN_RULE], "scope"), "own")

	def test_unknown_rule_is_not_found(self):
		self.assertRaises(
			frappe.DoesNotExistError,
			self.call,
			"propose_access_rule_change",
			ADMIN,
			"preview",
			name="AR-NO-SUCH",
			priority=1,
		)


class TestGenericWriteToolsAreClosed(AiToolsTestCase):
	"""O-28: the generic AI write tools may not change Access Rules. Only the engine's own tools may.

	The AI layer reads `ai_write_closed_doctypes` as a plain list of document type names
	(`contracts/platform_core-yapay-zeka.openapi.yaml`).
	"""

	def test_access_rule_is_closed_to_generic_write_tools(self):
		self.assertIn(RULE_DOCTYPE, frappe.get_hooks("ai_write_closed_doctypes") or [])

	def test_every_closed_document_type_of_the_engine_exists(self):
		from platform_core.access import ai_tools

		self.assertTrue(ai_tools.WRITE_CLOSED_DOCTYPES)
		for doctype in ai_tools.WRITE_CLOSED_DOCTYPES:
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)
			self.assertIn(doctype, frappe.get_hooks("ai_write_closed_doctypes") or [])

	def test_the_engine_still_offers_its_own_write_tools_for_the_closed_type(self):
		"""Closing the generic tools must not leave Access Rules unmanageable by AI (D-9)."""
		declarations = self.declarations()

		self.assertEqual({"propose_access_rule", "propose_access_rule_change"} - set(declarations), set())
