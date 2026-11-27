import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
import { BRAND, createUser, KC, MAILPIT, openLogin, REALM, screen, submitPassword } from './helpers';

// The brand name comes from one variable (IDENTITY_BRAND_NAME), never from the theme source.
// The test environment sets the variable to a name that differs from the theme name,
// so a hard-coded name anywhere in the theme makes these tests fail.

const themeRoot = fileURLToPath(new URL('../../', import.meta.url));

test('the test environment uses a brand name that differs from the theme name', () => {
  expect(BRAND, 'IDENTITY_BRAND_NAME is set in test/.env').not.toBe('');
  expect(BRAND.toLowerCase()).not.toContain('atonota');
});

test('login screens show the brand name from the variable', async ({ page }) => {
  for (const name of ['sign-in', 'register', 'password-reset']) {
    await screen(name).open(page);
    await expect(page.locator('#kc-header-wrapper .at-brand__name')).toHaveText(BRAND);
    await expect(page.locator('body')).not.toContainText(/atonota/i);
  }
});

// AJA-1062: on a 320 px phone the brand name and the sign-in button are both on screen.
test('@matrix sign-in shows the brand name and a visible sign-in button', async ({ page }) => {
  await screen('sign-in').open(page);
  await expect(page).toHaveTitle(new RegExp(BRAND));
  const name = page.locator('#kc-header-wrapper .at-brand__name');
  await expect(name).toHaveText(BRAND);
  await expect(name).toBeVisible();
  const button = page.locator('#kc-login');
  await button.scrollIntoViewIfNeeded();
  await expect(button).toBeVisible();
  await expect(button).toBeInViewport({ ratio: 1 });
  const width = page.viewportSize()?.width ?? 0;
  const box = await button.boundingBox();
  expect(box, 'the sign-in button has a box').not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(width);
});

test('@matrix account console shows the brand name from the variable', async ({ page }) => {
  const email = await createUser();
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible();

  await expect(page).toHaveTitle(BRAND);
  const brand = page.locator('.pf-v5-c-masthead__brand');
  // The name is drawn next to the mark. The console markup is not changed, so the text is a pseudo-element.
  const name = await brand.evaluate((element) => {
    const style = getComputedStyle(element, '::after');
    return { content: style.content, size: Number.parseFloat(style.fontSize), family: style.fontFamily, display: style.display };
  });
  expect(name.content).toBe(JSON.stringify(BRAND));
  expect(name.display).not.toBe('none');
  expect(name.size).toBeGreaterThanOrEqual(14);
  expect(name.family).toMatch(/^"?Outfit/);
  // The link has an accessible name that includes the brand.
  await expect(brand.locator('img')).toHaveAttribute('alt', /.+/);
  await expect(page.locator('body')).not.toContainText(/atonota/i);

  const edge = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
    brandRight: document.querySelector('.pf-v5-c-masthead__brand')!.getBoundingClientRect().right,
    mastheadHeight: document.querySelector('.pf-v5-c-masthead')!.getBoundingClientRect().height,
  }));
  expect(edge.scroll, 'horizontal overflow').toBeLessThanOrEqual(edge.client);
  expect(edge.brandRight, 'brand stays inside the viewport').toBeLessThanOrEqual(edge.client);
  // One row is 76px tall. A wrapped masthead is 128px.
  expect(edge.mastheadHeight, 'the masthead stays on one row').toBeLessThanOrEqual(80);
});

test('@matrix account console: a ten-letter brand name fits next to the mark without being cut', async ({ page }) => {
  const email = await createUser();
  await page.goto(`${KC}/realms/${REALM}/account/`);
  await submitPassword(page, email);
  await expect(page.locator('#save-btn')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  // The name is swapped for a ten-letter sample. The clip is lifted, so a name that does not fit overflows the link.
  await page.evaluate(() => document.documentElement.style.setProperty('--at-brand-name', '"Abcdefghij"'));
  await page.addStyleTag({ content: '.pf-v5-c-masthead__brand::after { overflow: visible !important; }' });
  const fit = await page.locator('.pf-v5-c-masthead__brand').evaluate((element) => ({
    needed: element.scrollWidth,
    available: element.clientWidth,
  }));
  expect(fit.needed, 'the name fits in the brand link').toBeLessThanOrEqual(fit.available);
  const height = await page.locator('.pf-v5-c-masthead').evaluate((element) => element.getBoundingClientRect().height);
  expect(height, 'the masthead stays on one row').toBeLessThanOrEqual(80);
});

test('emails show the brand name from the variable', async ({ page }) => {
  const email = await createUser();
  await screen('password-reset').open(page);
  await page.locator('#username').fill(email);
  await page.locator('#kc-reset-password-form [type=submit]').click();
  let id = '';
  await expect
    .poll(async () => {
      const found = (await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`)).json()) as { messages: { ID: string }[] };
      id = found.messages[0]?.ID ?? '';
      return id;
    })
    .not.toBe('');
  const mail = (await (await fetch(`${MAILPIT}/api/v1/message/${id}`)).json()) as { HTML: string; Text: string; From: { Name: string } };
  expect(mail.HTML).toContain(BRAND);
  expect(mail.Text).toContain(BRAND);
  expect(mail.From.Name).toBe(BRAND);
  expect(`${mail.HTML}${mail.Text}`).not.toMatch(/atonota/i);
});

test('theme source: no user-visible brand name outside comments', () => {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.(ftl|properties|css|js|svg)$/.test(entry)) files.push(path);
    }
  };
  for (const part of ['login', 'email', 'account']) walk(join(themeRoot, part));
  const hits: string[] = [];
  for (const file of files) {
    const text = readFileSync(file, 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '') // CSS and JS block comments
      .replace(/<#--[\s\S]*?-->/g, '') // FreeMarker comments
      .replace(/<!--[\s\S]*?-->/g, '') // HTML comments
      .split('\n')
      .filter((line) => !/^\s*(#|\/\/)/.test(line)) // .properties and JS line comments
      // File and folder names of the theme are identifiers, not text shown to the user.
      .map((line) => line.replace(/atonota(-account|-focus|-form)?\.(css|js)/g, '').replace(/themes\/atonota/g, ''))
      // A message key is an identifier too, for example atonotaEnterpriseSsoRequired. Only the value is shown.
      .map((line) => (file.endsWith('.properties') ? line.replace(/^[^=]*=/, '') : line));
    text.forEach((line, index) => {
      if (/atonota/i.test(line)) hits.push(`${file.replace(themeRoot, '')}:${index + 1}: ${line.trim().slice(0, 80)}`);
    });
  }
  expect(hits).toEqual([]);
});
