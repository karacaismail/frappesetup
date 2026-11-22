import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';

const viewports = [
  { name: '320 px', width: 320, height: 640 },
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

async function expectKeyboardIndicator(element: Locator, initialEdges: Awaited<ReturnType<typeof edgeStyles>>) {
  await expect(element).toBeFocused();
  await expect(element).toBeInViewport();
  await expect(element).toHaveCSS('text-decoration-line', 'underline');
  await expect(element).toHaveCSS('text-decoration-thickness', '2px');
  expect(await edgeStyles(element)).toEqual(initialEdges);
  for (const edge of initialEdges) {
    expect(edge.outline).toBe('none');
    expect(edge.shadow).toBe('none');
  }
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

    test('shows a non-enclosing indicator in both Tab directions and preserves focus with reduced motion', async ({ page }, testInfo) => {
      await openPanel(page);
      const root = page.locator('html');
      await page.keyboard.press('Escape');
      await expect(root).not.toHaveAttribute('data-keyboard-focus', '');
      const skip = page.getByRole('link', { name: 'Skip to main content' });
      const home = page.getByRole('link', { name: 'Go to site home' });
      await expect(skip).toHaveCount(1);
      await expect(home).toHaveCount(1);

      const skipEdges = await edgeStyles(skip);
      const homeEdges = await edgeStyles(home);
      await page.keyboard.press('Tab');
      await expectKeyboardIndicator(skip, skipEdges);
      await expect(skip).toHaveCSS('clip-path', 'none');
      await page.keyboard.press('Tab');
      await expectKeyboardIndicator(home, homeEdges);
      await page.keyboard.press('Shift+Tab');
      await expectKeyboardIndicator(skip, skipEdges);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
      await expectKeyboardIndicator(skip, skipEdges);
      await page.keyboard.press('Tab');
      await expectKeyboardIndicator(home, homeEdges);
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
      await page.keyboard.press('Shift+Tab');
      await expectKeyboardIndicator(skip, skipEdges);
      await expectLayout(page);
      if (width === 320) {
        await page.screenshot({ path: testInfo.outputPath('panel-320-keyboard.png') });
      }
      await page.keyboard.press('Enter');
      await expect(page.getByRole('main')).toBeFocused();
      await expect(root).toHaveAttribute('data-keyboard-focus', '');
      await page.mouse.down();
      await page.mouse.up();
      await expect(root).not.toHaveAttribute('data-keyboard-focus', '');
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
  await page.keyboard.press('Shift+Tab');
  await expect(skip).toBeFocused();
  await expect(skip).toHaveCSS('outline-style', 'solid');
  await expect(skip).toHaveCSS('outline-width', '2px');
  await expect(skip).toHaveCSS('text-decoration-thickness', '1px');
  await page.mouse.down();
  await page.mouse.up();
  await expect(skip).toHaveCSS('outline-style', 'none');
});
