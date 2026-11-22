import { createHmac, randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, type Page } from '@playwright/test';

// Ortam değerleri bin/tema-dev.sh betiğinin ürettiği .env dosyasından gelir.
const envPath = fileURLToPath(new URL('../.env', import.meta.url));
const env = Object.fromEntries(
  readFileSync(envPath, 'utf8')
    .split('\n')
    .filter((line) => line.includes('=') && !line.startsWith('#'))
    .map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]),
);

export const KC = env.KC_PUBLIC_URL;
export const MAILPIT = `http://127.0.0.1:${env.MAILPIT_UI_PORT}`;
export const REALM = 'tema-deneme';
/** Address of the account deletion page of the test environment. It comes from the IDENTITY_ACCOUNT_DELETION_URL variable. */
export const ACCOUNT_DELETION_URL: string = env.IDENTITY_ACCOUNT_DELETION_URL ?? '';
/** Brand name of the test environment. It comes from the IDENTITY_BRAND_NAME variable, never from the theme. */
export const BRAND: string = env.IDENTITY_BRAND_NAME ?? '';
// Uydurma deneme parolası. Gerçek hesapta kullanılmaz.
export const PASSWORD = 'uzun-deneme-parolasi-1';
export const TOTP_SECRET = 'atonota-deneme-anahtar';

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

export async function admin(path: string, init: { method?: string; body?: unknown } = {}): Promise<Response> {
  return fetch(`${KC}/admin/realms/${REALM}${path}`, {
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
  /** Marks the user as a customer: grants the realm role "request-account-deletion". An employee does not have it. */
  canDeleteAccount?: boolean;
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
  });
  if (res.status !== 201) throw new Error(`Kullanıcı açılamadı: ${res.status} ${await res.text()}`);
  if (options.canDeleteAccount) await grantDeleteAccount(res.headers.get('location')!.split('/').pop()!);
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
export function loginUrl(locale?: string): string {
  const params = new URLSearchParams({
    client_id: 'account-console',
    redirect_uri: `${KC}/realms/${REALM}/account/`,
    response_type: 'code',
    scope: 'openid',
    code_challenge: 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    code_challenge_method: 'S256',
  });
  if (locale) params.set('ui_locales', locale);
  return `${KC}/realms/${REALM}/protocol/openid-connect/auth?${params}`;
}

export async function openLogin(page: Page, locale?: string): Promise<void> {
  await page.goto(loginUrl(locale));
  await expect(page.locator('#kc-form-login')).toBeVisible();
}

export async function submitPassword(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.locator('#username').fill(email);
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
}

export type Screen = { name: string; open: (page: Page) => Promise<void> };

/** Görev kapsamındaki ekranlar: giriş, kayıt, parola sıfırlama, TOTP ve passkey. */
export const screens: Screen[] = [
  { name: 'giris', open: (page) => openLogin(page) },
  {
    name: 'giris-hata',
    open: async (page) => {
      await openLogin(page);
      await submitPassword(page, 'yok@ornek.test', 'yanlis-parola');
      await expect(page.locator('#input-error-username')).toBeVisible();
    },
  },
  {
    name: 'kayit',
    open: async (page) => {
      await openLogin(page);
      await page.locator('#kc-registration a').click();
      await expect(page.locator('#kc-register-form')).toBeVisible();
    },
  },
  {
    name: 'kayit-hata',
    open: async (page) => {
      await openLogin(page);
      await page.locator('#kc-registration a').click();
      await page.locator('#kc-register-form [type=submit]').click();
      await expect(page.locator('#input-error-email')).toBeVisible();
    },
  },
  {
    name: 'parola-sifirlama',
    open: async (page) => {
      await openLogin(page);
      await page.locator('a[href*="reset-credentials"]').click();
      await expect(page.locator('#kc-reset-password-form')).toBeVisible();
    },
  },
  {
    name: 'parola-yenileme',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['UPDATE_PASSWORD'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-passwd-update-form')).toBeVisible();
    },
  },
  {
    name: 'totp-kurulum',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['CONFIGURE_TOTP'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-totp-settings-form')).toBeVisible();
    },
  },
  {
    name: 'totp-giris',
    open: async (page) => {
      const email = await createUser({ totp: true });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#kc-otp-login-form')).toBeVisible();
    },
  },
  {
    name: 'passkey-kayit',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['webauthn-register-passwordless'] });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#registerWebAuthn')).toBeVisible();
    },
  },
  {
    name: 'passkey-giris',
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
    name: 'giris-yolu',
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
    name: 'eposta-dogrulama',
    open: async (page) => {
      const email = await createUser({ requiredActions: ['VERIFY_EMAIL'], emailVerified: false });
      await openLogin(page);
      await submitPassword(page, email);
      await expect(page.locator('#at-resend')).toBeVisible();
    },
  },
  {
    name: 'passkey-hata',
    open: async (page) => {
      // Tarayıcının anahtar penceresi testte açılamaz. Ret yanıtı burada taklit edilir.
      await page.addInitScript(() => {
        const reject = () => Promise.reject(new DOMException('Deneme reddi', 'NotAllowedError'));
        Object.defineProperty(navigator, 'credentials', { value: { create: reject, get: reject } });
      });
      const email = await createUser({ requiredActions: ['webauthn-register-passwordless'] });
      await openLogin(page);
      await submitPassword(page, email);
      await page.locator('#registerWebAuthn').click();
      await expect(page.locator('#kc-error-credential-form')).toBeAttached();
    },
  },
];

