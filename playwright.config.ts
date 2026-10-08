import { defineConfig, devices } from '@playwright/test';

// Üretim çıktısına (astro build → astro preview) karşı çalışır; base '/frappesetup/'.
// `--ignore-lock`: Astro 7 preview kilit dosyası tutar; test sunucusu ondan bağımsız ön planda çalışır.
// PW_PORT: aynı makinede başka bir preview sunucusu (ör. ikinci çalışma ağacı) 4329'u tutuyorsa.
const PORT = process.env.PW_PORT ? Number(process.env.PW_PORT) : 4329;
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) throw new Error(`Geçersiz PW_PORT: ${process.env.PW_PORT}`);
export const BASE_URL = `http://127.0.0.1:${PORT}/frappesetup/`;

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  timeout: 45_000,
  expect: {
    timeout: 10_000,
    // Görsel referanslar yalnız Linux CI'da üretilir ve karşılaştırılır (tests/visual.spec.ts).
    toHaveScreenshot: { maxDiffPixelRatio: 0.002, animations: 'disabled', caret: 'hide', scale: 'css' },
  },
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run preview -- --ignore-lock --host 127.0.0.1 --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    // Dokunma profili (emülasyon): yalnız @touch etiketli senaryolar.
    { name: 'iphone-13', use: { ...devices['iPhone 13'] }, grep: /@touch/ },
  ],
});
