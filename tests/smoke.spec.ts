import { readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { gzipSync } from 'node:zlib';
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const require = createRequire(import.meta.url);
const requirements: { id: string; title: string; detail: string; priority: string; phase: string; owner?: string }[] =
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

// Sayfa listesi içerik dizininden türer: yeni bölüm eklendiğinde testler kendiliğinden kapsar.
const DOC_SLUGS = readdirSync(new URL('../src/content/docs/', import.meta.url))
  .filter((f) => f.endsWith('.md'))
  .map((f) => f.replace(/\.md$/, ''))
  .sort();
const ALL_PAGES = ['', ...DOC_SLUGS.map((slug) => `${slug}/`)];
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

// Alt sınır 1rem = tarayıcı varsayılanı (16 px) × testin kök ölçeği (%100, %125, %200). Kök boyut da denetlenir:
// site `html` yazısını küçülterek (ör. %87,5) kuralı dolaylı biçimde aşamaz.
const BROWSER_DEFAULT_PX = 16;
async function expectMinFont(page: Page, rootPct = 100) {
  const expectedRoot = (BROWSER_DEFAULT_PX * rootPct) / 100;
  const rootPx = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
  expect(rootPx, `kök yazı boyutu ${rootPx}px, beklenen ${expectedRoot}px`).toBeCloseTo(expectedRoot, 1);
  const { min, count, where } = await minEffectiveFontPx(page);
  expect(count).toBeGreaterThan(20);
  expect(Number.isFinite(min)).toBe(true);
  expect(min, `en küçük etkin yazı boyutu ${min}px (1rem = ${expectedRoot}px): ${where}`).toBeGreaterThanOrEqual(
    expectedRoot - 0.05,
  );
}

// Satır kırılımı (kalıcı kural, AGENTS.md): metin sözcük aralarından ve tarayıcının doğal fırsatlarından (tire, eğik
// çizgi, noktalama) sarılır. Zorlayıcı kural (overflow-wrap: anywhere, word-break: break-all/break-word, line-break: anywhere) yoktur; bunlar
// içsel genişliği küçültüp tablo sütununda ve esnek öğede sığan sözcüğü böler. overflow-wrap: break-word yalnız satırın
// tamamından uzun dizgide devreye giren güvenlik ağıdır.
async function forcedBreakRules(page: Page) {
  return page.evaluate(() => {
    const out = new Set<string>();
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      if (el.closest('svg')) continue;
      const cs = getComputedStyle(el);
      if (cs.overflowWrap === 'anywhere' || ['break-all', 'break-word'].includes(cs.wordBreak) || cs.lineBreak === 'anywhere') {
        out.add(`${el.tagName}.${String(el.className).split(' ')[0]}: overflow-wrap ${cs.overflowWrap}, word-break ${cs.wordBreak}, line-break ${cs.lineBreak}`);
      }
    }
    return [...out].slice(0, 10);
  });
}

// Gerçek sözcük ortası bölünme: iki satıra yayılan belirtecin kırılma noktası iki tanımlayıcı karakteri (harf, rakam,
// alt çizgi) arasındaysa ve (a) belirteç satır içi koddaysa (kod bölünmez, kendi kutusunda kayar), (b) başlık, kimlik ya
// da başlık/model adıysa (`names`: %100 yazıda; büyük yazıda satırdan uzun ad satır sonunda kırılabilir) ya da (c)
// bölünmemiş doğal genişliği satır genişliğinden en az 1 px darsa (sığan sözcük) ihlaldir. Satırdan uzun dizginin satır
// sonunda kırılması güvenlik ağıdır. Doğal genişlik aynı ebeveynde görünmez, sarılmayan bir kopyayla ölçülür: bölünmüş
// parçaların toplamı alt piksel ve kerning farkı taşır, yarım piksellik sınır durumunu sığıyor gösterebilir.
const NAME_TEXT = 'h1, h2, h3, h4, th, td:first-child, .req-id, .req-title, .req-card-title, .brand-name, .nav-link-label, .toc-link';
async function midWordSplits(page: Page, { names = true }: { names?: boolean } = {}) {
  return page.evaluate(
    ({ names, nameText }) => {
      const out: string[] = [];
      const lineWidth = (el: HTMLElement) => {
        let box: HTMLElement | null = el;
        while (box && getComputedStyle(box).display === 'inline') box = box.parentElement;
        if (!box) return Infinity;
        const cs = getComputedStyle(box);
        return box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      };
      const naturalWidth = (parent: HTMLElement, word: string) => {
        const probe = document.createElement('span');
        probe.textContent = word;
        probe.style.cssText = 'position:absolute;top:0;left:0;visibility:hidden;white-space:nowrap';
        parent.appendChild(probe);
        const width = probe.getBoundingClientRect().width;
        probe.remove();
        return width;
      };
      // Tanımlayıcı karakterleri (harf, rakam, alt çizgi) arasında doğal satır fırsatı yoktur.
      const wordChar = /[\p{L}\p{N}_]/u;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n as Text);
      for (const node of nodes) {
        if (out.length >= 10) break;
        const parent = node.parentElement;
        const text = node.textContent ?? '';
        if (!parent || !/\S/.test(text) || parent.closest('pre, svg, script, style')) continue;
        const whole = document.createRange();
        whole.selectNodeContents(node);
        const lines = new Set(Array.from(whole.getClientRects()).filter((r) => r.width > 0).map((r) => Math.round(r.top)));
        if (lines.size < 2) continue;
        const re = /\S+/g;
        let m: RegExpExecArray | null;
        while ((m = re.exec(text))) {
          const range = document.createRange();
          range.setStart(node, m.index);
          range.setEnd(node, m.index + m[0].length);
          const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0);
          if (new Set(rects.map((r) => Math.round(r.top))).size < 2) continue;
          let at = -1;
          let prev: number | null = null;
          for (let i = 0; i < m[0].length; i++) {
            const c = document.createRange();
            c.setStart(node, m.index + i);
            c.setEnd(node, m.index + i + 1);
            const r = c.getClientRects()[0];
            if (!r || r.width === 0) continue;
            const top = Math.round(r.top);
            if (prev !== null && top > prev + 2) {
              at = i;
              break;
            }
            prev = top;
          }
          if (at <= 0 || !wordChar.test(m[0][at - 1]) || !wordChar.test(m[0][at])) continue;
          const inCode = Boolean(parent.closest('code'));
          const isName = names && Boolean(parent.closest(nameText));
          const line = lineWidth(parent);
          const natural = naturalWidth(parent, m[0]);
          if (inCode || isName || natural <= line - 1) {
            const where = `${parent.tagName}.${String(parent.className).split(' ')[0]}`;
            const why = inCode ? 'kod' : isName ? 'ad' : 'sığan sözcük';
            out.push(`${where} "${m[0].slice(0, 40)}" ${at}. karakterde (${why}; doğal ${natural.toFixed(1)} / satır ${line.toFixed(1)} px)`);
          }
        }
      }
      return out;
    },
    { names, nameText: NAME_TEXT },
  );
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
          // Ayrıştırılamayan diyagram (ör. mesajda ';') hata çıktısıyla yayımlanmaz.
          await expect(page.locator('figure.mermaid-figure[data-state="error"]'), 'Mermaid ayrıştırma hatası').toHaveCount(0);
          await noHorizontalOverflow(page);
          await expectMinFont(page);
          expect(await forcedBreakRules(page), 'zorlayıcı satır kırma kuralı').toEqual([]);
          expect(await midWordSplits(page), 'sözcük ortasından bölünme').toEqual([]);
        });
      }
    });
  }
});

