import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';

const viewports = [
  { name: '320 px', width: 320, height: 640 },
  { name: 'short phone 320x480', width: 320, height: 480 },
  { name: 'short phone 320x568', width: 320, height: 568 },
  { name: 'short landscape 568x320', width: 568, height: 320 },
  { name: '360 px', width: 360, height: 800 },
  { name: '375 px', width: 375, height: 812 },
  { name: '390 px', width: 390, height: 844 },
  { name: 'phone landscape', width: 667, height: 375 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 900 },
];

const wcagAA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

async function openPanel(page: Page, language = 'en') {
  const username = process.env.PANEL_TEST_USERNAME;
  const password = process.env.PANEL_TEST_PASSWORD;
  if (!username || !password) throw new Error('Set PANEL_TEST_USERNAME and PANEL_TEST_PASSWORD for the isolated test site.');
  const login = await page.request.post('/api/method/login', { form: { usr: username, pwd: password } });
  expect(login.status()).toBe(200);
  const response = await page.goto(`/panel?_lang=${language}`);
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL(/\/panel\?/);
  await page.evaluate(() => document.fonts.ready);
}

async function edgeStyles(element: Locator) {
  return element.evaluate((node) => {
    const computed = (target: Element, pseudo?: string) => {
      const css = getComputedStyle(target, pseudo);
      return { outline: css.outlineStyle, shadow: css.boxShadow, border: css.border };
    };
    const edges = [];
    for (let target: Element | null = node; target; target = target.parentElement) {
      edges.push(computed(target), computed(target, '::before'), computed(target, '::after'));
    }
    return edges;
  });
}

function tabKey(browserName: string, reverse = false) {
  // WebKit follows macOS link navigation preferences. Option+Tab includes links.
  return [reverse ? 'Shift' : '', browserName === 'webkit' ? 'Alt' : '', 'Tab'].filter(Boolean).join('+');
}

async function underlineWidth(element: Locator) {
  return await element.evaluate((node) => parseFloat(getComputedStyle(node).textDecorationThickness));
}

async function expectNoRing(element: Locator, initialEdges: Awaited<ReturnType<typeof edgeStyles>>) {
  const edges = await edgeStyles(element);
  expect(edges).toEqual(initialEdges);
  for (const edge of edges) {
    expect(edge.outline).toBe('none');
    expect(edge.shadow).toBe('none');
  }
}

async function expectKeyboardIndicator(
  element: Locator, initialEdges: Awaited<ReturnType<typeof edgeStyles>>, restingWidth: number,
) {
  await expect(element).toBeFocused();
  await expect(element).toBeInViewport();
  await expect(element).toHaveCSS('clip-path', 'none');
  await expect(element).toHaveCSS('text-decoration-line', 'underline');
  expect(await underlineWidth(element)).toBeGreaterThanOrEqual(Math.max(3, restingWidth + 2));
  await expectNoRing(element, initialEdges);
}

async function expectLayout(page: Page) {
  const layout = await page.evaluate(() => {
    const text = Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .filter((node) => node.checkVisibility() && Array.from(node.childNodes).some(
        (child) => child.nodeType === Node.TEXT_NODE && child.textContent?.trim(),
      ));
    return {
      viewport: document.documentElement.clientWidth,
      pageWidth: document.documentElement.scrollWidth,
      text: text.map((node) => {
        const css = getComputedStyle(node);
        return { size: parseFloat(css.fontSize), family: css.fontFamily.split(',')[0].replaceAll('"', '').trim() };
      }),
      loadedOutfit: Array.from(document.fonts).some(
        (font) => font.family.replaceAll('"', '') === 'Outfit' && font.status === 'loaded',
      ),
    };
  });
  expect(layout.pageWidth).toBeLessThanOrEqual(layout.viewport);
  expect(layout.text.length).toBeGreaterThan(0);
  expect(layout.loadedOutfit).toBe(true);
  for (const text of layout.text) {
    expect(text.size).toBeGreaterThanOrEqual(14);
    expect(text.family).toBe('Outfit');
  }
}

