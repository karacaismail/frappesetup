# Press TR

Keycloak sign-in and identity synchronization for Press on Frappe 16.

## Installation

Use the isolated environment in [Press development setup](../../dev/press/README.md).
Install the current shared `oidc_verify` package from `backend/libs/oidc_verify` into the bench Python environment. The package must export `JwksUnavailable`. The login callback, logout notification and service routes require it.

Configure these site settings before starting the web process:

- `host_name` is the exact Press origin registered for the Keycloak callback.
- `keycloak_public_url` and `keycloak_realm` identify the issuer. Use
  `keycloak_internal_url` when the bench reaches Keycloak through a different address.
- `keycloak_client_id` and `keycloak_client_secret` identify the Keycloak client. Keep the secret in site configuration.
- `platform_panel_url` is where legacy Press login and signup pages redirect.
- `press_identity_sync_user` identifies a dedicated, enabled Website User without administrative roles.

Register the exact callback and logout notification addresses in the
[OpenAPI contract](../../contracts/press_tr.openapi.yaml).

## Upgrading to Press Identity

On an existing site, run `bench --site <site> clear-cache` before
`bench --site <site> migrate`. This refreshes Frappe's cached module paths.
The migration moves the two DocType definitions to Press Identity and preserves their records.

## Organization mapping

Run `bench --site <site> migrate` to add the unique `Team.keycloak_org_id` field.
The same customization expresses Press v0.154.1's disabled performance-tuning default
as `0`, the value Frappe 16 accepts for a Check field.

Identity Sync must only send verified Keycloak email addresses to `ensure_team`.
Press creates a team at sign-in only if the user has no team membership.
Press assigns the first member as the owner of a new team. An existing owner must
transfer ownership before Identity Sync can remove that member.

## Operations

Password login is off by default. To recover Administrator access, temporarily run
`bench --site <site> set-config -p press_tr_allow_admin_password_login true`.
Use the standard Frappe password login API from the private network as Administrator.
After recovery, set the same option to the JSON boolean `false`.
Other users can only sign in through Keycloak.

Keep direct backend access private. The trusted proxy must overwrite
`X-Forwarded-For` so the request limits use the actual client address.

Review on MariaDB 11.8 uses the default repeatable-read transaction isolation.
Membership updates reset the read snapshot before acquiring a locking Team document.
Frappe locks its child membership rows as well. The first write follows the lock.
The lock behavior does not depend on MariaDB returning snapshot error 1020.
Tests can run with `innodb_snapshot_isolation` enabled or disabled.

## Local HTTP tests

Start and migrate the disposable `fs-press-tr` environment first. Set
`keycloak_client_id` to `press` and use a fake client secret.
Set the test issuer public URL to `http://keycloak.example.test`, its internal URL
to `http://127.0.0.1:3205`, and its realm to `platform`.
Set the site origin to HTTP for the local test and configure an enabled Website User
for service requests. Set `throttle_user_limit` to `300` on this disposable site to allow repeated test runs.
Set `PRESS_TEST_PANEL_URL` to the site's `platform_panel_url`.

From the repository root, run this command. It starts a temporary bench web process,
runs the checks, and stops that process. It creates fictional users, teams and sessions.

```sh
PRESS_TEST_PANEL_URL=http://tenant1.localhost:3201/panel sh backend/apps/press_tr/tests/run.sh
```

## License

AGPL-3.0. See [license.txt](license.txt).