test.describe('text scaling', () => {
  // Kullanıcının kök yazı boyutu (tarayıcı ayarı) büyüdüğünde: taşma yok, tüm metin yeni 1rem'in altına inmez.
  const SCALES = [
    { root: 125, viewport: { width: 320, height: 640 } },
    { root: 200, viewport: { width: 390, height: 844 } },
    { root: 200, viewport: { width: 1366, height: 900 } },
  ];
  for (const { root, viewport } of SCALES) {
    test(`${root}% root font at ${viewport.width}px keeps layout and text >= 1rem`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.addInitScript((pct) => {
        document.addEventListener('DOMContentLoaded', () => {
          document.documentElement.style.fontSize = `${pct}%`;
        });
      }, root);
      for (const path of ['', 'kararlar/', 'gereksinimler/', 'yol-haritasi/', 'rail-4-keycloak/']) {
        await page.goto(path);
        await expect(page.locator('h1')).toBeVisible();
        await waitForMermaid(page);
        await noHorizontalOverflow(page);
        await expectMinFont(page, root);
        // Büyük yazıda satırdan uzun sözcük ya da ad satır sonunda kırılabilir (güvenlik ağı); satırına sığan sözcük bölünmez.
        expect(await midWordSplits(page, { names: false }), 'sözcük ortasından bölünme').toEqual([]);
        // Sabit başlık çubuğu scrollWidth'e yansımaz: eylem düğmesi görünür alanda kalmalı (işlev kaybı yok).
        const toggle = await page.getByTestId('color-scheme-toggle').boundingBox();
        expect(toggle, 'tema düğmesi çizilmeli').not.toBeNull();
        expect(toggle!.x + toggle!.width, 'tema düğmesi görünür alanda').toBeLessThanOrEqual(viewport.width);
      }
    });
  }

  test('reduced motion disables smooth scrolling', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('kararlar/');
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
  });
});

