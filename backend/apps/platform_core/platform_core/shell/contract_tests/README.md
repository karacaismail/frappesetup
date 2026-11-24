# Shell contract tests

Use the isolated `test-kabuk.localhost` site and its synthetic
`Kabuk Test Record` fixture. The HTTP fixture suite creates that record.
Set `PANEL_TEST_URL`, `PANEL_TEST_USERNAME` and `PANEL_TEST_PASSWORD` as for
the panel browser tests. Run from the repository root.

```sh
uv run --no-project --with openapi-spec-validator==0.7.2 python backend/apps/platform_core/platform_core/shell/contract_tests/responses.py
```

This uses the existing OpenAPI validation tool's JSON Schema dependency.
The suite validates live JSON, contract examples, declared headers and empty
304 responses. Frappe does not need this dependency at runtime.

Mobile metadata is available only when the identity hook has verified the
mobile account and the request is on a mobile API route. Browser clients do
not gain mobile access by selecting `surface=mobile`. Website Users never
receive restricted fields through the shell metadata endpoint.

Set `shell_mobile_doctypes` to the site's allowed DocType names. An absent
list admits no mobile DocTypes. Use `shell_restricted_doctypes` for restricted
types and `shell_restricted_fields` for a mapping from DocType names to
restricted field names. Masked fields, Password fields and elevated
permission levels are also restricted. Validate configuration locally with
`bench --site <site> execute platform_core.shell.metadata_policy.validate_mobile_policy`.
An invalid mobile allowlist blocks mobile metadata only. Invalid restricted DocType or field
configuration also blocks metadata for users without desktop access.
System Managers can also run the check with `GET /api/method/platform_core.api.meta.validate_mobile_policy`.
Unknown names cause the mobile metadata service to fail closed.

The official Frappe runner checks projection components using
`tests/shell_contract_components.json`. The live suite enforces parity with
the authoritative OpenAPI schemas. From the repository root, regenerate
the snapshot whenever a covered component changes:

```sh
python3 backend/apps/platform_core/platform_core/shell/contract_tests/generate_snapshot.py
```

Add `--check` to verify that the tracked snapshot matches without writing it.

For absolute navigation URLs, configure `shell_navigation_hosts` as an array
of exact hostnames. Relative same-origin links require no host entry.
