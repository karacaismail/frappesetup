"""Portal employees must be allowed to request their own leave defaults."""

from unittest import TestCase

from hrms_tr import hooks


class WebsiteUserAllowedMethodsTest(TestCase):
	def test_leave_request_context_is_allowed_for_website_users(self):
		self.assertIn("hrms_tr.api.get_leave_request_context", hooks.website_user_allowed_methods)
