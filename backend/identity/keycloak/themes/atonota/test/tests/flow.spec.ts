import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';
import { admin, base32Decode, createUser, KC, loginUrl, openLogin, PASSWORD, REALM, screen, submitPassword, totp } from './helpers';

/**
 * Signs in the way a user does: the fields and the button are found by their visible label and role (TE-4).
 * A wrong accessible name makes this helper fail.
 */
async function signIn(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.getByLabel('E-posta').fill(email);
  await page.getByLabel('Parola', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Oturum açın', exact: true }).click();
}

const accountUrl = new RegExp(`${KC}/realms/${REALM}/account/`);

test('kayıt: yeni kullanıcı hesabını açar ve oturuma girer', async ({ page }) => {
  await screen('register').open(page);
  await page.locator('#email').fill(`kayit-${randomUUID().slice(0, 10)}@ornek.test`);
  await page.locator('#password').fill(PASSWORD);
  await page.locator('#password-confirm').fill(PASSWORD);
  await page.locator('#firstName').fill('Deneme');
  await page.locator('#lastName').fill('Kullanıcı');
  await page.locator('#kc-register-form [type=submit]').click();
  await expect(page).toHaveURL(accountUrl);
});

test('kayıt: kısa parola yalın Türkçe hata verir', async ({ page }) => {
  await screen('register').open(page);
  await page.locator('#email').fill(`kayit-${randomUUID().slice(0, 10)}@ornek.test`);
  await page.locator('#password').fill('kisa');
  await page.locator('#password-confirm').fill('kisa');
  await page.locator('#firstName').fill('Deneme');
  await page.locator('#lastName').fill('Kullanıcı');
  await page.locator('#kc-register-form [type=submit]').click();
  await expect(page.locator('#input-error-password')).toHaveText('Parola en az 12 karakter olmalı.');
});

test('giriş: doğru parola oturum açar, yanlış parola hata verir', async ({ page }) => {
  const email = await createUser();
  await openLogin(page);
  await signIn(page, email, 'yanlis-parola-123');
  await expect(page.locator('#input-error-username')).toHaveText('E-posta ya da parola yanlış.');
  await expect(page.locator('#username')).toHaveAttribute('aria-invalid', 'true');
  await signIn(page, email);
  await expect(page).toHaveURL(accountUrl);
});

test('parola alanındaki göster düğmesi parolayı gösterir ve gizler', async ({ page }) => {
  await openLogin(page);
  const toggle = page.getByRole('button', { name: /^Parolayı (gösterin|gizleyin)$/ });
  await expect(toggle).toHaveAttribute('aria-label', 'Parolayı gösterin');
  await toggle.click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'text');
  await expect(toggle).toHaveAttribute('aria-label', 'Parolayı gizleyin');
  await toggle.click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'password');
});

test('parola sıfırlama: istek gönderilir ve bilgi iletisi görünür', async ({ page }) => {
  const email = await createUser();
  await screen('password-reset').open(page);
  await page.getByLabel('E-posta').fill(email);
  await page.getByRole('button', { name: 'Gönderin', exact: true }).click();
  await expect(page.locator('.pf-v5-c-alert')).toContainText('Bu adres kayıtlıysa size bir e-posta gönderdik.');
});

test('TOTP: kurulum tamamlanır ve sonraki girişte kod sorulur', async ({ page, context }) => {
  const email = await createUser({ requiredActions: ['CONFIGURE_TOTP'] });
  await openLogin(page);
  await submitPassword(page, email);
  await page.getByRole('link', { name: 'Kare kodu okutamıyor musunuz?' }).click();
  const key = (await page.locator('#kc-totp-secret-key').innerText()).trim();
  await page.getByLabel('Tek kullanımlık kod').fill(totp(base32Decode(key)));
  await page.getByLabel('Cihaz adı').fill('Telefon');
  await page.getByRole('button', { name: 'Gönderin', exact: true }).click();
  await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });

  // The account console has loaded when its form is on screen. Only then is the session complete.
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 30_000 });
  await context.clearCookies();
  await openLogin(page);
  await submitPassword(page, email);
  await expect(page.locator('#kc-otp-login-form')).toBeVisible();
  await page.getByLabel('Doğrulama uygulamasındaki kod').fill('000000');
  await page.getByRole('button', { name: 'Oturum açın', exact: true }).click();
  await expect(page.locator('#input-error-otp')).toHaveText('Kod yanlış. Uygulamadaki yeni kodu yazın.');
  // Keycloak aynı kodu iki kez kabul etmez. Bu yüzden bir sonraki 30 saniyenin kodu yazılır.
  await page.getByLabel('Doğrulama uygulamasındaki kod').fill(totp(base32Decode(key), Date.now() + 30_000));
  await page.getByRole('button', { name: 'Oturum açın', exact: true }).click();
  await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
});

