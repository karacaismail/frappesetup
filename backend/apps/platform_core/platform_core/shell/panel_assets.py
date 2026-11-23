"""Read the web bundle's Vite manifest and list the files the /panel page loads.

The web bundle (atonota-web, built with base "/panel/" and build.manifest) is unpacked on the
server. The edge proxy serves its assets/ folder at /panel/assets/. Frappe serves only the HTML.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import frappe

SITE_CONFIG_KEY = "panel_manifest_path"
ENV_KEY = "ATONOTA_PANEL_MANIFEST"
ENTRY = "index.html"
URL_PREFIX = "/panel/"
MAX_MANIFEST_BYTES = 1_048_576
# Vite writes hashed names straight under assets/. Anything else could leave /panel/assets/.
_SCRIPT = re.compile(r"assets/[A-Za-z0-9][A-Za-z0-9._-]*\.m?js")
_STYLE = re.compile(r"assets/[A-Za-z0-9][A-Za-z0-9._-]*\.css")

logger = logging.getLogger(__name__)


class PanelAssetsError(Exception):
	"""The manifest is missing, unreadable or names a file outside /panel/assets/."""


@dataclass(frozen=True)
class PanelAssets:
	script: str
	styles: tuple[str, ...]
	preloads: tuple[str, ...]


def manifest_path() -> str | None:
	"""The site config key wins, so one site can test another bundle."""
	return frappe.conf.get(SITE_CONFIG_KEY) or os.environ.get(ENV_KEY) or None


def _url(file: object, pattern: re.Pattern) -> str:
	if not isinstance(file, str) or not pattern.fullmatch(file) or ".." in file:
		raise PanelAssetsError(f"manifest names an unexpected file: {file!r}")
	return URL_PREFIX + file


def _chunk(manifest: dict, key: str) -> dict:
	chunk = manifest.get(key)
	if not isinstance(chunk, dict):
		raise PanelAssetsError(f"manifest has no chunk {key!r}")
	return chunk


def _list(chunk: dict, field: str) -> list:
	value = chunk.get(field, [])
	if not isinstance(value, list):
		raise PanelAssetsError(f"manifest field {field!r} is not a list")
	return value


def panel_assets_from_manifest(manifest: object) -> PanelAssets:
	"""Follow Vite's rule: the entry, its CSS and the CSS and files of every static import."""
	if not isinstance(manifest, dict):
		raise PanelAssetsError("manifest is not an object")
	entry = _chunk(manifest, ENTRY)
	if entry.get("isEntry") is not True:
		raise PanelAssetsError("index.html is not an entry")
	script = _url(entry.get("file"), _SCRIPT)
	styles: list[str] = []
	preloads: list[str] = []
	seen = {ENTRY}

	def visit(chunk: dict) -> None:
		for file in _list(chunk, "css"):
			url = _url(file, _STYLE)
			if url not in styles:
				styles.append(url)
		for key in _list(chunk, "imports"):
			if key in seen:
				continue
			seen.add(key)
			imported = _chunk(manifest, key)
			url = _url(imported.get("file"), _SCRIPT)
			if url not in preloads:
				preloads.append(url)
			visit(imported)

	visit(entry)
	return PanelAssets(script=script, styles=tuple(styles), preloads=tuple(preloads))


def load_panel_assets(path: str | None) -> PanelAssets:
	if not path:
		raise PanelAssetsError(f"set {SITE_CONFIG_KEY} in site config or {ENV_KEY}")
	file = Path(path)
	if not file.is_absolute():
		raise PanelAssetsError(f"manifest path is not absolute: {path!r}")
	try:
		with file.open("rb") as stream:
			content = stream.read(MAX_MANIFEST_BYTES + 1)
	except OSError as error:
		raise PanelAssetsError(f"cannot read manifest {path!r}: {error.strerror}") from None
	if len(content) > MAX_MANIFEST_BYTES:
		raise PanelAssetsError(f"manifest {path!r} is larger than {MAX_MANIFEST_BYTES} bytes")
	try:
		manifest = json.loads(content)
	except ValueError:
		raise PanelAssetsError(f"manifest {path!r} is not valid JSON") from None
	return panel_assets_from_manifest(manifest)


def current_panel_assets() -> PanelAssets | None:
	"""Read the manifest on every request: a web release switches the "current" link at any time."""
	try:
		return load_panel_assets(manifest_path())
	except PanelAssetsError as error:
		logger.warning("The /panel page shows the placeholder: %s", error)
		return None
