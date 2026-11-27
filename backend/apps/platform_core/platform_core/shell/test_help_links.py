"""AJA-1038 acceptance: topic links, safe destinations and component fallback."""

import unittest

from platform_core.shell import help_content
from platform_core.shell.test_help_content import resolve, topic

LINKS = {
	"tour_url": "/tours/invoice",
	"doc_url": "https://docs.example.test/invoice",
	"support_url": "help/contact",
}


class HelpLinksTest(unittest.TestCase):
	def test_field_links_belong_to_the_selected_topic(self):
		answer = resolve([topic("app", "App", **LINKS), topic("tenant", "Tenant", doc_url="/tenant-docs")])
		self.assertEqual(answer["doc_url"], "/tenant-docs")
		self.assertIsNone(answer["tour_url"])
		self.assertIsNone(answer["support_url"])

	def test_field_without_topic_returns_null_links(self):
		for answer in (resolve([]), resolve([], description=""), resolve([], readable=False)):
			for key in LINKS:
				self.assertIsNone(answer[key])

	def test_valid_destinations_and_blank_values(self):
		for value in (
			*LINKS.values(),
			"./guide",
			"../guide",
			"/guide?q=1#step",
			"https://example.test",
			"",
			None,
			"  ",
		):
			with self.subTest(value=value):
				self.assertTrue(help_content.is_safe_help_url(value))

	def test_unsafe_or_ambiguous_destinations_are_rejected(self):
		for value in (
			"javascript:alert(1)",
			"data:text/html,test",
			"http://example.test",
			"//example.test",
			"///example.test",
			"\\\\example.test",
			"/\\example.test",
			"https:example.test",
			"https:///example.test",
			"https://user:pass@example.test",
			"java\nscript:alert(1)",
			"/\t/example.test",
			"https://example.test:bad",
			"https://[invalid",
			42,
		):
			with self.subTest(value=value):
				self.assertFalse(help_content.is_safe_help_url(value))

	def test_unsafe_legacy_links_are_not_returned(self):
		answer = resolve(
			[topic("tenant", "Tenant", tour_url="javascript:alert(1)", doc_url="", support_url="  ")]
		)
		for key in LINKS:
			self.assertIsNone(answer[key])


def component(name, layer="Tenant", **values):
	return topic(name, layer, target_type="Component", component_id="invoice-editor", app="erpnext", **values)


class ComponentHelpTest(unittest.TestCase):
	def resolve(self, topics, **values):
		args = {
			"component_id": "invoice-editor",
			"topics": topics,
			"language": "tr-TR",
			"versions": {"erpnext": "16.1.0"},
			"roles": ["Accounts User"],
		}
		args.update(values)
		return help_content.resolve_component_help(**args)

	def test_tenant_then_application_then_empty(self):
		self.assertEqual(
			self.resolve([component("app", "App"), component("tenant", **LINKS)])["topic"], "tenant"
		)
		self.assertEqual(self.resolve([component("app", "App")])["source"], "app")
		self.assertIsNone(self.resolve([]))

	def test_selected_component_returns_its_links(self):
		answer = self.resolve([component("tenant", **LINKS)])
		for key, value in LINKS.items():
			self.assertEqual(answer[key], value)

	def test_other_targets_unpublished_and_role_restricted_topics_are_skipped(self):
		candidates = [
			topic("field", "Tenant"),
			component("draft", status="Draft"),
			component("private", roles=["Accounts Manager"]),
		]
		other = component("other")
		other["component_id"] = "other-editor"
		self.assertIsNone(self.resolve([*candidates, other]))

	def test_language_version_and_recency_use_field_help_rules(self):
		generic = component("generic")
		regional = component("regional", language="tr-TR", version="16.1.0")
		newer = component("newer", language="tr-TR", version="16.1.0", modified="2026-11-26 10:00:00")
		self.assertEqual(self.resolve([generic, regional, newer])["topic"], "newer")
		self.assertEqual(self.resolve([generic, component("base", language="tr")])["topic"], "base")
		self.assertIsNone(
			self.resolve([component("wrong-language", language="en"), component("old", version="15.0.0")])
		)
		self.assertIsNone(self.resolve([regional], versions={}))


if __name__ == "__main__":
	unittest.main()
