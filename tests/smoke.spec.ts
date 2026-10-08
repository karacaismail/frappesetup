import { createRequire } from 'node:module';
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const require = createRequire(import.meta.url);
const requirements: { id: string; title: string; detail: string; priority: string; owner?: string }[] =
  require('../src/data/requirements.json');

// Kabul: 320→360→375→390→yatay telefon→tablet→masaüstü; yatay taşma yok; metin ≥ 1rem (SVG dahil);
// tek odak göstergesi yalnız klavye odağında; menü, tema, gezgin, diyagramlar ve erişilebilirlik.
const VIEWPORTS = [
  { name: '320', width: 320, height: 640 },
  { name: '360', width: 360, height: 740 },
  { name: '375', width: 375, height: 812 },
  { name: '390', width: 390, height: 844 },
  { name: 'landscape-phone', width: 844, height: 390 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1366, height: 900 },
];

const ALL_PAGES = [
  '',
  'kararlar/',
  'raylar/',
  'rail-1-press/',
  'rail-2-yapilandirma/',
  'rail-2-gelistirme/',
  'rail-3-frontend/',
  'rail-4-keycloak/',
  'rail-5-ai/',
  'rail-6-operasyon/',
  'gereksinimler/',
  'admin-shell/',
  'app-cercevesi/',
  'yol-haritasi/',
  'acik-kararlar/',
];
const KEY_PAGES = ['', 'kararlar/', 'raylar/', 'gereksinimler/', 'yol-haritasi/', 'rail-4-keycloak/'];

async function noHorizontalOverflow(page: Page) {
  const r = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    bodyScroll: document.body.scrollWidth,
  }));
  expect(r.scrollWidth, `document scrollWidth ${r.scrollWidth} > clientWidth ${r.clientWidth}`).toBeLessThanOrEqual(
    r.clientWidth,
  );
  expect(r.bodyScroll).toBeLessThanOrEqual(r.clientWidth);
}

// Görünür metnin etkin yazı boyutu: HTML'de hesaplanmış font-size; SVG içinde font-size × çizim ölçeği.
async function minEffectiveFontPx(page: Page) {
  return page.evaluate(() => {
    let min = Infinity;
    let count = 0;
    let where = '';
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      if (!node.textContent || !node.textContent.trim()) continue;
      const el = node.parentElement;
      if (!el || el.closest('script, style, noscript, template, title, desc')) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      let size = parseFloat(cs.fontSize);
      const svg = el.closest('svg') as SVGSVGElement | null;
      if (svg) {
        const vb = svg.viewBox.baseVal;
        const rendered = svg.getBoundingClientRect().width;
        if (vb && vb.width > 0 && rendered > 0) size = size * (rendered / vb.width);
      }
      if (size < min) {
        min = size;
        where = `${el.tagName}.${String(el.className).slice(0, 40)} "${(el.textContent || '').trim().slice(0, 40)}"`;
      }
      count++;
    }
    return { min, count, where };
  });
}

// Tüm Astro adaları hidrasyonunu bitirene kadar bekler (ssr özniteliği hidrasyonda kalkar).
async function waitForHydration(page: Page) {
  // client:visible adalar görünür olmadan hidrate olmaz: önce görünür alana getir.
  await page.evaluate(() => {
    document.querySelectorAll('astro-island[ssr]').forEach((el) => el.scrollIntoView({ block: 'center' }));
  });
  await page.waitForFunction(() => !document.querySelector('astro-island[ssr]'), undefined, { timeout: 20_000 });
  await page.evaluate(() => window.scrollTo(0, 0));
}

// Mermaid blokları varsa çizimin bitmesini bekler (ölçümler yerleşmiş SVG üzerinde yapılır).
async function waitForMermaid(page: Page) {
  await page.waitForFunction(
    () =>
      !document.querySelector('pre > code.language-mermaid') &&
      !document.querySelector('figure.mermaid-figure:not([data-state])'),
    undefined,
    { timeout: 20_000 },
  );
}

async function expectMinFont(page: Page) {
  const { min, count, where } = await minEffectiveFontPx(page);
  expect(count).toBeGreaterThan(20);
  expect(Number.isFinite(min)).toBe(true);
  expect(min, `en küçük etkin yazı boyutu ${min}px: ${where}`).toBeGreaterThanOrEqual(15.95);
}

