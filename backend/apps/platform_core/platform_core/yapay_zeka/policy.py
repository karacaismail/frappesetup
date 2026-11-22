"""Hangi alanın gizli, hangi DocType'ın kapalı olduğunu tek yerde tanımlar."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from frappe.core.doctype.docfield.docfield import DocField

SECRET_FIELDTYPES = frozenset({"Password"})
SECRET_NAME = re.compile(
	r"(^|_)(password|passwd|pwd|passphrase|secret|secretkey|token|key|keys|apikey|credential|credentials"
	r"|authorization|otp|signature|salt)(_|$)"
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

# Frappe çatısının kendi DocType'larından genel yazma araçlarına açık olanlar.
# Çatının öteki DocType'ları ayar, kod ya da sistem kaydıdır ve kapalıdır.
FRAMEWORK_OPEN = frozenset({"ToDo", "Note", "Event", "Contact", "Address"})

# Model önerileri yalnız `get_proposal` aracıyla okur. Böylece onay özetine ulaşamaz.
READ_BLOCKED = CREDENTIAL_DOCTYPES | LAYER_DOCTYPES
WRITE_BLOCKED = CREDENTIAL_DOCTYPES | CODE_DOCTYPES | LAYER_DOCTYPES

# Yapay zekâ yoluyla verilmeyen ve alınmayan roller.
PROTECTED_ROLES = frozenset({"Administrator", "System Manager", "Guest", "All", "Desk User"})
# İzinleri yapay zekâ yoluyla değişmeyen roller. Bu roller herkesi ya da tam yetkiyi kapsar.
PROTECTED_PERMISSION_ROLES = frozenset({"Administrator", "Guest", "All"})

FORBIDDEN_ARGUMENT_NAMES = frozenset({"confirm", "confirmed", "approve", "approved", "force"})


def is_framework_doctype(meta) -> bool:
	"""DocType Frappe çatısına aitse ve açık listede değilse doğru döner.

	Yeni bir sistem DocType'ı listeye eklenmese de kapalı kalır. Uygulamaların ve
	kullanıcıların kendi DocType'ları bu kurala girmez.
	"""
	import frappe

	if meta.custom or meta.name in FRAMEWORK_OPEN:
		return False
	return (frappe.local.module_app or {}).get(frappe.scrub(meta.module or "")) == "frappe"


def is_secret_fieldname(fieldname: str) -> bool:
	return bool(SECRET_NAME.search(fieldname or ""))


def is_secret_field(field: "DocField") -> bool:
	return field.fieldtype in SECRET_FIELDTYPES or is_secret_fieldname(field.fieldname)
