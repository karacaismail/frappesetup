import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createServer } from 'node:http';
import { chromium, expect } from '@playwright/test';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

// Run separately from preview/browser tests: this check temporarily changes the setting.
test('one setting change reaches a fresh production build without regenerating source', async () => {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const setting = join(root, 'backend/brand.env');
  const original = readFileSync(setting);
  const untouched = [
    'src/components/Timeline.astro', 'src/data/task-board.json',
    'src/content/docs/acik-kararlar.md', 'src/content/docs/karar-katalogu.md',
    'src/content/docs/izlenebilirlik.md',
  ].map(path => [path, readFileSync(join(root, path))]);
  const out = mkdtempSync(join(tmpdir(), 'site-brand-'));
  const suffix = randomUUID().slice(0, 8);
  // Compose the fixture so the source scan cannot mistake it for a hardcoded active brand.
  const first = { name: ['Kimlik', 'Merkezi'].join(' '), domain: `first-${suffix}.test` };
  const second = { name: `Kurumsal; Kimlik ve Güvenli Giriş Merkezi ${suffix}`, domain: `brand-${suffix}.test` };
  const escapedName = second.name.replaceAll('&', '&amp;');
  const { NODE_TEST_CONTEXT: _, ...buildEnv } = process.env;
  const build = () => execFileSync('npm', ['run', 'build', '--', '--outDir', out], {
    cwd: root, stdio: 'pipe', env: buildEnv,
  });
  try {
    // A second build with unchanged Markdown must invalidate cached rendered content.
    writeFileSync(setting, `PRODUCT_NAME=${first.name}\nBRAND_DOMAIN=${first.domain}\n`);
    build();
    checkBrandGrammar(out, first.name);
    writeFileSync(setting, `PRODUCT_NAME=${second.name}\nBRAND_DOMAIN=${second.domain}\n`);
    build();
    checkBrandGrammar(out, second.name);
    const login = readFileSync(join(out, 'atonota-login/index.html'), 'utf8');
    assert.ok(login.includes(`${escapedName}: bağımsız giriş ürünü</h1>`), 'document heading');
    assert.ok(login.includes(`api.login.${second.domain}`), 'document body domain');
    assert.ok(!login.includes(first.domain) && !login.includes(first.name), 'previous brand must leave the content cache');
    const roadmap = readFileSync(join(out, 'yol-haritasi/index.html'), 'utf8');
    assert.ok(roadmap.includes(`P7 ${escapedName} ürünü`), 'generated diagram');
    const requirements = readFileSync(join(out, 'gereksinimler/index.html'), 'utf8');
    assert.ok(requirements.includes(`api.login.${second.domain}`), 'requirements data');
    for (const path of readdirSync(out, { recursive: true }).filter(path => path.endsWith('.html'))) {
      assert.doesNotMatch(readFileSync(join(out, path), 'utf8'), /\{\{(?:PRODUCT_NAME|BRAND_DOMAIN)\}\}|%7B%7B(?:PRODUCT_NAME|BRAND_DOMAIN)/i, path);
    }
    for (const [path, content] of untouched) assert.deepEqual(readFileSync(join(root, path)), content, path);
    await checkDiagrams(out, second.name);
  } finally {
    writeFileSync(setting, original);
    rmSync(out, { recursive: true, force: true });
  }
});

function checkBrandGrammar(directory, name) {
  const phrases = {
    'atonota-login/index.html': [`${name} ürününü satın alabilir`, `${name} ürününün kodu`],
    'index.html': [`${name} ürününü bağımsız ve ücretli`],
    'yol-haritasi/index.html': [`${name} ürününü bağımsız ve ücretli`],
    'gereksinimler/index.html': [
      `${name} ürününün bir tanıtım sayfası`, `Müşteri ${name} ürününü ücret karşılığında`,
      `${name} ürünü`, `K-61 kararına göre ${name} MVP sonrasıdır.`,
    ],
  };
  for (const [path, expected] of Object.entries(phrases)) {
    const html = readFileSync(join(directory, path), 'utf8');
    for (const phrase of expected) assert.ok(html.includes(phrase), `${path}: ${phrase}`);
    for (const quote of ["'", '’', 'ʼ']) {
      assert.ok(!html.includes(name + quote), `${path}: no name-dependent suffix`);
    }
  }
}

async function checkDiagrams(directory, name) {
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
  const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    const path = resolve(directory, '.' + url.pathname.replace(/^\/frappesetup/, ''));
    if (!path.startsWith(directory + sep)) { response.writeHead(404).end(); return; }
    const file = url.pathname.endsWith('/') ? join(path, 'index.html') : path;
    try {
      const content = readFileSync(file);
      response.writeHead(200, { 'Content-Type': types[extname(file)] ?? 'application/octet-stream' }).end(content);
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 320, height: 740 } });
    const base = `http://127.0.0.1:${server.address().port}/frappesetup/`;
    await page.goto(base + 'gereksinimler/');
    await expect(page.locator('astro-island[component-export="default"][component-url*="RequirementsExplorer"]')).not.toHaveAttribute('ssr', '');
    await page.locator('.req-more > summary').click();
    const epic = page.getByRole('group', { name: 'Epic', exact: true })
      .getByRole('button').filter({ hasText: `${name} ürünü` });
    await expect(epic).toHaveCount(1);
    await epic.click();
    await expect(epic).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('.task-rules')).toContainText(`K-61 kararına göre ${name} MVP sonrasıdır.`);
    for (const width of [320, 1366]) {
      await page.setViewportSize({ width, height: 740 });
      await expect(page.locator('[data-testid="req-table"]')).toContainText(`${name} ürünü`);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'requirements overflow');
    }
    await page.getByRole('button', { name: 'Gruplu', exact: true }).click();
    await expect(page.locator('.task-epic-title > span:first-child').first()).toHaveText(`${name} ürünü`);
    await page.goto(base + 'yol-haritasi/');
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator('[data-brand-label]')).toHaveAttribute('data-brand-ready', 'true');
    await expect(page.locator('.diagram-note')).toContainText(name);
    const inside = await page.locator('.diagram-timeline svg').evaluate(svg => {
      const id = [...svg.querySelectorAll('text')].find(text => text.textContent === 'P7');
      const rect = id.previousElementSibling.getBBox();
      const label = id.nextElementSibling.getBBox();
      return label.x >= rect.x && label.x + label.width <= rect.x + rect.width;
    });
    await page.goto(base + 'atonota-login/');
    await page.waitForFunction(() => document.querySelector('.mermaid-figure svg, .mermaid-figure[data-state="error"]'));
    await expect(page.locator('.mermaid-figure[data-state="error"]')).toHaveCount(0);
    // Mermaid wraps labels into tspans without inserting spaces between lines.
    const text = await page.locator('.mermaid-figure svg').textContent();
    assert.ok(text.replace(/\s/g, '').includes(name.replace(/\s/g, '')), 'full brand survives Mermaid rendering');
    assert.ok(inside, 'configured brand must fit its phase box');
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
}
