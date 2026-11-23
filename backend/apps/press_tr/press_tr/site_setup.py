"""Press-side entry point for headless tenant setup."""

import frappe
from press.agent import Agent
from press.press.doctype.site.site import Site


class SetupSite(Site):
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
