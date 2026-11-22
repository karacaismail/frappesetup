import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
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
        post: async (url, options) => {
          if (!url.endsWith('/protocol/openid-connect/token')) return { ok: () => true };
          if (options.form.scope !== 'kc-admin-api') throw new Error('Missing admin API scope');
          return { ok: () => true, json: async () => ({ access_token: 'synthetic-reader-token' }) };
        },
        get: async () => ({ ok: () => true, text: async () => '<meta name="csrf-token" content="test-csrf">' }),
        storageState: async () => ({ cookies: [{ name: 'sid', value: 'test-session' }] }),
        dispose: async () => {},
      }) };
    `);
    writeFileSync(join(binaries, 'playwright'), `#!/usr/bin/env node
      if (process.argv.includes('browser.spec.ts') || process.argv.includes('integration.spec.ts')) {
        if (process.env.E2E_BROWSER_RUNTIME === 'container') {
          console.error('ran ' + process.argv.slice(2).join(' '));
          console.log(JSON.stringify({ suites: [] }));
        } else {
          console.log('ran ' + process.argv.slice(2).join(' '));
        }
      }
      if (process.argv.includes('lifecycle.spec.ts')) {
        if (process.env.E2E_FULL_BROWSER_FIXTURES === '1') {
          if (process.env.E2E_LIFECYCLE_READER_SECRET) process.exit(22);
          console.log(JSON.stringify({ suites: [{ specs: [{ title: process.env.E2E_MAGIC_OTP_SEED,
            tests: [{ projectName: 'webkit', results: [{ status: 'passed' }] }] }] }],
            readerToken: process.env.E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN }));
          console.error('http://identity.localhost?magickey=synthetic-mail-link');
          process.exit(0);
        }
        if (process.env.E2E_BROWSER_RUNTIME === 'container') console.error('ran ' + process.argv.slice(2).join(' '));
        console.log(JSON.stringify({ suites: [{ specs: [{ title: process.env.E2E_DELETE_PASSWORD,
          tests: [{ projectName: 'chromium', annotations: [], results: [{ status: 'passed' }] }] }] }], submitted: process.env.E2E_REVOKE_MOBILE_REFRESH_TOKEN }));
        console.error('Authorization value: ' + process.env.E2E_DELETE_PRESS_AUTHORIZATION);
      }
    `, { mode: 0o700 });
    writeFileSync(join(root, 'fixtures.json'), JSON.stringify(fixture));
    const result = spawnSync(process.execPath, [runner, root], {
      env: { ...process.env, ...settings, PANE_PORT: '4500', PREVIEW_DIR: root },
      encoding: 'utf8',
    });
    const log = readdirSync(root).filter((file) => file.endsWith('.log'))
      .map((file) => readFileSync(join(root, file), 'utf8')).join('\n');
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
  assert.match(result.stdout, /pass \[chromium\] \[redacted\]/);
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

test('container preview runs all requested files in both engines', () => {
  const result = runPreview({ E2E_PREVIEW_READER_PASSWORD: 'test-password' }, {
    E2E_BROWSER_RUNTIME: 'container',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stderr, /ran .*--project=chromium.*--project=webkit.*browser\.spec\.ts/);
  assert.match(result.stderr, /ran .*--project=chromium.*--project=webkit.*lifecycle\.spec\.ts/);
});

test('full preview requests the admin scope and redacts its credentials and magic links', () => {
  const fixture = {
    E2E_LIFECYCLE_READER_CLIENT: 'synthetic-reader',
    E2E_LIFECYCLE_READER_SECRET: 'synthetic-reader-secret',
    E2E_CHROMIUM_MAGIC_OTP_SEED: 'synthetic-otp-chromium',
    E2E_WEBKIT_MAGIC_OTP_SEED: 'synthetic-otp-webkit',
  };
  const result = runPreview(fixture, { E2E_FULL_BROWSER_FIXTURES: '1', TEST_CHROMIUM_UNAVAILABLE: '1' });
  assert.equal(result.status, 1);
  assert.match(result.stdout, /not_run chromium/);
  assert.match(result.stdout, /pass \[webkit\]/);
  assert.match(result.stderr, /magickey=\[redacted\]/);
  for (const sensitive of [...Object.values(fixture).slice(1), 'synthetic-reader-token', 'synthetic-mail-link']) {
    assert.equal((result.log + result.stdout + result.stderr).includes(sensitive), false);
  }
});
