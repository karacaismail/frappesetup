#!/bin/sh
set -eu

# Run from the repository root against the disposable fs-press-tr environment.
export PRESS_TEST_PANEL_URL="${PRESS_TEST_PANEL_URL:?Set platform_panel_url for the test site}"
export PRESS_TEST_PORT="${PRESS_TEST_PORT:-3363}"
container=fs-press-tr-web-1
repo_app=backend/apps/press_tr
container_app=/home/frappe/benches/source/press_tr

docker --context colima-factory cp "$repo_app/press_tr/." "$container:$container_app/press_tr/"
docker --context colima-factory cp "$repo_app/tests/." "$container:$container_app/tests/"
docker --context colima-factory cp backend/dev/press/forwarded-client.conf "$container:$container_app/tests/"
docker --context colima-factory exec -i -e PRESS_TEST_PORT -e PRESS_TEST_PANEL_URL "$container" bash -s <<'BENCH'
set -euo pipefail
bench_root=/home/frappe/benches/frappe-bench
cd "$bench_root/sites"
"$bench_root/env/bin/python" - <<'PY'
import frappe

frappe.init("press.localhost")
frappe.connect()
email = "desk-user@example.test"
if not frappe.db.exists("User", email):
    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": "Desk test",
        "send_welcome_email": 0,
        "roles": [{"role": "System Manager"}],
    })
    user.insert(ignore_permissions=True)
assert frappe.db.get_value("User", email, "user_type") == "System User"
frappe.db.commit()
PY

"$bench_root/env/bin/python" -m frappe.utils.bench_helper frappe serve \
    --port "$PRESS_TEST_PORT" --noreload > "$bench_root/logs/press-tr-tests.log" 2>&1 &
test_server=$!
trap 'kill "$test_server" 2>/dev/null || true; wait "$test_server" 2>/dev/null || true' EXIT
ready=
for _ in {1..40}; do
    if curl -fs -H 'Host: press.localhost' \
        "http://127.0.0.1:$PRESS_TEST_PORT/api/method/ping" >/dev/null; then
        ready=yes
        break
    fi
    sleep 0.25
done
if [ "$ready" != yes ]; then
    tail -20 "$bench_root/logs/press-tr-tests.log" >&2
    exit 1
fi

PANE_PORT="$((PRESS_TEST_PORT - 3))" "$bench_root/env/bin/python" -B -m unittest discover -s /home/frappe/benches/source/press_tr/tests
BENCH
