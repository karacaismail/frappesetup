import { createHmac, randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, type Page } from '@playwright/test';

// Ortam değerleri bin/theme-dev.sh betiğinin ürettiği .env dosyasından gelir.
const envPath = fileURLToPath(new URL('../.env', import.meta.url));
const env = Object.fromEntries(
  readFileSync(envPath, 'utf8')
    .split('\n')
    .filter((line) => line.includes('=') && !line.startsWith('#'))
    .map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]),
);

export const KC = env.KC_PUBLIC_URL;
export const MAILPIT = `http://127.0.0.1:${env.MAILPIT_UI_PORT}`;
export const REALM = 'theme-test';
/** Address of the account deletion page of the test environment. It comes from the IDENTITY_ACCOUNT_DELETION_URL variable. */
export const ACCOUNT_DELETION_URL: string = env.IDENTITY_ACCOUNT_DELETION_URL ?? '';
/** Brand name of the test environment. It comes from the IDENTITY_BRAND_NAME variable, never from the theme. */
export const BRAND: string = env.IDENTITY_BRAND_NAME ?? '';
/**
 * Reads a secret test value. The value comes from the environment or from the .env file that
 * bin/theme-dev.sh writes. The repository holds no test secret. The value is never printed.
 */
function requiredSecret(name: string): string {
  const value = process.env[name] ?? env[name];
  if (!value) throw new Error(`${name} is not set. Run bin/theme-dev.sh up first. It writes a random value to test/.env.`);
  return value;
}

/** Password of the made-up test users. Random for each test environment. */
export const PASSWORD = requiredSecret('IDENTITY_TEST_PASSWORD');
/** TOTP secret of the made-up test users. Random for each test environment. */
export const TOTP_SECRET = requiredSecret('IDENTITY_TEST_TOTP_SECRET');

let cachedToken: { value: string; until: number } | undefined;

async function adminToken(): Promise<string> {
  if (cachedToken && cachedToken.until > Date.now()) return cachedToken.value;
  const res = await fetch(`${KC}/realms/master/protocol/openid-connect/token`, {
    method: 'POST',
    body: new URLSearchParams({
      grant_type: 'password',
      client_id: 'admin-cli',
      username: env.KC_BOOTSTRAP_ADMIN_USERNAME,
      password: env.KC_BOOTSTRAP_ADMIN_PASSWORD,
    }),
  });
  if (!res.ok) throw new Error(`Yönetici belirteci alınamadı: ${res.status}`);
  const body = (await res.json()) as { access_token: string };
  cachedToken = { value: body.access_token, until: Date.now() + 30_000 };
  return body.access_token;
}