test('passkey: anahtar kaydedilir ve anahtarla oturum açılır', async ({ page, context, browserName }) => {
  test.skip(browserName !== 'chromium', 'Sanal güvenlik anahtarı yalnız Chromium ailesinde var');
  const cdp = await context.newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  // Keycloak anahtar adını tarayıcının soru penceresiyle sorar. Test varsayılan adı kabul eder.
  page.on('dialog', (dialog) => dialog.accept());
  const email = await createUser({ requiredActions: ['webauthn-register-passwordless'] });
  await openLogin(page);
  await submitPassword(page, email);
  // The page script binds the button while the page loads. A click before the "load" event does nothing,
  // so the test waits for that event. A second click would start a second registration, so there is only one.
  const addPasskey = page.getByRole('button', { name: 'Geçiş anahtarı ekleyin', exact: true });
  await expect(addPasskey).toBeVisible({ timeout: 20_000 });
  await page.waitForLoadState('load');
  await addPasskey.click();
  await expect(page).toHaveURL(accountUrl, { timeout: 30_000 });

  // The account console has loaded when its form is on screen. Only then is the session complete.
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 30_000 });
  await context.clearCookies();
  // Sanal anahtar soruyu kendiliğinden yanıtlar. Düğmeyi sınamak için yanıt önce durdurulur.
  await cdp.send('WebAuthn.setAutomaticPresenceSimulation', { authenticatorId, enabled: false });
  await openLogin(page);
  await cdp.send('WebAuthn.setAutomaticPresenceSimulation', { authenticatorId, enabled: true });
  const usePasskey = page.getByRole('link', { name: 'Geçiş anahtarıyla oturum açın', exact: true });
  await expect(usePasskey).toBeVisible({ timeout: 20_000 });
  await page.waitForLoadState('load');
  await usePasskey.click();
  await expect(page).toHaveURL(accountUrl, { timeout: 30_000 });
});

test('passkey hatası: yalın bir ileti ve yeniden deneme düğmesi görünür', async ({ page }) => {
  await screen('passkey-error').open(page);
  await expect(page.getByRole('button', { name: 'Yeniden deneyin', exact: true })).toBeVisible();
  await expect(page.locator('.pf-v5-c-alert')).toContainText('Geçiş anahtarı');
});

test('TOTP setup: a wrong code is announced with the field it belongs to', async ({ page }) => {
  await screen('totp-setup').open(page);
  await page.locator('#totp').fill('000000');
  await page.locator('#saveTOTPBtn').click();
  const error = page.locator('#input-error-otp-code');
  await expect(error).toBeVisible();
  // A screen reader reads the error together with the field only when the field points at it.
  await expect(page.locator('#totp')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('#totp')).toHaveAttribute('aria-describedby', 'input-error-otp-code');
  // A field without an error points at nothing.
  await expect(page.locator('#userLabel')).not.toHaveAttribute('aria-describedby', /.+/);
});

test('recovery codes: the setup finishes only after the user confirms that the codes are saved', async ({ page }) => {
  await screen('recovery-codes-setup').open(page);
  await page.waitForLoadState('load');
  const codes = page.locator('#kc-recovery-codes-list li');
  expect(await codes.count()).toBeGreaterThanOrEqual(8);
  const firstCode = (await codes.first().innerText()).trim();
  await page.evaluate(() => {
    const output = document.createElement('output');
    output.id = 'test-recovery-actions';
    output.hidden = true;
    document.body.append(output);

    document.execCommand = (command) => {
      if (command !== 'copy' || !(document.activeElement instanceof HTMLTextAreaElement)) return false;
      output.dataset.copied = document.activeElement.value;
      return true;
    };

    const printDocument = document.implementation.createHTMLDocument();
    window.open = () => ({
      document: printDocument,
      print: () => {
        output.dataset.printed = printDocument.body.textContent ?? '';
      },
      close: () => {},
    }) as unknown as Window;
  });
  const recoveryActions = page.locator('#test-recovery-actions');
  await page.getByRole('button', { name: 'Kopyalayın', exact: true }).click();
  await expect(recoveryActions).toHaveAttribute('data-copied', new RegExp(firstCode));
  await page.getByRole('button', { name: 'Yazdırın', exact: true }).click();
  await expect(recoveryActions).toHaveAttribute('data-printed', new RegExp(firstCode));

  const finish = page.locator('#saveRecoveryAuthnCodesBtn');
  await expect(finish).toBeDisabled();
  // The download holds the same codes and plain Turkish text. The date is written in the language of the page.
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'İndirin', exact: true }).click()]);
  const stream = await download.createReadStream();
  let file = '';
  for await (const chunk of stream) file += chunk.toString();
  expect(file).toContain('Bu kurtarma kodlarını güvenli bir yerde saklayın.');
  expect(file).toContain(firstCode);
  expect(file).toContain('Kodların üretildiği tarih:');
  expect(/(?<!\p{L})(?:January|February|March|April|May|June|July|August|September|October|November|December)(?!\p{L})/u.test(file), 'English month name in the file').toBe(false);
  await page.getByLabel('Kodları güvenli bir yere kaydettim').check();
  await expect(finish).toBeEnabled();
  await page.getByLabel('Kodları güvenli bir yere kaydettim').uncheck();
  await expect(finish).toBeDisabled();
  await page.getByLabel('Kodları güvenli bir yere kaydettim').check();
  await finish.click();
  await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
});

