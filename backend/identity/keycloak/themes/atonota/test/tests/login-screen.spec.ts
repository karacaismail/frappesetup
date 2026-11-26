import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import { BRAND, createUser, openLogin, submitPassword } from './helpers';

// Giriş ekranı onaylı taslağa uyar (AJA-1125). Taslak: AJA-880, 3. sürüm, "main-giris" bölümü.

const themeRoot = fileURLToPath(new URL('../../', import.meta.url));
const loginCss = readFileSync(`${themeRoot}login/resources/css/atonota.css`, 'utf8');

const GENERIC = 'E-posta ya da parola yanlış.';
const EMPTY_EMAIL = 'E-posta alanı boş. E-posta adresinizi yazın.';
const EMPTY_PASSWORD = 'Parola alanı boş. Parolanızı yazın.';

/** Fills the two fields with the given text. An empty string leaves the field empty. The values are never printed. */
async function fillFields(page: Page, email: string, password: string) {
  await page.waitForLoadState('load');
  await page.locator('#username').fill(email);
  await page.locator('#password').fill(password);
}

test('@matrix sign-in: the screen has one main region and every visible text is inside it', async ({ page }) => {
  await openLogin(page);
  await expect(page.locator('main')).toHaveCount(1);
  await expect(page.getByRole('main')).toHaveCount(1);
  const outside = await page.evaluate(() => {
    const found: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const element = node.parentElement;
      if (!element || !node.textContent?.trim()) continue;
      if (element.closest('script, style, noscript, main')) continue;
      if (!element.checkVisibility()) continue;
      found.push(node.textContent.trim().slice(0, 40));
    }
    return found;
  });
  expect(outside, 'visible text outside main').toEqual([]);
});

