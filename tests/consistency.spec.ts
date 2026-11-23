import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

// İçerik tutarlılığı (rapor E-15): gereksinim JSON'u, fazlar, açık kararlar ve markdown sayfaları aynı karar setine
// bağlı kalmalı. Tarayıcı gerektirmez; tek projede koşar.
const root = new URL('../', import.meta.url);
const read = (p: string) => readFileSync(new URL(p, root), 'utf8');
type Req = { id: string; title: string; detail: string; rail: string; priority: string; phase: string; source: string; owner?: string };
const reqs: Req[] = JSON.parse(read('src/data/requirements.json'));
type Phase = { id: string; after: string[]; entryGate?: string };
const phases: Phase[] = JSON.parse(read('src/data/phases.json'));
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

  test('phase order is told only by dependencies and the diagram follows phases.json', () => {
    const ph = Object.fromEntries(phases.map((p) => [p.id, p]));
    // Belgelenen bağımlılıklar (yol haritası metni): tek ara kapı P1 içindeki Keycloak adımıdır ve yalnız P2'yi açar.
    expect(Object.fromEntries(phases.map((p) => [p.id, p.after]))).toEqual({
      P0: [],
      P1: ['P0'],
      P2: ['P0'],
      P3: ['P1'],
      P4: ['P1'],
      P6: ['P2'],
      P5: ['P2', 'P4'],
      P7: ['P1', 'P2'],
    });
    expect(ph.P2.entryGate).toMatch(/Keycloak/);
    expect(ph.P2.entryGate).toMatch(/G-12.*G-16.*G-79.*G-81/);
    for (const p of phases) if (p.id !== 'P2') expect(p.entryGate, `${p.id} entryGate`).toBeUndefined();
    const diagram = read('src/components/Timeline.astro');
    for (const p of phases) expect(diagram, `faz sırası ${p.id}`).toContain(`>${p.id}<`);
    for (const p of phases) for (const pre of p.after) expect(diagram).toContain(`data-edge='${pre}-${p.id}'`);
    expect(diagram).toContain('Keycloak adımı');
    expect(diagram).toContain('Yol haritası faz sırası');
  });

  test('phases and tasks carry no duration, week, story point or effort estimate', () => {
    // Ürün kuralı olan süreler (log saklama günleri, 14 günlük deneme, haftalık yedek, K-26 yama hedefleri) görev
    // süresi değildir ve kalıpların dışındadır; yasak olan faz/görev süresi ve efor ölçümüdür.
    const raw: Record<string, unknown>[] = JSON.parse(read('src/data/phases.json'));
    const FORBIDDEN_FIELDS = ['start', 'end', 'weeks', 'duration', 'estimate', 'points'];
    for (const p of raw) {
      for (const f of FORBIDDEN_FIELDS) expect(p, `${p.id} alanı ${f}`).not.toHaveProperty(f);
      expect(Array.isArray(p.after), `${p.id} after`).toBe(true);
    }
    const seen = new Set<string>();
    for (const p of phases) {
      for (const pre of p.after) expect(seen.has(pre), `${p.id} önkoşulu ${pre} dizide daha önce gelmeli`).toBe(true);
      seen.add(p.id);
    }

    // Metin iki biçimde küçültülür ve ikisi de denenir: Türkçe kural "BİTİŞ HAFTASI" için gerekir (JavaScript `i`
    // bayrağı "I" ile "ı" harfini eşlemez), İngilizce kural "STORY POINTS" ve "SPRINT 3" için gerekir (Türkçe kural
    // "I" harfini "ı" yapar ve İngilizce sözcüğü bozar). Kalıplar küçük harfle yazılır ve Türkçe eklerde ASCII `\b`
    // yerine Unicode harf sınırı kullanılır: `\b` yalnız ASCII harf sınırıdır, "haftada" ve "eforu" gibi ekli
    // biçimlerde sınır oluşmaz.
    const forms = (t: string) => [t.toLocaleLowerCase('tr'), t.toLowerCase()];
    const PATTERNS: [RegExp, string][] = [
      [/\d+\.\s*hafta/u, 'N. hafta'],
      [/\d+\s*[–-]\s*\d+\.\s*hafta/u, 'N–M. hafta'],
      [/≈\s*\d+\s*hafta/u, '≈N hafta'],
      [/\d+\s*haftalık plan/u, 'N haftalık plan'],
      [/göreli süre/u, 'göreli süre'],
      [/story[- ]?points?/u, 'story point'],
      [/(?<![\p{L}])sprint/u, 'sprint'],
      [/adam[- /]?(gün|ay)/u, 'adam-gün'],
      [/hafta sayısı/u, 'hafta sayısı'],
      [/\d+\s*hafta(?!l[ıi]k)/u, 'N hafta'], // "4 haftalık" ürün süresidir, geçer
      [/hafta(s[ıi]|da(?!\s+bir(?![\p{L}]))|ya|dan|lar|larca)(?![\p{L}])|hafta(s[ıi]n)/u, 'haftası'], // "haftada bir" ürün sıklığıdır, geçer
      [/(?<![\p{L}])efor/u, 'efor'],
      [/(?<![\p{L}\p{N}])\d+\s*sp(?![\p{L}])/u, 'N SP'],
    ];
    // Kalıpların kendisi denenir: görev süresi yakalanır, ürün süresi geçer ("ay" için kalıp yok: "ilk 6 ay açık" ürün kuralıdır).
    const hit = (t: string) => forms(t).some((f) => PATTERNS.some(([re]) => re.test(f)));
    for (const bad of ['P1 12 hafta sürer', '3 hafta', "P0'ın ilk haftasında başlar", 'bitiş haftası', '5 SP', 'efor: 10 gün', '3 adam/gün', '14–26. hafta', '≈12 hafta', '42 haftalık plan', 'story point', 'iki sprint', 'P1 12 haftada biter', '3 haftaya sığar', 'ilk haftadan sonra', 'haftasından', 'eforu 10 gün', 'BİTİŞ HAFTASI', 'sprintler', 'STORY POINTS', 'SPRINT 3', '13 story-point', 'haftalarca sürer']) {
      expect(hit(bad), `yakalanmalı: ${bad}`).toBe(true);
    }
    for (const ok of ['4 haftalık', 'haftalık realm export', '14 günlük deneme', 'ilk 6 ay açık', '7 günlük/4 haftalık/12 aylık', 'haftalık sapma kontrolü', '72 saat', '365 gün', 'spring', 'haftada bir yedek', 'Spring Boot', 'SPRING', 'HAFTALIK', '4 HAFTALIK', 'SP-1', 'ISP', 'sp_config', 'effort', 'perforce', 'wasp']) {
      expect(hit(ok), `geçmeli: ${ok}`).toBe(false);
    }
    const rootDir = fileURLToPath(root);
    const walk = (dir: string, exts: string[]): string[] =>
      readdirSync(dir).flatMap((name) => {
        const full = join(dir, name);
        if (statSync(full).isDirectory()) return walk(full, exts);
        return exts.some((e) => name.endsWith(e)) ? [full] : [];
      });
    const files = [
      ...walk(join(rootDir, 'src/content/docs'), ['.md']),
      ...walk(join(rootDir, 'src/data'), ['.json', '.ts']),
      ...walk(join(rootDir, 'src/components'), ['.astro', '.tsx']),
      ...walk(join(rootDir, 'src/pages'), ['.astro']),
      ...walk(join(rootDir, 'src/layouts'), ['.astro']),
      join(rootDir, 'scripts/gen-diagrams.py'),
      join(rootDir, 'README.md'),
    ];
    expect(files.length).toBeGreaterThan(20);
    const offenders: string[] = [];
    for (const file of files) {
      const lines = readFileSync(file, 'utf8').split('\n');
      lines.forEach((line, i) => {
        const fs = forms(line);
        for (const [re, why] of PATTERNS) if (fs.some((f) => re.test(f))) offenders.push(`${file.slice(rootDir.length)}:${i + 1}: ${why}`);
      });
    }
    expect(offenders).toEqual([]);
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
