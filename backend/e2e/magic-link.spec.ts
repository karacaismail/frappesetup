import { createHash, createHmac, randomBytes, randomUUID } from 'node:crypto';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { localUrl, required } from './local';

const enabled = process.env.E2E_MAGIC_LINK === '1';
test.skip(!enabled, 'Magic-link realm and Mailpit fixtures are required.');

function totp(secret: string) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = secret.toUpperCase().replace(/=+$/, '').split('').map((letter) => {
    const index = alphabet.indexOf(letter);
    if (index < 0) throw new Error('The test OTP seed must be Base32.');
    return index.toString(2).padStart(5, '0');
  }).join('');
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => Number.parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const hash = createHmac('sha1', key).update(counter).digest();
  return String((hash.readUInt32BE(hash[hash.length - 1] & 15) & 0x7fffffff) % 1_000_000).padStart(6, '0');
}

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
  await page.getByRole('button', { name: /magiclink-display-name|magic link|e-posta bağlantısı/i }).click();

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
  const email = required('E2E_MAGIC_EMAIL');
  const expired = await requestLink(page, request, email);
  await new Promise((resolve) => setTimeout(resolve, (lifetime + 2) * 1000));
  await page.goto(expired.url.toString());
  expect(expired.issuedCode()).toBe(false);

  const retry = await browser.newContext();
  try {
    const retryPage = await retry.newPage();
    const fresh = await requestLink(retryPage, request, email);
    expect(fresh.url.toString() !== expired.url.toString()).toBe(true);
    await retryPage.goto(fresh.url.toString());
    expect(fresh.authorized()).toBe(true);
  } finally {
    await retry.close();
  }
});

test('magic link still requires the enrolled second factor', async ({ page, request }) => {
  test.setTimeout(70_000);
  const attempt = await requestLink(page, request, required('E2E_MAGIC_OTP_EMAIL'));
  await page.goto(attempt.url.toString());
  expect(attempt.issuedCode()).toBe(false);
  const otp = page.locator('input[name="otp"]:visible');
  await expect(otp).toBeVisible();
  const code = totp(required('E2E_MAGIC_OTP_SEED'));
  await otp.fill(code === '000000' ? '111111' : '000000');
  await otp.evaluate((input: HTMLInputElement) => input.form!.requestSubmit());
  expect(attempt.issuedCode()).toBe(false);
  // Keycloak rejects reuse of a time-based code across browser projects.
  await new Promise((resolve) => setTimeout(resolve, 30_000 - (Date.now() % 30_000) + 500));
  await otp.fill(totp(required('E2E_MAGIC_OTP_SEED')));
  await otp.evaluate((input: HTMLInputElement) => input.form!.requestSubmit());
  await expect.poll(attempt.authorized).toBe(true);
});
