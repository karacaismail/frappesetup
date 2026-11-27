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
