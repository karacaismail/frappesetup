#!/bin/bash
# Run only against the disposable Task C Compose project.
set -euo pipefail

press_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project=fs-pd-press-provision
web="$project-web-1"
target="$project-target"
network="${project}_default"
bench_dir=/home/frappe/benches/frappe-bench

if [[ ! "${PANE_PORT:-}" =~ ^[1-9][0-9]{3,4}$ ]] || (( PANE_PORT > 65526 )); then
	echo 'PANE_PORT must be an integer from 1000 to 65526.' >&2
	exit 2
fi

case "${FS_COLIMA_PROFILE:-factory}" in
	factory) press_context=colima-factory ;;
	default) press_context=colima ;;
	*) echo 'FS_COLIMA_PROFILE must be factory or default.' >&2; exit 2 ;;
esac

docker() { command docker --context "$press_context" "$@"; }

web_port="$((PANE_PORT + 3))"
if [[ "$(docker port "$web" "$web_port/tcp")" != "127.0.0.1:$web_port" ]]; then
	echo 'The Press web container must publish PANE_PORT + 3 on 127.0.0.1.' >&2
	exit 2
fi
if ! docker exec -w "$bench_dir" "$web" test -f sites/press.localhost/site_config.json; then
	echo 'Finish the Press site installation before running the smoke test.' >&2
	exit 1
fi
target_ip="$(docker inspect --format "{{with index .NetworkSettings.Networks \"$network\"}}{{.IPAddress}}{{end}}" "$target")"
if [[ -z "$target_ip" || "$(docker inspect --format '{{.HostConfig.NetworkMode}} {{len .NetworkSettings.Networks}}' "$target")" != "$network 1" ]]; then
	echo 'The target must only be attached to the provisioning Compose network.' >&2
	exit 2
fi

# Disable outbound package downloads before running the stock playbook.
docker exec --user root "$target" sh -eu -c '
	for family in -4 -6; do
		if [ -n "$(ip "$family" route show default)" ]; then
			ip "$family" route del default
		fi
		test -z "$(ip "$family" route show default)"
	done
	printf "%s\n" \
		"Acquire::http::Proxy \"http://127.0.0.1:9\";" \
		"Acquire::https::Proxy \"http://127.0.0.1:9\";" \
		"Acquire::Retries \"0\";" \
		"APT::Update::Error-Mode \"any\";" > /etc/apt/apt.conf.d/99-provisioning-smoke
'
docker exec "$web" ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes "root@$target_ip" true

host_name="target-$(uuidgen | tr '[:upper:]' '[:lower:]')"
docker exec -i -w "$bench_dir/sites" "$web" "$bench_dir/env/bin/python" - enqueue "$host_name" "$target_ip" < "$press_dir/provisioning_smoke.py"
docker exec -w "$bench_dir" "$web" bench worker --queue long --burst --quiet
docker exec -i -w "$bench_dir/sites" "$web" "$bench_dir/env/bin/python" - verify "$host_name" < "$press_dir/provisioning_smoke.py"
