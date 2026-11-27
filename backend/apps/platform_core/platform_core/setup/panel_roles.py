"""Setup step of the panel roles and their Role Profiles (G-62, G-168, G-169, G-170, AJA-899).

The roles and profiles are not fixtures. Frappe 16.56.0 loads every file of `fixtures/` on each
migrate and rewrites the record with `force=True`. A Role Profile write runs `on_update`, which
locks the profile and queues a job. Without a worker the lock stays and the next migrate fails
with "DocumentLockedError" (AJA-857).

This step reads the two files next to it, the only source of these records:

- `role.json`: the five roles. Only "Platform Operator" has desk access.
- `role_profile.json`: the four panel profiles. Each profile holds only its own role.

A record that exists is left alone: no write, no lock, no job. A System Manager may change a
role on the site, and the next migrate keeps that change. A missing record is inserted.

The profile insert borrows the install flag of Frappe. `RoleProfile.on_update` passes
`now=frappe.flags.in_install` to `queue_action`, so the job runs at once instead of in the queue.
The job removes the lock it took. A new profile has no holders, so the job has nothing to update.
"""

import json
from pathlib import Path

import frappe

ROLE_FILE = Path(__file__).with_name("role.json")
PROFILE_FILE = Path(__file__).with_name("role_profile.json")


def load_roles() -> list[dict]:
	return json.loads(ROLE_FILE.read_text(encoding="utf-8"))


def load_profiles() -> list[dict]:
	return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def ensure() -> None:
	"""Inserts every missing panel role, then every missing profile. Runs after install and migrate."""
	for record in load_roles():
		if not frappe.db.exists("Role", record["name"]):
			frappe.get_doc(
				doctype="Role",
				role_name=record["role_name"],
				desk_access=record.get("desk_access", 0),
			).insert(ignore_permissions=True)
	ensure_profiles(load_profiles())


def ensure_profiles(records: list[dict], app: str = "platform_core") -> None:
	"""Inserts every missing Role Profile of `records` and leaves an existing one alone.

	Other apps call this step through `frappe.get_attr`, for example `hrms_tr.role_profiles`.
	"""
	for record in records:
		if not frappe.db.exists("Role Profile", record["name"]):
			insert_profile_now(record, app)


def insert_profile_now(record: dict, app: str = "platform_core") -> None:
	doc = frappe.get_doc(
		{
			"doctype": "Role Profile",
			"role_profile": record["role_profile"],
			"roles": [{"role": row["role"]} for row in record.get("roles", [])],
		}
	)
	flags = frappe.local.flags
	before = flags.in_install
	if not before:
		flags.in_install = app
	try:
		doc.insert(ignore_permissions=True)
	finally:
		flags.in_install = before
