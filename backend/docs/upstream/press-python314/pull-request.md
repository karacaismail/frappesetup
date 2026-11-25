# Pull request text for frappe/press

Target repository: `frappe/press`. Base branch: `develop`.

Title: `fix(compat): Import on Python 3.13 and Frappe v16`

Paste everything below the line into the description box. Press asks that the description is not hard-wrapped.

---

## Why

Three Press modules fail to import on Python 3.13+ or on Frappe v16. Each failure happens at import time, so the whole module (and every DocType or API that imports it) is unusable, not only the function that needs the changed code.

| Module | Error | Cause |
| --- | --- | --- |
| `press/press/doctype/deploy_candidate/cache_utils.py` | `TypeError: TypedDict() got an unexpected keyword argument 'cwd'` | Python 3.13 removed the keyword form `TypedDict("Name", field=type)` |
| `press/saas/doctype/product_trial_request/product_trial_request.py` | `ImportError: cannot import name 'init_telemetry' from 'frappe.utils.telemetry'` | Frappe v16 removed `init_telemetry` |
| `press/api/cookies.py` | `ImportError: cannot import name 'get_cookie_dict_from_headers' from 'frappe.oauth'` | Frappe v16 removed `get_cookie_dict_from_headers` |

The telemetry error is the one reported in #7534.

## What

1. `fix(deploy-candidate)`: `CommandOutput` uses the class syntax. The fields, types and required keys stay the same. `AppInfo` in `test_deploy_candidate.py` moves to the same form, so its `noqa: UP013` goes. `AppInfo` only runs under `TYPE_CHECKING`.
2. `fix(product-trial)`: `init_telemetry` comes from `press.utils.telemetry`. Press already ships this helper. It reads `posthog_host` and `posthog_project_id` and returns early when they are unset, so the call sites do not change.
3. `fix(cookies)`: `cookie_perms` comes from `frappe.local.request.cookies`. Werkzeug returns a string, so the `.value` access goes. The `unquote` call stays, so a percent-encoded value still parses.

The class syntax was chosen over the dict form `TypedDict("Name", {...})` because the repository enables ruff `UP`, and UP013 rewrites the dict form to the class form anyway.

## Not in this pull request

- Dependency pins in `pyproject.toml` for Python 3.14 and Frappe v16 (for example `ansible`, `stripe` and `requests`). They need their own discussion, because each one changes runtime behaviour.
- `python-telegram-bot`. `develop` already calls the Telegram Bot API over HTTP, so nothing is left to change there.

## Testing

```text
ruff 0.13.1 check on the four files: no new findings
(cache_utils.py keeps four findings that exist on v0.154.1 too; UP013 is gone)

Python 3.12.16: CommandOutput required keys = cwd, image_tag, output, returncode
Python 3.14.10: CommandOutput required keys = cwd, image_tag, output, returncode
Python 3.14.10: TypedDict("X", cwd=str) -> TypeError (the bug this fixes)
```

Equivalent changes run in a Press v0.154.1 image on Frappe 16.56.0 and Python 3.14.10. That image builds `CommandOutput` with the dict form, and the other two changes are identical. There `press.press.doctype.deploy_candidate.cache_utils`, `press.saas.doctype.product_trial_request.product_trial_request` and `press.api.cookies` import, and `update_preferences` records a change of the analytics preference. These are import and unit checks. The Press test suite (`bench run-tests --app press`) was not run against these commits.

Suggested checks for reviewers:

```bash
bench --site <site> run-tests --app press --module press.press.doctype.deploy_candidate.test_deploy_candidate
bench --site <site> run-tests --app press --module press.saas.doctype.product_trial_request.test_product_trial_request
```
