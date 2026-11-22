# Press TR

Keycloak sign-in and identity synchronization for Press on Frappe 16.

## Installation

Use the isolated environment in [Press development setup](../../dev/press/README.md).
The Press image builds the shared `oidc_verify` wheel from `backend/libs/oidc_verify`.
The Bench setup installs that wheel together with `press_tr`.
The package exports `JwksUnavailable`. The login callback, logout notification and service routes require it.

Configure these site settings before starting the web process:

- `host_name` is the exact Press origin registered for the Keycloak callback.
- `keycloak_public_url` and `keycloak_realm` identify the issuer. Use
  `keycloak_internal_url` when the bench reaches Keycloak through a different address.
- `keycloak_client_id` and `keycloak_client_secret` identify the Keycloak client. Keep the secret in site configuration.
- `platform_panel_url` is where legacy Press login and signup pages redirect.
- `press_identity_sync_user` identifies a dedicated, enabled Website User without administrative roles.

Register the exact callback and logout notification addresses in the
[OpenAPI contract](../../contracts/press_tr.openapi.yaml).

## Organization mapping

Run `bench --site <site> migrate` to add the unique `Team.keycloak_org_id` field.
The same customization expresses Press v0.154.1's disabled performance-tuning default
as `0`, the value Frappe 16 accepts for a Check field.

Identity Sync must only send verified Keycloak email addresses to `ensure_team`.
Press creates a team at sign-in only if the user has no team membership.
Press assigns the first member as the owner of a new team. Single-team removal
requires an ownership transfer before removing an owner. Bulk deactivation removes
memberships and credentials while preserving the recorded team owner. A System Manager
can transfer ownership. Provisioning can add members and returns `owner_disabled: true` when the recorded owner is disabled. Re-enable a disabled Press account separately if needed.

## Operations

For Administrator recovery, run `bench --site <site> browse --user Administrator`
on the Press host. This opens an Administrator session without enabling password login.

Keep direct backend access private. Include
[`forwarded-client.conf`](../../dev/press/forwarded-client.conf) in the public proxy
location so request limits use the address seen by that proxy. If a load balancer
sits in front of Nginx, configure real-IP handling for the explicit trusted balancer
addresses first. Do not use a forwarding header from an untrusted client.

The request hook adds only documented RPC paths to Press's in-memory
`press.auth.ALLOWED_PATHS` before Press runs its own authentication hook. This
preserves native machine checks. The test suite requires Press tag `v0.154.1` so
an upgrade reopens review of the allowlist and webhook credentials.

A System Manager can run `press_tr.api.maintenance.cleanup_expired_sessions` with
an authenticated POST to remove expired Press session mappings.

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
PRESS_TEST_PANEL_URL=http://kiraci1.localhost:3201/panel sh backend/apps/press_tr/tests/run.sh
```

## License

AGPL-3.0. See [license.txt](license.txt).
