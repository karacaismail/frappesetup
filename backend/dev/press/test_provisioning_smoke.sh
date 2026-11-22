#!/bin/bash
set -euo pipefail

press_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test_dir="$(mktemp -d "${PANE_SCRATCH_DIR:-${TMPDIR:-/tmp}}/press-smoke.XXXXXX")"
trap 'rm -rf -- "$test_dir"' EXIT
export PATH="$test_dir:$PATH" DOCKER_CALLS="$test_dir/calls"

cat > "$test_dir/docker" <<'MOCK'
#!/bin/bash
printf '%s\n' "$*" >> "$DOCKER_CALLS"
case "$3" in
	port) printf '127.0.0.1:%s\n' "${MOCK_WEB_PORT:-${5%/tcp}}" ;;
	exec) exit 1 ;;
	*) exit 99 ;;
esac
MOCK
chmod +x "$test_dir/docker"

run_smoke() {
	local status=0
	: > "$DOCKER_CALLS"
	PANE_PORT="$1" FS_COLIMA_PROFILE="$2" bash "$press_dir/provisioning_smoke.sh" > "$test_dir/output" 2>&1 || status=$?
	if [[ "$status" != "$3" ]]; then
		cat "$test_dir/output" >&2
		printf 'Expected exit %s, got %s.\n' "$3" "$status" >&2
		return 1
	fi
}

run_smoke 47331 default 1
grep -Fxq -- '--context colima port fs-pd-press-provision-web-1 47334/tcp' "$DOCKER_CALLS"
grep -Fq -- '--context colima exec' "$DOCKER_CALLS"

run_smoke 1000 '' 1
grep -Fxq -- '--context colima-factory port fs-pd-press-provision-web-1 1003/tcp' "$DOCKER_CALLS"

export MOCK_WEB_PORT=2000
run_smoke 1000 factory 2
if grep -q ' exec ' "$DOCKER_CALLS"; then
	echo 'A mismatched port must stop the test before container access.' >&2
	exit 1
fi
unset MOCK_WEB_PORT

run_smoke 65527 factory 2
test ! -s "$DOCKER_CALLS"
run_smoke 0001 factory 2
test ! -s "$DOCKER_CALLS"
run_smoke 47330 other 2
test ! -s "$DOCKER_CALLS"

grep -Eq '^FROM ubuntu:22\.04@sha256:[0-9a-f]{64}$' "$press_dir/Dockerfile.provisioning-target"
grep -Eq '^      dockerfile: Dockerfile\.provisioning-target$' "$press_dir/compose.provisioning.yaml"
