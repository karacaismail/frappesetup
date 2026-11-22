# Panel browser tests

Use an isolated Frappe site named `test-kabuk.localhost` with `platform_core`
installed. Run `bench build --app platform_core` to publish the panel assets.
Serve the site through a loopback port. Set `PANEL_TEST_URL` to that origin and
provide a synthetic account through `PANEL_TEST_USERNAME` and
`PANEL_TEST_PASSWORD`.

Run from the repository root with its installed dependencies and browser engines.

```sh
node_modules/.bin/playwright test --config backend/apps/platform_core/platform_core/kabuk/browser_tests/playwright.config.ts
```

The suite runs Chromium and WebKit. It saves screenshots under
`.pane/scratch/panel-browser-results` unless `PANEL_TEST_OUTPUT` is set.
The axe checks cover automated WCAG 2.2 AA rules.

The WebKit keyboard tests use Option+Tab to reach links with macOS's default
link-navigation preference. Chromium uses Tab.
