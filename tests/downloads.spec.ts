import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import {
  existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, posix, relative } from 'node:path';
import { crc32, inflateRawSync } from 'node:zlib';
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { generatePressAiDownloads } from '../scripts/press-ai-downloads.mjs';

// press-ai indirmeleri: derlenmiş çıktıdaki dosyalar (dist/downloads/press-ai/) gerçek içerikle, sayfadaki bağlantılar
// gerçek tarayıcı indirmesiyle denetlenir. ZIP'ler üreticiden bağımsız iki okuyucuyla (aşağıdaki yerel ayrıştırıcı ve
// Python zipfile) açılır; tam paket ve MCP paketi açıldıkları dizinden çalıştırılır.
const ROOT = new URL('../', import.meta.url).pathname;
const DIST = join(ROOT, 'dist/downloads/press-ai');
const PKG = join(ROOT, 'packages/press-ai');
const sha256 = (b: Buffer) => createHash('sha256').update(b).digest('hex');

const SKILLS = ['frappe-app-extension', 'frappe-custom-app', 'press-build-triage', 'press-operations'];
const AGENTS = ['frappe-app-developer', 'frappe-change-reviewer', 'press-diagnoser', 'press-operator'];
const TOOLS = [
  'kit_status', 'contract_search', 'contract_get', 'ui_reference_search', 'press_read', 'press_triage_build',
  'press_propose', 'proposal_get', 'press_execute', 'press_track', 'app_inspect', 'app_check', 'app_propose_change',
  'app_apply',
];
const LICENSES = ['LICENSE', 'LICENSE-CONTENT'];

type Artifact = { path: string; save: string; zip: boolean };
const ARTIFACTS: Artifact[] = [
  { path: 'press-ai.zip', save: 'press-ai.zip', zip: true },
  { path: 'press-ai-mcp.zip', save: 'press-ai-mcp.zip', zip: true },
  ...SKILLS.map((s) => ({ path: `press-ai-skill-${s}.zip`, save: `press-ai-skill-${s}.zip`, zip: true })),
  ...SKILLS.map((s) => ({ path: `files/skills/${s}/SKILL.md`, save: 'SKILL.md', zip: false })),
  ...AGENTS.map((a) => ({ path: `files/agents/${a}.md`, save: `${a}.md`, zip: false })),
];
const SINGLE_SOURCE = (p: string) => join(PKG, p.replace(/^files\//, ''));

// Sayfa → beklenen indirme bağlantıları (tüm paket her blokta ayrı birincil düğmedir).
const PAGES: Record<string, string[]> = {
  'ai-mcp': ['press-ai-mcp.zip', 'press-ai.zip'],
  'ai-skills': [
    ...SKILLS.map((s) => `files/skills/${s}/SKILL.md`),
    ...SKILLS.map((s) => `press-ai-skill-${s}.zip`),
    'press-ai.zip',
  ],
  'ai-agents': [...AGENTS.map((a) => `files/agents/${a}.md`), 'press-ai.zip'],
  'ai-gelistirme': ['press-ai.zip'],
};

type Entry = { name: string; data: Buffer; method: number; time: number; date: number; mode: number };

/** Yerel ZIP okuyucu: EOCD → merkezi dizin → yerel başlık; CRC ve boyut doğrulanır (üretici kodu kullanılmaz). */
function readZip(buf: Buffer): Entry[] {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 22 - 65535); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error('EOCD yok');
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const out: Entry[] = [];
  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error(`merkezi başlık ${n} bozuk`);
    const method = buf.readUInt16LE(p + 10);
    const time = buf.readUInt16LE(p + 12);
    const date = buf.readUInt16LE(p + 14);
    const crc = buf.readUInt32LE(p + 16);
    const csize = buf.readUInt32LE(p + 20);
    const usize = buf.readUInt32LE(p + 24);
    const nlen = buf.readUInt16LE(p + 28);
    const xlen = buf.readUInt16LE(p + 30);
    const clen = buf.readUInt16LE(p + 32);
    const ext = buf.readUInt32LE(p + 38);
    const lho = buf.readUInt32LE(p + 42);
    const name = buf.subarray(p + 46, p + 46 + nlen).toString('utf8');
    if (buf.readUInt32LE(lho) !== 0x04034b50) throw new Error(`${name}: yerel başlık yok`);
    const start = lho + 30 + buf.readUInt16LE(lho + 26) + buf.readUInt16LE(lho + 28);
    const raw = buf.subarray(start, start + csize);
    const data = method === 8 ? inflateRawSync(raw) : Buffer.from(raw);
    if (data.length !== usize) throw new Error(`${name}: boyut ${data.length} ≠ ${usize}`);
    if (crc32(data) >>> 0 !== crc) throw new Error(`${name}: CRC uyuşmuyor`);
    out.push({ name, data, method, time, date, mode: ext >>> 16 });
    p += 46 + nlen + xlen + clen;
  }
  return out;
}

