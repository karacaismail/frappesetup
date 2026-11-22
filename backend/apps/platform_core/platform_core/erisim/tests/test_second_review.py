"""Finding of the second independent review that is not about reports: the stale reader.

The report findings of that review are covered by `test_report_rules.py`.
"""

import json

import frappe
from frappe.tests.test_api import make_request

from platform_core.erisim import rules
from platform_core.erisim.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	REST,
	ROLE_EMPLOYEE,
	RULE_DOCTYPE,
	ErisimTestCase,
)


class TestStaleReader(ErisimTestCase):
	"""Finding 3: a request that read the old rules must not hand them to later requests."""

	OWN_RULE = "Calisan kendi kaydi"

	def raw_request(self, client, method: str, path: str, body=None):
		"""Send a request without committing or rolling back this test's own connection."""
		kwargs = {"path": path, "method": method, "headers": {"Accept": "application/json"}}
		if body is not None:
			kwargs["headers"]["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		return make_request(client.open, args=(), kwargs=kwargs, site=self.site)

	def restore(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		rule = frappe.get_doc(RULE_DOCTYPE, self.rules[self.OWN_RULE])
		rule.update({"is_active": 1})
		rule.save()
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def test_reader_with_an_old_snapshot_cannot_restore_a_removed_permission(self):
		admin = self.login("er.admin@example.test")
		employee = self.login(EMPLOYEE_1)
		own = self.records[EMPLOYEE_1]
		self.addCleanup(self.restore)
		frappe.db.commit()  # nosemgrep: start a fresh snapshot for the slow reader

		# The slow reader opens its snapshot while the rule still grants access.
		self.assertTrue(any(rule["role"] == ROLE_EMPLOYEE for rule in rules.rules_for(DOCTYPE)))

		# Another request removes the permission and commits.
		path = f"{REST}{RULE_DOCTYPE}/{self.rules[self.OWN_RULE]}"
		changed = self.raw_request(admin, "PUT", path, {"is_active": 0})
		self.assertEqual(changed.status_code, 200, changed.get_data(as_text=True)[:300])

		# The slow reader looks the rules up again from its old snapshot, as a cache miss would.
		frappe.local.cache = {}
		if getattr(frappe.local, "request_cache", None) is not None:
			frappe.local.request_cache.clear()
		rules.rules_for(DOCTYPE)

		# The next request must already be denied.
		response = self.raw_request(employee, "GET", f"{REST}{DOCTYPE}/{own}")
		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
