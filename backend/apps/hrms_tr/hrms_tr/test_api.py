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


class LeaveRequestContextCleanupTest(TestCase):
	def test_cleanup_preserves_runner_flags(self):
		previous_flags = getattr(frappe.local, "flags", None)
		self.addCleanup(setattr, frappe.local, "flags", previous_flags)
		runner_flags = frappe._dict(in_test=True, mute_emails=True)
		frappe.local.flags = runner_flags

		case = LeaveRequestContextTest("test_no_employee_returns_null_values_and_sources")
		result = case.run()

		self.assertTrue(result.wasSuccessful(), (result.errors, result.failures))
		self.assertIs(frappe.local.flags, runner_flags)
		self.assertEqual(runner_flags, {"in_test": True, "mute_emails": True})


class LeaveRequestContextTest(TestCase):
	"""The request context exposes only the signed-in employee's data."""

	def setUp(self):
		from hrms_tr import api

		self.api = api
		previous_flags = getattr(frappe.local, "flags", None)
		frappe.local.flags = frappe._dict()
		self.addCleanup(setattr, frappe.local, "flags", previous_flags)
		self.fake = self.enterContext(patch.object(api, "frappe"))
		self.fake.session.user = "employee@example.test"
		self.fake.db.get_value.return_value = frappe._dict(
			name="EMP-SELF-0001", employee_name="Synthetic Employee"
		)
		self.fake.db.exists.return_value = "Annual Leave"
		self.fake.get_all.return_value = ["Annual Leave"]
		self.fake.PermissionError = frappe.PermissionError
		self.fake.get_attr.side_effect = frappe.get_attr
		self.enterContext(
			patch.object(frappe, "get_installed_apps", return_value=["frappe", "hrms", "hrms_tr"])
		)
		self.fake.throw.side_effect = raise_permission_error
		self.enterContext(patch.object(api, "_", side_effect=lambda message, **kwargs: message))
		self.enterContext(patch("frappe.utils.today", return_value="2026-11-26"))
		native = "hrms.hr.doctype.leave_application.leave_application"
		self.allocations = self.enterContext(patch(f"{native}.get_leave_allocation_records"))
		self.allocations.return_value = {"Annual Leave": {"total_leaves_allocated": 14}}
		self.balance = self.enterContext(patch(f"{native}.get_leave_balance_on", return_value=8.5))

	def test_context_returns_self_and_native_balance_with_sources(self):
		result = self.api.get_leave_request_context()
		self.assertEqual(
			result,
			{
				"employee": "EMP-SELF-0001",
				"employee_name": "Synthetic Employee",
				"leave_type": "Annual Leave",
				"leave_balance": 8.5,
				"sources": {
					"employee": "Employee",
					"employee_name": "Employee",
					"leave_type": "Leave Allocation",
					"leave_balance": "Leave Ledger Entry",
				},
			},
		)
		self.fake.db.get_value.assert_called_once_with(
			"Employee",
			{"user_id": "employee@example.test", "status": "Active"},
			["name", "employee_name"],
			as_dict=True,
		)
		self.fake.get_all.assert_called_once_with(
			"Leave Allocation",
			filters={
				"employee": "EMP-SELF-0001",
				"docstatus": 1,
				"from_date": ["<=", "2026-11-26"],
				"to_date": [">=", "2026-11-26"],
			},
			pluck="leave_type",
			distinct=True,
			order_by="leave_type",
			limit_page_length=2,
		)
		self.allocations.assert_called_once_with("EMP-SELF-0001", "2026-11-26", "Annual Leave")
		self.balance.assert_called_once_with("EMP-SELF-0001", "Annual Leave", "2026-11-26")
		self.fake.db.exists.assert_not_called()

	def test_single_allocated_type_does_not_require_an_annual_leave_record(self):
		self.fake.db.exists.return_value = None
		self.fake.get_all.return_value = ["Study Leave"]
		self.allocations.return_value = {"Study Leave": {"total_leaves_allocated": 5}}
		result = self.api.get_leave_request_context()
		self.assertEqual((result["leave_type"], result["leave_balance"]), ("Study Leave", 8.5))
		self.assertEqual(result["sources"]["leave_type"], "Leave Allocation")
		self.allocations.assert_called_once_with("EMP-SELF-0001", "2026-11-26", "Study Leave")
		self.balance.assert_called_once_with("EMP-SELF-0001", "Study Leave", "2026-11-26")

	def test_multiple_allocated_types_return_no_type_or_balance(self):
		self.fake.get_all.return_value = ["Annual Leave", "Study Leave"]
		self.allocations.return_value = {
			"Annual Leave": {"total_leaves_allocated": 14},
			"Study Leave": {"total_leaves_allocated": 5},
		}
		result = self.api.get_leave_request_context()
		for key in ("leave_type", "leave_balance"):
			self.assertIsNone(result[key])
			self.assertIsNone(result["sources"][key])
		self.balance.assert_not_called()
		self.allocations.assert_not_called()

	def test_no_employee_returns_null_values_and_sources(self):
		self.fake.db.get_value.return_value = None
		result = self.api.get_leave_request_context()
		fields = ("employee", "employee_name", "leave_type", "leave_balance")
		self.assertEqual({key: result[key] for key in fields}, dict.fromkeys(fields))
		self.assertEqual(result["sources"], dict.fromkeys(fields))
		self.allocations.assert_not_called()
		self.balance.assert_not_called()
		self.fake.get_all.assert_not_called()

	def test_missing_display_name_has_no_invented_value_or_source(self):
		self.fake.db.get_value.return_value.employee_name = None
		result = self.api.get_leave_request_context()
		self.assertIsNone(result["employee_name"])
		self.assertIsNone(result["sources"]["employee_name"])
		self.assertEqual(result["employee"], "EMP-SELF-0001")

	def test_requested_leave_type_uses_its_native_balance(self):
		self.fake.db.exists.return_value = "Study Leave"
		self.allocations.return_value = {"Study Leave": {"total_leaves_allocated": 5}}
		self.balance.return_value = 2.5
		result = self.api.get_leave_request_context(leave_type="Study Leave")
		self.assertEqual((result["leave_type"], result["leave_balance"]), ("Study Leave", 2.5))
		self.assertEqual(result["sources"]["leave_type"], "Leave Type")
		self.fake.db.exists.assert_called_once_with("Leave Type", "Study Leave")
		self.fake.get_all.assert_not_called()
		self.allocations.assert_called_once_with("EMP-SELF-0001", "2026-11-26", "Study Leave")
		self.balance.assert_called_once_with("EMP-SELF-0001", "Study Leave", "2026-11-26")

	def test_missing_leave_type_returns_null_type_and_balance(self):
		self.fake.db.exists.return_value = None
		result = self.api.get_leave_request_context(leave_type="Missing Leave")
		for key in ("leave_type", "leave_balance"):
			self.assertIsNone(result[key])
			self.assertIsNone(result["sources"][key])
		self.allocations.assert_not_called()
		self.balance.assert_not_called()

	def test_missing_allocation_does_not_invent_a_zero_balance(self):
		self.fake.get_all.return_value = []
		self.allocations.return_value = {}
		result = self.api.get_leave_request_context()
		for key in ("leave_type", "leave_balance"):
			self.assertIsNone(result[key])
			self.assertIsNone(result["sources"][key])
		self.balance.assert_not_called()
		self.allocations.assert_not_called()

	def test_ledger_adjustment_without_allocation_does_not_select_a_type(self):
		self.fake.get_all.return_value = []
		self.allocations.return_value = {"Study Leave": {"total_leaves_allocated": 5}}
		result = self.api.get_leave_request_context()
		for key in ("leave_type", "leave_balance"):
			self.assertIsNone(result[key])
			self.assertIsNone(result["sources"][key])
		self.allocations.assert_not_called()
		self.balance.assert_not_called()

	def test_requested_type_without_allocation_preserves_type_and_null_balance(self):
		self.allocations.return_value = {}
		result = self.api.get_leave_request_context(leave_type="Annual Leave")
		self.assertEqual(result["leave_type"], "Annual Leave")
		self.assertEqual(result["sources"]["leave_type"], "Leave Type")
		self.assertIsNone(result["leave_balance"])
		self.assertIsNone(result["sources"]["leave_balance"])
		self.balance.assert_not_called()

	def test_real_zero_balance_is_preserved(self):
		self.balance.return_value = 0
		result = self.api.get_leave_request_context()
		self.assertEqual(result["leave_balance"], 0)
		self.assertEqual(result["sources"]["leave_balance"], "Leave Ledger Entry")

	def test_native_missing_balance_has_no_source(self):
		self.balance.return_value = None
		result = self.api.get_leave_request_context()
		self.assertIsNone(result["leave_balance"])
		self.assertIsNone(result["sources"]["leave_balance"])

	def test_native_permission_error_is_not_hidden(self):
		self.balance.side_effect = frappe.PermissionError("Denied")
		with self.assertRaises(frappe.PermissionError):
			self.api.get_leave_request_context()

	def test_get_leave_request_context_foreign_data_denied(self):
		# Frappe discards unsupported arguments. Neither identifier may select another employee.
		allocations_by_employee = {
			"EMP-SELF-0001": ["Study Leave"],
			"EMP-FOREIGN-0001": ["Foreign Leave"],
		}
		self.fake.get_all.side_effect = lambda doctype, **kwargs: allocations_by_employee[
			kwargs["filters"]["employee"]
		]
		self.allocations.return_value = {"Study Leave": {"total_leaves_allocated": 5}}
		result = frappe.call(
			self.api.get_leave_request_context, employee="EMP-FOREIGN-0001", user="other@example.test"
		)
		self.assertEqual(result["employee"], "EMP-SELF-0001")
		self.assertEqual(result["leave_type"], "Study Leave")
		self.assertEqual(result["sources"]["leave_type"], "Leave Allocation")
		self.allocations.assert_called_once_with("EMP-SELF-0001", "2026-11-26", "Study Leave")
		self.assertEqual(self.fake.db.get_value.call_args.args[1]["user_id"], "employee@example.test")
		self.assertEqual(self.balance.call_args.args[0], "EMP-SELF-0001")

	def test_get_leave_request_context_guest_denied(self):
		with (
			patch.object(frappe, "session", {"user": "Guest"}),
			patch.object(frappe, "response", {}),
			patch.object(frappe, "_", side_effect=lambda message: message),
			patch.object(frappe, "throw", side_effect=raise_permission_error),
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(self.api.get_leave_request_context)
		self.fake.db.get_value.assert_not_called()

	def test_guest_cannot_call_context_internally(self):
		self.fake.session.user = "Guest"
		with self.assertRaises(frappe.PermissionError):
			self.api.get_leave_request_context()
		self.fake.db.get_value.assert_not_called()

	def test_http_post_is_rejected_before_reading_data(self):
		from types import SimpleNamespace

		from frappe.handler import is_valid_http_method

		with (
			patch.object(frappe.local, "request", SimpleNamespace(method="POST"), create=True),
			patch.object(frappe, "throw_permission_error", side_effect=frappe.PermissionError),
		):
			with self.assertRaises(frappe.PermissionError):
				is_valid_http_method(self.api.get_leave_request_context)
		self.fake.db.get_value.assert_not_called()
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[self.api.get_leave_request_context], ["GET"]
		)

	def test_invalid_leave_type_is_rejected_before_lookup(self):
		from types import SimpleNamespace

		with (
			patch.object(frappe.local, "request", SimpleNamespace(method="GET"), create=True),
			patch.object(frappe, "_", side_effect=lambda message, *args, **kwargs: message),
		):
			for value in ("", "x" * 141, {"name": "Annual Leave"}, ["Annual Leave"]):
				with self.subTest(value=value), self.assertRaises(frappe.FrappeTypeError):
					self.api.get_leave_request_context(leave_type=value)
		self.fake.db.get_value.assert_not_called()

	def test_http_get_accepts_the_typed_query(self):
		from types import SimpleNamespace

		from frappe.handler import is_valid_http_method

		with patch.object(frappe.local, "request", SimpleNamespace(method="GET"), create=True):
			is_valid_http_method(self.api.get_leave_request_context)
			result = self.api.get_leave_request_context(leave_type="Annual Leave")
		self.assertEqual(result["leave_balance"], 8.5)
