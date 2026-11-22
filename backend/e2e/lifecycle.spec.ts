import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { localUrl, required } from './local';

const LOGIN_METHOD = '/api/method/platform_core.api.auth.get_login_url';
const LOGGED_USER = '/api/method/frappe.auth.get_logged_user';
const CALLBACK = '/api/method/platform_core.api.auth.keycloak_callback';
const IDLE_MS = 60 * 60 * 1000;

function sites() {
  return {
    tenant: localUrl('kiraci1.localhost', 1),
    identity: localUrl('kimlik.localhost', 0),
    press: localUrl('press.localhost', 3),
  };
}

function fixtureEmail(name: string, purpose: 'delete' | 'employee') {
  const email = required(name);
  if (!new RegExp(`^e2e-${purpose}-[a-z0-9-]+@example\\.test$`).test(email)) {
    throw new Error('Use a dedicated synthetic account for this lifecycle test.');
  }
  return email;
}

function bearer(token: string) {
  return { Authorization: 'Bearer ' + token };
}

function tokenClaims(token: string) {
  const [, encoded] = token.split('.');
  return JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'));
}

async function signIn(page: Page, email: string, password: string, site: 'tenant' | 'press' = 'tenant') {
  const origins = sites();
  const origin = origins[site];
  const { identity } = origins;
  await page.route('**/*', async (route) => {
    const requestOrigin = new URL(route.request().url()).origin;
    if (requestOrigin === origin || requestOrigin === identity) await route.continue();
    else await route.abort();
  });
  const pressLogin = site === 'press';
  const method = pressLogin ? '/api/method/press_tr.api.auth.get_login_url' : LOGIN_METHOD;
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

async function enterCredentials(page: Page, email: string, password: string) {
  await expect.poll(() => new URL(page.url()).origin).toBe(sites().identity);
  const username = page.locator('#username');
  if (await username.isVisible()) await username.fill(email);
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
}

async function loggedUser(request: APIRequestContext) {
  const response = await request.get(sites().tenant + LOGGED_USER, { maxRedirects: 0 });
  if ([401, 403].includes(response.status())) return 'Guest';
  expect(response.status()).toBe(200);
  return (await response.json()).message;
}

function mobilePull(request: APIRequestContext, token: string, installation: string) {
  return request.post(sites().tenant + '/api/method/platform_core.api.mobile.v1_pull', {
    headers: { ...bearer(token), 'X-Mobile-App-Version': '1.0.0', 'X-Mobile-Contract-Version': '1' },
    data: { installation_id: installation }, maxRedirects: 0,
  });
}

function keycloakUser(request: APIRequestContext, subject: string, suffix = '') {
  return request.get(sites().identity + '/admin/realms/platform/users/' + encodeURIComponent(subject) + suffix, {
    headers: bearer(required('E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN')), maxRedirects: 0,
  });
}

async function resource(request: APIRequestContext, origin: string, cookie: string, doctype: string, name: string) {
  const response = await request.get(origin + '/api/resource/' + [doctype, name].map(encodeURIComponent).join('/'), {
    headers: { Cookie: cookie }, maxRedirects: 0,
  });
  expect(response.status()).toBe(200);
  return (await response.json()).data;
}

test.describe('Press account deletion', () => {
  test.skip(() => process.env.E2E_ACCOUNT_DELETION !== '1',
    'Requires the Press deletion page, identity-sync deletion workflow and dedicated synthetic fixtures.');

  test('customer self-deletion closes Press, tenant and mobile access', async ({ page, request }) => {
    test.setTimeout(120_000);
    const { tenant, press } = sites();
    const email = fixtureEmail('E2E_DELETE_EMAIL', 'delete');
    const subject = required('E2E_DELETE_SUBJECT');
    const tenantReader = required('E2E_DELETE_TENANT_READER_COOKIE');
    const pressReader = required('E2E_DELETE_PRESS_READER_COOKIE');
    const pressKey = required('E2E_DELETE_PRESS_AUTHORIZATION');
    const mobileToken = required('E2E_DELETE_MOBILE_TOKEN');
    expect(tokenClaims(mobileToken).sub === subject).toBe(true);
    const installation = required('E2E_DELETE_INSTALLATION');
    const readUser = (origin: string, cookie: string, name = email) =>
      resource(request, origin, cookie, 'User', name);
    const pressAccess = () => request.get(press + LOGGED_USER, {
      headers: { Authorization: pressKey }, maxRedirects: 0,
    });
    const business = {
      doctype: required('E2E_DELETE_RECORD_DOCTYPE'),
      name: required('E2E_DELETE_RECORD_NAME'),
      field: required('E2E_DELETE_RECORD_PERSON_FIELD'),
      anonymous: required('E2E_DELETE_RECORD_ANONYMOUS_VALUE'),
    };
    const readBusinessValue = async () =>
      (await resource(request, tenant, tenantReader, business.doctype, business.name))[business.field];

    const account = await keycloakUser(request, subject);
    expect(account.status()).toBe(200);
    const user = await account.json();
    expect(user.email === email && user.enabled === true).toBe(true);
    expect((await readUser(tenant, tenantReader)).enabled).toBe(1);
    expect((await readUser(press, pressReader)).enabled).toBe(1);
    const pressSession = await pressAccess();
    expect(pressSession.status()).toBe(200);
    expect((await pressSession.json()).message === email).toBe(true);
    expect((await mobilePull(request, mobileToken, installation)).status()).toBe(200);
    const before = await readBusinessValue();
    const anonymous = JSON.parse(business.anonymous);
    expect(before).not.toEqual(anonymous);

    const password = required('E2E_DELETE_PASSWORD');
    await signIn(page, email, password, 'press');
    await expect.poll(() => new URL(page.url()).origin).toBe(press);
    const deletionPage = press + '/account-deletion';
    await page.goto(deletionPage);
    const form = page.locator('#account-deletion');
    await expect(form).toHaveAttribute('data-confirm', 'false');

    const reauthentication = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.origin === sites().identity && url.pathname.endsWith('/protocol/openid-connect/auth');
    });
    await form.locator('button[type=submit]').click();
    const login = new URL((await reauthentication).url());
    expect(login.searchParams.get('prompt')).toBe('login');
    expect(login.searchParams.get('max_age')).toBe('0');
    await enterCredentials(page, email, password);
    await expect(form).toHaveAttribute('data-confirm', 'true');
    expect(new URL(page.url()).origin).toBe(press);
    const submission = page.waitForResponse((response) =>
      response.url() === press + '/api/method/press_tr.api.account.request_deletion'
      && response.request().method() === 'POST');
    await form.locator('button[type=submit]').click();
    const submitted = await submission;
    expect(submitted.request().postDataJSON()).toMatchObject({ confirm: true });
    expect(submitted.status()).toBe(200);
    expect((await submitted.json()).message).toMatchObject({ submitted: true });

    await expect.poll(async () => (await keycloakUser(request, subject)).status(), { timeout: 60_000 }).toBe(404);
    const pressAnonymous = required('E2E_DELETE_PRESS_ANONYMOUS_USER');
    const tenantAnonymous = required('E2E_DELETE_TENANT_ANONYMOUS_USER');
    expect((await readUser(press, pressReader, pressAnonymous)).enabled).toBe(0);
    expect((await readUser(tenant, tenantReader, tenantAnonymous)).enabled).toBe(0);
    for (const [origin, cookie] of [[press, pressReader], [tenant, tenantReader]]) {
      const previous = await request.get(origin + '/api/resource/User/' + encodeURIComponent(email), {
        headers: { Cookie: cookie }, maxRedirects: 0,
      });
      expect(previous.status()).toBe(404);
    }
    expect([401, 403]).toContain((await pressAccess()).status());
    expect([401, 403]).toContain((await mobilePull(request, mobileToken, installation)).status());
    expect(await readBusinessValue()).toEqual(anonymous);
  });
});

