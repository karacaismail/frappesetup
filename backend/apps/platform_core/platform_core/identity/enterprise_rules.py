"""Rules of the corporate sign-in provider exception (G-160).

A corporate provider must require the `email_verified` claim. Some providers never send it. Such a
provider needs an approved exception record. The exception replaces the claim with other proof:
the e-mail domain must be one of the organisation's DNS-verified domains (security opinion AJA-212).

This file is the single source of the rules. It uses only the Python standard library, because the
`atonota-login apply` command loads it by path and runs outside the application server.

Every rule break raises EnterpriseRuleError. Its message holds the rule name and never a value
from the record, so it cannot echo a secret.

The rules give no role and take no role. The enterprise-sso-required rule stays as it is.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from datetime import datetime
from urllib.parse import urlsplit

KINDS = ("grant", "revocation")
VERIFICATION_METHODS = ("dns-txt",)
APPROVAL_PRINCIPAL = "human_session"

RECORD_FIELDS = frozenset(
	{
		"name",
		"kind",
		"provider_alias",
		"issuer",
		"organization",
		"allowed_domains",
		"reason",
		"provider_document",
		"requested_by",
		"approved_by",
		"approval_principal",
		"approved_on",
		"expires_on",
		"supersedes",
	}
)
DOMAIN_FIELDS = frozenset({"domain", "verification_method", "verified_on", "verification_record"})

# Mail services where anyone can open an address. The list is not complete; it blocks the common
# ones. A domain that is not listed still needs DNS proof of the organisation.
PUBLIC_MAIL_DOMAINS = frozenset(
	{
		"gmail.com",
		"googlemail.com",
		"outlook.com",
		"hotmail.com",
		"live.com",
		"msn.com",
		"yahoo.com",
		"ymail.com",
		"icloud.com",
		"me.com",
		"mac.com",
		"aol.com",
		"proton.me",
		"protonmail.com",
		"gmx.com",
		"gmx.net",
		"mail.com",
		"yandex.com",
		"yandex.ru",
		"yandex.com.tr",
		"mail.ru",
		"zoho.com",
		"hotmail.com.tr",
		"outlook.com.tr",
	}
)

# Issuers that many organisations share. Microsoft's common, organizations and consumers endpoints
# and the consumer tenant number are examples. Google's issuer serves every Google account.
_MICROSOFT_HOSTS = (
	"login.microsoftonline.com",
	"login.microsoftonline.us",
	"login.partner.microsoftonline.cn",
)
_MICROSOFT_SHARED_TENANTS = frozenset(
	{"common", "organizations", "consumers", "9188040d-6c67-4c5b-b112-36a304b66dad"}
)
SHARED_ISSUER_HOSTS = frozenset({"accounts.google.com", "appleid.apple.com", "www.linkedin.com"})

# Social platforms never take an exception (AJA-212, case 2). The aliases are the records in
# backend/identity/atonota_login/platforms/; a test keeps the two lists equal. The provider types are
# Keycloak's social providers.
SOCIAL_PROVIDER_ALIASES = frozenset({"apple", "facebook", "google", "linkedin", "x"})
SOCIAL_PROVIDER_IDS = frozenset(
	{
		"apple",
		"bitbucket",
		"facebook",
		"github",
		"gitlab",
		"google",
		"instagram",
		"linkedin-openid-connect",
		"microsoft",
		"openshift-v4",
		"paypal",
		"stackoverflow",
		"twitter",
	}
)

_ALIAS = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_SECRET_KEY = re.compile(r"secret|password|passwd|private|token|credential|api[_-]?key", re.IGNORECASE)
_SECRET_VALUE = re.compile(
	r"-----BEGIN [A-Z ]*KEY-----|\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+"
)


class EnterpriseRuleError(ValueError):
	"""A rule of the exception is broken. `rule` names the rule."""

	def __init__(self, rule: str):
		super().__init__(f"Corporate provider exception rule broken: {rule}.")
		self.rule = rule


def _text(value: object) -> str:
	return value.strip() if isinstance(value, str) else ""


def _required(record: Mapping, key: str, rule: str = "field_missing") -> str:
	value = _text(record.get(key))
	if not value:
		raise EnterpriseRuleError(rule)
	return value


def parse_time(value: object, rule: str = "invalid_datetime") -> datetime:
	"""Read an ISO 8601 time with a time zone. A time without a zone is refused."""
	text = _text(value)
	if not text:
		raise EnterpriseRuleError(rule)
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	try:
		moment = datetime.fromisoformat(text)
	except ValueError:
		raise EnterpriseRuleError("invalid_datetime") from None
	if moment.tzinfo is None or moment.utcoffset() is None:
		raise EnterpriseRuleError("invalid_datetime")
	return moment


def _check_no_secret(value: object, depth: int = 0) -> None:
	if depth > 4:
		raise EnterpriseRuleError("invalid_record")
	if isinstance(value, Mapping):
		for key, item in value.items():
			if not isinstance(key, str) or _SECRET_KEY.search(key):
				raise EnterpriseRuleError("secret_in_record")
			_check_no_secret(item, depth + 1)
	elif isinstance(value, (list, tuple)):
		for item in value:
			_check_no_secret(item, depth + 1)
	elif isinstance(value, str) and _SECRET_VALUE.search(value):
		raise EnterpriseRuleError("secret_in_record")


def _https_url(value: str, rule: str) -> str:
	parts = urlsplit(value)
	if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
		raise EnterpriseRuleError(rule)
	return value


def is_shared_issuer(issuer: str) -> bool:
	parts = urlsplit(issuer)
	host = (parts.hostname or "").lower()
	if host in SHARED_ISSUER_HOSTS:
		return True
	if host in _MICROSOFT_HOSTS:
		segments = [segment for segment in parts.path.lower().split("/") if segment]
		return not segments or segments[0] in _MICROSOFT_SHARED_TENANTS
	return False


def check_domain(domain: object) -> str:
	text = _text(domain)
	if not text:
		raise EnterpriseRuleError("invalid_domain")
	if "*" in text:
		raise EnterpriseRuleError("wildcard_domain")
	if text != text.lower() or text.endswith("."):
		raise EnterpriseRuleError("invalid_domain")
	labels = text.split(".")
	if len(labels) < 2 or len(text) > 253 or not all(_DOMAIN_LABEL.fullmatch(label) for label in labels):
		raise EnterpriseRuleError("invalid_domain")
	if text in PUBLIC_MAIL_DOMAINS:
		raise EnterpriseRuleError("public_mail_domain")
	return text


def _check_domains(rows: object, approved_on: datetime | None) -> list[str]:
	if not isinstance(rows, (list, tuple)) or not rows:
		raise EnterpriseRuleError("domains_missing")
	domains = []
	for row in rows:
		if not isinstance(row, Mapping):
			raise EnterpriseRuleError("invalid_record")
		if set(row) - DOMAIN_FIELDS:
			raise EnterpriseRuleError("unknown_field")
		domain = check_domain(row.get("domain"))
		if row.get("verification_method") not in VERIFICATION_METHODS:
			raise EnterpriseRuleError("domain_not_verified")
		if not _text(row.get("verification_record")):
			raise EnterpriseRuleError("domain_not_verified")
		verified_on = parse_time(row.get("verified_on"), "domain_not_verified")
		if approved_on is not None and verified_on >= approved_on:
			raise EnterpriseRuleError("domain_not_verified")
		if domain in domains:
			raise EnterpriseRuleError("duplicate_domain")
		domains.append(domain)
	return domains


def check_request(record: Mapping, *, social_aliases: Collection[str] = ()) -> dict:
	"""Check the fields that the requester fills. The approval is not checked here."""
	return _check(record, social_aliases=social_aliases, approved=False)


def check_record(record: Mapping, *, social_aliases: Collection[str] = ()) -> dict:
	"""Check a whole, approved record. Returns a short summary that holds no role."""
	return _check(record, social_aliases=social_aliases, approved=True)


def _check(record: Mapping, *, social_aliases: Collection[str], approved: bool) -> dict:
	if not isinstance(record, Mapping):
		raise EnterpriseRuleError("invalid_record")
	# The secret check comes first, so no later rule can stop before it.
	_check_no_secret(record)
	if set(record) - RECORD_FIELDS:
		raise EnterpriseRuleError("unknown_field")
	kind = record.get("kind")
	if kind not in KINDS:
		raise EnterpriseRuleError("invalid_kind")
	alias = _required(record, "provider_alias")
	if not _ALIAS.fullmatch(alias):
		raise EnterpriseRuleError("invalid_alias")
	if alias in SOCIAL_PROVIDER_ALIASES or alias in social_aliases:
		raise EnterpriseRuleError("social_platform")
	organization = record.get("organization")
	if not isinstance(organization, str) or not organization.strip():
		raise EnterpriseRuleError("field_missing")
	_required(record, "reason")
	requested_by = _required(record, "requested_by")
	summary = {
		"name": _text(record.get("name")),
		"kind": kind,
		"provider_alias": alias,
		"organization": organization.strip(),
	}
	if kind == "revocation":
		_required(record, "supersedes")
		return summary
	issuer = _https_url(_required(record, "issuer"), "invalid_issuer")
	if is_shared_issuer(issuer):
		raise EnterpriseRuleError("shared_issuer")
	_https_url(_required(record, "provider_document"), "invalid_document")
	expires_on = parse_time(record.get("expires_on"), "expiry_missing")
	approved_on = None
	if approved:
		approved_by = _text(record.get("approved_by"))
		if not approved_by or not _text(record.get("approved_on")):
			raise EnterpriseRuleError("not_approved")
		if approved_by.lower() == requested_by.lower():
			raise EnterpriseRuleError("self_approval")
		if record.get("approval_principal") != APPROVAL_PRINCIPAL:
			raise EnterpriseRuleError("agent_approval")
		approved_on = parse_time(record.get("approved_on"))
		if expires_on <= approved_on:
			raise EnterpriseRuleError("expiry_before_approval")
	domains = _check_domains(record.get("allowed_domains"), approved_on)
	summary.update({"issuer": issuer, "allowed_domains": domains, "expires_on": expires_on.isoformat()})
	return summary


def check_time(now: datetime) -> datetime:
	if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
		raise EnterpriseRuleError("invalid_datetime")
	return now


def is_expired(record: Mapping, now: datetime) -> bool:
	return parse_time(record.get("expires_on"), "expiry_missing") <= check_time(now)


def check_login(
	record: Mapping, claims: Mapping, *, now: datetime, social_aliases: Collection[str] = ()
) -> dict:
	"""Check one sign-in through a provider that has an exception.

	`email_verified` may be missing. If it is present, it must be true. The e-mail domain must be
	one of the record's verified domains. Sub-domains are not included.
	"""
	checked = check_record(record, social_aliases=social_aliases)
	if checked["kind"] != "grant":
		raise EnterpriseRuleError("revoked")
	if is_expired(record, now):
		raise EnterpriseRuleError("expired")
	if "email_verified" in claims and claims["email_verified"] not in (True, "true", "True"):
		raise EnterpriseRuleError("email_verified_false")
	issuer = claims.get("iss")
	if issuer is not None and issuer != checked["issuer"]:
		raise EnterpriseRuleError("issuer_mismatch")
	email = _text(claims.get("email")).lower()
	local, at, domain = email.rpartition("@")
	if not at or not local or domain not in checked["allowed_domains"]:
		raise EnterpriseRuleError("email_domain_not_allowed")
	return {"exception": checked["name"], "email_domain": domain}


__all__ = [
	"PUBLIC_MAIL_DOMAINS",
	"SOCIAL_PROVIDER_ALIASES",
	"SOCIAL_PROVIDER_IDS",
	"EnterpriseRuleError",
	"check_domain",
	"check_login",
	"check_record",
	"check_request",
	"is_expired",
	"is_shared_issuer",
	"parse_time",
]
