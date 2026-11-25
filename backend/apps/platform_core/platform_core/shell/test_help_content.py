"""G-138: help content resolution order, field permission and coverage report.

The expected results come from requirement G-138 in `src/data/requirements.json`:
tenant content, then application content, then the Frappe field `description`,
then the generic "no help" answer with a request-help action. A field the user
cannot read returns no help at all.
"""

import unittest

from platform_core.shell.help_content import (
	NO_HELP_MESSAGE,
	coverage_report,
	resolve_field_help,
	target_errors,
)

DOCTYPE = "Sales Invoice"
FIELD = "due_date"


def topic(name, layer, **values):
	record = {
		"name": name,
		"title": f"Title {name}",
		"content": f"Content {name}",
		"layer": layer,
		"status": "Published",
		"target_type": "Field",
		"document_type": DOCTYPE,
		"fieldname": FIELD,
		"language": "",
		"version": "",
		"roles": [],
		"modified": "2026-11-25 10:00:00",
	}
	record.update(values)
	return record


def resolve(
	topics,
	*,
	readable=True,
	description="Field description.",
	language="tr",
	version="16.1.0",
	roles=("Accounts User",),
):
	return resolve_field_help(
		doctype=DOCTYPE,
		fieldname=FIELD,
		readable=readable,
		topics=topics,
		description=description,
		language=language,
		version=version,
		roles=roles,
	)


class FallbackOrderTest(unittest.TestCase):
	def test_tenant_content_comes_first(self):
		answer = resolve([topic("APP-1", "App"), topic("TEN-1", "Tenant")])
		self.assertEqual(answer["source"], "tenant")
		self.assertEqual(answer["topic"], "TEN-1")
		self.assertEqual(answer["content"], "Content TEN-1")
		self.assertEqual(answer["actions"], [])

	def test_application_content_follows_when_tenant_content_is_missing(self):
		answer = resolve([topic("APP-1", "App")])
		self.assertEqual(answer["source"], "app")
		self.assertEqual(answer["topic"], "APP-1")
		self.assertEqual(answer["content"], "Content APP-1")

	def test_field_description_follows_when_no_topic_applies(self):
		answer = resolve([], description="Date the payment is due.")
		self.assertEqual(answer["source"], "description")
		self.assertIsNone(answer["topic"])
		self.assertEqual(answer["content"], "Date the payment is due.")
		self.assertEqual(answer["actions"], [])

	def test_generic_answer_offers_the_request_help_action_last(self):
		answer = resolve([], description="  ")
		self.assertEqual(answer["source"], "none")
		self.assertIsNone(answer["topic"])
		self.assertIsNone(answer["content"])
		self.assertEqual(answer["message"], NO_HELP_MESSAGE)
		self.assertEqual(NO_HELP_MESSAGE, "No help is available for this field.")
		self.assertEqual(answer["actions"], ["request_help"])

	def test_unpublished_topics_are_skipped(self):
		for status in ("Draft", "In Review", "Archived"):
			with self.subTest(status=status):
				answer = resolve([topic("TEN-1", "Tenant", status=status)])
				self.assertEqual(answer["source"], "description")

	def test_topics_of_another_target_are_skipped(self):
		other_field = topic("TEN-1", "Tenant", fieldname="posting_date")
		other_doctype = topic("TEN-2", "Tenant", document_type="Purchase Invoice")
		other_kind = topic("TEN-3", "Tenant", target_type="Route", route_pattern="/app/*")
		self.assertEqual(resolve([other_field, other_doctype, other_kind])["source"], "description")

	def test_language_must_match_or_be_empty(self):
		self.assertEqual(resolve([topic("TEN-1", "Tenant", language="en")])["source"], "description")
		self.assertEqual(resolve([topic("TEN-1", "Tenant", language="tr")])["source"], "tenant")
		# A regional language falls back to its base language.
		self.assertEqual(
			resolve([topic("TEN-1", "Tenant", language="tr")], language="tr-TR")["source"], "tenant"
		)

	def test_version_must_match_or_be_empty(self):
		self.assertEqual(resolve([topic("APP-1", "App", version="15.0.0")])["source"], "description")
		self.assertEqual(resolve([topic("APP-1", "App", version="16.1.0")])["source"], "app")

	def test_target_roles_must_include_a_role_of_the_user(self):
		other_role = topic("TEN-1", "Tenant", roles=["Accounts Manager"])
		self.assertEqual(resolve([other_role])["source"], "description")
		own_role = topic("TEN-1", "Tenant", roles=["Accounts Manager", "Accounts User"])
		self.assertEqual(resolve([own_role])["source"], "tenant")

	def test_the_most_specific_topic_wins_inside_a_layer(self):
		generic = topic("TEN-1", "Tenant", modified="2026-11-25 12:00:00")
		language = topic("TEN-2", "Tenant", language="tr", modified="2026-11-24 12:00:00")
		self.assertEqual(resolve([generic, language])["topic"], "TEN-2")
		newer = topic("TEN-3", "Tenant", language="tr", modified="2026-11-25 12:00:00")
		self.assertEqual(resolve([generic, language, newer])["topic"], "TEN-3")


