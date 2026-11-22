import { defineConfig } from '@playwright/test';

// Atonota giriş temasının testleri. Firefox bilinçli olarak yoktur (kalıcı proje kuralı).
// Önce `bin/theme-dev.sh up` ve `bin/theme-dev.sh tunnel` çalışmalıdır.
const viewports = {
  '320': { width: 320, height: 568 },
  '360': { width: 360, height: 740 },
  '375': { width: 375, height: 667 },
  '390': { width: 390, height: 844 },
  landscape: { width: 667, height: 375 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 800 },
} as const;

// Akış ve klavye testleri yalnız en dar ve en geniş görünümde koşar.
// @matrix etiketli yerleşim testleri bütün görünümlerde koşar.
const fullRun = new Set(['320', 'desktop']);

export default defineConfig({
  testDir: './tests',
  outputDir: './test-results',
  fullyParallel: true,
  workers: 4,
  retries: 0,
  timeout: 60_000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: { locale: 'tr-TR', trace: 'retain-on-failure' },
  projects: [
    ...(['chromium', 'webkit'] as const).flatMap((browserName) =>
      Object.entries(viewports).map(([name, viewport]) => ({
        name: `${browserName}-${name}`,
        grep: fullRun.has(name) ? undefined : /@matrix/,
        use: { browserName, viewport },
      })),
    ),
  ],
});
