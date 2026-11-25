"""Press-side entry point for headless tenant setup."""

from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from press.agent import Agent
from press.press.doctype.site.site import Site


TIMEZONE = "Europe/Istanbul"


class SetupSite(Site):
	def setup_wizard_args(self):
		"""Build the G-42 setup wizard values from the site's team owner."""
		team = frappe.db.get_value("Team", self.team, ["user", "billing_name"], as_dict=True)
		user = frappe.db.get_value("User", team.user, ["full_name", "email"], as_dict=True)
		company = (team.billing_name or user.full_name or self.name.split(".", 1)[0]).strip()
		year = datetime.now(ZoneInfo(TIMEZONE)).year
		return {
			"language": "tr",
			"country": "Türkiye",
			"timezone": TIMEZONE,
			"currency": "TRY",
			"company_name": company,
			"company_abbr": "".join(word[0] for word in company.split())[:5].upper(),
			"chart_of_accounts": "Turkey - Chart of Accounts",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"full_name": user.full_name,
			"email": user.email,
			"enable_telemetry": 0,
		}

	def complete_setup_wizard(self, args):
		"""Dispatch setup from the provisioning flow once Press has activated this site."""
		state = frappe.db.get_value(
			"Site", self.name, ["status", "setup_wizard_complete", "server"], for_update=True
		)
		if not state:
			return None
		status, completed, server = state
		if status != "Active" or completed:
			return None

		if frappe.db.get_value(
			"Agent Job",
			{
				"site": self.name,
				"job_type": "Complete Setup Wizard",
				"status": ("in", ("Undelivered", "Pending", "Running", "Success")),
			},
			"name",
			for_update=True,
		):
			return None

		return Agent(server).complete_setup_wizard(self, args)
