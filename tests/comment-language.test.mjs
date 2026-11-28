import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { checkFile, extractComments, formatError, loadConfig } from '../scripts/check-comment-language.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const fixtures = join(root, 'tests/comment-language/fixtures');
const script = join(root, 'scripts/check-comment-language.mjs');
const installer = join(root, 'scripts/install-comment-hook.mjs');

const check = (path, text, options = {}) => checkFile(path, text, options);
const read = (lang, name) => readFileSync(join(fixtures, lang, name), 'utf8');

// Every supported language has a Turkish sample that fails and an English sample that passes.
for (const lang of readdirSync(fixtures)) {
  const files = readdirSync(join(fixtures, lang));
  const tr = files.find(name => name.startsWith('tr.'));
  const en = files.find(name => name.startsWith('en.'));

  test(`${lang}: a Turkish comment fails`, () => {
    const { errors } = check(`${lang}/${tr}`, read(lang, tr));
    assert.ok(errors.length > 0, `no error for ${lang}/${tr}`);
    assert.ok(errors.every(error => error.kind === 'letter' || error.kind === 'words'));
  });

  test(`${lang}: English comments and Turkish code text pass`, () => {
    const { errors } = check(`${lang}/${en}`, read(lang, en));
    assert.deepEqual(errors.map(formatError), []);
  });
}

test('Python docstrings count as comments and are read with tokenize', () => {
  const { errors } = check('py/tr.py', read('py', 'tr.py'));
  assert.deepEqual(errors.map(error => error.line), [5, 8]);
  const comments = extractComments('a.py', 'x = "# ş"\n');
  assert.deepEqual(comments, []);
});

test('a YAML run block is read as shell', () => {
  const { errors } = check('yml/tr.yml', read('yml', 'tr.yml'));
  assert.deepEqual(errors.map(error => error.line), [1, 8]);
});

test('two list words without Turkish letters fail, one word passes', () => {
  const two = check('a.ts', '// bu alan icin degil\nexport {};\n');
  assert.equal(two.errors.length, 1);
  assert.equal(two.errors[0].kind, 'words');
  assert.deepEqual(two.errors[0].found, ['icin', 'degil']);
  assert.deepEqual(check('a.ts', '// sent icin review\n').errors, []);
  assert.deepEqual(check('a.ts', '// Run once, or once more\n').errors, []);
  assert.equal(check('a.py', '# eger dosya yoksa\n').errors.length, 1);
});

test('lang-ok with a reason passes and is counted, without a reason fails', () => {
  const ok = check('a.ts', '// Author: Müller. lang-ok: German surname\nexport {};\n');
  assert.deepEqual(ok.errors, []);
  assert.equal(ok.langOk.length, 1);
  assert.equal(ok.langOk[0].reason, 'German surname');
  assert.equal(check('a.ts', '// Author: Müller\n').errors.length, 1);
  const empty = check('a.ts', '// Author: Müller lang-ok:\n');
  assert.equal(empty.errors.length, 1);
  assert.equal(empty.errors[0].kind, 'lang-ok');
});

test('backtick spans are skipped, double quotes are not', () => {
  assert.deepEqual(check('a.ts', '// Clicks the `Kaydet` button\n').errors, []);
  assert.deepEqual(check('a.py', '# Uses ``Değer`` from the API\n').errors, []);
  const quoted = check('a.ts', '// Shows the "Değer" label\n');
  assert.equal(quoted.errors.length, 1);
  assert.deepEqual(quoted.errors[0].found, ['ğ']);
});

test('string // and regex # are not comments', () => {
  assert.deepEqual(extractComments('a.js', 'const u = "http://x // ş";\nconst r = /#ş/;\n'), []);
  assert.deepEqual(extractComments('a.py', 'import re\nr = re.compile(r"#ş")\ns = "// ç"\n'), []);
  assert.deepEqual(extractComments('a.sh', 'echo "# ş" ${#x} $#\n'), []);
  assert.deepEqual(extractComments('a.yml', 'url: https://site/sayfa#bolum\n'), []);
});

