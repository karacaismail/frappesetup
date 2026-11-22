import { defineConfig } from '@playwright/test';

// Atonota giriş temasının testleri. Firefox bilinçli olarak yoktur (kalıcı proje kuralı).
// Önce `bin/tema-dev.sh up` ve `bin/tema-dev.sh tunel` çalışmalıdır.
const viewports = {
  '320': { width: 320, height: 568 },
  '360': { width: 360, height: 740 },
  '375': { width: 375, height: 667 },
  '390': { width: 390, height: 844 },
  yatay: { width: 667, height: 375 },
  tablet: { width: 768, height: 1024 },
  masaustu: { width: 1280, height: 800 },
} as const;

// Akış ve klavye testleri yalnız en dar ve en geniş görünümde koşar.
// @matris etiketli yerleşim testleri bütün görünümlerde koşar.
const fullRun = new Set(['320', 'masaustu']);

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
    // Tests that change a realm-wide setting run first and alone. Every other project depends on this one.
    {
      name: 'realm-settings',
      testMatch: /realm-settings\.spec\.ts/,
      fullyParallel: false,
      use: { browserName: 'chromium', viewport: viewports.masaustu },
    },
    ...(['chromium', 'webkit'] as const).flatMap((browserName) =>
      Object.entries(viewports).map(([name, viewport]) => ({
        name: `${browserName}-${name}`,
        grep: fullRun.has(name) ? undefined : /@matris/,
        testIgnore: /realm-settings\.spec\.ts/,
        dependencies: ['realm-settings'],
        use: { browserName, viewport },
      })),
    ),
  ],
});
