import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { base32Decode, createUser, KC, openLogin, PASSWORD, REALM, screen, submitPassword, totp } from './helpers';

const accountUrl = new RegExp(`${KC}/realms/${REALM}/account/`);

test('kayıt: yeni kullanıcı hesabını açar ve oturuma girer', async ({ page }) => {
  await screen('kayit').open(page);
  await page.locator('#email').fill(`kayit-${randomUUID().slice(0, 10)}@ornek.test`);
  await page.locator('#password').fill(PASSWORD);
  await page.locator('#password-confirm').fill(PASSWORD);
  await page.locator('#firstName').fill('Deneme');
  await page.locator('#lastName').fill('Kullanıcı');
  await page.locator('#kc-register-form [type=submit]').click();
  await expect(page).toHaveURL(accountUrl);
});

test('kayıt: kısa parola yalın Türkçe hata verir', async ({ page }) => {
  await screen('kayit').open(page);
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
  await submitPassword(page, email, 'yanlis-parola-123');
  await expect(page.locator('#input-error-username')).toHaveText('E-posta ya da parola yanlış.');
  await expect(page.locator('#username')).toHaveAttribute('aria-invalid', 'true');
  await submitPassword(page, email);
  await expect(page).toHaveURL(accountUrl);
});

test('parola alanındaki göster düğmesi parolayı gösterir ve gizler', async ({ page }) => {
  await openLogin(page);
  const toggle = page.locator('#password-show-password');
  await expect(toggle).toHaveAttribute('aria-label', 'Parolayı gösterin');
  await toggle.click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'text');
  await expect(toggle).toHaveAttribute('aria-label', 'Parolayı gizleyin');
  await toggle.click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'password');
});

test('parola sıfırlama: istek gönderilir ve bilgi iletisi görünür', async ({ page }) => {
  const email = await createUser();
  await screen('parola-sifirlama').open(page);
  await page.locator('#username').fill(email);
  await page.locator('#kc-reset-password-form [type=submit]').click();
  await expect(page.locator('.pf-v5-c-alert')).toContainText('Bu adres kayıtlıysa size bir e-posta gönderdik.');
});

test('TOTP: kurulum tamamlanır ve sonraki girişte kod sorulur', async ({ page, context }) => {
  const email = await createUser({ requiredActions: ['CONFIGURE_TOTP'] });
  await openLogin(page);
  await submitPassword(page, email);
  await page.locator('#mode-manual').click();
  const key = (await page.locator('#kc-totp-secret-key').innerText()).trim();
  await page.locator('#totp').fill(totp(base32Decode(key)));
  await page.locator('#userLabel').fill('Telefon');
  await page.locator('#saveTOTPBtn').click();
  await expect(page).toHaveURL(accountUrl);

  await page.waitForLoadState('networkidle');
  await context.clearCookies();
  await openLogin(page);
  await submitPassword(page, email);
  await expect(page.locator('#kc-otp-login-form')).toBeVisible();
  await page.locator('#otp').fill('000000');
  await page.locator('#kc-login').click();
  await expect(page.locator('#input-error-otp')).toHaveText('Kod yanlış. Uygulamadaki yeni kodu yazın.');
  // Keycloak aynı kodu iki kez kabul etmez. Bu yüzden bir sonraki 30 saniyenin kodu yazılır.
  await page.locator('#otp').fill(totp(base32Decode(key), Date.now() + 30_000));
  await page.locator('#kc-login').click();
  await expect(page).toHaveURL(accountUrl);
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
  await page.locator('#registerWebAuthn').click();
  await expect(page).toHaveURL(accountUrl);

  await page.waitForLoadState('networkidle');
  await context.clearCookies();
  // Sanal anahtar soruyu kendiliğinden yanıtlar. Düğmeyi sınamak için yanıt önce durdurulur.
  await cdp.send('WebAuthn.setAutomaticPresenceSimulation', { authenticatorId, enabled: false });
  await openLogin(page);
  await cdp.send('WebAuthn.setAutomaticPresenceSimulation', { authenticatorId, enabled: true });
  await page.locator('#authenticateWebAuthnButton').click();
  await expect(page).toHaveURL(accountUrl);
});

test('passkey hatası: yalın bir ileti ve yeniden deneme düğmesi görünür', async ({ page }) => {
  await screen('passkey-hata').open(page);
  await expect(page.locator('#kc-try-again')).toBeVisible();
  await expect(page.locator('.pf-v5-c-alert')).toContainText('Geçiş anahtarı');
});