// Belgede görünür outline taşıyan öğeler (tek odak göstergesi kuralı için).
async function outlinedElements(page: Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .filter((el) => {
        if (el.getClientRects().length === 0) return false; // çizilmeyen (display:none) öğeler
        const cs = getComputedStyle(el);
        return cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 && cs.visibility !== 'hidden';
      })
      .map((el) => `${el.tagName}.${String(el.className).split(' ')[0]}`),
  );
}

/* ------------------------------------------------------------------ */
test.describe('viewport matrix', () => {
  for (const vp of VIEWPORTS) {
    const pages = vp.name === '320' ? ALL_PAGES : KEY_PAGES;
    test.describe(`viewport ${vp.name}`, () => {
      test.use({ viewport: { width: vp.width, height: vp.height } });
      for (const path of pages) {
        test(`no horizontal overflow and text >= 1rem on /${path}`, async ({ page }) => {
          await page.goto(path);
          await expect(page.locator('h1')).toBeVisible();
          await waitForMermaid(page);
          await noHorizontalOverflow(page);
          await expectMinFont(page);
        });
      }
    });
  }
});

test.describe('text scaling', () => {
  test('125% root font at 320px keeps layout without overflow', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.addInitScript(() => {
      document.addEventListener('DOMContentLoaded', () => {
        document.documentElement.style.fontSize = '125%';
      });
    });
    for (const path of ['kararlar/', 'gereksinimler/', '']) {
      await page.goto(path);
      await expect(page.locator('h1')).toBeVisible();
      await noHorizontalOverflow(page);
    }
  });

  test('reduced motion disables smooth scrolling', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('kararlar/');
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
  });
});

/* ------------------------------------------------------------------ */
test.describe('shell', () => {
  test('mobile burger opens navigation without overflow and navigates @touch', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('');
    await waitForHydration(page);
    const burger = page.getByRole('button', { name: 'Menüyü aç' });
    await expect(burger).toBeVisible();
    await expect(burger).toHaveAttribute('aria-expanded', 'false');
    await burger.click();
    await expect(page.getByRole('button', { name: 'Menüyü kapat' })).toHaveAttribute('aria-expanded', 'true');
    await noHorizontalOverflow(page);
    const link = page
      .getByRole('navigation', { name: 'Bölümler', exact: true })
      .getByRole('link', { name: 'Kararlar', exact: true });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/frappesetup\/kararlar\/$/);
    await expect(page.locator('h1')).toContainText('Sabitlenen kararlar');
  });

  test('desktop navbar lists 15 entries, marks the current page, skip link works', async ({ page, browserName }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('raylar/');
    await waitForHydration(page);
    const nav = page.getByRole('navigation', { name: 'Bölümler', exact: true });
    await expect(nav.getByRole('link')).toHaveCount(15);
    const current = nav.getByRole('link', { name: 'Raylar', exact: true });
    await expect(current).toHaveAttribute('data-active', 'true');
    await expect(current).toHaveAttribute('aria-current', 'page');
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    const skip = page.locator('.skip-link');
    await expect(skip).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/#icerik$/);
  });

  test('color scheme toggle switches to dark and persists', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('');
    await waitForHydration(page);
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'light');
    await page.getByTestId('color-scheme-toggle').click();
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
  });

  test('stored color scheme applies before hydration (ColorSchemeScript)', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('mantine-color-scheme-value', 'dark');
      } catch {
        /* yok say */
      }
    });
    // Adalar engellenir: yalnız <head> içindeki satır içi betik çalışır.
    await page.route('**/_astro/*.js', (route) => route.abort());
    await page.goto('kararlar/', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
  });
});