/** Kaynak paket ağacı (önbellek ve gizli dosyalar hariç): tam paket ZIP'iyle birebir aynı küme olmalı. */
function packageTree(): string[] {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (name === '__pycache__' || name === '.DS_Store' || name.endsWith('.pyc')) continue;
      if (lstatSync(full).isSymbolicLink()) throw new Error(`paket ağacında sembolik bağ: ${full}`);
      if (statSync(full).isDirectory()) walk(full);
      else files.push(relative(PKG, full).split('\\').join('/'));
    }
  };
  walk(PKG);
  return files.sort();
}

const FORBIDDEN = /(^|\/)(\.git|\.github|\.env[^/]*|__pycache__|node_modules|\.pytest_cache|\.DS_Store|sites|logs)(\/|$)|\.(pyc|pyo|key|pem|sqlite3?|db)$/;
const SECRET = /-----BEGIN [A-Z ]*PRIVATE KEY-----|\bghp_[A-Za-z0-9]{36}\b|\bAKIA[0-9A-Z]{16}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}/;

function python(args: string[], opts: { cwd?: string; input?: string } = {}) {
  const r = spawnSync('python3', ['-I', ...args], { cwd: opts.cwd, input: opts.input, encoding: 'utf8', timeout: 60_000 });
  return { code: r.status, out: r.stdout ?? '', err: r.stderr ?? '' };
}

/** Python zipfile ile aç (bağımsız standart uygulama; testzip CRC'leri yeniden doğrular). */
function extract(zipPath: string): string {
  const dir = mkdtempSync(join(tmpdir(), 'press-ai-dl-'));
  const r = python(
    ['-c', 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); bad=z.testzip(); assert bad is None, bad; z.extractall(sys.argv[2])', zipPath, dir],
  );
  expect(r.code, `zipfile: ${r.err}`).toBe(0);
  return dir;
}

function manifest(): { version: string; files: { path: string; save: string; bytes: number; sha256: string; entries?: number }[] } {
  return JSON.parse(readFileSync(join(DIST, 'manifest.json'), 'utf8'));
}

