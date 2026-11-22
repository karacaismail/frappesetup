import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  workers: 1,
  retries: 0,
  reporter: 'list',
  projects: [
    { name: 'chromium', testMatch: 'browser.spec.ts', use: { browserName: 'chromium' } },
    { name: 'webkit', testMatch: 'browser.spec.ts', use: { browserName: 'webkit' } },
    { name: 'api', testMatch: 'integration.spec.ts' },
  ],
});