for (const { name, width, height } of viewports) {
  test.describe(name, () => {
    test.use({ viewport: { width, height } });

    test('fits the viewport, uses Outfit and passes automated WCAG AA rules', async ({ page }, testInfo) => {
      await openPanel(page, 'tr');
      await expectLayout(page);
      const results = await new AxeBuilder({ page }).withTags(wcagAA).analyze();
      expect(results.violations).toEqual([]);
      if (width === 320) {
        await expect(page.getByRole('link', { name: 'Sitenin ana sayfasına gidin' })).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath('panel-320.png') });
      }
    });

    test('shows a non-enclosing indicator in both Tab directions and preserves focus with reduced motion', async ({ page, browserName }, testInfo) => {
      await openPanel(page);
      const root = page.locator('html');
      for (const key of ['Escape', 'ArrowDown', 'ArrowUp', 'A']) {
        await page.keyboard.press(key);
        await expect(root).not.toHaveAttribute('data-keyboard-focus', '');
      }
      const skip = page.getByRole('link', { name: 'Skip to main content' });
      const home = page.getByRole('link', { name: 'Go to site home' });
      await expect(skip).toHaveCount(1);
      await expect(home).toHaveCount(1);

      const main = page.getByRole('main');
      const heading = main.getByRole('heading', { level: 1 });
      const mainEdges = await edgeStyles(main);
      const skipEdges = await edgeStyles(skip);
      const homeEdges = await edgeStyles(home);
      const skipResting = await underlineWidth(skip);
      const homeResting = await underlineWidth(home);
      if (width === 320 && height === 640) {
        await home.screenshot({ path: testInfo.outputPath('home-resting.png') });
      }
      await page.keyboard.press(tabKey(browserName));
      await expectKeyboardIndicator(skip, skipEdges, skipResting);
      await expect(skip).toHaveCSS('clip-path', 'none');
      await page.keyboard.press(tabKey(browserName));
      await expectKeyboardIndicator(home, homeEdges, homeResting);
      if (width === 320 && height === 640) {
        await home.screenshot({ path: testInfo.outputPath('home-focused.png') });
      }
      await page.keyboard.press(tabKey(browserName, true));
      await expectKeyboardIndicator(skip, skipEdges, skipResting);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
      await expectKeyboardIndicator(skip, skipEdges, skipResting);
      await page.keyboard.press(tabKey(browserName));
      await expectKeyboardIndicator(home, homeEdges, homeResting);
      const motion = await page.evaluate(() => {
        const hasTime = (durations: string) => durations.split(',').some((duration) => parseFloat(duration) > 0);
        return {
          running: document.getAnimations().length,
          configured: Array.from(document.querySelectorAll('body, body *')).some((node) => {
            const css = getComputedStyle(node);
            return (css.animationName !== 'none' && hasTime(css.animationDuration))
              || hasTime(css.transitionDuration)
              || css.scrollBehavior === 'smooth';
          }),
        };
      });
      expect(motion).toEqual({ running: 0, configured: false });
      await page.keyboard.press(tabKey(browserName, true));
      await expectKeyboardIndicator(skip, skipEdges, skipResting);
      await expectLayout(page);
      if (width === 320) {
        await page.screenshot({ path: testInfo.outputPath('panel-320-keyboard.png') });
      }
      await page.keyboard.press('Enter');
      await expect(main).toBeFocused();
      await expectNoRing(main, mainEdges);
      await expect(heading).toBeInViewport();
      await expect(heading).toHaveCSS('clip-path', 'none');
      await expect(heading).toHaveCSS('text-decoration-line', 'underline');
      expect(await underlineWidth(heading)).toBeGreaterThanOrEqual(3);
      await expect(root).toHaveAttribute('data-keyboard-focus', '');
      await page.mouse.down();
      await page.mouse.up();
      await expect(root).not.toHaveAttribute('data-keyboard-focus', '');
      await skip.focus();
      await expect(skip).toBeFocused();
      await expectNoRing(skip, skipEdges);
      expect(await skip.getAttribute('tabindex')).toBeNull();
      expect(await home.getAttribute('tabindex')).toBeNull();
    });
  });
}


