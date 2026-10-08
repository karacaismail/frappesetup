import { readdirSync, readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

// İçerik tutarlılığı (rapor E-15): gereksinim JSON'u, fazlar, açık kararlar ve markdown sayfaları aynı karar setine
// bağlı kalmalı. Tarayıcı gerektirmez; tek projede koşar.
const root = new URL('../', import.meta.url);
const read = (p: string) => readFileSync(new URL(p, root), 'utf8');
type Req = { id: string; title: string; detail: string; rail: string; priority: string; phase: string; source: string; owner?: string };
const reqs: Req[] = JSON.parse(read('src/data/requirements.json'));
const phases: { id: string; start: number; end: number }[] = JSON.parse(read('src/data/phases.json'));
const docsDir = new URL('src/content/docs/', root);
const docs = readdirSync(docsDir)
  .filter((f) => f.endsWith('.md'))
  .map((f) => ({ slug: f.replace(/\.md$/, ''), text: readFileSync(new URL(f, docsDir), 'utf8') }));
const ids = new Set(reqs.map((r) => r.id));
const RAILS = ['R1 Press', 'R2 Frappe yapılandırma', 'R2 Frappe geliştirme', 'R3 Frontend', 'R4 Keycloak', 'R5 AI', 'Shell', 'App çerçevesi', 'Çapraz', 'R6 Operasyon düzlemi'];

test.describe('content consistency', () => {
  test.beforeEach(({ browserName }) => {
    test.skip(browserName !== 'chromium', 'Dosya düzeyi denetim; tek motorda koşar.');
  });

  test('requirement ids are unique, contiguous and well formed', () => {
    expect(ids.size).toBe(reqs.length);
    for (const prefix of ['G', 'SA']) {
      const nums = reqs.filter((r) => r.id.startsWith(`${prefix}-`)).map((r) => Number(r.id.split('-')[1])).sort((a, b) => a - b);
      expect(nums, `${prefix} serisi boşluksuz`).toEqual(nums.map((_, i) => i + 1));
    }
    const phaseIds = new Set(phases.map((p) => p.id));
    for (const r of reqs) {
      expect(r.title.trim(), r.id).not.toBe('');
      expect(r.detail.trim(), r.id).not.toBe('');
      expect((r.owner ?? '').trim(), `${r.id} sahibi`).not.toBe('');
      expect(['MUST', 'SHOULD', 'MAY'], `${r.id} öncelik`).toContain(r.priority);
      expect(phaseIds.has(r.phase), `${r.id} fazı ${r.phase}`).toBe(true);
      expect(['native', 'configure', 'develop', 'integrate'], `${r.id} kaynak`).toContain(r.source);
      expect(RAILS, `${r.id} ray`).toContain(r.rail);
    }
    for (const p of phases) expect(p.end, p.id).toBeGreaterThan(p.start);
  });

  test('every G/SA reference in pages and requirement details exists', () => {
    const missing: string[] = [];
    const scan = (where: string, text: string) => {
      for (const m of text.matchAll(/\b(G|SA)-(\d+)\b/g)) {
        const id = `${m[1]}-${m[2]}`;
        if (!ids.has(id)) missing.push(`${where}: ${id}`);
      }
    };
    for (const d of docs) scan(d.slug, d.text);
    for (const r of reqs) scan(r.id, r.detail);
    expect(missing).toEqual([]);
  });

  test('every K decision reference exists in the open decisions page', () => {
    const decisions = docs.find((d) => d.slug === 'acik-kararlar')!.text;
    const defined = new Set([...decisions.matchAll(/^\| (K-\d+) \|/gm)].map((m) => m[1]));
    const missing: string[] = [];
    const scan = (where: string, text: string) => {
      for (const m of text.matchAll(/\bK-(\d+)\b/g)) if (!defined.has(`K-${m[1]}`)) missing.push(`${where}: K-${m[1]}`);
    };
    for (const d of docs) scan(d.slug, d.text);
    for (const r of reqs) scan(r.id, r.detail);
    expect(missing).toEqual([]);
  });

  test('internal links point to existing pages and anchors', () => {
    const slugs = new Set(docs.map((d) => d.slug));
    // Çapalar derlenmiş HTML'deki gerçek id'lere karşı denetlenir (başlık kimliği üreticisi kaynakta tahmin edilmez).
    const anchorCache = new Map<string, Set<string>>();
    const anchorsOf = (slug: string) => {
      if (!anchorCache.has(slug)) {
        const html = readFileSync(new URL(slug ? `dist/${slug}/index.html` : 'dist/index.html', root), 'utf8');
        anchorCache.set(slug, new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])));
      }
      return anchorCache.get(slug)!;
    };
    const broken: string[] = [];
    let anchors = 0;
    const check = (from: string, slug: string, fragment?: string) => {
      if (slug && !slugs.has(slug)) return broken.push(`${from} → ${slug}`);
      if (!fragment) return;
      anchors++;
      if (!anchorsOf(slug).has(decodeURIComponent(fragment))) broken.push(`${from} → ${slug || '/'}#${fragment}`);
    };
    for (const d of docs) {
      for (const m of d.text.matchAll(/\]\(\/frappesetup\/([^/)#]*)\/?(?:#([^)\s]+))?\)/g)) check(d.slug, m[1], m[2]);
      for (const m of d.text.matchAll(/\]\(#([^)\s]+)\)/g)) check(d.slug, d.slug, m[1]);
    }
    expect(anchors, 'en az bir çapa denetlenmeli').toBeGreaterThan(0);
    expect(broken).toEqual([]);
  });

  test('phase decisions from the evaluation report hold (Y-01, Y-02)', () => {
    const phaseOf = (id: string) => reqs.find((r) => r.id === id)!.phase;
    // P2 kabulü operasyon sitesi finans çekirdeğine dayanır: çekirdek P2'de, P6'da değil.
    for (const id of ['SA-17', 'SA-18', 'SA-19', 'SA-21', 'SA-22', 'SA-23', 'SA-34', 'SA-35', 'SA-41']) expect(phaseOf(id), id).toBe('P2');
    // İlk dikey dilimin AI ve destek adımları P1 prototipleridir; tam teslimler sonraki fazda.
    expect(phaseOf('G-129')).toBe('P1');
    expect(phaseOf('SA-40')).toBe('P1');
    // P0 çıkışı yalnız P0 kalemlerine dayanır: Press'e Keycloak girişi (G-12) P1'dedir.
    expect(phaseOf('G-12')).toBe('P1');
    const p0exit = JSON.stringify(phases.find((p) => p.id === 'P0'));
    expect(p0exit).not.toMatch(/Press'e (sosyal )?giriş/);
  });

  test('built pages have no table rows rendered as paragraphs', () => {
    // Tablo içindeki boş satır markdown tablosunu böler; kalan satırlar `<p>| …` olarak yayımlanır.
    const dist = new URL('dist/', root);
    const pages = readdirSync(dist, { recursive: true, encoding: 'utf8' }).filter((f) => f.endsWith('.html'));
    expect(pages.length).toBeGreaterThan(docs.length);
    const broken = pages.filter((f) => /<p>\s*\|/.test(readFileSync(new URL(f, dist), 'utf8')));
    expect(broken).toEqual([]);
  });

  test('phase order has no backward dependency and the timeline matches phases.json', () => {
    const ph = Object.fromEntries(phases.map((p) => [p.id, p]));
    // Belgelenen bağımlılıklar: bağımlı faz önkoşulun bitişinden sonra başlar. P2'nin tek ara kapısı P1 içindeki
    // Keycloak adımıdır (14. hafta, yol haritası metni).
    const after: [string, string][] = [['P1', 'P0'], ['P2', 'P0'], ['P3', 'P1'], ['P4', 'P1'], ['P6', 'P2'], ['P5', 'P4']];
    for (const [dep, pre] of after) expect(ph[dep].start, `${dep} ${pre} bitmeden başlıyor`).toBeGreaterThanOrEqual(ph[pre].end);
    expect(ph.P2.start).toBeGreaterThan(ph.P1.start);
    const timeline = read('src/components/Timeline.astro');
    for (const p of phases) expect(timeline, `zaman çizelgesi ${p.id}`).toContain(`${p.start}–${p.end}. hafta`);
    expect(timeline).toContain(`${Math.max(...phases.map((p) => p.end))} haftalık plan`);
  });

  test('README counts match the requirement data', () => {
    const readme = read('README.md');
    const g = reqs.filter((r) => r.id.startsWith('G-')).length;
    const sa = reqs.filter((r) => r.id.startsWith('SA-')).length;
    expect(readme).toContain(`${reqs.length} numaralı gereksinim (G-1..G-${g}, SA-1..SA-${sa})`);
    expect(readme).toContain(`${docs.length} bölüm`);
  });

  test('superseded names and hosts do not reappear in pages or requirements', () => {
    // Kaçışlı yazımlar (\\<kiracı\\>, &lt;kiracı&gt;) da yakalanır: metin önce normalleştirilir.
    const norm = (t: string) => t.replace(/\\([<>_])/g, '$1').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
    const RULES: [RegExp, string][] = [
      // Adın geçersiz olduğunu söyleyen yasak cümleleri ("... adı kullanılmaz", "... açılmaz") muaftır.
      [/(?<![_\w])press\.api\.ops(?!.{0,40}(kullanılmaz|açılmaz))/, 'press.api.ops (press_tr.api.ops olmalı)'],
      [/<kiracı>\.<marka>\.com\.tr/, '<kiracı>.<marka>.com.tr (app. alt bölgesi olmalı)'],
      [/buy_credits_iyzico|press\.api\.billing\.create_iyzico/, 'iyzico ucu press_tr.api.billing.create_iyzico_checkout_form olmalı'],
      [/kullanıcının Keycloak token/, 'kiracı verisi kullanıcının Keycloak belirteciyle değil aracı belirteciyle (G-148)'],
    ];
    const offenders: string[] = [];
    const scan = (where: string, text: string) => {
      const t = norm(text);
      for (const [re, why] of RULES) if (re.test(t)) offenders.push(`${where}: ${why}`);
      if (/panel-spa/.test(t) && !/K-25/.test(t)) offenders.push(`${where}: panel-spa`);
    };
    for (const d of docs) scan(d.slug, d.text);
    for (const r of reqs) scan(r.id, `${r.title} ${r.detail}`);
    expect(offenders).toEqual([]);
  });
});
