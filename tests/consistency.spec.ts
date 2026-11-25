import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
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
type TaskItem = { epic: string; status: string; level: string; evidence?: { commit: string; tests: string[] } };
type TaskBoard = {
  audit: { date: string; commit: string; note: string; addedAfter: string[] };
  epics: { id: string; title: string; goal: string }[];
  statuses: { id: string; label: string; rule: string }[];
  levels: { id: string; label: string; rule: string; phases?: string[]; ids?: string[] }[];
  items: Record<string, TaskItem>;
};
const RAILS = ['R1 Press', 'R2 Frappe yapılandırma', 'R2 Frappe geliştirme', 'R3 Frontend', 'R4 Keycloak', 'R5 AI', 'Shell', 'App çerçevesi', 'Çapraz', 'R6 Operasyon düzlemi'];

test.describe('content consistency', () => {
  test.beforeEach(({ browserName }) => {
    test.skip(browserName !== 'chromium', 'Dosya düzeyi denetim; tek motorda koşar.');
  });

  test('task board covers every requirement with a valid epic, status and level', () => {
    // Görev panosu verisi (src/data/task-board.json) gereksinim kaydını değiştirmez; yalnız sunum bilgisini taşır.
    expect(existsSync(new URL('src/data/task-board.json', root)), 'task-board.json yok').toBe(true);
    const board: TaskBoard = JSON.parse(read('src/data/task-board.json'));
    const itemIds = Object.keys(board.items);
    expect(itemIds.filter((id) => !ids.has(id)), 'gereksinimde olmayan kimlik').toEqual([]);
    expect(reqs.map((r) => r.id).filter((id) => !(id in board.items)), 'kaydı olmayan gereksinim').toEqual([]);
    const epicIds = board.epics.map((e) => e.id);
    expect(new Set(epicIds).size, 'epic kimliği tekil').toBe(epicIds.length);
    expect(board.statuses.map((s) => s.id)).toEqual(['done', 'in-progress', 'not-started', 'unverified']);
    expect(board.levels.map((l) => l.id)).toEqual(['poc', 'mvp', 'post-mvp', 'scale', 'enterprise']);
    for (const e of board.epics) {
      expect(e.title.trim(), e.id).not.toBe('');
      expect(e.goal.trim(), `${e.id} amacı`).not.toBe('');
      expect(itemIds.some((id) => board.items[id].epic === e.id), `${e.id} boş epic`).toBe(true);
    }
    for (const l of [...board.levels, ...board.statuses]) expect(l.rule.trim(), `${l.id} kuralı`).not.toBe('');
    for (const [id, it] of Object.entries(board.items)) {
      expect(epicIds, `${id} epic`).toContain(it.epic);
      expect(board.statuses.map((s) => s.id), `${id} durum`).toContain(it.status);
      expect(board.levels.map((l) => l.id), `${id} düzey`).toContain(it.level);
      const allowed = ['epic', 'status', 'level', ...(it.status === 'done' ? ['evidence'] : [])];
      expect(Object.keys(it).filter((k) => !allowed.includes(k)), `${id} fazla alan`).toEqual([]);
    }
  });

  test('task board levels follow the written mapping rules', () => {
    // Düzey elle seçilmez: sayfadaki kural (faz eşlemesi + adı yazılı istisna listesi) her kalemi tek düzeye bağlar.
    const board: TaskBoard = JSON.parse(read('src/data/task-board.json'));
    const byId = new Map<string, string>();
    const byPhase = new Map<string, string>();
    for (const l of board.levels) {
      for (const id of l.ids ?? []) {
        expect(byId.has(id), `${id} iki istisna listesinde`).toBe(false);
        expect(ids.has(id), `${l.id} istisnasında bilinmeyen ${id}`).toBe(true);
        byId.set(id, l.id);
      }
      for (const p of l.phases ?? []) {
        expect(byPhase.has(p), `${p} iki düzeyde`).toBe(false);
        byPhase.set(p, l.id);
      }
    }
    expect([...byPhase.keys()].sort(), 'her faz bir düzeye bağlı').toEqual(phases.map((p) => p.id).sort());
    const wrong = reqs
      .map((r) => ({ id: r.id, want: byId.get(r.id) ?? byPhase.get(r.phase), got: board.items[r.id].level }))
      .filter((x) => x.want !== x.got)
      .map((x) => `${x.id}: ${x.got} (kural ${x.want})`);
    expect(wrong).toEqual([]);
    // MVP kapsam kararı: P2 ödeme katmanı ve P4 kendi kendine deneme ve etkinleştirme MVP dışındadır.
    for (const r of reqs.filter((x) => x.phase === 'P2')) expect(board.items[r.id].level, r.id).not.toBe('mvp');
    for (const id of ['G-31', 'G-95']) expect(board.items[id].level, id).toBe('post-mvp');
  });

  test('every done task carries evidence that exists in the repository', () => {
    // "Bitti" yalnız kanıtla yazılır: denetim commit'i depoda olmalı, test dosyası yolu gerçek olmalı.
    const board: TaskBoard = JSON.parse(read('src/data/task-board.json'));
    const done = Object.entries(board.items).filter(([, it]) => it.status === 'done');
    expect(done.length, 'en az bir bitti kaydı').toBeGreaterThan(0);
    for (const [id, it] of done) {
      expect(it.evidence, `${id} kanıt`).toBeTruthy();
      const ev = it.evidence!;
      expect(ev.commit, `${id} commit`).toMatch(/^[0-9a-f]{7,40}$/);
      expect(ev.tests.length, `${id} test listesi boş`).toBeGreaterThan(0);
      for (const t of ev.tests) expect(existsSync(new URL(t, root)), `${id} test dosyası ${t}`).toBe(true);
    }
    const commits = new Set(done.map(([, it]) => it.evidence!.commit));
    for (const c of commits) {
      expect(() => execFileSync('git', ['cat-file', '-e', `${c}^{commit}`], { cwd: fileURLToPath(root), stdio: 'ignore' }), `commit ${c}`).not.toThrow();
    }
    // Denetlenmemiş kalem bitti ya da sürüyor sayılmaz: denetim yalnız P0..P4 MUST kalemlerini okudu.
    // Denetimden sonra eklenen kalemler (audit.addedAfter) ayrıca adlandırılır; bunlar da denetim dışıdır.
    const addedAfter = new Set(board.audit.addedAfter);
    expect([...addedAfter].filter((id) => !ids.has(id)), 'addedAfter bilinmeyen kimlik').toEqual([]);
    expect(addedAfter.size, 'addedAfter tekrarsız').toBe(board.audit.addedAfter.length);
    expect(board.statuses.find((s) => s.id === 'unverified')!.rule).toContain('denetimden sonra eklen');
    const audited = (r: Req) =>
      !addedAfter.has(r.id) && r.priority === 'MUST' && ['P0', 'P1', 'P2', 'P3', 'P4'].includes(r.phase);
    const claimed = reqs.filter((r) => !audited(r) && board.items[r.id].status !== 'unverified').map((r) => r.id);
    expect(claimed, 'denetim dışı kalemde durum iddiası').toEqual([]);
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

  test('panel roles G-168, G-169 and G-170 are MVP items (AJA-827)', () => {
    const board: TaskBoard = JSON.parse(read('src/data/task-board.json'));
    for (const id of ['G-168', 'G-169', 'G-170']) {
      const r = reqs.find((x) => x.id === id)!;
      expect(r.priority, id).toBe('MUST');
      expect(r.phase, id).toBe('P1');
      expect(board.items[id].level, id).toBe('mvp');
    }
    for (const id of ['G-169', 'G-170']) {
      const d = reqs.find((x) => x.id === id)!.detail;
      expect(d, id).not.toContain('Kalem G-33 partner programına bağlıdır.');
      expect(d, id).not.toContain('Kalem MVP kapsamında değildir.');
    }
    const g169 = reqs.find((x) => x.id === 'G-169')!.detail;
    expect(g169).not.toContain('Partner programı G-33 gereksinimindedir.');
    expect(g169).toContain('Press partner ödemeleri ve partner seviyeleri G-33 içinde kalır.');
    expect(g169).toContain('Bağ, platform_core içinde bir kayıtla tutulur.');
    expect(g169).toContain('Kayıt bayi kiracısını müşteri kiracısına bağlar.');
    expect(g169).toContain('Bu kaydı yalnız platform operatörü açar ve kapatır.');
    expect(g169).toContain('Platform operatörü isteği onaylar.');
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

  test('phase diagram arrows read exactly as the after lists in phases.json', () => {
    // Okur, birbirine değen çizgileri tek bir bağlantı gibi okur. Bu yüzden değen oklar bir grup oluşturur.
    // Bir grupta her çıkış fazı her hedef faza bağlı görünür. Grubun okunan bağımlılıkları veriyle birebir aynı olmalı.
    // Aynı fazdan çıkan oklar (P0 → P1, P2) ve aynı faza giren oklar bu yüzden çizgi paylaşabilir.
    // Uçları değmeyen dik kesişme bağlantı sayılmaz. Çizimde kesişme noktası zemin renginde bir boşlukla ayrılır.
    const svg = read('src/components/Timeline.astro');
    type Pt = [number, number];
    const boxes = [...svg.matchAll(/<rect x='(\d+)' y='(\d+)' width='(\d+)' height='(\d+)'[^>]*\/>\s*<text[^>]*>(P\d)</g)].map((m) => ({
      id: m[5],
      x: +m[1],
      y: +m[2],
      w: +m[3],
      h: +m[4],
    }));
    expect(boxes.map((b) => b.id).sort()).toEqual(phases.map((p) => p.id).sort());
    const edges = [...svg.matchAll(/<path data-edge='([^']+)' d='([^']+)'/g)].map((m) => {
      const pts: Pt[] = [...m[2].matchAll(/[ML]\s*(-?[\d.]+)\s+(-?[\d.]+)/g)].map((c) => [+c[1], +c[2]]);
      expect(m[2].replace(/[ML]\s*-?[\d.]+\s+-?[\d.]+/g, '').trim(), `${m[1]} yalnız M/L komutu kullanır`).toBe('');
      return { label: m[1], pts };
    });
    const onBoundary = ([x, y]: Pt, b: (typeof boxes)[number]) =>
      x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h && (x === b.x || x === b.x + b.w || y === b.y || y === b.y + b.h);
    const boxAt = (p: Pt) => boxes.filter((b) => onBoundary(p, b)).map((b) => b.id);
    const ends = edges.map((e) => {
      const from = boxAt(e.pts[0]);
      const to = boxAt(e.pts[e.pts.length - 1]);
      expect(from, `${e.label} tek bir fazdan çıkar`).toHaveLength(1);
      expect(to, `${e.label} tek bir faza girer`).toHaveLength(1);
      const expected = e.label.replace(/-gate$/, '');
      expect(`${from[0]}-${to[0]}`, `${e.label} çizilen uçlar`).toBe(expected);
      return { ...e, from: from[0], to: to[0] };
    });
    const deps = ends.filter((e) => !e.label.endsWith('-gate')).map((e) => e.label).sort();
    expect(deps, 'oklar phases.json after listesiyle birebir').toEqual(phases.flatMap((p) => p.after.map((a) => `${a}-${p.id}`)).sort());
    const onSeg = ([x, y]: Pt, [a, b]: [Pt, Pt]) =>
      (a[0] === b[0] && x === a[0] && y >= Math.min(a[1], b[1]) && y <= Math.max(a[1], b[1])) ||
      (a[1] === b[1] && y === a[1] && x >= Math.min(a[0], b[0]) && x <= Math.max(a[0], b[0]));
    const segs = (pts: Pt[]) => pts.slice(1).map((p, i) => [pts[i], p] as [Pt, Pt]);
    for (const e of ends) for (const [a, b] of segs(e.pts)) expect(a[0] === b[0] || a[1] === b[1], `${e.label} dik parçalı`).toBe(true);
    const touch = (a: Pt[], b: Pt[]) => a.some((p) => segs(b).some((s) => onSeg(p, s))) || b.some((p) => segs(a).some((s) => onSeg(p, s)));
    const parent = ends.map((_, i) => i);
    const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
    for (let i = 0; i < ends.length; i++) for (let j = i + 1; j < ends.length; j++) if (touch(ends[i].pts, ends[j].pts)) parent[find(i)] = find(j);
    const groups = new Map<number, typeof ends>();
    for (const [i, e] of ends.entries()) groups.set(find(i), [...(groups.get(find(i)) ?? []), e]);
    for (const g of groups.values()) {
      const drawn = g.map((e) => `${e.from}-${e.to}`).sort();
      const seen = [...new Set(g.map((e) => e.from))].flatMap((f) => [...new Set(g.map((e) => e.to))].map((t) => `${f}-${t}`)).sort();
      expect(seen, `değen oklar (${g.map((e) => e.label).join(', ')}) yalnız çizilen bağımlılıkları göstermeli`).toEqual(drawn);
    }
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
