import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import { KC, MAILPIT, REALM, admin, createUser, loginUrl, screen } from './helpers';

// Atonota e-posta temasının testleri. E-postalar Mailpit kutusundan okunur.
// Her test kendi uydurma alıcısını açar ve yalnız o alıcının postasını arar.
// Beklenen metinler görev belgesinden ve yalın Türkçe yazım kurallarından gelir.

const emailDir = fileURLToPath(new URL('../../email/', import.meta.url));
// Dolu ise her e-postanın 320 ve 600 piksel görüntüsü bu klasöre yazılır.
const shotDir = process.env.KC_THEME_EMAIL_SCREENSHOTS;
// Sihirli bağlantı eklentisi tema deneme ortamında kurulu değildir.
// Eklentili ikinci bir Keycloak varsa adresi bu değişkenle verilir.
const magicKc = process.env.MAGIC_LINK_KC_URL;

type Lang = 'tr' | 'en';
type Mail = { subject: string; html: string; text: string };
type Copy = { subject: string; title: string; intro: string; button: string; note: string };

const common: Record<Lang, { copyHint: string; sentBy: (realm: string) => string; expiry: (period: string) => string }> = {
  tr: {
    copyHint: 'Düğme çalışmazsa bu adresi kopyalayın ve tarayıcınıza yapıştırın.',
    sentBy: (realm) => `Bu e-postayı ${realm} gönderdi.`,
    expiry: (period) => `Bu bağlantı ${period} geçerlidir.`,
  },
  en: {
    copyHint: 'If the button does not work, copy this address into your browser.',
    sentBy: (realm) => `${realm} sent this email.`,
    expiry: (period) => `This link works for ${period}.`,
  },
};

const copy: Record<'verification' | 'password' | 'action', Record<Lang, (realm: string) => Copy>> = {
  verification: {
    tr: (realm) => ({
      subject: 'E-posta adresinizi doğrulayın',
      title: 'E-posta adresinizi doğrulayın',
      intro: `Bu e-posta adresiyle bir ${realm} hesabı açıldı. Hesabı siz açtıysanız aşağıdaki düğmeye basın.`,
      button: 'E-posta adresinizi doğrulayın',
      note: 'Hesabı siz açmadıysanız bu e-postayı yok sayın.',
    }),
    en: (realm) => ({
      subject: 'Verify your email address',
      title: 'Verify your email address',
      intro: `A ${realm} account was created with this email address. If you created it, press the button below.`,
      button: 'Verify your email address',
      note: 'If you did not create this account, ignore this email.',
    }),
  },
  password: {
    tr: (realm) => ({
      subject: 'Parolanızı sıfırlayın',
      title: 'Parolanızı sıfırlayın',
      intro: `${realm} hesabınız için parola sıfırlama isteği aldık. Yeni parola belirlemek için aşağıdaki düğmeye basın.`,
      button: 'Yeni parola belirleyin',
      note: 'Bu isteği siz yapmadıysanız bu e-postayı yok sayın. Parolanız değişmez.',
    }),
    en: (realm) => ({
      subject: 'Reset your password',
      title: 'Reset your password',
      intro: `We received a request to reset the password of your ${realm} account. Press the button below to set a new password.`,
      button: 'Set a new password',
      note: 'If you did not ask for this, ignore this email. Your password stays the same.',
    }),
  },
  action: {
    tr: (realm) => ({
      subject: 'Hesabınızı güncelleyin',
      title: 'Hesabınızı güncelleyin',
      intro: `Yöneticiniz ${realm} hesabınızda şu işlemleri yapmanızı istedi.`,
      button: 'İşlemlere başlayın',
      note: 'Bu istekten haberiniz yoksa bu e-postayı yok sayın. Hesabınızda hiçbir şey değişmez.',
    }),
    en: (realm) => ({
      subject: 'Update your account',
      title: 'Update your account',
      intro: `Your administrator asked you to do the following in your ${realm} account.`,
      button: 'Start',
      note: 'If you did not expect this, ignore this email. Nothing in your account changes.',
    }),
  },
};

