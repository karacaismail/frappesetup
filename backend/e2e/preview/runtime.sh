#!/bin/bash
# Run the frozen worktree in a dedicated Colima preview project.
set -euo pipefail
umask 077

suite_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
worktree="${1:?A frozen worktree is required.}"
: "${PREVIEW_DIR:?A private preview directory is required.}"
: "${PREVIEW_PROJECT:?A unique preview project is required.}"

if [[ ! "$PREVIEW_PROJECT" =~ ^fs-e2e-preview-[a-z0-9-]+$ ]] || [[ ! "${PANE_PORT:-}" =~ ^[1-9][0-9]{3,4}$ ]] || (( PANE_PORT > 65526 )); then
    printf '%s\n' 'Invalid preview project or Pane port.' >&2
    exit 2
fi
if [[ "$worktree" != "$PREVIEW_DIR/worktree" || ! -d "$worktree" ]]; then
    printf '%s\n' 'The preview runtime requires its own disposable worktree.' >&2
    exit 2
fi
export FS_COLIMA_PROFILE="${FS_COLIMA_PROFILE:-default}"
case "$FS_COLIMA_PROFILE" in
    default) docker_context=colima ;;
    factory) docker_context=colima-factory ;;
    *) printf '%s\n' 'FS_COLIMA_PROFILE must be default or factory.' >&2; exit 2 ;;
esac
case "${E2E_BROWSER_RUNTIME:-host}" in
    host|container) ;;
    *) printf '%s\n' 'E2E_BROWSER_RUNTIME must be host or container.' >&2; exit 2 ;;
esac

docker_preview() { docker --context "$docker_context" "$@"; }
tenant_image=frappe/erpnext:v16.55.0
if ! available="$(docker_preview run --rm --pull never --network none --read-only --entrypoint cat \
    "$tenant_image" /proc/meminfo | awk '$1 == "MemAvailable:" { print int($2 / 1048576) }')"; then
    printf '%s\n' 'Cannot measure Colima memory through its Docker context and local tenant image.' >&2
    exit 1
fi
if [[ ! "$available" =~ ^[0-9]+$ ]] || (( available < 3 )); then
    printf '%s\n' 'The preview requires at least 3 GiB of available memory in the selected Colima profile.' >&2
    exit 1
fi
printf 'Colima available memory: %s GiB\n' "$available"

dev_dir="$worktree/backend/dev"
identity_dir="$worktree/backend/identity"
tenant="$PREVIEW_PROJECT-tenant-web-1"
press="$PREVIEW_PROJECT-web-1"
sync="$PREVIEW_PROJECT-identity"
sync_host=event-sink.localhost
provider="$PREVIEW_PROJECT-provider"
network="${PREVIEW_PROJECT}_default"
builder="$PREVIEW_PROJECT-builder"
sidecar_label=com.frappesetup.preview
browser="$PREVIEW_PROJECT-browser"
export FS_TENANT_WEB_PORT="$((PANE_PORT + 1))"
export FS_TENANT_SOCKET_PORT="$((PANE_PORT + 2))"
export PTR_WEB_PORT="$((PANE_PORT + 3))"
export PTR_SOCKET_PORT="$((PANE_PORT + 4))"
sync_port="$((PANE_PORT + 5))"
export MAILPIT_UI_PORT="$((PANE_PORT + 6))"
provider_port="$((PANE_PORT + 7))"
export KC_PORT="$PANE_PORT"
export KC_PUBLIC_URL="http://identity.localhost:$KC_PORT"
export ATONOTA_SITE_TENANT1_URL="http://tenant1.localhost:$FS_TENANT_WEB_PORT"
export ATONOTA_PRESS_URL="http://press.localhost:$PTR_WEB_PORT"
export IDENTITY_SYNC_EVENTS_URL="http://$sync_host:$sync_port/v1/events"
export DEV_ENV_FILE="$PREVIEW_DIR/tenant.env"
keycloak_env="$PREVIEW_DIR/keycloak.env"
press_env="$PREVIEW_DIR/press.env"
sync_env="$PREVIEW_DIR/sync.env"
tunnel_state="$PREVIEW_DIR/tunnel"
docker_config="$PREVIEW_DIR/docker-config"
for port in "$KC_PORT" "$FS_TENANT_WEB_PORT" "$FS_TENANT_SOCKET_PORT" "$PTR_WEB_PORT" "$PTR_SOCKET_PORT" "$sync_port" "$MAILPIT_UI_PORT" "$provider_port"; do
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
        printf 'The preview port is already in use: %s\n' "$port" >&2
        exit 1
    fi
