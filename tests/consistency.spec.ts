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
// release: commit'i içeren main yayını (PR numarası ve yayın commit'i); null ise commit henüz yayımlanmadı.
type Release = { pr: number; commit: string } | null;
type TaskItem = { epic: string; status: string; level: string; evidence?: { commit: string; tests: string[]; release: Release } };
type TaskBoard = {
  audit: { date: string; commit: string; release: Release; note: string; addedAfter: string[] };
  update: { date: string; commit: string; release: Release; note: string; reviewed: string[] };
  epics: { id: string; title: string; goal: string }[];
  statuses: { id: string; label: string; rule: string }[];
  levels: { id: string; label: string; rule: string; phases?: string[]; ids?: string[] }[];
  items: Record<string, TaskItem>;
};
const decisionRows = docs.flatMap(({ text }) => [...text.matchAll(/^\| (K-\d+) \|.*$/gm)]);
const RAILS = ['R1 Press', 'R2 Frappe yapılandırma', 'R2 Frappe geliştirme', 'R3 Frontend', 'R4 Keycloak', 'R5 AI', 'Shell', 'App çerçevesi', 'Çapraz', 'R6 Operasyon düzlemi'];

// Git yardımcıları: kanıt commit'leri backend dalındadır; main dalına her yayın tek commit olarak girer.
const cwd = fileURLToPath(root);
const git = (...args: string[]) => execFileSync('git', args, { cwd, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
const gitOk = (...args: string[]) => {
  try {
    execFileSync('git', args, { cwd, stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
};
const isShallow = () => git('rev-parse', '--is-shallow-repository') === 'true';
const hasCommit = (c: string) => gitOk('cat-file', '-e', `${c}^{commit}`);
const inHead = (c: string) => hasCommit(c) && gitOk('merge-base', '--is-ancestor', c, 'HEAD');
// Yayın commit'i backend commit'ini metninde adlandırır: "Birleşmeler" listesinde "- <kısa ad> " satırıyla ya da
// "Kaynak: <tam ad>" satırıyla. Kısa ad en az 7 karakterdir; iki ad önek olarak karşılaştırılır.
const samePrefix = (a: string, b: string) => a.length >= 7 && b.length >= 7 && (a.startsWith(b) || b.startsWith(a));
const namesCommit = (message: string, c: string) =>
  /^Kaynak: [0-9a-f]{7,40}$/m.test(message) &&
  message.split('\n').some((l) => {
    const m = l.match(/^(?:- |Kaynak: )([0-9a-f]{7,40})\b/);
    return m !== null && samePrefix(m[1], c);
  });
const releaseMessages = (ref: string) =>
  git('log', '--format=%H%n%B%x1e', ref)
    .split('\x1e')
    .map((e) => e.trim())
    .filter(Boolean)
    .map((e) => ({ sha: e.slice(0, e.indexOf('\n') < 0 ? e.length : e.indexOf('\n')), body: e }))
    .filter((e) => /^Kaynak: /m.test(e.body));
// Kanıt commit'leri backend dalındadır. Backend geçmişi GitHub'a gitmez ve CI kopyası sığdır (tek commit).
// Yayın commit'lerinin "Kaynak:" satırı backend commit'idir. Bu commit'lerden biri yerelde varsa backend geçmişi vardır.
const mainRef = () => (gitOk('rev-parse', '--verify', '--quiet', 'refs/remotes/origin/main') ? 'refs/remotes/origin/main' : null);
let backendCache: boolean | undefined;
const hasBackendHistory = () => {
  if (backendCache !== undefined) return backendCache;
  const refs = ['refs/heads/backend', 'refs/remotes/origin/backend'];
  const sources = [...releaseMessages('HEAD'), ...(mainRef() ? releaseMessages(mainRef()!) : [])]
    .map((e) => e.body.match(/^Kaynak: ([0-9a-f]{7,40})$/m)?.[1])
    .filter((x): x is string => Boolean(x));
  backendCache = refs.some((r) => gitOk('rev-parse', '--verify', '--quiet', r)) || sources.some(hasCommit);
  return backendCache;
};
// Denetim kopyanın türüne göre ayrılır (inceleme 1 Ö-2, inceleme r2-1 E-1 ve K-1):
// 1. Commit yerelde varsa HEAD geçmişinde olmalıdır. release doluysa yayın commit'i de yerelde olmalı ve metninde kanıt
//    commit'ini adlandırmalıdır. release null ise origin/main'deki hiçbir yayın commit'i onu adlandırmamalıdır.
// 2. Commit yerelde yoksa ve backend geçmişi varsa commit uydurmadır.
// 3. Tam geçmişli main kopyasında commit yoktur. release doluysa yayın commit'i HEAD geçmişinde olmalı ve kanıt commit'ini
//    adlandırmalıdır. release null ise HEAD geçmişindeki bir yayın commit'i onu adlandırmalıdır. Bu, dosyayı main'e
//    getiren yayındır.
// 4. Sığ kopyada geçmiş yoktur. Yayın commit'i yerelde varsa onu adlandırmalıdır. Yoksa yalnız alan biçimi denetlenir.
//    release null ise kayıt açıkça "henüz yayımlanmadı" der. Alan eksik olamaz (releaseShape).
const evidenceProblems = (label: string, c: string, rel: Release): string[] => {
  const out: string[] = [];
  const shallow = isShallow();
  const relNames = (r: NonNullable<Release>) => {
    if (hasCommit(r.commit)) {
      if (!namesCommit(git('log', '-1', '--format=%B', r.commit), c))
        out.push(`${label}: yayın commit'i ${r.commit} metninde ${c} commit'ini adlandırmıyor`);
    } else if (!shallow) {
      out.push(`${label}: yayın commit'i ${r.commit} depoda yok (origin/main çekilmemiş olabilir)`);
    }
  };
  if (hasCommit(c)) {
    if (!inHead(c)) out.push(`${label}: ${c} HEAD geçmişinde değil`);
    if (rel) relNames(rel);
    else if (mainRef()) {
      const named = releaseMessages(mainRef()!).filter((e) => namesCommit(e.body, c));
      if (named.length > 0) out.push(`${label}: ${c} ${named[0].sha.slice(0, 8)} ile yayımlandı ama release alanı null`);
    }
    return out;
  }
  if (shallow) {
    if (rel) relNames(rel);
    return out;
  }
  if (hasBackendHistory()) {
    out.push(`${label}: ${c} depoda yok`);
    return out;
  }
  if (rel) {
    relNames(rel);
    if (hasCommit(rel.commit) && !inHead(rel.commit)) out.push(`${label}: yayın commit'i ${rel.commit} HEAD geçmişinde değil`);
  } else if (!releaseMessages('HEAD').some((e) => namesCommit(e.body, c))) {
    out.push(`${label}: ${c} depoda yok ve HEAD geçmişindeki hiçbir yayın commit'i onu adlandırmıyor`);
  }
  return out;
};
const releaseShape = (label: string, rel: unknown): string[] => {
  if (rel === null) return [];
  if (typeof rel !== 'object' || rel === undefined) return [`${label}: release alanı yok`];
  const r = rel as Record<string, unknown>;
  const out: string[] = [];
  if (Object.keys(r).sort().join(',') !== 'commit,pr') out.push(`${label}: release yalnız pr ve commit taşır`);
  if (!Number.isInteger(r.pr) || (r.pr as number) < 1) out.push(`${label}: release.pr pozitif tam sayı değil`);
  if (typeof r.commit !== 'string' || !/^[0-9a-f]{7,40}$/.test(r.commit)) out.push(`${label}: release.commit biçimi`);
  return out;
};

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
    // "Bitti" yalnız kanıtla yazılır: kanıt commit'i depoda olmalı, test dosyası yolu gerçek olmalı.
    const board: TaskBoard = JSON.parse(read('src/data/task-board.json'));
    const done = Object.entries(board.items).filter(([, it]) => it.status === 'done');
    expect(done.length, 'en az bir bitti kaydı').toBeGreaterThan(0);
    const shape: string[] = [];
    for (const [id, it] of done) {
      expect(it.evidence, `${id} kanıt`).toBeTruthy();
      const ev = it.evidence!;
      expect(Object.keys(ev).sort(), `${id} kanıt alanları`).toEqual(['commit', 'release', 'tests']);
      expect(ev.commit, `${id} commit`).toMatch(/^[0-9a-f]{7,40}$/);
      shape.push(...releaseShape(id, ev.release));
      expect(ev.tests.length, `${id} test listesi boş`).toBeGreaterThan(0);
      for (const t of ev.tests) expect(existsSync(new URL(t, root)), `${id} test dosyası ${t}`).toBe(true);
    }
    expect(shape, 'release biçimi').toEqual([]);
    // Kural metinleri iki sınırı açık söyler: "Bitti" yalnız yerel yığında geçti, canlı kabul "Sürüyor" kalır.
    expect(board.statuses.find((s) => s.id === 'done')!.rule).toContain('yalnız yerel yığında');
    expect(board.statuses.find((s) => s.id === 'in-progress')!.rule).toContain('canlı');
    // Sığ kopyada da koşar: commit yerelde yoksa release eşlemesi ve yayın commit'i denetlenir (evidenceProblems).
    const problems = done.flatMap(([id, it]) => evidenceProblems(id, it.evidence!.commit, it.evidence!.release));
    expect(problems, 'kanıt commit geçmişi').toEqual([]);
    // Denetlenmemiş kalem bitti ya da sürüyor sayılmaz: denetim yalnız P0..P4 MUST kalemlerini okudu.
    // Denetimden sonra eklenen kalemler (audit.addedAfter) ayrıca adlandırılır; bunlar da denetim dışıdır.
    const addedAfter = new Set(board.audit.addedAfter);
    expect([...addedAfter].filter((id) => !ids.has(id)), 'addedAfter bilinmeyen kimlik').toEqual([]);
    expect(addedAfter.size, 'addedAfter tekrarsız').toBe(board.audit.addedAfter.length);
    expect(board.statuses.find((s) => s.id === 'unverified')!.rule).toContain('denetimden sonra eklen');
    // Güncelleme (update.reviewed) denetim dışındaki kalemleri adıyla okur; yalnız bu kalemler ek durum taşıyabilir.
    const reviewed = new Set(board.update.reviewed);
    expect([...reviewed].filter((id) => !ids.has(id)), 'reviewed bilinmeyen kimlik').toEqual([]);
    expect(reviewed.size, 'reviewed tekrarsız').toBe(board.update.reviewed.length);
    // Okunan kalem "Doğrulanmadı" kalamaz: güncelleme onu okudu ve bir durum verdi (inceleme 1, K-4).
    expect(
      [...reviewed].filter((id) => board.items[id]?.status === 'unverified'),
      'reviewed listesinde Doğrulanmadı kalan kalem',
    ).toEqual([]);
    const audited = (r: Req) =>
      reviewed.has(r.id) ||
      (!addedAfter.has(r.id) && r.priority === 'MUST' && ['P0', 'P1', 'P2', 'P3', 'P4'].includes(r.phase));
    const claimed = reqs.filter((r) => !audited(r) && board.items[r.id].status !== 'unverified').map((r) => r.id);
    expect(claimed, 'denetim dışı kalemde durum iddiası').toEqual([]);
  });

  test('task board update names a commit that is an ancestor of HEAD', () => {
    // Pano güncel kalır: gereksinimi bitiren ya da ilerleten dal, aynı dalda task-board.json kaydını ve update
    // bloğunu da günceller. update.commit depoda olmalı ve HEAD'in atası olmalı; tarih denetim tarihinden önce olamaz.
    const board: TaskBoard = JSON.parse(read('src/data/task-board.json'));
    const u = board.update;
    const a = board.audit;
    expect(u.date, 'update.date YYYY-AA-GG').toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(Number.isNaN(Date.parse(`${u.date}T00:00:00Z`)), 'update.date geçerli tarih').toBe(false);
    expect(u.date >= a.date, 'güncelleme denetimden önce olamaz').toBe(true);
    expect(u.commit, 'update.commit').toMatch(/^[0-9a-f]{7,40}$/);
    expect(a.commit, 'audit.commit').toMatch(/^[0-9a-f]{7,40}$/);
    expect(u.note.trim(), 'update.note').not.toBe('');
    expect([...releaseShape('update', u.release), ...releaseShape('audit', a.release)], 'release biçimi').toEqual([]);
    // Sığ kopyada da koşar: commit yerelde yoksa release eşlemesi ve yayın commit'i denetlenir (evidenceProblems).
    expect(
      [...evidenceProblems('update', u.commit, u.release), ...evidenceProblems('audit', a.commit, a.release)],
      'update ve audit commit geçmişi',
    ).toEqual([]);
    // Güncelleme denetimden sonra gelir: iki commit de varsa update.commit audit.commit'in torunudur (K-2).
    if (hasCommit(u.commit) && hasCommit(a.commit)) {
      expect(gitOk('merge-base', '--is-ancestor', a.commit, u.commit), `update.commit ${u.commit}, audit.commit ${a.commit} torunu`).toBe(true);
    }
  });

  test('fabricated evidence commits fail in full history', () => {
    // Uydurma commit kodu tam geçmişte geçmez (inceleme r2-1, E-1). release null olsa da geçmez.
    // Sığ kopyada geçmiş yoktur; orada bu denetim koşamaz.
    test.skip(isShallow(), 'Sığ kopya: commit geçmişi yok.');
    const fake = { pr: 18, commit: '1d3e6344' };
    for (const c of ['deadbeef', 'abcdef12']) {
      expect(evidenceProblems('sahte', c, null), `${c}, release null`).not.toEqual([]);
      expect(evidenceProblems('sahte', c, fake), `${c}, release dolu`).not.toEqual([]);
    }
    // Yayın commit'i uydurmaysa da geçmez (inceleme r2-1, K-1).
    expect(evidenceProblems('sahte', '36afb874', { pr: 18, commit: 'abcdef12' }), 'uydurma yayın commit').not.toEqual([]);
  });

  test('task board names environments, not staging', () => {
    // Backend'de staging ortamı yoktur; canlı ortamlar alpha, beta, rc ve prod'dur. Pano kuralları ortam adını yazar.
    expect(read('src/data/task-board.json')).not.toMatch(/staging/i);
  });

  test('published retention, AI safeguards and decision caveats remain documented', () => {
    const text = (slug: string) => docs.find((doc) => doc.slug === slug)!.text;
    expect(text('rail-5-ai')).toContain('konuşma içeriği 90 gün');
    expect(reqs.find((req) => req.id === 'G-87')?.detail).toContain('konuşma içeriği 90 gün');

    const k9 = text('kararlar').split('\n').find((line) => line.startsWith('| K9 |'));
    const homeCard = read('src/pages/index.astro').split('\n').find((line) => line.includes("id: 'K9'"));
    for (const decision of [k9, homeCard]) {
      expect(decision).toContain('AI eylemleri aynı sunucu izinlerinden geçer.');
      expect(decision).toContain('Yazma eylemleri önizleme ve onay gerektirir.');
      expect(decision).toContain('Sistem her eylemi denetim kaydına yazar.');
      expect(decision).toContain('KVKK uyumu zorunlu');
    }

    const introduction = text('acik-kararlar').split('\n## ')[0];
    expect(introduction).toContain('Kararlar üç türdür ve **Tür** sütununda yazılıdır');
    expect(introduction).toContain('"Öneri" sütunundaki sayılar ölçülmüş kapasite veya kabul edilmiş taahhüt değildir.');
  });

  test('revised rows retain their original ids and decision links', () => {
    // Bunlar incelemede karşılaştırılan önceki satırların bağlarıdır. CI için bir Git dalı gerekmez.
    const originalLinks: Record<string, string[]> = {
      'G-12': ['G-120'],
      'G-57': ['G-120'],
      'G-64': ['G-52'],
      'G-77': ['G-124', 'G-148', 'G-16', 'G-82', 'K-25'],
      'G-78': ['G-57'],
      'G-81': ['G-152'],
      'G-83': ['G-15'],
      'G-87': ['G-64'],
      'G-88': ['G-137'],
      'G-90': ['G-116'],
      'G-110': ['G-3'],
      'G-116': ['G-24', 'G-52'],
      'G-148': ['G-28', 'K-25'],
      'SA-41': ['G-22', 'K-13', 'SA-19', 'SA-21'],
    };
    const linksById = new Map(reqs.map((req) => [req.id, req.detail.match(/\b(?:G-|SA-|K-|X-)\d+\b/g) ?? []]));
    const missing = Object.entries(originalLinks).flatMap(([id, links]) => {
      const current = linksById.get(id);
      return current ? links.filter((link) => !current.includes(link)).map((link) => `${id} → ${link}`) : [id];
    });
    expect(missing).toEqual([]);

    const decisions = new Map(decisionRows.map((row) => [row[1], row[0]]));
    for (const [id, links] of Object.entries({ 'K-6': ['G-80', 'G-152'], 'K-8': ['G-43'], 'K-41': ['G-78', 'K-8'] })) {
      for (const link of links) expect(decisions.get(id), `${id} → ${link}`).toContain(link);
    }
  });

  test('revised approval and identity rules retain their acceptance conditions', () => {
    const requirements = new Map(reqs.map((req) => [req.id, req.detail]));
    const approval = requirements.get('G-86');
    for (const rule of [
      'approve_proposal', 'İnsan oturumu', 'fiyat sürümü', 'yeniden önizleme',
      'Otomatik zincirleme yazma yasaktır', 'silme', 'iptal', 'submit', 'toplu güncelleme',
      'ödeme', 'dış sisteme gönderim', 'tekrar gönderim', 'süresi dolan', 'değişen belge', 'başka kullanıcı',
    ]) expect(approval?.toLocaleLowerCase('tr'), `G-86: ${rule}`).toContain(rule.toLocaleLowerCase('tr'));

    const pressLogin = requirements.get('G-12');
    for (const endpoint of [
      'signup', 'send_otp', 'verify_otp', 'send_login_link', 'login_using_key',
      'reset_password', 'enable_2fa', 'verify_2fa', 'product_trial.send_verification_code_for_login',
      'Press Vue `/dashboard` yalnız iç ağa açıktır', 'Press 2FA kapalı, Keycloak MFA açık kalır',
    ]) expect(pressLogin, `G-12: ${endpoint}`).toContain(endpoint);

    for (const rule of ['K-25', 'açık', 'PKCE S256']) expect(requirements.get('G-77')).toContain(rule);
    for (const rule of ['yetki gereksinimi', 'yıkıcı', 'ücretli']) expect(requirements.get('G-84')).toContain(rule);
    for (const setting of ['enable_onboarding=0', 'disable_system_update_notification=1', 'disable_change_log_notification=1']) {
      expect(requirements.get('G-53')).toContain(setting);
    }
    expect(requirements.get('G-90')).toContain('Rail 6 ile aynı maskeleme sözlüğü');
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

  test('decision ids are unique', () => {
    const seen = new Set<string>();
    const duplicates = new Set<string>();
    for (const [, id] of decisionRows) {
      if (seen.has(id)) duplicates.add(id);
      seen.add(id);
    }
    expect([...duplicates]).toEqual([]);
  });

  test('every K decision reference has a documented decision', () => {
    const defined = new Set(decisionRows.map((row) => row[1]));
    const missing: string[] = [];
    const scan = (where: string, text: string) => {
      for (const m of text.matchAll(/\bK-(\d+)\b/g)) if (!defined.has(`K-${m[1]}`)) missing.push(`${where}: K-${m[1]}`);
    };
    for (const d of docs) scan(d.slug, d.text);
    for (const r of reqs) scan(r.id, r.detail);
    expect(missing).toEqual([]);
  });

  test('all document embeds render once without placeholders', () => {
    for (const doc of docs) {
      const names = [...doc.text.matchAll(/<div data-embed="([a-z0-9-]+)"><\/div>/g)].map((match) => match[1]);
      expect(new Set(names).size, doc.slug).toBe(names.length);
      if (names.length === 0) continue;
      const html = read(`dist/${doc.slug}/index.html`);
      expect(html, doc.slug).not.toMatch(/<[^>]*\sdata-embed=/);
      const sources = [...html.matchAll(/data-embed-source="([a-z0-9-]+)"/g)].map((match) => match[1]);
      expect(sources, doc.slug).toEqual(names);
    }
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
      [/<marka>\.com\.tr|<kiracı>\.atonota\.net/, 'eski ad: kiracı <kiracı>.app.atonota.net, marka alanı atonota.net olmalı (backend ad haritası)'],
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
