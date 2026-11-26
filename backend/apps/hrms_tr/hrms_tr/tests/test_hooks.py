"""Portal employees must be allowed to request their own leave defaults."""

from unittest import TestCase

from hrms_tr import hooks


class WebsiteUserAllowedMethodsTest(TestCase):
	def test_leave_request_context_is_allowed_for_website_users(self):
		self.assertIn("hrms_tr.api.get_leave_request_context", hooks.website_user_allowed_methods)

	def test_review_actions_and_home_summary_are_allowed_for_website_users(self):
		for method in (
			"hrms_tr.api.approve_leave",
			"hrms_tr.api.cancel_leave",
			"hrms_tr.api.get_leave_approver",
			"hrms_tr.api.reject_leave",
			"hrms_tr.api.get_home_summary",
		):
			with self.subTest(method=method):
				self.assertIn(method, hooks.website_user_allowed_methods)
