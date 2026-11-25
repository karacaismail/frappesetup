"""HTTP entry points of large file jobs (G-156, D-9)."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from platform_core.api import model
from platform_core.model_gateway import large_file, policy

ENDPOINTS = ("create_file_job", "file_job_status", "start_file_job", "retry_file_chunk")


class FileJobHttpTests(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch.object(frappe.local, "request", object(), create=True))
		self.enterContext(patch.object(frappe.local, "response", frappe._dict(), create=True))
		self.enterContext(patch.object(frappe.local, "db", Mock(), create=True))
		self.enterContext(patch.object(model.policy, "require_session"))
		self.enterContext(
			patch.object(frappe.local, "session", frappe._dict(user="owner@example.test"), create=True)
		)

	def test_every_file_job_command_is_a_post_only_endpoint(self):
		for name in ENDPOINTS:
			with self.subTest(endpoint=name):
				endpoint = getattr(model, name)
				self.assertIn(endpoint, frappe.whitelisted)
				self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[endpoint], ["POST"])
				self.assertNotIn(endpoint, frappe.guest_methods)

	def test_endpoints_call_the_large_file_service(self):
		with patch.object(model.api, "create_file_job", return_value="job-1") as create:
			self.assertEqual(model.create_file_job("route", "file", "Summarize.", 64), {"name": "job-1"})
		create.assert_called_once_with("route", "file", "Summarize.", 64)
		status = {"name": "job-1", "status": "planned"}
		with patch.object(model.api, "file_job_status", return_value=status):
			self.assertEqual(model.file_job_status("job-1"), status)
		with patch.object(model.api, "start_file_job") as start:
			self.assertEqual(model.start_file_job("job-1"), {"name": "job-1", "status": "queued"})
		start.assert_called_once_with("job-1")
		with patch.object(model.api, "retry_file_chunk") as retry:
			self.assertEqual(
				model.retry_file_chunk("job-1", 2), {"name": "job-1", "chunk_index": 2, "status": "queued"}
			)
		retry.assert_called_once_with("job-1", 2)

	def test_guest_is_rejected_before_the_service_runs(self):
		denial = policy.Denied(401, "authentication_required")
		for name, arguments in (
			("create_file_job", ("route", "file", "Summarize.")),
			("file_job_status", ("job-1",)),
			("start_file_job", ("job-1",)),
			("retry_file_chunk", ("job-1", 0)),
		):
			with (
				self.subTest(endpoint=name),
				patch.object(model.policy, "require_session", side_effect=denial),
				patch.object(model.api, name) as service,
			):
				self.assertEqual(getattr(model, name)(*arguments), {"error": "authentication_required"})
				self.assertEqual(frappe.local.response.http_status_code, 401)
				service.assert_not_called()

	def test_another_user_cannot_read_start_or_retry_the_job(self):
		job = SimpleNamespace(name="job-1", owner="owner@example.test", status="planned", chunks=[])
		frappe.local.session.user = "other@example.test"
		with (
			patch.object(large_file, "_job", return_value=job),
			patch.object(large_file.policy, "require_user"),
			patch.object(frappe, "get_roles", return_value=["Employee"]),
			patch.object(frappe, "enqueue") as enqueue,
		):
			for name, arguments in (
				("file_job_status", ("job-1",)),
				("start_file_job", ("job-1",)),
				("retry_file_chunk", ("job-1", 0)),
			):
				with self.subTest(endpoint=name), self.assertRaises(frappe.PermissionError):
					getattr(model, name)(*arguments)
		enqueue.assert_not_called()

	def test_service_denial_keeps_its_status_and_code(self):
		with patch.object(model.api, "start_file_job", side_effect=policy.Denied(409, "job_not_planned")):
			self.assertEqual(model.start_file_job("job-1"), {"error": "job_not_planned"})
		self.assertEqual(frappe.local.response.http_status_code, 409)
		frappe.db.rollback.assert_called_once_with(chain=True)
