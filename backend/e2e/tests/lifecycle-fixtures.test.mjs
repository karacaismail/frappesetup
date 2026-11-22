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

test('a failed runner does not cancel the independent one-hour check', async () => {
  const { browserRunStatuses } = await import('../preview/browser-fixtures.mjs');
  let complete;
  const pending = new Promise((resolve) => { complete = resolve; });
  let settled = false;
  const reported = [];
  const work = browserRunStatuses([Promise.reject(new Error('report failed')), pending],
    (error) => reported.push(error.message)).then((statuses) => {
    settled = true;
    return statuses;
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  complete(0);
  assert.deepEqual(await work, [1, 0]);
  assert.deepEqual(reported, ['report failed']);
});
