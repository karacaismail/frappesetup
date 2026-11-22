#!/bin/sh
# Run from the candidate Bench root.
set -eu

if [ -e /opt/press-local/development-image ] || [ -e /opt/press-local/scripts/patch-py314.sh ]; then
    printf '%s\n' 'Press development patch is present.' >&2
    exit 1
fi
if ! git -C apps/press diff --quiet HEAD --; then
    printf '%s\n' 'Press source differs from the checked-out commit.' >&2
    exit 1
fi

cd sites
../env/bin/python -B - <<'PY'
import sys
from importlib import import_module

import frappe

if sys.version_info[:2] != (3, 14) or not frappe.__version__.startswith("16."):
    raise SystemExit("The candidate must use Python 3.14 and Frappe 16.")

for module in (
    "press.runner",
    "press.press.doctype.deploy_candidate.cache_utils",
    "press.saas.doctype.product_trial_request.product_trial_request",
):
    import_module(module)
PY
