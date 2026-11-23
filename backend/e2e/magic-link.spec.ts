import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { localUrl, required } from './local';
import { invalidTotpCode, totpCode, totpWaitMs } from './totp';

const enabled = process.env.E2E_MAGIC_LINK === '1';
test.skip(!enabled, 'Magic-link realm and Mailpit fixtures are required.');

function identityOrigin() {
  return localUrl('identity.localhost', 0);
}

function mailpitUrl(path: string) {
  return localUrl('127.0.0.1', 6) + '/api/v1/' + path;
}

async function mailbox(request: APIRequestContext, email: string) {
  const response = await request.get(mailpitUrl('messages'), { maxRedirects: 0 });
  expect(response.status()).toBe(200);
  const items: { ID: string; To: { Address: string }[] }[] = (await response.json()).messages;
  return items.filter((item) => item.To.some(({ Address }) => Address === email));
}

async function observe(page: Page, state: string) {
  const callback = localUrl('tenant1.localhost', 1) + '/api/method/platform_core.api.auth.keycloak_callback';
  let authorized = false;
  let issuedCode = false;
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin + url.pathname === callback) {
      issuedCode ||= url.searchParams.has('code');
      authorized ||= url.searchParams.get('state') === state && url.searchParams.has('code');
    }
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin + url.pathname === callback) {
      await route.fulfill({ status: 200, body: 'Local test callback' });
    } else if (url.origin === identityOrigin()) {
      await route.continue();
    } else {
      await route.abort();
    }
  });
  return { authorized: () => authorized, issuedCode: () => issuedCode };
}

async function requestLink(page: Page, request: APIRequestContext, email: string) {
  if (!email.endsWith('@example.test')) throw new Error('Use a synthetic mail recipient.');
  const previous = new Set((await mailbox(request, email)).map(({ ID }) => ID));
  const state = randomUUID();
  const observation = await observe(page, state);
  const entry = new URL(identityOrigin() + '/realms/platform/protocol/openid-connect/auth');
  const challenge = createHash('sha256').update(randomBytes(32).toString('base64url')).digest('base64url');
  entry.search = new URLSearchParams({
    client_id: 'site-tenant1', response_type: 'code', scope: 'openid', state,
    redirect_uri: localUrl('tenant1.localhost', 1) + '/api/method/platform_core.api.auth.keycloak_callback',
    code_challenge: challenge, code_challenge_method: 'S256',
  }).toString();
  await page.goto(entry.toString());

  const alternate = page.locator('form:has([name="tryAnotherWay"])');
  await alternate.evaluate((form: HTMLFormElement) => form.requestSubmit());
  await page.getByRole('button', {
    name: /^(?:Email link Sign in with a link sent to your email|E-posta bağlantısı E-postanıza gelen bağlantıyla oturum açın)\.$/,
  }).click();

  const emailInput = page.locator('input[name="username"]:visible');
  await emailInput.fill(email);
  await emailInput.evaluate((input: HTMLInputElement) => input.form!.requestSubmit());

  let messageId: string | undefined;
  await expect.poll(async () => {
    messageId = (await mailbox(request, email)).find(({ ID }) => !previous.has(ID))?.ID;
    return Boolean(messageId);
  }, { timeout: 20_000 }).toBe(true);
  const mail = await request.get(mailpitUrl('message/' + encodeURIComponent(messageId!)), { maxRedirects: 0 });
  expect(mail.status()).toBe(200);
  const { Text, HTML } = await mail.json();
  const link = `${Text ?? ''} ${HTML ?? ''}`.match(/https?:\/\/[^\s"'<>]+login-actions\/authenticate[^\s"'<>]+magickey=[^\s"'<>]+/i);
  expect(Boolean(link)).toBe(true);
  const url = new URL(link![0].replaceAll('&amp;', '&'));
  expect(url.origin).toBe(identityOrigin());
  return { url, ...observation };
}