const actionNames: Record<Lang, string[]> = {
  tr: ['Yeni parola belirleyin', 'Doğrulama uygulamasını kurun'],
  en: ['Set a new password', 'Set up the authenticator app'],
};

type RealmInfo = { name: string; userLifespan: number; adminLifespan: number };
let realmInfo: RealmInfo | undefined;

async function realm(): Promise<RealmInfo> {
  if (realmInfo) return realmInfo;
  const rep = (await (await admin('')).json()) as {
    displayName?: string;
    actionTokenGeneratedByUserLifespan: number;
    actionTokenGeneratedByAdminLifespan: number;
  };
  if (!rep.displayName) throw new Error('Deneme realm’inde görünen ad yok');
  realmInfo = {
    name: rep.displayName,
    userLifespan: rep.actionTokenGeneratedByUserLifespan,
    adminLifespan: rep.actionTokenGeneratedByAdminLifespan,
  };
  return realmInfo;
}

/** Keycloak süreyi dakika olarak verir ve en büyük tam birimle yazar. */
function period(seconds: number, lang: Lang): string {
  const minutes = Math.floor(seconds / 60);
  const units = { tr: ['gün', 'saat', 'dakika'], en: ['day', 'hour', 'minute'] }[lang];
  const [value, unit] =
    minutes % 1440 === 0 ? [minutes / 1440, units[0]] : minutes % 60 === 0 ? [minutes / 60, units[1]] : [minutes, units[2]];
  return `${value} ${unit}${lang === 'en' && value !== 1 ? 's' : ''}`;
}

async function userId(email: string): Promise<string> {
  const users = (await (await admin(`/users?exact=true&email=${encodeURIComponent(email)}`)).json()) as { id: string }[];
  if (users.length !== 1) throw new Error(`Kullanıcı bulunamadı: ${email}`);
  return users[0].id;
}

