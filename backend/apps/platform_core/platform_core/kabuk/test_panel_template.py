"""Check missing Jinja context and isolate panel styles from other pages."""

import re
from html.parser import HTMLParser
from pathlib import Path
from unittest import TestCase

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

APP = Path(__file__).resolve().parents[1]
PANEL_CLASS = "platform-shell-panel"


class PanelAttributes(HTMLParser):
	def __init__(self, html: str):
		super().__init__()
		self.element = {}
		self.csrf = None
		self.feed(html)

	def handle_starttag(self, tag, attrs):
		attributes = dict(attrs)
		if tag == "html":
			self.element = attributes
		if tag == "meta" and attributes.get("name") == "csrf-token":
			self.csrf = attributes.get("content")


class TestPanelTemplate(TestCase):
	def render_panel(self, **context):
		environment = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)
		environment.globals.update(
			_=lambda value, **_options: value,
			include_style=lambda _name: "",
			include_script=lambda _name: "",
		)
		source = (APP / "www" / "panel.html").read_text(encoding="utf-8")
		return PanelAttributes(environment.from_string(source).render(**context))

	def test_missing_context_has_language_and_no_csrf_token(self):
		panel = self.render_panel()
		self.assertEqual(panel.element["lang"], "en")
		self.assertEqual(panel.csrf, "")

	def test_given_context_is_preserved(self):
		panel = self.render_panel(panel_language="tr", panel_csrf_token='test"&token')
		self.assertEqual(panel.element["lang"], "tr")
		self.assertEqual(panel.csrf, 'test"&token')

	def test_rendered_page_matches_style_scope(self):
		panel = self.render_panel(panel_language="tr", panel_csrf_token="test-token")
		self.assertIn(PANEL_CLASS, panel.element.get("class", "").split())
		stylesheet = (APP / "public" / "panel" / "panel.bundle.css").read_text(encoding="utf-8")
		stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
		for rule in re.findall(r"([^{}]+)\{", stylesheet):
			if rule.lstrip().startswith("@"):
				continue
			selectors = re.split(r",\s*(?=[^()]*(?:\(|$))", rule.strip())
			for selector in selectors:
				with self.subTest(selector=selector):
					self.assertTrue(selector.startswith(f"html:where(.{PANEL_CLASS})"))
