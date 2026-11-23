# Runs inside the tenant container: remote/apply pipes this file into "python -I -".
# Usage: python -I - site-settings-probe '<fixed values JSON>' <site>...
# For every site that exists it prints {"<site>": {"set": [...], "differs": [...]}}:
#   set      names of the non-empty settings (common_site_config.json counts for every site)
#   differs  fixed settings (settings.py site-fixed) that hold another value
# No value leaves the container. remote/settings.py compares the names with
# backend/deploy/settings/tenant-site.production.env.example.
# A value written as <...> is a placeholder from the list and counts as not set.
import json
import os
import re
import sys

root = os.environ.get("ATONOTA_SITES_PATH", "/home/frappe/frappe-bench/sites")
fixed = json.loads(sys.argv[2])


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


def same(value, expected):
    # The list writes "0"; site_config.json may hold 0, "0" or false. True and 1 are not 0.
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, str):
        return value == expected
    try:
        wanted = json.loads(expected)
    except ValueError:
        return False
    return type(value) is type(wanted) and value == wanted


common = read(os.path.join(root, "common_site_config.json"))
found = {}
for site in sys.argv[3:]:
    path = os.path.join(root, site, "site_config.json")
    if os.path.isfile(path):
        merged = {**common, **read(path)}
        found[site] = {
            "set": sorted(key for key, value in merged.items() if is_set(value)),
            "differs": sorted(key for key, expected in fixed.items()
                              if key in merged and is_set(merged[key]) and not same(merged[key], expected)),
        }
print(json.dumps(found, sort_keys=True))
