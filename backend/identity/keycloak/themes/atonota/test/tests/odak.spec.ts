import { expect, test, type Page } from '@playwright/test';
import { diffBox, focusDiff, PAD } from './focus-diff';
import { openLogin, screen } from './helpers';

// WebKit bağlantıları Tab sırasına almaz. Safari'deki Option+Tab karşılığı kullanılır.
const keys = (browserName: string) =>
  browserName === 'webkit' ? { tab: 'Alt+Tab', back: 'Alt+Shift+Tab' } : { tab: 'Tab', back: 'Shift+Tab' };

const activeName = (page: Page) =>
  page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return 'body';
    if (element.id) return element.id;
    const href = element.getAttribute('href') ?? '';
    if (href.includes('reset-credentials')) return 'parolami-unuttum';
    if (href.includes('registration')) return 'hesap-ac';
    // Kimliksiz öğeler sıra numarasıyla ayrılır. Böylece iki kimliksiz öğe aynı adı almaz.
    const index = [...document.querySelectorAll(element.tagName)].indexOf(element);
    return `${element.tagName.toLowerCase()}[${index}]`;
  });

const mode = (page: Page) => page.evaluate(() => document.documentElement.dataset.atFocus ?? '');

test('giriş ekranında Tab ve Shift+Tab sırası görsel sırayı izler', async ({ page, browserName }) => {
  const { tab, back } = keys(browserName);
  await openLogin(page);
  await expect(page.locator('#username')).toBeFocused();
  const expected = [
    'password',
    'password-show-password',
    'parolami-unuttum',
    'kc-login',
    'authenticateWebAuthnButton',
    'hesap-ac',
    'at-locale-tr',
    'at-locale-en',
  ];
  const forward: string[] = [];
  for (let step = 0; step < expected.length; step += 1) {
    await page.keyboard.press(tab);
    forward.push(await activeName(page));
  }
  expect(forward).toEqual(expected);
  const backward: string[] = [];
  for (let step = 0; step < expected.length; step += 1) {
    await page.keyboard.press(back);
    backward.push(await activeName(page));
  }
  expect(backward).toEqual([...expected.slice(0, -1).reverse(), 'username']);
});

test('klavye odak kipini yalnız Tab açar, işaretçi kapatır', async ({ page, browserName }) => {
  const { tab, back } = keys(browserName);
  await openLogin(page);
  expect(await mode(page), 'kip kapalı başlar').toBe('');

  await page.locator('#username').click();
  await page.keyboard.type('ab');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Escape');
  expect(await mode(page), 'yazma, ok ve Escape kipi açmaz').toBe('');

  await page.keyboard.press(tab);
  expect(await mode(page), 'Tab kipi açar').toBe('keyboard');
  await expect(page.locator('#password')).toBeFocused();

  // İşaretçi yalnız görsel kipi kapatır. Odak yerinde kalır.
  await page.locator('#password').dispatchEvent('pointerdown', { bubbles: true });
  expect(await mode(page), 'işaretçi kipi kapatır').toBe('');
  await expect(page.locator('#password')).toBeFocused();

  await page.keyboard.press(back);
  expect(await mode(page), 'Shift+Tab kipi açar').toBe('keyboard');
  await expect(page.locator('#username')).toBeFocused();

  // Dokunma da kipi kapatır.
  await page.locator('#username').dispatchEvent('touchstart', { bubbles: true });
  expect(await mode(page)).toBe('');
});

const focusCases = [
  { name: 'giris', scheme: 'light' },
  { name: 'giris', scheme: 'dark' },
  { name: 'kayit', scheme: 'light' },
  { name: 'totp-kurulum', scheme: 'light' },
  { name: 'totp-giris', scheme: 'dark' },
  { name: 'passkey-kayit', scheme: 'light' },
  { name: 'giris-yolu', scheme: 'light' },
  { name: 'eposta-dogrulama', scheme: 'dark' },
] as const;

// Her ekranda en az bu kadar kontrol ölçülmelidir. Döngü erken durursa test başarısız olur.
const minimumChecked: Record<string, number> = {
  giris: 8,
  kayit: 9,
  'totp-kurulum': 6,
  'totp-giris': 3,
  'passkey-kayit': 4,
  'giris-yolu': 4,
  'eposta-dogrulama': 3,
};

