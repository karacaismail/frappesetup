#!/usr/bin/env bash
# Shared helpers of the Jenkins side scripts. Source this file; do not run it.
# shellcheck shell=bash

DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export DEPLOY_DIR

fail() {
    printf 'deploy: %s\n' "$*" >&2
    exit 1
}

# Validate deploy/environments/<env>.env with release.py, then load it into the shell.
load_env() {
    local env="$1"
    case "$env" in alpha | beta | rc | prod) ;; *) fail "unknown environment: $env" ;; esac
    release_py env-check "$env" || fail "invalid environment file: $env"
    set -a
    # shellcheck source=/dev/null
    . "$DEPLOY_DIR/environments/$env.env"
    set +a
}

release_py() {
    python3 -I "$DEPLOY_DIR/release.py" "$@"
}

# The SSH key comes from the Jenkins credential "atonota-deploy-ssh-<env>" (sshagent step).
# Each environment has its own key and its own server user (ATONOTA_SSH_USER, "deploy-<env>").
# Host names are Tailscale names; port 22 is not open to the internet.
ssh_options=(-o BatchMode=yes -o StrictHostKeyChecking=yes)

# ssh joins its arguments into one line and the server shell splits it again. Quote every word
# here, so a value can never become a second command on the server.
remote() {
    local command
    command="$(printf '%q ' "$@")"
    ssh "${ssh_options[@]}" -- "$ATONOTA_SSH_USER@$ATONOTA_SSH_HOST" "${command% }"
}

copy_to_remote() {
    local destination="$1"
    shift
    scp -q "${ssh_options[@]}" -- "$@" "$ATONOTA_SSH_USER@$ATONOTA_SSH_HOST:$destination"
}

copy_from_remote() {
    local source="$1" destination="$2"
    scp -q "${ssh_options[@]}" -- "$ATONOTA_SSH_USER@$ATONOTA_SSH_HOST:$source" "$destination"
}

# Server copies of the remote scripts: each kind keeps the scripts of its last applied release.
server_bin() {
    local env="$1" kind="$2"
    case "$kind" in
    backend) printf '/srv/atonota/%s/bin' "$env" ;;
    web | web-asset) printf '/srv/atonota/web/%s/bin' "$env" ;;
    *) fail "unknown kind: $kind" ;;
    esac
}

# A release id goes into server paths; release.py checks it too. This is the second fence.
check_release_id() {
    [[ "$1" =~ ^(backend|web)-[0-9a-f]{12}-b[1-9][0-9]*$ ]] || fail "bad release id: $1"
}

# Press runs only when the environment switch is 1 and the release carries the Press image.
# remote/common.sh has the same rule for remote/apply. Usage: press_on <switch> <release.json>
press_on() {
    [[ "$1" == 1 ]] && release_py images "$2" | grep -q '^press='
}
