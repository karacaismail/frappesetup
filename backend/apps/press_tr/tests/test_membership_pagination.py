"""Check that bulk organization removal reads and locks bounded pages."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from press_tr.api import identity
from press_tr.press_identity import anonymization


class MembershipPaginationTest(TestCase):
	def test_membership_lookup_and_team_locks_are_bounded_in_name_order(self):
		memberships = [
			frappe._dict(name=f"member-{index:03}", parent=f"team-{100 - index:03}") for index in range(101)
		]
		locked = []

		def read_memberships(doctype, filters, **options):
			self.assertEqual(doctype, "Team Member")
			self.assertEqual(options.get("limit"), 100)
			self.assertEqual(options.get("order_by"), "name asc")
			after = filters.get("name", [">", ""])[1]
			return [row for row in memberships if row.name > after][: options["limit"]]

		def lock_teams(doctype, filters, _field, **options):
			self.assertEqual(doctype, "Team")
			self.assertTrue(options["for_update"])
			names = filters["name"][1]
			self.assertLessEqual(len(names), 100)
			locked.extend(names)
			return names

		framework = Mock()
		framework.get_all.side_effect = read_memberships
		framework.db.get_values.side_effect = lock_teams
		framework.get_doc.side_effect = lambda _doctype, name, **options: SimpleNamespace(name=name)
		with (
			patch.object(identity, "frappe", framework),
			patch.object(anonymization, "frappe", framework),
			patch.object(identity, "reset_read_snapshot"),
			patch.object(identity, "remove_memberships") as remove,
		):
			identity.remove_organization_memberships("person@example.test")

		teams = [team.name for call in remove.call_args_list for team in call.args[0]]
		self.assertEqual(locked, sorted(row.parent for row in memberships))
		self.assertEqual(teams, locked)
