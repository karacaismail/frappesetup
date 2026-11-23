"""Install the Press fields used for priced Site Plan revisions."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from press_tr.pricing import NOTICE_TYPE


def sync_pricing_fields():
	create_custom_fields(
		{
			"Site Plan": [
				{
					"fieldname": "price_try",
					"fieldtype": "Currency",
					"label": "Price (TRY)",
					"options": "TRY",
					"precision": "2",
					"insert_after": "price_usd",
					"description": "Plan price in Turkish lira.",
				},
				{
					"fieldname": "price_effective_date",
					"fieldtype": "Date",
					"label": "Price Start Date",
					"read_only": 1,
					"insert_after": "price_try",
					"description": "First date when the revised price can be enabled.",
				},
			],
		}
	)
	field = frappe.get_meta("Press Notification").get_field("type")
	if NOTICE_TYPE not in field.options.splitlines():
		make_property_setter(
			"Press Notification", "type", "options", f"{field.options.rstrip()}\n{NOTICE_TYPE}", "Text"
		)
