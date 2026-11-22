import assert from 'node:assert/strict';
import { test } from 'node:test';

test('browser fixtures isolate the accounts for each engine and reject missing data', async () => {
  const { engineFixture } = await import('../preview/browser-fixtures.mjs');
  const settings = {
    E2E_CHROMIUM_DELETE_EMAIL: 'e2e-delete-chromium@example.test',
    E2E_WEBKIT_DELETE_EMAIL: 'e2e-delete-webkit@example.test',
  };
  assert.deepEqual(engineFixture(settings, 'webkit'), { E2E_DELETE_EMAIL: 'e2e-delete-webkit@example.test' });
  assert.throws(() => engineFixture({}, 'webkit'), /Missing fixture/);
});
