#!/bin/bash
set -euo pipefail

press_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! "${PANE_PORT:-}" =~ ^[1-9][0-9]{3,4}$ ]] || (( PANE_PORT > 65526 )); then
	printf '%s\n' 'PANE_PORT must be an integer from 1000 to 65526.' >&2
	exit 2
fi
export PRESS_WEB_PORT="$((PANE_PORT + 3))"
export PRESS_SOCKET_PORT="$((PANE_PORT + 4))"

case "${FS_COLIMA_PROFILE:-factory}" in
	factory) press_context=colima-factory ;;
	default) press_context=colima ;;
	*) printf '%s\n' 'FS_COLIMA_PROFILE must be factory or default.' >&2; exit 2 ;;
esac

exec docker --context "$press_context" compose \
	--env-file "${PRESS_ENV_FILE:-$press_dir/.env}" \
	--file "$press_dir/../compose.press.yaml" "$@"
