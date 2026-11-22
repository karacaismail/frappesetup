import { spawn } from 'node:child_process';
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';

const worktree = resolve(process.argv[2]);
const previewDir = process.env.PREVIEW_DIR;
const require = createRequire(join(worktree, 'package.json'));
const { chromium, request, webkit } = require('@playwright/test');
const fixture = readFixture(join(previewDir, 'fixtures.json'));
const tenant = 'http://tenant1.localhost:' + (Number(process.env.PANE_PORT) + 1);
const credentialName = /(?:^|_)(?:AUTHORIZATION|COOKIE|CSRF|PASSWORD|SECRET|SEED|TOKEN)(?:_|$)/;

const env = {
  ...process.env,
  ...fixture,
  IDENTITY_SYNC_WEBHOOK_SECRET: process.env.E2E_IDENTITY_SYNC_WEBHOOK_SECRET,
};
for (const name of [
  'E2E_ADMIN_PASSWORD', 'E2E_KEYCLOAK_ADMIN_PASSWORD', 'E2E_KEYCLOAK_CLIENT_SECRET',
  'ATONOTA_SITE_TENANT1_SERVICE_SECRET', 'E2E_KEYCLOAK_SERVICE_CLIENT_SECRET', 'E2E_PREVIEW_READER_PASSWORD', 'E2E_PRESS_ADMIN_PASSWORD', 'E2E_PRESS_CLIENT_SECRET',
  'E2E_CHROMIUM_UNAVAILABLE',
]) delete env[name];

function readFixture(path) {
  try {
    const file = statSync(path);
    if (file.isFile() && file.size <= 64 * 1024) {
      const data = JSON.parse(readFileSync(path, 'utf8'));
      if (data && Object.getPrototypeOf(data) === Object.prototype
        && Object.entries(data).every(([key, value]) => /^E2E_[A-Z0-9_]+$/.test(key)
          && typeof value === 'string' && !value.includes('\0'))) {
        return data;
      }
    }
  } catch {
    // Do not print input contents or parser errors.
  }
  throw new Error('Invalid preview fixture.');
}

async function openTenantSession(role, username, password) {
  const client = await request.newContext();
  try {
    const login = await client.post(tenant + '/api/method/login', {
      data: { usr: username, pwd: password }, maxRedirects: 0,
    });
    if (!login.ok()) throw new Error(role + ' login HTTP ' + login.status());
    const panel = await client.get(tenant + '/panel', { maxRedirects: 0 });
    if (!panel.ok()) throw new Error(role + ' panel HTTP ' + panel.status());
    const token = /<meta name="csrf-token" content="([^"]+)"/.exec(await panel.text())?.[1];
    const { cookies } = await client.storageState();
    const sid = cookies.find((cookie) => cookie.name === 'sid');
    if (!token || !sid || sid.value === 'Guest') throw new Error(role + ' session fixture is incomplete');
    env['E2E_' + role + '_COOKIE'] = 'sid=' + sid.value;
    env['E2E_' + role + '_CSRF'] = token;
  } finally {
    await client.dispose();
  }
}

