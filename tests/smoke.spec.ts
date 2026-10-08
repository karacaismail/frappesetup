import { test, expect, type Page } from '@playwright/test';

// Kabul: 320→360→375→390→yatay telefon→tablet→masaüstü; yatay taşma yok; metin ≥ 1rem;
// tek odak göstergesi yalnız klavye odağında; menü ve tema değişimi çalışır; diyagramlar çizilir.
const VIEWPORTS = [
  { name: '320', width: 320, height: 640 },
  { name: '360', width: 360, height: 740 },
  { name: '375', width: 375, height: 812 },
  { name: '390', width: 390, height: 844 },
  { name: 'landscape-phone', width: 844, height: 390 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1366, height: 900 },
];

const PAGES = ['', 'kararlar/', 'raylar/', 'gereksinimler/', 'yol-haritasi/', 'rail-4-keycloak/'];

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

async function minFontSizePx(page: Page) {
  // Görünür metin taşıyan HTML öğelerinin hesaplanmış yazı boyutu (SVG metni ayrı ölçeklenir).
  return page.evaluate(() => {
    let min = Infinity;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      if (!node.textContent || !node.textContent.trim()) continue;
      const el = node.parentElement;
      if (!el || el.closest('svg, script, style, noscript, template')) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      min = Math.min(min, parseFloat(cs.fontSize));
    }
    return min;
  });
}

for (const vp of VIEWPORTS) {
  test.describe(`viewport ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const path of PAGES) {
      test(`no horizontal overflow and text >= 1rem on /${path}`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator('h1')).toBeVisible();
        await noHorizontalOverflow(page);
        expect(await minFontSizePx(page)).toBeGreaterThanOrEqual(16);
      });
    }
  });
}

test.describe('shell', () => {
  test('mobile burger opens navigation and navigates', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('');
    const burger = page.getByRole('button', { name: 'Menüyü aç' });
    await expect(burger).toBeVisible();
    await burger.click();
    const link = page
      .getByRole('navigation', { name: 'Bölümler', exact: true })
      .getByRole('link', { name: 'Kararlar', exact: true });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/frappesetup\/kararlar\/$/);
    await expect(page.locator('h1')).toContainText('Sabitlenen kararlar');
  });

  test('desktop navbar lists 15 entries and marks the current page', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('raylar/');
    const nav = page.getByRole('navigation', { name: 'Bölümler', exact: true });
    await expect(nav.getByRole('link')).toHaveCount(15);
    await expect(nav.getByRole('link', { name: 'Raylar', exact: true })).toHaveAttribute('data-active', 'true');
  });

  test('color scheme toggle switches to dark and persists', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('');
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'light');
    await page.getByRole('button', { name: 'Koyu temaya geç' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
  });
});

test.describe('focus', () => {
  test('mouse click on content leaves no focus ring; keyboard Tab shows exactly one', async ({ page, browserName }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('kararlar/');
    // Fare: tabloya ve başlığa tıkla → hiçbir kapsayıcıda outline/box-shadow odak çerçevesi oluşmamalı.
    await page.locator('.prose table').first().click({ position: { x: 20, y: 20 } });
    await page.locator('h1').click();
    const ringed = await page.evaluate(() => {
      const out: string[] = [];
      for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
        const cs = getComputedStyle(el);
        const hasOutline = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0;
        if (hasOutline && el.matches(':focus-visible, :focus-within:not(:focus)')) {
          out.push(el.tagName + '.' + el.className);
        }
      }
      return out;
    });
    expect(ringed).toEqual([]);

    // Klavye: Tab → odaklanan öğede görünür tek gösterge (outline), kapsayıcılarda yok.
    // WebKit varsayılanı bağlantıları Tab sırasına almaz; Safari'deki Option+Tab karşılığı kullanılır.
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    const focus = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const cs = getComputedStyle(el);
      const ancestorsWithOutline = [] as string[];
      let p = el.parentElement;
      while (p) {
        const pcs = getComputedStyle(p);
        if (pcs.outlineStyle !== 'none' && parseFloat(pcs.outlineWidth) > 0) ancestorsWithOutline.push(p.tagName);
        p = p.parentElement;
      }
      return {
        tag: el.tagName,
        outlineStyle: cs.outlineStyle,
        outlineWidth: parseFloat(cs.outlineWidth),
        focusVisible: el.matches(':focus-visible'),
        ancestorsWithOutline,
      };
    });
    expect(focus).not.toBeNull();
    expect(focus!.focusVisible).toBe(true);
    expect(focus!.outlineStyle).not.toBe('none');
    expect(focus!.outlineWidth).toBeGreaterThan(0);
    expect(focus!.ancestorsWithOutline).toEqual([]);
  });
});

test.describe('content', () => {
  test('requirements explorer filters by priority and search', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('gereksinimler/');
    const count = page.getByTestId('req-count');
    await expect(count).toContainText('157 / 157');
    await page.getByRole('combobox', { name: 'Öncelik' }).click();
    await page.getByRole('option', { name: 'SHOULD', exact: true }).click();
    await expect(count).toContainText('18 / 157');
    await page.getByRole('textbox', { name: 'Ara' }).fill('iyzico');
    await expect(count).not.toContainText('18 / 157');
    await page.getByRole('button', { name: 'Filtreleri temizle' }).click();
    await expect(count).toContainText('157 / 157');
  });

  test('explorer works at 320px and its table scrolls inside its own container', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto('gereksinimler/');
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

  test('mermaid diagrams render as SVG on Keycloak page', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('rail-4-keycloak/');
    await expect(page.locator('figure.mermaid-figure[data-state="ok"] svg')).toHaveCount(3, { timeout: 20_000 });
  });

  test('roadmap timeline is moved next to its placeholder', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('yol-haritasi/');
    const fig = page.locator('.prose .diagram-timeline');
    await expect(fig).toHaveCount(1);
    await expect(page.locator('[data-embed]')).toHaveCount(0);
  });

  test('markdown tables keep words intact and scroll in their own box at 320px', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto('kararlar/');
    const wrap = page.locator('.prose .table-wrap').first();
    const m = await wrap.evaluate((el) => {
      const td = el.querySelector('td')!;
      return {
        overflowX: getComputedStyle(el).overflowX,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        wordBreak: getComputedStyle(td).wordBreak,
        overflowWrap: getComputedStyle(td).overflowWrap,
        tabIndex: (el as HTMLElement).tabIndex,
      };
    });
    expect(m.overflowX).toBe('auto');
    expect(m.scrollWidth).toBeGreaterThan(m.clientWidth);
    expect(m.wordBreak).toBe('normal');
    expect(m.overflowWrap).toBe('normal');
    expect(m.tabIndex).toBe(0);
    // Kaydırma sarmalayıcısına fare ile tıklamak odak çerçevesi üretmez.
    await wrap.click({ position: { x: 10, y: 10 } });
    expect(await wrap.evaluate((el) => el.matches(':focus-visible'))).toBe(false);
  });
});
