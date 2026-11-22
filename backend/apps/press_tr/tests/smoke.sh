#!/bin/sh
set -eu

export PRESS_WEB_PORT="$((${PANE_PORT:?Set the Pane port base} + 3))"
export PRESS_SOCKET_PORT="$((PANE_PORT + 4))"
env_file="${PRESS_ENV_FILE:-backend/dev/press/.env.example}"
base="http://127.0.0.1:$PRESS_WEB_PORT"

response=$(curl --fail --silent --show-error --max-time 10 \
    --header 'Host: press.localhost' "$base/api/method/ping")
printf '%s\n' "$response" | python3 -c '
import json
import sys

if json.load(sys.stdin)["message"] != "pong":
    raise SystemExit("Frappe ping did not return pong")
'

apps=$(PRESS_ENV_FILE="$env_file" bash backend/dev/press/compose.sh exec -T \
    --workdir /home/frappe/benches/frappe-bench web \
    bench --site press.localhost execute frappe.get_installed_apps)
printf '%s\n' "$apps" | python3 -c '
import json
import sys

apps = json.load(sys.stdin)
for app in ("frappe", "press", "press_tr"):
    if app not in apps:
        raise SystemExit(f"Missing site application: {app}")
'
