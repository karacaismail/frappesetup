import { randomBytes, randomUUID } from 'node:crypto';
import { expect, request as apiRequest, test } from '@playwright/test';
import { localUrl, required } from './local';
import { authorizeMobile, previewMobileToken } from './mobile-fixture';
import { postMobile } from './mobile-request';

const fullPreview = process.env.E2E_FULL_BROWSER_FIXTURES === '1';

test.skip(process.env.E2E_MOBILE_PKCE !== '1', 'A public PKCE client and mobile token fixtures are required.');

function claims(token: string) {
  const [, payload] = token.split('.');
  return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
}

test('public PKCE client gets a token restricted to mobile endpoints', async ({ browser }) => {
  test.setTimeout(fullPreview ? 155_000 : 30_000);
  const identity = localUrl('identity.localhost', 0);
  const site = localUrl('tenant1.localhost', 1);
  const methods = site + '/api/method/';
  const clientId = required('E2E_MOBILE_CLIENT_ID');
  const redirect = new URL(required('E2E_MOBILE_REDIRECT_URI'));

  const context = await apiRequest.newContext();
  try {
    const exchange = ({ code, verifier }: { code: string; verifier: string }) => context.post(
      identity + '/realms/platform/protocol/openid-connect/token',
      { maxRedirects: 0, form: {
        grant_type: 'authorization_code', code, redirect_uri: redirect.href,
        client_id: clientId, code_verifier: verifier,
      } },
    );
    const email = required('E2E_MOBILE_EMAIL');
    const password = required('E2E_MOBILE_PASSWORD');
    const expired = fullPreview ? (await previewMobileToken(browser, context, email, password,
      required('E2E_MOBILE_EXPIRED_CLIENT_ID'))).access : required('E2E_MOBILE_EXPIRED_TOKEN');
    const wrong = fullPreview ? (await previewMobileToken(browser, context, email, password, clientId,
      'openid mobile')).access : required('E2E_MOBILE_WRONG_AUDIENCE_TOKEN');

    const authorize = () => authorizeMobile(browser, clientId, redirect, email, password, required('E2E_MOBILE_SCOPE'));
    const mismatch = await authorize();
    const denied = await exchange({ code: mismatch.code, verifier: randomBytes(32).toString('base64url') });
    expect(denied.status()).toBe(400);

    const response = await exchange(await authorize());
    expect(response.status()).toBe(200);
    const { access_token: token, token_type } = await response.json();
    expect(token_type).toBe('Bearer');
    expect(typeof token).toBe('string');
    const audience = required('E2E_MOBILE_AUDIENCE');
    const payload = claims(token);
    expect(payload.iss === identity + '/realms/platform' && payload.azp === clientId).toBe(true);
    expect([payload.aud].flat().includes(audience)).toBe(true);

    const installation = randomUUID();
    const device = { installation_id: installation };
    const registered = await postMobile(methods, 'register', token, installation);
    expect(registered.status).toBe(200);
    expect(registered.json().message).toMatchObject(device);
    const pulled = await postMobile(methods, 'pull', token, installation);
    expect(pulled.status).toBe(200);
    const page = pulled.json().message;
    expect(Array.isArray(page.changes) && typeof page.cursor === 'string' && typeof page.has_more === 'boolean').toBe(true);

    const expiredClaims = claims(expired);
    if (fullPreview) {
      await expect.poll(() => Math.floor(Date.now() / 1000) - expiredClaims.exp, {
        timeout: 70_000, intervals: [1000],
      }).toBeGreaterThan(60);
    }
    expect(expiredClaims.iss === payload.iss && [expiredClaims.aud].flat().includes(audience)
      && expiredClaims.exp < Math.floor(Date.now() / 1000) - 60).toBe(true);
    const wrongClaims = claims(wrong);
    expect(wrongClaims.iss === payload.iss && ![wrongClaims.aud].flat().includes(audience)
      && wrongClaims.exp > Math.floor(Date.now() / 1000)).toBe(true);

    for (const invalid of [undefined, expired, wrong, 'eyJhbGciOiJub25lIn0.e30.']) {
      expect([401, 403]).toContain((await postMobile(methods, 'pull', invalid, installation)).status);
    }
    expect([400, 401, 403]).toContain(
      (await postMobile(methods, 'pull', token, installation, {}, required('E2E_MOBILE_SESSION_COOKIE'))).status,
    );
    expect([400, 401, 403]).toContain(
      (await postMobile(methods, 'pull', token, installation, { cmd: 'ping' })).status,
    );
    const preflight = await context.fetch(methods + 'platform_core.api.mobile.v1_pull', {
      method: 'OPTIONS',
      headers: { Origin: required('E2E_MOBILE_ORIGIN'), 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,x-platform-installation,x-mobile-app-version,x-mobile-contract-version' },
      maxRedirects: 0,
    });
    expect(preflight.ok()).toBe(true);
    const outside = await context.get(methods + 'frappe.auth.get_logged_user', {
      headers: { Authorization: 'Bearer ' + token }, maxRedirects: 0,
    });
    expect([401, 403]).toContain(outside.status());

    expect((await postMobile(methods, 'revoke', token, installation)).status).toBe(200);
  } finally {
    await context.dispose();
  }
});