function sanitize(raw) {
  const credentials = new Set();
  for (const settings of [process.env, fixture, env]) {
    for (const [name, value] of Object.entries(settings)) {
      if (credentialName.test(name) && typeof value === 'string' && value) {
        credentials.add(value);
        credentials.add(JSON.stringify(value).slice(1, -1));
      }
    }
  }
  for (const value of [...credentials].sort((left, right) => right.length - left.length)) {
    raw = raw.replaceAll(value, '[redacted]');
  }
  return raw
    .replace(/([?&](?:code|state|session_state)=)[^&\s"']+/gi, '$1[redacted]')
    .replace(/(authorization:\s*(?:Bearer|Basic|token)\s+)[^\s"']+/gi, '$1[redacted]')
    .replace(/(\bsid=|x-frappe-csrf-token:\s*)[^;\s"']+/gi, '$1[redacted]');
}

async function browserAvailable(engine, browserType) {
  let browser;
  const browserEnv = Object.fromEntries(Object.entries(process.env).filter(([name]) => !credentialName.test(name)));
  try {
    browser = await browserType.launch({ timeout: 10000, env: browserEnv });
  } catch (error) {
    const output = sanitize(String(error));
    writeFileSync(join(previewDir, engine + '-launch.log'), output + '\n', { mode: 0o600 });
    process.stdout.write(`not_run ${engine} (browser launch failed)\n`);
    return false;
  }
  await browser.close();
  return true;
}

async function runPlaywright(label, args, reporter = 'list') {
  const child = spawn(join(worktree, 'node_modules', '.bin', 'playwright'), [
    'test', '-c', 'backend/e2e/playwright.config.ts', '--reporter=' + reporter,
    '--output=' + join(previewDir, label), ...args,
  ], { cwd: worktree, env });
  const output = [];
  const errors = [];
  child.stdout.setEncoding('utf8').on('data', (chunk) => output.push(chunk));
  child.stderr.setEncoding('utf8').on('data', (chunk) => errors.push(chunk));
  const status = await new Promise((done, reject) => {
    child.on('error', reject);
    child.on('close', (code) => done(code ?? 1));
  });
  const raw = output.join('');
  const safe = sanitize(raw);
  const safeErrors = sanitize(errors.join(''));
  writeFileSync(join(previewDir, label + '.log'), safe + safeErrors, { mode: 0o600 });
  if (reporter === 'json' && status === 0) {
    let pending;
    try {
      pending = [...JSON.parse(raw).suites];
    } catch {
      throw new Error('Invalid Playwright JSON report.');
    }
    while (pending.length) {
      const suite = pending.pop();
      pending.push(...(suite.suites ?? []));
      for (const spec of suite.specs ?? []) {
        for (const test of spec.tests) {
          const skipped = test.annotations?.find(({ type }) => type === 'skip');
          const line = skipped ? `not_run ${spec.title} (${skipped.description})` : `pass ${spec.title}`;
          process.stdout.write(sanitize(line) + '\n');
        }
      }
    }
  } else {
    process.stdout.write(safe);
  }
  process.stderr.write(safeErrors);
  return status;
}

try {
  const results = [];
  const projects = [];
  if (await browserAvailable('chromium', chromium)) projects.push('--project=chromium');
  else env.E2E_CHROMIUM_UNAVAILABLE = '1';
  if (await browserAvailable('webkit', webkit)) projects.push('--project=webkit');
  if (projects.length) {
    results.push(await runPlaywright('browser', [
      ...projects, 'browser.spec.ts', 'magic-link.spec.ts', 'mobile-pkce.spec.ts',
    ]));
  }
  try {
    await openTenantSession('OPERATOR', 'Administrator', process.env.E2E_ADMIN_PASSWORD);
    env.E2E_DELETE_TENANT_READER_COOKIE ||= env.E2E_OPERATOR_COOKIE;
    env.E2E_REVOKE_ADMIN_COOKIE ||= env.E2E_OPERATOR_COOKIE;
    env.E2E_REVOKE_ADMIN_CSRF ||= env.E2E_OPERATOR_CSRF;
    await openTenantSession('READER', fixture.E2E_PREVIEW_READER_EMAIL, fixture.E2E_PREVIEW_READER_PASSWORD);
    results.push(await runPlaywright('api', ['--project=api', 'integration.spec.ts']));
  } catch (error) {
    const message = 'API fixture failed: ' + sanitize(String(error)) + '\n';
    process.stderr.write(message);
    writeFileSync(join(previewDir, 'api.log'), message, { mode: 0o600 });
    results.push(1);
  }
  results.push(await runPlaywright('lifecycle', ['--project=chromium', 'lifecycle.spec.ts'], 'json'));
  process.exitCode = results.find((code) => code !== 0) ?? 0;
} catch (error) {
  process.stderr.write(sanitize(String(error)) + '\n');
  process.exitCode = 1;
}