/* ------------------------------------------------------------------ */
test.describe('focus', () => {
  test('mouse never shows a ring; keyboard shows exactly one, radius unchanged', async ({ page, browserName }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('kararlar/');
    await waitForHydration(page);

    // Fare: odaklanabilir bir kontrole (tema düğmesi) ve içeriğe tıkla → hiçbir yerde outline yok.
    const toggle = page.getByTestId('color-scheme-toggle');
    const radiusBefore = await toggle.evaluate((el) => getComputedStyle(el).borderRadius);
    await toggle.click();
    await toggle.click();
    expect(await toggle.evaluate((el) => el.matches(':focus-visible'))).toBe(false);
    await page.locator('.prose .table-wrap').first().click({ position: { x: 20, y: 20 } });
    await page.locator('h1').click();
    expect(await outlinedElements(page)).toEqual([]);

    // Klavye: Tab → belgede tam olarak bir outline, odaklanan öğede; yarıçap değişmez.
    // WebKit varsayılanı bağlantıları Tab sırasına almaz; Safari'deki Option+Tab karşılığı kullanılır.
    const tab = browserName === 'webkit' ? 'Alt+Tab' : 'Tab';
    await page.keyboard.press(tab);
    let outlined = await outlinedElements(page);
    expect(outlined).toHaveLength(1);
    expect(await page.evaluate(() => document.activeElement?.matches(':focus-visible'))).toBe(true);

    await page.keyboard.press(tab);
    outlined = await outlinedElements(page);
    expect(outlined).toHaveLength(1);

    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Shift+Tab' : 'Shift+Tab');
    outlined = await outlinedElements(page);
    expect(outlined).toHaveLength(1);

    // Tema düğmesi klavyeyle odaklandığında köşe yarıçapı korunur (odak kuralı şekli değiştirmez).
    await toggle.focus();
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Shift+Tab' : 'Shift+Tab');
    await page.keyboard.press(tab);
    const focusedToggle = await toggle.evaluate((el) => ({
      focusVisible: el.matches(':focus-visible'),
      radius: getComputedStyle(el).borderRadius,
      outline: getComputedStyle(el).outlineStyle,
    }));
    expect(focusedToggle.focusVisible).toBe(true);
    expect(focusedToggle.outline).not.toBe('none');
    expect(focusedToggle.radius).toBe(radiusBefore);
  });
});

