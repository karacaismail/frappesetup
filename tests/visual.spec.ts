import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';
import { waitForRequirementsView } from './requirements-view';

// Visual regression (report Y-11): reference images are generated and compared only in the Linux CI environment (ubuntu-24.04 + Playwright's own
// browsers). Font rendering differs by operating system, so on a local macOS
// run these tests are skipped and counted as not_run. References are generated only when `deploy.yml` is triggered by hand with
// `visual_baseline` selected; no silent or bulk update is made, a new reference is committed after review.
test.skip(process.platform !== 'linux', 'Görsel referanslar Linux CI ortamına aittir; bu platformda not_run.');

// Diagram element screenshots: the fixed header must not cover the top of a long figure (applied only while the screenshot is taken).
const HIDE_CHROME = fileURLToPath(new URL('./visual-hide-chrome.css', import.meta.url));

async function settle(page: Page) {
  await page.waitForFunction(() => !document.querySelector('astro-island[ssr]'), undefined, { timeout: 20_000 });
  await waitForRequirementsView(page);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.mouse.move(0, 0);
}

const VIEWPORT_SHOTS = [
  { name: 'home-1366-light', path: '', width: 1366, height: 900, scheme: 'light' as const },
  { name: 'home-320-light', path: '', width: 320, height: 640, scheme: 'light' as const },
  { name: 'kararlar-390-dark', path: 'kararlar/', width: 390, height: 844, scheme: 'dark' as const },
  // On a wide screen the table is drawn in place of the cards once the browser is idle (requestIdleCallback, at most 1.5 s).
  // The reference has the table header; if the screenshot is taken before the table is drawn, WebKit gives an unstable diff.
  {
    name: 'gereksinimler-1366-light',
    path: 'gereksinimler/',
    width: 1366,
    height: 900,
    scheme: 'light' as const,
    ready: '.req-table thead',
  },
];

test.describe('visual regression', () => {
  for (const shot of VIEWPORT_SHOTS) {
    test(`viewport ${shot.name}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: shot.scheme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width: shot.width, height: shot.height });
      await page.goto(shot.path);
      await settle(page);
      if ('ready' in shot) await expect(page.locator(shot.ready)).toBeVisible({ timeout: 10_000 });
      // The explorer result list, which changes with content, is masked: the test catches shell, filter and typography regressions.
      await expect(page).toHaveScreenshot(`${shot.name}.png`, {
        mask: [page.locator('.req-table tbody')],
      });
    });
  }

  test('diagram timeline', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('yol-haritasi/');
    await settle(page);
    await expect(page.locator('.diagram-timeline')).toHaveScreenshot('timeline-1366-light.png', { stylePath: HIDE_CHROME });
  });

  test('diagram rails dark', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('raylar/');
    await settle(page);
    await expect(page.locator('.diagram-rails')).toHaveScreenshot('rails-1366-dark.png', { stylePath: HIDE_CHROME });
  });

  test('keyboard focus on search input', async ({ page, browserName }) => {
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('gereksinimler/');
    await settle(page);
    const search = page.getByRole('textbox', { name: 'Ara' });
    const tab = browserName === 'webkit' ? 'Alt+Tab' : 'Tab';
    for (let i = 0; i < 60 && !(await search.evaluate((el) => el === document.activeElement)); i++) {
      await page.keyboard.press(tab);
    }
    await expect(search).toBeFocused();
    // The crop is wider than the input's box by enough to fully contain the outline (2 px) and its offset (2 px).
    const box = await search.boundingBox();
    expect(box).not.toBeNull();
    await expect(page).toHaveScreenshot('search-focus-1366-light.png', {
      clip: { x: box!.x - 8, y: box!.y - 8, width: box!.width + 16, height: box!.height + 16 },
    });
  });
});
