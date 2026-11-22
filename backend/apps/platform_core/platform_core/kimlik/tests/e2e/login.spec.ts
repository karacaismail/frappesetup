import { expect, test, type Page } from "@playwright/test";

const START = "/api/method/platform_core.api.auth.start_login";
const LABEL = "Atonota ile oturum aç";

async function fontSizes(page: Page) {
	return page.evaluate(() => {
		const out: { tag: string; size: number; text: string }[] = [];
		for (const el of Array.from(document.body.querySelectorAll<HTMLElement>("*"))) {
			const text = (el.childNodes[0]?.nodeType === Node.TEXT_NODE ? el.textContent : "")?.trim() ?? "";
			if (!text) continue;
			const style = getComputedStyle(el);
			if (style.display === "none" || style.visibility === "hidden") continue;
			out.push({ tag: el.tagName, size: parseFloat(style.fontSize), text: text.slice(0, 30) });
		}
		return out;
	});
}

test.describe("tenant /login with the Keycloak-only gate on", () => {
	test("shows only the brand button, in Outfit, readable from 320 px", async ({ page }) => {
		await page.goto("/login?redirect-to=/panel");
		await expect(page.locator('[data-page="platform-core-login"]')).toHaveCount(1);
		const button = page.getByRole("link", { name: LABEL });
		await expect(button).toHaveCount(1);
		await expect(button).toHaveAttribute("href", `${START}?redirect_to=%2Fpanel`);
		await expect(page.locator('input[type="password"]')).toHaveCount(0);
		await expect(page.locator("form")).toHaveCount(0);

		const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
		expect(overflow, "no horizontal page overflow").toBeLessThanOrEqual(0);

		const sizes = await fontSizes(page);
		expect(sizes.length).toBeGreaterThan(0);
		for (const item of sizes) expect(item.size, `${item.tag} "${item.text}"`).toBeGreaterThanOrEqual(14);
		const body = await page.evaluate(() => parseFloat(getComputedStyle(document.body).fontSize));
		expect(body).toBeGreaterThanOrEqual(16);

		await page.evaluate(() => (document as any).fonts.ready);
		const family = await button.evaluate((el) => getComputedStyle(el).fontFamily);
		expect(family.toLowerCase().startsWith('"outfit"') || family.toLowerCase().startsWith("outfit")).toBeTruthy();
		const loaded = await page.evaluate(() => (document as any).fonts.check('16px "Outfit Variable"'));
		expect(loaded, "self-hosted Outfit loaded").toBeTruthy();

		const box = await button.boundingBox();
		expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
		const radius = await button.evaluate((el) => getComputedStyle(el).borderLeftWidth);
		expect(radius, "no coloured accent edge on a rounded box").toBe("0px");
	});

	test("keyboard focus is visible without a surrounding ring and only after Tab", async ({ page }) => {
		await page.goto("/login");
		const button = page.getByRole("link", { name: LABEL });
		await button.click({ trial: true });
		await page.mouse.click(5, 5);
		await button.focus();
		const afterMouse = await button.evaluate((el) => {
			const s = getComputedStyle(el);
			return { outline: s.outlineWidth, shadow: s.boxShadow, kbd: document.documentElement.hasAttribute("data-kbd") };
		});
		expect(afterMouse.kbd).toBeFalsy();
		expect(afterMouse.shadow).toBe("none");

		await page.mouse.click(5, 5);
		await page.keyboard.press("Tab");
		await expect(button).toBeFocused();
		const afterTab = await button.evaluate((el) => {
			const s = getComputedStyle(el);
			return { outline: s.outlineWidth, shadow: s.boxShadow, kbd: document.documentElement.hasAttribute("data-kbd") };
		});
		expect(afterTab.kbd).toBeTruthy();
		expect(afterTab.outline, "no outline ring").toBe("0px");
		expect(afterTab.shadow, "a visible non-surrounding indicator").not.toBe("none");
	});

	test("forced colours use the single allowed outline", async ({ page }) => {
		await page.emulateMedia({ forcedColors: "active" });
		await page.goto("/login");
		await page.keyboard.press("Tab");
		const button = page.getByRole("link", { name: LABEL });
		await expect(button).toBeFocused();
		const outline = await button.evaluate((el) => getComputedStyle(el).outlineWidth);
		expect(outline).toBe("2px");
	});

	test("dark scheme redefines the tokens", async ({ page }) => {
		await page.goto("/login");
		const light = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
		await page.emulateMedia({ colorScheme: "dark" });
		const dark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
		expect(dark).not.toBe(light);
	});

	test("the button starts the Keycloak flow with PKCE and a browser cookie", async ({ page, context }) => {
		let authorize = "";
		await page.route("**/realms/platform/protocol/openid-connect/auth**", async (route) => {
			authorize = route.request().url();
			await route.fulfill({ status: 200, contentType: "text/html", body: "<title>keycloak stub</title>" });
		});
		await page.goto("/login?redirect-to=/panel");
		await page.getByRole("link", { name: LABEL }).click();
		await page.waitForURL(/realms\/platform/);
		const url = new URL(authorize);
		expect(url.searchParams.get("code_challenge_method")).toBe("S256");
		expect(url.searchParams.get("state")?.length ?? 0).toBeGreaterThanOrEqual(32);
		expect(url.searchParams.get("nonce")?.length ?? 0).toBeGreaterThanOrEqual(32);
		expect(url.searchParams.get("redirect_uri")).toContain("/api/method/platform_core.api.auth.keycloak_callback");
		const cookie = (await context.cookies()).find((c) => c.name === "kimlik_login");
		expect(cookie?.httpOnly).toBeTruthy();
		expect(cookie?.sameSite).toBe("Lax");
	});
});
