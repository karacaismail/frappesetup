"""Pure serialization checks derived from G-63 and the shell task acceptance cases.

HTTP authorization and the Frappe permission engine require separate integration tests.
These fixtures contain invented metadata only.
"""

import copy
import unittest

from platform_core.kabuk.serialization import digest, etag_for, matches_etag, project_meta


def sample_schema() -> dict:
	"""Return effective metadata after a site's custom fields and property setters."""
	return {
		"name": "Sample Record",
		"module": "Kabuk",
		"title_field": "title",
		"search_fields": "title,private_note",
		"sort_field": "private_note",
		"permissions": [{"role": "Internal Administrator", "read": 1}],
		"links": [{"link_doctype": "Private Record"}],
		"actions": [{"name": "Internal operation"}],
		"owner": "internal@example.test",
		"modified_by": "internal@example.test",
		"creation": "2026-11-22 00:00:00",
		"modified": "2026-11-22 01:00:00",
		"fields": [
			{
				"fieldname": "title",
				"fieldtype": "Data",
				"label": "Custom title",
				"description": "The site's customized title.",
				"reqd": 1,
				"read_only": 0,
				"hidden": 0,
				"permlevel": 0,
				"length": 80,
			},
			{
				"fieldname": "private_note",
				"fieldtype": "Small Text",
				"label": "Private note",
				"description": "A note restricted to the second permission level.",
				"permlevel": 1,
				"read_only": 0,
			},
		],
	}


