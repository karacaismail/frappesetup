"""Install step of the four panel Role Profiles (G-62, G-168, G-169, G-170, AJA-857).

The profiles are not fixtures. Frappe 16.56.0 loads every file of `fixtures/` on each migrate and
rewrites the record with `force=True`. A Role Profile write runs `on_update`, which locks the
profile and queues a job. Without a worker the lock stays and the next migrate fails with
"DocumentLockedError".

This step reads `role_profile.json` next to this file, the only source of the profiles:

- A profile that exists is left alone. No write, no lock, no job.
- A missing profile is inserted with its roles.

The insert borrows the install flag of Frappe. `RoleProfile.on_update` passes
`now=frappe.flags.in_install` to `queue_action`, so the job runs at once instead of in the queue.
The job removes the lock it took. A new profile has no holders, so the job has nothing to update.
On install the flag is already set, as Frappe sets it for every app.

On install Frappe runs `after_install` before it loads the fixtures of the app. The roles of
`fixtures/role.json` are then missing, so this step loads the fixtures first. Role writes take
no lock. On migrate the fixtures are loaded before `after_migrate` and the roles exist.
"""

import json
from pathlib import Path

import frappe
from frappe.utils.fixtures import sync_fixtures

PROFILE_FILE = Path(__file__).with_name("role_profile.json")


def load_profiles() -> list[dict]:
	return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def ensure_role_profiles() -> None:
	"""Insert every missing panel profile. Called by `after_install` and `after_migrate`."""
	missing = [record for record in load_profiles() if not frappe.db.exists("Role Profile", record["name"])]
	if not missing:
		return
	roles = {row["role"] for record in missing for row in record.get("roles", [])}
	if not all(frappe.db.exists("Role", role) for role in roles):
		sync_fixtures("platform_core")
	for record in missing:
		insert_now(record)


def insert_now(record: dict) -> None:
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
		flags.in_install = "platform_core"
	try:
		doc.insert(ignore_permissions=True)
	finally:
		flags.in_install = before
