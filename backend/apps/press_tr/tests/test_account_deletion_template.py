"""Render the Press deletion template with normal and missing page context."""

import unittest
from pathlib import Path

from jinja2 import DictLoader, Environment, StrictUndefined

TEMPLATE = Path(__file__).resolve().parents[1] / "press_tr" / "www" / "account-deletion.html"


class AccountDeletionTemplateTest(unittest.TestCase):
	def render(self, translate, **context):
		environment = Environment(
			loader=DictLoader(
				{
					"account-deletion.html": TEMPLATE.read_text(encoding="utf-8"),
					"templates/web.html": "{% block page_content %}{% endblock %}",
				}
			),
			autoescape=False,
			undefined=StrictUndefined,
		)
		return environment.get_template("account-deletion.html").render(_=translate, **context)

	def test_localized_html_and_form_values_are_escaped(self):
		def translate(_text, *, context):
			self.assertEqual(context, "press_tr")
			return '<em data-test="translation">Example</em>'

		output = self.render(translate, reauthenticated=True, deletion_csrf_token='token"><input>')
		self.assertNotIn('<em data-test="translation">', output)
		self.assertIn("&lt;em", output)
		self.assertIn("token&#34;&gt;&lt;input&gt;", output)

	def test_absent_or_empty_csrf_token_only_offers_a_reload(self):
		for context in ({}, {"deletion_csrf_token": "", "reauthenticated": True}):
			with self.subTest(context=context):
				output = self.render(lambda text, **_options: text, **context)
				self.assertNotIn("<form", output)
				self.assertIn("Reload this page to try again.", output)

	def test_refresh_renders_the_known_deletion_state(self):
		def translate(text, **_options):
			return text

		pending = self.render(translate, deletion_csrf_token="fixture", deletion_status="pending")
		self.assertIn('id="account-deletion-status">Account deletion is in progress.', pending)
		self.assertIn("Last status known to Press.", pending)
		submitted = self.render(translate, deletion_csrf_token="fixture", deletion_status="submitted")
		self.assertIn('role="status">Your deletion request was submitted.', submitted)
		self.assertNotIn("<form", submitted)
