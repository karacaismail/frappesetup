"""G-7: start the Agent "Complete Setup Wizard" job for a new site.

Press defines ``Agent.complete_setup_wizard`` but nothing calls it (Press v0.154.1, commit
``7a4384d5``). press_tr starts the job once, when the site becomes Active. The Agent runs
``frappe.desk.page.setup_wizard.setup_wizard.setup_complete`` with this payload.

Product trial and standby sites are left to Press: Press prefills their wizard itself.
Every payload value comes from the site owner's records; nothing is guessed.
"""

import frappe

JOB_TYPE = "Complete Setup Wizard"


def start_setup_wizard(doc, method=None):
	if doc.status != "Active" or doc.setup_wizard_complete:
		return
	if doc.standby_for or doc.standby_for_product:
		return
	if frappe.db.exists("Product Trial Request", {"site": doc.name}):
		return
	# One job per site: a later save must not start the wizard again.
	if frappe.db.exists("Agent Job", {"job_type": JOB_TYPE, "site": doc.name}):
		return

	payload = _owner_payload(doc)
	if not payload:
		frappe.log_error(
			title="press_tr setup wizard skipped",
			message="Site owner data is incomplete; the setup wizard job was not started.",
			reference_doctype="Site",
			reference_name=doc.name,
		)
		return

	from press.agent import Agent

	Agent(doc.server, server_type="Server").complete_setup_wizard(doc, payload)


def _owner_payload(doc):
	team = frappe.db.get_value("Team", doc.team, ["user", "country", "currency"], as_dict=True)
	if not team or not team.user:
		return None
	user = frappe.db.get_value("User", team.user, ["full_name", "email", "language"], as_dict=True)
	request = None
	if doc.account_request:
		request = frappe.db.get_value("Account Request", doc.account_request, ["geo_location"], as_dict=True)
	geo = frappe.parse_json(request.geo_location) if request and request.geo_location else {}

	payload = {
		"language": user.language if user else None,
		"country": team.country,
		"timezone": (geo or {}).get("timezone"),
		"currency": team.currency,
		"full_name": user.full_name if user else None,
		"email": user.email if user else None,
	}
	if not all(payload.values()):
		return None
	return payload