for (const { name, scheme } of focusCases) {
  test(`${name} (${scheme}): odak göstergesi görünür ve öğeyi çevrelemez`, async ({ page, browserName }) => {
    const { tab } = keys(browserName);
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await screen(name).open(page);
    if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
    await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
    const checked: string[] = [];
    const first = await activeName(page);
    for (let step = 0; step < 14; step += 1) {
      await page.keyboard.press(tab);
      const current = await activeName(page);
      if (current === 'body' || checked.includes(current)) break;
      checked.push(current);
      const focused = page.locator(':focus');
      await focused.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      // Onay kutusunun göstergesi etiket metnindedir. Ölçüm etiketin tamamında yapılır.
      const isCheck = await focused.evaluate((element) => element.matches('input[type=checkbox], input[type=radio]'));
      const target = isCheck ? focused.locator('xpath=ancestor::label[1]') : focused;

      // Çevreleyen çizgi kaynakları: outline ve odakta değişen kenarlık ya da gölge halkası.
      const style = await focused.evaluate((element) => {
        const computed = getComputedStyle(element);
        return { outlineStyle: computed.outlineStyle, outlineWidth: computed.outlineWidth };
      });
      expect(style.outlineStyle === 'none' || style.outlineWidth === '0px', `${current}: outline yok`).toBe(true);

      const { diff, rect } = await focusDiff(page, target);
      expect(diff.count, `${current}: görünür odak göstergesi`).toBeGreaterThanOrEqual(24);
      expect(diff.contrast, `${current}: gösterge kontrastı`).toBeGreaterThanOrEqual(3);
      // Gösterge yalnız öğenin alt yarısında ya da altındadır. Üstünü ve yanlarını sarmaz.
      // Onay kutusunun etiketi birkaç satır olabilir. Her satırın altı çizilir, etiketin üstü boş kalır.
      const upperLimit = isCheck ? rect.top + 8 : rect.top + rect.height / 2;
      expect(diff.minY, `${current}: üst kenarda çizgi yok`).toBeGreaterThanOrEqual(upperLimit);
      expect(diff.minX, `${current}: sol kenarda çizgi yok`).toBeGreaterThanOrEqual(Math.floor(rect.left));
      expect(diff.maxX, `${current}: sağ kenarda çizgi yok`).toBeLessThanOrEqual(Math.ceil(rect.left + rect.width));
      if (!isCheck) expect(diff.maxY - diff.minY, `${current}: gösterge düz bir çizgidir`).toBeLessThanOrEqual(6);
    }
    expect(checked.length, `${first} sonrası ölçülen öğe sayısı: ${checked.join(', ')}`).toBeGreaterThanOrEqual(minimumChecked[name]);
  });
}

test('işaretçiyle odakta hiçbir gösterge çizilmez', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openLogin(page);
  await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
  const username = page.locator('#username');
  const password = page.locator('#password');
  await password.click();
  const box = (await username.boundingBox())!;
  const clip = { x: Math.max(0, box.x - PAD), y: box.y - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2 };
  clip.width = Math.min(clip.width, page.viewportSize()!.width - clip.x);
  await page.mouse.move(0, 0);
  const blurred = await page.screenshot({ clip, scale: 'css' });
  await username.click();
  await page.mouse.move(0, 0);
  const focused = await page.screenshot({ clip, scale: 'css' });
  const diff = await diffBox(page, blurred, focused);
  expect(diff.count, 'işaretçi odağında görsel fark').toBe(0);
});

test('zorlanmış renklerde halka yalnız klavye kipinde görünür', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'forced-colors öykünmesi yalnız Chromium ailesinde var');
  await page.emulateMedia({ forcedColors: 'active' });
  await openLogin(page);
  const password = page.locator('#password');
  await password.click();
  expect(await password.evaluate((element) => getComputedStyle(element).outlineStyle)).toBe('none');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  const outline = await password.evaluate((element) => {
    const style = getComputedStyle(element);
    return `${style.outlineWidth} ${style.outlineStyle}`;
  });
  expect(outline).toBe('2px solid');
});

test('Enter tuşu formu gönderir', async ({ page }) => {
  await openLogin(page);
  await page.locator('#username').fill('yok@ornek.test');
  await page.locator('#password').fill('yanlis-parola');
  await page.keyboard.press('Enter');
  await expect(page.locator('#input-error-username')).toBeVisible();
});

test('giriş yolu seçeneği Enter ve Space tuşuyla çalışır', async ({ page, browserName }) => {
  const { tab } = keys(browserName);
  for (const key of ['Enter', 'Space']) {
    await screen('giris-yolu').open(page);
    const names = await page.locator('.at-choice__title').allInnerTexts();
    expect(names.length).toBeGreaterThanOrEqual(2);
    await page.locator('#at-choice-0').focus();
    await page.keyboard.press(tab);
    await expect(page.locator('#at-choice-1')).toBeFocused();
    await page.keyboard.press(key);
    await expect(page.locator('.at-choice')).toHaveCount(0);
    await expect(page.locator('#kc-otp-login-form, #authenticateWebAuthnButton').first()).toBeVisible();
    await page.context().clearCookies();
  }
});
