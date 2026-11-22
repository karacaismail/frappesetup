"""Hangi alanın gizli, hangi DocType'ın kapalı olduğunu tek yerde tanımlar."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from frappe.core.doctype.docfield.docfield import DocField

SECRET_FIELDTYPES = frozenset({"Password"})
SECRET_NAME = re.compile(
	r"(^|_)(password|passwd|pwd|secret|token|api_key|apikey|private_key|credential|credentials|otp|signature)(_|$)"
)

# Kimlik bilgisi taşıyan kayıtlar. Okunmaz ve yazılmaz.
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
	}
)

# Kod, şablon, dış istek ya da zamanlama taşıyan kayıtlar. Yazmak kod çalıştırma yolu açar.
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

# Yapı, rol ve izin kayıtları. Yalnız yönetim araçları değiştirir.
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
	}
)

# Katmanın kendi kayıtları. Yapay zekâ yoluyla değişmez.
LAYER_DOCTYPES = frozenset({"AI Action Log", "AI Action Proposal"})

READ_BLOCKED = CREDENTIAL_DOCTYPES
WRITE_BLOCKED = CREDENTIAL_DOCTYPES | CODE_DOCTYPES | LAYER_DOCTYPES

FORBIDDEN_ARGUMENT_NAMES = frozenset({"confirm", "confirmed", "approve", "approved", "force"})


def is_secret_fieldname(fieldname: str) -> bool:
	return bool(SECRET_NAME.search(fieldname or ""))


def is_secret_field(field: "DocField") -> bool:
	return field.fieldtype in SECRET_FIELDTYPES or is_secret_fieldname(field.fieldname)
