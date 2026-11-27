import { expect, test, type Page, type Response } from '@playwright/test';
import { ACCOUNT_DELETION_URL, admin, BRAND, createUser, endSessions, KC, loginUrl, openLogin, REALM, submitPassword } from './helpers';

// Access is tested on the real sign-in path, and the refusal is tested too (backend/AGENTS.md:69).
// Three states of the visitor: guest, signed in, and a session that ended on the server while the
// browser still holds its cookies. Three screens: sign-in, account console, account deletion link.

const ACCOUNT = `${KC}/realms/${REALM}/account/`;
const LINK = '#at-account-deletion-link';
/** Text of the sign-out item in the Turkish message bundle of the account theme. */
const SIGN_OUT = 'Oturumu kapatın';

async function signIn(page: Page, options: { customer: boolean }): Promise<string> {
  const email = await createUser({ customer: options.customer });
  await page.goto(ACCOUNT);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
  return email;
}

/** The themed sign-in screen: brand header, the theme stylesheet and the password form. */
async function expectThemedSignIn(page: Page): Promise<void> {
  await expect(page).toHaveURL(new RegExp(`/realms/${REALM}/protocol/openid-connect/auth|/realms/${REALM}/login-actions/`), { timeout: 20_000 });
  await expect(page.locator('#kc-form-login')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.at-brand')).toContainText(BRAND);
  expect(await page.locator('link[href*="css/atonota.css"]').count(), 'theme stylesheet').toBe(1);
}

test.describe('guest', () => {
  test('the account console sends a guest to the themed sign-in screen', async ({ page }) => {
    await page.goto(ACCOUNT);
    await expectThemedSignIn(page);
    await expect(page.locator('#save-btn')).toHaveCount(0);
    await expect(page.locator(LINK)).toHaveCount(0);
  });

  test('a deep page of the account console also sends a guest to the sign-in screen', async ({ page }) => {
    await page.goto(`${ACCOUNT}account-security/signing-in`);
    await expectThemedSignIn(page);
  });

  test('the account API refuses a guest', async ({ request }) => {
    const res = await request.get(`${ACCOUNT}?userProfileMetadata=true`, { headers: { accept: 'application/json' } });
    expect(res.status()).toBe(401);
    expect(await res.text()).not.toContain(ACCOUNT_DELETION_URL);
  });

  test('the sign-in screen shows no account data and no deletion link to a guest', async ({ page }) => {
    await openLogin(page);
    await expectThemedSignIn(page);
    await expect(page.locator(LINK)).toHaveCount(0);
    expect(await page.content()).not.toContain(ACCOUNT_DELETION_URL);
  });
});

test.describe('signed in', () => {
  test('a signed-in user who opens the sign-in address goes straight to the account console', async ({ page }) => {
    await signIn(page, { customer: false });
    await page.goto(loginUrl());
    await expect(page).toHaveURL(new RegExp(`${ACCOUNT}`));
    await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('#kc-form-login')).toHaveCount(0);
  });

  test('the account data request answers a signed-in user with the own account only', async ({ page }) => {
    // A second account exists in the same realm. Its data must not reach this user.
    const other = await createUser();
    const email = await signIn(page, { customer: false });
    // The console asks the server for the account data as JSON. This is that request, made by the browser itself.
    const isAccountData = (response: Response) =>
      response.request().method() === 'GET' &&
      response.url().startsWith(`${ACCOUNT}?`) &&
      (response.headers()['content-type'] ?? '').includes('application/json');
    const [response] = await Promise.all([page.waitForResponse(isAccountData, { timeout: 20_000 }), page.reload()]);
    expect(response.status(), 'status of the account data request').toBe(200);
    const text = await response.text();
    const data = JSON.parse(text) as { email?: string; username?: string };
    expect(data.email, 'the answer belongs to the signed-in user').toBe(email);
    expect(data.username).toBe(email);
    expect(text.includes(other), 'data of the second account in the answer').toBe(false);
    await expect(page.locator('#email')).toHaveValue(email);
  });

  test('signing out ends the access: the console asks for the password again', async ({ page }) => {
    await signIn(page, { customer: true });
    await expect(page.locator(LINK)).toBeVisible();
    // The user menu is the first visible menu toggle of the header, on a phone and on a wide screen.
    await page.locator('.pf-v5-c-masthead .pf-v5-c-menu-toggle:visible').first().click();
    await page.getByRole('menuitem', { name: SIGN_OUT, exact: true }).click();
    await expect(page).not.toHaveURL(new RegExp(`${ACCOUNT}$`), { timeout: 20_000 });
    await page.goto(ACCOUNT);
    await expectThemedSignIn(page);
    expect(await (await page.request.get(ACCOUNT)).text()).not.toContain('at-account-deletion');
  });
});

