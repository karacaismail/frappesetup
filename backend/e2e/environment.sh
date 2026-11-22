#!/bin/bash
set -euo pipefail

dev_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../dev" && pwd)"
test_dir="$(dirname -- "$dev_dir")/e2e"
if [[ ! "${PANE_PORT:-}" =~ ^[1-9][0-9]{3,4}$ ]] || (( PANE_PORT > 65526 )); then
    printf '%s\n' 'PANE_PORT must be an integer from 1000 to 65526.' >&2
    exit 2
fi

export FS_TENANT_WEB_PORT="$((PANE_PORT + 1))"
export FS_TENANT_SOCKET_PORT="$((PANE_PORT + 2))"
export DEV_ENV_FILE="${DEV_ENV_FILE:-$dev_dir/.env}"
project="fs-integration-e2e-$PANE_PORT"
provider_port="$((PANE_PORT + 7))"
tenant_image="fs-tenant-dev:$PANE_PORT"
colima_bin="${COLIMA_BIN:-$HOME/.local/bin/colima}"
press=false
if [[ "${1:-}" == --press ]]; then
    press=true
    export FS_COLIMA_PROFILE=default
    shift
fi
export FS_COLIMA_PROFILE="${FS_COLIMA_PROFILE:-factory}"
case "$FS_COLIMA_PROFILE" in
    factory) context=colima-factory; other_context=colima ;;
    default) context=colima; other_context=colima-factory ;;
    *) printf '%s\n' 'FS_COLIMA_PROFILE must be factory or default.' >&2; exit 2 ;;
esac
engine=(docker --context "$context")
compose=("${engine[@]}" compose --project-name "$project"
    --env-file "$DEV_ENV_FILE" --file "$dev_dir/compose.yaml")

if [[ "$context" == colima && "${1:-}" == up ]]; then
    minimum_memory=2
    if "$press"; then minimum_memory=3; fi
    memory="$("$colima_bin" ssh -- free -g)"
    available="$(awk '$1 == "Mem:" { print $7 }' <<< "$memory")"
    if [[ ! "$available" =~ ^[0-9]+$ ]] || (( available < minimum_memory )); then
        printf 'The default Colima profile needs at least %s GB of available memory.\n' "$minimum_memory" >&2
        exit 1
    fi
    printf 'Default Colima available memory: %s GB\n' "$available"
fi
if "$press"; then
    printf '%s\n' 'Press integration is pending on the backend branch.' >&2
    exit 2
fi

case "${1:-}" in
    up)
        trap 'printf "%s\n" "Startup stopped. Run environment.sh down to close this test environment." >&2' ERR
        if running="$(docker --context "$other_context" ps -q --filter "label=com.docker.compose.project=$project" 2>/dev/null)" && [[ -n "$running" ]]; then
            printf '%s\n' 'Close this integration environment in the other Colima profile first.' >&2
            exit 1
        fi
        if [[ "$context" == colima-factory ]]; then
            disk="$("$colima_bin" ssh -p factory -- df -Pk /var/lib/docker)"
            available="$(awk 'NR == 2 { print $4 }' <<< "$disk")"
            if [[ ! "$available" =~ ^[0-9]+$ ]] || (( available < 5 * 1024 * 1024 )); then
                printf '%s\n' 'The factory Colima profile needs at least 5 GiB of free disk space.' >&2
                exit 1
            fi
            if [[ ! -f "$DEV_ENV_FILE" ]] || ! "${engine[@]}" image inspect "$tenant_image" >/dev/null 2>&1 \
                || ! "${engine[@]}" volume inspect "${project}_kiraci-db" "${project}_kiraci-sites" "${project}_kiraci-logs" >/dev/null 2>&1; then
                printf '%s\n' 'Factory can only reuse an existing environment. Use FS_COLIMA_PROFILE=default for a new site.' >&2
                exit 2
            fi
            printf 'Reusing tenant image: %s\n' "$tenant_image"
            "${compose[@]}" up --no-build --pull never -d --wait --wait-timeout 90 tenant-db tenant-redis
            "${compose[@]}" up --no-build --pull never -d tenant-web tenant-socket
        else
            python3 "$dev_dir/init_env.py"
            "${compose[@]}" config --quiet
            if "${engine[@]}" image inspect "$tenant_image" >/dev/null 2>&1; then
                printf 'Reusing tenant image: %s\n' "$tenant_image"
            else
                "${compose[@]}" build tenant-web
            fi
            "${compose[@]}" up --no-build -d --wait --wait-timeout 90 tenant-db tenant-redis
            "${compose[@]}" run --rm --no-deps tenant-web \
                env/bin/python /workspace/dev/bootstrap.py tenant1.localhost --app erpnext --app platform_core
            "${compose[@]}" up --no-build -d tenant-web tenant-socket
        fi
        "$dev_dir/bin/tunnel" close
        forward_ports=()
        for port in "$FS_TENANT_WEB_PORT" "$FS_TENANT_SOCKET_PORT" "$provider_port"; do
            if ! nc -z 127.0.0.1 "$port" 2>/dev/null; then
                forward_ports+=("$port")
            fi
        done
        if [[ -n "${forward_ports[0]-}" ]]; then
            "$dev_dir/bin/tunnel" open "${forward_ports[@]}"
        fi
        printf 'Tenant URL: http://kiraci1.localhost:%s\n' "$FS_TENANT_WEB_PORT"
        ;;
    down)
        if [[ ! -f "$DEV_ENV_FILE" ]]; then
            printf '%s\n' 'Cannot close the test environment: the local environment file is missing.' >&2
            exit 2
        fi
        if "${engine[@]}" container inspect "$project-provider" >/dev/null 2>&1; then
            "${engine[@]}" stop "$project-provider"
        fi
        if [[ "$context" == colima ]]; then
            "${compose[@]}" down --volumes
        else
            "${compose[@]}" down
        fi
        "$dev_dir/bin/tunnel" close
        if [[ "$context" == colima ]]; then
            owned_image="$("${engine[@]}" image ls --filter "reference=$tenant_image" \
                --filter "label=com.docker.compose.project=$project" --format '{{.ID}}')"
            if [[ -n "$owned_image" ]]; then
                "${engine[@]}" image rm --no-prune "$tenant_image"
            fi
        fi
        ;;
    provider)
        "${engine[@]}" run --pull never --detach --rm --name "$project-provider" \
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
