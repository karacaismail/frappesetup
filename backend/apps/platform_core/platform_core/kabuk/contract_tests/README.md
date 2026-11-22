# Shell contract tests

Use the isolated `test-kabuk.localhost` site and its synthetic
`Kabuk Test Record` fixture. The HTTP fixture suite creates that record.
Set `PANEL_TEST_URL`, `PANEL_TEST_USERNAME` and `PANEL_TEST_PASSWORD` as for
the panel browser tests. Run from the repository root.

```sh
uv run --no-project --with openapi-spec-validator==0.7.2 python backend/apps/platform_core/platform_core/kabuk/contract_tests/responses.py
```

This uses the existing OpenAPI validation tool's JSON Schema dependency.
The suite validates live JSON, contract examples, declared headers and empty
304 responses. Frappe does not need this dependency at runtime.

Cookie-based clients can request the mobile projection with `surface=mobile`.
The metadata service also forces this projection when the verified identity
hook has established `mobile_identity`, regardless of the requested surface.
Mobile bearer tokens remain limited to the mobile API. That API must call the
metadata service through its verified route when it adds metadata delivery.

Set
`shell_mobile_doctypes` in the site's configuration to an array of permitted
DocType names. An absent list admits no mobile DocTypes. Mark whole DocTypes
as restricted using `shell_restricted_doctypes`. Fields with elevated
permission levels and Password fields are also restricted on mobile.
For absolute navigation URLs, configure `shell_navigation_hosts` as an array
of exact hostnames. Relative same-origin links require no host entry.