test('only changed lines are checked, a touched comment is checked as a whole block', () => {
  const text = '// Eski yorum: değer\n// eski yorum: ölçü\nexport const a = 1;\n\n// New English note\nexport const b = 2;\n';
  assert.deepEqual(check('a.ts', text, { changedLines: new Set([5, 6]) }).errors, []);
  const touched = check('a.ts', text, { changedLines: new Set([2]) });
  assert.deepEqual(touched.errors.map(error => error.line), [1, 2]);
  const trailing = 'const a = 1; // açık\nconst b = 2; // kapalı\n';
  assert.deepEqual(check('a.ts', trailing, { changedLines: new Set([2]) }).errors.map(error => error.line), [2]);
});

test('the error message shows path, line and what was found', () => {
  const [error] = check('src/a.ts', 'export {};\n// Değer\n').errors;
  const message = formatError(error);
  assert.match(message, /^src\/a\.ts:2: /);
  assert.match(message, /ğ/);
  const [words] = check('src/a.ts', '// bu alan icin degil\n').errors;
  assert.match(formatError(words), /^src\/a\.ts:1: .*icin.*degil/);
});

test('every exclusion has a reason, and fixtures are excluded', () => {
  const config = loadConfig(join(root, 'scripts/comment-language.config.json'));
  assert.ok(config.exclude.length > 0);
  for (const entry of config.exclude) assert.ok(entry.pattern && entry.reason, JSON.stringify(entry));
  assert.ok(config.isExcluded('tests/comment-language/fixtures/py/tr.py'));
  assert.ok(config.isExcluded('node_modules/x/index.js'));
  assert.ok(config.isExcluded('src/content/docs/a.md'));
  assert.ok(!config.isExcluded('scripts/check-comment-language.mjs'));
  assert.ok(!config.isExcluded('tests/comment-language.test.mjs'));
  const dir = mkdtempSync(join(tmpdir(), 'comment-config-'));
  writeFileSync(join(dir, 'bad.json'), JSON.stringify({ exclude: [{ pattern: 'dist/**' }] }));
  assert.throws(() => loadConfig(join(dir, 'bad.json')), /reason/);
});

function git(cwd, ...args) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim();
}

function repo() {
  const dir = mkdtempSync(join(tmpdir(), 'comment-lang-'));
  git(dir, 'init', '-q', '-b', 'main');
  git(dir, 'config', 'user.name', 'karacaismail');
  git(dir, 'config', 'user.email', '35493655+karacaismail@users.noreply.github.com');
  mkdirSync(join(dir, 'scripts'));
  writeFileSync(join(dir, 'scripts/comment-language.config.json'), JSON.stringify({ exclude: [{ pattern: 'vendor/**', reason: 'test vendor code' }] }));
  writeFileSync(join(dir, 'a.ts'), '// Eski Türkçe yorum\nexport const a = 1;\n');
  writeFileSync(join(dir, 'b.py'), 'x = 1\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-q', '-m', 'base');
  return dir;
}

function run(cwd, ...args) {
  return spawnSync(process.execPath, [script, ...args], { cwd, encoding: 'utf8' });
}

test('CLI: old untouched Turkish comments do not fail, new ones do', () => {
  const dir = repo();
  const base = git(dir, 'rev-parse', 'HEAD');
  writeFileSync(join(dir, 'a.ts'), '// Eski Türkçe yorum\nexport const a = 1;\n// New English note\nexport const b = 2;\n');
  git(dir, 'commit', '-qam', 'english');
  let result = run(dir, '--base', base);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  writeFileSync(join(dir, 'b.py'), 'x = 1\n# Yeni yorum: değer\n');
  mkdirSync(join(dir, 'vendor'));
  writeFileSync(join(dir, 'vendor/c.js'), '// Dış kod\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-qm', 'turkish');
  result = run(dir, '--base', base);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /b\.py:2: .*ğ/);
  assert.doesNotMatch(result.stdout, /a\.ts|vendor/);
  result = run(dir, '--all');
  assert.equal(result.status, 1);
  assert.match(result.stdout, /a\.ts:1: /);
});