export async function admin(path: string, init: { method?: string; body?: unknown } = {}, realm = REALM): Promise<Response> {
  return fetch(`${KC}/admin/realms/${realm}${path}`, {
    method: init.method ?? 'GET',
    headers: { authorization: `Bearer ${await adminToken()}`, 'content-type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

type UserOptions = {
  requiredActions?: string[];
  totp?: boolean;
  webauthn?: boolean;
  locale?: string;
  emailVerified?: boolean;
  /**
   * Marks the user as a customer: grants the realm role "request-account-deletion". An employee does not have it.
   * The role only shows the link to the deletion page. It gives no permission inside Keycloak.
   */
  customer?: boolean;
  /** Realm that gets the user. Default: the test realm. */
  realm?: string;
};

/** Uydurma bir kullanıcı açar. E-posta alanı `ornek.test` ayrılmış deneme alanıdır. */
export async function createUser(options: UserOptions = {}): Promise<string> {
  const email = `deneme-${randomUUID().slice(0, 12)}@ornek.test`;
  const credentials: Record<string, unknown>[] = [{ type: 'password', value: PASSWORD, temporary: false }];
  if (options.totp) {
    credentials.push({
      type: 'otp',
      userLabel: 'Telefon',
      secretData: JSON.stringify({ value: TOTP_SECRET }),
      credentialData: JSON.stringify({ subType: 'totp', digits: 6, period: 30, algorithm: 'HmacSHA1', counter: 0 }),
    });
  }
  if (options.webauthn) {
    // Yalnız ekranı göstermek için uydurma bir güvenlik anahtarı kaydı. Bu kayıtla giriş yapılamaz.
    credentials.push({
      type: 'webauthn',
      userLabel: 'Deneme anahtarı',
      secretData: '{}',
      credentialData: JSON.stringify({
        aaguid: '00000000-0000-0000-0000-000000000000',
        credentialId: Buffer.from(randomUUID()).toString('base64'),
        counter: 0,
        credentialPublicKey: 'pQECAyYgASFYIA',
        attestationStatementFormat: 'none',
        transports: ['usb'],
      }),
    });
  }
  const realm = options.realm ?? REALM;
  const res = await admin('/users', {
    method: 'POST',
    body: {
      username: email,
      email,
      enabled: true,
      emailVerified: options.emailVerified ?? true,
      firstName: 'Deneme',
      lastName: 'Kullanıcı',
      attributes: options.locale ? { locale: [options.locale] } : undefined,
      requiredActions: options.requiredActions ?? [],
      credentials,
    },
  }, realm);
  if (res.status !== 201) throw new Error(`Kullanıcı açılamadı: ${res.status} ${await res.text()}`);
  if (options.customer) await grantCustomerRole(res.headers.get('location')!.split('/').pop()!, realm);
  return email;
}

/** Giriş akışında güvenlik anahtarı adımını açar. Yalnız deneme realm'ini değiştirir. */
export async function enableWebAuthnSecondFactor(): Promise<void> {
  const executions = (await (await admin('/authentication/flows/browser/executions')).json()) as {
    id: string;
    providerId?: string;
    requirement: string;
  }[];
  const execution = executions.find((item) => item.providerId === 'webauthn-authenticator');
  if (!execution) throw new Error('webauthn-authenticator adımı bulunamadı');
  if (execution.requirement === 'ALTERNATIVE') return;
  const res = await admin('/authentication/flows/browser/executions', {
    method: 'PUT',
    body: { ...execution, requirement: 'ALTERNATIVE' },
  });
  if (!res.ok) throw new Error(`Akış değişmedi: ${res.status}`);
}

/** RFC 6238 tek kullanımlık kodu. Anahtar düz metindir (Keycloak kaydındaki değer). */
export function totp(secret: string | Buffer = TOTP_SECRET, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const digest = createHmac('sha1', secret).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const code = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return code.toString().padStart(6, '0');
}

export function base32Decode(text: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const char of text.replace(/[\s=]/g, '').toUpperCase()) {
    const index = alphabet.indexOf(char);
    if (index < 0) throw new Error(`Base32 dışı karakter: ${char}`);
    bits += index.toString(2).padStart(5, '0');
  }
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((byte) => Number.parseInt(byte, 2)));
}

/** Giriş ekranını açar. Hesap konsolu istemcisi PKCE ister, bu yüzden sabit bir sınama değeri verilir. */
export function loginUrl(locale?: string, realm = REALM, server = KC): string {
  const params = new URLSearchParams({
    client_id: 'account-console',
    redirect_uri: `${server}/realms/${realm}/account/`,
    response_type: 'code',
    scope: 'openid',
    code_challenge: 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    code_challenge_method: 'S256',
  });
  if (locale) params.set('ui_locales', locale);
  return `${server}/realms/${realm}/protocol/openid-connect/auth?${params}`;
}

export async function openLogin(page: Page, locale?: string): Promise<void> {
  await page.goto(loginUrl(locale));
  await expect(page.locator('#kc-form-login')).toBeVisible();
}

export async function submitPassword(page: Page, email: string, password = PASSWORD): Promise<void> {
  const username = page.locator('#username');
  const secret = page.locator('#password');
  // While the page loads, it moves focus to the first field. Text typed in that moment can land in the
  // wrong field. So the test waits for the "load" event and submits only when both fields hold the
  // right text. The check never prints the values.
  await expect(username).toBeVisible({ timeout: 20_000 });
  await page.waitForLoadState('load');
  await expect(async () => {
    await username.fill(email);
    await secret.fill(password);
    expect((await username.inputValue()) === email, 'the email field holds the email').toBe(true);
    expect((await secret.inputValue()) === password, 'the password field holds the password').toBe(true);
  }).toPass({ timeout: 20_000 });
  await page.locator('#kc-login').click();
}

export type Screen = { name: string; open: (page: Page) => Promise<void> };

/** Görev kapsamındaki ekranlar: giriş, kayıt, parola sıfırlama, TOTP ve passkey. */
export const screens: Screen[] = [
  { name: 'sign-in', open: (page) => openLogin(page) },
  {
    name: 'sign-in-error',
    open: async (page) => {
      await openLogin(page);
      await submitPassword(page, 'yok@ornek.test', 'yanlis-parola');
      await expect(page.locator('#input-error-username')).toBeVisible();
    },
  },
  {
    name: 'register',
    open: async (page) => {
      await openLogin(page);
      await page.locator('#kc-registration a').click();
      await expect(page.locator('#kc-register-form')).toBeVisible();
    },
  },
  {
    name: 'register-error',
    open: async (page) => {
      await openLogin(page);
      await page.locator('#kc-registration a').click();
      await page.locator('#kc-register-form [type=submit]').click();
      await expect(page.locator('#input-error-email')).toBeVisible();
    },
  },
  {
    name: 'password-reset',
    open: async (page) => {
      await openLogin(page);
      await page.locator('a[href*="reset-credentials"]').click();
      await expect(page.locator('#kc-reset-password-form')).toBeVisible();
    },
  },
  {
    name: 'password-update',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['UPDATE_PASSWORD'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-passwd-update-form')).toBeVisible();
    },
  },
  {
    name: 'totp-setup',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['CONFIGURE_TOTP'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-totp-settings-form')).toBeVisible();
    },
  },
  {
    name: 'totp-sign-in',
    open: async (page) => {
      const email = await createUser({ totp: true });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-otp-login-form')).toBeVisible();
    },
  },
  {
    name: 'passkey-register',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['webauthn-register-passwordless'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#registerWebAuthn')).toBeVisible();
    },
  },
  {
    name: 'passkey-sign-in',
    open: async (page) => {
      await enableWebAuthnSecondFactor();
      const email = await createUser({ webauthn: true });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#authenticateWebAuthnButton')).toBeVisible();
    },
  },
  {
    // Kullanıcının hem doğrulama uygulaması hem güvenlik anahtarı vardır. "Başka bir yol" seçenek listesini açar.
    name: 'sign-in-method',
    open: async (page) => {
      await enableWebAuthnSecondFactor();
      const email = await createUser({ totp: true, webauthn: true });
      await openLogin(page);
      await submitPassword(page, email);
      await page.locator('#try-another-way').click();
      await expect(page.locator('.at-choice').first()).toBeVisible();
    },
  },
  {
    name: 'email-verification',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['VERIFY_EMAIL'], emailVerified: false });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#at-resend')).toBeVisible();
    },
  },
  {
    name: 'passkey-error',
    open: async (page) => {
      // Tarayıcının anahtar penceresi testte açılamaz. Ret yanıtı burada taklit edilir.
      await page.addInitScript(() => {
        const reject = () => Promise.reject(new DOMException('Deneme reddi', 'NotAllowedError'));
        Object.defineProperty(navigator, 'credentials', { value: { create: reject, get: reject } });
      });
      const email = await createUser({ requiredActions: ['webauthn-register-passwordless'] });
      await openLogin(page);
      await submitPassword(page, email);
      // The page script binds the button after it loads. A click that comes earlier does nothing,
      // so the click is repeated until the error form arrives.
      const errorForm = page.locator('#kc-error-credential-form');
      await expect(async () => {
        if ((await errorForm.count()) === 0) await page.locator('#registerWebAuthn').click({ timeout: 2_000 }).catch(() => undefined);
        await expect(errorForm).toBeAttached({ timeout: 2_000 });
      }).toPass({ timeout: 30_000 });
    },
  },
  // Screens added for the technical debt "some theme screens are not tested".
  {
    name: 'update-profile',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['UPDATE_PROFILE'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-update-profile-form')).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    name: 'recovery-codes-setup',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['CONFIGURE_RECOVERY_AUTHN_CODES'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-recovery-codes-settings-form')).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    name: 'delete-credential',
    open: async (page) => {
      // The account console sends the user here to remove a sign-in method. The user must prove the identity first.
      const email = await createUser({ totp: true });
      const [user] = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as { id: string }[];
      const credentials = (await (await admin(`/users/${user.id}/credentials`)).json()) as { id: string; type: string }[];
      const otp = credentials.find((credential) => credential.type === 'otp')!;
      await page.goto(`${loginUrl()}&kc_action=${encodeURIComponent(`delete_credential:${otp.id}`)}`);
      await submitPassword(page, email);
      await expect(page.locator('#otp')).toBeVisible({ timeout: 20_000 });
      await page.locator('#otp').fill(totp());
      await page.locator('#kc-login').click();
      await expect(page.locator('#kc-accept')).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    name: 'sign-out-confirm',
    open: async (page) => {
      await page.goto(`${KC}/realms/${REALM}/protocol/openid-connect/logout`);
      await expect(page.locator('#kc-logout')).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    name: 'signed-out',
    open: async (page) => {
      await page.goto(`${KC}/realms/${REALM}/protocol/openid-connect/logout`);
      await page.locator('#kc-logout').click();
      await expect(page.locator('#kc-info-message')).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    name: 'error',
    open: async (page) => {
      // An application that Keycloak does not know. This is what a broken sign-in link looks like.
      await page.goto(`${KC}/realms/${REALM}/protocol/openid-connect/auth?client_id=unknown-application&response_type=code`);
      await expect(page.locator('#kc-error-message')).toBeVisible({ timeout: 20_000 });
    },
  },
  {
    name: 'page-expired',
    open: async (page) => {
      const email = await createUser({ totp: true });
      await openLogin(page);
      const firstStep = (await page.locator('#kc-form-login').getAttribute('action'))!;
      await submitPassword(page, email);
      await expect(page.locator('#otp')).toBeVisible({ timeout: 20_000 });
      // The address of the first step is now out of date. A restored tab or an old link opens it like this.
      await page.goto(firstStep);
      await expect(page.locator('#loginRestartLink')).toBeVisible({ timeout: 20_000 });
    },
  },
];

export const screen = (name: string): Screen => {
  const found = screens.find((item) => item.name === name);
  if (!found) throw new Error(`Ekran yok: ${name}`);
  return found;
};

/** Realm role that marks a customer. The account console provider shows the deletion link only to this role. */
export const CUSTOMER_ROLE = 'request-account-deletion';

async function grantCustomerRole(userId: string, realm = REALM): Promise<void> {
  // The role is created on first use. A second create answers 409, which is fine.
  const created = await admin('/roles', { method: 'POST', body: { name: CUSTOMER_ROLE, description: 'May ask for the deletion of the own account' } }, realm);
  if (!created.ok && created.status !== 409) throw new Error(`Could not create ${CUSTOMER_ROLE}: ${created.status}`);
  const role = await (await admin(`/roles/${CUSTOMER_ROLE}`, {}, realm)).json();
  const res = await admin(`/users/${userId}/role-mappings/realm`, { method: 'POST', body: [role] }, realm);
  if (!res.ok) throw new Error(`Could not grant ${CUSTOMER_ROLE}: ${res.status}`);
}

/**
 * Grants Keycloak's own "delete-account" role of the "account" client.
 * The product grants this role to nobody. Tests use it to prove that it does not show the deletion link.
 */
export async function grantStockDeleteRole(email: string): Promise<void> {
  const [user] = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as { id: string }[];
  const [client] = (await (await admin('/clients?clientId=account')).json()) as { id: string }[];
  const role = await (await admin(`/clients/${client.id}/roles/delete-account`)).json();
  const res = await admin(`/users/${user.id}/role-mappings/clients/${client.id}`, { method: 'POST', body: [role] });
  if (!res.ok) throw new Error(`Could not grant delete-account: ${res.status}`);
}

/** Reads the current state of Keycloak's "delete_account" required action. Nothing in the tests changes it in the test realm. */
export async function keycloakDeleteActionEnabled(realm = REALM): Promise<boolean> {
  return ((await (await admin('/authentication/required-actions/delete_account', {}, realm)).json()) as { enabled: boolean }).enabled;
}

/**
 * A second realm that is set up wrongly on purpose: Keycloak's "delete_account" action is switched on.
 * It is created from the realm file of the test realm. The test realm itself is never changed, so its own setting stays
 * exactly as the realm file installed it and a wrong start setting cannot be hidden.
 */
export const MISCONFIGURED_REALM = 'theme-test-delete-action-on';

/** Creates the wrongly configured realm when it does not exist yet and switches the delete action on in it. */
export async function ensureMisconfiguredRealm(): Promise<void> {
  if (!(await admin('', {}, MISCONFIGURED_REALM)).ok) {
    // The realm file of the test realm is the source, so both realms start with the same settings.
    const source = JSON.parse(readFileSync(new URL('../realm/theme-test-realm.json', import.meta.url), 'utf8')) as Record<string, unknown>;
    const created = await fetch(`${KC}/admin/realms`, {
      method: 'POST',
      headers: { authorization: `Bearer ${await adminToken()}`, 'content-type': 'application/json' },
      body: JSON.stringify({ ...source, realm: MISCONFIGURED_REALM }),
    });
    // Another worker may have created the realm a moment ago. That answers 409. The realm must exist afterwards.
    if (!created.ok && created.status !== 409) throw new Error(`Could not create ${MISCONFIGURED_REALM}: ${created.status} ${await created.text()}`);
    if (!(await admin('', {}, MISCONFIGURED_REALM)).ok) throw new Error(`${MISCONFIGURED_REALM} does not exist after its creation`);
  }
  const path = '/authentication/required-actions/delete_account';
  const action = (await (await admin(path, {}, MISCONFIGURED_REALM)).json()) as { enabled: boolean };
  if (!action.enabled) {
    const res = await admin(path, { method: 'PUT', body: { ...action, enabled: true } }, MISCONFIGURED_REALM);
    if (!res.ok) throw new Error(`Could not switch delete_account on in ${MISCONFIGURED_REALM}: ${res.status}`);
  }
}

/** Returns true when a user with this email still exists in the test realm. */
export async function userExists(email: string, realm = REALM): Promise<boolean> {
  const users = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`, {}, realm)).json()) as unknown[];
  return users.length > 0;
}

/** Ends every session of the user on the server, as an expired or revoked session would. The browser keeps its cookies. */
export async function endSessions(email: string, realm = REALM): Promise<void> {
  const [user] = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`, {}, realm)).json()) as { id: string }[];
  const res = await admin(`/users/${user.id}/logout`, { method: 'POST' }, realm);
  if (!res.ok) throw new Error(`Could not end the sessions: ${res.status}`);
}
