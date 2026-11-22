#!/bin/bash
set -euo pipefail

dev_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../dev" && pwd)"
if [[ ! "${PANE_PORT:-}" =~ ^[1-9][0-9]{3,4}$ ]] || (( PANE_PORT > 65526 )); then
    printf '%s\n' 'PANE_PORT must be an integer from 1000 to 65526.' >&2
    exit 2
fi

export KIRACI_WEB_PORT="$((PANE_PORT + 1))"
export KIRACI_SOCKET_PORT="$((PANE_PORT + 2))"
export DEV_ENV_FILE="${DEV_ENV_FILE:-$dev_dir/.env}"
compose=(docker --context colima-factory compose --project-name "fs-integration-e2e-$PANE_PORT"
    --env-file "$DEV_ENV_FILE" --file "$dev_dir/compose.yaml")

case "${1:-}" in
    up)
        python3 "$dev_dir/init_env.py"
        "${compose[@]}" config --quiet
        "${compose[@]}" build kiraci-web
        "${compose[@]}" up -d --wait --wait-timeout 90 kiraci-db kiraci-redis
        "${compose[@]}" run --rm --no-deps kiraci-web \
            env/bin/python /workspace/dev/bootstrap.py kiraci1.localhost --app erpnext --app platform_core
        "${compose[@]}" up -d kiraci-web kiraci-socket
        "$dev_dir/bin/tunel" ac "$KIRACI_WEB_PORT" "$KIRACI_SOCKET_PORT"
        printf 'Tenant URL: http://kiraci1.localhost:%s\n' "$KIRACI_WEB_PORT"
        ;;
    down)
        if [[ -f "$DEV_ENV_FILE" ]]; then
            "${compose[@]}" down
            "$dev_dir/bin/tunel" kapat
        fi
        ;;
    config)
        python3 "$dev_dir/init_env.py"
        "${compose[@]}" config --quiet
        ;;
    *)
        printf '%s\n' 'Usage: environment.sh <up|down|config>' >&2
        exit 2
        ;;
esac
