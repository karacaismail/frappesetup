#!/usr/bin/env bash
# Shared helpers of the server side scripts. Source this file; do not run it.
# Layout on the server (docs/dagitim/ortamlar.md):
#   /srv/atonota/<env>/releases/<id>/   backend release: release.json, release.env, compose files
#   /srv/atonota/<env>/backend-current  relative link to the running backend release
#   /srv/atonota/<env>/backend-previous relative link to the release before it
#   /srv/atonota/<env>/backend-pending  relative link to the release being applied (until it is current)
#   /srv/atonota/<env>/backend-failed   relative link to the last release that was rolled back
#   /srv/atonota/<env>/incoming/<id>/   files that Jenkins sent for one release
#   /srv/atonota/<env>/bin/             scripts of the last applied backend release
#   /srv/atonota/web/<env>/releases/<id>/ and current, previous, failed: web releases
#   /srv/atonota/web/<env>/bin/         scripts of the last applied web release
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

# panel_entry <web bundle folder>: print the entry script that .vite/manifest.json names, relative
# to assets/. The /panel page of Frappe loads it from /panel/assets/ (E-3). Fails when the manifest
# is missing, names a file outside assets/ or names a file the bundle does not have.
panel_entry() {
    local entry
    entry="$(python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1]))["index.html"]
assert m.get("isEntry") is True
print(m["file"])' "$1/.vite/manifest.json" 2>/dev/null)" ||
        fail "the bundle has no Vite manifest with an index.html entry"
    [[ "$entry" =~ ^assets/[A-Za-z0-9][A-Za-z0-9._-]*\.m?js$ && -f "$1/$entry" ]] ||
        fail "the Vite manifest names a missing entry script: $entry"
    printf '%s\n' "${entry#assets/}"
}

# phase <release folder> <name>: how far a backend release got. rollback reads the folder copy.
# Names in order: preparing, pulling, stopping, backing-up, migrating, migrated, starting, done.
# rollback ends a release with "abandoned" or "rolled-back"; after those and "done" it may start
# again. Between stopping and starting the phase never goes back: a lower name would hide that
# the old release is stopped or that the database may be half migrated (review 2, finding E3).
phase_rank() {
    case "$1" in
    preparing) printf 0 ;; pulling) printf 1 ;; stopping) printf 2 ;; backing-up) printf 3 ;;
    migrating) printf 4 ;; migrated) printf 5 ;; starting) printf 6 ;; done) printf 7 ;;
    *) printf -- -1 ;;
    esac
}

phase() {
    local old
    old="$(cat "$1/phase" 2>/dev/null || true)"
    case "$old" in
    stopping | backing-up | migrating | migrated | starting)
        (($(phase_rank "$2") >= $(phase_rank "$old"))) ||
            fail "phase of $(basename "$1") would go back from $old to $2"
        ;;
    esac
    printf '%s\n' "$2" >"$1/phase"
    printf '%s %s\n' "$2" "$(basename "$1")" >"$ATONOTA_ROOT/$ATONOTA_ENV/phase"
}

# health_passed <kind> <release id>: true when the Jenkins health step stored a record for it.
health_passed() {
    local record="$ATONOTA_ROOT/$ATONOTA_ENV/health/$1.json"
    [[ -f "$record" && "$(json_field "$record" release_id 2>/dev/null)" == "$2" ]]
}
