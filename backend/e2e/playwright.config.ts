import { defineConfig } from '@playwright/test';

// Ağır test kilidi (AJA-1807). Yerelde Playwright yalnız scripts/agir-test içinden koşar.
// Önizleme yığını kilidi bir kez alır. İçerideki koşu AGIR_TEST_YER ile gelir.
if (process.env.GITHUB_ACTIONS !== 'true' && !process.env.AGIR_TEST_YER) {
  throw new Error(
    'Playwright yerelde doğrudan koşmaz. Test kilitle koşmalıdır.\n'
    + 'Bu komutu kullanın: scripts/agir-test npx playwright test -c backend/e2e/playwright.config.ts',
  );
}

export default defineConfig({
  testDir: '.',
  workers: 1,
  retries: 0,
  reporter: 'list',
  projects: [
    { name: 'chromium', testMatch: ['browser.spec.ts', 'magic-link.spec.ts', 'mobile-pkce.spec.ts', 'lifecycle.spec.ts', 'press-deletion.spec.ts'], use: { browserName: 'chromium' } },
    { name: 'webkit', testMatch: ['browser.spec.ts', 'magic-link.spec.ts', 'mobile-pkce.spec.ts', 'lifecycle.spec.ts', 'press-deletion.spec.ts'], use: { browserName: 'webkit' } },
    { name: 'api', testMatch: 'integration.spec.ts' },
  ],
});
