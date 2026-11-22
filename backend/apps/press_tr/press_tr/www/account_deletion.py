from frappe import _
from frappe.sessions import get_csrf_token

from press_tr.press_identity.deletion import fresh_reauthentication, human_identity

no_cache = 1


def get_context(context):
	human_identity()
	context.title = _("Delete your account", context="press_tr")
	context.deletion_csrf_token = get_csrf_token()
	context.reauthenticated = fresh_reauthentication() is not None
