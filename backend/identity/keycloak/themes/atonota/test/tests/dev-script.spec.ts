import { execFileSync, spawnSync } from 'node:child_process';
import { chmodSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

// The development script writes the secrets of the made-up test users into test/.env.
// These tests run a copy of the script in a temporary folder with stand-in "openssl" and "docker" commands.
// No container starts and the real .env file is not touched. No secret value is printed.

const script = fileURLToPath(new URL('../bin/theme-dev.sh', import.meta.url));
const SECRETS = ['IDENTITY_TEST_PASSWORD', 'IDENTITY_TEST_TOTP_SECRET'];

type Sandbox = { root: string; env: string; run: (command: string, openssl: 'works' | 'fails' | 'empty' | 'fails-second') => { status: number | null; output: string } };

function sandbox(): Sandbox {
  const root = mkdtempSync(join(tmpdir(), 'theme-dev-'));
  mkdirSync(join(root, 'theme', 'test', 'bin'), { recursive: true });
  mkdirSync(join(root, 'fake'));
  const copy = join(root, 'theme', 'test', 'bin', 'theme-dev.sh');
  copyFileSync(script, copy);
  chmodSync(copy, 0o755);
  // "docker" only records that it was called.
  writeFileSync(join(root, 'fake', 'docker'), `#!/bin/sh\necho called >> "${root}/docker-calls"\n`, { mode: 0o755 });
  const real = execFileSync('/bin/sh', ['-c', 'command -v openssl'], { encoding: 'utf8' }).trim();
  const run: Sandbox['run'] = (command, openssl) => {
    const bodies = {
      works: `exec "${real}" "$@"`,
      fails: 'exit 1',
      empty: 'exit 0',
      // The first call works, every later call fails.
      'fails-second': `if [ -f "${root}/openssl-used" ]; then exit 1; fi\n: > "${root}/openssl-used"\nexec "${real}" "$@"`,
    };
    rmSync(join(root, 'openssl-used'), { force: true });
    writeFileSync(join(root, 'fake', 'openssl'), `#!/bin/sh\n${bodies[openssl]}\n`, { mode: 0o755 });
    const result = spawnSync(copy, [command], { encoding: 'utf8', env: { PATH: `${join(root, 'fake')}:/usr/bin:/bin`, HOME: root } });
    return { status: result.status, output: `${result.stdout}${result.stderr}` };
  };
  return { root, env: join(root, 'theme', 'test', '.env'), run };
}

const values = (file: string) =>
  Object.fromEntries(
    readFileSync(file, 'utf8')
      .split('\n')
      .filter((line) => line.includes('='))
      .map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]),
  );

const dockerCalled = (box: Sandbox) => {
  try {
    return readFileSync(join(box.root, 'docker-calls'), 'utf8').length > 0;
  } catch {
    return false;
  }
};

test.describe('theme-dev.sh and the test secrets', () => {
  let box: Sandbox;
  test.beforeEach(() => {
    box = sandbox();
  });
  test.afterEach(() => {
    rmSync(box.root, { recursive: true, force: true });
  });

  test('"up" writes two random values, keeps the file private and prints no value', () => {
    const first = box.run('up', 'works');
    expect(first.status).toBe(0);
    const before = values(box.env);
    for (const name of SECRETS) expect(before[name], name).toMatch(/^[0-9a-f]{32}$/);
    expect(before.IDENTITY_TEST_PASSWORD).not.toBe(before.IDENTITY_TEST_TOTP_SECRET);
    expect(statSync(box.env).mode & 0o777).toBe(0o600);
    const second = box.run('up', 'works');
    const after = values(box.env);
    // Each start gets new values. Everything else stays.
    for (const name of SECRETS) expect(after[name], `${name} changes`).not.toBe(before[name]);
    expect(after.KC_BOOTSTRAP_ADMIN_PASSWORD).toBe(before.KC_BOOTSTRAP_ADMIN_PASSWORD);
    expect(after.KC_PORT).toBe(before.KC_PORT);
    for (const output of [first.output, second.output]) {
      for (const value of [...SECRETS.map((name) => before[name]), ...SECRETS.map((name) => after[name]), after.KC_BOOTSTRAP_ADMIN_PASSWORD]) {
        expect(output.includes(value), 'a secret value in the output').toBe(false);
      }
    }
  });

  for (const failure of ['fails', 'empty', 'fails-second'] as const) {
    test(`when the random generator ${failure}, "up" stops with an error and keeps the filled file`, () => {
      expect(box.run('up', 'works').status).toBe(0);
      const before = readFileSync(box.env, 'utf8');
      rmSync(join(box.root, 'docker-calls'), { force: true });
      const result = box.run('up', failure);
      expect(result.status, 'exit code').not.toBe(0);
      expect(result.output).toContain('Could not create a random test value');
      expect(readFileSync(box.env, 'utf8'), 'the filled file is unchanged').toBe(before);
      expect(dockerCalled(box), 'docker was started with broken settings').toBe(false);
    });
  }

  test('when the random generator fails on the first run, no half-written file is left', () => {
    const result = box.run('up', 'fails');
    expect(result.status).not.toBe(0);
    let content = '';
    try {
      content = readFileSync(box.env, 'utf8');
    } catch {
      content = '';
    }
    expect(content).toBe('');
    expect(dockerCalled(box)).toBe(false);
  });
});

test('the account provider is built in one place only', () => {
  // Project record, technical debt: the build step must not exist as two copies that can drift apart.
  // Every image that needs the provider calls account-provider/build.sh. No other tracked file compiles it.
  const repo = fileURLToPath(new URL('../../../../../../../', import.meta.url));
  const single = 'backend/identity/keycloak/themes/atonota/account-provider/build.sh';
  const tracked = execFileSync('git', ['-C', repo, 'ls-files', '-z', '--', 'backend'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
    .split('\0')
    .filter((file) => file && !/\.(png|woff2|jar|ico|svg|md)$/.test(file) && !file.endsWith('dev-script.spec.ts'));
  expect(tracked).toContain(single);
  const copies: string[] = [];
  for (const file of tracked) {
    if (file === single) continue;
    let text = '';
    try {
      text = readFileSync(join(repo, file), 'utf8');
    } catch {
      continue;
    }
    // Compiling Java or packing the provider jar anywhere else is a second copy of the build step.
    if (/\bjavac\b/.test(text) || /jar\s+(--create|-?cf)\b[^\n]*account-deletion-link/.test(text)) copies.push(file);
  }
  expect(copies, 'files that repeat the build step').toEqual([]);
  // The test image uses the shared script.
  const dockerfile = readFileSync(join(repo, 'backend/identity/keycloak/themes/atonota/test/Dockerfile'), 'utf8');
  expect(dockerfile).toMatch(/RUN \S*build\.sh /);
});
