"""Setup step of the HRMS TR Role Profiles (AJA-934, AJA-952).

The profiles are not fixtures. Frappe 16.56.0 loads every file of `fixtures/` on each migrate and
rewrites the record (`frappe/utils/fixtures.py`, `import_fixtures`). A Role Profile write queues a
job that locks the profile. Without a worker the lock stays, and the next migrate fails with
"DocumentLockedError" on "HRT Admin".

`role_profile.json` next to this file is the only source of the profiles. The step inserts a
missing profile and leaves an existing one alone: no write, no lock, no job. It reuses the
profile step of platform_core (AJA-857), which runs the profile job at once.

The step runs in `after_sync` on install and in `after_migrate`. Frappe runs `after_install`
before it loads the fixtures (`frappe/installer.py`, `install_app`), so the roles of
`fixtures/01_role.json` would not exist yet there.
"""

import json
from pathlib import Path

import frappe

PROFILE_FILE = Path(__file__).with_name("role_profile.json")
PROFILE_STEP = "platform_core.setup.panel_roles.ensure_profiles"


def load_profiles():
	return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def ensure():
	frappe.get_attr(PROFILE_STEP)(load_profiles(), "hrms_tr")
