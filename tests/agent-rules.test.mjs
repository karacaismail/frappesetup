import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// Ortak bitti kuralı (AJA-1807, mimari karar AJA-1804): AGENTS.md ve CLAUDE.md "Teslim ve Git" bölümünde aynı metin.
const read = (name) => readFileSync(new URL(`../${name}`, import.meta.url), 'utf8');
const section = (text) => {
  const start = text.indexOf('\n## Teslim ve Git\n');
  assert.notEqual(start, -1, '"Teslim ve Git" bölümü yok');
  const next = text.indexOf('\n## ', start + 1);
  return text.slice(start, next === -1 ? undefined : next);
};
const files = ['AGENTS.md', 'CLAUDE.md'];

test('both files carry the same Teslim ve Git section', () => {
  assert.equal(section(read('AGENTS.md')), section(read('CLAUDE.md')));
});

for (const name of files) {
  test(`${name}: shared done rule with the architect's corrections`, () => {
    const s = section(read(name));
    for (const needle of [
      '### Ortak bitti tanımı: test ortamını kapatma ve paralel test sınırı',
      'astro dev stop',
      'fs-dev-ortam-',
      'fs-e2e-',
      'docker ps',
      'Ortamlarım kapalı:',
      'Veri birimlerini silmeyin.',
      'en çok 2 ajan',
      'yer-1',
      'yer-2',
      'Test sırası bekleniyor',
      'lockf -k -s -t 0',
      '~$(id -un)/.cache/frappesetup-test-kilidi',
      '`HOME`',
      'GITHUB_ACTIONS=true',
      'AGIR_TEST_YER',
      'işçi sayısı 4',
      '`npx playwright test`',
      '`npm run test:e2e`',
      'Kilit dosyasını elle silmeyin.',
    ]) assert.ok(s.includes(needle), `eksik: ${needle}`);
  });
}

// Yerel ve CI test ayrımı (AJA-2167, kaynak iş AJA-2153): kural ortak bitti tanımının içindedir.
const FAST_SCRIPT = 'test:e2e:hizli';
const subsection = (s) => {
  const start = s.indexOf("\n#### Yerelde hızlı test, tam matris GitHub CI'da\n");
  assert.notEqual(start, -1, '"Yerelde hızlı test" alt bölümü yok');
  const next = s.indexOf('\n#### ', start + 1);
  return s.slice(start, next === -1 ? undefined : next);
};

for (const name of files) {
  test(`${name}: local fast tests, full matrix in GitHub CI`, () => {
    const s = section(read(name));
    const done = s.indexOf('### Ortak bitti tanımı');
    const rule = subsection(s);
    assert.ok(done !== -1 && s.indexOf(rule) > done, 'kural ortak bitti tanımının içinde değil');
    for (const needle of [
      'Bu kural 28 Kasım 2026 Cumartesi günü eklendi. Kaynak iş AJA-2153 kaydıdır.',
      'Yerelde yalnız hızlı testleri koşun. Hızlı testler şunlardır:',
      '- birim testleri,',
      '- lint,',
      '- tip denetimi,',
      '- tek bir Playwright projesi ve yalnız 320 px genişlik.',
      'Tam tarayıcı matrisi GitHub CI\'da koşar. PR açılınca CI bu matrisi kendisi koşar.',
      'Yerelde tam matrisi yalnız gerekçe yazınca koşun. Gerekçeyi testten önce göreve yorum olarak yazın.',
      'Playwright testi ağır test kilidinden geçer. Aynı anda en çok 2 ajan Playwright koşar. Test bitince açtığınız ortamı kapatın.',
      `\`npm run ${FAST_SCRIPT}\``,
    ]) assert.ok(rule.includes(needle), `eksik: ${needle}`);
  });
}

test('fast Playwright script: one project, 320 px only, through the heavy-test lock', () => {
  const { scripts } = JSON.parse(read('package.json'));
  const cmd = scripts[FAST_SCRIPT];
  assert.ok(cmd, `package.json içinde ${FAST_SCRIPT} yok`);
  assert.match(cmd, /^scripts\/agir-test playwright test /, 'komut ağır test kilidinden geçmiyor');
  assert.equal((cmd.match(/--project[= ]/g) || []).length, 1, 'tek proje seçilmeli');
  assert.match(cmd, /--project[= ]chromium\b/);
  assert.match(cmd, /--grep[= ]\S*320/, 'yalnız 320 px testleri seçilmeli');
});