/** Alıcının kutusuna düşen tek e-postayı bekler ve okur. Başka alıcının postasına bakmaz. */
async function waitMail(to: string, base = MAILPIT): Promise<Mail> {
  const until = Date.now() + 20_000;
  while (Date.now() < until) {
    const res = await fetch(`${base}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    const list = ((await res.json()) as { messages?: { ID: string }[] }).messages ?? [];
    if (list.length > 0) {
      expect(list, `${to} tek e-posta almalı`).toHaveLength(1);
      const mail = (await (await fetch(`${base}/api/v1/message/${list[0].ID}`)).json()) as {
        Subject: string;
        HTML: string;
        Text: string;
      };
      return { subject: mail.Subject, html: mail.HTML, text: mail.Text };
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`${to} için e-posta gelmedi`);
}

async function sendVerify(lang: Lang): Promise<string> {
  const email = await createUser({ locale: lang });
  const id = await userId(email);
  const off = await admin(`/users/${id}`, { method: 'PUT', body: { emailVerified: false } });
  expect(off.status).toBe(204);
  const res = await admin(`/users/${id}/send-verify-email`, { method: 'PUT' });
  expect(res.status, 'doğrulama e-postası isteği').toBe(204);
  return email;
}

async function sendActions(lang: Lang): Promise<string> {
  const email = await createUser({ locale: lang });
  const res = await admin(`/users/${await userId(email)}/execute-actions-email`, {
    method: 'PUT',
    body: ['UPDATE_PASSWORD', 'CONFIGURE_TOTP'],
  });
  expect(res.status, 'gerekli işlem e-postası isteği').toBe(204);
  return email;
}

/** Parola sıfırlamayı kullanıcının gerçek yolundan ister: giriş ekranındaki bağlantı. */
async function sendReset(page: Page, lang: Lang): Promise<string> {
  const email = await createUser({ locale: lang });
  await screen('password-reset').open(page);
  await page.locator('#username').fill(email);
  await page.locator('#kc-reset-password-form [type=submit]').click();
  await expect(page.locator('#kc-reset-password-form')).toHaveCount(0);
  return email;
}

const urlsIn = (text: string): string[] => [
  ...new Set((text.match(/https?:\/\/[^\s"'<>]+/g) ?? []).map((url) => url.replaceAll('&amp;', '&'))),
];

function linkOf(mail: Mail): string {
  const links = urlsIn(mail.text);
  expect(links, 'düz metinde tek bağlantı').toHaveLength(1);
  return links[0];
}

/** Dış betik, dış stil, dış yazı tipi ve dış görsel yoktur. Tek dış adres işlem bağlantısıdır. */
function expectSelfContained(html: string, link: string): void {
  expect(html).not.toMatch(/<script/i);
  expect(html).not.toMatch(/<link/i);
  expect(html).not.toMatch(/<style/i);
  expect(html).not.toMatch(/@import/i);
  expect(html).not.toMatch(/<img/i);
  expect(html).not.toMatch(/\ssrc\s*=/i);
  expect(html).not.toMatch(/url\(/i);
  expect(html).not.toMatch(/\son[a-z]+\s*=/i);
  expect(urlsIn(html), 'HTML gövdedeki dış adresler').toEqual([link]);
}

/** HTML gövdeyi tarayıcıda açar. Ağ isteği atılmamalıdır. */
async function render(page: Page, html: string, width: number): Promise<string[]> {
  const requests: string[] = [];
  // Önceki sayfanın süren istekleri sayıma karışmasın.
  await page.goto('about:blank');
  await page.route('**/*', (route) => {
    requests.push(route.request().url());
    return route.abort();
  });
  await page.setViewportSize({ width, height: 800 });
  await page.setContent(html, { waitUntil: 'load' });
  return requests;
}

async function expectReadable(page: Page, width: number): Promise<void> {
  const result = await page.evaluate(() => {
    const small: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent?.trim();
      const parent = node.parentElement;
      if (!text || !parent || parent.getClientRects().length === 0) continue;
      const size = Number.parseFloat(getComputedStyle(parent).fontSize);
      if (size < 14) small.push(`${size}px: ${text.slice(0, 40)}`);
    }
    const wide = [...document.body.querySelectorAll('*')]
      .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 0.5)
      .map((el) => `${el.tagName} ${Math.round(el.getBoundingClientRect().right)}`);
    return { small, wide, scroll: document.documentElement.scrollWidth, inner: window.innerWidth };
  });
  expect(result.small, `${width}: 14 pikselden küçük metin`).toEqual([]);
  expect(result.wide, `${width}: ekrandan taşan öğe`).toEqual([]);
  expect(result.scroll, `${width}: yatay taşma`).toBeLessThanOrEqual(result.inner);
}

async function expectMail(
  page: Page,
  mail: Mail,
  lang: Lang,
  expected: Copy,
  expiry: string,
  shotName: string,
  extra: string[] = [],
): Promise<string> {
  const { name } = await realm();
  expect(mail.subject).toBe(expected.subject);

  const link = linkOf(mail);
  expect(link.startsWith(`${KC}/realms/${REALM}/login-actions/action-token`), link).toBe(true);
  const lines = [name, expected.title, expected.intro, ...extra, expiry, expected.note];
  for (const line of lines) expect(mail.text, 'düz metin sürümü').toContain(line);
  expect(mail.text).not.toMatch(/<[a-z/]/i);

  expectSelfContained(mail.html, link);

  for (const width of [320, 600]) {
    const requests = await render(page, mail.html, width);
    await expect(page.locator('html')).toHaveAttribute('lang', lang);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(expected.title);
    const button = page.getByRole('link', { name: expected.button, exact: true });
    await expect(button).toHaveAttribute('href', link);
    await expect(page.getByRole('link', { name: link, exact: true })).toHaveAttribute('href', link);
    const body = page.locator('body');
    for (const line of [...lines, common[lang].copyHint, common[lang].sentBy(name)]) {
      await expect(body).toContainText(line);
    }
    await expectReadable(page, width);
    const box = await button.boundingBox();
    expect(box?.height ?? 0, `${width}: düğme yüksekliği`).toBeGreaterThanOrEqual(44);
    expect(
      await page.getByText(expected.intro).evaluate((el) => Number.parseFloat(getComputedStyle(el).fontSize)),
      `${width}: gövde metni`,
    ).toBeGreaterThanOrEqual(16);
    expect(requests, `${width}: ağ isteği`).toEqual([]);
    if (shotDir) {
      mkdirSync(shotDir, { recursive: true });
      const browser = page.context().browser()?.browserType().name();
      await page.screenshot({ path: join(shotDir, `${shotName}-${lang}-${width}-${browser}.png`), fullPage: true });
    }
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  }
  return link;
}

const readMessages = (lang: Lang, directory = emailDir): Map<string, string> => {
  const entries = new Map<string, string>();
  for (const line of readFileSync(join(directory, 'messages', `messages_${lang}.properties`), 'utf8').split('\n')) {
    if (!line.trim() || line.startsWith('#') || !line.includes('=')) continue;
    entries.set(line.slice(0, line.indexOf('=')).trim().replace(/\\ /g, ' '), line.slice(line.indexOf('=') + 1));
  }
  return entries;
};

test.describe('e-posta ileti dosyaları', () => {
  test('Türkçe ve İngilizce e-posta iletileri aynı anahtarları taşır', () => {
    const tr = readMessages('tr');
    const en = readMessages('en');
    expect(tr.size).toBeGreaterThan(0);
    expect([...tr.keys()].filter((key) => !en.has(key)), 'İngilizcede eksik').toEqual([]);
    expect([...en.keys()].filter((key) => !tr.has(key)), 'Türkçede eksik').toEqual([]);
    for (const [lang, entries] of [['tr', tr], ['en', en]] as const) {
      expect([...entries].filter(([, value]) => !value.trim()).map(([key]) => key), `${lang}: boş ileti`).toEqual([]);
    }
  });

  test('e-posta iletilerinde marka adı sabit yazılmaz ve HTML etiketi bulunmaz', () => {
    for (const lang of ['tr', 'en'] as const) {
      const entries = [...readMessages(lang)];
      expect(entries.filter(([, value]) => /atonota/i.test(value)).map(([key]) => key), `${lang}: marka adı`).toEqual([]);
      expect(entries.filter(([, value]) => /<[a-z/]/i.test(value)).map(([key]) => key), `${lang}: HTML etiketi`).toEqual([]);
      // Noktalı virgül ve uzun çizgi yalın yazım kuralına aykırıdır.
      expect(entries.filter(([, value]) => /[;—–]/.test(value)).map(([key]) => key), `${lang}: yasak işaret`).toEqual([]);
    }
  });

  test('HTML şablonları dış kaynak çağırmaz ve her şablonun düz metin eşi vardır', () => {
    const htmlFiles = readdirSync(join(emailDir, 'html')).filter((file) => file.endsWith('.ftl'));
    for (const file of ['template.ftl', 'email-verification.ftl', 'password-reset.ftl', 'executeActions.ftl']) {
      expect(htmlFiles, file).toContain(file);
    }
    for (const file of htmlFiles) {
      // Açıklama satırları e-postaya çıkmaz. Denetim yalnız çıktıya giden bölüme bakar.
      const source = readFileSync(join(emailDir, 'html', file), 'utf8').replace(/<#--[\s\S]*?-->/g, '');
      expect(source, file).not.toMatch(/<script|<link|<style|@import|<img|\ssrc\s*=|url\(|https?:\/\//i);
      expect(source, `${file}: sabit marka adı`).not.toMatch(/atonota/i);
      if (file !== 'template.ftl') expect(existsSync(join(emailDir, 'text', file)), `text/${file}`).toBe(true);
    }
  });

  test('sihirli bağlantı şablonları ve iletileri kurulu eklentiyle eşleşir', () => {
    const jar = process.env.MAGIC_LINK_PROVIDER_JAR;
    test.skip(!jar, 'Kurulu eklentinin arşiv yolu MAGIC_LINK_PROVIDER_JAR ile verilir.');
    if (!jar) return;

    const entries = execFileSync('unzip', ['-Z1', jar], { encoding: 'utf8' }).trim().split(/\r?\n/);
    const templates = entries.flatMap((entry) => {
      const template = /^theme-resources\/templates\/((?:html|text)\/[^/]+\.ftl)$/.exec(entry);
      return template ? [template[1]] : [];
    });
    expect(templates.map((template) => template.split('/')[0]).sort()).toEqual(['html', 'text']);

    const messagesEntry = 'theme-resources/messages/messages_en.properties';
    expect(entries).toContain(messagesEntry);
    const messages = execFileSync('unzip', ['-p', jar, messagesEntry], { encoding: 'utf8' });
    const subjectKeys = [...messages.matchAll(/^([^#=\s]+[Ss]ubject)\s*=/gm)].map((match) => match[1]);
    expect(subjectKeys).toHaveLength(1);

    const constants = (className: string) => {
      const entry = entries.find((path) => path.endsWith(`/${className}.class`));
      if (!entry) throw new Error(`Provider class missing from archive: ${className}`);
      return execFileSync('unzip', ['-p', jar, entry]).toString('latin1').split(/[^ -~]+/);
    };
    const providerId = constants('MagicLinkAuthenticatorNormalFactory').find((value) => value === 'magiclink');
    const sentKey = constants('MagicLinkAuthenticatorNormal').find((value) => value.endsWith('-emailSentText'));
    const emptyEmailKey = constants('AbstractMagicLinkAuthenticator').find((value) => value === 'Email cannot be empty');
    expect(providerId).toBeDefined();
    expect(sentKey).toBeDefined();
    expect(emptyEmailKey).toBeDefined();
    expect(messages).toContain(`${sentKey}=`);
    // Keycloak looks up the alternatives using the provider ID and these suffixes.
    const loginKeys = [`${providerId}-display-name`, `${providerId}-help-text`, sentKey!, emptyEmailKey!];
    const loginDir = fileURLToPath(new URL('../../login/', import.meta.url));

    const missing = templates.filter((template) => !existsSync(join(emailDir, template)));
    for (const lang of ['tr', 'en'] as const) {
      if (!readMessages(lang).get(subjectKeys[0])?.trim()) {
        missing.push(`email/messages/messages_${lang}.properties: ${subjectKeys[0]}`);
      }
      const loginMessages = readMessages(lang, loginDir);
      for (const key of loginKeys) {
        if (!loginMessages.get(key)?.trim()) missing.push(`login/messages/messages_${lang}.properties: ${key}`);
      }
    }
    expect(missing, 'temada eksik şablon veya ileti anahtarı').toEqual([]);
  });
});

for (const lang of ['tr', 'en'] as const) {
  test.describe(`e-posta gövdesi (${lang})`, () => {
    test('e-posta doğrulama iletisi yalın metinle gelir', async ({ page }) => {
      const { name, adminLifespan } = await realm();
      const mail = await waitMail(await sendVerify(lang));
      await expectMail(page, mail, lang, copy.verification[lang](name), common[lang].expiry(period(adminLifespan, lang)), 'verification');
    });

    test('parola sıfırlama iletisi yalın metinle gelir', async ({ page }) => {
      const { name, userLifespan } = await realm();
      const mail = await waitMail(await sendReset(page, lang));
      await expectMail(page, mail, lang, copy.password[lang](name), common[lang].expiry(period(userLifespan, lang)), 'password');
    });

    test('gerekli işlem iletisi işlemleri sayar', async ({ page }) => {
      const { name, adminLifespan } = await realm();
      const mail = await waitMail(await sendActions(lang));
      const expiry = common[lang].expiry(period(adminLifespan, lang));
      await expectMail(page, mail, lang, copy.action[lang](name), expiry, 'action', actionNames[lang]);
      await expect(page.getByRole('listitem')).toHaveText(actionNames[lang]);
    });
  });
}

test.describe('e-postadaki bağlantı', () => {
  const proceed = (page: Page) => page.locator('a[href*="login-actions/action-token"]');

  test('parola sıfırlama bağlantısı yeni parola formunu açar', async ({ page }) => {
    const mail = await waitMail(await sendReset(page, 'tr'));
    await page.goto(linkOf(mail));
    await expect(page.locator('#kc-passwd-update-form')).toBeVisible();
  });

  test('doğrulama bağlantısı e-posta adresini doğrular', async ({ page }) => {
    const email = await sendVerify('tr');
    const mail = await waitMail(email);
    await page.goto(linkOf(mail));
    // Keycloak yöneticinin gönderdiği bağlantıda önce onay ister.
    if (await proceed(page).count()) await proceed(page).first().click();
    const id = await userId(email);
    await expect
      .poll(async () => ((await (await admin(`/users/${id}`)).json()) as { emailVerified: boolean }).emailVerified)
      .toBe(true);
  });

  test('gerekli işlem bağlantısı istenen işlemin formunu açar', async ({ page }) => {
    const mail = await waitMail(await sendActions('tr'));
    await page.goto(linkOf(mail));
    // İki işlem istendi. Keycloak sırayı kendi belirler ve ilk işlemin formunu açar.
    const form = page.locator('#kc-passwd-update-form, #kc-totp-settings-form');
    await expect(form.or(proceed(page)).first()).toBeVisible();
    if (!(await form.isVisible())) await proceed(page).first().click();
    await expect(form).toBeVisible();
  });
});

test.describe('sihirli bağlantı e-postası', () => {
  test.skip(!magicKc, 'Eklentili Keycloak adresi (MAGIC_LINK_KC_URL) verilmedi. Tema deneme ortamında eklenti yok.');

  for (const lang of ['tr', 'en'] as const) {
    test(`sihirli bağlantı iletisi yalın metinle gelir (${lang})`, async ({ page }) => {
      const base = magicKc as string;
      const mailpit = process.env.MAGIC_LINK_MAILPIT_URL ?? MAILPIT;
      const realmName = process.env.MAGIC_LINK_REALM ?? REALM;
      const email = `sihirli-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}@ornek.test`;
      const token = process.env.MAGIC_LINK_ADMIN_TOKEN;
      if (!token) throw new Error('MAGIC_LINK_ADMIN_TOKEN gerekli');
      const headers = { authorization: `Bearer ${token}`, 'content-type': 'application/json' };
      const created = await fetch(`${base}/admin/realms/${realmName}/users`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ username: email, email, enabled: true, emailVerified: true, attributes: { locale: [lang] } }),
      });
      expect(created.status).toBe(201);
      await page.goto(loginUrl(lang, realmName, base));
      const alternative = page.locator('form:has([name="tryAnotherWay"])');
      await alternative.evaluate((form: HTMLFormElement) => form.requestSubmit());
      const signInOption = {
        tr: 'E-posta bağlantısı E-postanıza gelen bağlantıyla oturum açın.',
        en: 'Email link Sign in with a link sent to your email.',
      };
      await page.getByRole('button', { name: signInOption[lang], exact: true }).click();
      const username = page.locator('input[name="username"]:visible');
      await username.fill(email);
      await username.evaluate((input: HTMLInputElement) => input.form!.requestSubmit());

      const mail = await waitMail(email, mailpit);
      const expected: Record<Lang, Copy & { expiry: string; browser: string }> = {
        tr: {
          subject: 'Oturum açma bağlantınız',
          title: 'Oturum açın',
          intro: 'hesabınıza parola yazmadan girebilirsiniz. Oturum açmak için aşağıdaki düğmeye basın.',
          button: 'Oturum açın',
          note: 'Bu isteği siz yapmadıysanız bu e-postayı yok sayın. Bağlantıya basmazsanız oturum açılmaz.',
          expiry: 'Bu bağlantı kısa süre geçerlidir ve yalnız bir kez çalışır.',
          browser: 'Bağlantıyı oturum açmayı başlattığınız tarayıcıda açın.',
        },
        en: {
          subject: 'Your sign-in link',
          title: 'Sign in',
          intro: 'account without a password. Press the button below to sign in.',
          button: 'Sign in',
          note: 'If you did not ask for this, ignore this email. Nobody is signed in unless the link is opened.',
          expiry: 'This link works for a short time and only once.',
          browser: 'Open the link in the browser where you started signing in.',
        },
      };
      const want = expected[lang];
      expect(mail.subject).toBe(want.subject);
      const link = linkOf(mail);
      expectSelfContained(mail.html, link);
      for (const line of [want.title, want.intro, want.expiry, want.browser, want.note]) expect(mail.text).toContain(line);
      for (const width of [320, 600]) {
        const requests = await render(page, mail.html, width);
        await expect(page.getByRole('heading', { level: 1 })).toHaveText(want.title);
        await expect(page.getByRole('link', { name: want.button, exact: true })).toHaveAttribute('href', link);
        for (const line of [want.intro, want.expiry, want.browser, want.note]) {
          await expect(page.locator('body')).toContainText(line);
        }
        await expectReadable(page, width);
        expect(requests).toEqual([]);
        if (shotDir) {
          mkdirSync(shotDir, { recursive: true });
          const browser = page.context().browser()?.browserType().name();
          await page.screenshot({ path: join(shotDir, `sihirli-${lang}-${width}-${browser}.png`), fullPage: true });
        }
        await page.unrouteAll({ behavior: 'ignoreErrors' });
      }
    });
  }
});

test('email colours are the light design tokens of the login theme', () => {
  // An email cannot read CSS variables, so the template repeats the values. This test keeps the copy equal.
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const css = readFileSync(`${root}login/resources/css/atonota.css`, 'utf8');
  const lightStart = css.indexOf('/* tokens:start */');
  const darkStart = css.indexOf(':root.pf-v5-theme-dark');
  expect(lightStart).toBeGreaterThanOrEqual(0);
  expect(darkStart).toBeGreaterThan(lightStart);
  const lightBlock = css.slice(lightStart, darkStart);
  const token = (name: string) => new RegExp(`${name}:\\s*(#[0-9a-fA-F]{3,8})`).exec(lightBlock)?.[1].toLowerCase();
  const template = readFileSync(`${root}email/html/template.ftl`, 'utf8');
  const value = (name: string) => new RegExp(`${name} = "(#[0-9a-fA-F]{3,8})"`).exec(template)?.[1].toLowerCase();
  const pairs: Record<string, string> = {
    pageBg: '--at-color-page',
    cardBg: '--at-color-surface',
    ink: '--at-color-ink',
    quiet: '--at-color-ink-soft',
    buttonBg: '--at-color-action',
    buttonInk: '--at-color-on-action',
    linkInk: '--at-color-link',
    brandDot: '--at-color-seal',
  };
  for (const [emailName, tokenName] of Object.entries(pairs)) {
    expect(token(tokenName), `${tokenName} exists in the login theme`).toBeTruthy();
    expect(value(emailName), `${emailName} equals ${tokenName}`).toBe(token(tokenName));
  }
});
