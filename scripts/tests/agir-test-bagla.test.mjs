// Ağır testlerin kilit betiğine bağlandığını denetler (AJA-1813).
// Çalıştırma: node --test scripts/tests/agir-test-bagla.test.mjs
// Testler Playwright'ı yalnız --list ile açar. Tarayıcı ve sunucu açılmaz.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const KOK = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PLAYWRIGHT = join(KOK, 'node_modules', '.bin', 'playwright');
const AYARLAR = {
  kok: [],
  backend: ['-c', 'backend/e2e/playwright.config.ts'],
};
// Her ayarın hata mesajında yazması gereken doğru komut.
const DOGRU_KOMUT = {
  kok: /npm run test:e2e/,
  backend: /scripts\/agir-test npx playwright test -c backend\/e2e\/playwright\.config\.ts/,
};

// Kilit ve CI değişkenleri olmadan temiz bir ortam kurar.
function ortam(ek = {}) {
  const env = { ...process.env };
  for (const ad of ['GITHUB_ACTIONS', 'AGIR_TEST_YER', 'CI']) delete env[ad];
  return { ...env, ...ek };
}

function listele(ayar, ek) {
  return spawnSync(PLAYWRIGHT, ['test', ...AYARLAR[ayar], '--list'], {
    cwd: KOK, env: ortam(ek), encoding: 'utf8', timeout: 120_000,
  });
}

// Kök ayarın işçi sayısını okur. Ayar TypeScript olduğu için Node türleri atar.
function isciSayisi(ek) {
  const kod = "const c = (await import('./playwright.config.ts')).default;"
    + ' console.log(JSON.stringify(c.workers ?? null));';
  const sonuc = spawnSync(process.execPath, ['--input-type=module', '-e', kod], {
    cwd: KOK, env: ortam(ek), encoding: 'utf8', timeout: 60_000,
  });
  assert.equal(sonuc.status, 0, sonuc.stderr);
  return JSON.parse(sonuc.stdout.trim().split('\n').at(-1));
}

test('test:e2e komutu kilit betiğinden geçer', () => {
  const paket = JSON.parse(readFileSync(join(KOK, 'package.json'), 'utf8'));
  assert.equal(paket.scripts['test:e2e'], 'scripts/agir-test playwright test');
});

for (const ayar of Object.keys(AYARLAR)) {
  test(`${ayar} ayarı: doğrudan koşu yerelde hata verir`, () => {
    const sonuc = listele(ayar);
    assert.notEqual(sonuc.status, 0, 'kilitsiz koşu hata vermeli');
    assert.match(sonuc.stdout + sonuc.stderr, DOGRU_KOMUT[ayar]);
  });

  test(`${ayar} ayarı: GITHUB_ACTIONS=true iken hata vermez`, () => {
    const sonuc = listele(ayar, { GITHUB_ACTIONS: 'true' });
    assert.equal(sonuc.status, 0, sonuc.stdout + sonuc.stderr);
  });

  test(`${ayar} ayarı: kilidin içinde hata vermez`, () => {
    const sonuc = listele(ayar, { AGIR_TEST_YER: 'yer-1' });
    assert.equal(sonuc.status, 0, sonuc.stdout + sonuc.stderr);
  });

  test(`${ayar} ayarı: CI=1 tek başına kilidi atlatmaz`, () => {
    const sonuc = listele(ayar, { CI: '1' });
    assert.notEqual(sonuc.status, 0, 'CI=1 yerelde kilidi atlatmamalı');
  });
}

test('kök ayar yerelde en çok 4 işçi açar', () => {
  assert.equal(isciSayisi({ AGIR_TEST_YER: 'yer-1' }), 4);
});

test('kök ayarın CI işçi değeri değişmez', () => {
  assert.equal(isciSayisi({ GITHUB_ACTIONS: 'true', CI: 'true' }), null);
});
