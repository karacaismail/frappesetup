import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const runtime = fileURLToPath(new URL('../preview/runtime.sh', import.meta.url));

test('tenant seeding and web server use the private module directory', () => {
  const script = readFileSync(runtime, 'utf8');
  const fixtures = readFileSync(new URL('../preview/fixtures.py', import.meta.url), 'utf8');
  assert.match(script, /E2E_TENANT_MODULE_DIR=.*tempfile\.mkdtemp/);
  assert.ok(script.includes('$tenant:$E2E_TENANT_MODULE_DIR/preview_site_config.py'));
  assert.ok(script.includes('PYTHONPATH="$E2E_TENANT_MODULE_DIR"'));
  assert.ok(fixtures.includes('"PYTHONPATH": os.environ["E2E_TENANT_MODULE_DIR"]'));
});

test('preview writes the fixture configuration before starting either Frappe web process', () => {
  const script = readFileSync(runtime, 'utf8');
  const fixture = script.indexOf('preview/fixtures.py" prepare');
  const webProcesses = [...script.matchAll(/exec bench serve/g)];
  assert.ok(fixture >= 0);
  assert.equal(webProcesses.length, 2);
  for (const process of webProcesses) assert.ok(process.index > fixture);
});

test('preview webhook uses the Keycloak development hostname and its network alias', () => {
  const root = mkdtempSync(join(process.env.PANE_SCRATCH_DIR || tmpdir(), 'runtime-config-'));
  try {
    const worktree = join(root, 'worktree');
    const dev = join(worktree, 'backend', 'dev');
    const keycloak = join(worktree, 'backend', 'identity', 'keycloak');
    const bin = join(root, 'bin');
    for (const path of [join(dev, 'press'), keycloak, bin]) mkdirSync(path, { recursive: true });
    writeFileSync(join(dev, 'press', 'install.sh'), '');
    copyFileSync(fileURLToPath(new URL('../../dev/init_env.py', import.meta.url)), join(dev, 'init_env.py'));
    writeFileSync(join(keycloak, '.env.example'), 'ATONOTA_SITE_TENANT1_SERVICE_SECRET=degistir-preview\n');
    const stubs = {
      nc: 'exit 1',
      colima: 'exit 17',
      docker: `
        if [[ "$1" == --context ]]; then shift 2; fi
        case "$1 $2" in
          "run --rm") printf '%s\\n' "$*" > "$PREVIEW_DIR/memory-probe"; echo "MemAvailable: 5242880 kB" ;;
          "context inspect") echo unix:///test.sock ;;
          "image inspect") [[ "$3" == frappe/erpnext:v16.55.0 ]] ;;
          "container inspect") echo other-project ;;
          "compose --project-name")
            if [[ "$*" == *" config --quiet" ]]; then printf '%s\\n' "$IDENTITY_SYNC_EVENTS_URL" > "$PREVIEW_DIR/webhook"; fi ;;
          "create --label")
            [[ -n "$ATONOTA_SITE_TENANT1_SERVICE_SECRET" ]] && touch "$PREVIEW_DIR/service-secret-in-env"
            if grep -q '^ATONOTA_SITE_TENANT1_SERVICE_SECRET=' "$PREVIEW_DIR/keycloak.env"; then
              touch "$PREVIEW_DIR/service-secret-on-disk"
            fi
            for ((index = 1; index < $#; index++)); do
              if [[ "\${!index}" == --env-file ]]; then
                next=$((index + 1))
                grep -E '^IDENTITY_SYNC_(EXECUTE|SESSION)_AZP=' "\${!next}" > "$PREVIEW_DIR/tenant-service-clients"
              fi
            done
            while [[ "$1" != --network-alias && $# -gt 1 ]]; do shift; done
            printf '%s\\n' "$2" > "$PREVIEW_DIR/alias"
            exit 42 ;;
        esac
      `,
    };
    for (const [name, script] of Object.entries(stubs)) {
      writeFileSync(join(bin, name), '#!/bin/bash\n' + script + '\n', { mode: 0o700 });
    }
    const result = spawnSync('bash', [runtime, worktree], {
      env: {
        ...process.env,
        PATH: bin + ':' + process.env.PATH,
        COLIMA_BIN: join(bin, 'colima'),
        PANE_PORT: '6500',
        FS_COLIMA_PROFILE: 'default',
        PREVIEW_DIR: root,
        PREVIEW_PROJECT: 'fs-e2e-preview-test',
      },
      encoding: 'utf8',
    });
    assert.equal(result.status, 42, result.stderr);
    assert.match(readFileSync(join(root, 'memory-probe'), 'utf8'), /--pull never --network none --read-only/);
    const webhook = new URL(readFileSync(join(root, 'webhook'), 'utf8').trim());
    assert.equal(webhook.protocol, 'http:');
    assert.equal(webhook.hostname, 'event-sink.localhost');
    assert.equal(webhook.pathname, '/v1/events');
    assert.equal(readFileSync(join(root, 'alias'), 'utf8').trim(), webhook.hostname);
    assert.equal(readFileSync(join(root, 'service-secret-in-env'), 'utf8'), '');
    assert.throws(() => readFileSync(join(root, 'service-secret-on-disk')), { code: 'ENOENT' });
    assert.deepEqual(readFileSync(join(root, 'tenant-service-clients'), 'utf8').trim().split('\n'), [
      'IDENTITY_SYNC_SESSION_AZP=site-tenant1-service',
      'IDENTITY_SYNC_EXECUTE_AZP=site-tenant1-service',
    ]);
  } finally {
    rmSync(root, { recursive: true });
  }
});
