"""G-163: email access alone does not recover an account; a recovery request opens a review record.

Expected behaviour comes from the G-163 gap table (AJA-354, rows 3, 5 and 11):
- a recovery request only records a review; it never changes Keycloak credentials or signs anyone in;
- the answer is the same for a known and an unknown address;
- a person other than the account owner decides, with a written note, and a decision is final.
"""

import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1] / "press_tr"
DOCTYPE = APP / "press_identity/doctype/ptr_recovery_review/ptr_recovery_review.json"


def _framework(user=None, link=None, open_review=False, session_user="reviewer@example.test"):
	framework = Mock()
	framework.session = SimpleNamespace(user=session_user)

	def get_value(doctype, filters, field):
		if doctype == "User":
			return user
		if doctype == "PTR Identity Link":
			return link if isinstance(filters, dict) else user
		raise AssertionError(doctype)

	framework.db.get_value.side_effect = get_value
	framework.db.exists.return_value = open_review
	framework.throw.side_effect = PermissionError
	return framework


class RecoveryRequestTest(unittest.TestCase):
	def setUp(self):
		from press_tr.press_identity import recovery

		self.recovery = recovery

	def test_request_opens_review_record_and_changes_nothing_else(self):
		framework = _framework(user="customer@example.test", link="link-1")
		with patch.object(self.recovery, "frappe", framework):
			self.recovery.open_review("  Customer@Example.test ")
		framework.db.get_value.assert_any_call("User", {"email": "customer@example.test"}, "name")
		framework.get_doc.assert_called_once()
		record = framework.get_doc.call_args.args[0]
		self.assertEqual(record["doctype"], "PTR Recovery Review")
		self.assertEqual(record["identity_link"], "link-1")
		self.assertEqual(record["status"], "Open")
		framework.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
		framework.sendmail.assert_not_called()
		framework.db.set_value.assert_not_called()
		framework.delete_doc.assert_not_called()

	def test_recovery_module_cannot_reach_keycloak_or_sessions(self):
		tree = ast.parse((APP / "press_identity/recovery.py").read_text(encoding="utf-8"))
		imported = set()
		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				imported.update(alias.name for alias in node.names)
			elif isinstance(node, ast.ImportFrom):
				imported.add(node.module or "")
		self.assertEqual(imported, {"frappe"})

	def test_unknown_or_unlinked_address_opens_nothing(self):
		for user, link, email in (
			(None, None, "nobody@example.test"),
			("customer@example.test", None, "customer@example.test"),
			(None, None, "not-an-address"),
			(None, None, ""),
		):
			with self.subTest(email=email):
				framework = _framework(user=user, link=link)
				with patch.object(self.recovery, "frappe", framework):
					self.recovery.open_review(email)
				framework.get_doc.assert_not_called()

	def test_second_request_does_not_stack_open_reviews(self):
		framework = _framework(user="customer@example.test", link="link-1", open_review=True)
		with patch.object(self.recovery, "frappe", framework):
			self.recovery.open_review("customer@example.test")
		framework.db.exists.assert_called_once_with(
			"PTR Recovery Review", {"identity_link": "link-1", "status": "Open"}
		)
		framework.get_doc.assert_not_called()


class RecoveryDecisionTest(unittest.TestCase):
	def setUp(self):
		from press_tr.press_identity import recovery

		self.recovery = recovery

	def _doc(self, status, before=None, note="Identity confirmed by phone call."):
		previous = SimpleNamespace(status=before, review_note="") if before else None
		return SimpleNamespace(
			status=status,
			review_note=note,
			identity_link="link-1",
			reviewed_by=None,
			reviewed_at=None,
			get_doc_before_save=lambda: previous,
		)

	def _check(self, doc, session_user="reviewer@example.test"):
		framework = _framework(user="customer@example.test", session_user=session_user)
		with (
			patch.object(self.recovery, "frappe", framework),
			patch.object(self.recovery, "_", lambda text, context=None: text),
		):
			self.recovery.check_decision(doc)
		return framework

	def test_new_record_must_start_open(self):
		self._check(self._doc("Open"))
		for status in ("Approved", "Rejected"):
			with self.subTest(status=status), self.assertRaises(PermissionError):
				self._check(self._doc(status))

	def test_reviewer_decides_with_note(self):
		for status in ("Approved", "Rejected"):
			with self.subTest(status=status):
				doc = self._doc(status, before="Open")
				framework = self._check(doc)
				self.assertEqual(doc.reviewed_by, "reviewer@example.test")
				self.assertIs(doc.reviewed_at, framework.utils.now_datetime.return_value)

	def test_owner_guest_or_empty_note_cannot_decide(self):
		cases = (
			(self._doc("Approved", before="Open"), "customer@example.test"),
			(self._doc("Approved", before="Open"), "Guest"),
			(self._doc("Approved", before="Open", note="  "), "reviewer@example.test"),
		)
		for doc, user in cases:
			with self.subTest(user=user, note=doc.review_note), self.assertRaises(PermissionError):
				self._check(doc, session_user=user)

	def test_decision_is_final(self):
		for before, after in (("Approved", "Open"), ("Rejected", "Approved"), ("Approved", "Rejected")):
			with self.subTest(before=before, after=after), self.assertRaises(PermissionError):
				self._check(self._doc(after, before=before))
		for before in ("Approved", "Rejected"):
			doc = self._doc(before, before=before, note="Changed later.")
			with self.subTest(edit=before), self.assertRaises(PermissionError):
				self._check(doc)


class RecoveryRouteTest(unittest.TestCase):
	def test_route_is_rate_limited_guest_post_with_the_same_answer(self):
		tree = ast.parse((APP / "api/account.py").read_text(encoding="utf-8"))
		route = next(
			node
			for node in tree.body
			if isinstance(node, ast.FunctionDef) and node.name == "request_recovery"
		)
		decorators = [ast.unparse(item) for item in route.decorator_list]
		self.assertIn("frappe.whitelist(allow_guest=True, methods=['POST'])", decorators)
		self.assertIn("rate_limit_namespace('press_tr.api.account.request_recovery')", decorators)
		self.assertTrue(any(item.startswith("rate_limit(limit=") for item in decorators))
		returns = [ast.unparse(node.value) for node in ast.walk(route) if isinstance(node, ast.Return)]
		self.assertEqual(returns, ["{'received': True}"])
		calls = {ast.unparse(node.func) for node in ast.walk(route) if isinstance(node, ast.Call)}
		self.assertIn("open_review", calls)

	def test_review_doctype_is_desk_only_with_final_states(self):
		doc = json.loads(DOCTYPE.read_text(encoding="utf-8"))
		fields = {field["fieldname"]: field for field in doc["fields"]}
		self.assertEqual(doc["name"], "PTR Recovery Review")
		self.assertEqual(doc["module"], "Press Identity")
		self.assertEqual(fields["status"]["options"].split("\n"), ["Open", "Approved", "Rejected"])
		self.assertEqual(fields["status"]["default"], "Open")
		self.assertEqual(fields["identity_link"]["options"], "PTR Identity Link")
		for name in ("reviewed_by", "reviewed_at", "identity_link", "requested_at"):
			self.assertTrue(fields[name].get("read_only"), name)
		self.assertTrue(all(field.get("description") for field in doc["fields"]))
		roles = {permission["role"]: permission for permission in doc["permissions"]}
		self.assertEqual(set(roles), {"System Manager"})
		self.assertFalse(roles["System Manager"].get("create"))
		self.assertFalse(roles["System Manager"].get("delete"))


if __name__ == "__main__":
	unittest.main()