done
if [[ -n "$(docker_preview ps -aq --filter "label=com.docker.compose.project=$PREVIEW_PROJECT")" ]] \
    || [[ -n "$(docker_preview volume ls -q --filter "label=com.docker.compose.project=$PREVIEW_PROJECT")" ]]; then
    printf '%s\n' 'The preview project already owns Docker resources.' >&2
    exit 1
fi
for image in "$PREVIEW_PROJECT-keycloak" "$PREVIEW_PROJECT-press"; do
    if docker_preview image inspect "$image" >/dev/null 2>&1; then
        printf '%s\n' 'A preview image tag already exists.' >&2
        exit 1
    fi
done
compose=(docker --context "$docker_context" compose --project-name "$PREVIEW_PROJECT"
    --env-file "$DEV_ENV_FILE" --env-file "$keycloak_env" --env-file "$press_env"
    -f "$PREVIEW_DIR/compose.yaml")

cleanup() {
    result=$?
    trap - EXIT
    set +e
    if [[ -f "$PREVIEW_DIR/compose.yaml" ]]; then
        for container in "$browser" "$sync" "$provider"; do
            if [[ "$(docker_preview container inspect --format '{{index .Config.Labels "com.frappesetup.preview"}}' "$container" 2>/dev/null)" == "$PREVIEW_PROJECT" ]]; then
                if [[ "$container" == "$sync" ]]; then
                    docker_preview exec -i "$sync" /home/frappe/frappe-bench/env/bin/python - \
                        > "$PREVIEW_DIR/identity-diagnostics.log" 2>> "$PREVIEW_DIR/cleanup.log" <<'PYTHON'
import os
import re
import sqlite3

path = os.environ["IDENTITY_SYNC_DB"]
with sqlite3.connect("file:" + path + "?mode=ro", uri=True) as database:
    for (error,) in database.execute("SELECT error FROM dead_letters ORDER BY last_failed_at DESC LIMIT 20"):
        for step in error.split("; "):
            operation = re.match(r"^(?:keycloak|press|tenant)\.[a-z_]+", step)
            status = re.search(r": (HTTP [1-5][0-9]{2}(?: [A-Za-z_][A-Za-z0-9_]{0,47})?)$", step)
            print(operation[0] if operation else "unidentified_step", status[1] if status else "no_http_status")
PYTHON
                fi
                docker_preview rm -f "$container" >> "$PREVIEW_DIR/cleanup.log" 2>&1 || cleanup_failed=1
            fi
        done
        "${compose[@]}" down --volumes --timeout 4 >> "$PREVIEW_DIR/cleanup.log" 2>&1 || cleanup_failed=1
        for image in "$PREVIEW_PROJECT-keycloak" "$PREVIEW_PROJECT-press"; do
            if docker_preview image inspect "$image" >/dev/null 2>&1; then
                docker_preview image rm "$image" >> "$PREVIEW_DIR/cleanup.log" 2>&1 || cleanup_failed=1
            fi
        done
    fi
    if [[ -d "$docker_config" ]] && docker_preview buildx inspect "$builder" >/dev/null 2>&1; then
        docker_preview buildx rm "$builder" >> "$PREVIEW_DIR/cleanup.log" 2>&1 || cleanup_failed=1
    fi
    if [[ -d "$tunnel_state" ]]; then
        PANE_SCRATCH_DIR="$tunnel_state" "$dev_dir/bin/tunnel" close >> "$PREVIEW_DIR/cleanup.log" 2>&1 || cleanup_failed=1
    fi
    rm -f -- "$DEV_ENV_FILE" "$keycloak_env" "$press_env" "$sync_env" "$PREVIEW_DIR/fixtures.json"
    rm -rf -- "$PREVIEW_DIR/playwright-output" "$tunnel_state" "$docker_config" "$PREVIEW_DIR/session-tls"
    if [[ "${cleanup_failed:-}" ]]; then
        printf '%s\n' "Preview cleanup failed. See $PREVIEW_DIR/cleanup.log." >&2
        if (( result == 0 )); then result=1; fi
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Public preview build dependencies need no credentials. Recreate the local
# context in scratch so the user's credential helper and settings stay intact.
docker_endpoint="$(docker context inspect "$docker_context" --format '{{.Endpoints.docker.Host}}')"
if [[ "$docker_endpoint" != unix://* ]]; then
    printf '%s\n' 'The preview requires the local Colima socket.' >&2
    exit 2
fi
docker_plugins="$(docker_preview info --format '{{range .ClientInfo.Plugins}}{{if or (eq .Name "compose") (eq .Name "buildx")}}{{println .Name .Path}}{{end}}{{end}}')"
mkdir -p "$docker_config/cli-plugins"
while read -r plugin executable; do
    if [[ -n "$plugin" && -x "$executable" ]]; then
        ln -s "$executable" "$docker_config/cli-plugins/docker-$plugin"
    fi
done <<< "$docker_plugins"
export DOCKER_CONFIG="$docker_config"
docker context create "$docker_context" --docker "host=$docker_endpoint" >/dev/null

docker_preview image inspect "$tenant_image" >/dev/null
python3 "$dev_dir/init_env.py"
python3 - "$identity_dir/keycloak/.env.example" "$keycloak_env" "$press_env" <<'PY'
from pathlib import Path
from secrets import token_urlsafe
import sys

source, keycloak, press = (Path(name) for name in sys.argv[1:])
defaults = {}
for line in source.read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, _, value = line.partition("=")
        if key != "ATONOTA_SITE_TENANT1_SERVICE_SECRET":
            defaults[key] = token_urlsafe(32) if value.startswith("degistir-") else value
defaults.setdefault("IDENTITY_SYNC_WEBHOOK_SECRET", token_urlsafe(32))
keycloak.write_text("".join(f"{key}={value}\n" for key, value in defaults.items()))
press.write_text("".join(f"{key}={token_urlsafe(32)}\n" for key in ("PTR_DB_PASSWORD", "PTR_ADMIN_PASSWORD")))
PY

setting() { awk -F= -v name="$1" '$1 == name { sub(/^[^=]*=/, ""); print; exit }' "$2"; }
E2E_ADMIN_PASSWORD="$(setting ADMIN_PASSWORD "$DEV_ENV_FILE")"
E2E_KEYCLOAK_ADMIN_USER="$(setting KC_BOOTSTRAP_ADMIN_USERNAME "$keycloak_env")"
E2E_KEYCLOAK_ADMIN_PASSWORD="$(setting KC_BOOTSTRAP_ADMIN_PASSWORD "$keycloak_env")"
E2E_KEYCLOAK_CLIENT_SECRET="$(setting ATONOTA_SITE_TENANT1_SECRET "$keycloak_env")"
ATONOTA_SITE_TENANT1_SERVICE_SECRET="$(python3 -c 'from secrets import token_urlsafe; print(token_urlsafe(32))')"
export ATONOTA_SITE_TENANT1_SERVICE_SECRET
E2E_KEYCLOAK_SERVICE_CLIENT_SECRET="$ATONOTA_SITE_TENANT1_SERVICE_SECRET"
E2E_PRESS_CLIENT_SECRET="$(setting ATONOTA_PRESS_SECRET "$keycloak_env")"
E2E_PRESS_ADMIN_PASSWORD="$(setting PTR_ADMIN_PASSWORD "$press_env")"
E2E_IDENTITY_SYNC_WEBHOOK_SECRET="$(setting IDENTITY_SYNC_WEBHOOK_SECRET "$keycloak_env")"
export E2E_ADMIN_PASSWORD E2E_KEYCLOAK_ADMIN_USER E2E_KEYCLOAK_ADMIN_PASSWORD E2E_KEYCLOAK_CLIENT_SECRET
export E2E_KEYCLOAK_SERVICE_CLIENT_SECRET E2E_PRESS_CLIENT_SECRET E2E_PRESS_ADMIN_PASSWORD E2E_IDENTITY_SYNC_WEBHOOK_SECRET
export E2E_PROVIDER_HOST=e2e-provider

# Include each source fragment with an isolated override. The source fragments keep their own
# path resolution, and no files in the merged tree are changed for the runtime.
python3 - "$dev_dir" "$PREVIEW_DIR" "$PREVIEW_PROJECT" "$tenant_image" <<'PY'
import json
from pathlib import Path
import sys

dev, scratch = map(Path, sys.argv[1:3])
project, image = sys.argv[3:]
overrides = {
    "tenant": {
        "tenant-db": {"mem_limit": "512m"},
        "tenant-redis": {"mem_limit": "128m"},
        "tenant-web": {"image": image, "pull_policy": "never", "command": ["sleep", "infinity"], "mem_limit": "1024m"},
        "tenant-socket": {"image": image, "pull_policy": "never", "mem_limit": "128m"},
    },
    "keycloak": {
        "keycloak": {
            "image": f"{project}-keycloak", "pull_policy": "never", "mem_limit": "1100m",
            "environment": {"ATONOTA_SITE_TENANT1_SERVICE_SECRET": "${ATONOTA_SITE_TENANT1_SERVICE_SECRET:?}"},
        },
        "keycloak-db": {"mem_limit": "256m"},
        "mailpit": {"mem_limit": "64m"},
    },
    "press": {
        "web": {"image": f"{project}-press", "pull_policy": "never", "mem_limit": "3584m"},
        "mariadb": {"mem_limit": "512m"},
        "redis": {"mem_limit": "128m"},
    },
}
includes = []
for fragment, services in overrides.items():
    file = scratch / f"{fragment}-override.yaml"
    file.write_text(json.dumps({"services": services}))
    includes.append({"path": [str(dev / f"compose.{fragment}.yaml"), str(file)]})
(scratch / "compose.yaml").write_text(json.dumps({"include": includes}))
PY

"${compose[@]}" config --quiet
printf '%s\n' "Preparing a disposable stack. See $PREVIEW_DIR/runtime.log."
{
    # Factory's separate BuildKit container cannot resolve the image registries.
    # Select the daemon builder only in the preview's private Docker configuration.
    if [[ "$FS_COLIMA_PROFILE" == factory ]]; then
        docker context use "$docker_context" >/dev/null
        "${compose[@]}" build web keycloak
    else
        docker_preview buildx create --name "$builder" --driver docker-container --driver-opt default-load=true "$docker_context"
        "${compose[@]}" build --builder "$builder" web keycloak
    fi
    "${compose[@]}" up --no-build -d --wait --wait-timeout 120 mariadb redis
    "${compose[@]}" up --no-build -d web
    docker_preview exec -i -u root "$press" bash -s <<'BASH'
owner="$(id -u frappe):$(id -g frappe)"
chown "$owner" /home/frappe/benches
install -d -o "$(id -u frappe)" -g "$(id -g frappe)" /home/frappe/benches/source
BASH
    docker_preview cp "$worktree/backend/apps/press_tr" "$press:/home/frappe/benches/source/press_tr"
    docker_preview exec -u root "$press" bash -c "chown -R \"\$(id -u frappe):\$(id -g frappe)\" /home/frappe/benches/source/press_tr"
    docker_preview exec -i -e GOMAXPROCS=2 -e NODE_OPTIONS=--max-old-space-size=2048 -e SENTRY_TELEMETRY=false "$press" bash -s < "$dev_dir/press/install.sh"

    "${compose[@]}" up --no-build -d --wait --wait-timeout 120 tenant-db tenant-redis keycloak-db mailpit
    "${compose[@]}" up --no-build -d tenant-web keycloak
    docker_preview cp "$worktree/backend/apps/platform_core" "$tenant:/tmp/platform_core"
    docker_preview cp "$worktree/backend/libs/oidc_verify" "$tenant:/tmp/oidc_verify"
    docker_preview cp "$dev_dir/bootstrap.py" "$tenant:/tmp/preview-bootstrap.py"
    docker_preview exec -i -u root "$tenant" bash -s <<'BASH'
if [[ -d apps/platform_core ]]; then mv apps/platform_core /tmp/previous-platform-core; fi
mv /tmp/platform_core apps/platform_core
chown -R "$(id -u frappe):$(id -g frappe)" apps/platform_core /tmp/oidc_verify
BASH
    docker_preview exec "$tenant" uv pip install --python env/bin/python --no-deps /tmp/oidc_verify -e apps/platform_core
    docker_preview exec "$tenant" env/bin/python /tmp/preview-bootstrap.py tenant1.localhost --app erpnext --app platform_core
    "${compose[@]}" up --no-build -d tenant-socket

    {
        printf 'IDENTITY_SYNC_KEYCLOAK_PUBLIC_URL=%s\n' "$KC_PUBLIC_URL"
        printf 'IDENTITY_SYNC_KEYCLOAK_INTERNAL_URL=%s\n' "$KC_PUBLIC_URL"
        printf 'IDENTITY_SYNC_PRESS_URL=%s\n' "$ATONOTA_PRESS_URL"
        printf 'IDENTITY_SYNC_TENANTS=[{"name":"tenant1","base_url":"%s","organization":"tenant1"}]\n' "$ATONOTA_SITE_TENANT1_URL"
        printf 'IDENTITY_SYNC_CLIENT_SECRET=%s\n' "$(setting ATONOTA_IDENTITY_SYNC_SECRET "$keycloak_env")"
        printf 'IDENTITY_SYNC_WEBHOOK_SECRET=%s\n' "$E2E_IDENTITY_SYNC_WEBHOOK_SECRET"
        printf 'IDENTITY_SYNC_DIGEST_KEY=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')"
        printf 'IDENTITY_SYNC_PORT=%s\n' "$sync_port"
        printf '%s\n' 'IDENTITY_SYNC_HOST=0.0.0.0' 'IDENTITY_SYNC_REALM=platform' 'IDENTITY_SYNC_CLIENT_ID=identity-sync' \
            'IDENTITY_SYNC_ADMIN_SCOPE=admin-api kc-admin-api' 'IDENTITY_SYNC_DB=/tmp/e2e-sync.sqlite' 'IDENTITY_SYNC_SESSION_AZP=site-tenant1-service' 'IDENTITY_SYNC_EXECUTE_AZP=site-tenant1-service'
    } > "$sync_env"
    docker_preview create --label "$sidecar_label=$PREVIEW_PROJECT" --name "$sync" --network "$network" --network-alias "$sync_host" --network-alias identity-sync --memory 128m \
        --env-file "$sync_env" -e PYTHONPATH=/tmp --publish "127.0.0.1:$sync_port:$sync_port" \
        --entrypoint /home/frappe/frappe-bench/env/bin/python "$tenant_image" -m identity_sync serve
    docker_preview cp "$identity_dir/identity_sync/identity_sync" "$sync:/tmp/identity_sync"
    docker_preview cp "$worktree/backend/libs/oidc_verify/src/oidc_verify" "$sync:/tmp/oidc_verify"
    docker_preview start "$sync"

    docker_preview run -d --rm --label "$sidecar_label=$PREVIEW_PROJECT" --name "$provider" --network "$network" --network-alias "$E2E_PROVIDER_HOST" --memory 96m \
        --publish "127.0.0.1:$provider_port:$provider_port" --env PANE_PORT --env E2E_PROVIDER_BIND=0.0.0.0 \
        --entrypoint node "$tenant_image" --input-type=module -e "$(cat "$suite_dir/fake-provider.mjs")"
} > "$PREVIEW_DIR/runtime.log" 2>&1

export E2E_PROVIDER_IP
E2E_PROVIDER_IP="$(docker_preview inspect --format "{{(index .NetworkSettings.Networks \"$network\").IPAddress}}" "$provider")"
if [[ "${E2E_BROWSER_RUNTIME:-host}" == host ]]; then
    ports=()
    for port in "$KC_PORT" "$FS_TENANT_WEB_PORT" "$PTR_WEB_PORT" "$sync_port" "$MAILPIT_UI_PORT" "$provider_port"; do
        if ! nc -z 127.0.0.1 "$port" 2>/dev/null; then ports+=("$port"); fi
    done
    if [[ -n "${ports[0]-}" ]]; then
        PANE_SCRATCH_DIR="$tunnel_state" "$dev_dir/bin/tunnel" open "${ports[@]}"
    fi
fi

wait_http() {
    local url="$1" service="$2" attempt
    local request=(curl -4 -fsS --noproxy "*" --max-time 2 -o /dev/null)
    if [[ "${E2E_BROWSER_RUNTIME:-host}" == container ]]; then
        request=(docker --context "$docker_context" exec "$tenant" "${request[@]}")
    else
        service=127.0.0.1
    fi
    for ((attempt = 0; attempt < 40; attempt++)); do
        if "${request[@]}" --connect-to "::$service:" "$url" 2>/dev/null; then return; fi
        sleep 1
    done
    printf 'Preview endpoint is not ready: %s\n' "$url" >&2
    return 1
}

wait_http "$KC_PUBLIC_URL/realms/platform/.well-known/openid-configuration" keycloak
wait_http "http://$sync_host:$sync_port/healthz" identity-sync
wait_http "http://$E2E_PROVIDER_HOST:$provider_port/attempts" "$E2E_PROVIDER_HOST"

if [[ "${E2E_FULL_BROWSER_FIXTURES:-0}" == 1 ]]; then
    bash "$suite_dir/preview/session-tls.sh" "$docker_context" "$sync" "$tenant" "$sync_port" "$KC_PORT" "$PREVIEW_DIR/session-tls"
fi

# Frappe caches site settings on requests, including the readiness ping.
E2E_TENANT_MODULE_DIR="$(docker_preview exec "$tenant" env/bin/python -c 'import tempfile; print(tempfile.mkdtemp(prefix="e2e-tenant-"))')"
docker_preview cp "$suite_dir/preview/preview_site_config.py" "$tenant:$E2E_TENANT_MODULE_DIR/preview_site_config.py"
E2E_TENANT_MODULE_DIR="$E2E_TENANT_MODULE_DIR" python3 "$suite_dir/preview/fixtures.py" prepare
docker_preview exec -d -w /home/frappe/benches/frappe-bench "$press" bash -c "exec bench serve --port \"\$PTR_WEB_PORT\" --noreload > logs/e2e-preview-web.log 2>&1"
tenant_web_options=(-e PYTHONPATH="$E2E_TENANT_MODULE_DIR" -e E2E_KEYCLOAK_SERVICE_CLIENT_SECRET)
if [[ "${E2E_FULL_BROWSER_FIXTURES:-0}" == 1 ]]; then
    tenant_web_options+=(-e REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt)
fi
docker_preview exec -d "${tenant_web_options[@]}" "$tenant" bash -c "exec bench serve --port \"\$FS_TENANT_WEB_PORT\" --noreload > logs/e2e-preview-web.log 2>&1"
wait_http "$ATONOTA_SITE_TENANT1_URL/api/method/ping" tenant-web
wait_http "$ATONOTA_PRESS_URL/api/method/ping" web
if [[ "${E2E_BROWSER_RUNTIME:-host}" == container ]]; then
    bash "$suite_dir/preview/run-container.sh" "$docker_context" "$network" "$browser" "$worktree"
else
    node "$suite_dir/preview/run-tests.mjs" "$worktree"
fi