class TestMetadataProjection(unittest.TestCase):
	def test_two_users_receive_different_fields_and_etags(self):
		schema = sample_schema()
		reader = project_meta(schema, {"title"}, set())
		manager = project_meta(schema, {"title", "private_note"}, {"title", "private_note"})

		self.assertEqual([field["fieldname"] for field in reader["fields"]], ["title"])
		self.assertEqual([field["fieldname"] for field in manager["fields"]], ["title", "private_note"])
		self.assertNotIn("private_note", str(reader))
		self.assertNotEqual(
			etag_for("site.example.test", "reader@example.test", "1", reader),
			etag_for("site.example.test", "manager@example.test", "1", manager),
		)

	def test_revoked_field_does_not_survive_a_new_projection(self):
		schema = sample_schema()
		before = project_meta(schema, {"title", "private_note"}, {"title", "private_note"})
		after = project_meta(schema, {"title"}, {"title"})

		self.assertNotIn("private_note", str(after))
		self.assertNotEqual(
			etag_for("site.example.test", "reader@example.test", "1", before),
			etag_for("site.example.test", "reader@example.test", "2", after),
		)

	def test_empty_read_permission_exposes_no_fields(self):
		result = project_meta(sample_schema(), set(), {"title", "private_note"})

		self.assertEqual(result["fields"], [])
		self.assertNotIn("title", result.get("search_fields") or "")
		self.assertFalse(result.get("title_field"))
		self.assertFalse(result.get("sort_field"))

	def test_read_permission_without_write_makes_field_read_only(self):
		result = project_meta(sample_schema(), {"title"}, set())

		self.assertTrue(result["fields"][0]["read_only"])

	def test_write_permission_cannot_remove_site_read_only_setting(self):
		schema = sample_schema()
		schema["fields"][0]["read_only"] = 1

		result = project_meta(schema, {"title"}, {"title"})

		self.assertTrue(result["fields"][0]["read_only"])

	def test_writable_field_remains_editable(self):
		result = project_meta(sample_schema(), {"title"}, {"title"})

		self.assertFalse(result["fields"][0]["read_only"])

	def test_custom_field_settings_are_preserved(self):
		schema = sample_schema()
		custom = schema["fields"][0]
		custom.update(
			options="Short\nLong",
			default="Short",
			depends_on="eval:doc.title",
			mandatory_depends_on="eval:doc.title",
			read_only_depends_on="eval:doc.title",
			fetch_from="source.title",
			fetch_if_empty=1,
			set_only_once=1,
			unique=1,
			in_list_view=1,
			in_standard_filter=1,
			precision="2",
			non_negative=1,
			collapsible=1,
			collapsible_depends_on="eval:doc.title",
		)

		result = project_meta(schema, {"title", "source"}, {"title"})

		for key in ("depends_on", "mandatory_depends_on", "read_only_depends_on", "collapsible_depends_on"):
			custom[key] = {"scope": "doc", "field": "title", "op": "truthy"}
		self.assertEqual(result["fields"][0], custom)

	def test_dependencies_on_unreadable_fields_are_removed(self):
		schema = sample_schema()
		schema["fields"][0].update(
			depends_on="eval:doc.title && doc.private_note",
			mandatory_depends_on="private_note",
			read_only_depends_on="eval:doc['private_note']",
			collapsible_depends_on="eval:doc.title",
		)
		field = project_meta(schema, {"title"}, {"title"})["fields"][0]
		for key in ("depends_on", "mandatory_depends_on", "read_only_depends_on"):
			self.assertNotIn(key, field)
		self.assertEqual(field["collapsible_depends_on"], {"scope": "doc", "field": "title", "op": "truthy"})
		self.assertEqual(
			field["unsupported_conditions"], ["depends_on", "mandatory_depends_on", "read_only_depends_on"]
		)

	def test_dependencies_require_a_readable_parent_field(self):
		schema = sample_schema()
		schema["fields"][0]["depends_on"] = "eval:parent.private_note"
		field = project_meta(schema, {"title"}, {"title"})["fields"][0]
		self.assertNotIn("depends_on", field)
		allowed = project_meta(schema, {"title"}, {"title"}, parent_readable={"private_note"})
		self.assertEqual(
			allowed["fields"][0]["depends_on"], {"scope": "parent", "field": "private_note", "op": "truthy"}
		)

	def test_comparison_is_declarative_and_function_calls_are_omitted(self):
		schema = sample_schema()
		schema["fields"][0].update(
			depends_on="eval:doc.title === 'Sample'",
			read_only_depends_on="eval:customFunction(doc.title)",
		)
		field = project_meta(schema, {"title"}, {"title"})["fields"][0]
		self.assertEqual(
			field["depends_on"], {"scope": "doc", "field": "title", "op": "eq", "value": "Sample"}
		)
		self.assertNotIn("read_only_depends_on", field)
		self.assertEqual(field["unsupported_conditions"], ["read_only_depends_on"])

	def test_fetch_from_and_dynamic_links_cannot_reference_hidden_fields(self):
		schema = sample_schema()
		schema["fields"][0]["fetch_from"] = "private_note.title"
		schema["fields"].append(
			{
				"fieldname": "target",
				"fieldtype": "Dynamic Link",
				"options": "private_note",
			}
		)
		readable = {"title", "target"}
		fields = project_meta(schema, readable, set())["fields"]
		self.assertNotIn("fetch_from", fields[0])
		self.assertNotIn("options", fields[1])
		visible_source = project_meta(schema, readable | {"private_note"}, set())["fields"]
		self.assertEqual(visible_source[0]["fetch_from"], "private_note.title")
		self.assertEqual(visible_source[-1]["options"], "private_note")

	def test_display_hidden_setting_is_not_a_permission_grant(self):
		schema = sample_schema()
		schema["fields"][0]["hidden"] = 1
		schema["fields"][1]["hidden"] = 0

		result = project_meta(schema, {"title"}, {"title"})

		self.assertEqual([field["fieldname"] for field in result["fields"]], ["title"])
		self.assertEqual(result["fields"][0]["hidden"], 1)

	def test_permission_rules_and_audit_metadata_are_not_exported(self):
		schema = sample_schema()
		schema["fields"][0].update(
			name="private-docfield-id",
			parent="Sample Record",
			owner="internal@example.test",
			modified_by="internal@example.test",
			_internal_cache={"sensitive": True},
		)

		result = project_meta(schema, {"title"}, {"title"})

		for key in ("permissions", "links", "actions", "owner", "modified_by", "creation", "modified"):
			with self.subTest(top_level_key=key):
				self.assertNotIn(key, result)
		for key in ("name", "parent", "owner", "modified_by", "_internal_cache"):
			with self.subTest(field_key=key):
				self.assertNotIn(key, result["fields"][0])

	def test_field_references_only_name_readable_fields(self):
		schema = sample_schema()
		schema["title_field"] = "private_note"

		result = project_meta(schema, {"title"}, {"title"})

		self.assertFalse(result.get("title_field"))
		self.assertFalse(result.get("sort_field"))
		self.assertEqual(result.get("search_fields"), "title")

	def test_visible_field_references_are_preserved(self):
		schema = sample_schema()
		schema["sort_field"] = "title"
		schema["search_fields"] = "title"

		result = project_meta(schema, {"title"}, {"title"})

		self.assertEqual(result.get("title_field"), "title")
		self.assertEqual(result.get("sort_field"), "title")
		self.assertEqual(result.get("search_fields"), "title")

	def test_source_metadata_is_not_mutated_or_shared(self):
		schema = sample_schema()
		before = copy.deepcopy(schema)

		result = project_meta(schema, {"title"}, set())

		self.assertEqual(schema, before)
		result["fields"][0]["label"] = "Client changed label"
		self.assertEqual(schema, before)


