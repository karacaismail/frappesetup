#!/bin/bash
set -euo pipefail

dev_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../dev" && pwd)"
test_dir="$(dirname -- "$dev_dir")/e2e"
if [[ ! "${PANE_PORT:-}" =~ ^[1-9][0-9]{3,4}$ ]] || (( PANE_PORT > 65526 )); then
    printf '%s\n' 'PANE_PORT must be an integer from 1000 to 65526.' >&2
    exit 2
fi

export KIRACI_WEB_PORT="$((PANE_PORT + 1))"
export KIRACI_SOCKET_PORT="$((PANE_PORT + 2))"
export DEV_ENV_FILE="${DEV_ENV_FILE:-$dev_dir/.env}"
project="fs-integration-e2e-$PANE_PORT"
provider_port="$((PANE_PORT + 7))"
tenant_image="fs-kiraci-dev:$PANE_PORT"
colima_bin="${COLIMA_BIN:-$HOME/.local/bin/colima}"
context=colima-factory
if [[ "${1:-}" == --press ]]; then
    context=colima
    shift
fi
engine=(docker --context "$context")
compose=("${engine[@]}" compose --project-name "$project"
    --env-file "$DEV_ENV_FILE" --file "$dev_dir/compose.yaml")

if [[ "$context" == colima ]]; then
    if [[ "${1:-}" == up ]]; then
        memory="$("$colima_bin" ssh -- free -g)"
        available="$(awk '$1 == "Mem:" { print $7 }' <<< "$memory")"
        if [[ ! "$available" =~ ^[0-9]+$ ]] || (( available < 3 )); then
            printf '%s\n' 'The default Colima profile needs at least 3 GB of available memory.' >&2
            exit 1
        fi
        printf 'Default Colima available memory: %s GB\n' "$available"
    fi
    printf '%s\n' 'Press integration is pending on the backend branch.' >&2
    exit 2
fi

case "${1:-}" in
    up)
        trap 'printf "%s\n" "Startup stopped. Run environment.sh down to close this test environment." >&2' ERR
        disk="$("$colima_bin" ssh -p factory -- df -Pk /var/lib/docker)"
        available="$(awk 'NR == 2 { print $4 }' <<< "$disk")"
        if [[ ! "$available" =~ ^[0-9]+$ ]] || (( available < 5 * 1024 * 1024 )); then
            printf '%s\n' 'The factory Colima profile needs at least 5 GiB of free disk space.' >&2
            exit 1
        fi
        python3 "$dev_dir/init_env.py"
        "${compose[@]}" config --quiet
        if "${engine[@]}" image inspect "$tenant_image" >/dev/null 2>&1; then
            printf 'Reusing tenant image: %s\n' "$tenant_image"
        else
            "${compose[@]}" build kiraci-web
        fi
        "${compose[@]}" up --no-build -d --wait --wait-timeout 90 kiraci-db kiraci-redis
        "${compose[@]}" run --rm --no-deps kiraci-web \
            env/bin/python /workspace/dev/bootstrap.py kiraci1.localhost --app erpnext --app platform_core
        "${compose[@]}" up --no-build -d kiraci-web kiraci-socket
        "$dev_dir/bin/tunel" kapat
        "$dev_dir/bin/tunel" ac "$KIRACI_WEB_PORT" "$KIRACI_SOCKET_PORT" "$provider_port"
        printf 'Tenant URL: http://kiraci1.localhost:%s\n' "$KIRACI_WEB_PORT"
        ;;
    down)
        if [[ ! -f "$DEV_ENV_FILE" ]]; then
            printf '%s\n' 'Cannot close the test environment: the local environment file is missing.' >&2
            exit 2
        fi
        if "${engine[@]}" container inspect "$project-provider" >/dev/null 2>&1; then
            "${engine[@]}" stop "$project-provider"
        fi
        "${compose[@]}" down
        "$dev_dir/bin/tunel" kapat
        ;;
    provider)
        "${engine[@]}" run --detach --rm --name "$project-provider" \
            --network "${project}_default" --network-alias e2e-provider \
            --publish "127.0.0.1:$provider_port:$provider_port" --env PANE_PORT \
            --env E2E_PROVIDER_BIND=0.0.0.0 \
            --entrypoint node "$tenant_image" \
            --input-type=module -e "$(cat "$test_dir/fake-provider.mjs")"
        ;;
    config)
        python3 "$dev_dir/init_env.py"
        "${compose[@]}" config --quiet
        ;;
    *)
        printf '%s\n' 'Usage: environment.sh [--press] <up|down|config|provider>' >&2
        exit 2
        ;;
esac