test.describe('session ended on the server', () => {
  test('the server stops sending the deletion link as soon as the session ends', async ({ page }) => {
    const email = await signIn(page, { customer: true });
    expect(await (await page.request.get(ACCOUNT)).text(), 'link while signed in').toContain('id="at-account-deletion-link"');
    await endSessions(email);
    // The browser still sends its old cookies. The server must not trust them.
    const html = await (await page.request.get(ACCOUNT)).text();
    expect(html).not.toContain('at-account-deletion');
    expect(html).not.toContain(ACCOUNT_DELETION_URL);
  });

  test('a reload after the session ended leads to the themed sign-in screen', async ({ page }) => {
    const email = await signIn(page, { customer: true });
    await endSessions(email);
    await page.reload();
    await expectThemedSignIn(page);
    await expect(page.locator('#save-btn')).toHaveCount(0);
    await expect(page.locator(LINK)).toHaveCount(0);
  });

  test('saving in a stale tab is refused, changes nothing and leads to the sign-in screen', async ({ page }) => {
    const email = await signIn(page, { customer: false });
    await endSessions(email);
    const refused = page.waitForResponse((response) => response.request().method() === 'POST' && response.url() === ACCOUNT);
    await page.locator('#firstName').fill('Changed');
    await page.locator('#save-btn').click();
    expect((await refused).status(), 'the account API refuses the ended session').toBe(401);
    await expectThemedSignIn(page);
    const [user] = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as { firstName: string }[];
    expect(user.firstName, 'the stale tab changed nothing').not.toBe('Changed');
  });

  test('a sign-in form whose attempt is gone shows a themed error in plain Turkish and signs nobody in', async ({ page, context }) => {
    const email = await createUser();
    await openLogin(page);
    // The sign-in attempt lives in cookies. Without them Keycloak cannot continue the form.
    await context.clearCookies();
    await page.locator('#username').fill(email);
    await page.locator('#password').fill('not-used-here');
    await page.locator('#kc-login').click();
    await expect(page.locator('#kc-page-title')).toHaveText('Bir sorun oldu');
    await expect(page.locator('#kc-error-message')).toContainText('Giriş bilgisini bulamadık.');
    await expect(page.locator('#backToApplication')).toBeVisible();
    await expect(page.locator('.at-brand')).toContainText(BRAND);
    expect(await page.locator('link[href*="css/atonota.css"]').count(), 'theme stylesheet').toBe(1);
    // Nobody is signed in: the account console still asks for the password.
    await page.goto(ACCOUNT);
    await expectThemedSignIn(page);
  });

  test('an expired sign-in page offers to start again, in plain Turkish', async ({ page }) => {
    // The user has a second step. After the password the attempt has moved on to that step.
    const email = await createUser({ totp: true });
    await openLogin(page);
    const firstStep = (await page.locator('#kc-form-login').getAttribute('action'))!;
    await submitPassword(page, email);
    await expect(page.locator('#otp')).toBeVisible();
    // The address of the first step is now out of date. A restored tab or an old link opens it like this.
    await page.goto(firstStep);
    await expect(page.locator('#kc-page-title')).toHaveText('Sayfanın süresi doldu');
    await expect(page.locator('#instruction1')).toHaveText('Bu sayfanın süresi doldu. Ne yapmak istersiniz?');
    await expect(page.locator('#loginRestartLink')).toHaveText('Baştan başlayın');
    await expect(page.locator('#loginContinueLink')).toHaveText('Kaldığınız yerden devam edin');
    await expect(page.locator('.at-brand')).toContainText(BRAND);
    // Starting again leads to a fresh, working sign-in form.
    await page.locator('#loginRestartLink').click();
    await expectThemedSignIn(page);
    await submitPassword(page, email);
    await expect(page.locator('#otp')).toBeVisible();
  });
});
