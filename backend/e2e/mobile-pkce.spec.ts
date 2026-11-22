import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { expect, request as apiRequest, test, type Browser } from '@playwright/test';
import { localUrl, required } from './local';

test.skip(process.env.E2E_MOBILE_PKCE !== '1', 'A public PKCE client and mobile token fixtures are required.');

async function authorize(browser: Browser, clientId: string, redirect: URL) {
  const identity = localUrl('kimlik.localhost', 0);
  const verifier = randomBytes(32).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const state = randomUUID();
  const browserContext = await browser.newContext();
  try {
    const page = await browserContext.newPage();
    let code: string | null = null;
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.origin === redirect.origin && url.pathname === redirect.pathname && url.searchParams.get('state') === state) {
        code = url.searchParams.get('code');
      }
    });
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin === redirect.origin && url.pathname === redirect.pathname) {
        await route.fulfill({ status: 200, body: 'Local mobile callback' });
      } else if (url.origin === identity) {
        await route.continue();
      } else {
        await route.abort();
      }
    });
    const url = new URL(identity + '/realms/platform/protocol/openid-connect/auth');
    url.search = new URLSearchParams({
      redirect_uri: redirect.href, client_id: clientId, response_type: 'code',
      scope: required('E2E_MOBILE_SCOPE'), state, code_challenge: challenge, code_challenge_method: 'S256',
    }).toString();
    const email = required('E2E_MOBILE_EMAIL');
    if (!email.endsWith('@example.test')) throw new Error('Use a synthetic mobile account.');
    await page.goto(url.href);
    await page.locator('#username').fill(email);
    await page.locator('#password').fill(required('E2E_MOBILE_PASSWORD'));
    await page.locator('#kc-login').click();
    await expect.poll(() => code !== null).toBe(true);
    return { code: code!, verifier };
  } finally {
    await browserContext.close();
  }
}

function claims(token: string) {
  const [, payload] = token.split('.');
  return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
}

test('public PKCE client gets a token restricted to mobile endpoints', async ({ browser }) => {
  const identity = localUrl('kimlik.localhost', 0);
  const site = localUrl('kiraci1.localhost', 1);
  const methods = site + '/api/method/';
  const clientId = required('E2E_MOBILE_CLIENT_ID');
  const redirect = new URL(required('E2E_MOBILE_REDIRECT_URI'));
  if (redirect.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(redirect.hostname)
      || redirect.search || redirect.hash || redirect.username || redirect.password) {
    throw new Error('Use a dedicated loopback redirect URI for the preview client.');
  }

  const context = await apiRequest.newContext();
  try {
    const exchange = ({ code, verifier }: { code: string; verifier: string }) => context.post(
      identity + '/realms/platform/protocol/openid-connect/token',
      { maxRedirects: 0, form: {
        grant_type: 'authorization_code', code, redirect_uri: redirect.href,
        client_id: clientId, code_verifier: verifier,
      } },
    );
    const mismatch = await authorize(browser, clientId, redirect);
    const denied = await exchange({ code: mismatch.code, verifier: randomBytes(32).toString('base64url') });
    expect(denied.status()).toBe(400);

    const response = await exchange(await authorize(browser, clientId, redirect));
    expect(response.status()).toBe(200);
    const { access_token: token, token_type } = await response.json();
    expect(token_type).toBe('Bearer');
    expect(typeof token).toBe('string');
    const audience = required('E2E_MOBILE_AUDIENCE');
    const payload = claims(token);
    expect(payload.iss === identity + '/realms/platform' && payload.azp === clientId).toBe(true);
    expect([payload.aud].flat().includes(audience)).toBe(true);

    const headers = {
      'X-Mobile-App-Version': '1.0.0', 'X-Mobile-Contract-Version': '1',
    };
    const postMobile = (method: string, accessToken?: string, cookie?: string, extra = {}) => context.post(
      methods + 'platform_core.api.mobile.v1_' + method,
      { maxRedirects: 0,
        headers: { ...headers, ...(accessToken ? { Authorization: 'Bearer ' + accessToken } : {}),
          ...(cookie ? { Cookie: cookie } : {}) },
        data: { installation_id: randomUUID(), ...extra },
      },
    );
    const installation = randomUUID();
    const device = { installation_id: installation };
    const registered = await postMobile('register', token, 'sid=Guest', device);
    expect(registered.status()).toBe(200);
    expect((await registered.json()).message).toMatchObject(device);
    const pulled = await postMobile('pull', token, undefined, device);
    expect(pulled.status()).toBe(200);
    const page = (await pulled.json()).message;
    expect(Array.isArray(page.changes) && typeof page.cursor === 'string' && typeof page.has_more === 'boolean').toBe(true);

    const expired = required('E2E_MOBILE_EXPIRED_TOKEN');
    const expiredClaims = claims(expired);
    expect(expiredClaims.iss === payload.iss && [expiredClaims.aud].flat().includes(audience)
      && expiredClaims.exp < Math.floor(Date.now() / 1000) - 60).toBe(true);
    const wrong = required('E2E_MOBILE_WRONG_AUDIENCE_TOKEN');
    const wrongClaims = claims(wrong);
    expect(wrongClaims.iss === payload.iss && ![wrongClaims.aud].flat().includes(audience)
      && wrongClaims.exp > Math.floor(Date.now() / 1000)).toBe(true);

    for (const invalid of [undefined, expired, wrong, 'eyJhbGciOiJub25lIn0.e30.']) {
      expect([401, 403]).toContain((await postMobile('pull', invalid, undefined, device)).status());
    }
    expect([400, 401, 403]).toContain(
      (await postMobile('pull', token, required('E2E_MOBILE_SESSION_COOKIE'), device)).status(),
    );
    expect([400, 401, 403]).toContain(
      (await postMobile('pull', token, undefined, { ...device, cmd: 'ping' })).status(),
    );
    const outside = await context.get(methods + 'frappe.auth.get_logged_user', {
      headers: { Authorization: 'Bearer ' + token }, maxRedirects: 0,
    });
    expect([401, 403]).toContain(outside.status());

    const preflight = await context.fetch(methods + 'platform_core.api.mobile.v1_pull', {
      method: 'OPTIONS',
      headers: { Origin: required('E2E_MOBILE_ORIGIN'), 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,x-mobile-app-version,x-mobile-contract-version' },
      maxRedirects: 0,
    });
    expect(preflight.ok()).toBe(true);
    expect((await postMobile('revoke', token, undefined, device)).status()).toBe(200);
  } finally {
    await context.dispose();
  }
});
