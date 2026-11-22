import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const target = new URL(process.env.PANEL_TEST_URL ?? 'http://127.0.0.1:8000');
if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1') {
  throw new Error('PANEL_TEST_URL must use HTTP on 127.0.0.1.');
}

export default defineConfig({
  testDir: '.',
  outputDir: resolve(process.env.PANEL_TEST_OUTPUT ?? '.pane/scratch/panel-browser-results'),
  workers: 1,
  use: {
    baseURL: target.origin,
    extraHTTPHeaders: { 'X-Frappe-Site-Name': 'test-shell.localhost' },
    screenshot: 'only-on-failure',
    trace: 'off',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