/* ------------------------------------------------------------------ */
test.describe('shell', () => {
  test.describe('narrow header', () => {
    test.use({ viewport: { width: 320, height: 640 } });
    test('brand name and header actions fit at 320 px with fine and coarse pointers @touch', async ({ page }) => {
      await page.goto('');
      await waitForHydration(page);
      const name = await page.locator('.brand-name').evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
      expect(name.scroll, 'marka adı kısalmaz').toBeLessThanOrEqual(name.client);
      for (const sel of ['.burger', '.header-end .icon-btn[href]', '[data-testid="color-scheme-toggle"]']) {
        const b = await page.locator(sel).boundingBox();
        expect(b, sel).not.toBeNull();
        expect(b!.x, `${sel} görünür alanda`).toBeGreaterThanOrEqual(0);
        expect(b!.x + b!.width, `${sel} görünür alanda`).toBeLessThanOrEqual(320);
      }
      // Menü simgesi kendi etkili alanında ortalanır.
      const offset = await page.locator('.burger').evaluate((el) => {
        const r = el.getBoundingClientRect();
        const g = el.querySelector('.mantine-Burger-burger')!.getBoundingClientRect();
        return Math.abs(r.left + r.width / 2 - (g.left + g.width / 2));
      });
      expect(offset, 'menü simgesi ortada').toBeLessThanOrEqual(1);
    });
  });

  test('active section link is scrolled into view in the navigation list', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 700 });
    for (const path of ['izlenebilirlik/', 'gereksinimler/', '']) {
      await page.goto(path);
      await waitForHydration(page);
      const inside = await page.evaluate(() => {
        const nav = document.querySelector('.nav-scroll')!.getBoundingClientRect();
        const a = document.querySelector('.nav-link[data-active]')!.getBoundingClientRect();
        return a.top >= nav.top - 1 && a.bottom <= nav.bottom + 1;
      });
      expect(inside, `/${path}: etkin bağlantı gezinme listesinde görünür`).toBe(true);
    }
  });

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

  test('desktop navbar lists every section, marks the current page, skip link works', async ({ page, browserName }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('raylar/');
    await waitForHydration(page);
    const nav = page.getByRole('navigation', { name: 'Bölümler', exact: true });
    // Kapalı AI grubunun bağlantıları da DOM'dadır (hidden); varsayılan rol sorgusu bunları saymaz.
    await expect(nav.getByRole('link', { includeHidden: true })).toHaveCount(ALL_PAGES.length);
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

  test('color scheme toggle follows a dark OS preference when nothing is stored', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('');
    await waitForHydration(page);
    const html = page.locator('html');
    await expect(html).toHaveAttribute('data-mantine-color-scheme', 'dark');
    // 'auto' tercihte düğme gerçek şemaya göre adlanır; tek tıklama açık temaya geçirir.
    const toggle = page.getByTestId('color-scheme-toggle');
    await expect(toggle).toHaveAccessibleName('Açık temaya geç');
    await toggle.click();
    await expect(html).toHaveAttribute('data-mantine-color-scheme', 'light');
    await expect(toggle).toHaveAccessibleName('Koyu temaya geç');
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

// Çerçeve üreten hesaplanmış stiller (outline, box-shadow, kenarlık), belge sırasıyla. Ölçüm ve karşılaştırma sayfada
// yapılır: her Tab adımında Node'a yalnız sonuç (değişen çerçeveler, çizili göstergeler) döner, büyük DOM listesi taşınmaz.
// outline-style 'none' ise genişlik/renk görünmez olduğundan 'none' sayılır (WebKit odak kaybında bu değerleri farklı
// raporlar); saydam outline (ör. Mantine Burger çizgisinin yüksek kontrast modu için taşıdığı) gösterge sayılmaz.
type FrameProbe = {
  __fsCollect: () => { tag: string; outline: string; frame: string; focused: boolean; proxy: boolean; opaque: boolean }[];
  __fsBase: ReturnType<FrameProbe['__fsCollect']>;
};
async function installFrameProbe(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as FrameProbe;
    w.__fsCollect = () => {
      const active = document.activeElement as HTMLElement | null;
      // Görsel vekil: odaklanan kontrol görünmezse (Switch'in opacity 0 input'u) göstergeyi aynı kapsayıcıdaki kardeş çizer.
      const activeHidden = active ? getComputedStyle(active).opacity === '0' : false;
      return Array.from(document.querySelectorAll<HTMLElement>('body *')).map((el) => {
        const cs = getComputedStyle(el);
        const transparent = cs.outlineColor === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(cs.outlineColor);
        const drawn = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 && !transparent;
        return {
          tag: `${el.tagName}.${String(el.className).split(' ')[0]}`,
          outline: drawn ? `${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}` : 'none',
          frame: [
            cs.boxShadow,
            cs.borderTopColor,
            cs.borderRightColor,
            cs.borderBottomColor,
            cs.borderLeftColor,
            cs.borderTopWidth,
            cs.borderBottomWidth,
          ].join(' | '),
          focused: el === active,
          proxy: Boolean(active && activeHidden && el !== active && active.parentElement?.contains(el)),
          opaque: cs.opacity !== '0' && el.getClientRects().length > 0,
        };
      });
    };
    w.__fsBase = w.__fsCollect();
  });
}
// Karşılaştırma tabanını yeniler (ör. açılan bölümden sonra).
async function frameBaseline(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as FrameProbe;
    w.__fsBase = w.__fsCollect();
  });
}
async function frameStep(page: Page) {
  return page.evaluate(() => {
    const w = window as unknown as FrameProbe;
    const now = w.__fsCollect();
    const base = w.__fsBase;
    return {
      sameLength: now.length === base.length,
      secondFrames: now.filter((s, j) => base[j] && s.frame !== base[j].frame).map((s) => s.tag),
      focused: now.find((s) => s.focused)?.tag ?? null,
      drawn: now.filter((s) => s.opaque && s.outline !== 'none').map(({ tag, focused, proxy }) => ({ tag, focused, proxy })),
    };
  });
}

/* ------------------------------------------------------------------ */
test.describe('AI nav group', () => {
  test('wrapper is collapsed elsewhere, open on AI pages, keyboard operable', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('kararlar/');
    await waitForHydration(page);
    const wrapper = page.getByTestId('nav-wrapper-ai');
    const links = page.locator('#site-nav a[href*="/ai-"]');
    await expect(wrapper).toBeVisible();
    await expect(links.first()).toBeHidden();
    await wrapper.focus();
    await page.keyboard.press('Enter');
    await expect(links).toHaveCount(6);
    await expect(links.first()).toBeVisible();

    await page.goto('ai-mcp/');
    await waitForHydration(page);
    await expect(links).toHaveCount(6);
    await expect(page.locator('#site-nav a[aria-current="page"]')).toHaveText(/MCP sunucuları/);
  });
});

