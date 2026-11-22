import { expect, test } from "@playwright/test";

// Password form of the tenant /login page. It exists only while kimlik_yalniz_keycloak is 0
// (see README.md). Rule E-9: one double click sends one request, and a failed sign-in shows the alert.
test.describe("tenant /login with the Keycloak-only gate off", () => {
	test("a double click sends one sign-in request and a failure shows the alert", async ({ page }) => {
		await page.goto("/login");
		const form = page.locator("form[data-login-endpoint]");
		test.skip((await form.count()) === 0, "The gate is on. Run this spec with kimlik_yalniz_keycloak=0.");

		let posts = 0;
		let releaseResponse!: () => void;
		const waitForDoubleClick = new Promise<void>((resolve) => {
			releaseResponse = resolve;
		});
		await page.route("**/api/method/login", async (route) => {
			posts += 1;
			await waitForDoubleClick;
			await route.fulfill({ status: 401, contentType: "application/json", body: '{"exc_type":"AuthenticationError"}' });
		});
		await page.locator("#usr").fill("ornek@example.test");
		await page.locator("#pwd").fill("yanlis-parola");
		try {
			await page.locator("button[type=submit]").dblclick();
		} finally {
			releaseResponse();
		}
		const alert = page.getByRole("alert");
		await expect(alert).toBeVisible();
		await expect(alert).not.toHaveText("");
		expect(posts).toBe(1);
		await expect(page.locator("button[type=submit]")).toBeEnabled();
	});
});
