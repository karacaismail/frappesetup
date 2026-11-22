"""Etkin kuralların okunması, önbelleği ve kural dilinin sabitleri.

Karar notu: `docs/kararlar/0006-erisim-kurali.md`, 3. ve 12. bölüm.
"""

import json

import frappe
from frappe import _

RULE_DOCTYPE = "Access Rule"
CACHE_KEY = "platform_core:erisim:rules"

SCOPES = ("own", "team", "department", "company", "all")
OPERATIONS = ("read", "write", "create", "delete", "submit", "cancel")
OPERATORS = ("=", "!=", "in", "not in")
VARIABLES = ("$user", "$user.employee", "$user.department", "$user.company")

# Frappe'nin işlem adı kuralın hangi bayrağını arar? Tanınmayan ad en dar bayrağı arar.
PTYPE_TO_OPERATION = {
	"read": "read",
	"select": "read",
	"print": "read",
	"email": "read",
	"export": "read",
	"report": "read",
	"share": "read",
	"write": "write",
	"create": "create",
	"amend": "create",
	"delete": "delete",
	"submit": "submit",
	"cancel": "cancel",
}

# `match_field` alanının gösterdiği kayıt türü ve kapsamın kabul ettiği türler.
MATCH_KINDS = {"User": "user", "Employee": "employee", "Department": "department", "Company": "company"}
SCOPE_KINDS = {
	"own": ("user", "employee"),
	"team": ("user", "employee"),
	"department": ("department", "employee", "user"),
	"company": ("company", "employee", "user"),
}

# Bu türlere kural yazılırsa yönetici kendi yönetim yolunu kapatabilir.
PROTECTED_DOCTYPES = frozenset(
	{
		RULE_DOCTYPE,
		"DocType",
		"DocPerm",
		"Custom DocPerm",
		"Role",
		"Has Role",
		"Role Profile",
		"User Permission",
		"Property Setter",
		"DocShare",
		"Module Def",
	}
)

RULE_FIELDS = (
	"name",
	"title",
	"document_type",
	"role",
	"scope",
	"match_field",
	"filters",
	"priority",
	*(f"allow_{operation}" for operation in OPERATIONS),
)


def operation_of(ptype: str | None) -> str:
	return PTYPE_TO_OPERATION.get(ptype or "read", "write")


def active_rules() -> dict[str, list[dict]]:
	"""Etkin kuralları kayıt türüne göre döner. Sonuç önbellekte durur ve kullanıcıya özel değildir."""
	if frappe.flags.in_install or frappe.flags.in_migrate:
		# Kurulumda tablo henüz olmayabilir. Kurulum yönetici kimliğiyle çalışır.
		return {}
	return frappe.cache.get_value(CACHE_KEY, generator=_load)


def _load() -> dict[str, list[dict]]:
	grouped: dict[str, list[dict]] = {}
	# Kural tablosu küçüktür ve sistem verisidir. İzin süzmesi burada döngü kurardı (G-3 istisnası).
	rows = frappe.get_all(
		RULE_DOCTYPE,
		filters={"is_active": 1},
		fields=list(RULE_FIELDS),
		order_by="priority asc, name asc",
		limit=0,
	)
	for row in rows:
		rule = dict(row)
		rule["filters"] = parse_filters(rule["filters"])
		grouped.setdefault(rule["document_type"], []).append(rule)
	return grouped


def clear_cache(*_args, **_kwargs) -> None:
	"""Kural, rol ya da kayıt türü değişince çağrılır. Kayıt kesinleşince bir kez daha siler."""
	frappe.cache.delete_value(CACHE_KEY)
	frappe.db.after_commit.add(_delete_cached_rules)


def _delete_cached_rules() -> None:
	frappe.cache.delete_value(CACHE_KEY)


def rules_for(doctype: str) -> list[dict]:
	return active_rules().get(doctype) or []


def is_governed(doctype: str) -> bool:
	return bool(rules_for(doctype))


def applies(rule: dict, roles: set[str], operation: str) -> bool:
	return rule["role"] in roles and bool(rule[f"allow_{operation}"])


def applicable(doctype: str, user: str, operation: str) -> list[dict]:
	"""Kullanıcının rollerine uyan ve işlemi kapsayan etkin kurallar."""
	roles = set(frappe.get_roles(user))
	return [rule for rule in rules_for(doctype) if applies(rule, roles, operation)]


def match_kind(doctype: str, fieldname: str | None) -> str | None:
	"""`match_field` neyi gösterir: kullanıcı, çalışan, bölüm ya da şirket. Bilinmiyorsa `None`."""
	if not fieldname:
		return None
	if fieldname in ("owner", "modified_by"):
		return "user"
	if fieldname == "name":
		return MATCH_KINDS.get(doctype)
	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df or df.fieldtype != "Link":
		return None
	return MATCH_KINDS.get(df.options)


def parse_filters(raw: str | None) -> list[list]:
	"""Kayıtlı süzgeç metnini listeye çevirir. Metin kayıt sırasında doğrulanmıştır."""
	return json.loads(raw) if raw else []


def validate_filters(doctype: str, raw: str | None) -> str:
	"""Süzgeci kural diline göre doğrular ve düzgün JSON metnini döner (karar notu 3. bölüm)."""
	if not raw or not raw.strip():
		return ""
	try:
		rows = json.loads(raw)
	except ValueError:
		frappe.throw(_("Filters must be valid JSON."))
	if not isinstance(rows, list):
		frappe.throw(_("Filters must be a list of [field, operator, value] rows."))
	columns = set(frappe.get_meta(doctype).get_valid_columns())
	for row in rows:
		if not isinstance(row, list) or len(row) != 3:
			frappe.throw(_("Each filter must be a [field, operator, value] row."))
		fieldname, operator, value = row
		if fieldname not in columns:
			frappe.throw(
				_("Filter field {0} is not a column of {1}.").format(frappe.bold(str(fieldname)), doctype)
			)
		if operator not in OPERATORS:
			frappe.throw(_("Filter operator must be one of: {0}").format(", ".join(OPERATORS)))
		_validate_filter_value(operator, value)
	return json.dumps(rows, ensure_ascii=False)


def _validate_filter_value(operator: str, value) -> None:
	if operator in ("in", "not in"):
		if not isinstance(value, list) or not value:
			frappe.throw(_("Operator {0} needs a non-empty list of values.").format(operator))
		values = value
	else:
		values = [value]
	for item in values:
		if isinstance(item, bool) or not isinstance(item, str | int | float):
			frappe.throw(_("Filter values must be text or numbers."))
		if isinstance(item, str) and item.startswith("$") and item not in VARIABLES:
			frappe.throw(_("Unknown variable {0}. Allowed: {1}").format(item, ", ".join(VARIABLES)))
		if isinstance(item, str) and item.startswith("$") and operator in ("in", "not in"):
			frappe.throw(_("Variables can only be used with = and !=."))
