import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { admin, createUser, KC, loginUrl, MAILPIT, openLogin, PASSWORD, REALM, submitPassword } from './helpers';

/**
 * AJA-648. A password manager links a saved password to an account only through a field with
 * autocomplete="username" in the same form. Without it, Chrome and Apple Passwords do not offer to save
 * a changed password, or they save it for the wrong account.
 *
 * Every form that takes a password must hold:
 * - one username field with autocomplete="username" and the account e-mail as its value,
 * - autocomplete="current-password" on a sign-in password, or "new-password" on a new password.
 *
 * The username field may be hidden. A hidden field stays out of the Tab order and out of the accessibility tree.
 */

const accountUrl = new RegExp(`${KC}/realms/${REALM}/account/`);
const loginDir = fileURLToPath(new URL('../../login/', import.meta.url));

/** Checks the username field of a password form. Returns the field. */
async function expectUsernameField(form: Locator, email: string): Promise<Locator> {
  const username = form.locator('input[autocomplete~="username"]');
  await expect(username, 'the form holds exactly one username field').toHaveCount(1);
  await expect(username).toHaveValue(email);
  // A field with type="hidden" is ignored by password managers.
  expect(await username.getAttribute('type')).not.toBe('hidden');
  return username;
}

/** A hidden username field must not reach keyboard or screen reader users. */
async function expectQuietField(field: Locator): Promise<void> {
  if (await field.isVisible()) return;
  const state = await field.evaluate((el) => ({
    tabIndex: (el as HTMLInputElement).tabIndex,
    disabled: (el as HTMLInputElement).disabled,
    ariaHidden: el.closest('[aria-hidden="true"]') !== null,
    hiddenAttr: el.closest('[hidden]') !== null,
  }));
  expect(state.disabled, 'a disabled field is skipped by password managers').toBe(false);
  expect(state.tabIndex, 'the hidden field is out of the Tab order').toBe(-1);
  expect(state.ariaHidden || state.hiddenAttr, 'the hidden field is out of the accessibility tree').toBe(true);
}

/** Checks the update-password form: a username field and two new-password fields. */
async function expectUpdatePasswordForm(page: Page, email: string): Promise<void> {
  const form = page.locator('#kc-passwd-update-form');
  await expect(form).toBeVisible();
  const username = await expectUsernameField(form, email);
  await expectQuietField(username);
  await expect(form.locator('#password-new')).toHaveAttribute('autocomplete', 'new-password');
  await expect(form.locator('#password-confirm')).toHaveAttribute('autocomplete', 'new-password');
  await expect(form.locator('input[autocomplete="current-password"]')).toHaveCount(0);
}

/**
 * Sets a new password on the update-password screen. By default it checks that the account console opens.
 * An action sent by e-mail ends on Keycloak's "account updated" screen instead.
 */
async function submitNewPassword(page: Page, end: 'account' | 'updated' = 'account'): Promise<void> {
  const fresh = `${PASSWORD}-yeni`;
  const first = page.locator('#password-new');
  const second = page.locator('#password-confirm');
  // The page moves focus while it loads. The test waits for "load" and submits only when both fields hold
  // the new password. The check never prints the values.
  await page.waitForLoadState('load');
  await expect(async () => {
    await first.fill(fresh);
    await second.fill(fresh);
    expect((await first.inputValue()) === fresh && (await second.inputValue()) === fresh, 'both fields hold the new password').toBe(true);
  }).toPass({ timeout: 20_000 });
  await page.locator('#kc-submit').click();
  if (end === 'updated') {
    await expect(page.getByRole('heading', { name: 'Hesap güncellendi' })).toBeVisible({ timeout: 20_000 });
    return;
  }
  await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
}

/**
 * Opens an address in a new tab of the same browser session. The account console redirects on its own
 * after sign-in. A navigation in the same tab can be cut by that redirect.
 */
async function openAfterSignIn(page: Page, url: string): Promise<Page> {
  // The account console finishes its own sign-in in the background. A new sign-in request before that
  // ends can restart the second tab's flow. The console heading shows that the first sign-in ended.
  await expect(page.getByRole('heading', { name: 'Kişisel bilgiler' }).first()).toBeVisible({ timeout: 20_000 });
  await page.close();
  const tab = await page.context().newPage();
  await tab.goto(url);
  return tab;
}

