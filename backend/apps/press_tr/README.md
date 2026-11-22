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

Register the exact callback and logout notification addresses in the
[OpenAPI contract](../../contracts/press_tr.openapi.yaml).

## License

AGPL-3.0. See [license.txt](license.txt).
