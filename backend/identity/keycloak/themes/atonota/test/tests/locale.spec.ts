import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
import { BRAND, openLogin } from './helpers';

const read = (locale: string) => {
  const path = fileURLToPath(new URL(`../../login/messages/messages_${locale}.properties`, import.meta.url));
  const entries = new Map<string, string>();
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    if (!line.trim() || line.startsWith('#') || !line.includes('=')) continue;
    entries.set(line.slice(0, line.indexOf('=')).trim(), line.slice(line.indexOf('=') + 1));
  }
  return entries;
};

test('Türkçe ve İngilizce ileti dosyaları aynı anahtarları taşır', () => {
  const tr = read('tr');
  const en = read('en');
  expect([...tr.keys()].filter((key) => !en.has(key)), 'İngilizcede eksik').toEqual([]);
  expect([...en.keys()].filter((key) => !tr.has(key)), 'Türkçede eksik').toEqual([]);
  expect([...tr].filter(([, value]) => !value.trim()).map(([key]) => key), 'boş Türkçe ileti').toEqual([]);
});

test('giriş seçeneği e-posta bağlantısını açıkça adlandırır', () => {
  expect(read('tr').get('magiclink-display-name')).toBe('E-posta bağlantısı');
});

test('Türkçe ve İngilizce iletiler aynı yer tutucuları taşır', () => {
  const tr = read('tr');
  const en = read('en');
  const holders = (value: string) => [...value.matchAll(/\{(\d+)\}/g)].map((match) => match[1]).sort().join(',');
  const different = [...tr].filter(([key, value]) => holders(value) !== holders(en.get(key) ?? '')).map(([key]) => key);
  expect(different).toEqual([]);
});

test('ileti dosyalarında marka adı sabit yazılmaz', () => {
  for (const locale of ['tr', 'en']) {
    const hits = [...read(locale)].filter(([, value]) => /atonota/i.test(value)).map(([key]) => key);
    expect(hits, `${locale}: marka adı ayardan gelir`).toEqual([]);
  }
});

test('varsayılan dil Türkçedir ve dil bağlantısı İngilizceye geçirir', async ({ page }) => {
  await openLogin(page);
  await expect(page.locator('html')).toHaveAttribute('lang', 'tr');
  await expect(page.locator('#kc-page-title')).toHaveText('Oturum açın');
  await expect(page.locator('#kc-login')).toHaveText('Oturum açın');
  await expect(page.locator('#kc-header-wrapper')).toContainText(BRAND);
  await expect(page.locator('#at-locale-tr')).toHaveAttribute('aria-current', 'true');

  await page.locator('#at-locale-en').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.locator('#kc-login')).toHaveText('Sign in');
  await expect(page.locator('#at-locale-en')).toHaveAttribute('aria-current', 'true');

  await page.locator('#at-locale-tr').click();
  await expect(page.locator('#kc-login')).toHaveText('Oturum açın');
});