test.describe('press-ai downloads: artifacts', () => {
  test.beforeEach(({ browserName }) => {
    test.skip(browserName !== 'chromium', 'Dosya düzeyi denetim; tek motorda koşar.');
  });

  test('every artifact exists, matches the manifest and SHA256SUMS, and nothing else is published', () => {
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        if (statSync(full).isDirectory()) walk(full);
        else files.push(relative(DIST, full).split('\\').join('/'));
      }
    };
    expect(existsSync(DIST), `${DIST} derlemede üretilmeli`).toBe(true);
    walk(DIST);
    expect(files.sort()).toEqual([...ARTIFACTS.map((a) => a.path), 'SHA256SUMS.txt', 'manifest.json'].sort());

    const m = manifest();
    expect(m.files.map((f) => f.path).sort()).toEqual(ARTIFACTS.map((a) => a.path).sort());
    const sums = readFileSync(join(DIST, 'SHA256SUMS.txt'), 'utf8').trim().split('\n');
    expect(sums).toEqual(ARTIFACTS.map((a) => a.path).sort().map((p) => `${sha256(readFileSync(join(DIST, p)))}  ${p}`));
    for (const f of m.files) {
      const body = readFileSync(join(DIST, f.path));
      expect(f.bytes, f.path).toBe(body.length);
      expect(f.sha256, f.path).toBe(sha256(body));
      expect(f.save, f.path).toBe(ARTIFACTS.find((a) => a.path === f.path)!.save);
    }
  });

  test('the generator refuses symbolic links instead of following them', () => {
    const tmp = mkdtempSync(join(tmpdir(), 'press-ai-link-'));
    try {
      mkdirSync(join(tmp, 'packages/press-ai/references'), { recursive: true });
      writeFileSync(join(tmp, 'outside.txt'), 'outside bytes\n');
      symlinkSync(join(tmp, 'outside.txt'), join(tmp, 'packages/press-ai/references/leak.md'));
      expect(() => generatePressAiDownloads(tmp)).toThrow(/sembolik bağ/);
      expect(existsSync(join(tmp, 'public')), 'hata öncesi hiçbir şey yazılmaz').toBe(false);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test('single files are byte-identical to the package sources', () => {
    for (const a of ARTIFACTS.filter((x) => !x.zip)) {
      expect(sha256(readFileSync(join(DIST, a.path))), a.path).toBe(sha256(readFileSync(SINGLE_SOURCE(a.path))));
    }
  });

  test('zips are deterministic, whitelisted, licensed and byte-identical to sources', () => {
    const repoLicense = Object.fromEntries(LICENSES.map((l) => [l, readFileSync(join(ROOT, l))]));
    const tree = packageTree();
    for (const a of ARTIFACTS.filter((x) => x.zip)) {
      const entries = readZip(readFileSync(join(DIST, a.path)));
      const names = entries.map((e) => e.name);
      expect(names, `${a.path} sıralı`).toEqual([...names].sort());
      expect(new Set(names).size, `${a.path} tekil adlar`).toBe(names.length);
      for (const e of entries) {
        expect(FORBIDDEN.test(e.name), `${a.path}: yasaklı yol ${e.name}`).toBe(false);
        expect(SECRET.test(e.data.toString('utf8')), `${a.path}: gizli değer deseni ${e.name}`).toBe(false);
        expect([e.date, e.time], `${a.path}: sabit zaman ${e.name}`).toEqual([0x0021, 0]);
        expect(e.mode, `${a.path}: kip ${e.name}`).toBe(0o100644);
        expect(e.method, `${a.path}: deflate ${e.name}`).toBe(8);
        if (LICENSES.includes(e.name)) {
          expect(e.data.equals(repoLicense[e.name]), `${a.path}: ${e.name} depodakiyle aynı`).toBe(true);
          continue;
        }
        expect(e.name.startsWith('packages/press-ai/'), `${a.path}: kök ${e.name}`).toBe(true);
        const src = join(ROOT, e.name);
        expect(existsSync(src), `${a.path}: kaynağı olmayan girdi ${e.name}`).toBe(true);
        expect(e.data.equals(readFileSync(src)), `${a.path}: ${e.name} kaynakla aynı`).toBe(true);
      }
      for (const l of LICENSES) expect(names, `${a.path}: ${l}`).toContain(l);

      const inPkg = names.filter((n) => n.startsWith('packages/press-ai/')).map((n) => n.slice('packages/press-ai/'.length));
      if (a.path === 'press-ai.zip') {
        expect(inPkg, 'tam paket = kaynak paket ağacı').toEqual(tree);
      } else if (a.path === 'press-ai-mcp.zip') {
        const runtime = tree.filter(
          (f) =>
            f === 'server.py' ||
            f === 'INTERFACE.md' ||
            f === 'README.md' ||
            /^press_ai\/[^/]+\.py$/.test(f) ||
            f.startsWith('contracts/') ||
            /^config\/[^/]+\.example\.json$/.test(f),
        );
        expect(inPkg, 'MCP paketi: çalışma zamanı, kontrat, örnek yapılandırma').toEqual(runtime);
      } else {
        const skill = a.path.replace(/^press-ai-skill-|\.zip$/g, '');
        const expected = tree.filter((f) => f.startsWith(`skills/${skill}/`) || /^references\/[^/]+\.md$/.test(f));
        expect(inPkg, `${skill}: skill + paylaşılan başvurular`).toEqual(expected);
      }
    }
  });

  test('full package and MCP zip run from the directory they are extracted to', () => {
    for (const zip of ['press-ai.zip', 'press-ai-mcp.zip']) {
      const dir = extract(join(DIST, zip));
      try {
        const check = python(['packages/press-ai/server.py', 'check-contract'], { cwd: dir });
        expect(check.code, `${zip} check-contract: ${check.err}`).toBe(0);

        const state = mkdtempSync(join(tmpdir(), 'press-ai-state-'));
        const cfg = join(state, 'config.json');
        writeFileSync(cfg, JSON.stringify({ approval: { state_dir: join(state, 'state') } }));
        const input = [
          { jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'dl-test', version: '0' } } },
          { jsonrpc: '2.0', method: 'notifications/initialized' },
          { jsonrpc: '2.0', id: 2, method: 'tools/list' },
        ].map((m) => JSON.stringify(m)).join('\n') + '\n';
        const serve = python(['packages/press-ai/server.py', 'serve', '--config', cfg], { cwd: dir, input });
        rmSync(state, { recursive: true, force: true });
        const replies = serve.out.trim().split('\n').filter(Boolean).map((l) => JSON.parse(l));
        const list = replies.find((r) => r.id === 2);
        expect(list?.result?.tools?.map((t: { name: string }) => t.name).sort(), `${zip} tools/list: ${serve.err}`).toEqual([...TOOLS].sort());
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    }
  });

  test('extracted skill zips and the full package keep every relative markdown link and the plugin manifest', () => {
    for (const zip of ['press-ai.zip', ...SKILLS.map((s) => `press-ai-skill-${s}.zip`)]) {
      const dir = extract(join(DIST, zip));
      try {
        const pkg = join(dir, 'packages/press-ai');
        const mds: string[] = [];
        const walk = (d: string) => {
          for (const name of readdirSync(d)) {
            const full = join(d, name);
            if (statSync(full).isDirectory()) walk(full);
            else if (name.endsWith('.md')) mds.push(full);
          }
        };
        walk(pkg);
        expect(mds.length, zip).toBeGreaterThan(0);
        for (const md of mds) {
          const text = readFileSync(md, 'utf8');
          for (const [, target] of text.matchAll(/\]\(([^)#\s]+)(?:#[^)]*)?\)/g)) {
            if (/^[a-z]+:\/\//.test(target)) continue;
            const resolved = posix.normalize(posix.join(posix.dirname(md), target));
            expect(existsSync(resolved), `${zip}: ${relative(dir, md)} → ${target}`).toBe(true);
          }
        }
        if (zip === 'press-ai.zip') {
          const plugin = JSON.parse(readFileSync(join(pkg, '.claude-plugin/plugin.json'), 'utf8'));
          expect(plugin.name).toBe('press-ai');
          for (const s of SKILLS) expect(existsSync(join(pkg, 'skills', s, 'SKILL.md')), s).toBe(true);
          for (const a of AGENTS) expect(existsSync(join(pkg, 'agents', `${a}.md`)), a).toBe(true);
        }
        for (const l of LICENSES) expect(readFileSync(join(dir, l)).equals(readFileSync(join(ROOT, l))), `${zip}: ${l}`).toBe(true);
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    }
  });
});

async function gotoAi(page: Page, slug: string) {
  await page.goto(`${slug}/`);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}

test.describe('press-ai downloads: pages', () => {
  for (const [slug, expected] of Object.entries(PAGES)) {
    test(`/${slug}/ lists real same-origin download links next to its placeholder`, async ({ page, baseURL }) => {
      await gotoAi(page, slug);
      const m = manifest();
      await expect(page.locator('[data-embed^="dl-"]'), 'yer tutucu yerinde kalmamalı').toHaveCount(0);
      const block = page.locator('.prose [data-embed-source^="dl-"]');
      await expect(block, 'blok metindeki yerine taşınır').toHaveCount(1);
      const links = block.locator('a.dl-link');
      const hrefs = await links.evaluateAll((els) => els.map((el) => (el as HTMLAnchorElement).getAttribute('href') ?? ''));
      const prefix = new URL('downloads/press-ai/', baseURL).pathname;
      expect(hrefs.map((h) => h.replace(prefix, '')).sort()).toEqual([...expected].sort());
      for (const path of expected) {
        const link = block.locator(`a.dl-link[href="${prefix}${path}"]`);
        const art = m.files.find((f) => f.path === path)!;
        await expect(link, path).toHaveAttribute('download', art.save);
        await expect(link, `${path} erişilebilir ad`).toHaveAccessibleName(/\S/);
        const res = await page.request.get(new URL(`${prefix}${path}`, baseURL).href);
        expect(res.status(), path).toBe(200);
        expect(sha256(await res.body()), `${path} sunulan bayt = manifest`).toBe(art.sha256);
        if (path.endsWith('.zip')) expect(res.headers()['content-type'], path).toContain('application/zip');
      }
      const sums = block.locator(`a[href="${prefix}SHA256SUMS.txt"]`);
      await expect(sums).toHaveAttribute('download', 'SHA256SUMS');
      const served = await page.request.get(new URL(`${prefix}SHA256SUMS.txt`, baseURL).href);
      expect(served.status(), 'SHA256SUMS.txt önizlemede sunulur').toBe(200);
      expect(sha256(await served.body()), 'SHA256SUMS sunulan bayt').toBe(sha256(readFileSync(join(DIST, 'SHA256SUMS.txt'))));
      await expect(block.locator('script, astro-island')).toHaveCount(0);
    });
  }

  test('clicking a zip, a SKILL.md and an agent file performs a real browser download', async ({ page }) => {
    const m = manifest();
    const cases = [
      { slug: 'ai-skills', path: 'press-ai.zip' },
      { slug: 'ai-skills', path: 'files/skills/press-operations/SKILL.md' },
      { slug: 'ai-skills', path: 'press-ai-skill-press-build-triage.zip' },
      { slug: 'ai-agents', path: 'files/agents/press-operator.md' },
      { slug: 'ai-mcp', path: 'press-ai-mcp.zip' },
    ];
    for (const c of cases) {
      await gotoAi(page, c.slug);
      const art = m.files.find((f) => f.path === c.path)!;
      const link = page.locator(`.prose a.dl-link[href$="/downloads/press-ai/${c.path}"]`);
      const [download] = await Promise.all([page.waitForEvent('download'), link.click()]);
      expect(download.suggestedFilename(), c.path).toBe(art.save);
      const saved = await download.path();
      expect(sha256(readFileSync(saved)), `${c.path} indirilen bayt`).toBe(art.sha256);
    }
  });

  // Aynı layout denetimi 320'den masaüstüne: hesaplanan yazı ≥ 1rem, taşma yok, bağlantılar görünümde, etkili alan.
  // Kanıt ekranları test çıktısına yazılır ve rapora eklenir (bağımsız görsel inceleme için; referans değildir).
  const VIEWPORTS = [
    { name: '320', width: 320, height: 640 },
    { name: '360', width: 360, height: 740 },
    { name: '375', width: 375, height: 812 },
    { name: '390', width: 390, height: 844 },
    { name: 'landscape-phone', width: 844, height: 390 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1366, height: 900 },
  ];
  for (const vp of VIEWPORTS) {
    test(`download blocks at ${vp.name}: no overflow, text >= 1rem, hit areas, natural wrapping`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      for (const slug of Object.keys(PAGES)) {
        await gotoAi(page, slug);
        const r = await page.evaluate(() => {
          const block = document.querySelector<HTMLElement>('.prose [data-embed-source^="dl-"]')!;
          const vw = document.documentElement.clientWidth;
          const small = Array.from(block.querySelectorAll<HTMLElement>('*'))
            .filter((el) => Array.from(el.childNodes).some((n) => n.nodeType === 3 && /\S/.test(n.textContent ?? '')))
            .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
            .map((el) => `${el.tagName}.${el.className} ${getComputedStyle(el).fontSize}`);
          const links = Array.from(block.querySelectorAll<HTMLElement>('a.dl-link')).map((a) => {
            const b = a.getBoundingClientRect();
            return { left: b.left, right: b.right, w: b.width, h: b.height };
          });
          const breakers = Array.from(block.querySelectorAll<HTMLElement>('*')).filter((el) => {
            const cs = getComputedStyle(el);
            return cs.wordBreak === 'break-all' || cs.overflowWrap === 'anywhere';
          }).length;
          const family = getComputedStyle(block.querySelector('a.dl-link')!).fontFamily;
          return { vw, scroll: document.documentElement.scrollWidth, small, links, breakers, family };
        });
        expect(r.scroll, `${slug} ${vp.name}: yatay taşma`).toBeLessThanOrEqual(r.vw);
        expect(r.small, `${slug} ${vp.name}: 1rem altı metin`).toEqual([]);
        expect(r.breakers, `${slug} ${vp.name}: zorlayıcı kırma`).toBe(0);
        expect(r.family, 'Outfit ilk sırada').toMatch(/^"?Outfit/);
        const coarse = await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches);
        for (const l of r.links) {
          expect(l.left, `${slug} ${vp.name}`).toBeGreaterThanOrEqual(0);
          expect(l.right, `${slug} ${vp.name}`).toBeLessThanOrEqual(r.vw);
          expect(Math.min(l.w, l.h), `${slug} ${vp.name}: etkili alan`).toBeGreaterThanOrEqual(coarse ? 47.5 : 43.5);
        }
        if (slug === 'ai-skills' || vp.name === '320') {
          const shot = testInfo.outputPath(`${slug}-${vp.name}.png`);
          // Kanıt görüntüsü: sabit başlık, okuma çubuğu ve atlama bağlantısı bloğun üstüne binmesin (referans değildir).
          await page.locator('.prose [data-embed-source^="dl-"]').screenshot({
            path: shot,
            animations: 'disabled',
            style: '.site-header, .progress, .skip-link { visibility: hidden !important; }',
          });
          await testInfo.attach(`${slug}-${vp.name}`, { path: shot, contentType: 'image/png' });
        }
      }
    });
  }

  test('tapping the full package ZIP on a coarse pointer downloads it; download controls keep 48 px @touch', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'Kaba işaretçi profili (iPhone 13) gerekir.');
    const m = manifest();
    await gotoAi(page, 'ai-skills');
    expect(await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches), 'any-pointer: coarse').toBe(true);
    const sizes = await page
      .locator('.prose a.dl-link')
      .evaluateAll((els) => els.map((el) => Math.min(el.getBoundingClientRect().width, el.getBoundingClientRect().height)));
    expect(sizes.length).toBeGreaterThan(0);
    expect(sizes.filter((s) => s < 47.5), 'kaba işaretçide 48 px').toEqual([]);
    const art = m.files.find((f) => f.path === 'press-ai.zip')!;
    const link = page.locator('.prose a.dl-primary[href$="/downloads/press-ai/press-ai.zip"]');
    await link.scrollIntoViewIfNeeded();
    const [download] = await Promise.all([page.waitForEvent('download'), link.tap()]);
    expect(download.suggestedFilename()).toBe(art.save);
    expect(sha256(readFileSync(await download.path())), 'dokunarak indirilen bayt').toBe(art.sha256);
  });

  // Blok kapsamlı axe: WCAG 2.0/2.1/2.2 A ve AA; her etki düzeyi başarısızlıktır. Tam AA uyumu iddiası değildir.
  for (const scheme of ['light', 'dark'] as const) {
    test(`axe AA on download blocks (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      for (const slug of Object.keys(PAGES)) {
        await gotoAi(page, slug);
        const results = await new AxeBuilder({ page })
          .include('.prose [data-embed-source^="dl-"]')
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
          .analyze();
        expect(
          results.violations.map((v) => `${slug} ${v.impact} ${v.id}: ${v.nodes.length} × ${v.nodes[0]?.target.join(' ')}`),
        ).toEqual([]);
        expect(results.passes.length, `${slug}: axe blokta kural koştu`).toBeGreaterThan(0);
      }
    });
  }

  test('keyboard focus shows a single outline on the download link, mouse shows none', async ({ page, browserName }) => {
    await gotoAi(page, 'ai-agents');
    const first = page.locator('.prose a.dl-link').first();
    const frame = () =>
      first.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { outline: `${cs.outlineStyle} ${cs.outlineWidth}`, shadow: cs.boxShadow, border: cs.borderStyle };
      });
    const rest = await frame();
    await first.hover();
    await page.mouse.down();
    await page.mouse.up();
    const afterMouse = await frame();
    expect(afterMouse.outline.startsWith('none') || afterMouse.outline.endsWith(' 0px'), `${browserName}: fare halkası`).toBe(true);
    // Klavye: önceki odaklanabilir öğeden Tab ile gel.
    await first.evaluate((el) => {
      const all = Array.from(document.querySelectorAll<HTMLElement>('a[href], button, [tabindex="0"], summary'));
      const i = all.indexOf(el);
      (all[i - 1] ?? document.body).focus();
    });
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    await expect(first).toBeFocused();
    const focused = await frame();
    expect(focused.outline, 'tek outline').toBe('solid 2px');
    expect(focused.shadow, 'odakta ikinci çerçeve yok').toBe(rest.shadow);
    expect(focused.border, 'odakta kenarlık değişmez').toBe(rest.border);
  });
});
