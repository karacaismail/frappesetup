import { listenOAuthCallback } from './container-network.mjs';
import { spawn } from 'node:child_process';
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { browserRunStatuses, engineFixture } from './browser-fixtures.mjs';

const worktree = resolve(process.argv[2]);
const previewDir = process.env.PREVIEW_DIR;
const fullPreview = process.env.E2E_FULL_BROWSER_FIXTURES === '1';
const containerRuntime = process.env.E2E_BROWSER_RUNTIME === 'container';
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
    .replace(/([?&](?:code|state|session_state|magickey)=)[^&\s"']+/gi, '$1[redacted]')
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

function withoutSyncSecret(settings) {
  return Object.fromEntries(Object.entries(settings).filter(([name]) => name !== 'E2E_SYNC_KEYCLOAK_SECRET'));
}

async function runPlaywright(label, args, reporter = 'list', settings = env) {
  const child = spawn(join(worktree, 'node_modules', '.bin', 'playwright'), [
    'test', '-c', 'backend/e2e/playwright.config.ts', '--reporter=' + reporter,
    '--output=' + join(previewDir, 'playwright-output', label), ...args,
  ], { cwd: worktree, env: settings });
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
  if (reporter === 'json' && (status === 0 || raw.trim())) {
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
          const result = test.results?.at(-1);
          const skipped = test.annotations?.find(({ type }) => type === 'skip');
          const outcome = {
            passed: 'pass', failed: 'fail', timedOut: 'fail', interrupted: 'fail', skipped: 'not_run',
          }[result?.status] ?? 'not_run';
          const detail = skipped?.description ?? result?.error?.message?.split('\n')[0];
          const project = test.projectName ? `[${test.projectName}] ` : '';
          const file = spec.file ? `${spec.file} · ` : '';
          const line = `${outcome} ${project}${file}${spec.title}${detail ? ` (${detail})` : ''}`;
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

async function runFullPreview(projects) {
  const ref = await request.newContext();
  try {
    const identity = 'http://identity.localhost:' + Number(process.env.PANE_PORT);
    const response = await ref.post(identity + '/realms/platform/protocol/openid-connect/token', {
      maxRedirects: 0,
      form: { grant_type: 'client_credentials', scope: 'kc-admin-api', client_id: fixture.E2E_LIFECYCLE_READER_CLIENT,
        client_secret: fixture.E2E_LIFECYCLE_READER_SECRET },
    });
    if (!response.ok()) throw new Error('Keycloak preview reader HTTP ' + response.status());
    env.E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN = (await response.json()).access_token;
    if (!env.E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN) throw new Error('Keycloak preview reader token is missing.');
    await openTenantSession('OPERATOR', 'Administrator', process.env.E2E_ADMIN_PASSWORD);
  } finally {
    await ref.dispose();
  }

  const shared = Object.fromEntries(Object.entries(env)
    .filter(([name]) => !/^E2E_(CHROMIUM|WEBKIT)_/.test(name)
      && name !== 'E2E_LIFECYCLE_READER_SECRET'
      && name !== 'E2E_SYNC_KEYCLOAK_SECRET'));
  const runs = projects.flatMap((project) => {
    const engine = project.slice('--project='.length);
    const settings = {
      ...shared, ...engineFixture(fixture, engine),
      E2E_ACCOUNT_DELETION: '1', E2E_MOBILE_SESSION_REVOKE: '1', E2E_EMPLOYEE_IDLE: '1',
      E2E_MAGIC_LINK: '1', E2E_MOBILE_PKCE: '1',
      E2E_DELETE_TENANT_READER_COOKIE: env.E2E_OPERATOR_COOKIE,
      E2E_REVOKE_ADMIN_COOKIE: env.E2E_OPERATOR_COOKIE,
      E2E_REVOKE_ADMIN_CSRF: env.E2E_OPERATOR_CSRF,
      E2E_MOBILE_SESSION_COOKIE: env.E2E_OPERATOR_COOKIE,
    };
    const idle = 'employee must authenticate again';
    return [
      runPlaywright(engine + '-idle', [project, 'lifecycle.spec.ts', '--grep', idle], 'json', settings),
      runPlaywright(engine + '-scenarios', [project, 'lifecycle.spec.ts', 'magic-link.spec.ts',
        'mobile-pkce.spec.ts', '--grep-invert', idle], 'json', settings),
    ];
  });
  return browserRunStatuses(runs, (error) => process.stderr.write(sanitize(String(error)) + '\n'));
}

try {
  const results = [];
  const projects = [];
  if (await browserAvailable('chromium', chromium)) projects.push('--project=chromium');
  else if (!fullPreview) env.E2E_CHROMIUM_UNAVAILABLE = '1';
  if (await browserAvailable('webkit', webkit)) projects.push('--project=webkit');
  if (fullPreview) {
    // A redirect can bypass Playwright routing. Accept it on loopback in either runtime.
    const callback = await listenOAuthCallback(Number(process.env.PANE_PORT) + 8);
    try {
      results.push(...await runFullPreview(projects));
    } finally {
      callback.close();
    }
    if (projects.length !== 2) results.push(1);
  } else {
    if (projects.length) {
      results.push(await runPlaywright('browser', [
        ...projects, 'browser.spec.ts', 'magic-link.spec.ts', 'mobile-pkce.spec.ts',
      ], containerRuntime ? 'json' : 'list', withoutSyncSecret(env)));
    }
    try {
      if (!containerRuntime || env.E2E_ACCOUNT_DELETION === '1' || env.E2E_MOBILE_SESSION_REVOKE === '1') {
        await openTenantSession('OPERATOR', 'Administrator', process.env.E2E_ADMIN_PASSWORD);
        env.E2E_DELETE_TENANT_READER_COOKIE ||= env.E2E_OPERATOR_COOKIE;
        env.E2E_REVOKE_ADMIN_COOKIE ||= env.E2E_OPERATOR_COOKIE;
        env.E2E_REVOKE_ADMIN_CSRF ||= env.E2E_OPERATOR_CSRF;
      }
      if (!containerRuntime) {
        await openTenantSession('READER', fixture.E2E_PREVIEW_READER_EMAIL, fixture.E2E_PREVIEW_READER_PASSWORD);
        results.push(await runPlaywright('api', ['--project=api', 'integration.spec.ts']));
      }
    } catch (error) {
      const message = 'API fixture failed: ' + sanitize(String(error)) + '\n';
      process.stderr.write(message);
      writeFileSync(join(previewDir, 'api.log'), message, { mode: 0o600 });
      results.push(1);
    }
    const lifecycleProjects = containerRuntime ? projects : ['--project=chromium'];
    if (lifecycleProjects.length) {
      results.push(await runPlaywright('lifecycle', [...lifecycleProjects, 'lifecycle.spec.ts'], 'json', withoutSyncSecret(env)));
    }
  }
  process.exitCode = results.find((code) => code !== 0) ?? 0;
} catch (error) {
  process.stderr.write(sanitize(String(error)) + '\n');
  process.exitCode = 1;
}
