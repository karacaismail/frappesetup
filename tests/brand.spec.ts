import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';
import { parseBrand } from '../src/lib/brand.mjs';

const brand = parseBrand(readFileSync(new URL('../backend/brand.env', import.meta.url), 'utf8'));

test('brand setting reaches the document, navigation, code and phase diagram @touch', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto('atonota-login/');
  await expect(page.locator('h1')).toHaveText(`${brand.PRODUCT_NAME}: bağımsız giriş ürünü`);
  await expect(page.locator('#site-nav a[href$="/atonota-login/"]')).toHaveText(brand.PRODUCT_NAME);
  await expect(page).toHaveTitle(new RegExp(brand.PRODUCT_NAME.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  await expect(page.locator('.prose')).toContainText(`api.login.${brand.BRAND_DOMAIN}`);
  expect(await page.locator('body').innerText()).not.toMatch(/\{\{(?:PRODUCT_NAME|BRAND_DOMAIN)\}\}/);
  await test.info().attach('brand-320', { body: await page.screenshot(), contentType: 'image/png' });
  await page.goto('yol-haritasi/');
  await expect(page.locator('.diagram-timeline')).toContainText(brand.PRODUCT_NAME);
  await expect(page.locator('.phase-table')).toContainText(brand.PRODUCT_NAME);
  expect(await page.locator('body').innerText()).not.toMatch(/\{\{(?:PRODUCT_NAME|BRAND_DOMAIN)\}\}/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  expect(overflow).toBe(false);
  await page.setViewportSize({ width: 1366, height: 900 });
  await expect(page.locator('[data-brand-label]')).toHaveAttribute('data-brand-ready', 'true');
  await page.locator('.diagram-timeline').scrollIntoViewIfNeeded();
  await test.info().attach('brand-desktop', { body: await page.screenshot(), contentType: 'image/png' });
});