test('administrator revocation also terminates the Keycloak mobile session', async ({ request }) => {
  test.skip(process.env.E2E_MOBILE_SESSION_REVOKE !== '1',
    'Requires mobile bearer authentication, the administrator approval tool and identity-sync session revocation.');
  test.setTimeout(90_000);
  const { identity, tenant } = sites();
  const installation = required('E2E_REVOKE_INSTALLATION');
  const subject = required('E2E_REVOKE_SUBJECT');
  const token = required('E2E_REVOKE_MOBILE_TOKEN');
  const { sid, sub, preferred_username } = tokenClaims(token);
  expect(typeof sid === 'string' && sid.length > 0 && sub === subject
    && /^e2e-revoke-[a-z0-9-]+@example\.test$/.test(preferred_username)).toBe(true);

  const sessions = async () => {
    const response = await keycloakUser(request, subject, '/sessions');
    expect(response.status()).toBe(200);
    const rows: { id: string }[] = await response.json();
    return rows.some(({ id }) => id === sid);
  };
  const refresh = (refreshToken: string) => request.post(identity + '/realms/platform/protocol/openid-connect/token', {
    form: { grant_type: 'refresh_token', client_id: required('E2E_MOBILE_CLIENT_ID'), refresh_token: refreshToken },
    maxRedirects: 0,
  });
  expect(await sessions()).toBe(true);
  expect((await mobilePull(request, token, installation)).status()).toBe(200);
  const rotated = await refresh(required('E2E_REVOKE_MOBILE_REFRESH_TOKEN'));
  expect(rotated.status()).toBe(200);
  const next = (await rotated.json()).refresh_token;
  expect(typeof next).toBe('string');

  const method = tenant + '/api/method/platform_core.api.ai.';
  const headers = {
    Cookie: required('E2E_REVOKE_ADMIN_COOKIE'),
    'X-Frappe-CSRF-Token': required('E2E_REVOKE_ADMIN_CSRF'),
    'Mcp-Conversation-Id': randomUUID(),
  };
  const proposal = await request.post(method + 'mcp', {
    headers, maxRedirects: 0, data: {
      jsonrpc: '2.0', id: randomUUID(), method: 'tools/call',
      params: { name: 'platform_core_revoke_mobile_installation', arguments: { installation_id: installation } },
    },
  });
  expect(proposal.status()).toBe(200);
  const result = (await proposal.json()).result;
  expect(result.isError).toBe(false);
  const { proposal_id, status } = result.structuredContent;
  expect(status).toBe('approval_required');
  expect(await sessions()).toBe(true);

  const preview = await request.get(method + 'get_proposal', { headers, params: { proposal_id }, maxRedirects: 0 });
  expect(preview.status()).toBe(200);
  const { digest } = (await preview.json()).message;
  const approved = await request.post(method + 'approve_proposal', {
    headers, data: { proposal_id, digest }, maxRedirects: 0,
  });
  expect(approved.status()).toBe(200);
  expect((await approved.json()).message.executed).toBe(true);
  await expect.poll(sessions, { timeout: 30_000 }).toBe(false);
  expect([401, 403]).toContain((await mobilePull(request, token, installation)).status());
  const denied = await refresh(next);
  expect(denied.status()).toBe(400);
  expect((await denied.json()).error).toBe('invalid_grant');
});

