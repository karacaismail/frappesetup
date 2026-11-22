"""Static check that report and search code reads only through permission-aware calls.

The engine cannot follow what arbitrary code reads. It therefore accepts only code it can
read at a glance: `frappe.get_list` on a document type written as a literal, and a short list
of harmless `frappe` names. Anything else is reported, and the caller refuses to run the code.

The check is deliberately narrow. It refuses code that may be perfectly safe, for example a
report that imports a helper from its own app. Refusing is the safe default (decision C and D
of the third review).
"""

import ast

# `frappe.<name>` that code may use. Everything else on `frappe` is reported.
ALLOWED_FRAPPE_NAMES = frozenset(
	{
		"get_list",
		"has_permission",
		"get_meta",
		"get_roles",
		"session",
		"throw",
		"msgprint",
		"_",
		"_dict",
		"utils",
		"bold",
		"scrub",
		"unscrub",
		"parse_json",
		"as_json",
		"whitelist",
		"validate_and_sanitize_search_inputs",
		"PermissionError",
		"ValidationError",
		"DoesNotExistError",
	}
)
ALLOWED_FROM_FRAPPE = frozenset({"_", "_dict"})
FORBIDDEN_BUILTINS = frozenset(
	{
		"eval",
		"exec",
		"compile",
		"getattr",
		"setattr",
		"delattr",
		"globals",
		"locals",
		"vars",
		"open",
		"__import__",
		"breakpoint",
		"input",
	}
)
# A search function receives the searched document type in this argument.
DOCTYPE_ARGUMENT = "doctype"


def _dotted(node: ast.AST) -> str | None:
	parts = []
	while isinstance(node, ast.Attribute):
		parts.append(node.attr)
		node = node.value
	if isinstance(node, ast.Name):
		parts.append(node.id)
		return ".".join(reversed(parts))
	return None


def problems(source: str | None, doctypes: set[str] | None) -> list[str]:
	"""Return why the code cannot be trusted to read with permissions. Empty when it can.

	`doctypes` are the document types the code may read. With None the code may only read the
	type it is given in its `doctype` argument, which is how a search function works.
	"""
	if not source or not source.strip():
		return ["there is no code to check"]
	try:
		tree = ast.parse(source)
	except SyntaxError:
		return ["the code does not parse"]

	found: list[str] = []
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			found.extend(f"imports {alias.name}" for alias in node.names if alias.name != "frappe")
		elif isinstance(node, ast.ImportFrom):
			module = node.module or ""
			if module == "frappe":
				found.extend(
					f"imports frappe.{alias.name}"
					for alias in node.names
					if alias.name not in ALLOWED_FROM_FRAPPE
				)
			elif module != "frappe.utils":
				found.append(f"imports {module or 'a relative module'}")
		elif isinstance(node, ast.Attribute):
			dotted = _dotted(node)
			if dotted and dotted.startswith("frappe."):
				name = dotted.split(".")[1]
				if name not in ALLOWED_FRAPPE_NAMES:
					found.append(f"uses frappe.{name}")
		elif isinstance(node, ast.Name) and node.id in FORBIDDEN_BUILTINS:
			found.append(f"uses {node.id}")
		elif isinstance(node, ast.Call):
			found.extend(_call_problems(node, doctypes))
	return sorted(set(found))


def _call_problems(node: ast.Call, doctypes: set[str] | None) -> list[str]:
	found = []
	if any(keyword.arg is None for keyword in node.keywords) or any(
		isinstance(argument, ast.Starred) for argument in node.args
	):
		found.append("passes arguments that cannot be read from the code")
	if any(keyword.arg in ("ignore_permissions", "ignore_user_permissions") for keyword in node.keywords):
		found.append("asks to ignore permissions")
	if _dotted(node.func) != "frappe.get_list":
		return found

	target = node.args[0] if node.args else None
	for keyword in node.keywords:
		if keyword.arg == "doctype":
			target = keyword.value
	if isinstance(target, ast.Constant) and isinstance(target.value, str):
		if doctypes is None or target.value not in doctypes:
			found.append(f"reads {target.value}, which is not declared")
	elif isinstance(target, ast.Name) and target.id == DOCTYPE_ARGUMENT and doctypes is None:
		pass
	else:
		found.append("reads a document type that is not written as a literal")
	return found