test('CLI: --merge-base-with uses the common ancestor', () => {
  const dir = repo();
  git(dir, 'checkout', '-qb', 'feature');
  writeFileSync(join(dir, 'c.mjs'), '// Yeni modül\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-qm', 'feature');
  git(dir, 'checkout', '-q', 'main');
  writeFileSync(join(dir, 'd.mjs'), '// Ana dalda başka iş\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-qm', 'main moves');
  git(dir, 'checkout', '-q', 'feature');
  const result = run(dir, '--merge-base-with', 'main');
  assert.equal(result.status, 1);
  assert.match(result.stdout, /c\.mjs:1: /);
  assert.doesNotMatch(result.stdout, /d\.mjs/);
});

test('CLI: --staged checks only the staged content', () => {
  const dir = repo();
  writeFileSync(join(dir, 'b.py'), 'x = 1\n# Staged English note\n');
  git(dir, 'add', 'b.py');
  writeFileSync(join(dir, 'b.py'), 'x = 1\n# Hazırlanmamış değişiklik\n');
  let result = run(dir, '--staged');
  assert.equal(result.status, 0, result.stdout + result.stderr);
  git(dir, 'add', 'b.py');
  result = run(dir, '--staged');
  assert.equal(result.status, 1);
  assert.match(result.stdout, /b\.py:2: /);
});

test('CLI: lang-ok notes are counted in the report', () => {
  const dir = repo();
  const base = git(dir, 'rev-parse', 'HEAD');
  writeFileSync(join(dir, 'e.ts'), '// Written by Müller. lang-ok: German surname\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-qm', 'note');
  const result = run(dir, '--base', base);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /lang-ok notes: 1/);
  assert.match(result.stdout, /e\.ts:1: German surname/);
});

