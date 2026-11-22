"""Check the route target's database-level uniqueness rule."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.model_gateway.doctype.plt_ai_route_target import plt_ai_route_target


class TestRouteTargetIndexHook(unittest.TestCase):
	def test_upgrade_patch_runs_after_the_legacy_target_migration(self):
		patches = (Path(__file__).resolve().parents[2] / "patches.txt").read_text(encoding="utf-8")
		post_sync = patches.split("[post_model_sync]", 1)[1].splitlines()
		self.assertGreater(
			post_sync.index("platform_core.patches.ensure_route_target_unique"),
			post_sync.index("platform_core.patches.migrate_route_targets"),
		)
		from platform_core.patches import ensure_route_target_unique

		with patch.object(plt_ai_route_target, "on_doctype_update") as ensure:
			ensure_route_target_unique.execute()
		ensure.assert_called_once_with()

	def test_hook_reuses_the_equivalent_index_restored_from_another_database(self):
		db = Mock(db_type="mariadb", cur_db_name="restored_tenant")
		db.sql.return_value = [
			("unique_route_target_old_db", position, field, None)
			for position, field in reversed(list(enumerate(("parent", "model", "api"), start=1)))
		]
		with patch.object(frappe.local, "db", db, create=True):
			plt_ai_route_target.on_doctype_update()
		db.add_unique.assert_not_called()

	def test_hook_installs_parent_model_api_constraint_per_database(self):
		names = []
		for database in ("tenant_one", "tenant_two", "tenant_one"):
			db = Mock(cur_db_name=database)
			with patch.object(frappe.local, "db", db, create=True):
				plt_ai_route_target.on_doctype_update()
			args, kwargs = db.add_unique.call_args
			self.assertEqual(args, ("PLT AI Route Target", ["parent", "model", "api"]))
			names.append(kwargs["constraint_name"])
		self.assertRegex(names[0], r"^[a-z0-9_]{1,64}$")
		self.assertNotEqual(names[0], names[1])
		self.assertEqual(names[0], names[2])

	def test_index_failure_surfaces_without_writing_target_rows(self):
		db = Mock(cur_db_name="tenant_one")
		db.add_unique.side_effect = RuntimeError("Duplicate existing route target")
		with patch.object(frappe.local, "db", db, create=True):
			with self.assertRaisesRegex(RuntimeError, "Duplicate existing route target"):
				plt_ai_route_target.on_doctype_update()
		self.assertEqual(len(db.mock_calls), 1)


class TestRouteTargetUnique(IntegrationTestCase):
	def test_database_rejects_only_the_repeated_pair_in_the_same_route(self):
		parent, model, api = (str(uuid4()) for _sample_index in range(3))

		def insert(route, selected_model, selected_api):
			frappe.get_doc(
				{
					"doctype": "PLT AI Route Target",
					"name": uuid4().hex,
					"parent": route,
					"parenttype": "PLT AI Route",
					"parentfield": "targets",
					"model": selected_model,
					"api": selected_api,
				}
			).db_insert()

		insert(parent, model, api)
		insert(str(uuid4()), model, api)
		insert(parent, str(uuid4()), api)
		insert(parent, model, str(uuid4()))
		with self.assertRaises(frappe.UniqueValidationError):
			insert(parent, model, api)
