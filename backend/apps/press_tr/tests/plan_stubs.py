"""An in-memory ``frappe`` for the G-9 and G-10 plan tests.

The tests need no Frappe install. Records live in ``{doctype: {name: {field: value}}}``.
"""

import importlib
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 24)


class Rejected(Exception):
	pass


class Document(SimpleNamespace):
	def __init__(self, store, values):
		super().__init__(**values)
		self._store = store

	def get(self, field, default=None):
		return getattr(self, field, default)

	def insert(self, set_name=None, ignore_permissions=False):
		name = set_name or self.name
		self.name = name
		values = {key: value for key, value in vars(self).items() if not key.startswith("_")}
		self._store.records.setdefault(values["doctype"], {})[name] = values
		self._store.inserted.append((values["doctype"], name))
		return self

	def suspend(self, reason=None, skip_reload=False):
		self._store.suspended.append((self.name, reason))
		self._store.records["Site"][self.name]["status"] = "Suspended"


class FakeFrappe:
	"""Holds the records and builds a ``frappe`` module that reads and writes them."""

	def __init__(self, test, records=None, roles=("Administrator", "System Manager")):
		self.test = test
		self.records = records if records is not None else {}
		self.roles = list(roles)
		self.inserted = []
		self.suspended = []
		self.singles = {}
		self.today = TODAY

	def _matches(self, name, row, filters):
		for field, expected in (filters or {}).items():
			value = name if field == "name" else row.get(field)
			if isinstance(expected, (list, tuple)):
				operator, operand = expected
				if operator == "in" and value not in operand:
					return False
				if operator == "<" and not (value is not None and value < operand):
					return False
				if operator == "<=" and not (value is not None and value <= operand):
					return False
				continue
			if value != expected:
				return False
		return True

	def get_all(self, doctype, filters=None, pluck=None, **_kwargs):
		rows = self.records.get(doctype, {})
		names = sorted(name for name, row in rows.items() if self._matches(name, row, filters))
		if pluck == "name":
			return names
		return [rows[name] for name in names]

	def get_doc(self, doctype_or_values, name=None, for_update=False):
		if isinstance(doctype_or_values, dict):
			return Document(self, dict(doctype_or_values))
		row = self.records[doctype_or_values][name]
		return Document(self, {"doctype": doctype_or_values, "name": name, **row})

	def module(self):
		frappe = ModuleType("frappe")
		frappe._ = lambda message, *args, **kwargs: message
		frappe.throw = self.throw
		frappe.get_all = self.get_all
		frappe.get_doc = self.get_doc
		frappe.get_roles = lambda user=None: list(self.roles)
		frappe.only_for = self.only_for
		frappe.db = SimpleNamespace(
			exists=lambda doctype, name: name in self.records.get(doctype, {}),
			get_value=self.get_value,
			set_value=self.set_value,
			set_single_value=self.set_single_value,
			get_single_value=lambda doctype, field: self.singles.get((doctype, field)),
		)
		frappe.utils = SimpleNamespace(
			getdate=lambda value=None: value if isinstance(value, date) else self.today,
			add_days=lambda value, days: (value if isinstance(value, date) else self.today)
			+ timedelta(days=days),
		)
		frappe.PermissionError = PermissionError
		return frappe

	def throw(self, message, *args, **kwargs):
		raise Rejected(message)

	def only_for(self, role):
		if role not in self.roles:
			raise PermissionError(role)

	def get_value(self, doctype, name, field):
		row = self.records.get(doctype, {}).get(name)
		if row is None:
			return None
		if isinstance(field, (list, tuple)):
			return SimpleNamespace(**{key: row.get(key) for key in field})
		return row.get(field)

	def set_value(self, doctype, name, field, value=None, update_modified=True):
		values = field if isinstance(field, dict) else {field: value}
		self.records[doctype][name].update(values)

	def set_single_value(self, doctype, field, value):
		self.singles[(doctype, field)] = value


def load(test, fake, *modules, extra_modules=None):
	"""Import press_tr modules against the fake ``frappe`` and return them in order."""
	frappe = fake.module()
	for patcher in (
		patch.object(sys, "path", [str(APP_ROOT), *sys.path]),
		patch.dict(sys.modules, {"frappe": frappe, **(extra_modules or {})}),
	):
		patcher.start()
		test.addCleanup(patcher.stop)
	for name in modules:
		sys.modules.pop(name, None)
	return [importlib.import_module(name) for name in modules]
