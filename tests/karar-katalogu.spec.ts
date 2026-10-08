import { readdirSync, readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

// Karar kataloğu denetimi: kullanıcının araştırma notlarından gelen kararlar (kimlik, arayüz, AI ekosistemi, kalite)
// tek katalogda, kaynak etiketli ve çelişkileri açık kararlara bağlı olmalı. Kaynaktan fazla kelime üretilmez.
// Tarayıcı gerektirmez; tek projede koşar.
const root = new URL('../', import.meta.url);
const read = (p: string) => readFileSync(new URL(p, root), 'utf8');
const body = (t: string) => t.replace(/^---[\s\S]*?---\n/, '');
const words = (t: string) => body(t).split(/\s+/).filter(Boolean).length;
const docsDir = new URL('src/content/docs/', root);
const slugs = new Set(readdirSync(docsDir).filter((f) => f.endsWith('.md')).map((f) => f.replace(/\.md$/, '')));
const doc = (slug: string) => read(`src/content/docs/${slug}.md`);

type Source = { code: string; file: string; date: string; words: number; kd: string };
const sources: { sources: Source[] } = JSON.parse(read('src/data/karar-kaynaklari.json'));
const codes = new Set(sources.sources.map((s) => s.code));

const STATUSES = ['Kesin', 'Koşullu', 'Açık', 'Çelişki'];
const PREFIXES = ['KM', 'AU', 'AI', 'KZ'];
const NEW_PAGES = ['karar-katalogu'];

type Row = { id: string; text: string; status: string; src: string[]; where: string };
function catalogRows(): Row[] {
  const rows: Row[] = [];
  for (const line of doc('karar-katalogu').split('\n')) {
    const m = line.match(/^\| ((?:KM|AU|AI|KZ)-\d{2}) \|(.*)\|$/);
    if (!m) continue;
    const cells = m[2].split('|').map((c) => c.trim());
    expect(cells.length, `${m[1]} sütun sayısı`).toBe(4);
    rows.push({ id: m[1], text: cells[0], status: cells[1], src: cells[2].split(/[,\s]+/).filter(Boolean), where: cells[3] });
  }
  return rows;
}

test.describe('karar kataloğu', () => {
  test.beforeEach(({ browserName }) => {
    test.skip(browserName !== 'chromium', 'Dosya düzeyi denetim; tek motorda koşar.');
  });

  test('source ledger lists the seven attached notes with word counts', () => {
    expect(sources.sources.map((s) => s.code).sort()).toEqual(['A1', 'A2', 'AE', 'AM', 'KC', 'KP', 'KS']);
    for (const s of sources.sources) {
      expect(s.words, s.code).toBeGreaterThan(0);
      expect(s.file, s.code).toMatch(/\.(md|zip)$/);
      expect(s.kd, s.code).toMatch(/^KD-\d+$/);
    }
    expect(new Set(sources.sources.map((s) => s.kd)).size).toBe(sources.sources.length);
  });

  test('catalog ids are unique and contiguous per domain', () => {
    const rows = catalogRows();
    expect(new Set(rows.map((r) => r.id)).size).toBe(rows.length);
    for (const p of PREFIXES) {
      const nums = rows.filter((r) => r.id.startsWith(`${p}-`)).map((r) => Number(r.id.split('-')[1])).sort((a, b) => a - b);
      expect(nums.length, `${p} serisi boş`).toBeGreaterThan(0);
      expect(nums, `${p} serisi boşluksuz`).toEqual(nums.map((_, i) => i + 1));
    }
  });

  test('every row has a status, known sources and a resolvable location', () => {
    const decisions = doc('acik-kararlar');
    const openIds = new Set([...decisions.matchAll(/^\| (K-\d+) \|/gm)].map((m) => m[1]));
    for (const r of catalogRows()) {
      expect(r.text.length, `${r.id} metni`).toBeGreaterThan(10);
      expect(STATUSES, `${r.id} durumu ${r.status}`).toContain(r.status);
      expect(r.src.length, `${r.id} kaynağı`).toBeGreaterThan(0);
      for (const c of r.src) expect(codes.has(c), `${r.id} kaynak kodu ${c}`).toBe(true);
      const link = r.where.match(/\(\/frappesetup\/([a-z0-9-]+)\/\)/);
      const kid = r.where.match(/\bK-\d+\b/);
      if (r.status === 'Çelişki' || r.status === 'Açık') {
        expect(kid, `${r.id} açık karar bağı`).not.toBeNull();
        expect(openIds.has(kid![0]), `${r.id} → ${kid![0]} açık kararlarda yok`).toBe(true);
      } else {
        expect(link, `${r.id} sayfa bağı`).not.toBeNull();
        expect(slugs.has(link![1]), `${r.id} → ${link![1]} sayfası yok`).toBe(true);
      }
    }
  });

  test('conflict decisions K-37.. exist and every one is reachable from the catalog', () => {
    const decisions = doc('acik-kararlar');
    const defined = [...decisions.matchAll(/^\| (K-(\d+)) \|/gm)].map((m) => ({ id: m[1], n: Number(m[2]) })).filter((k) => k.n >= 37);
    expect(defined.length).toBeGreaterThanOrEqual(20);
    const catalog = doc('karar-katalogu');
    for (const k of defined) expect(catalog, `${k.id} katalogda anılmıyor`).toContain(k.id);
  });

  test('catalog adopts no sub-1rem body size; such values may only appear in conflict rows', () => {
    for (const slug of NEW_PAGES) {
      const adopted = doc(slug).split('\n').filter((l) => !l.includes('| Çelişki |')).join('\n');
      expect(adopted, `${slug}: clamp(15px`).not.toContain('clamp(15px');
      expect(adopted, `${slug}: 14px gövde`).not.toMatch(/gövde[^.\n]{0,40}\b1[0-5] ?px/i);
    }
  });

  test('new pages add no more words than their sources', () => {
    const budget = sources.sources.reduce((n, s) => n + s.words, 0);
    const added = NEW_PAGES.reduce((n, slug) => n + words(doc(slug)), 0);
    expect(added, `yeni sayfalar ${added} kelime; kaynak toplamı ${budget}`).toBeLessThanOrEqual(budget);
    // Katalog özettir: kaynak toplamının beşte birini geçmez.
    for (const slug of NEW_PAGES) expect(words(doc(slug)), slug).toBeLessThanOrEqual(budget / 5);
  });

  test('source ledger rows exist in the traceability page', () => {
    const t = doc('izlenebilirlik');
    for (const s of sources.sources) {
      expect(t, `${s.kd}`).toMatch(new RegExp(`\\| ${s.kd} \\|`));
      expect(t, `${s.kd} dosya adı`).toContain(s.file.replace(/\.(md|zip)$/, ''));
    }
  });

  test('new pages are registered with section metadata', () => {
    const sections = read('src/data/sections.ts');
    for (const slug of NEW_PAGES) {
      expect(slugs.has(slug), `${slug} sayfası`).toBe(true);
      expect(sections, `${slug} meta`).toMatch(new RegExp(`['"]?${slug}['"]?: \\{`));
    }
  });
});