test('hook installer writes the project hook without touching core.hooksPath', () => {
  const dir = repo();
  const before = spawnSync('git', ['config', '--local', '--get', 'core.hooksPath'], { cwd: dir, encoding: 'utf8' }).stdout;
  const hooks = join(git(dir, 'rev-parse', '--path-format=absolute', '--git-common-dir'), 'hooks');
  let result = spawnSync(process.execPath, [installer], { cwd: dir, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(spawnSync('git', ['config', '--local', '--get', 'core.hooksPath'], { cwd: dir, encoding: 'utf8' }).stdout, before);
  const hook = readFileSync(join(hooks, 'pre-commit'), 'utf8');
  assert.match(hook, /check-comment-language\.mjs/);
  assert.match(hook, /--staged/);
  result = spawnSync(process.execPath, [installer], { cwd: dir, encoding: 'utf8' });
  assert.equal(result.status, 0, 'reinstalling our own hook is allowed');
  writeFileSync(join(hooks, 'pre-commit'), '#!/bin/sh\necho other\n');
  chmodSync(join(hooks, 'pre-commit'), 0o755);
  result = spawnSync(process.execPath, [installer], { cwd: dir, encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.equal(readFileSync(join(hooks, 'pre-commit'), 'utf8'), '#!/bin/sh\necho other\n');
});

test('the installed hook rejects a staged Turkish comment', () => {
  const dir = repo();
  const hooks = join(git(dir, 'rev-parse', '--path-format=absolute', '--git-common-dir'), 'hooks');
  mkdirSync(join(dir, 'scripts'), { recursive: true });
  writeFileSync(join(dir, 'scripts/check-comment-language.mjs'), readFileSync(script));
  spawnSync(process.execPath, [installer], { cwd: dir, encoding: 'utf8' });
  assert.ok(existsSync(join(hooks, 'pre-commit')));
  writeFileSync(join(dir, 'f.ts'), '// Yeni değer\n');
  git(dir, 'add', 'f.ts');
  symlinkSync(join(root, 'node_modules'), join(dir, 'node_modules'));
  const result = spawnSync(join(hooks, 'pre-commit'), [], { cwd: dir, encoding: 'utf8' });
  assert.equal(result.status, 1, result.stdout + result.stderr);
  assert.match(result.stdout, /f\.ts:1: /);
});

test('package.json pins typescript and exposes lint:comments', () => {
  const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  assert.match(pkg.devDependencies.typescript, /^\d+\.\d+\.\d+$/);
  assert.match(pkg.scripts['lint:comments'], /check-comment-language\.mjs/);
});

for (const [file, aggregator] of [['ci.yml', 'build-and-test'], ['deploy.yml', 'build']]) {
  test(`${file} runs comment-language and the aggregator waits for it`, () => {
    const text = readFileSync(join(root, '.github/workflows', file), 'utf8');
    assert.match(text, /^ {2}comment-language:\n/m);
    const job = text.split(/^ {2}comment-language:\n/m)[1].split(/^ {2}\S/m)[0];
    assert.match(job, /fetch-depth: 0/);
    assert.match(job, /npm run lint:comments|check-comment-language\.mjs/);
    const block = text.split(new RegExp(`^ {2}${aggregator}:\\n`, 'm'))[1].split(/^ {2}\S/m)[0];
    assert.match(block, /needs: \[[^\]]*\bcomment-language\b[^\]]*\]/);
    assert.match(block, /if: \$\{\{ always\(\)/);
  });
}

test('review fixes: the word rule counts across a block of line comments', () => {
  const result = check('a.py', '# Bu ayar icin\n# boyle yapildi\nx = 1\n');
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].line, 1);
  assert.deepEqual(result.errors[0].found, ['icin', 'boyle']);
  assert.deepEqual(check('a.py', 'x = 1  # icin\ny = 2  # boyle\n').errors, []);
});

test('review fixes: an empty lang-ok in a docstring fails', () => {
  const result = check('a.py', 'def f():\n    """Müller lang-ok:"""\n');
  assert.equal(result.errors.length, 1);
  assert.equal(result.errors[0].kind, 'lang-ok');
});

test('review fixes: shell arithmetic shifts are not here-documents', () => {
  const comments = extractComments('a.sh', 'n=$((1<<x))\n# Yorum değer\nx\n');
  assert.deepEqual(comments.map(c => c.startLine), [2]);
});

test('review fixes: script and style line numbers in markup', () => {
  const text = '<p>x</p>\n<script>\n  const a = 1;\n  // Değer\n</script>\n<style>\n  /* Başlık */\n</style>\n';
  assert.deepEqual(check('a.html', text).errors.map(e => e.line), [4, 7]);
  assert.deepEqual(check('a.astro', `---\nconst a = 1;\n---\n${text}`).errors.map(e => e.line), [7, 10]);
});

test('review fixes: diff parsing keeps odd paths and content lines that look like headers', () => {
  const dir = repo();
  const base = git(dir, 'rev-parse', 'HEAD');
  writeFileSync(join(dir, 'with space.ts'), '// Boşluklu yol\n');
  writeFileSync(join(dir, 'notes.md'), '++ not a header\n+++ still not a header\n');
  writeFileSync(join(dir, 'z.ts'), 'export {};\n// Son değer\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-qm', 'odd');
  const result = run(dir, '--base', base);
  assert.equal(result.status, 1, result.stdout + result.stderr);
  assert.match(result.stdout, /^with space\.ts:1: /m);
  assert.match(result.stdout, /^z\.ts:2: /m);
});

test('review fixes: the message explains backticks and lang-ok', () => {
  const [error] = check('a.ts', '// uses yeni_deger icin\n').errors;
  assert.match(formatError(error), /backticks/);
});
