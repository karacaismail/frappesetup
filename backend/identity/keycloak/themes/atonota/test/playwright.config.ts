import { defineConfig } from '@playwright/test';

// Tests for the Atonota sign-in theme. Firefox is left out on purpose (standing project rule).
// Run `bin/theme-dev.sh up` and `bin/theme-dev.sh tunnel` first.
const viewports = {
  '320': { width: 320, height: 568 },
  '360': { width: 360, height: 740 },
  '375': { width: 375, height: 667 },
  '390': { width: 390, height: 844 },
  landscape: { width: 667, height: 375 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 800 },
} as const;

// Flow and keyboard tests run only in the narrowest and the widest view.
// Layout tests tagged @matrix run in every view.
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
