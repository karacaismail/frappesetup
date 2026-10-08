// Görsel kanıt: belirli sayfaları açık/koyu şema ve farklı genişliklerde PNG olarak kaydeder.
// Kullanım: node scripts/screenshots.mjs <baseURL> <çıktıKlasörü>
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
const [base = 'http://127.0.0.1:4329/frappesetup/', out = 'playwright-report/shots'] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const shots = [
  { path: '', w: 1366, h: 900, scheme: 'light', name: 'home-light-1366', full: true },
  { path: '', w: 1366, h: 900, scheme: 'dark', name: 'home-dark-1366', full: false },
  { path: '', w: 320, h: 640, scheme: 'light', name: 'home-light-320', full: false },
  { path: 'raylar/', w: 1366, h: 900, scheme: 'light', name: 'raylar-light-1366', full: false, scrollTo: '.diagram-rails' },
  { path: 'yol-haritasi/', w: 1366, h: 900, scheme: 'dark', name: 'yol-dark-1366', full: false, scrollTo: '.diagram-timeline' },
  { path: 'gereksinimler/', w: 1366, h: 900, scheme: 'light', name: 'gereksinimler-light-1366', full: false },
  { path: 'gereksinimler/', w: 320, h: 640, scheme: 'dark', name: 'gereksinimler-dark-320', full: false, scrollTo: '.req-cards' },
  { path: 'rail-4-keycloak/', w: 320, h: 640, scheme: 'dark', name: 'keycloak-dark-320', full: false, scrollTo: 'figure.mermaid-figure' },
  { path: 'rail-1-press/', w: 1366, h: 900, scheme: 'light', name: 'press-light-1366', full: false, scrollTo: 'figure.mermaid-figure' },
  { path: 'kararlar/', w: 390, h: 844, scheme: 'light', name: 'kararlar-light-390', full: false, scrollTo: '.table-wrap' },
];
const browser = await chromium.launch();
for (const s of shots) {
  const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, colorScheme: s.scheme, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(base + s.path, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => !document.querySelector('pre > code.language-mermaid') && !document.querySelector('figure.mermaid-figure:not([data-state])'));
  if (s.scrollTo) {
    await page.locator(s.scrollTo).first().evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await page.evaluate(() => window.scrollBy(0, -72));
    await page.waitForTimeout(300);
  }
  await page.screenshot({ path: `${out}/${s.name}.png`, fullPage: s.full });
  console.log('saved', `${out}/${s.name}.png`);
  await ctx.close();
}
await browser.close();
