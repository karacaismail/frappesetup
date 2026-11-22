"""Keep generated panel source maps out of the public asset tree."""

from pathlib import Path

import frappe


def remove_panel_source_maps() -> None:
	dist = Path(frappe.get_app_path("platform_core", "public", "dist"))
	for folder, pattern in (
		("css", "panel.bundle.*.css.map"),
		("css-rtl", "panel.bundle.*.css.map"),
		("js", "panel-focus.bundle.*.js.map"),
	):
		for path in (dist / folder).glob(pattern):
			path.unlink(missing_ok=True)
