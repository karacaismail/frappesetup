import { expect, test } from '@playwright/test';
import { KC, screens } from './helpers';

// Yerleşim testleri bütün görünümlerde koşar: 320, 360, 375, 390, yatay telefon, tablet ve masaüstü.
for (const item of screens) {
  test(`@matris ${item.name}: taşma, yazı boyutu, yazı tipi ve kontrol ölçüsü`, async ({ page }) => {
    const requests: string[] = [];
    page.on('request', (request) => requests.push(request.url()));
    await item.open(page);
    await page.evaluate(() => document.fonts.ready);

    // Sayfa yatay taşmaz.
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll, 'yatay taşma').toBeLessThanOrEqual(overflow.client);

    // Okunabilir her metin en az 14 CSS pikseldir ve Outfit ile çizilir.
    const text = await page.evaluate(() => {
      const small: string[] = [];
      const wrongFont: string[] = [];
      const forcedBreak: string[] = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const seen = new Set<Element>();
      while (walker.nextNode()) {
        const node = walker.currentNode;
        const element = node.parentElement;
        if (!element || seen.has(element) || !node.textContent?.trim()) continue;
        if (element.closest('script, style, noscript')) continue;
        const style = getComputedStyle(element);
        const box = element.getBoundingClientRect();
        if (style.visibility === 'hidden' || style.display === 'none' || box.width === 0 || box.height === 0) continue;
        if (!element.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
        seen.add(element);
        const label = `${element.tagName.toLowerCase()}#${element.id}.${element.className} "${node.textContent.trim().slice(0, 30)}"`;
        if (Number.parseFloat(style.fontSize) < 14) small.push(`${label} ${style.fontSize}`);
        const mono = element.closest('pre, code, kbd, samp, #kc-totp-secret-key');
        if (!mono && !/^"?Outfit/.test(style.fontFamily)) wrongFont.push(`${label} ${style.fontFamily}`);
        if (style.overflowWrap === 'anywhere' || style.wordBreak === 'break-all') forcedBreak.push(label);
      }
      for (const control of document.querySelectorAll<HTMLElement>('input:not([type=hidden]), button, select, textarea')) {
        const style = getComputedStyle(control);
        if (control.offsetParent && Number.parseFloat(style.fontSize) < 14) small.push(`${control.tagName}#${control.id} ${style.fontSize}`);
        if (control.offsetParent && !/^"?Outfit/.test(style.fontFamily)) wrongFont.push(`${control.tagName}#${control.id} ${style.fontFamily}`);
      }
      return { small, wrongFont, forcedBreak, outfitLoaded: document.fonts.check('16px "Outfit Variable"', 'Şifre ığüşöç') };
    });
    expect(text.small, '14 pikselden küçük metin').toEqual([]);
    expect(text.wrongFont, 'Outfit dışı yazı tipi').toEqual([]);
    expect(text.forcedBreak, 'zorlayıcı satır kırma').toEqual([]);
    expect(text.outfitLoaded, 'Outfit yüklendi').toBe(true);

    // Bütün istekler Keycloak'ın kendi adresine gider. Dış yazı tipi ve dış betik yoktur.
    const external = requests.filter((url) => !url.startsWith(KC) && !url.startsWith('data:') && !url.startsWith('blob:'));
    expect(external, 'dış istek').toEqual([]);
    const fonts = requests.filter((url) => /\.(woff2?|ttf|otf|eot)(\?|$)/.test(url));
    expect(fonts.filter((url) => /RedHat|overpass/i.test(url)), 'tema dışı yazı tipi isteği').toEqual([]);
    expect(fonts.some((url) => /outfit-latin-wght-normal\.woff2/.test(url)), 'Outfit isteği').toBe(true);

    // İşletim sisteminin açılır listesi kullanılmaz.
    await expect(page.locator('select')).toHaveCount(0);

    // Tek başına duran kontrolün etkili alanı en az 44 pikseldir. Kaba işaretçide 48 pikseldir.
    const minimum = await page.evaluate(() => (matchMedia('(any-pointer: coarse)').matches ? 48 : 44));
    const smallTargets = await page.evaluate((min) => {
      const found: string[] = [];
      const selector =
        'button, a[class*="c-button"], input:not([type=hidden]):not([type=checkbox]):not([type=radio]), [data-at-standalone], .pf-v5-c-helper-text a, #kc-registration a, .at-link-line a, .at-link-list a';
      for (const control of document.querySelectorAll<HTMLElement>(selector)) {
        if (!control.checkVisibility()) continue;
        const box = control.getBoundingClientRect();
        // Bağlantıda yükseklik ölçülür. Kısa bağlantı metni 44 pikselden dar olabilir.
        const narrow = control.tagName !== 'A' && box.width < min - 0.5;
        if (box.height < min - 0.5 || narrow) {
          found.push(`${control.tagName.toLowerCase()}#${control.id} ${Math.round(box.width)}x${Math.round(box.height)}`);
        }
      }
      return found;
    }, minimum);
    expect(smallTargets, 'küçük dokunma alanı').toEqual([]);
  });
}

// Kullanıcı kök yazı boyutunu büyütebilir. Yerleşim taşmamalı ve kontroller görünür kalmalıdır.
for (const percent of [125, 200]) {
  for (const name of ['giris', 'totp-kurulum', 'passkey-giris']) {
    test(`${name}: kök yazı %${percent} iken sayfa taşmaz`, async ({ page }) => {
      await screens.find((item) => item.name === name)!.open(page);
      await page.addStyleTag({ content: `html { font-size: ${percent}% !important; }` });
      const size = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
        root: Number.parseFloat(getComputedStyle(document.documentElement).fontSize),
      }));
      expect(size.root).toBe((16 * percent) / 100);
      expect(size.scroll, 'yatay taşma').toBeLessThanOrEqual(size.client);
      await expect(page.locator('.pf-v5-c-button.pf-m-primary').first()).toBeVisible();
    });
  }
}

test.describe('dokunmatik profil', () => {
  test.use({ hasTouch: true, isMobile: false });
  test('kaba işaretçide kontroller en az 48 pikseldir', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'any-pointer öykünmesi yalnız Chromium ailesinde güvenilir');
    await screens[0].open(page);
    expect(await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches)).toBe(true);
    const heights = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('button, a[class*="c-button"], input:not([type=hidden])')]
        .filter((element) => element.checkVisibility())
        .map((element) => Math.round(element.getBoundingClientRect().height)),
    );
    expect(Math.min(...heights)).toBeGreaterThanOrEqual(48);
  });
});
