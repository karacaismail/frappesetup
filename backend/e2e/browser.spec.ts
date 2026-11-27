import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { parseBrand } from '../../src/lib/brand.mjs';
import { account, localUrl, required } from './local';

const { PRODUCT_NAME } = parseBrand(readFileSync(new URL('../brand.env', import.meta.url), 'utf8'));
const escapedProductName = PRODUCT_NAME.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const loginLinkName = new RegExp(`^(Sign in with ${escapedProductName}|${escapedProductName} ile oturum aç)$`, 'i');

async function login(page: Page, entry: 'button' | 'api') {
  const site = localUrl('tenant1.localhost', 1);
  const identity = localUrl('identity.localhost', 0);
  const blockedOrigins = new Set<string>();
  await page.route('**/*', async (route) => {
    const origin = new URL(route.request().url()).origin;
    if (origin === site || origin === identity) await route.continue();
    else {
      blockedOrigins.add(origin);
      await route.abort();
    }
  });

  if (entry === 'button') {
    await page.goto(`${site}/panel`);
    await page.getByRole('link', { name: loginLinkName }).click();
  } else {
    const response = await page.request.post(`${site}/api/method/platform_core.api.auth.get_login_url`, {
      data: { redirect_to: '/panel' }, maxRedirects: 0,
    });
    expect(response.status()).toBe(200);
    const { login_url } = (await response.json()).message;
    expect(new URL(login_url).origin).toBe(identity);
    await page.goto(login_url);
  }
  await expect.poll(() => new URL(page.url()).origin).toBe(identity);
  const loginParameters = new URL(page.url()).searchParams;
  expect(loginParameters.get('client_id')).toBe('site-tenant1');
  expect((loginParameters.get('scope') ?? '').split(/\s+/)).not.toContain('aud-identity-sync');
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
  const { blockedOrigins } = await login(page, 'button');
  expect([...blockedOrigins]).toEqual([]);
});

test('Keycloak logout closes the tenant session within 60 seconds', async ({ page }) => {
  test.setTimeout(90_000);
  const { identity, currentUser, blockedOrigins } = await login(page, 'api');
  await page.goto(`${identity}/realms/platform/protocol/openid-connect/logout`);
  await page.locator('#kc-logout').click();
  await expect.poll(currentUser, { timeout: 60_000 }).toBe('Guest');
  expect([...blockedOrigins]).toEqual([]);
});