/* ------------------------------------------------------------------ */
test.describe('requirements explorer', () => {
  const shouldCount = requirements.filter((r) => r.priority === 'SHOULD').length;
  const mayCount = requirements.filter((r) => r.priority === 'MAY').length;
  const keycloakCount = requirements.filter((r) =>
    `${r.id} ${r.title} ${r.detail} ${r.owner ?? ''}`.toLocaleLowerCase('tr').includes('keycloak'),
  ).length;
  const shouldIyzico = requirements.filter(
    (r) =>
      r.priority === 'SHOULD' &&
      `${r.id} ${r.title} ${r.detail} ${r.owner ?? ''}`.toLocaleLowerCase('tr').includes('iyzico'),
  ).length;

  test('filters by priority and search with exact counts', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const count = page.getByTestId('req-count');
    await expect(count).toContainText(`${requirements.length} / ${requirements.length}`);
    await page.getByRole('combobox', { name: 'Öncelik' }).click();
    await page.getByRole('option', { name: 'SHOULD', exact: true }).click();
    await expect(count).toContainText(`${shouldCount} / ${requirements.length}`);
    await page.getByRole('textbox', { name: 'Ara' }).fill('iyzico');
    await expect(count).toContainText(`${shouldIyzico} / ${requirements.length}`);
    await page.getByRole('button', { name: 'Filtreleri temizle' }).click();
    await expect(count).toContainText(`${requirements.length} / ${requirements.length}`);
  });

  test('Select is fully keyboard operable (ArrowDown, Enter, Escape, focus return)', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const combo = page.getByRole('combobox', { name: 'Öncelik' });
    await combo.focus();
    // ArrowDown listeyi açar ve ilk seçeneği (MUST) vurgular; Enter seçer.
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('listbox')).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('req-count')).toContainText(
      `${requirements.filter((r) => r.priority === 'MUST').length} / ${requirements.length}`,
    );
    await expect(combo).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('listbox')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('listbox')).toBeHidden();
    await expect(combo).toBeFocused();
  });

  test('shows cards at 320px and priority chips filter @touch', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const cards = page.locator('.req-cards .req-card');
    await expect(cards.first()).toBeVisible();
    await expect(cards).toHaveCount(requirements.length);
    await expect(page.getByTestId('req-table')).toBeHidden();
    await page.getByRole('button', { name: new RegExp(`^MAY · ${mayCount}$`) }).click();
    await expect(cards).toHaveCount(mayCount);
    await noHorizontalOverflow(page);
  });

  test('table scrolls inside its own container at 1024px', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const table = page.getByTestId('req-table');
    await table.scrollIntoViewIfNeeded();
    await expect(table).toBeVisible();
    const sc = await page.evaluate(() => {
      const t = document.querySelector('[data-testid="req-table"]') as HTMLElement;
      let p = t.parentElement;
      while (p && getComputedStyle(p).overflowX !== 'auto' && getComputedStyle(p).overflowX !== 'scroll') p = p.parentElement;
      return p ? { scrollWidth: p.scrollWidth, clientWidth: p.clientWidth } : null;
    });
    expect(sc).not.toBeNull();
    expect(sc!.scrollWidth).toBeGreaterThan(sc!.clientWidth);
    await noHorizontalOverflow(page);
  });

  // Regresyon (rapor Y-10): ada JS'i gecikirken bir kez yazılan metin kaybolmamalı ve filtre uygulanmalı.
  // JS isteği bekletilir; yazım hidrasyondan önce tek sefer yapılır, test yazmayı yinelemez.
  test('text typed once before hydration is kept and applied (slow island JS)', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    await page.route(/\/_astro\/RequirementsExplorer\.[^/]+\.js$/, async (route) => {
      await gate;
      await route.continue();
    });
    await page.goto('gereksinimler/', { waitUntil: 'domcontentloaded' });
    const island = page.locator('astro-island[component-url*="RequirementsExplorer"]');
    const search = page.getByRole('textbox', { name: 'Ara' });
    const detail = page.getByRole('switch', { name: 'Ayrıntıları göster' });
    await expect(island).toHaveAttribute('ssr', '');
    await search.fill('Keycloak');
    await detail.uncheck();
    // Girdi anında ada hâlâ sunucu HTML'idir (React bağlı değil).
    await expect(island).toHaveAttribute('ssr', '');
    release();
    await expect(page.getByTestId('req-count')).toContainText(`${keycloakCount} / ${requirements.length}`);
    await expect(search).toHaveValue('Keycloak');
    await expect(detail).not.toBeChecked();
    await expect(page.locator('.req-detail')).toHaveCount(0);
    await expect(island).not.toHaveAttribute('ssr', '');
  });

  test('search text and focus survive orientation change', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const search = page.getByRole('textbox', { name: 'Ara' });
    const count = page.getByTestId('req-count');
    // Tek yazım: hidrasyon sırasında yazılan metni bileşen kendisi korur (yukarıdaki regresyon testi).
    await search.fill('Keycloak');
    await expect(count).toContainText(`${keycloakCount} / ${requirements.length}`);
    await page.setViewportSize({ width: 844, height: 390 });
    await expect(search).toHaveValue('Keycloak');
    await expect(count).toContainText(`${keycloakCount} / ${requirements.length}`);
    await expect(search).toBeFocused();
    await noHorizontalOverflow(page);
  });
});

/* ------------------------------------------------------------------ */
test.describe('diagrams', () => {
  test('mermaid renders 3 diagrams with accessible names and source fallback', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('rail-4-keycloak/');
    const figs = page.locator('figure.mermaid-figure[data-state="ok"]');
    await expect(figs).toHaveCount(3, { timeout: 20_000 });
    const labels = await figs.evaluateAll((els) => els.map((e) => e.getAttribute('aria-label') ?? ''));
    for (const l of labels) expect(l).toMatch(/^Akış diyagramı: .+/);
    await expect(page.locator('details.mermaid-details')).toHaveCount(3);
  });

  test('mermaid keeps natural width at 320px (text stays >= 1rem) and scrolls in its figure', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto('rail-1-press/');
    await waitForMermaid(page);
    const fig = page.locator('figure.mermaid-figure[data-state="ok"]').first();
    await expect(fig).toBeVisible({ timeout: 20_000 });
    const m = await fig.evaluate((f) => {
      const svg = f.querySelector('svg') as SVGSVGElement;
      return {
        rendered: svg.getBoundingClientRect().width,
        viewBox: svg.viewBox.baseVal.width,
        figScroll: f.scrollWidth,
        figClient: f.clientWidth,
      };
    });
    expect(m.rendered).toBeGreaterThanOrEqual(m.viewBox - 1);
    expect(m.figScroll).toBeGreaterThan(m.figClient);
    await noHorizontalOverflow(page);
    await expectMinFont(page);
  });

  test('static SVG labels stay inside the viewBox and do not collide', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('');
    const problems = await page.evaluate(() => {
      const out: string[] = [];
      for (const svg of Array.from(document.querySelectorAll<SVGSVGElement>('.diagram svg'))) {
        const vbW = svg.viewBox.baseVal.width;
        const vbH = svg.viewBox.baseVal.height;
        const texts = Array.from(svg.querySelectorAll('text'));
        const boxes = texts.map((t) => ({ t, b: t.getBBox() }));
        for (const { t, b } of boxes) {
          if (b.x < 0 || b.x + b.width > vbW + 0.5 || b.y + b.height > vbH + 0.5) {
            out.push(`overflow: "${t.textContent}" right=${(b.x + b.width).toFixed(0)}`);
          }
        }
        for (let i = 0; i < boxes.length; i++) {
          for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i].b;
            const c = boxes[j].b;
            const overlap = a.x < c.x + c.width && c.x < a.x + a.width && a.y < c.y + c.height && c.y < a.y + a.height;
            if (overlap) out.push(`collision: "${boxes[i].t.textContent}" × "${boxes[j].t.textContent}"`);
          }
        }
      }
      return out;
    });
    expect(problems).toEqual([]);
  });

  test('roadmap timeline is moved next to its placeholder', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('yol-haritasi/');
    await expect(page.locator('.prose .diagram-timeline')).toHaveCount(1);
    await expect(page.locator('[data-embed]')).toHaveCount(0);
  });
});