/* ------------------------------------------------------------------ */
test.describe('focus', () => {
  // Klavye odağı yalnız odaklanan öğenin outline'ını değiştirir: box-shadow/kenarlık ikinci çerçeve
  // üretmez, başka hiçbir öğe (kapsayıcı, satır, bölüm) değişmez. Gezgindeki metin kutusuna kadar Tab.
  test('keyboard focus adds only one outline; border and box-shadow never form a second frame', async ({
    page,
    browserName,
  }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    await page.mouse.move(1, 1);
    const tab = browserName === 'webkit' ? 'Alt+Tab' : 'Tab';
    const seen = new Set<string>();
    // Bir Tab adımı: kenarlık/gölge hiçbir öğede değişmez; görünür gösterge tam bir tanedir ve odaklanan öğede ya da
    // görünmez kontrolün görsel vekilindedir (Switch girdisi opaklık 0, gösterge izde).
    const step = async () => {
      await page.keyboard.press(tab);
      const r = await frameStep(page);
      expect(r.sameLength, 'öğe sayısı değişmez').toBe(true);
      expect(r.focused, 'odaklanan öğe yok').toBeTruthy();
      seen.add(r.focused!);
      expect(r.secondFrames, `odakta ikinci çerçeve (kenarlık/gölge): ${r.focused}`).toEqual([]);
      // Belgenin tamamında çizili gösterge tam bir tanedir: önceki öğede takılı kalan outline da yakalanır.
      for (const d of r.drawn) expect(d.focused || d.proxy, `odak dışı öğede gösterge: ${d.tag}`).toBe(true);
      expect(r.drawn.length, `tek görünür odak göstergesi: ${r.focused}`).toBe(1);
      return { indicator: r.drawn[0], tag: r.focused! };
    };
    const isActive = (selector: string) => page.locator(selector).evaluate((el) => el === document.activeElement);

    // 1) Öncelik düğmeleri ve metin kutusundan süzgeç bölümünün özetine kadar.
    await installFrameProbe(page);
    for (let i = 0; i < 60 && !(await isActive('.req-more > summary')); i++) await step();
    expect(await isActive('.req-more > summary')).toBe(true);
    expect([...seen].some((t) => t.startsWith('INPUT')), `metin kutusuna ulaşılmadı: ${[...seen].join(', ')}`).toBe(true);

    // 2) Özet Enter ile açılır; içindeki süzgeç düğmeleri ve ayrıntı anahtarı aynı kurala tabidir.
    await page.keyboard.press('Enter');
    await expect(page.locator('.req-more')).toHaveAttribute('open', '');
    await frameBaseline(page);
    const switchInput = '.req-explorer input[role="switch"]';
    let switchIndicator: { proxy: boolean } | undefined;
    let facetButtons = 0;
    for (let i = 0; i < 60; i++) {
      const { indicator, tag } = await step();
      if (tag.startsWith('BUTTON')) facetButtons++;
      if (await isActive(switchInput)) {
        switchIndicator = indicator;
        break;
      }
    }
    expect(facetButtons, 'açılan bölümdeki süzgeç düğmeleri Tab sırasında').toBeGreaterThan(0);
    expect(switchIndicator, 'Tab ayrıntı anahtarına ulaşmadı').toBeTruthy();
    expect(switchIndicator!.proxy, 'anahtarın göstergesi izde (görsel vekil) çizilir').toBe(true);
  });

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
// Etkili dokunma alanı (AGENTS.md, --fs-hit): tek başına duran kontrol ince işaretçide ≥ 44, kaba işaretçi varsa ≥ 48
// CSS px. Metin içi bağlantılar politikanın açık istisnasıdır ve ölçülmez. Görünmeyen (kapalı panel) öğeler atlanır.
const STANDALONE_CONTROLS = [
  '.skip-link',
  '.icon-btn',
  '.burger',
  '.brand',
  '.nav-link',
  '.toc-link',
  '.pager-link',
  '.footer-link',
  '.btn',
  '.more',
  '.rail',
  '.section-card',
  '.req-explorer .mantine-Button-root',
  '.req-more > summary',
  '.req-explorer .mantine-Switch-body',
  '.req-explorer .mantine-Input-input',
  'details.mermaid-details > summary',
].join(', ');

async function hitAreas(page: Page) {
  return page.evaluate((sel) => {
    const coarse = matchMedia('(any-pointer: coarse)').matches;
    const rows = Array.from(document.querySelectorAll<HTMLElement>(sel))
      .filter((el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')
      .map((el) => {
        const r = el.getBoundingClientRect();
        const name = `${el.tagName}.${String(el.className).split(' ')[0]} "${(el.textContent || '').trim().slice(0, 24)}"`;
        return { name, w: r.width, h: r.height };
      });
    return { coarse, rows };
  }, STANDALONE_CONTROLS);
}

async function expectHitAreas(page: Page, expectCoarse: boolean) {
  const { coarse, rows } = await hitAreas(page);
  expect(coarse, 'any-pointer: coarse profili').toBe(expectCoarse);
  const min = coarse ? 48 : 44;
  expect(rows.length, 'ölçülen kontrol sayısı').toBeGreaterThan(3);
  const small = rows.filter((r) => r.w < min - 0.5 || r.h < min - 0.5).map((r) => `${r.name} ${r.w.toFixed(0)}×${r.h.toFixed(0)}`);
  expect(small, `etkili alan < ${min} CSS px`).toEqual([]);
}

test.describe('touch targets', () => {
  test('standalone controls keep a 44 px hit area with a fine pointer', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    for (const path of ['', 'kararlar/', 'rail-4-keycloak/', 'gereksinimler/']) {
      await page.goto(path);
      await waitForHydration(page);
      await waitForMermaid(page);
      if (path === 'gereksinimler/') await page.locator('.req-more > summary').click();
      await expectHitAreas(page, false);
    }
  });

  test('standalone controls keep a 48 px hit area with a coarse pointer @touch', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Kaba işaretçi profili (iPhone 13) gerekir; ince işaretçi 44 px testinde.');
    await page.goto('');
    await waitForHydration(page);
    await expectHitAreas(page, true);
    await page.getByRole('button', { name: 'Menüyü aç' }).tap();
    await expect(page.locator('.nav-link').first()).toBeVisible();
    await expectHitAreas(page, true);
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    await page.locator('.req-more > summary').tap();
    await expectHitAreas(page, true);
  });
});

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
    // Erken girdi yokken hidrasyon varsayılanı değiştirmez: ayrıntılar açık kalır.
    await expect(page.getByRole('switch', { name: 'Ayrıntıları göster' })).toBeChecked();
    await expect(page.locator('.req-detail').first()).toBeVisible();
    await page.getByRole('button', { name: new RegExp(`^SHOULD · ${shouldCount}$`) }).click();
    await expect(count).toContainText(`${shouldCount} / ${requirements.length}`);
    await page.getByRole('textbox', { name: 'Ara' }).fill('iyzico');
    await expect(count).toContainText(`${shouldIyzico} / ${requirements.length}`);
    await page.getByRole('button', { name: 'Filtreleri temizle' }).click();
    await expect(count).toContainText(`${requirements.length} / ${requirements.length}`);
  });

  test('facet filters are keyboard operable toggle groups (no dropdown code)', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const count = page.getByTestId('req-count');
    const summary = page.locator('.req-more > summary');
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.req-more')).toHaveAttribute('open', '');
    const p1 = requirements.filter((r) => r.phase === 'P1').length;
    const phaseGroup = page.getByRole('group', { name: 'Faz' });
    const p1Button = phaseGroup.getByRole('button', { name: new RegExp(`^P1 · ${p1}$`) });
    await p1Button.focus();
    await page.keyboard.press('Space');
    await expect(p1Button).toHaveAttribute('aria-pressed', 'true');
    await expect(count).toContainText(`${p1} / ${requirements.length}`);
    await expect(summary).toContainText('1 etkin');
    await page.keyboard.press('Enter');
    await expect(p1Button).toHaveAttribute('aria-pressed', 'false');
    await expect(count).toContainText(`${requirements.length} / ${requirements.length}`);
    // Açılır liste yok: combobox/listbox rolü ve floating-ui portalı sayfada bulunmaz.
    await expect(page.getByRole('combobox')).toHaveCount(0);
    await expect(page.getByRole('listbox')).toHaveCount(0);
  });

  test('titles and details keep every character in table and cards', async ({ page }) => {
    // Metin işlenmez: gezgin yalnız `kod` parçalarını <code> yapar; satır fırsatı eklenmez (<wbr>, U+200B, U+00AD yok).
    const strip = (t: string) => t.replace(/`/g, '');
    const titles = requirements.map((r) => r.title).sort();
    const details = requirements.map((r) => strip(r.detail)).sort();
    for (const v of [
      { width: 1366, title: '.req-table .req-title', detail: '.req-table .req-detail' },
      { width: 390, title: '.req-card-title', detail: '.req-card-detail' },
    ]) {
      await page.setViewportSize({ width: v.width, height: 900 });
      await page.goto('gereksinimler/');
      await waitForHydration(page);
      const got = await page.evaluate(
        ({ t, d }) => ({
          titles: Array.from(document.querySelectorAll(t)).map((el) => el.textContent ?? ''),
          details: Array.from(document.querySelectorAll(d)).map((el) => el.textContent ?? ''),
          inserted: document.querySelectorAll('main wbr').length + ((document.querySelector('main')?.textContent ?? '').match(/[\u200b\u00ad]/g) ?? []).length,
        }),
        { t: v.title, d: v.detail },
      );
      expect(got.titles.sort(), `${v.width}px başlıklar`).toEqual(titles);
      expect(got.details.sort(), `${v.width}px ayrıntılar`).toEqual(details);
      expect(got.inserted, `${v.width}px eklenmiş satır fırsatı`).toBe(0);
    }
  });

  test('requirements table keeps six columns and scrolls only inside its own container', async ({ page }) => {
    // 1280 ve 1366 px'te altı sütun kapsayıcıya sığar (uzun kod ayrıntı hücresinde kendi kutusunda kayar, sütunu
    // genişletmez); daha dar kapsayıcıda tablo kendi kapsayıcısında kayar, sayfa yatay taşmaz.
    for (const width of [1024, 1280, 1366]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('gereksinimler/');
      await waitForHydration(page);
      const region = page.getByRole('region', { name: 'Gereksinim tablosu (yatay kaydırılabilir)' });
      await expect(region.locator('thead th')).toHaveCount(6);
      expect(await region.evaluate((el) => getComputedStyle(el).overflowX)).toBe('auto');
      if (width >= 1280) {
        const m = await region.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
        expect(m.scroll, `${width}px: tablo kapsayıcısına sığar`).toBeLessThanOrEqual(m.client);
      }
      await noHorizontalOverflow(page);
    }
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
  // JS isteği bekletilir; yazım hidrasyondan önce tek sefer yapılır, test yazmayı yinelemez. Sayaç kesin metinle
  // eşleşir (alt dizgi değil): süzülmemiş "N / N" metni hiçbir veri durumunda kabul edilmez.
  const exactCount = (n: number) => new RegExp(`^${n} / ${requirements.length} gereksinim$`);
  for (const vp of [
    { name: 'desktop', width: 1366, height: 900, detailSelector: '.req-detail', tag: '' },
    { name: '320', width: 320, height: 640, detailSelector: '.req-card-detail', tag: ' @touch' },
  ]) {
    test(`text typed once before hydration is kept and applied at ${vp.name} (slow island JS)${vp.tag}`, async ({ page }) => {
      expect(keycloakCount).toBeGreaterThan(0);
      expect(keycloakCount).toBeLessThan(requirements.length);
      await page.setViewportSize({ width: vp.width, height: vp.height });
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
      await expect(page.locator(vp.detailSelector).first()).toBeVisible();
      await search.fill('Keycloak');
      await detail.uncheck();
      // Girdi anında ada hâlâ sunucu HTML'idir (React bağlı değil).
      await expect(island).toHaveAttribute('ssr', '');
      release();
      await expect(page.getByTestId('req-count')).toHaveText(exactCount(keycloakCount));
      await expect(search).toHaveValue('Keycloak');
      await expect(detail).not.toBeChecked();
      await expect(page.locator('.req-detail, .req-card-detail')).toHaveCount(0);
      await expect(island).not.toHaveAttribute('ssr', '');
    });
  }

  test('search text and focus survive orientation change', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    const search = page.getByRole('textbox', { name: 'Ara' });
    const count = page.getByTestId('req-count');
    // Tek yazım: hidrasyon sırasında yazılan metni bileşen kendisi korur (yukarıdaki regresyon testi).
    await search.fill('Keycloak');
    await expect(count).toHaveText(exactCount(keycloakCount));
    await page.setViewportSize({ width: 844, height: 390 });
    await expect(search).toHaveValue('Keycloak');
    await expect(count).toHaveText(exactCount(keycloakCount));
    await expect(search).toBeFocused();
    await noHorizontalOverflow(page);
  });
});

/* ------------------------------------------------------------------ */
// Uzun satır içi kod bölünmez; satırdan uzunsa kendi kutusunda kayar (global.css). Yalnız gerçekten taşan kutu Tab
// sırasındadır (sayfa betiği; WebKit taşan kutuyu kendiliğinden odaklamaz), ok tuşuyla kayar, sığınca sıradan çıkar.
const INLINE_CODE = '.prose :not(pre, a) > code, .req-code';
async function codeBoxes(page: Page) {
  return page.evaluate((sel) =>
    Array.from(document.querySelectorAll<HTMLElement>(sel))
      .filter((c) => c.getClientRects().length > 0)
      .map((c) => {
        // Yalnız kaydırma kutusu taşabilir: satır içi (display: inline) kod kutu değildir (Firefox satır içi öğede de
        // scrollWidth raporlar); taşma, kaydırılabilecek en az bir piksel demektir.
        const cs = getComputedStyle(c);
        const box = cs.display !== 'inline' && ['auto', 'scroll'].includes(cs.overflowX);
        return { overflows: box && c.scrollWidth > c.clientWidth, tabbable: c.getAttribute('tabindex') === '0' };
      }),
  INLINE_CODE);
}
const mismatched = async (page: Page) => (await codeBoxes(page)).filter((c) => c.overflows !== c.tabbable).length;
// Satır içi kod ve kaydırma kutusu, satır kutusunun içerik sağ kenarını aşmaz (yarım piksel tolerans).
async function codeOutsideLine(page: Page) {
  return page.evaluate((sel) => {
    const out: string[] = [];
    for (const c of Array.from(document.querySelectorAll<HTMLElement>(sel)).filter((c) => c.getClientRects().length > 0)) {
      let box = c.parentElement!;
      while (box.parentElement && getComputedStyle(box).display === 'inline') box = box.parentElement;
      const cs = getComputedStyle(box);
      const right = box.getBoundingClientRect().right - parseFloat(cs.borderRightWidth) - parseFloat(cs.paddingRight);
      for (const r of Array.from(c.getClientRects())) if (r.right > right + 0.5) out.push(`${(c.textContent ?? '').slice(0, 30)} ${Math.round(r.right - right)} px`);
    }
    return out.slice(0, 5);
  }, INLINE_CODE);
}

test.describe('long inline code', () => {
  test('scrolls in its own box, is keyboard reachable while it overflows and leaves the tab order when it fits', async ({
    page,
    browserName,
  }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto('rail-6-operasyon/');
    await expect(page.locator('h1')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect.poll(async () => (await codeBoxes(page)).filter((c) => c.overflows).length, 'taşan kod kutusu').toBeGreaterThan(0);
    await expect.poll(() => mismatched(page), 'yalnız taşan kod Tab sırasında').toBe(0);
    await noHorizontalOverflow(page);

    // Klavye: Tab sırasında hedeften önceki öğeden tek Tab ile ilk taşan koda gelinir; ok tuşu kutuyu kaydırır.
    const hasPrev = await page.evaluate((sel) => {
      const target = Array.from(document.querySelectorAll<HTMLElement>(sel)).find((c) => c.getAttribute('tabindex') === '0')!;
      target.setAttribute('data-test-code', '');
      const order = Array.from(
        document.querySelectorAll<HTMLElement>('main a[href], main button, main input, main summary, main [tabindex="0"]'),
      ).filter((el) => el.getClientRects().length > 0);
      const prev = order[order.indexOf(target) - 1];
      prev?.setAttribute('data-test-prev', '');
      return Boolean(prev);
    }, INLINE_CODE);
    await page.locator(hasPrev ? '[data-test-prev]' : '#icerik').focus();
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    const code = page.locator('[data-test-code]');
    await expect(code).toBeFocused();
    expect(await code.evaluate((el) => el.matches(':focus-visible') && getComputedStyle(el).outlineStyle !== 'none')).toBe(true);
    // WebKit odak değişiminden sonraki ilk ok tuşunu kaydırmaya kullanmaz ve kaydırmayı canlandırır: her basıştan sonra
    // sonuç 1 sn'ye kadar beklenir, en çok üç basış.
    const scrolled = async () => {
      for (let t = 0; t < 10; t++) {
        if ((await code.evaluate((el) => el.scrollLeft)) > 0) return true;
        await page.waitForTimeout(100);
      }
      return false;
    };
    let moved = false;
    for (let i = 0; i < 3 && !moved; i++) {
      await page.keyboard.press('ArrowRight');
      moved = await scrolled();
    }
    expect(moved, 'ok tuşu kod kutusunu kaydırır').toBe(true);
    expect(await page.evaluate(() => window.scrollX), 'sayfa yatay kaymaz').toBe(0);

    // Satır içi kod ve kaydırma kutusu satır kutusunun içerik kenarını aşmaz.
    expect(await codeOutsideLine(page), 'kod satır kutusunu aşmaz').toEqual([]);

    // Geniş ekranda aynı kod sığar: odaktayken odak kaybolmaz; odak ayrılınca Tab sırasından çıkar.
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.waitForTimeout(300);
    await expect(code, '1366 px: odaktaki kod kutusu odakta kalır').toBeFocused();
    await page.locator('#icerik').focus();
    await expect.poll(() => mismatched(page), '1366 px: yalnız taşan kod Tab sırasında').toBe(0);
    await expect.poll(() => code.evaluate((el) => el.hasAttribute('tabindex')), '1366 px: sığan kod Tab sırasında değil').toBe(false);
  });

  test('requirement card code stays keyboard reachable after filtering re-renders the cards', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto('gereksinimler/');
    await waitForHydration(page);
    await page.evaluate(() => document.fonts.ready);
    await expect.poll(async () => (await codeBoxes(page)).filter((c) => c.overflows).length).toBeGreaterThan(0);
    await expect.poll(() => mismatched(page)).toBe(0);
    await page.getByRole('textbox', { name: 'Ara' }).fill('press');
    await expect.poll(() => mismatched(page), 'süzme sonrası yalnız taşan kod Tab sırasında').toBe(0);
    expect(await codeOutsideLine(page), 'kart kodu satır kutusunu aşmaz').toEqual([]);
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
        // Hale kopyaları (.halo) dolgu metninin altındaki çizimdir, ayrı etiket sayılmaz.
        const texts = Array.from(svg.querySelectorAll('text:not(.halo)'));
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
      await page.evaluate(() => document.fonts.ready);
      const wrap = page.locator('.prose .table-wrap').first();
      const m = await wrap.evaluate((el) => ({
        overflowX: getComputedStyle(el).overflowX,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        tabIndex: (el as HTMLElement).tabIndex,
      }));
      expect(m.overflowX).toBe('auto');
      expect(m.scrollWidth).toBeGreaterThan(m.clientWidth);
      expect(m.tabIndex).toBe(0);
      // İlk sütun ad sayılır: sözcük yalnız doğal fırsatta (boşluk, tire, eğik çizgi) sarılır, iki harf/rakam arasında
      // hiçbir genişlikte bölünmez (midWordSplits `names`).
      expect(await midWordSplits(page), `/${path}: sözcük ortasından bölünme`).toEqual([]);
      await wrap.click({ position: { x: 10, y: 10 } });
      expect(await wrap.evaluate((el) => el.matches(':focus-visible'))).toBe(false);
    }
  });
});

/* ------------------------------------------------------------------ */
test.describe('accessibility (axe)', () => {
  // Kapı: WCAG 2.0/2.1/2.2 A ve AA kuralları + axe best-practice; HER etki düzeyi (minor dahil) başarısızlıktır.
  // Bu, otomatik kuralların kapsadığı kadarını kanıtlar; tam WCAG AA uyumu iddiası değildir (elle denetim ayrı).
  for (const scheme of ['light', 'dark'] as const) {
    for (const path of ALL_PAGES) {
      test(`axe ${scheme} /${path}`, async ({ page }) => {
        await page.setViewportSize({ width: 1366, height: 900 });
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto(path);
        await expect(page.locator('h1')).toBeVisible();
        await waitForMermaid(page);
        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
          .analyze();
        expect(
          results.violations.map(
            (v) =>
              `${v.impact} ${v.id}: ${v.nodes.length} × ${v.nodes[0]?.target.join(' ')} — ${v.nodes[0]?.any?.[0]?.message ?? ''}`,
          ),
        ).toEqual([]);
      });
    }
  }
});

/* ------------------------------------------------------------------ */
// Ağ bütçesi (AGENTS.md tablosu): her rota gerçekten indirdiği varlıklarla ölçülür; gzip boyutu `gzip -c` ile
// aynı yöntemle (zlib, varsayılan düzey) hesaplanır. Koşullu yükleme de burada kanıtlanır.
test.describe('network budget', () => {
  type Asset = { url: string; kind: string; gz: number };
  async function load(page: Page, path: string): Promise<Asset[]> {
    const assets: Asset[] = [];
    const pending: Promise<void>[] = [];
    // Dinleyici yalnız bu yükleme süresince açıktır: sonraki sayfaların istekleri bu listeye karışmaz.
    const onResponse = (res: import('@playwright/test').Response) => {
      const url = res.url();
      if (!url.includes('/frappesetup/') || res.status() !== 200) return;
      pending.push(
        res
          .body()
          .then((body) => {
            const kind = url.endsWith('.js')
              ? 'js'
              : url.endsWith('.css')
                ? 'css'
                : /\.woff2?$/.test(url)
                  ? 'font'
                  : res.request().resourceType() === 'document'
                    ? 'html'
                    : 'other';
            // Yazı tipleri zaten sıkıştırılmıştır: aktarılan bayt olarak sayılır.
            assets.push({ url, kind, gz: kind === 'font' ? body.length : gzipSync(body).length });
          })
          .catch(() => undefined),
      );
    };
    // Yarıda kalan istek ölçümü eksik bırakır: aynı origin'de başarısız istek testi düşürür.
    const failed: string[] = [];
    const onFailed = (req: import('@playwright/test').Request) => {
      if (req.url().includes('/frappesetup/')) failed.push(`${req.url()} ${req.failure()?.errorText ?? ''}`);
    };
    page.on('response', onResponse);
    page.on('requestfailed', onFailed);
    try {
      await page.goto(path, { waitUntil: 'networkidle' });
      await waitForHydration(page);
      await waitForMermaid(page);
      await page.waitForLoadState('networkidle');
      await Promise.all(pending);
    } finally {
      page.off('response', onResponse);
      page.off('requestfailed', onFailed);
    }
    expect(failed, `yarıda kalan istek: /${path}`).toEqual([]);
    return assets;
  }
  const kb = (assets: Asset[], kind: string, filter: (a: Asset) => boolean = () => true) =>
    assets.filter((a) => a.kind === kind && filter(a)).reduce((sum, a) => sum + a.gz, 0) / 1024;
  const isMermaid = (a: Asset) => /mermaid|cytoscape|dagre|katex|elk|d3/i.test(a.url.split('/').pop() ?? '');
  const isExplorer = (a: Asset) => /RequirementsExplorer/.test(a.url);

  test('budgets per route and conditional loading', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Bayt bütçesi tarayıcıdan bağımsızdır; tek motorda ölçülür.');
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1366, height: 900 });

    const home = await load(page, '');
    expect(kb(home, 'html'), 'ana sayfa HTML').toBeLessThanOrEqual(25);
    // Kabuk bütçesinin kapsamı kabuğun ilk görünümde gerektirdiği TOPLAM JS'tir (giriş parçaları + paylaşılan
    // Mantine/tema ve React parçaları). Giriş parçaları ayrıca raporlanır, bütçe onlarla daraltılmaz.
    const shellEntry = (a: Asset) => /\/(client|Shell)\.[^/]+\.js$/.test(a.url);
    const shellTotal = kb(home, 'js');
    test.info().annotations.push({
      type: 'ölçüm',
      description: `kabuk ilk görünüm JS toplam ${shellTotal.toFixed(1)} KB gzip; giriş parçaları (client + Shell) ${kb(home, 'js', shellEntry).toFixed(1)} KB`,
    });
    console.log(`[bütçe] kabuk toplam JS ${shellTotal.toFixed(1)} KB; giriş parçaları ${kb(home, 'js', shellEntry).toFixed(1)} KB`);
    expect(shellTotal, 'kabuk: ilk görünümde gerekli toplam JS').toBeLessThanOrEqual(100);
    expect(kb(home, 'css'), 'CSS').toBeLessThanOrEqual(70);
    expect(kb(home, 'font'), 'ilk görünüm yazı tipleri').toBeLessThanOrEqual(200);
    expect(home.filter(isExplorer), 'gezgin adası yalnız Gereksinimler sayfasında').toEqual([]);
    expect(home.filter(isMermaid), 'mermaid yalnız diyagramlı sayfada').toEqual([]);

    // Koşullu yükleme ad bağımsız denetlenir: kabuk dışındaki her JS parçası "ek" sayılır.
    const shellUrls = new Set(home.filter((a) => a.kind === 'js').map((a) => a.url));
    const extraJs = (assets: Asset[]) => assets.filter((a) => a.kind === 'js' && !shellUrls.has(a.url)).map((a) => a.url);

    const section = await load(page, 'kararlar/');
    expect(kb(section, 'html'), 'tipik bölüm HTML').toBeLessThanOrEqual(25);
    expect(section.filter(isMermaid), 'diyagramsız bölümde mermaid yok').toEqual([]);
    expect(extraJs(section), 'adasız ve diyagramsız bölüm kabuk dışında JS indirmez').toEqual([]);

    const reqs = await load(page, 'gereksinimler/');
    const reqsHtml = kb(reqs, 'html');
    test.info().annotations.push({ type: 'ölçüm', description: `Gereksinimler HTML ${reqsHtml.toFixed(1)} KB gzip (bütçe 200)` });
    console.log(`[bütçe] Gereksinimler HTML ${reqsHtml.toFixed(1)} KB`);
    expect(reqsHtml, 'Gereksinimler HTML').toBeLessThanOrEqual(200);
    // Ada bütçesi: Gereksinimler sayfasının kabuğa EK olarak indirdiği tüm JS (adanın kendi parçası + yalnız onun
    // çektiği paylaşılmayan parçalar).
    const islandExtra = kb(reqs, 'js', (a) => !shellUrls.has(a.url));
    expect(kb(reqs, 'js', isExplorer), 'gezgin adası yüklendi').toBeGreaterThan(0);
    test.info().annotations.push({ type: 'ölçüm', description: `gezgin adası ek JS ${islandExtra.toFixed(1)} KB gzip` });
    console.log(`[bütçe] gezgin adası ek JS ${islandExtra.toFixed(1)} KB`);
    expect(islandExtra, 'gezgin adasının kabuğa ek JS toplamı').toBeLessThanOrEqual(30);

    const diagram = await load(page, 'rail-4-keycloak/');
    expect(diagram.filter(isMermaid).length, 'diyagramlı sayfada mermaid dinamik yüklenir').toBeGreaterThan(0);
    expect(extraJs(diagram).length, 'diyagram parçaları kabuğa ek olarak yalnız burada iner').toBeGreaterThan(0);
  });
});
