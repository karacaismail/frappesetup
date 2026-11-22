#!/bin/bash
# Run in the deployable Press environment using the verified release wheel bundle.
set -euo pipefail

wheel_dir="${1:?Pass the trusted wheel directory}"
python="${2:?Pass the Press environment Python executable}"
expected="${PRESS_OIDC_WHEEL_SHA256:?Set the SHA-256 from the trusted release manifest}"
if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ ]]; then
	printf '%s\n' 'The OIDC release wheel requires a valid SHA-256.' >&2
	exit 2
fi
requirement="$(mktemp)"
trap 'rm -f -- "$requirement"' EXIT
printf 'oidc_verify==0.1.0 --hash=sha256:%s\n' "$expected" > "$requirement"
uv pip install --python "$python" --no-index --find-links "$wheel_dir" --require-hashes --reinstall-package oidc_verify --no-deps -r "$requirement"