test('sign-out: the confirmation signs the user out', async ({ page }) => {
  const email = await createUser();
  await openLogin(page);
  await submitPassword(page, email);
  await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });
  await screen('sign-out-confirm').open(page);
  await page.getByRole('button', { name: 'Bu oturumu kapatın', exact: true }).click();
  await expect(page.locator('#kc-page-title')).toHaveText('Oturumu kapattınız');
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await expect(page.locator('#kc-form-login')).toBeVisible({ timeout: 20_000 });
});

test('sign-out: the screen offers three scopes, and every device ends the sessions of all devices', async ({ page, browser }) => {
  const email = await createUser();
  // A second device: another browser with its own Keycloak session.
  const other = await browser.newContext({ locale: 'tr-TR' });
  const otherPage = await other.newPage();
  await openLogin(otherPage);
  await submitPassword(otherPage, email);
  await expect(otherPage).toHaveURL(accountUrl, { timeout: 20_000 });
  await openLogin(page);
  await submitPassword(page, email);
  await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
  await expect(page.locator('#save-btn')).toBeVisible({ timeout: 20_000 });

  await screen('sign-out-confirm').open(page);
  const scopes = page.locator('#kc-logout-scopes > li');
  await expect(scopes).toHaveCount(3);
  await expect(scopes.getByRole('heading', { level: 2 })).toHaveText(['Bu oturum', 'Başka bir oturum', 'Bütün cihazlar']);
  await expect(page.getByRole('button', { name: 'Bu oturumu kapatın', exact: true })).toBeVisible();
  const deviceActivity = `/realms/${REALM}/account/account-security/device-activity`;
  for (const name of ['Başka bir oturumu kapatın', 'Bütün cihazlarda oturumu kapatın']) {
    await expect(page.getByRole('link', { name, exact: true })).toHaveAttribute('href', deviceActivity);
  }

  await page.getByRole('link', { name: 'Bütün cihazlarda oturumu kapatın', exact: true }).click();
  await expect(page).toHaveURL(`${KC}${deviceActivity}`, { timeout: 20_000 });
  // The every-device text names this button. The account console shows it when another device is signed in.
  await page.getByRole('button', { name: 'Bütün cihazlarda oturumu kapatın', exact: true }).click({ timeout: 20_000 });
  const signedOutAll = page.waitForResponse((response) => response.request().method() === 'DELETE' && response.url().includes('/account/sessions'));
  await page.getByRole('dialog').getByRole('button', { name: 'Onaylayın', exact: true }).click();
  expect((await signedOutAll).ok()).toBe(true);

  // Both devices must sign in again. The account console reloads this device by itself.
  await expect(page.locator('#kc-form-login')).toBeVisible({ timeout: 20_000 });
  await otherPage.goto(`${KC}/realms/${REALM}/account/`);
  await expect(otherPage.locator('#kc-form-login')).toBeVisible({ timeout: 20_000 });
  await other.close();
});

for (const choice of ['decline', 'confirm'] as const) {
  test(`removing a sign-in method: the user can ${choice}`, async ({ page }) => {
    const email = await createUser({ totp: true });
    const [user] = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as { id: string }[];
    const otpCredentials = async () => ((await (await admin(`/users/${user.id}/credentials`)).json()) as { id: string; type: string }[]).filter((credential) => credential.type === 'otp');
    const [credential] = await otpCredentials();
    // The account console starts this action. The user proves the identity before the question appears.
    await page.goto(`${loginUrl()}&kc_action=${encodeURIComponent(`delete_credential:${credential.id}`)}`);
    await submitPassword(page, email);
    await expect(page.locator('#otp')).toBeVisible({ timeout: 20_000 });
    await page.locator('#otp').fill(totp());
    await page.locator('#kc-login').click();
    await expect(page.locator('#kc-page-title')).toHaveText('Telefon silinsin mi?', { timeout: 20_000 });
    if (choice === 'decline') {
      await page.getByRole('button', { name: 'Vazgeçin', exact: true }).click();
      await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
      expect((await otpCredentials()).length, 'declining keeps the sign-in method').toBe(1);
    } else {
      await page.getByRole('button', { name: 'Silmeyi onaylayın', exact: true }).click();
      await expect(page).toHaveURL(accountUrl, { timeout: 20_000 });
      expect((await otpCredentials()).length, 'confirming removes the sign-in method').toBe(0);
    }
  });
}
