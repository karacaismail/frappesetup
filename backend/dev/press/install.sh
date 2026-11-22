#!/bin/bash
# Run in the isolated fs-press-tr web container.
set -euo pipefail
if [[ ! -f /opt/press-local/development-image ]]; then
	echo "Site setup is only available in the Press development image." >&2
	exit 78
fi

cd /home/frappe/benches
python="$HOME/.pyenv/versions/3.14.10/bin/python3"
if [ ! -x "$python" ]; then
	echo "Python 3.14.10 is missing from the bench image" >&2
	exit 1
fi

if [ ! -d frappe-bench/apps/frappe ]; then
	bench init --skip-assets --skip-redis-config-generation --frappe-branch v16.50.0 --python "$python" frappe-bench
fi
cd frappe-bench

bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis:6379/0
bench set-config -g redis_queue redis://redis:6379/1
bench set-config -g redis_socketio redis://redis:6379/2
bench set-config -gp webserver_port "$PRESS_WEB_PORT"
bench set-config -gp socketio_port "$PRESS_SOCKET_PORT"

# Redis is external and this environment has no scheduler.
sed -i '/^redis_/d; /^schedule:/d' Procfile
sed -i -E "s/(bench serve[[:space:]]+--port )[0-9]+/\1$PRESS_WEB_PORT/" Procfile

if [ ! -d apps/press ]; then
	bench get-app --skip-assets --branch v0.154.1 press https://github.com/frappe/press
elif ! grep -qxF press sites/apps.txt; then
	# Resume a partial installation without deleting its clone.
	uv pip install --python env/bin/python -e apps/press
	(cd apps/press && yarn install --check-files)
	grep -qxF press sites/apps.txt || printf '\n%s\n' press >> sites/apps.txt
fi

test "$(git -C apps/frappe rev-parse HEAD)" = f20f92d29706510551b4438cc196b0323a7f1a92
test "$(git -C apps/press rev-parse HEAD)" = 7a4384d5eec9f0f0dce4124e9dd48b106e51222f

bash /opt/press-local/scripts/patch-py314.sh
bench build --app frappe
# The site-less Press after_build hook can fail after emitting the dashboard.
bench build --app press || test -f apps/press/press/public/dashboard/index.html

if [ ! -f sites/press.localhost/site_config.json ]; then
	(cd sites && ../env/bin/python /opt/press-local/scripts/create_site.py)
fi

ln -sfn /home/frappe/benches/source/press_tr apps/press_tr
identity_wheels=(/opt/press-local/wheels/oidc_verify-*.whl)
if (( ${#identity_wheels[@]} != 1 )) || [[ ! -f "${identity_wheels[0]}" ]]; then
	echo "The Press image must provide exactly one oidc_verify wheel." >&2
	exit 1
fi
uv pip install --python env/bin/python -e 'apps/press_tr[test]' "${identity_wheels[0]}"
grep -qxF press_tr sites/apps.txt || printf '\n%s\n' press_tr >> sites/apps.txt
bench --site press.localhost install-app press_tr
bench --site press.localhost disable-scheduler
# Press preserves these caches during clear-cache. Evict them after installation commits.
bench --site press.localhost execute frappe.cache.delete_value --args '[["all_apps", "app_hooks"]]'