async function keycloakStillSignedIn(page: Page) {
  const { identity, tenant } = sites();
  const state = randomUUID();
  const challenge = createHash('sha256').update(randomBytes(32).toString('base64url')).digest('base64url');
  const url = new URL(identity + '/realms/platform/protocol/openid-connect/auth');
  url.search = new URLSearchParams({
    client_id: 'site-kiraci1', response_type: 'code', scope: 'openid', state, prompt: 'none',
    redirect_uri: tenant + CALLBACK, code_challenge: challenge, code_challenge_method: 'S256',
  }).toString();
  const response = await page.request.get(url.href, { maxRedirects: 0 });
  const location = response.headers().location;
  if (!location) return false;
  const callback = new URL(location, identity);
  // Do not follow the callback. The Keycloak probe must not touch the tenant session.
  return callback.origin === tenant && callback.pathname === CALLBACK
    && callback.searchParams.get('state') === state && callback.searchParams.has('code');
}

test.describe('Employee idle session', () => {
  test.skip(() => process.env.E2E_EMPLOYEE_IDLE !== '1',
      'Requires the employee one-hour idle configuration and the tenant forced re-authentication flow.');

  test('employee must authenticate again after one hour idle despite live Keycloak SSO', async ({ page }) => {
    test.setTimeout(IDLE_MS + 180_000);
    const email = fixtureEmail('E2E_EMPLOYEE_EMAIL', 'employee');
    const password = required('E2E_EMPLOYEE_PASSWORD');
    await signIn(page, email, password);
    expect(await loggedUser(page.request)).toBe(email);
    const started = Date.now();
    await new Promise((resolve) => setTimeout(resolve, 55 * 60 * 1000));
    expect(await keycloakStillSignedIn(page)).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, Math.max(0, started + IDLE_MS + 2000 - Date.now())));
    expect(await keycloakStillSignedIn(page)).toBe(true);

    await page.goto(sites().tenant + '/panel');
    await expect.poll(() => new URL(page.url()).origin).toBe(sites().identity);
    await expect(page.locator('#password')).toBeVisible();
    await enterCredentials(page, email, password);
    await expect.poll(() => loggedUser(page.request)).toBe(email);
  });
});
