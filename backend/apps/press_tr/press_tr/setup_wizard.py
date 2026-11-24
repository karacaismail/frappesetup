"""G-7: start the Agent "Complete Setup Wizard" job for a new site.

Press defines ``Agent.complete_setup_wizard`` but nothing calls it (Press v0.154.1, commit
``7a4384d5``). The Agent runs Frappe ``setup_complete`` with this payload.

When the hook runs: Press sets a new site Active with ``frappe.db.set_value``, which skips
``on_update``. Press's own five-minute scheduler event ``sync_sites_setup_wizard_complete_status``
then saves each Active site whose wizard is not done. That save runs this hook, so the job starts
a few minutes after the site becomes Active.

Rules:

- One attempt per site. A failed job is not retried; the Agent Job record shows the failure.
- Product trial, standby and Administrator team sites are left to Press.
- Only sites whose apps need no extra wizard data get the job. ERPNext-family apps need company
  data; the product owner decides whether to support them.
- Every payload value comes from the site owner's records. Nothing is guessed. When a value is
  missing, no job starts and one Error Log row records why.
"""

import frappe

JOB_TYPE = "Complete Setup Wizard"
SKIP_TITLE = "press_tr setup wizard skipped"
# Apps whose setup wizard stages run with the payload below and need nothing more.
WIZARD_READY_APPS = frozenset({"frappe"})


def start_setup_wizard(doc, method=None):
	if doc.status != "Active" or doc.setup_wizard_complete:
		return
	if doc.standby_for or doc.standby_for_product:
		return
	if {row.app for row in doc.apps or []} - WIZARD_READY_APPS:
		return
	if frappe.db.exists("Product Trial Request", {"site": doc.name}):
		return
	team = frappe.db.get_value("Team", doc.team, ["user", "country", "currency", "account_request"], as_dict=True)
	if not team or team.user == "Administrator":
		return

	# Lock the site row, so two saves at the same time cannot both start a job.
	frappe.db.get_value("Site", doc.name, "name", for_update=True)
	if frappe.db.exists("Agent Job", {"job_type": JOB_TYPE, "site": doc.name}):
		return

	payload = _owner_payload(doc, team)
	if not payload:
		if not frappe.db.exists("Error Log", {"method": SKIP_TITLE, "reference_name": doc.name}):
			frappe.log_error(
				title=SKIP_TITLE,
				message="Site owner data is incomplete; the setup wizard job was not started.",
				reference_doctype="Site",
				reference_name=doc.name,
			)
		return

	from press.agent import Agent

	Agent(doc.server, server_type="Server").complete_setup_wizard(doc, payload)


def _owner_payload(doc, team):
	if not team.user:
		return None
	user = frappe.db.get_value("User", team.user, ["full_name", "email", "language"], as_dict=True)
	if not user:
		return None
	# Frappe setup_complete looks up the Language by its name, not by its code.
	language = None
	if user.language:
		row = frappe.db.get_value("Language", user.language, ["language_name"], as_dict=True)
		language = row.language_name if row else None

	payload = {
		"language": language,
		"lang": language,
		"country": team.country,
		"timezone": _timezone(doc, team),
		"currency": team.currency,
		"full_name": user.full_name,
		"email": user.email,
	}
	if not all(payload.values()):
		return None
	return payload


def _timezone(doc, team):
	# Dashboard sites have no Account Request of their own; the team keeps the signup request.
	for request_name in (doc.account_request, team.account_request):
		if not request_name:
			continue
		request = frappe.db.get_value("Account Request", request_name, ["geo_location"], as_dict=True)
		geo = frappe.parse_json(request.geo_location) if request and request.geo_location else None
		if geo and geo.get("timezone"):
			return geo["timezone"]
	# A country with exactly one time zone gives an exact answer. More than one is a guess.
	if team.country:
		country = frappe.db.get_value("Country", team.country, ["time_zones"], as_dict=True)
		zones = [zone for zone in (country.time_zones or "").split("\n") if zone.strip()] if country else []
		if len(zones) == 1:
			return zones[0].strip()
	return None
