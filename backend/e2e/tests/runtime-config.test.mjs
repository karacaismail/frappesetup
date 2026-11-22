import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const runtime = fileURLToPath(new URL('../preview/runtime.sh', import.meta.url));

test('preview webhook uses the Keycloak development hostname and its network alias', () => {
  const root = mkdtempSync(join(process.env.PANE_SCRATCH_DIR || tmpdir(), 'runtime-config-'));
  try {
    const worktree = join(root, 'worktree');
    const dev = join(worktree, 'backend', 'dev');
    const keycloak = join(worktree, 'backend', 'identity', 'keycloak');
    const bin = join(root, 'bin');
    for (const path of [join(dev, 'press'), keycloak, bin]) mkdirSync(path, { recursive: true });
    writeFileSync(join(dev, 'press', 'install.sh'), '');
    writeFileSync(join(dev, 'init_env.py'), '');
    writeFileSync(join(keycloak, '.env.example'), '');
    const stubs = {
      nc: 'exit 1',
      colima: 'echo "Mem: 7 2 2 0 3 5"',
      docker: `
        if [[ "$1" == --context ]]; then shift 2; fi
        case "$1 $2" in
          "context inspect") echo unix:///test.sock ;;
          "image inspect") [[ "$3" == frappe/erpnext:v16.55.0 ]] ;;
          "container inspect") echo other-project ;;
          "compose --project-name")
            if [[ "$*" == *" config --quiet" ]]; then printf '%s\\n' "$IDENTITY_SYNC_EVENTS_URL" > "$PREVIEW_DIR/webhook"; fi ;;
          "create --label")
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
    const webhook = new URL(readFileSync(join(root, 'webhook'), 'utf8').trim());
    assert.equal(webhook.protocol, 'http:');
    assert.match(webhook.hostname, /\.localhost$/);
    assert.equal(webhook.pathname, '/v1/events');
    assert.equal(readFileSync(join(root, 'alias'), 'utf8').trim(), webhook.hostname);
  } finally {
    rmSync(root, { recursive: true });
  }
});
