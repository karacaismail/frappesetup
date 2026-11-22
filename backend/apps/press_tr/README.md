# Press TR

Keycloak sign-in and identity synchronization for Press on Frappe 16.

## Installation

Use the isolated environment in [Press development setup](../../dev/press/README.md).
Install the shared `oidc_verify` package from `backend/libs/oidc_verify` into the bench Python environment. The login callback, logout notification and service routes require it.

Configure these site settings before starting the web process:

- `host_name` is the exact Press origin registered for the Keycloak callback.
- `keycloak_public_url` and `keycloak_realm` identify the issuer. Use
  `keycloak_internal_url` when the bench reaches Keycloak through a different address.
- `keycloak_client_secret` is the secret for the `press` client. Keep it in site configuration.
- `platform_panel_url` is where legacy Press login and signup pages redirect.
- `press_identity_sync_user` identifies a dedicated, enabled Website User without administrative roles.

Register the exact callback and logout notification addresses in the
[OpenAPI contract](../../contracts/press_tr.openapi.yaml).

## Local HTTP tests

Run these tests only on a disposable bench. They create example users, teams and sessions.
The test issuer runs inside the web container and signs its own short-lived tokens.
Set its public URL to `http://keycloak.example.test`. Set its internal URL to
`http://127.0.0.1:3205` and its realm to `platform`. Use a fake client secret and an
enabled Website User for service requests.

Copy both `tests/test_*_http.py` files into the same directory inside the web container.
From that directory, run the bench Python with `-m unittest test_auth_http test_identity_http`.
Set `PANE_PORT` to the test web port minus three. Set `PRESS_TEST_PANEL_URL` to the
configured `platform_panel_url`.

## License

AGPL-3.0. See [license.txt](license.txt).
