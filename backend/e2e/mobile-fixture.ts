import { createHash, randomBytes } from 'node:crypto';
import { expect, type APIRequestContext, type Browser } from '@playwright/test';
import { localUrl, required } from './local';

export async function authorizeMobile(browser: Browser, client: string, redirect: URL,
  email: string, password: string, scope: string) {
  if (!email.endsWith('@example.test')) throw new Error('Expected a synthetic mobile user.');
  if (redirect.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(redirect.hostname)
      || redirect.search || redirect.hash || redirect.username || redirect.password) {
    throw new Error('Use a dedicated loopback redirect URI for the preview client.');
  }
  const identity = localUrl('identity.localhost', 0);
  const verifier = randomBytes(32).toString('base64url');
  const state = randomBytes(32).toString('hex');
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    let code: string | null = null;
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin === redirect.origin && url.pathname === redirect.pathname) {
        if (url.searchParams.get('state') === state) code = url.searchParams.get('code');
        await route.fulfill({ status: 200, body: 'Preview callback' });
      } else if (url.origin === identity) {
        await route.continue();
      } else {
        await route.abort();
      }
    });
    const url = new URL(identity + '/realms/platform/protocol/openid-connect/auth');
    url.search = new URLSearchParams({
      client_id: client, redirect_uri: redirect.href, scope, response_type: 'code', state,
      code_challenge: createHash('sha256').update(verifier).digest('base64url'), code_challenge_method: 'S256',
    }).toString();
    await page.goto(url.href);
    await page.locator('#username').fill(email);
    await page.locator('#password').fill(password);
    await page.locator('#kc-login').click();
    await expect.poll(() => Boolean(code)).toBe(true);
    return { code: code!, verifier };
  } finally {
    await context.close();
  }
}

export async function previewMobileToken(browser: Browser, request: APIRequestContext,
  email: string, password: string, client = required('E2E_MOBILE_CLIENT_ID'),
  scope = required('E2E_MOBILE_SCOPE')) {
  const identity = localUrl('identity.localhost', 0);
  const redirect = new URL(required('E2E_MOBILE_REDIRECT_URI'));
  if (redirect.href !== localUrl('127.0.0.1', 8) + '/callback') throw new Error('Invalid preview redirect.');
  const { code, verifier } = await authorizeMobile(browser, client, redirect, email, password, scope);
  const response = await request.post(identity + '/realms/platform/protocol/openid-connect/token', {
    maxRedirects: 0, form: { grant_type: 'authorization_code', client_id: client, redirect_uri: redirect.href,
      code, code_verifier: verifier },
  });
  expect(response.status()).toBe(200);
  const result = await response.json();
  if (!result.access_token || !result.refresh_token) throw new Error('Preview mobile tokens are missing.');
  return { access: String(result.access_token), refresh: String(result.refresh_token) };
}

export function mobileHeaders(token: string | undefined, installation: string) {
  return {
    ...(token ? { Authorization: 'Bearer ' + token } : {}),
    'X-Platform-Installation': installation,
    'X-Mobile-App-Version': '1.0.0',
    'X-Mobile-Contract-Version': '1',
  };
}
