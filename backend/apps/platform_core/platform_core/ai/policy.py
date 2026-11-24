"""Define in one place which field is secret and which DocType is closed."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from frappe.core.doctype.docfield.docfield import DocField

SECRET_FIELDTYPES = frozenset({"Password"})
SECRET_NAME = re.compile(
	r"(^|_)(password|passwd|pwd|passphrase|secret|secrets|secretkey|clientsecret|token|accesstoken|key|keys"
	r"|apikey|credential|credentials|authorization|otp|signature|salt|cookie|sid|pem)(_|$)"
)

# Records that carry credentials. Not read and not written.
CREDENTIAL_DOCTYPES = frozenset(
	{
		"OAuth Bearer Token",
		"OAuth Authorization Code",
		"OAuth Client",
		"Token Cache",
		"Connected App",
		"Social Login Key",
		"User Social Login",
		"Integration Request",
		"Document Share Key",
		"Email Account",
		"Email Queue",
		"Email Queue Recipient",
		"LDAP Settings",
		"SMS Settings",
		"SMS Parameter",
		"Webhook",
		"Webhook Header",
		"Webhook Request Log",
		"Error Log",
		# Those that carry old values of deleted or changed records, and job inputs.
		"Deleted Document",
		"Version",
		"RQ Job",
		"Console Log",
		"Recorder",
		"Scheduled Job Log",
	}
)

# Records that carry code, templates, outbound requests or schedules. Writing them opens a
# way to run code.
CODE_DOCTYPES = frozenset(
	{
		"Server Script",
		"Client Script",
		"Report",
		"Print Format",
		"Notification",
		"Webhook",
		"Workflow",
		"Web Page",
		"Web Template",
		"Web Form",
		"Custom HTML Block",
		"Page",
		"Scheduled Job Type",
		"Auto Repeat",
		"Auto Email Report",
		"Data Import",
		"Package Import",
	}
)

# Structure, role and permission records. Only admin tools change them.
ADMIN_DOCTYPES = frozenset(
	{
		"DocType",
		"DocField",
		"DocPerm",
		"Custom Field",
		"Custom DocPerm",
		"Property Setter",
		"Customize Form",
		"Role",
		"Role Profile",
		"Has Role",
		"User",
		"User Type",
		"User Permission",
		"DocShare",
		"Module Def",
		"Module Profile",
		"System Settings",
		"OAuth Settings",
		"OAuth Provider Settings",
		# Decides which records a user may see. It changes only through admin tools.
		"PLT Access Rule",
	}
)

# Records that bind a person to an account. AI tools never write them, admin tools included.
IDENTITY_DOCTYPES = frozenset({"PLT Identity Link"})

# The layer's own records. They do not change through AI.
LAYER_DOCTYPES = frozenset({"PLT AI Action Log", "PLT AI Action Proposal", "PLT MCP Call Budget"})

# Frappe framework DocTypes that are open to the general write tools.
# The other framework DocTypes are settings, code or system records and are closed.
FRAMEWORK_OPEN = frozenset({"ToDo", "Note", "Event", "Contact", "Address"})

# The model reads proposals only with the `get_proposal` tool. So it cannot reach the
# approval digest.
READ_BLOCKED = CREDENTIAL_DOCTYPES | LAYER_DOCTYPES
WRITE_BLOCKED = CREDENTIAL_DOCTYPES | CODE_DOCTYPES | LAYER_DOCTYPES | IDENTITY_DOCTYPES
# No admin tool may touch these: no custom field, no field property, no role permission.
ADMIN_TOOL_BLOCKED = CREDENTIAL_DOCTYPES | LAYER_DOCTYPES | IDENTITY_DOCTYPES

# Roles that are not granted and not removed through AI.
PROTECTED_ROLES = frozenset(
	{
		"Administrator",
		"System Manager",
		"Guest",
		"All",
		"Desk User",
		"Script Manager",
		"Report Manager",
		"Website Manager",
		"Workspace Manager",
	}
)
# Roles whose permissions do not change through AI. These roles cover everyone or full access.
PROTECTED_PERMISSION_ROLES = frozenset({"Administrator", "Guest", "All", "Desk User"})

FORBIDDEN_ARGUMENT_NAMES = frozenset({"confirm", "confirmed", "approve", "approved", "force"})


def is_framework_doctype(meta) -> bool:
	"""Return true if the DocType belongs to the Frappe framework and is not on the open list.

	A new system DocType stays closed even if it is not added to a list. The DocTypes of apps
	and of users do not fall under this rule. If the app of the module cannot be found, the
	DocType counts as closed.
	"""
	import frappe

	if meta.custom or meta.name in FRAMEWORK_OPEN:
		return False
	app = (frappe.local.module_app or {}).get(frappe.scrub(meta.module or ""))
	return app is None or app == "frappe"


def is_closed_by_app(doctype: str) -> bool:
	"""Return true if an app closed this DocType with the `ai_write_closed_doctypes` hook.

	For example, the owner of a DocType that holds identity links or access rules closes it
	with this hook.
	"""
	import frappe

	return doctype in (frappe.get_hooks("ai_write_closed_doctypes") or [])


def is_secret_fieldname(fieldname: str) -> bool:
	return bool(SECRET_NAME.search(fieldname or ""))


def is_secret_field(field: "DocField") -> bool:
	return field.fieldtype in SECRET_FIELDTYPES or is_secret_fieldname(field.fieldname)


# Clients the log names. The key is the name a client reports, in lower case. The value is the
# fixed text that is stored. Every other client is stored as `OTHER_CLIENT`.
KNOWN_CLIENTS = {
	"mcp-inspector": "mcp-inspector",
	"mcp": "mcp-sdk",
}
OTHER_CLIENT = "other"