test('mail preview and a different login cannot consume a one-time magic link', async ({ browser, page, request }) => {
  const email = required('E2E_MAGIC_EMAIL');
  const original = await requestLink(page, request, email);
  const preview = await request.get(original.url.toString(), { maxRedirects: 0 });
  expect(new URL(preview.headers().location ?? '/', identityOrigin()).searchParams.has('code')).toBe(false);

  const other = await browser.newContext();
  try {
    const otherPage = await other.newPage();
    const separate = await requestLink(otherPage, request, email);
    await otherPage.goto(original.url.toString());
    expect(separate.issuedCode()).toBe(false);
    expect(original.authorized()).toBe(false);
  } finally {
    await other.close();
  }

  const secondTab = await page.context().newPage();
  try {
    const separate = await requestLink(secondTab, request, email);
    separate.url.searchParams.set('magickey', original.url.searchParams.get('magickey')!);
    await secondTab.goto(separate.url.toString());
    expect(separate.issuedCode()).toBe(false);
  } finally {
    await secondTab.close();
  }

  await page.goto(original.url.toString());
  expect(original.authorized()).toBe(true);
  const repeated = await page.request.get(original.url.toString(), { maxRedirects: 0 });
  expect(new URL(repeated.headers().location ?? '/', identityOrigin()).searchParams.has('code')).toBe(false);
});

test('expired magic link is rejected and a new send works', async ({ browser, page, request }) => {
  const lifetime = Number(required('E2E_MAGIC_TTL_SECONDS'));
  expect(Number.isInteger(lifetime) && lifetime > 0 && lifetime <= 300).toBe(true);
  test.setTimeout((lifetime + 70) * 1000);
  const email = process.env.E2E_FULL_BROWSER_FIXTURES === '1'
    ? required('E2E_MAGIC_EXPIRY_EMAIL') : required('E2E_MAGIC_EMAIL');
  const expired = await requestLink(page, request, email);
  await new Promise((resolve) => setTimeout(resolve, (lifetime + 2) * 1000));
  await page.goto(expired.url.toString());
  expect(expired.issuedCode()).toBe(false);
  await new Promise((resolve) => setTimeout(resolve, 1200));

  const retry = await browser.newContext();
  try {
    const retryPage = await retry.newPage();
    const fresh = await requestLink(retryPage, request, email);
    expect(fresh.url.toString() !== expired.url.toString()).toBe(true);
    await retryPage.goto(fresh.url.toString());
    await expect.poll(fresh.authorized).toBe(true);
  } finally {
    await retry.close();
  }
});

test('magic link still requires the enrolled second factor', async ({ page, request }, testInfo) => {
  test.setTimeout(90_000);
  const seed = required('E2E_MAGIC_OTP_SEED');
  const attempt = await requestLink(page, request, required('E2E_MAGIC_OTP_EMAIL'));
  await page.goto(attempt.url.toString());
  expect(attempt.issuedCode()).toBe(false);
  const otp = page.locator('input[name="otp"]:visible');
  await expect(otp).toBeVisible();
  await new Promise((resolve) => setTimeout(resolve, 1200));
  await otp.fill(invalidTotpCode(seed));
  const rejection = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'POST' && url.origin === identityOrigin()
      && url.pathname === '/realms/platform/login-actions/authenticate';
  });
  await otp.evaluate((input: HTMLInputElement) => input.form!.requestSubmit());
  await rejection;
  await expect(otp).toBeVisible();
  expect(attempt.issuedCode()).toBe(false);
  // Leave the quick-login lockout window and avoid reusing a consumed 30-second code across browsers.
  const sharedAccount = process.env.E2E_FULL_BROWSER_FIXTURES !== '1' && testInfo.project.name !== 'chromium';
  const waitMs = Math.max(1200, totpWaitMs(Date.now(), sharedAccount));
  await new Promise((resolve) => setTimeout(resolve, waitMs));
  const boundaryMs = totpWaitMs(Date.now(), false);
  if (boundaryMs > 0) await new Promise((resolve) => setTimeout(resolve, boundaryMs));
  await otp.fill(totpCode(seed));
  await otp.evaluate((input: HTMLInputElement) => input.form!.requestSubmit());
  await expect.poll(attempt.authorized).toBe(true);
});
