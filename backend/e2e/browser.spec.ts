import { expect, test, type Page } from '@playwright/test';
import { account, localUrl, required } from './local';

async function login(page: Page) {
  const site = localUrl('kiraci1.localhost', 1);
  const identity = localUrl('kimlik.localhost', 0);
  const blockedOrigins = new Set<string>();
  await page.route('**/*', async (route) => {
    const origin = new URL(route.request().url()).origin;
    if (origin === site || origin === identity) await route.continue();
    else {
      blockedOrigins.add(origin);
      await route.abort();
    }
  });

  await page.goto(`${site}/panel`);
  await page.getByRole('button', { name: 'Atonota ile oturum aç', exact: true }).click();
  await expect.poll(() => new URL(page.url()).origin).toBe(identity);
  await page.locator('#username').fill(account);
  await page.locator('#password').fill(required('E2E_KEYCLOAK_PASSWORD'));
  await page.locator('#kc-login').click();
  await expect.poll(() => new URL(page.url()).origin).toBe(site);

  const currentUser = async () => {
    const response = await page.request.get(`${site}/api/method/frappe.auth.get_logged_user`, {
      maxRedirects: 0,
      timeout: 4000,
    });
    if ([401, 403].includes(response.status())) return 'Guest';
    expect(response.ok()).toBe(true);
    return (await response.json()).message;
  };
  expect(await currentUser()).toBe(account);
  return { identity, currentUser, blockedOrigins };
}

test('tenant session opens through Keycloak', async ({ page }) => {
  const { blockedOrigins } = await login(page);
  expect([...blockedOrigins]).toEqual([]);
});

test('Keycloak logout closes the tenant session within 60 seconds', async ({ page }) => {
  test.setTimeout(90_000);
  const { identity, currentUser, blockedOrigins } = await login(page);
  await page.goto(`${identity}/realms/platform/protocol/openid-connect/logout`);
  await page.locator('#kc-logout').click();
  await expect.poll(currentUser, { timeout: 60_000 }).toBe('Guest');
  expect([...blockedOrigins]).toEqual([]);
});