class TestMetadataDigests(unittest.TestCase):
	def test_digest_ignores_mapping_insertion_order(self):
		left = {"fields": [{"label": "Café", "fieldname": "title"}], "name": "Sample"}
		right = {"name": "Sample", "fields": [{"fieldname": "title", "label": "Café"}]}

		self.assertEqual(digest(left), digest(right))
		self.assertRegex(digest(left), r"^[0-9a-f]{64}$")

	def test_digest_preserves_field_order_and_values(self):
		first = {"fields": ["title", "private_note"]}
		reordered = {"fields": ["private_note", "title"]}
		changed = {"fields": ["title", "public_note"]}

		self.assertNotEqual(digest(first), digest(reordered))
		self.assertNotEqual(digest(first), digest(changed))

	def test_etag_is_quoted_and_scoped_to_site_user_and_permission_version(self):
		payload = {"fields": []}
		baseline = etag_for("site-a.example.test", "reader@example.test", "1", payload)

		self.assertRegex(baseline, r'^"[0-9a-f]{64}"$')
		for site, user, version in [
			("site-b.example.test", "reader@example.test", "1"),
			("site-a.example.test", "other@example.test", "1"),
			("site-a.example.test", "reader@example.test", "2"),
		]:
			with self.subTest(site=site, user=user, version=version):
				self.assertNotEqual(baseline, etag_for(site, user, version, payload))

	def test_etag_changes_when_effective_metadata_changes(self):
		before = {"fields": [{"fieldname": "title", "label": "Title"}]}
		after = {"fields": [{"fieldname": "title", "label": "Custom title"}]}

		self.assertNotEqual(
			etag_for("site.example.test", "reader@example.test", "1", before),
			etag_for("site.example.test", "reader@example.test", "1", after),
		)


class TestConditionalGet(unittest.TestCase):
	def test_matching_strong_weak_list_and_wildcard_validators(self):
		for header in ['"abc"', 'W/"abc"', '"other", W/"abc"', '  "other" , "abc"  ', "*"]:
			with self.subTest(header=header):
				self.assertTrue(matches_etag(header, '"abc"'))

	def test_empty_different_or_partial_validators_do_not_match(self):
		for header in [None, "", " ", '"other"', 'W/"other"', '"abc-extra"', "abc", '"abc"extra']:
			with self.subTest(header=header):
				self.assertFalse(matches_etag(header, '"abc"'))


if __name__ == "__main__":
	unittest.main()
