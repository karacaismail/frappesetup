import { defineConfig, devices } from "@playwright/test";

// Tenant /login page of platform_core. The site must run with kimlik_yalniz_keycloak=1
// (see kimlik/tests/e2e/README.md). Firefox is excluded by project policy.
const baseURL = process.env.KIMLIK_E2E_BASE_URL ?? "http://tenant1.localhost:8661";

const viewports = [320, 360, 375, 390, 1280];

export default defineConfig({
	testDir: ".",
	testMatch: /.*\.spec\.ts/,
	timeout: 30_000,
	retries: 0,
	reporter: [["list"]],
	use: {
		baseURL,
		extraHTTPHeaders: { "Accept-Language": "tr" },
		locale: "tr-TR",
	},
	projects: [
		...viewports.map((width) => ({
			name: `chromium-${width}`,
			use: { ...devices["Desktop Chrome"], viewport: { width, height: 720 } },
		})),
		...viewports.map((width) => ({
			name: `webkit-${width}`,
			use: { ...devices["Desktop Safari"], viewport: { width, height: 720 } },
		})),
	],
});
