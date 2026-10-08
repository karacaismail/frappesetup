import frappe
from erpnext.accounts import utils

frappe.whitelist = lambda *a, **k: (lambda f: f)
utils.get_balance_on = lambda *a, **k: 0