test('sign-in: brand mark and brand name sit at the top of the card', async ({ page }) => {
  await openLogin(page);
  const main = page.getByRole('main');
  const brand = main.locator('.at-brand');
  await expect(brand).toHaveCount(1);
  await expect(brand.locator('.at-brand__name')).toHaveText(BRAND);
  // The mark shows the first letter of the brand name. The letter comes from the variable, never from the theme.
  const mark = brand.locator('.at-brand__mark');
  await expect(mark).toHaveAttribute('aria-hidden', 'true');
  await expect(mark).toHaveText(BRAND.slice(0, 1).toUpperCase());
  const order = await page.evaluate(() => {
    const brandBox = document.querySelector('.at-brand')!;
    const title = document.querySelector('#kc-page-title')!;
    return Boolean(brandBox.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(order, 'brand comes before the page title').toBe(true);
});

test('sign-in: the forgot-password link comes after the sign-in button, as in the draft', async ({ page }) => {
  await openLogin(page);
  const link = page.getByRole('link', { name: 'Parolamı unuttum' });
  await expect(link).toHaveCount(1);
  const after = await page.evaluate(() => {
    const button = document.querySelector('#kc-login')!;
    const forgot = document.querySelector('#at-forgot-password')!;
    return Boolean(button.compareDocumentPosition(forgot) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(after).toBe(true);
});

test('sign-in: light theme uses the draft colours and #00aacc is never a text colour', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await openLogin(page);
  const button = page.locator('#kc-login');
  await expect(button).toHaveCSS('background-color', 'rgb(0, 170, 204)');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(244, 245, 247)');
  await expect(page.getByRole('main')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  const cyanText = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('body *')]
      .filter((element) => element.checkVisibility() && [...element.childNodes].some((n) => n.nodeType === 3 && n.textContent?.trim()))
      .filter((element) => getComputedStyle(element).color === 'rgb(0, 170, 204)')
      .map((element) => `${element.tagName}#${element.id}.${element.className}`),
  );
  expect(cyanText).toEqual([]);
});

test('sign-in: card width and title size come from the tokens', async ({ page }) => {
  await openLogin(page);
  await expect(page.locator('#kc-page-title')).toHaveCSS('font-size', '26px');
  const width = await page.getByRole('main').evaluate((element) => element.getBoundingClientRect().width);
  expect(width).toBeLessThanOrEqual(420.5);
});

test.describe('touch profile', () => {
  test.use({ hasTouch: true, isMobile: false });
  test('the forgot-password link is at least 48px high with a coarse pointer', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'any-pointer emulation is only reliable in Chromium');
    await openLogin(page);
    expect(await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches)).toBe(true);
    const box = await page.getByRole('link', { name: 'Parolamı unuttum' }).boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(48);
  });
});

test.describe('empty fields', () => {
  test('only the email is empty: the screen says so under the email field', async ({ page }) => {
    await openLogin(page);
    await fillFields(page, '', 'bir-parola-degil');
    await page.locator('#kc-login').click();
    const email = page.locator('#username');
    await expect(page.locator('#input-error-username')).toHaveText(EMPTY_EMAIL);
    await expect(email).toHaveAttribute('aria-invalid', 'true');
    await expect(email).toHaveAccessibleDescription(EMPTY_EMAIL);
    await expect(email).toBeFocused();
    await expect(page.locator('#input-error-password')).toHaveCount(0);
    await expect(page.getByText(GENERIC)).toHaveCount(0);
  });

  test('only the password is empty: the screen says so under the password field', async ({ page }) => {
    await openLogin(page);
    await fillFields(page, 'biri@ornek.test', '');
    await page.locator('#kc-login').click();
    const password = page.locator('#password');
    await expect(page.locator('#input-error-password')).toHaveText(EMPTY_PASSWORD);
    await expect(password).toHaveAttribute('aria-invalid', 'true');
    await expect(password).toHaveAccessibleDescription(EMPTY_PASSWORD);
    await expect(password).toBeFocused();
    await expect(page.locator('#input-error-username')).toHaveCount(0);
    await expect(page.getByText(GENERIC)).toHaveCount(0);
  });

  test('both are empty: two errors appear, each under its own field', async ({ page }) => {
    await openLogin(page);
    await fillFields(page, '', '');
    await page.locator('#kc-login').click();
    await expect(page.locator('#input-error-username')).toHaveText(EMPTY_EMAIL);
    await expect(page.locator('#input-error-password')).toHaveText(EMPTY_PASSWORD);
    await expect(page.locator('#username')).toBeFocused();
    await expect(page.getByText(GENERIC)).toHaveCount(0);
    // Each error sits below its own field.
    const below = await page.evaluate(() =>
      (['username', 'password'] as const).every((name) => {
        const field = document.getElementById(name)!.getBoundingClientRect();
        const error = document.getElementById(`input-error-${name}`)!.getBoundingClientRect();
        return error.top >= field.bottom - 0.5;
      }),
    );
    expect(below).toBe(true);
  });

  test('the error goes away when the field is filled and the form is sent again', async ({ page }) => {
    const email = await createUser();
    await openLogin(page);
    await fillFields(page, '', '');
    await page.locator('#kc-login').click();
    await expect(page.locator('#input-error-username')).toBeVisible();
    await submitPassword(page, email);
    await expect(page).toHaveURL(/\/account/);
  });

  test.describe('without JavaScript', () => {
    test.use({ javaScriptEnabled: false });
    test('an empty email is named by the server, not reported as a wrong password', async ({ page }) => {
      await openLogin(page);
      await page.locator('#kc-login').click();
      await expect(page.locator('#input-error-username')).toHaveText(EMPTY_EMAIL);
      await expect(page.getByText(GENERIC)).toHaveCount(0);
    });
  });

  test('a filled but wrong sign-in keeps the general message', async ({ page }) => {
    await openLogin(page);
    await submitPassword(page, 'yok@ornek.test', 'yanlis-parola');
    await expect(page.locator('#input-error-username')).toHaveText(GENERIC);
  });
});

test('the shared design tokens carry the values of atonota-web commit d21799c', () => {
  const block = loginCss.slice(loginCss.indexOf('/* tokens:start */'), loginCss.indexOf('/* tokens:end */'));
  const light = block.slice(0, block.indexOf(':root.pf-v5-theme-dark'));
  const dark = block.slice(block.indexOf(':root.pf-v5-theme-dark'));
  const value = (part: string, name: string) => new RegExp(`${name}:\\s*([^;]+);`).exec(part)?.[1].trim().toLowerCase();
  const expected: Record<string, string> = {
    '--at-color-primary': '#00aacc',
    '--at-color-bg-layout': '#f4f5f7',
    '--at-color-bg-panel': '#ffffff',
    '--at-color-text': '#1b1f24',
    '--at-color-text-quiet': '#4b5563',
    '--at-color-link': '#006f86',
    '--at-focus-indicator-color': '#006f86',
    '--at-color-error': '#ab3335',
    '--at-radius': '5px',
    '--at-hit-target': '44px',
    '--at-focus-indicator-size': '2px',
    '--at-form-max-width': '420px',
    '--at-motion-easing-standard': 'cubic-bezier(.65, 0, .35, 1)',
  };
  for (const [name, want] of Object.entries(expected)) expect(value(light, name), name).toBe(want);
  const expectedDark: Record<string, string> = {
    '--at-color-bg-layout': '#17171a',
    '--at-color-bg-panel': '#1f1f23',
    '--at-color-text': '#ececf0',
    '--at-color-link': '#16b1d0',
    '--at-primary-bg': '#142c33',
    '--at-color-error': '#e88182',
  };
  for (const [name, want] of Object.entries(expectedDark)) expect(value(dark, name), `dark ${name}`).toBe(want);
  // No rule outside the token block writes a fixed colour.
  const rules = loginCss.slice(loginCss.indexOf('/* tokens:end */')).replace(/\/\*[\s\S]*?\*\//g, '');
  expect(rules.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g) ?? [], 'fixed colour in a rule').toEqual([]);
});

// The approved draft says "Giriş yapın". The theme uses this phrase on every screen (orchestrator answer, AJA-1125).
// Sign-out texts such as "Oturumu kapatın" and "oturum açık kalır" stay as they are.
const SIGN_IN_OLD = /oturum a[çc](?!ık)/i;

test('the Turkish texts of the login theme say "giriş yap", never "oturum aç"', () => {
  const files = [`${themeRoot}login/messages/messages_tr.properties`, ...['login.ftl', 'template.ftl'].map((f) => `${themeRoot}login/${f}`)];
  const hits: string[] = [];
  for (const file of files) {
    readFileSync(file, 'utf8')
      .split('\n')
      .forEach((line, index) => {
        if (!line.trim().startsWith('#') && SIGN_IN_OLD.test(line)) hits.push(`${file.replace(themeRoot, '')}:${index + 1}: ${line.trim()}`);
      });
  }
  expect(hits).toEqual([]);
});

test('sign-in: the title is "Giriş yapın" and the button is "Giriş yap"', async ({ page }) => {
  await openLogin(page, 'tr');
  await expect(page.locator('#kc-page-title')).toHaveText('Giriş yapın');
  await expect(page.locator('#kc-login')).toHaveText('Giriş yap');
  await expect(page.locator('body')).not.toContainText(SIGN_IN_OLD);
});
