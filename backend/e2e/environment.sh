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
compose=(docker --context colima-factory compose --project-name "$project"
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
        "$dev_dir/bin/tunel" ac "$KIRACI_WEB_PORT" "$KIRACI_SOCKET_PORT" "$provider_port"
        printf 'Tenant URL: http://kiraci1.localhost:%s\n' "$KIRACI_WEB_PORT"
        ;;
    down)
        if [[ -f "$DEV_ENV_FILE" ]]; then
            if docker --context colima-factory container inspect "$project-provider" >/dev/null 2>&1; then
                docker --context colima-factory stop "$project-provider"
            fi
            "${compose[@]}" down
            "$dev_dir/bin/tunel" kapat
        fi
        ;;
    provider)
        docker --context colima-factory run --detach --rm --name "$project-provider" \
            --network "${project}_default" --network-alias e2e-provider \
            --publish "127.0.0.1:$provider_port:$provider_port" --env PANE_PORT \
            --env E2E_PROVIDER_BIND=0.0.0.0 \
            --entrypoint node "fs-kiraci-dev:$PANE_PORT" \
            --input-type=module -e "$(cat "$test_dir/fake-provider.mjs")"
        ;;
    config)
        python3 "$dev_dir/init_env.py"
        "${compose[@]}" config --quiet
        ;;
    *)
        printf '%s\n' 'Usage: environment.sh <up|down|config|provider>' >&2
        exit 2
        ;;
esac
