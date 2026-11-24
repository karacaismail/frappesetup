#!/bin/sh
set -eu

# Run from the repository root against a disposable Press Compose project.
project="${PRESS_TEST_COMPOSE_PROJECT:?Set the disposable Press Compose project name}"
export PRESS_TEST_PANEL_URL="${PRESS_TEST_PANEL_URL:?Set platform_panel_url for the test site}"
export PRESS_TEST_PORT="${PRESS_TEST_PORT:-3363}"
export PRESS_TEST_MEASURE_ANONYMIZATION="${PRESS_TEST_MEASURE_ANONYMIZATION:-0}"
case "${FS_COLIMA_PROFILE:-factory}" in
	factory) press_context=colima-factory ;;
	default) press_context=colima ;;
	*) printf '%s\n' 'FS_COLIMA_PROFILE must be factory or default.' >&2; exit 2 ;;
esac
container="$(docker --context "$press_context" ps -q \
    --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=web" \
    --filter "label=com.docker.compose.oneoff=False")"
if [ -z "$container" ] || [ "$(printf '%s\n' "$container" | wc -l)" -ne 1 ]; then
    printf 'Expected exactly one running web service in Compose project %s.\n' "$project" >&2
    exit 2
fi
repo_app=backend/apps/press_tr
container_app=/home/frappe/benches/source/press_tr

python3.14 -B -m unittest discover -s backend/dev/press

docker --context "$press_context" cp "$repo_app/press_tr/." "$container:$container_app/press_tr/"
docker --context "$press_context" cp "$repo_app/tests/." "$container:$container_app/tests/"
docker --context "$press_context" cp backend/contracts/press_tr.openapi.yaml "$container:$container_app/tests/"
docker --context "$press_context" exec -i -e PRESS_TEST_PORT -e PRESS_TEST_PANEL_URL \
    -e PRESS_TEST_MEASURE_ANONYMIZATION "$container" bash -s <<'BENCH'
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

fixture_state="$(mktemp /dev/shm/press-deletion-fixture.XXXXXX)"
fixture_script=/home/frappe/benches/source/press_tr/tests/deletion_fixture.py
test_server=
cleanup() {
    if [ -n "$test_server" ]; then
        kill "$test_server" 2>/dev/null || true
        wait "$test_server" 2>/dev/null || true
    fi
    "$bench_root/env/bin/python" "$fixture_script" restore "$fixture_state"
}
trap cleanup EXIT
"$bench_root/env/bin/python" "$fixture_script" setup "$fixture_state"

"$bench_root/env/bin/python" -m frappe.utils.bench_helper frappe serve \
    --port "$PRESS_TEST_PORT" --noreload > "$bench_root/logs/press-tr-tests.log" 2>&1 &
test_server=$!
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

export PANE_PORT="$((PRESS_TEST_PORT - 3))"
tests=/home/frappe/benches/source/press_tr/tests
if [ "$PRESS_TEST_MEASURE_ANONYMIZATION" = 1 ]; then
    "$bench_root/env/bin/python" -B "$tests/measure_anonymization.py"
else
    "$bench_root/env/bin/python" -B -m unittest discover -s "$tests"
fi
BENCH