/* ------------------------------------------------------------------ */
test.describe('content', () => {
  test('heading anchors, TOC scroll-spy and reading progress work', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('rail-4-keycloak/');
    const anchors = page.locator('.prose h2 .heading-anchor');
    expect(await anchors.count()).toBeGreaterThan(2);
    await expect(anchors.first()).toHaveAttribute('href', /^#/);
    const bar = page.locator('#progress-bar');
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect
      .poll(async () => bar.evaluate((el) => parseFloat(getComputedStyle(el).width)))
      .toBeGreaterThan(100);
    await expect(page.locator('.toc-link[aria-current="true"]')).toHaveCount(1);
  });

  test('markdown tables scroll in a focusable wrapper and never split words at 320px', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    for (const path of ['raylar/', 'yol-haritasi/']) {
      await page.goto(path);
      const wrap = page.locator('.prose .table-wrap').first();
      const m = await wrap.evaluate((el) => {
        const cells = Array.from(el.querySelectorAll<HTMLElement>('tbody tr > :first-child'));
        const split: string[] = [];
        for (const cell of cells) {
          const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
          let node: Node | null;
          while ((node = walker.nextNode())) {
            const text = node.textContent ?? '';
            const re = /\S+/g;
            let mt: RegExpExecArray | null;
            while ((mt = re.exec(text))) {
              const range = document.createRange();
              range.setStart(node, mt.index);
              range.setEnd(node, mt.index + mt[0].length);
              const lines = new Set(Array.from(range.getClientRects()).map((r) => Math.round(r.top)));
              if (lines.size > 1) split.push(mt[0]);
            }
          }
        }
        return {
          overflowX: getComputedStyle(el).overflowX,
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
          tabIndex: (el as HTMLElement).tabIndex,
          split,
        };
      });
      expect(m.overflowX).toBe('auto');
      expect(m.scrollWidth).toBeGreaterThan(m.clientWidth);
      expect(m.tabIndex).toBe(0);
      expect(m.split, `kelime ortasından bölünen: ${m.split.join(', ')}`).toEqual([]);
      await wrap.click({ position: { x: 10, y: 10 } });
      expect(await wrap.evaluate((el) => el.matches(':focus-visible'))).toBe(false);
    }
  });
});

/* ------------------------------------------------------------------ */
test.describe('accessibility (axe)', () => {
  for (const scheme of ['light', 'dark'] as const) {
    for (const path of ['', 'gereksinimler/', 'raylar/']) {
      test(`axe ${scheme} /${path}`, async ({ page }) => {
        await page.setViewportSize({ width: 1366, height: 900 });
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto(path);
        await expect(page.locator('h1')).toBeVisible();
        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();
        const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
        expect(
          serious.map(
            (v) =>
              `${v.id}: ${v.nodes.length} × ${v.nodes[0]?.target.join(' ')} — ${v.nodes[0]?.any?.[0]?.message ?? ''}`,
          ),
        ).toEqual([]);
      });
    }
  }
});
