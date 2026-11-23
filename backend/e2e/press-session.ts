import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { localUrl, required } from './local';

const LOGIN_METHOD = '/api/method/platform_core.api.auth.get_login_url';
const PRESS_LOGIN_METHOD = '/api/method/press_tr.api.auth.get_login_url';
const DELETION_METHOD = '/api/method/press_tr.api.account.request_deletion';

export function sites() {
  return {
    tenant: localUrl('tenant1.localhost', 1),
    identity: localUrl('identity.localhost', 0),
    press: localUrl('press.localhost', 3),
  };
}

export function fixtureEmail(name: string, purpose: 'delete' | 'employee') {
  const email = required(name);
  if (!new RegExp(`^e2e-${purpose}-[a-z0-9-]+@example\\.test$`).test(email)) {
    throw new Error('Use a dedicated synthetic account for this lifecycle test.');
  }
  return email;
}

export function bearer(token: string) {
  return { Authorization: 'Bearer ' + token };
}

export function tokenClaims(token: string) {
  const [, encoded] = token.split('.');
  return JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'));
}

export async function signIn(page: Page, email: string, password: string, site: 'tenant' | 'press' = 'tenant') {
  const origins = sites();
  const origin = origins[site];
  const { identity } = origins;
  await page.route('**/*', async (route) => {
    const requestOrigin = new URL(route.request().url()).origin;
    if (requestOrigin === origin || requestOrigin === identity) await route.continue();
    else await route.abort();
  });
  const pressLogin = site === 'press';
  const method = pressLogin ? PRESS_LOGIN_METHOD : LOGIN_METHOD;
  const response = await page.request.post(origin + method, {
    data: pressLogin ? {} : { redirect_to: '/panel' }, maxRedirects: 0,
  });
  expect(response.status()).toBe(200);
  const { message } = await response.json();
  const login = new URL(pressLogin ? message.url : message.login_url);
  expect(login.origin).toBe(identity);
  await page.goto(login.href);
  await enterCredentials(page, email, password);
}

export async function enterCredentials(page: Page, email: string, password: string) {
  await expect.poll(() => new URL(page.url()).origin).toBe(sites().identity);
  const username = page.locator('#username');
  if (await username.isVisible()) await username.fill(email);
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
}

export async function resource(request: APIRequestContext, origin: string, cookie: string, doctype: string, name: string) {
  const response = await request.get(origin + '/api/resource/' + [doctype, name].map(encodeURIComponent).join('/'), {
    headers: { Cookie: cookie }, maxRedirects: 0,
  });
  expect(response.status()).toBe(200);
  return (await response.json()).data;
}

/** The customer's own deletion request on Press: sign in, confirm with a fresh Keycloak login, submit. */
export async function requestPressDeletion(page: Page, email: string, password: string) {
  const { press, identity } = sites();
  await signIn(page, email, password, 'press');
  await expect.poll(() => new URL(page.url()).origin).toBe(press);
  await page.goto(press + '/account-deletion');
  const form = page.locator('#account-deletion');
  await expect(form).toHaveAttribute('data-confirm', 'false');

  const reauthentication = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.origin === identity && url.pathname.endsWith('/protocol/openid-connect/auth');
  });
  await form.locator('button[type=submit]').click();
  const login = new URL((await reauthentication).url());
  expect(login.searchParams.get('prompt')).toBe('login');
  expect(login.searchParams.get('max_age')).toBe('0');
  await enterCredentials(page, email, password);
  await expect(form).toHaveAttribute('data-confirm', 'true');
  expect(new URL(page.url()).origin).toBe(press);
  const submission = page.waitForResponse((response) =>
    response.url() === press + DELETION_METHOD && response.request().method() === 'POST');
  await form.locator('button[type=submit]').click();
  const submitted = await submission;
  expect(submitted.request().postDataJSON()).toMatchObject({ confirm: true });
  expect(submitted.status()).toBe(200);
  return (await submitted.json()).message as Record<string, unknown>;
}

/** A Keycloak Admin API token that may only read users. The stack seed writes the client and its secret. */
export async function keycloakReaderToken(request: APIRequestContext) {
  const given = process.env.E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN;
  if (given) return given;
  const response = await request.post(sites().identity + '/realms/platform/protocol/openid-connect/token', {
    form: {
      grant_type: 'client_credentials', scope: 'kc-admin-api',
      client_id: required('E2E_LIFECYCLE_READER_CLIENT'), client_secret: required('E2E_LIFECYCLE_READER_SECRET'),
    },
    maxRedirects: 0,
  });
  expect(response.status(), 'Keycloak reader token').toBe(200);
  const token = (await response.json()).access_token;
  if (typeof token !== 'string' || !token) throw new Error('Keycloak reader token is missing.');
  return token;
}

/**
 * Closes a fixture session on a Frappe site. The seed opened it for one test run.
 * Returns the HTTP status, or 0 when the site did not answer. It never throws, so a caller
 * can close every session and check the results after its own assertions.
 */
export async function closeSession(request: APIRequestContext, origin: string, cookie: string) {
  try {
    const response = await request.post(origin + '/api/method/logout', { headers: { Cookie: cookie }, maxRedirects: 0 });
    return response.status();
  } catch {
    return 0;
  }
}