class FieldPermissionTest(unittest.TestCase):
	def test_unreadable_field_returns_no_help_from_any_layer(self):
		answer = resolve(
			[topic("TEN-1", "Tenant"), topic("APP-1", "App")],
			readable=False,
			description="Secret field description.",
		)
		self.assertEqual(answer["source"], "unavailable")
		self.assertIsNone(answer["topic"])
		self.assertIsNone(answer["content"])
		self.assertIsNone(answer["title"])
		self.assertEqual(answer["actions"], [])
		self.assertNotIn("Content", repr(answer))
		self.assertNotIn("Secret", repr(answer))


class TargetRuleTest(unittest.TestCase):
	def test_field_target_needs_document_type_and_fieldname(self):
		self.assertEqual(
			target_errors(
				{"target_type": "Field", "layer": "App"}, field_exists=False, field_is_custom=False
			),
			["document_type", "fieldname"],
		)

	def test_field_target_needs_an_existing_field(self):
		record = topic("TEN-1", "Tenant")
		self.assertEqual(target_errors(record, field_exists=False, field_is_custom=False), ["field_missing"])
		self.assertEqual(target_errors(record, field_exists=True, field_is_custom=False), [])

	def test_custom_field_help_belongs_to_the_tenant_layer(self):
		record = topic("APP-1", "App")
		self.assertEqual(
			target_errors(record, field_exists=True, field_is_custom=True), ["custom_field_layer"]
		)
		record = topic("TEN-1", "Tenant")
		self.assertEqual(target_errors(record, field_exists=True, field_is_custom=True), [])

	def test_component_and_route_targets_need_their_key(self):
		self.assertEqual(target_errors({"target_type": "Component", "layer": "App"}), ["component_id"])
		self.assertEqual(target_errors({"target_type": "Route", "layer": "App"}), ["route_pattern"])
		self.assertEqual(
			target_errors({"target_type": "Route", "layer": "App", "route_pattern": "/app/*"}), []
		)
		self.assertEqual(target_errors({"target_type": "Other", "layer": "App"}), ["target_type"])


FIELDS = [
	{"doctype": DOCTYPE, "fieldname": "due_date", "description": "", "is_custom": False},
	{"doctype": DOCTYPE, "fieldname": "posting_date", "description": "Posting date.", "is_custom": False},
	{"doctype": DOCTYPE, "fieldname": "customer", "description": None, "is_custom": False},
	{"doctype": DOCTYPE, "fieldname": "custom_region", "description": "", "is_custom": True},
]


class CoverageReportTest(unittest.TestCase):
	def test_ratio_counts_topics_and_descriptions(self):
		topics = [
			topic("TEN-1", "Tenant"),
			# A draft topic does not count as help.
			topic("TEN-2", "Tenant", fieldname="customer", status="Draft"),
			# Two topics on one field count once.
			topic("APP-1", "App"),
		]
		report = coverage_report(FIELDS, topics)
		self.assertEqual(report["total"], 4)
		self.assertEqual(report["with_topic"], 1)
		self.assertEqual(report["with_description_only"], 1)
		self.assertEqual(report["covered"], 2)
		self.assertEqual(report["without_help"], 2)
		self.assertEqual(report["ratio"], 0.5)
		self.assertEqual(report["topic_ratio"], 0.25)
		self.assertEqual(
			report["missing"],
			[
				{"doctype": DOCTYPE, "fieldname": "customer", "is_custom": False},
				{"doctype": DOCTYPE, "fieldname": "custom_region", "is_custom": True},
			],
		)

	def test_ratio_is_unknown_without_fields(self):
		report = coverage_report([], [])
		self.assertEqual(report["total"], 0)
		self.assertIsNone(report["ratio"])
		self.assertIsNone(report["topic_ratio"])


if __name__ == "__main__":
	unittest.main()
