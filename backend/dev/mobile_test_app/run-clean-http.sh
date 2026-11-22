#!/usr/bin/env bash
set -euo pipefail
run_label="${1:?Choose a new test run label}"
[[ "$run_label" =~ ^[a-z0-9-]+$ ]] || exit 2
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"
: "${PANE_PORT:?Set PANE_PORT to your Pane port base}"
[[ "$PANE_PORT" =~ ^[1-9][0-9]{3,4}$ ]] && (( PANE_PORT <= 65526 )) || exit 2
export PANE_PORT FS_TENANT_WEB_PORT="$((PANE_PORT + 1))" FS_TENANT_SOCKET_PORT="$((PANE_PORT + 2))"
review="${PANE_SCRATCH_DIR:-$repo_root/.pane/scratch}/mobile-review"
mkdir -p "$review"
test_env="$review/$run_label.env"
project="fs-mobile-http-$run_label-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
web="$project-web"
umask 077
if [ -e "$test_env" ]; then
    echo "The test run label already exists." >&2
    exit 2
fi
python3 - <<'PY' > "$test_env"
import secrets
print("MARIADB_ROOT_PASSWORD="+secrets.token_hex(24))
print("ADMIN_PASSWORD="+secrets.token_hex(24))
PY
dock=(docker --context colima-factory)
compose=("${dock[@]}" compose -p "$project" --env-file "$test_env" -f backend/dev/compose.tenant.yaml)
cleanup() {
    "${dock[@]}" cp "$web:/home/frappe/frappe-bench/logs/mobile-http-review.log" "$review/$run_label-server.log" 2>/dev/null || true
    "${dock[@]}" stop -t 2 "$web" >/dev/null 2>&1 || true
    "${dock[@]}" rm "$web" >/dev/null 2>&1 || true
    "${compose[@]}" down >> "$review/$run_label-stop.log" 2>&1 || true
}
trap cleanup EXIT
"${compose[@]}" build tenant-web > "$review/$run_label-build.log" 2>&1
"${compose[@]}" up --no-build --wait -d tenant-db tenant-redis > "$review/$run_label-start.log" 2>&1
"${compose[@]}" run --no-deps -d --name "$web" tenant-web sleep infinity >> "$review/$run_label-start.log" 2>&1
"${dock[@]}" exec "$web" env/bin/python /workspace/dev/bootstrap.py test-mobile.localhost --app platform_core > "$review/$run_label-bootstrap.log" 2>&1
"${dock[@]}" exec "$web" cp -a /workspace/dev/mobile_test_app apps/
"${dock[@]}" exec "$web" sh -c 'uv pip install --offline --python env/bin/python --no-deps -e apps/mobile_test_app && printf "\nmobile_test_app\n" >> sites/apps.txt'
"${dock[@]}" exec "$web" bench --site test-mobile.localhost install-app mobile_test_app > "$review/$run_label-install.log" 2>&1
"${dock[@]}" exec "$web" bench --site test-mobile.localhost migrate > "$review/$run_label-migrate.log" 2>&1
"${dock[@]}" exec -i "$web" env/bin/python - > "$review/$run_label-empty.log" <<'PY'
import os
import json
import secrets
from pathlib import Path
path = Path("sites/test-mobile.localhost/site_config.json")
conf = json.loads(path.read_text())
conf["mobile_cursor_key"] = secrets.token_hex(32)
path.write_text(json.dumps(conf))
os.chdir("sites")
import frappe
frappe.init("test-mobile.localhost")
frappe.connect()
for table in ("PLT Mobile Installation", "PLT Mobile Operation", "Mobile Fixture Record"):
    count = frappe.db.count(table)
    print(f"{table}: {count}")
    assert count == 0
frappe.destroy()
PY
"${dock[@]}" exec -d "$web" sh -c 'bench --site test-mobile.localhost serve --port "$KIRACI_WEB_PORT" --noreload > logs/mobile-http-review.log 2>&1'
"${dock[@]}" exec "$web" env/bin/python -c 'import os,socket,time
for _ in range(50):
    try:
        with socket.create_connection(("127.0.0.1",int(os.environ["FS_TENANT_WEB_PORT"])),0.2): break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("Mobile HTTP site did not start")'
"${dock[@]}" exec -e MOBILE_TEST_URL="http://127.0.0.1:$FS_TENANT_WEB_PORT" -e MOBILE_TEST_BEARER=fixture-first -e MOBILE_TEST_OTHER_BEARER=fixture-second -e MOBILE_TEST_FIXTURE=1 "$web" env/bin/python -m unittest discover -v -s apps/platform_core/platform_core/api -p test_mobile.py > "$review/$run_label-http.log" 2>&1
tail -7 "$review/$run_label-http.log"
"${dock[@]}" exec "$web" env/bin/python -m mobile_test_app.load_test "$FS_TENANT_WEB_PORT" > "$review/$run_label-load.log" 2>&1 || {
    cat "$review/$run_label-load.log"
    exit 1
}
cat "$review/$run_label-load.log"
