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

  test('internal links point to existing pages', () => {
    const slugs = new Set(docs.map((d) => d.slug));
    const broken: string[] = [];
    for (const d of docs) {
      for (const m of d.text.matchAll(/\]\(\/frappesetup\/([^/)#]*)\/?(#[^)]*)?\)/g)) {
        if (m[1] && !slugs.has(m[1])) broken.push(`${d.slug} → ${m[1]}`);
      }
    }
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

  test('README counts match the requirement data', () => {
    const readme = read('README.md');
    const g = reqs.filter((r) => r.id.startsWith('G-')).length;
    const sa = reqs.filter((r) => r.id.startsWith('SA-')).length;
    expect(readme).toContain(`${reqs.length} numaralı gereksinim (G-1..G-${g}, SA-1..SA-${sa})`);
    expect(readme).toContain(`${docs.length} bölüm`);
  });

  test('superseded names and hosts do not reappear in pages', () => {
    const offenders: string[] = [];
    for (const d of docs) {
      if (/(?<![_\w])press\.api\.ops/.test(d.text)) offenders.push(`${d.slug}: press.api.ops`);
      if (/<kiracı>\.<marka>\.com\.tr/.test(d.text)) offenders.push(`${d.slug}: <kiracı>.<marka>.com.tr`);
      if (/panel-spa/.test(d.text) && !/K-25/.test(d.text)) offenders.push(`${d.slug}: panel-spa`);
    }
    expect(offenders).toEqual([]);
  });
});
