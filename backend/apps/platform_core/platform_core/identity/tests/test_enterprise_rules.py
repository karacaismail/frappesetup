"""Rules of the corporate sign-in provider exception (G-160, AJA-229).

The rules come from the security opinion (AJA-212) and the design (AJA-238). The module needs no
Frappe and no database. The `apply` command loads the same file by path.
"""

import ast
import copy
import unittest
from datetime import UTC, datetime, timezone
from pathlib import Path

from platform_core.identity import enterprise_rules
from platform_core.identity.enterprise_rules import EnterpriseRuleError

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def grant():
	"""A valid, approved exception record. Each test breaks one field."""
	return {
		"name": "EIDP-0001",
		"kind": "grant",
		"provider_alias": "acme-entra",
		"issuer": "https://login.microsoftonline.com/0b5e3b55-1f4c-4d2e-9a77-1c2d3e4f5a6b/v2.0",
		"organization": "acme",
		"allowed_domains": [
			{
				"domain": "acme.example",
				"verification_method": "dns-txt",
				"verified_on": "2026-11-20T09:00:00+00:00",
				"verification_record": "_atonota-verify.acme.example",
			}
		],
		"reason": "The provider does not send the email_verified claim.",
		"provider_document": "https://docs.example/provider/claims",
		"requested_by": "owner@acme.example",
		"approved_by": "security@platform.example",
		"approval_principal": "human_session",
		"approved_on": "2026-11-21T10:00:00+00:00",
		"expires_on": "2027-01-01T00:00:00+00:00",
		"supersedes": None,
	}


def claims(**changes):
	value = {"email": "kisi@acme.example", "iss": grant()["issuer"]}
	value.update(changes)
	return value


class RuleTestCase(unittest.TestCase):
	def assert_rule(self, rule, function, *arguments, **keywords):
		with self.assertRaises(EnterpriseRuleError) as raised:
			function(*arguments, **keywords)
		self.assertEqual(raised.exception.rule, rule)
		return raised.exception


