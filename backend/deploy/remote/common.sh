#!/usr/bin/env bash
# Shared helpers of the server side scripts. Source this file; do not run it.
# Layout on the server (docs/dagitim/ortamlar.md):
#   /srv/atonota/<env>/releases/<id>/   backend release: release.json, release.env, compose files
#   /srv/atonota/<env>/backend-current  relative link to the running backend release
#   /srv/atonota/<env>/backend-previous relative link to the release before it
#   /srv/atonota/web/<env>/releases/<id>/ and current, previous: web releases
#   /srv/atonota/<env>/backups/<time>/  backups taken before each backend release
#   /srv/atonota/<env>/health/<kind>.json health record written by the Jenkins health step
#   /etc/atonota/<env>/*.env            secrets, mode 0600, created by the DevOps owner
# shellcheck shell=bash

# Tests point these at a temporary folder. On a server they keep their defaults.
ATONOTA_ROOT="${ATONOTA_ROOT:-/srv/atonota}"
ATONOTA_ETC="${ATONOTA_ETC:-/etc/atonota}"

fail() {
    printf 'remote: %s\n' "$*" >&2
    exit 1
}

say() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

check_env_name() {
    case "$1" in alpha | beta | rc | prod) ;; *) fail "unknown environment: $1" ;; esac
}

load_host_env() {
    local file="$1"
    set -a
    # shellcheck source=/dev/null
    . "$file"
    set +a
}

# Point a link at a target in one rename, so readers never see a missing link.
switch_link() {
    local target="$1" link="$2"
    ln -sfn "$target" "$link.next"
    mv -T "$link.next" "$link"
}

# docker compose for the backend release in folder $1.
stack() {
    local folder="$1"
    shift
    COMPOSE_PROFILES="$(sed -n 's/^COMPOSE_PROFILES=//p' "$folder/release.env")" \
        docker compose --project-name "atonota-${ATONOTA_ENV:?host.env is not loaded}" \
        --env-file "$folder/host.env" --env-file "$folder/release.env" \
        --file "$folder/stack.yaml" "$@"
}

json_field() {
    python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1]))
for k in sys.argv[2:]: d=d[k]
print(d)' "$@"
}

phase() {
    printf '%s\n' "$1" >"$ATONOTA_ROOT/$ATONOTA_ENV/phase"
}
