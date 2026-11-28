#!/usr/bin/env node
// Installs the comment-language pre-commit hook into <git-common-dir>/hooks.
// The personal author guard runs that project hook first, so core.hooksPath stays unchanged.
// The hook checks only the staged change. CI is still the real gate.

import { spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const MARKER = '# comment-language-hook';
const HOOK = `#!/bin/sh
${MARKER}: installed by scripts/install-comment-hook.mjs
top=$(git rev-parse --show-toplevel) || exit 1
script="$top/scripts/check-comment-language.mjs"
# Branches without the check have nothing to run.
[ -f "$script" ] || exit 0
if ! command -v node >/dev/null 2>&1; then
  echo "comment-language: node not found, the hook was skipped. CI still runs the check." >&2
  exit 0
fi
exec node "$script" --staged
`;

const run = spawnSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], { encoding: 'utf8' });
if (run.status !== 0) {
  console.error(`install-comment-hook: not a Git repository. ${run.stderr.trim()}`);
  process.exit(2);
}
const hooks = join(run.stdout.trim(), 'hooks');
const target = join(hooks, 'pre-commit');
if (existsSync(target) && !readFileSync(target, 'utf8').includes(MARKER)) {
  console.error(`install-comment-hook: ${target} already exists and was not written by this script. Nothing was changed.`);
  console.error('Add this line to that hook instead: node "$(git rev-parse --show-toplevel)/scripts/check-comment-language.mjs" --staged || exit 1');
  process.exit(1);
}
mkdirSync(hooks, { recursive: true });
writeFileSync(target, HOOK);
chmodSync(target, 0o755);
console.log(`install-comment-hook: wrote ${target}`);
