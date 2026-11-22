"""Regression tests for exact budget comparisons on MariaDB."""

from decimal import Decimal
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from platform_core.model_gecidi import gateway, ledger


class TestLedger(IntegrationTestCase):
	def test_budget_preserves_all_stored_decimal_places(self):
		provider = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Ledger fixture {uuid4().hex}",
				"adapter": "openai",
			}
		).insert()
		account = frappe.get_doc(
			{
				"doctype": "AI Account",
				"provider": provider.name,
				"account_name": "Exact budget fixture",
				"has_monthly_budget": 1,
				"currency": "USD",
			}
		).insert()
		frappe.db.set_value("AI Account", account.name, "monthly_budget", Decimal("100000000000.123456792"))
		for outcome, known, amount in (
			("success", 1, Decimal("100000000000.123456789")),
			("pending", 0, Decimal("0.000000001")),
		):
			name = uuid4().hex
			frappe.get_doc(
				{
					"doctype": "AI Usage Log",
					"name": name,
					"attempted_at": now_datetime(),
					"user": frappe.session.user,
					"provider": provider.name,
					"account": account.name,
					"api": "ledger-fixture",
					"model": "ledger-fixture",
					"result": outcome,
					"currency": "USD",
				}
			).db_insert()
			frappe.db.set_value(
				"AI Usage Log",
				name,
				{
					"cost_known": known,
					"cost": amount if known else 0,
					"reservation_known": int(not known),
					"reserved_cost": amount if not known else 0,
				},
			)
		locked = gateway.lock_row(
			"AI Account",
			account.name,
			("name", "has_monthly_budget", "monthly_budget", "currency"),
		)
		self.assertEqual(ledger.remaining(locked), Decimal("0.000000002"))
