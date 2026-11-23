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

# The SSH key comes from the Jenkins credential "atonota-deploy-ssh" (sshagent step).
# Host names are Tailscale names; port 22 is not open to the internet.
remote() {
    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "deploy@$ATONOTA_SSH_HOST" "$@"
}

copy_to_remote() {
    local destination="$1"
    shift
    scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes "$@" "deploy@$ATONOTA_SSH_HOST:$destination"
}

copy_from_remote() {
    local source="$1" destination="$2"
    scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes "deploy@$ATONOTA_SSH_HOST:$source" "$destination"
}
