#!/bin/bash
# UI-only trial shims so Press v0.154.1 can be *imported* on Python 3.14 (Frappe v16).
# Press's Ansible-based server provisioning still does NOT work: ansible-base 2.10's collection
# loader relies on importlib APIs removed in Python 3.12.
set -euo pipefail
if [[ ! -f /opt/press-local/development-image ]]; then
	echo "This patch is only available in the Press development image." >&2
	exit 78
fi
cd /home/frappe/benches/frappe-bench
SP=env/lib/python3.14/site-packages

# patch-id: standard-imghdr
# patch-id: standard-pipes
# patch-id: standard-crypt
# patch-id: standard-cgi
# Stdlib modules removed in Python 3.13 (imghdr is used by python-telegram-bot 13.15).
uv pip install -q --python env/bin/python standard-imghdr standard-pipes standard-crypt standard-cgi

# patch-id: ansible-six
# patch-id: telegram-six
# patch-id: stripe-six
# Vendored six < 1.16 only implements find_module(), removed from importlib in Python 3.12, so
# `six.moves` cannot be imported. Swap in the bench's six 1.17 (same API, adds find_spec).
for f in "$SP/ansible/module_utils/six/__init__.py" \
	"$SP/telegram/vendor/ptb_urllib3/urllib3/packages/six.py" \
	"$SP/stripe/six.py"; do
	[ -f "$f.orig" ] || cp "$f" "$f.orig"
	cp "$SP/six.py" "$f"
done
mkdir -p logs

# patch-id: ansible-collection-loader
# ansible-base 2.10 installs a path-hook finder without find_spec(); once installed it breaks every
# later import in the process on Python 3.12+. Skip installing it (UI-only: no collections/plays).
L="$SP/ansible/plugins/loader.py"
[ -f "$L.orig" ] || cp "$L" "$L.orig"
grep -q "press-local: skip collection finder" "$L" || sed -i \
	's/^    finder = _AnsibleCollectionFinder(C.config.get_config_value/    return  # press-local: skip collection finder (Python 3.12+)\n&/' "$L"

# patch-id: deploy-candidate-typed-dict
# press: TypedDict keyword-argument syntax was removed in Python 3.13. Use the dict form.
C=apps/press/press/press/doctype/deploy_candidate/cache_utils.py
env/bin/python - "$C" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
old = re.search(r'CommandOutput = TypedDict\(\n\t"CommandOutput",\n((?:\t\w+=\w+,\n)+)\)', s)
if old:
	fields = re.findall(r'\t(\w+)=(\w+),', old.group(1))
	new = 'CommandOutput = TypedDict(\n\t"CommandOutput",\n\t{' + ", ".join(f'"{k}": {v}' for k, v in fields) + '},\n)'
	open(p, "w").write(s.replace(old.group(0), new))
PY

# patch-id: product-trial-telemetry
# Frappe v16 removed PostHog telemetry (frappe.utils.telemetry.init_telemetry). Press only uses it
# to send product-trial analytics events; fall back to a no-op so the doctype module imports.
P=apps/press/press/saas/doctype/product_trial_request/product_trial_request.py
grep -q "press-local: v16 telemetry" "$P" || sed -i \
	's/^from frappe.utils.telemetry import init_telemetry$/try:\n\tfrom frappe.utils.telemetry import init_telemetry\nexcept ImportError:  # press-local: v16 telemetry removed\n\n\tdef init_telemetry():\n\t\tpass/' "$P"
