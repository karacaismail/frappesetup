"""Check the leave endpoints' transport and record permission boundaries."""

from inspect import signature
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from hrms_tr import leave, retention
from hrms_tr.api import approve_leave, cancel_leave, get_leave_approver


def raise_permission_error(message, exc=frappe.PermissionError, **kwargs):
	raise exc(message)


class ApprovalEndpointTest(TestCase):
	def test_get_leave_approver_has_typed_response(self):
		self.assertEqual(signature(get_leave_approver).return_annotation, dict[str, str | None])

	def test_approve_leave_guest_denied(self):
		self.assert_guest_denied(approve_leave)

	def test_cancel_leave_guest_denied(self):
		self.assert_guest_denied(cancel_leave)

	def test_get_leave_approver_guest_denied(self):
		self.assert_guest_denied(get_leave_approver)

	def assert_guest_denied(self, endpoint):
		with (
			patch.object(frappe, "session", {"user": "Guest"}),
			patch.object(frappe, "response", {}),
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(endpoint)

	def test_cancel_leave_foreign_data_denied(self):
		doc = Mock()
		doc.check_permission.side_effect = frappe.PermissionError("Foreign application")
		with patch.object(leave, "frappe") as fake:
			fake.get_roles.return_value = ["HRT Admin"]
			fake.get_doc.return_value = doc
			with self.assertRaises(frappe.PermissionError):
				cancel_leave("LEAVE-FOREIGN-0001", "2026-11-22 12:00:00")
		fake.get_doc.assert_called_once_with("Leave Application", "LEAVE-FOREIGN-0001", for_update=True)
		doc.check_permission.assert_called_once_with("read")
		doc.cancel.assert_not_called()

	def test_get_leave_approver_foreign_data_denied(self):
		native_module, method_name = leave.HRMS_APPROVER_METHOD.rsplit(".", 1)
		native_lookup = getattr(frappe.get_module(native_module), method_name)
		with (
			patch.object(leave, "frappe") as fake,
			patch(f"{native_module}.validate_leave_access", side_effect=frappe.PermissionError) as validate,
			patch(f"{native_module}.get_employee_leave_approver") as lookup,
		):
			fake.get_roles.return_value = ["HRT Employee"]
			fake.db.exists.return_value = True
			fake.get_attr.return_value = native_lookup
			with self.assertRaises(frappe.PermissionError):
				get_leave_approver("EMP-FOREIGN-0001")
		fake.get_attr.assert_called_once_with(leave.HRMS_APPROVER_METHOD)
		validate.assert_called_once_with("EMP-FOREIGN-0001", None)
		lookup.assert_not_called()

	def test_approve_leave_foreign_data_denied(self):
		doc = Mock()
		doc.check_permission.side_effect = frappe.PermissionError("Foreign application")
		with patch.object(leave, "frappe") as fake:
			fake.get_roles.return_value = ["HRT Manager"]
			fake.get_doc.return_value = doc
			with self.assertRaises(frappe.PermissionError):
				approve_leave("LEAVE-FOREIGN-0001", "2026-11-22 12:00:00")
		doc.check_permission.assert_called_once_with("read")
		doc.submit.assert_not_called()

	def test_approve_leave_stale_version_is_rejected_under_lock(self):
		doc = Mock(employee="EMP-0001", docstatus=0, status="Open", modified="2026-11-22 12:00:01")
		with (
			patch.object(leave, "frappe") as fake,
			patch.object(leave, "_", side_effect=lambda message, context=None: message),
		):
			fake.get_roles.return_value = ["HRT Manager"]
			fake.session.user = "manager@example.test"
			fake.db.get_value.return_value = "employee@example.test"
			fake.get_doc.return_value = doc
			fake.TimestampMismatchError = frappe.TimestampMismatchError
			fake.throw.side_effect = raise_permission_error
			with self.assertRaises(frappe.TimestampMismatchError) as error:
				approve_leave("LEAVE-STALE-0001", "2026-11-22 12:00:00")
		self.assertEqual(error.exception.http_status_code, 417)
		fake.get_doc.assert_called_once_with("Leave Application", "LEAVE-STALE-0001", for_update=True)
		doc.submit.assert_not_called()
		self.assertEqual(doc.status, "Open")

	def test_approve_leave_throttles_by_authenticated_user(self):
		from types import SimpleNamespace

		cache = Mock()
		cache.make_key.return_value = b"site:counter"
		cache.get.return_value = 60
		cache.incrby.return_value = 61
		with (
			patch.object(frappe, "request", SimpleNamespace(method="POST")),
			patch.object(frappe, "session", frappe._dict(user="manager@example.test")),
			patch.object(frappe, "cache", cache),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
			patch("frappe.rate_limiter._", side_effect=lambda text: text),
			patch.object(leave, "approve") as approve,
		):
			with self.assertRaises(frappe.RateLimitExceededError):
				approve_leave("HR-LAP-TEST", "2026-11-22 12:00:00")
		cache.make_key.assert_called_once_with("rl:hrms_tr.api.approve_leave:manager@example.test")
		approve.assert_not_called()

	def test_missing_version_raises_native_validation_error(self):
		from hrms_tr import api

		with (
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(api, "_", create=True, side_effect=lambda message, context=None: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
			patch.object(leave, "approve") as approve,
		):
			with self.assertRaises(frappe.ValidationError):
				approve_leave("LEAVE-MISSING")
		approve.assert_not_called()


class RetentionIntegrationTest(IntegrationTestCase):
	def test_purge_only_deletes_expired_leave_and_keeps_employee_and_allocation(self):
		prefix = frappe.generate_hash(length=12)
		expired = add_days(today(), -31)
		employee = frappe.get_doc(
			doctype="Employee", name=f"{prefix}-employee", status="Left", relieving_date=expired
		)
		employee.db_insert()
		allocation = frappe.get_doc(
			doctype="Leave Allocation", name=f"{prefix}-allocation", employee=employee.name, docstatus=1
		)
		allocation.db_insert()

		def insert_leave(suffix, end, docstatus=0, amended_from=None):
			doc = frappe.get_doc(
				doctype="Leave Application",
				name=f"{prefix}-{suffix}",
				employee=employee.name,
				from_date=end,
				to_date=end,
				docstatus=docstatus,
				amended_from=amended_from,
			)
			doc.db_insert()
			return doc.name

		older = insert_leave("1-expired", expired, docstatus=2)
		other = insert_leave("2-expired", expired)
		submitted = insert_leave("submitted", expired, docstatus=1)
		recent = insert_leave("recent", today(), amended_from=older)
		with patch.dict(frappe.conf, {"hrms_tr_retention_days": 30}):
			preview = retention.purge(limit=1)
			self.assertEqual((preview["leaves"], preview["remaining"]), (1, 1))
			self.assertTrue(frappe.db.exists("Leave Application", older))
			frappe.db.savepoint("before_retention_link_check")
			with self.assertRaises(frappe.LinkExistsError):
				retention.purge(dry_run=False, limit=1)
			frappe.db.rollback(save_point="before_retention_link_check")
			self.assertTrue(frappe.db.exists("Leave Application", older))
			frappe.db.set_value("Leave Application", recent, "amended_from", None)

			purge_outcome = retention.purge(dry_run=False, limit=1)
			self.assertEqual((purge_outcome["leaves"], purge_outcome["remaining"]), (1, 1))
			self.assertFalse(frappe.db.exists("Leave Application", older))
			self.assertFalse(frappe.db.exists("Deleted Document", {"deleted_name": older}))
			self.assertTrue(frappe.db.exists("Employee", employee.name))
			self.assertTrue(frappe.db.exists("Leave Allocation", allocation.name))
			for name in (other, submitted, recent):
				self.assertTrue(frappe.db.exists("Leave Application", name))


class EmployeeAnonymizationTest(IntegrationTestCase):
	def test_account_deletion_redacts_employee_and_keeps_leave(self):
		suffix = frappe.generate_hash(length=12)
		user = f"retention-{suffix}@example.test"
		frappe.get_doc(
			doctype="User", email=user, first_name="Synthetic", last_name="Employee", send_welcome_email=0
		).insert()
		issuer = "http://identity.localhost:8660/realms/platform"
		frappe.get_doc(doctype="PLT Identity Link", issuer=issuer, subject=suffix, user=user).insert()
		redacted_fields = {
			"first_name": "Synthetic",
			"middle_name": "Example",
			"last_name": "Employee",
			"employee_name": "Synthetic Example Employee",
			"cell_number": "+90 200 000 00 00",
			"emergency_phone_number": "+90 200 000 00 00",
			"person_to_be_contacted": "Synthetic Emergency Contact",
			"relation": "Synthetic relation",
			"passport_number": "NOT-A-PASSPORT",
			"place_of_issue": "Synthetic issuing place",
			"iban": "NOT-AN-IBAN",
			"bank_name": "Synthetic Bank",
			"bank_ac_no": "NOT-A-BANK-ACCOUNT",
			"health_details": "Synthetic health note",
			"health_insurance_no": "NOT-AN-INSURANCE-NUMBER",
			"family_background": "Synthetic family note",
			"current_address": "Synthetic current address",
			"permanent_address": "Synthetic permanent address",
			"bio": "Synthetic biography",
		}
		email_fields = {
			"personal_email": f"personal-{suffix}@example.test",
			"prefered_email": f"personal-{suffix}@example.test",
			"company_email": f"company-{suffix}@example.test",
		}
		cleared_fields = {
			"date_of_birth": "1990-01-01",
			"date_of_issue": "2010-01-01",
			"valid_upto": "2020-01-01",
			"blood_group": "A+",
			"marital_status": "Single",
			"image": "/files/synthetic-employee-image.png",
		}
		personal_fields = {**redacted_fields, **email_fields, **cleared_fields}
		employee = frappe.get_doc(
			doctype="Employee",
			name=f"{suffix}-employee",
			user_id=user,
			status="Active",
			attendance_device_id=f"SYNTHETIC-DEVICE-{suffix}",
			**personal_fields,
		)
		employee.db_insert()
		historical = frappe.get_doc(
			doctype="Employee",
			name=f"{suffix}-historical",
			user_id=user,
			status="Left",
			attendance_device_id=f"SYNTHETIC-OLD-DEVICE-{suffix}",
			**personal_fields,
		)
		historical.db_insert()
		other = frappe.get_doc(doctype="Employee", name=f"{suffix}-other", **personal_fields)
		other.db_insert()
		application = frappe.get_doc(
			doctype="Leave Application",
			name=f"{suffix}-leave",
			employee=employee.name,
			employee_name=personal_fields["employee_name"],
			from_date=today(),
			to_date=today(),
		)
		application.db_insert()
		delete_account = frappe.get_attr("platform_core.api.identity.anonymize_user")
		with (
			patch.dict(
				frappe.conf,
				{
					"keycloak_public_url": "http://identity.localhost:8660",
					"keycloak_realm": "platform",
					"kimlik_deletion_hmac_key": "synthetic-anonymization-test-key",
				},
			),
			patch.object(frappe.local, "identity_service_claims", {"azp": "identity-sync"}, create=True),
			patch.object(frappe.local, "form_dict", {"issuer": issuer, "subject": suffix}, create=True),
			# Keep the real two-stage write inside the integration test's rollback.
			patch.object(frappe.db, "commit"),
		):
			deleted_account = delete_account(issuer=issuer, subject=suffix)
		self.assertEqual(deleted_account["status"], "Anonymized")
		employee.reload()
		self.assertEqual(employee.user_id, deleted_account["user"])
		for field in redacted_fields:
			self.assertEqual(employee.get(field), "[REDACTED]", field)
		for field in email_fields:
			self.assertEqual(employee.get(field), deleted_account["user"], field)
		for field in cleared_fields:
			self.assertFalse(employee.get(field), field)
		self.assertFalse(employee.attendance_device_id)
		historical.reload()
		self.assertFalse(historical.attendance_device_id)
		self.assertEqual(historical.user_id, deleted_account["user"])
		self.assertEqual(historical.first_name, "[REDACTED]")
		other.reload()
		self.assertEqual(other.employee_name, personal_fields["employee_name"])
		self.assertEqual(other.personal_email, personal_fields["personal_email"])
		application.reload()
		self.assertEqual(application.employee, employee.name)
		self.assertEqual(application.employee_name, personal_fields["employee_name"])
		self.assertEqual(employee.status, "Active")
