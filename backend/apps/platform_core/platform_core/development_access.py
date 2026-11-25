"""Keep development endpoints off on tenant sites without the matching opt-in."""

import frappe
from frappe import _

_CONSOLE_MODULE = "frappe.desk.doctype.system_console.system_console"
_CONSOLE_PATHS = {"/app/system-console", "/desk/system-console"}


def _is_test_method(command: str) -> bool:
	modules = command.split(".")[:-1]
	return any(part == "tests" or part.startswith("test_") for part in modules) or (
		command.startswith("mobile_test_app.")
	)


def guard_development_endpoints() -> None:
	path = frappe.local.request.path.rstrip("/")
	commands = [frappe.form_dict.get("cmd")]
	for prefix in ("/api/method/", "/api/v1/method/", "/api/v2/method/"):
		if path.startswith(prefix):
			commands.append(path.removeprefix(prefix))
			break
	methods = [command for command in commands if isinstance(command, str)]

	console = path in _CONSOLE_PATHS or any(
		method.startswith(_CONSOLE_MODULE + ".") for method in methods
	)
	test_endpoint = any(_is_test_method(method) for method in methods)
	if (console and frappe.conf.get("developer_mode") not in (1, "1")) or (
		test_endpoint and frappe.conf.get("allow_tests") not in (1, "1")
	):
		frappe.throw(_("This development tool is disabled on this site."), frappe.PermissionError)
