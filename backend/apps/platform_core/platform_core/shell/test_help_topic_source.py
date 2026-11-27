"""G-138: check the shipped help topic DocType definitions without a site."""

import csv
import json
import unittest
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DOCTYPES = APP / "shell" / "doctype"
TOPIC = DOCTYPES / "plt_help_topic" / "plt_help_topic.json"
ROLE = DOCTYPES / "plt_help_topic_role" / "plt_help_topic_role.json"

# G-138 names these attributes of a help topic.
REQUIRED_FIELDS = {
	"layer",
	"app",
	"target_type",
	"document_type",
	"fieldname",
	"component_id",
	"route_pattern",
	"language",
	"version",
	"target_roles",
	"content_owner",
	"status",
	"content",
}


def load(path):
	return json.loads(path.read_text(encoding="utf-8"))


class HelpTopicSourceTest(unittest.TestCase):
	def test_definitions_follow_frappe_export_format(self):
		for path in (TOPIC, ROLE):
			with self.subTest(doctype=path.stem):
				source = path.read_text(encoding="utf-8")
				definition = json.loads(source)
				self.assertEqual(source, json.dumps(definition, indent=1, sort_keys=True) + "\n")
				self.assertIsInstance(datetime.fromisoformat(definition["modified"]), datetime)
				self.assertEqual(definition["module"], "Shell")
				self.assertEqual(definition["field_order"], [f["fieldname"] for f in definition["fields"]])

	def test_topic_carries_the_g138_attributes(self):
		definition = load(TOPIC)
		self.assertEqual(definition["name"], "PLT Help Topic")
		fields = {field["fieldname"]: field for field in definition["fields"]}
		self.assertLessEqual(REQUIRED_FIELDS, set(fields))
		self.assertEqual(fields["layer"]["options"].splitlines(), ["Tenant", "App"])
		self.assertEqual(fields["target_type"]["options"].splitlines(), ["Field", "Component", "Route"])
		self.assertEqual(
			fields["status"]["options"].splitlines(), ["Draft", "In Review", "Published", "Archived"]
		)
		self.assertEqual(fields["status"]["default"], "Draft")
		self.assertEqual(fields["document_type"]["options"], "DocType")
		self.assertEqual(fields["language"]["options"], "Language")
		self.assertEqual(fields["content_owner"]["options"], "User")
		self.assertEqual(fields["target_roles"]["fieldtype"], "Table MultiSelect")
		self.assertEqual(fields["target_roles"]["options"], "PLT Help Topic Role")
		# Content is plain text, so the help panel never renders stored markup.
		self.assertEqual(fields["content"]["fieldtype"], "Text")

	def test_only_the_system_manager_edits_topics(self):
		permissions = load(TOPIC)["permissions"]
		self.assertEqual([p["role"] for p in permissions], ["System Manager"])
		self.assertTrue(all(p.get(key) for p in permissions for key in ("read", "write", "create", "delete")))

	def test_help_links_are_optional_data_fields(self):
		fields = {field["fieldname"]: field for field in load(TOPIC)["fields"]}
		for name in ("tour_url", "doc_url", "support_url"):
			self.assertEqual(fields[name]["fieldtype"], "Data")
			self.assertFalse(fields[name].get("reqd"))

	def test_role_table_is_a_child_table(self):
		definition = load(ROLE)
		self.assertEqual(definition["name"], "PLT Help Topic Role")
		self.assertEqual(definition["istable"], 1)
		self.assertEqual([f["fieldname"] for f in definition["fields"]], ["role"])
		self.assertEqual(definition["fields"][0]["options"], "Role")

	def test_every_field_has_a_description_and_translation(self):
		with (APP / "translations" / "tr.csv").open(encoding="utf-8", newline="") as source:
			translations = {(row[0], row[2]) for row in csv.reader(source, strict=True)}
		for path in (TOPIC, ROLE):
			definition = load(path)
			name = definition["name"]
			texts = [name, definition["description"]]
			for field in definition["fields"]:
				if field["fieldtype"] in {"Section Break", "Column Break"}:
					continue
				with self.subTest(doctype=name, field=field["fieldname"]):
					self.assertTrue(field.get("description", "").strip())
				texts.extend((field["label"], field["description"]))
				if field["fieldtype"] == "Select":
					texts.extend(field["options"].splitlines())
			for text in texts:
				with self.subTest(doctype=name, source=text):
					self.assertTrue((text, name) in translations or (text, "") in translations)


if __name__ == "__main__":
	unittest.main()
