import { test, expect, type Page } from '@playwright/test';

// Görsel regresyon (rapor Y-11): referans görüntüler yalnız Linux CI ortamında (ubuntu-latest + Playwright'ın kendi
// tarayıcıları) üretilir ve karşılaştırılır. Yazı tipi işleme işletim sistemine göre değiştiği için macOS yerel
// koşusunda bu testler atlanır ve not_run sayılır. Referanslar yalnız `deploy.yml` elle tetiklenip `visual_baseline`
// seçilince üretilir; sessiz veya toplu güncelleme yapılmaz, yeni referans incelemeden sonra commit edilir.
test.skip(process.platform !== 'linux', 'Görsel referanslar Linux CI ortamına aittir; bu platformda not_run.');

async function settle(page: Page) {
  await page.waitForFunction(() => !document.querySelector('astro-island[ssr]'), undefined, { timeout: 20_000 });
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.mouse.move(0, 0);
}

const VIEWPORT_SHOTS = [
  { name: 'home-1366-light', path: '', width: 1366, height: 900, scheme: 'light' as const },
  { name: 'home-320-light', path: '', width: 320, height: 640, scheme: 'light' as const },
  { name: 'kararlar-390-dark', path: 'kararlar/', width: 390, height: 844, scheme: 'dark' as const },
  { name: 'gereksinimler-1366-light', path: 'gereksinimler/', width: 1366, height: 900, scheme: 'light' as const },
];

test.describe('visual regression', () => {
  for (const shot of VIEWPORT_SHOTS) {
    test(`viewport ${shot.name}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: shot.scheme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width: shot.width, height: shot.height });
      await page.goto(shot.path);
      await settle(page);
      // İçerikle değişen gezgin sonuç listesi maskelenir: test kabuk, süzgeç ve tipografi gerilemelerini yakalar.
      await expect(page).toHaveScreenshot(`${shot.name}.png`, {
        mask: [page.locator('.req-table tbody'), page.locator('.req-cards')],
      });
    });
  }

  test('diagram timeline', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('yol-haritasi/');
    await settle(page);
    await expect(page.locator('.diagram-timeline')).toHaveScreenshot('timeline-1366-light.png');
  });

  test('diagram rails dark', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto('raylar/');
    await settle(page);
    await expect(page.locator('.diagram-rails')).toHaveScreenshot('rails-1366-dark.png');
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
    await expect(page.locator('.req-filters')).toHaveScreenshot('search-focus-1366-light.png');
  });
});
