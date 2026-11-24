"""Install the Press fields used for priced Site Plan revisions and the invoice lira rate."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from press_tr.pricing import NOTICE_TYPE


def sync_pricing_fields():
	create_custom_fields(
		{
			"Site Plan": [
				{
					"fieldname": "price_effective_date",
					"fieldtype": "Date",
					"label": "Price Start Date",
					"read_only": 1,
					"insert_after": "price_usd",
					"description": "First date when the revised price can be enabled.",
				},
				{
					"fieldname": "price_previous_plan",
					"fieldtype": "Link",
					"label": "Previous Plan",
					"options": "Site Plan",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "price_effective_date",
				},
			],
			# G-10: set once when the invoice leaves Draft (press_tr.exchange_rates.set_invoice_rate).
			"Invoice": [
				{
					"fieldname": "try_exchange_rate",
					"fieldtype": "Float",
					"label": "Turkish Lira Rate",
					"precision": "4",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "exchange_rate",
					"description": "US dollar selling rate on the invoice day.",
				},
				{
					"fieldname": "try_exchange_rate_date",
					"fieldtype": "Date",
					"label": "Turkish Lira Rate Date",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "try_exchange_rate",
				},
				{
					"fieldname": "try_exchange_rate_source",
					"fieldtype": "Data",
					"label": "Turkish Lira Rate Source",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "try_exchange_rate_date",
				},
				{
					"fieldname": "try_total",
					"fieldtype": "Float",
					"label": "Total in Turkish Lira",
					"precision": "2",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "try_exchange_rate_source",
				},
			],
		}
	)
	field = frappe.get_meta("Press Notification").get_field("type")
	if NOTICE_TYPE not in field.options.splitlines():
		make_property_setter(
			"Press Notification", "type", "options", f"{field.options.rstrip()}\n{NOTICE_TYPE}", "Text"
		)