export const screen = (name: string): Screen => {
  const found = screens.find((item) => item.name === name);
  if (!found) throw new Error(`Ekran yok: ${name}`);
  return found;
};

/**
 * Keeps the Keycloak "delete_account" required action switched off in the test realm, as the contract says.
 * Keycloak's own action deletes the user in the first step, so the product does not use it.
 */
export async function ensureKeycloakDeleteActionOff(): Promise<void> {
  const action = (await (await admin('/authentication/required-actions/delete_account')).json()) as { enabled: boolean };
  if (!action.enabled) return;
  const res = await admin('/authentication/required-actions/delete_account', { method: 'PUT', body: { ...action, enabled: false } });
  if (!res.ok) throw new Error(`Could not disable delete_account: ${res.status}`);
}

/** Realm role that marks a customer. The account console provider shows the deletion link only to this role. */
export const CUSTOMER_ROLE = 'request-account-deletion';

async function grantDeleteAccount(userId: string): Promise<void> {
  await ensureKeycloakDeleteActionOff();
  // The role is created on first use. A second create answers 409, which is fine.
  const created = await admin('/roles', { method: 'POST', body: { name: CUSTOMER_ROLE, description: 'May ask for the deletion of the own account' } });
  if (!created.ok && created.status !== 409) throw new Error(`Could not create ${CUSTOMER_ROLE}: ${created.status}`);
  const role = await (await admin(`/roles/${CUSTOMER_ROLE}`)).json();
  const res = await admin(`/users/${userId}/role-mappings/realm`, { method: 'POST', body: [role] });
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

/** Reads the current state of Keycloak's "delete_account" required action. */
export async function keycloakDeleteActionEnabled(): Promise<boolean> {
  return ((await (await admin('/authentication/required-actions/delete_account')).json()) as { enabled: boolean }).enabled;
}

/** Switches Keycloak's "delete_account" required action on or off. Only the serial realm-settings tests use it. */
export async function setKeycloakDeleteAction(enabled: boolean): Promise<void> {
  const action = (await (await admin('/authentication/required-actions/delete_account')).json()) as { enabled: boolean };
  const res = await admin('/authentication/required-actions/delete_account', { method: 'PUT', body: { ...action, enabled } });
  if (!res.ok) throw new Error(`Could not set delete_account to ${enabled}: ${res.status}`);
}

/** Returns true when a user with this email still exists in the test realm. */
export async function userExists(email: string): Promise<boolean> {
  const users = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as unknown[];
  return users.length > 0;
}