test('giriş ekranı: e-posta alanı username, parola alanı current-password taşır', async ({ page }) => {
  await openLogin(page);
  const form = page.locator('#kc-form-login');
  await expect(form.locator('#username')).toHaveAttribute('autocomplete', /(^|\s)username(\s|$)/);
  await expect(form.locator('#password')).toHaveAttribute('autocomplete', 'current-password');
});

test('yeniden giriş ekranı: e-posta yalnız yazıyken de formda username alanı vardır', async ({ page }) => {
  const email = await createUser();
  await openLogin(page);
  await submitPassword(page, email);
  await expect(page).toHaveURL(accountUrl);
  // prompt=login asks a signed-in user for the password again. Keycloak shows the e-mail only as text.
  const again = await openAfterSignIn(page, `${loginUrl()}&prompt=login`);
  const form = again.locator('#kc-form-login');
  await expect(form.locator('#password')).toHaveAttribute('autocomplete', 'current-password');
  const username = await expectUsernameField(form, email);
  await expectQuietField(username);
});

test('zorunlu parola değişikliği: yönetici istediğinde form hesabı bilir', async ({ page }) => {
  const email = await createUser({ requiredActions: ['UPDATE_PASSWORD'] });
  await openLogin(page);
  await submitPassword(page, email);
  await expectUpdatePasswordForm(page, email);
  await submitNewPassword(page);
});

test('hesap ekranından parola değiştirme: form hesabı bilir', async ({ page }) => {
  const email = await createUser();
  await openLogin(page);
  await submitPassword(page, email);
  await expect(page).toHaveURL(accountUrl);
  // The account console starts the change with this application-initiated action.
  const change = await openAfterSignIn(page, `${loginUrl()}&kc_action=UPDATE_PASSWORD`);
  await expectUpdatePasswordForm(change, email);
  await submitNewPassword(change);
});

test('parolamı unuttum: e-postadaki bağlantının açtığı form hesabı bilir', async ({ page }) => {
  const email = await createUser();
  await openLogin(page);
  await page.locator('#kc-form-login a[href*="reset-credentials"]').click();
  await page.locator('#username').fill(email);
  await page.locator('#kc-reset-password-form [type=submit]').click();
  const link = await resetLink(email);
  await page.goto(link);
  await expectUpdatePasswordForm(page, email);
  await submitNewPassword(page);
});

test('yöneticinin e-postayla gönderdiği parola işlemi: form hesabı bilir', async ({ page }) => {
  const email = await createUser();
  const users = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as { id: string }[];
  const sent = await admin(`/users/${users[0].id}/execute-actions-email?client_id=account-console&redirect_uri=${encodeURIComponent(`${KC}/realms/${REALM}/account/`)}`, {
    method: 'PUT',
    body: ['UPDATE_PASSWORD'],
  });
  expect(sent.status).toBe(204);
  await page.goto(await resetLink(email));
  // Keycloak first lists the requested actions. The link on that screen opens the form.
  const proceed = page.locator('a[href*="login-actions/action-token"], #kc-info-message a').first();
  if (await page.locator('#kc-passwd-update-form').count() === 0) await proceed.click();
  await expectUpdatePasswordForm(page, email);
  await submitNewPassword(page, 'updated');
});

test('kaynak: parola adımı şablonu username alanı taşır', () => {
  // The test realm signs in with one screen, so login-password.ftl is not reached here.
  // This check reads the template. The template must hold the shared username field.
  const source = readFileSync(`${loginDir}login-password.ftl`, 'utf8');
  expect(source).toContain('<@account.usernameField/>');
  expect(source).toContain('autocomplete="current-password"');
});

/** Reads the reset link from the one e-mail that the address received. */
async function resetLink(to: string): Promise<string> {
  const until = Date.now() + 20_000;
  while (Date.now() < until) {
    const res = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    const list = ((await res.json()) as { messages?: { ID: string }[] }).messages ?? [];
    if (list.length > 0) {
      const mail = (await (await fetch(`${MAILPIT}/api/v1/message/${list[0].ID}`)).json()) as { Text: string };
      const match = mail.Text.match(/https?:\/\/\S+login-actions\/action-token\S+/);
      if (!match) throw new Error('The reset e-mail holds no link');
      return match[0];
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`No e-mail for ${to}`);
}

