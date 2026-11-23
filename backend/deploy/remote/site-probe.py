# Runs inside the tenant container: remote/apply pipes this file into "python -I -".
# Usage: python -I - site-settings-probe <site>...
# Prints {"<site>": [names of its non-empty settings]} for every site that exists. A setting of
# common_site_config.json counts for every site. No value leaves the container; remote/settings.py
# compares the names with backend/deploy/settings/tenant-site.production.env.example.
# A value written as <...> is a placeholder from the list and counts as not set.
import json
import os
import re
import sys

root = os.environ.get("ATONOTA_SITES_PATH", "/home/frappe/frappe-bench/sites")


def read(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def is_set(value):
    if value is None or value == "" or value == [] or value == {}:
        return False
    return not (isinstance(value, str) and re.fullmatch(r"<[^<>]*>", value.strip()))


common = read(os.path.join(root, "common_site_config.json"))
found = {}
for site in sys.argv[2:]:
    path = os.path.join(root, site, "site_config.json")
    if os.path.isfile(path):
        merged = {**common, **read(path)}
        found[site] = sorted(key for key, value in merged.items() if is_set(value))
print(json.dumps(found, sort_keys=True))
