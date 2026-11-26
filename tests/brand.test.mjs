import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { satteri } from '@astrojs/markdown-satteri';
import { parseBrand, fillBrand, fillBrandData } from '../src/lib/brand.mjs';
import { brandPlaceholders } from '../src/lib/satteri-brand.mjs';

const brand = { PRODUCT_NAME: 'Örnek & Güven <Giriş>', BRAND_DOMAIN: 'example.test' };
const setting = `# Public branding\nPRODUCT_NAME=${brand.PRODUCT_NAME}\nBRAND_DOMAIN=${brand.BRAND_DOMAIN}\n`;

test('reads the single UTF-8 setting, including spaces and CRLF', () => {
  assert.deepEqual(parseBrand(setting.replaceAll('\n', '\r\n')), brand);
  assert.deepEqual(Object.keys(parseBrand(readFileSync(new URL('../backend/brand.env', import.meta.url), 'utf8'))).sort(), ['BRAND_DOMAIN', 'PRODUCT_NAME']);
});

test('rejects malformed settings instead of falling back to a brand', () => {
  for (const invalid of [
    '', setting.replace('PRODUCT_NAME=', 'UNKNOWN='), setting + 'EXTRA=value\n',
    setting + 'PRODUCT_NAME=Other\n', setting.replace(brand.PRODUCT_NAME, ''),
    setting.replace(brand.PRODUCT_NAME, 'Bad\u0000name'), setting.replace('PRODUCT_NAME=', 'PRODUCT_NAME '),
    ...['https://example.test', 'example.test/path', 'example.test:443', '-example.test', 'example..test', 'localhost', '"example.test"'].map(domain => setting.replace(brand.BRAND_DOMAIN, domain)),
  ]) assert.throws(() => parseBrand(invalid));
});

test('fills exact placeholders once and preserves technical identifiers', () => {
  assert.equal(fillBrand('{{PRODUCT_NAME}}: https://api.login.{{BRAND_DOMAIN}} atonota_login {{UNKNOWN}}', brand),
    `${brand.PRODUCT_NAME}: https://api.login.example.test atonota_login {{UNKNOWN}}`);
  assert.equal(fillBrand('{{PRODUCT_NAME}}', { ...brand, PRODUCT_NAME: '{{BRAND_DOMAIN}}' }), '{{BRAND_DOMAIN}}');
});

test('fills nested JSON data without changing ids, types or the input', () => {
  const input = [{ id: 'G-12', title: '{{PRODUCT_NAME}}', detail: { host: '{{BRAND_DOMAIN}}', count: 2, active: true, empty: null } }];
  const result = fillBrandData(input, brand);
  assert.deepEqual(result, [{ id: 'G-12', title: brand.PRODUCT_NAME, detail: { host: brand.BRAND_DOMAIN, count: 2, active: true, empty: null } }]);
  assert.equal(input[0].title, '{{PRODUCT_NAME}}');
});

test('Sätteri fills text, headings, links, inline code and highlighted code safely', async () => {
  const renderer = await satteri({ hastPlugins: [brandPlaceholders(brand)] }).createRenderer({
    syntaxHighlight: { type: 'shiki', excludeLangs: ['mermaid'] },
  });
  const source = [
    '## {{PRODUCT_NAME}}', '',
    '[{{PRODUCT_NAME}}](https://api.login.{{BRAND_DOMAIN}} "{{PRODUCT_NAME}}")', '',
    '`{{PRODUCT_NAME}}`', '',
    '```json', '{ "name": "{{PRODUCT_NAME}}", "host": "{{BRAND_DOMAIN}}" }', '```', '',
    '```mermaid', 'flowchart LR', 'A["{{PRODUCT_NAME}}"]', '```',
  ].join('\n');
  const result = await renderer.render(source);
  assert.doesNotMatch(result.code, /\{\{(?:PRODUCT_NAME|BRAND_DOMAIN)\}\}|%7B%7B/i);
  assert.match(result.code, /https:\/\/api\.login\.example\.test/);
  assert.match(result.code, /Örnek &amp; Güven &lt;Giriş&gt;/);
  // Angle brackets are valid inside a quoted HTML attribute. Text stays escaped.
  assert.doesNotMatch(result.code.replace(/title="[^"]*"/g, ''), /<Giriş>/);
  assert.equal(result.metadata.headings[0].text, brand.PRODUCT_NAME);
});

test('fills placeholders split across Shiki tokens without removing highlighting', async () => {
  const renderer = await satteri({ hastPlugins: [brandPlaceholders(brand)] }).createRenderer({ syntaxHighlight: { type: 'shiki' } });
  for (const [language, code] of [['js', 'const host = {{BRAND_DOMAIN}};'], ['sh', 'HOST={{BRAND_DOMAIN}}']]) {
    const result = await renderer.render(`\`\`\`${language}\n${code}\n\`\`\``);
    assert.ok(result.code.includes('<span'), 'syntax highlighting remains');
    assert.equal(result.code.replace(/<[^>]*>/g, '').trim(), code.replace('{{BRAND_DOMAIN}}', brand.BRAND_DOMAIN));
  }
});
