"""Read the web bundle's Vite manifest for the /panel page (blocker E-3)."""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from platform_core.shell.panel_assets import (
	ENV_KEY,
	MAX_MANIFEST_BYTES,
	SITE_CONFIG_KEY,
	PanelAssetsError,
	load_panel_assets,
	manifest_path,
	panel_assets_from_manifest,
)

# The shape Vite writes to dist/.vite/manifest.json with build.manifest and base "/panel/".
MANIFEST = {
	"index.html": {
		"file": "assets/index-B1x_9a.js",
		"name": "index",
		"src": "index.html",
		"isEntry": True,
		"imports": ["_vendor-C2.js", "_antd-D3.js"],
		"dynamicImports": ["src/modules/account/Page.tsx"],
		"css": ["assets/index-E4.css"],
	},
	"_vendor-C2.js": {"file": "assets/vendor-C2.js", "imports": ["_antd-D3.js"]},
	"_antd-D3.js": {"file": "assets/antd-D3.js", "css": ["assets/antd-F5.css"]},
	"src/modules/account/Page.tsx": {
		"file": "assets/Page-G6.js",
		"isDynamicEntry": True,
		"css": ["assets/Page-H7.css"],
	},
	"src/fonts/outfit.woff2": {"file": "assets/outfit-I8.woff2"},
}


class TestPanelAssetsFromManifest(TestCase):
	def test_entry_script_styles_and_static_preloads(self):
		assets = panel_assets_from_manifest(MANIFEST)
		self.assertEqual(assets.script, "/panel/assets/index-B1x_9a.js")
		self.assertEqual(assets.styles, ("/panel/assets/index-E4.css", "/panel/assets/antd-F5.css"))
		self.assertEqual(assets.preloads, ("/panel/assets/vendor-C2.js", "/panel/assets/antd-D3.js"))

	def test_dynamic_imports_are_not_preloaded(self):
		assets = panel_assets_from_manifest(MANIFEST)
		self.assertNotIn("/panel/assets/Page-G6.js", assets.preloads)
		self.assertNotIn("/panel/assets/Page-H7.css", assets.styles)

	def test_entry_without_imports(self):
		assets = panel_assets_from_manifest({"index.html": {"file": "assets/index-1.js", "isEntry": True}})
		self.assertEqual((assets.styles, assets.preloads), ((), ()))

	def test_import_cycle_ends(self):
		manifest = {
			"index.html": {"file": "assets/index-1.js", "isEntry": True, "imports": ["_a.js"]},
			"_a.js": {"file": "assets/a.js", "imports": ["_b.js"]},
			"_b.js": {"file": "assets/b.js", "imports": ["_a.js", "index.html"]},
		}
		self.assertEqual(
			panel_assets_from_manifest(manifest).preloads, ("/panel/assets/a.js", "/panel/assets/b.js")
		)

	def test_rejected_manifests(self):
		cases = {
			"no entry": {"main.js": {"file": "assets/main.js", "isEntry": True}},
			"entry not marked": {"index.html": {"file": "assets/index.js"}},
			"not an object": [],
			"entry not an object": {"index.html": "assets/index.js"},
			"script is css": {"index.html": {"file": "assets/index.css", "isEntry": True}},
			"parent folder": {"index.html": {"file": "assets/../index.js", "isEntry": True}},
			"outside assets": {"index.html": {"file": "index.js", "isEntry": True}},
			"absolute": {"index.html": {"file": "/assets/index.js", "isEntry": True}},
			"other origin": {"index.html": {"file": "https://cdn.example.test/a.js", "isEntry": True}},
			"markup": {"index.html": {"file": 'assets/a.js"><script>', "isEntry": True}},
			"style is script": {
				"index.html": {"file": "assets/a.js", "isEntry": True, "css": ["assets/b.js"]}
			},
			"css not a list": {"index.html": {"file": "assets/a.js", "isEntry": True, "css": "assets/b.css"}},
			"missing import": {"index.html": {"file": "assets/a.js", "isEntry": True, "imports": ["_x.js"]}},
			"subfolder": {"index.html": {"file": "assets/sub/a.js", "isEntry": True}},
		}
		for name, manifest in cases.items():
			with self.subTest(name), self.assertRaises(PanelAssetsError):
				panel_assets_from_manifest(manifest)


class TestLoadPanelAssets(TestCase):
	def write(self, folder, content):
		path = Path(folder) / ".vite" / "manifest.json"
		path.parent.mkdir()
		path.write_bytes(content)
		return str(path)

	def test_reads_a_manifest_file(self):
		with tempfile.TemporaryDirectory() as folder:
			path = self.write(folder, json.dumps(MANIFEST).encode())
			self.assertEqual(load_panel_assets(path).script, "/panel/assets/index-B1x_9a.js")

	def test_missing_unreadable_and_oversized_files(self):
		with tempfile.TemporaryDirectory() as folder:
			cases = {
				"no path": None,
				"empty path": "",
				"relative path": ".vite/manifest.json",
				"missing file": str(Path(folder) / "missing.json"),
				"folder": folder,
				"bad json": self.write(folder, b"{"),
			}
			oversized = Path(folder) / "big.json"
			oversized.write_bytes(b" " * (MAX_MANIFEST_BYTES + 1))
			cases["oversized"] = str(oversized)
			for name, path in cases.items():
				with self.subTest(name), self.assertRaises(PanelAssetsError):
					load_panel_assets(path)


class TestManifestPath(TestCase):
	def test_site_config_wins_over_the_environment(self):
		with (
			patch("platform_core.shell.panel_assets.frappe") as frappe,
			patch.dict(os.environ, {ENV_KEY: "/srv/panel/current/.vite/manifest.json"}),
		):
			frappe.conf = {SITE_CONFIG_KEY: "/srv/other/.vite/manifest.json"}
			self.assertEqual(manifest_path(), "/srv/other/.vite/manifest.json")
			frappe.conf = {}
			self.assertEqual(manifest_path(), "/srv/panel/current/.vite/manifest.json")

	def test_no_setting(self):
		with patch("platform_core.shell.panel_assets.frappe") as frappe, patch.dict(os.environ, clear=True):
			frappe.conf = {}
			self.assertIsNone(manifest_path())
