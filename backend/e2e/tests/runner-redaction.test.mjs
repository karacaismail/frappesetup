import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const runner = fileURLToPath(new URL('../preview/run-tests.mjs', import.meta.url));

function runPreview(fixture, settings = {}) {
  const root = mkdtempSync(join(process.env.PANE_SCRATCH_DIR || tmpdir(), 'runner-redaction-'));
  try {
    const playwright = join(root, 'node_modules', '@playwright', 'test');
    const binaries = join(root, 'node_modules', '.bin');
    mkdirSync(playwright, { recursive: true });
    mkdirSync(binaries, { recursive: true });
    writeFileSync(join(playwright, 'index.js'), `
      exports.chromium = { launch: async () => {
        if (process.env.TEST_CHROMIUM_UNAVAILABLE) throw new Error('could not launch test Chromium');
        return { close: async () => {} };
      } };
      exports.webkit = { launch: async () => ({ close: async () => {} }) };
      exports.request = { newContext: async () => ({
        post: async () => ({ ok: () => true }),
        get: async () => ({ ok: () => true, text: async () => '<meta name="csrf-token" content="test-csrf">' }),
        storageState: async () => ({ cookies: [{ name: 'sid', value: 'test-session' }] }),
        dispose: async () => {},
      }) };
    `);
    writeFileSync(join(binaries, 'playwright'), `#!/usr/bin/env node
      if (process.argv.includes('browser.spec.ts') || process.argv.includes('integration.spec.ts')) {
        console.log('ran ' + process.argv.slice(2).join(' '));
      }
      if (process.argv.includes('lifecycle.spec.ts')) {
        console.log(JSON.stringify({ suites: [{ specs: [{ title: process.env.E2E_DELETE_PASSWORD,
          tests: [{ annotations: [] }] }] }], submitted: process.env.E2E_REVOKE_MOBILE_REFRESH_TOKEN }));
        console.error('Authorization value: ' + process.env.E2E_DELETE_PRESS_AUTHORIZATION);
      }
    `, { mode: 0o700 });
    writeFileSync(join(root, 'fixtures.json'), JSON.stringify(fixture));
    const result = spawnSync(process.execPath, [runner, root], {
      env: { ...process.env, ...settings, PANE_PORT: '4500', PREVIEW_DIR: root },
      encoding: 'utf8',
    });
    let log = '';
    if (result.status === 0) log = readFileSync(join(root, 'lifecycle.log'), 'utf8');
    return { ...result, log };
  } finally {
    rmSync(root, { recursive: true });
  }
}

test('preview redacts lifecycle credentials from logs and terminal output', () => {
  const settings = {
    E2E_DELETE_PASSWORD: 'test-password-with-"quote"',
    E2E_REVOKE_MOBILE_REFRESH_TOKEN: 'synthetic-refresh-value',
    E2E_DELETE_PRESS_AUTHORIZATION: 'example-key:example-secret',
  };
  const result = runPreview({ E2E_PREVIEW_READER_PASSWORD: 'test-password' }, settings);
  const { log } = result;
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /pass \[redacted\]/);
  for (const value of Object.values(settings)) {
    for (const output of [log, result.stdout, result.stderr]) {
      assert.equal(output.includes(value), false);
      assert.equal(output.includes(JSON.stringify(value).slice(1, -1)), false);
    }
  }
});

test('preview rejects a fixture with a non-text value', () => {
  const result = runPreview({ E2E_PREVIEW_READER_PASSWORD: ['test-password'] });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Invalid preview fixture/);
});

test('preview reports a launch failure as not run and keeps the other engine and API', () => {
  const result = runPreview({ E2E_PREVIEW_READER_PASSWORD: 'test-password' }, {
    TEST_CHROMIUM_UNAVAILABLE: '1',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /not_run chromium/);
  assert.match(result.stdout, /ran .*--project=webkit.*browser\.spec\.ts/);
  assert.doesNotMatch(result.stdout, /ran .*--project=chromium.*browser\.spec\.ts/);
  assert.match(result.stdout, /ran .*integration\.spec\.ts/);
});
