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

# Press runs only when the environment switch is 1 and the release carries the Press image.
# bin/lib.sh has the same rule for the health check. Usage: press_on <switch> <release.json>
# The switch is 1 only in alpha and beta, as in release.py (PRESS_ENVIRONMENTS). Backup and restore
# do not cover the Press site yet (blocker E-2). Jenkins checks this too; the server checks again,
# because a person may run apply by hand (review 1, finding 5).
press_on() {
    if [[ "$1" == 1 ]]; then
        case "${ATONOTA_ENV:?host.env is not loaded}" in
        alpha | beta) ;;
        *) fail "ATONOTA_PRESS_ENABLED=1 is refused in $ATONOTA_ENV; Press is not backed up there yet (E-2)" ;;
        esac
    fi
    [[ "$1" == 1 ]] && python3 -I -c 'import json,sys; sys.exit("press" not in json.load(open(sys.argv[1]))["components"])' "$2"
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
# to assets/. The /panel page of Frappe loads it from /panel/assets/ (E-3). The check follows the
# rules of platform_core/shell/panel_assets.py: the entry, every CSS file and every static import
# must be a file straight under assets/ (scripts .js or .mjs, styles .css) and must be in the
# bundle. Otherwise the page would fall back to the placeholder after the release (review 1, K-1).
panel_entry() {
    local entry
    entry="$(python3 -I -c 'import json, os, re, sys
folder = sys.argv[1]
try:
    with open(os.path.join(folder, ".vite", "manifest.json"), "rb") as stream:
        manifest = json.load(stream)
    entry = manifest["index.html"]
except (OSError, ValueError, KeyError, TypeError):
    sys.exit("the bundle has no readable Vite manifest with an index.html entry")
script = re.compile(r"assets/[A-Za-z0-9][A-Za-z0-9._-]*\.m?js")
style = re.compile(r"assets/[A-Za-z0-9][A-Za-z0-9._-]*\.css")
def check(file, pattern):
    if not (isinstance(file, str) and pattern.fullmatch(file) and ".." not in file and os.path.isfile(os.path.join(folder, file))):
        sys.exit("the Vite manifest names a missing or unexpected file: %r" % (file,))
def items(chunk, field):
    value = chunk.get(field, [])
    if not isinstance(value, list):
        sys.exit("the Vite manifest field %r is not a list" % field)
    return value
if not isinstance(entry, dict) or entry.get("isEntry") is not True:
    sys.exit("the Vite manifest entry index.html is not an entry")
check(entry.get("file"), script)
seen, todo = {"index.html"}, [entry]
while todo:
    chunk = todo.pop()
    for file in items(chunk, "css"):
        check(file, style)
    for key in items(chunk, "imports"):
        if key not in seen:
            seen.add(key)
            imported = manifest.get(key)
            if not isinstance(imported, dict):
                sys.exit("the Vite manifest has no chunk %r" % (key,))
            check(imported.get("file"), script)
            todo.append(imported)
print(entry["file"])' "$1")" ||
        fail "the bundle has no valid Vite manifest with an index.html entry"
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
