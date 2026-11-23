"""Check missing Jinja context and isolate panel styles from other pages."""

import re
from html.parser import HTMLParser
from pathlib import Path
from unittest import TestCase

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from platform_core.shell.panel_assets import PanelAssets

APP = Path(__file__).resolve().parents[1]
PANEL_CLASS = "platform-shell-panel"
SAMPLE_CSRF = "sample-csrf"


class PanelAttributes(HTMLParser):
	def __init__(self, html: str):
		super().__init__()
		self.element = {}
		self.csrf = None
		self.nonce = None
		self.styles = []
		self.preloads = []
		self.scripts = []
		self.ids = []
		self.feed(html)

	def handle_starttag(self, tag, attrs):
		attributes = dict(attrs)
		if tag == "html":
			self.element = attributes
		if tag == "meta" and attributes.get("name") == "csrf-token":
			self.csrf = attributes.get("content")
		if tag == "meta" and attributes.get("property") == "csp-nonce":
			self.nonce = attributes.get("nonce")
		if tag == "link" and attributes.get("rel") == "stylesheet":
			self.styles.append(attributes["href"])
		if tag == "link" and attributes.get("rel") == "modulepreload":
			self.preloads.append(attributes["href"])
		if tag == "script":
			self.scripts.append((attributes.get("type"), attributes.get("src")))
		if "id" in attributes:
			self.ids.append(attributes["id"])


class TestPanelTemplate(TestCase):
	def render_panel(self, **context):
		self.included = []
		environment = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)
		environment.globals.update(
			_=lambda value, **_options: value,
			include_style=lambda name: self.included.append(("style", name)) or "",
			include_script=lambda name: self.included.append(("script", name)) or "",
		)
		source = (APP / "www" / "panel.html").read_text(encoding="utf-8")
		self.html = environment.from_string(source).render(**context)
		return PanelAttributes(self.html)

	def test_bundle_assets_replace_the_placeholder(self):
		assets = PanelAssets(
			script="/panel/assets/index-1.js",
			styles=("/panel/assets/index-2.css", "/panel/assets/antd-3.css"),
			preloads=("/panel/assets/vendor-4.js",),
		)
		panel = self.render_panel(panel_assets=assets, panel_csp_nonce="n0nce", panel_csrf_token=SAMPLE_CSRF)
		self.assertEqual(panel.styles, list(assets.styles))
		self.assertEqual(panel.preloads, list(assets.preloads))
		self.assertEqual(panel.scripts, [("module", "/panel/assets/index-1.js")])
		self.assertEqual(panel.nonce, "n0nce")
		self.assertEqual(panel.csrf, SAMPLE_CSRF)
		self.assertIn("root", panel.ids)
		self.assertNotIn("The panel is not available yet.", self.html)
		self.assertEqual(self.included, [])

	def test_placeholder_explains_missing_bundle(self):
		panel = self.render_panel(panel_csrf_token=SAMPLE_CSRF)
		self.assertIn("The panel is not available yet.", self.html)
		self.assertIn("The panel files are not installed on this site.", self.html)
		self.assertEqual(self.included, [("style", "panel.bundle.css"), ("script", "panel-focus.bundle.js")])
		self.assertEqual((panel.styles, panel.scripts), ([], []))
		self.assertEqual(panel.preloads, [])
		self.assertIsNone(panel.nonce)
		self.assertNotIn("root", panel.ids)

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