test('allows the forced-colors outline only in keyboard mode', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Forced-colors emulation is checked in Chromium.');
  await page.emulateMedia({ forcedColors: 'active' });
  await openPanel(page);
  const skip = page.getByRole('link', { name: 'Skip to main content' });
  const home = page.getByRole('link', { name: 'Go to site home' });
  await home.focus();
  await expect(home).toHaveCSS('outline-style', 'none');
  await page.keyboard.press(tabKey(browserName, true));
  await expect(skip).toBeFocused();
  await expect(skip).toHaveCSS('outline-style', 'solid');
  await expect(skip).toHaveCSS('outline-width', '2px');
  await expect(skip).toHaveCSS('text-decoration-thickness', '1px');
  await page.mouse.down();
  await page.mouse.up();
  await skip.focus();
  await expect(skip).toBeFocused();
  await expect(skip).toHaveCSS('outline-style', 'none');
});

test('reveals the focused skip link when the focus script cannot run', async ({ page, browserName }) => {
  let blocked = 0;
  await page.route(/\/(?:focus\.js|panel-focus\.bundle\.[^/]+\.js)$/, (route) => {
    blocked += 1;
    return route.abort();
  });
  await openPanel(page);
  expect(blocked).toBeGreaterThan(0);
  await expectLayout(page);
  const skip = page.getByRole('link', { name: 'Skip to main content' });
  await expect(skip).not.toHaveCSS('clip-path', 'none');
  await page.keyboard.press(tabKey(browserName));
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await expect(skip).toHaveCSS('clip-path', 'none');
  await expect(page.locator('html')).not.toHaveAttribute('data-keyboard-focus', '');
});

test('serves versioned panel styles and scripts', async ({ page }) => {
  await openPanel(page);
  await expect(page.locator('link[rel=stylesheet]')).toHaveAttribute('href', /panel\.bundle\.[\w-]+\.css$/);
  await expect(page.locator('script[src]')).toHaveAttribute('src', /panel-focus\.bundle\.[\w-]+\.js$/);
});

test('fits larger user text and CSS zoom in a short viewport', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 480 });
  await openPanel(page, 'tr');
  for (const scale of ['125%', '200%']) {
    await page.locator('html').evaluate((node, value) => { node.style.fontSize = value; }, scale);
    await expect(page.locator('html')).toHaveCSS('font-size', scale === '125%' ? '20px' : '32px');
    await expectLayout(page);
  }
  await page.locator('html').evaluate((node) => {
    node.style.fontSize = '';
    node.style.zoom = '200%';
  });
  await expect(page.locator('html')).toHaveCSS('zoom', '2');
  await expectLayout(page);
});

test.describe('touch input', () => {
  test.use({ hasTouch: true, viewport: { width: 320, height: 480 } });
  test('touchstart closes visual keyboard mode without blurring', async ({ page, browserName }) => {
    await openPanel(page);
    const root = page.locator('html');
    const skip = page.getByRole('link', { name: 'Skip to main content' });
    await page.keyboard.press(tabKey(browserName));
    await expect(skip).toBeFocused();
    await expect(root).toHaveAttribute('data-keyboard-focus', '');
    await skip.dispatchEvent('touchstart');
    await expect(skip).toBeFocused();
    await expect(root).not.toHaveAttribute('data-keyboard-focus', '');
    await page.keyboard.press(tabKey(browserName));
    await expect(root).toHaveAttribute('data-keyboard-focus', '');
    await page.touchscreen.tap(1, 1);
    await expect(root).not.toHaveAttribute('data-keyboard-focus', '');
  });
});