class RejectedRecordTest(RuleTestCase):
	def test_valid_record_passes(self):
		checked = enterprise_rules.check_record(grant())
		self.assertEqual(checked["provider_alias"], "acme-entra")
		self.assertEqual(checked["allowed_domains"], ["acme.example"])

	def test_email_verified_false_is_rejected(self):
		# Case 1: the exception replaces a missing claim, never a negative one.
		for value in (False, "false", "False"):
			with self.subTest(value=value):
				self.assert_rule(
					"email_verified_false",
					enterprise_rules.check_login,
					grant(),
					claims(email_verified=value),
					now=NOW,
				)

	def test_wildcard_domain_is_rejected(self):
		# Case 3.
		for domain in ("*.com", "*.acme.example", "acme.*"):
			record = grant()
			record["allowed_domains"][0]["domain"] = domain
			with self.subTest(domain=domain):
				self.assert_rule("wildcard_domain", enterprise_rules.check_record, record)

	def test_public_mail_domain_is_rejected(self):
		# Case 4.
		for domain in ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "yandex.com"):
			record = grant()
			record["allowed_domains"][0]["domain"] = domain
			with self.subTest(domain=domain):
				self.assert_rule("public_mail_domain", enterprise_rules.check_record, record)

	def test_unverified_domain_is_rejected(self):
		# Case 5: the DNS TXT proof is required and must come before the approval.
		changes = (
			("verification_method", "email"),
			("verification_method", None),
			("verified_on", None),
			("verified_on", "2026-11-22T10:00:00+00:00"),
			("verification_record", ""),
		)
		for key, value in changes:
			record = grant()
			record["allowed_domains"][0][key] = value
			with self.subTest(key=key, value=value):
				self.assert_rule("domain_not_verified", enterprise_rules.check_record, record)

	def test_shared_issuer_is_rejected(self):
		# Case 6: an issuer that many organisations share.
		for issuer in (
			"https://login.microsoftonline.com/common/v2.0",
			"https://login.microsoftonline.com/organizations/v2.0",
			"https://login.microsoftonline.com/consumers/v2.0",
			"https://login.microsoftonline.com/COMMON",
			"https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0",
			"https://accounts.google.com",
		):
			record = grant()
			record["issuer"] = issuer
			with self.subTest(issuer=issuer):
				self.assert_rule("shared_issuer", enterprise_rules.check_record, record)

	def test_self_approval_is_rejected(self):
		# Case 8.
		record = grant()
		record["approved_by"] = record["requested_by"]
		self.assert_rule("self_approval", enterprise_rules.check_record, record)
		record = grant()
		record["approved_by"] = record["requested_by"].upper()
		self.assert_rule("self_approval", enterprise_rules.check_record, record)

	def test_agent_approval_is_rejected(self):
		# Case 8, second part: an agent prepares a request but never approves it.
		for principal in ("agent_token", "oauth", "other", None, ""):
			record = grant()
			record["approval_principal"] = principal
			with self.subTest(principal=principal):
				self.assert_rule("agent_approval", enterprise_rules.check_record, record)

	def test_missing_expiry_is_rejected(self):
		# Case 9: there is no default length. The length is a product decision.
		for value in (None, ""):
			record = grant()
			record["expires_on"] = value
			with self.subTest(value=value):
				self.assert_rule("expiry_missing", enterprise_rules.check_record, record)
		record = grant()
		del record["expires_on"]
		self.assert_rule("expiry_missing", enterprise_rules.check_record, record)

	def test_expiry_before_approval_is_rejected(self):
		record = grant()
		record["expires_on"] = "2026-11-21T09:00:00+00:00"
		self.assert_rule("expiry_before_approval", enterprise_rules.check_record, record)

	def test_secret_in_record_is_rejected(self):
		# Case 11: a secret-like field name or a secret-like value.
		for key in ("client_secret", "password", "token", "access_token", "private_key", "api_key"):
			record = grant()
			record[key] = "x"
			with self.subTest(key=key):
				self.assert_rule("secret_in_record", enterprise_rules.check_record, record)
		values = (
			"eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl",
			# Fake key headers. They match the record check but are not a real key format.
			"-----BEGIN TEST KEY-----",
		)
		for value in values:
			record = grant()
			record["reason"] = value
			with self.subTest(value=value[:12]):
				self.assert_rule("secret_in_record", enterprise_rules.check_record, record)
		record = grant()
		record["allowed_domains"][0]["client_secret"] = "x"
		self.assert_rule("secret_in_record", enterprise_rules.check_record, record)

	def test_secret_error_does_not_echo_the_value(self):
		record = grant()
		record["reason"] = "-----BEGIN TEST KEY----- abc"
		error = self.assert_rule("secret_in_record", enterprise_rules.check_record, record)
		self.assertNotIn("BEGIN", str(error))

	def test_email_outside_allowed_domains_is_rejected(self):
		# Case 12.
		for email in ("kisi@baska.example", "kisi@sub.acme.example", "kisi@acme.example.invalid", "kisi"):
			with self.subTest(email=email):
				self.assert_rule(
					"email_domain_not_allowed",
					enterprise_rules.check_login,
					grant(),
					claims(email=email),
					now=NOW,
				)

	def test_trust_email_field_is_rejected(self):
		for key in ("trustEmail", "trust_email"):
			record = grant()
			record[key] = False
			with self.subTest(key=key):
				self.assert_rule("unknown_field", enterprise_rules.check_record, record)

	def test_unknown_field_is_rejected(self):
		record = grant()
		record["realm_wide"] = True
		self.assert_rule("unknown_field", enterprise_rules.check_record, record)

	def test_one_provider_and_one_organisation(self):
		for key, value in (("organization", ""), ("organization", ["a", "b"]), ("provider_alias", "")):
			record = grant()
			record[key] = value
			with self.subTest(key=key, value=value):
				with self.assertRaises(EnterpriseRuleError):
					enterprise_rules.check_record(record)

	def test_issuer_must_be_https(self):
		record = grant()
		record["issuer"] = "http://login.microsoftonline.com/0b5e3b55-1f4c-4d2e-9a77-1c2d3e4f5a6b/v2.0"
		self.assert_rule("invalid_issuer", enterprise_rules.check_record, record)

	def test_unapproved_record_is_rejected(self):
		for key in ("approved_by", "approved_on"):
			record = grant()
			record[key] = None
			with self.subTest(key=key):
				self.assert_rule("not_approved", enterprise_rules.check_record, record)

	def test_social_alias_is_rejected_when_named(self):
		record = grant()
		record["provider_alias"] = "google"
		self.assert_rule(
			"social_platform", enterprise_rules.check_record, record, social_aliases={"google", "facebook"}
		)

	def test_social_alias_is_rejected_by_default(self):
		for alias in ("google", "facebook", "x", "apple", "linkedin"):
			record = grant()
			record["provider_alias"] = alias
			with self.subTest(alias=alias):
				self.assert_rule("social_platform", enterprise_rules.check_record, record)
				self.assert_rule("social_platform", enterprise_rules.check_request, record)

	def test_request_needs_no_approval_yet(self):
		record = grant()
		for key in ("approved_by", "approved_on", "approval_principal"):
			record[key] = None
		self.assertEqual(enterprise_rules.check_request(record)["provider_alias"], "acme-entra")
		record["expires_on"] = None
		self.assert_rule("expiry_missing", enterprise_rules.check_request, record)

	def test_record_is_not_changed_by_the_check(self):
		record = grant()
		before = copy.deepcopy(record)
		enterprise_rules.check_record(record)
		self.assertEqual(record, before)


class LoginTest(RuleTestCase):
	def test_matching_email_passes(self):
		result = enterprise_rules.check_login(grant(), claims(email="Kisi@ACME.example"), now=NOW)
		self.assertEqual(result, {"exception": "EIDP-0001", "email_domain": "acme.example"})

	def test_expired_exception_refuses_login(self):
		later = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
		self.assert_rule("expired", enterprise_rules.check_login, grant(), claims(), now=later)

	def test_other_issuer_refuses_login(self):
		self.assert_rule(
			"issuer_mismatch",
			enterprise_rules.check_login,
			grant(),
			claims(iss="https://login.microsoftonline.com/other/v2.0"),
			now=NOW,
		)

	def test_now_must_carry_a_time_zone(self):
		with self.assertRaises(EnterpriseRuleError):
			enterprise_rules.check_login(grant(), claims(), now=datetime(2026, 11, 24, 12, 0))


class EnterpriseRoleTest(unittest.TestCase):
	def test_exception_never_touches_enterprise_role(self):
		# The enterprise-sso-required rule stays as it is. The rules give and take no role.
		checked = enterprise_rules.check_record(grant())
		login = enterprise_rules.check_login(grant(), claims(), now=NOW)
		for result in (checked, login):
			self.assertNotIn("roles", result)
			self.assertNotIn("enterprise-sso-required", repr(result))


class ModuleBoundaryTest(unittest.TestCase):
	def test_rules_module_has_no_frappe_import(self):
		path = Path(enterprise_rules.__file__)
		tree = ast.parse(path.read_text(encoding="utf-8"))
		names = set()
		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				names.update(alias.name.split(".")[0] for alias in node.names)
			elif isinstance(node, ast.ImportFrom):
				names.add((node.module or "").split(".")[0])
		self.assertNotIn("frappe", names)
		self.assertNotIn("platform_core", names)
		self.assertNotIn("frappe", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
	unittest.main()
