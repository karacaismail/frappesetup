import { expect, test } from '@playwright/test';
import { KC, screen, screens } from './helpers';

// Layout tests run in every view: 320, 360, 375, 390, landscape phone, tablet and desktop.
for (const item of screens) {
  test(`@matrix ${item.name}: taşma, yazı boyutu, yazı tipi ve kontrol ölçüsü`, async ({ page }) => {
    const requests: string[] = [];
    page.on('request', (request) => requests.push(request.url()));
    await item.open(page);
    await page.evaluate(() => document.fonts.ready);

    // The page does not overflow sideways.
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll, 'yatay taşma').toBeLessThanOrEqual(overflow.client);

    // Every readable text is at least 14 CSS pixels and is drawn in Outfit.
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

    // Every request goes to Keycloak's own address. There is no external font or script.
    const external = requests.filter((url) => !url.startsWith(KC) && !url.startsWith('data:') && !url.startsWith('blob:'));
    expect(external, 'dış istek').toEqual([]);
    const fonts = requests.filter((url) => /\.(woff2?|ttf|otf|eot)(\?|$)/.test(url));
    expect(fonts.filter((url) => /RedHat|overpass/i.test(url)), 'tema dışı yazı tipi isteği').toEqual([]);
    expect(fonts.some((url) => /outfit-latin-wght-normal\.woff2/.test(url)), 'Outfit isteği').toBe(true);

    // The operating system's drop-down list is not used.
    await expect(page.locator('select')).toHaveCount(0);

    // A standalone control's effective area is at least 44 pixels. With a coarse pointer it is 48 pixels.
    const minimum = await page.evaluate(() => (matchMedia('(any-pointer: coarse)').matches ? 48 : 44));
    const smallTargets = await page.evaluate((min) => {
      const found: string[] = [];
      const selector =
        'button, a[class*="c-button"], input:not([type=hidden]):not([type=checkbox]):not([type=radio]), [data-at-standalone], .pf-v5-c-helper-text a, #kc-registration a, .at-link-line a, .at-link-list a';
      for (const control of document.querySelectorAll<HTMLElement>(selector)) {
        if (!control.checkVisibility()) continue;
        const box = control.getBoundingClientRect();
        // For links the height is measured. A short link text may be narrower than 44 pixels.
        const narrow = control.tagName !== 'A' && box.width < min - 0.5;
        if (box.height < min - 0.5 || narrow) {
          found.push(`${control.tagName.toLowerCase()}#${control.id} ${Math.round(box.width)}x${Math.round(box.height)}`);
        }
      }
      for (const checkbox of document.querySelectorAll<HTMLInputElement>('input[type=checkbox]')) {
        if (!checkbox.checkVisibility()) continue;
        const boxes = [...(checkbox.labels ?? [])].map((label) => label.getBoundingClientRect());
        if (!boxes.some((box) => box.width >= min - 0.5 && box.height >= min - 0.5)) {
          found.push(`checkbox#${checkbox.id} has no label with a ${min}px touch target`);
        }
      }
      return found;
    }, minimum);
    expect(smallTargets, 'küçük dokunma alanı').toEqual([]);
  });
}

test('@matrix recovery codes stay on one line and within their column', async ({ page }) => {
  await screen('recovery-codes-setup').open(page);
  await page.evaluate(() => document.fonts.ready);
  const wrappedOrOverflowing = await page.locator('#kc-recovery-codes-list li').evaluateAll((items) =>
    items.flatMap((item, index) => {
      const range = document.createRange();
      range.selectNodeContents(item);
      const lines = range.getClientRects();
      const box = item.getBoundingClientRect();
      return lines.length !== 1 || lines[0].right > box.right + 0.5 ? [index + 1] : [];
    }),
  );
  expect(wrappedOrOverflowing).toEqual([]);
});

// The user may enlarge the root font size. The layout must not overflow and controls must stay visible.
for (const percent of [125, 200]) {
  for (const name of ['sign-in', 'totp-setup', 'passkey-sign-in']) {
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

test('recovery confirmation can be selected from the edge of its label', async ({ page }) => {
  await screen('recovery-codes-setup').open(page);
  const checkbox = page.getByRole('checkbox', { name: 'Kodları güvenli bir yere kaydettim' });
  const label = page.locator('label').filter({ hasText: 'Kodları güvenli bir yere kaydettim' });
  const inputBox = await checkbox.boundingBox();
  const labelBox = await label.boundingBox();
  expect(inputBox!.height).toBeLessThan(44);
  expect(labelBox!.height).toBeGreaterThanOrEqual(44);
  await label.click({ position: { x: labelBox!.width - 3, y: 3 } });
  await expect(checkbox).toBeChecked();
});

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

  test('recovery confirmation has a 48px target with a coarse pointer', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Coarse pointer emulation is only reliable in Chromium');
    await screen('recovery-codes-setup').open(page);
    expect(await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches)).toBe(true);
    const label = page.locator('label').filter({ hasText: 'Kodları güvenli bir yere kaydettim' });
    const box = await label.boundingBox();
    expect(box!.width).toBeGreaterThanOrEqual(48);
    expect(box!.height).toBeGreaterThanOrEqual(48);
    await label.tap({ position: { x: box!.width - 3, y: 3 } });
    await expect(page.getByRole('checkbox', { name: 'Kodları güvenli bir yere kaydettim' })).toBeChecked();
  });
});
