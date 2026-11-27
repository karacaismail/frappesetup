#!/usr/bin/env node
// Rejects new Turkish code comments. Only comments are read, never strings or names.
//
// Usage:
//   node scripts/check-comment-language.mjs                     uncommitted changes against HEAD
//   node scripts/check-comment-language.mjs --staged            staged changes only (pre-commit hook)
//   node scripts/check-comment-language.mjs --base <rev>        changes from <rev> to HEAD
//   node scripts/check-comment-language.mjs --merge-base-with <ref>
//                                                               changes since the common ancestor with <ref>
//   node scripts/check-comment-language.mjs --all               every tracked file, every line
//   --config <file>                                             exclusion list (default scripts/comment-language.config.json)
//
// Only changed lines are checked. When a changed line touches a comment, the whole
// comment block is checked. A comment may keep Turkish letters when it ends with a
// lang-ok note and a reason. The next line is an example and is counted in the report.
// Written by Müller. lang-ok: example of a German surname
// Exit code: 0 clean, 1 problems found, 2 usage or Git error.

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const TURKISH_LETTERS = /[çğıİöşüÇĞÖŞÜ]/g;

// Turkish words written without Turkish letters. Each word must not be an English word,
// so a single hit is never enough: two different list words are needed.
export const TURKISH_WORDS = new Set([
  'icin', 'degil', 'olarak', 'gore', 'eger', 'artik', 'yoksa', 'veya', 'cunku', 'sonra',
  'simdi', 'burada', 'sadece', 'yani', 'bunu', 'buna', 'boyle', 'gibi', 'kadar', 'ancak',
  'hata', 'dosya', 'satir', 'deger', 'yorum', 'eski', 'yeni', 'bir', 'iki', 'olur',
  'olsun', 'yapar', 'icinde', 'zaten', 'henuz', 'hemen', 'daha', 'ilk', 'tum', 'hic',
  'neden', 'nasil', 'olmali', 'gerekir', 'varsa', 'degilse', 'ise', 'kullanici', 'sayfa',
]);

export const EXTENSIONS = new Map([
  ['.py', 'python'],
  ['.ts', 'ts'], ['.mts', 'ts'], ['.cts', 'ts'], ['.tsx', 'tsx'],
  ['.js', 'js'], ['.mjs', 'js'], ['.cjs', 'js'], ['.jsx', 'jsx'],
  ['.css', 'css'], ['.astro', 'astro'], ['.html', 'html'], ['.sh', 'shell'],
  ['.yml', 'yaml'], ['.yaml', 'yaml'], ['.java', 'java'],
]);

export const languageOf = path => EXTENSIONS.get(extname(path).toLowerCase()) ?? null;

// ---------------------------------------------------------------- extraction

// A comment is { startLine, endLine, body, ownLine }. Lines are 1-based. body has no delimiters.
// ownLine is true when only whitespace precedes the comment on its first line.

function lineStarts(text) {
  const starts = [0];
  for (let i = 0; i < text.length; i++) if (text[i] === '\n') starts.push(i + 1);
  return starts;
}

function lineOf(starts, offset) {
  let lo = 0;
  let hi = starts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (starts[mid] <= offset) lo = mid;
    else hi = mid - 1;
  }
  return lo + 1;
}

function makeComment(text, starts, from, to, body, base = 0) {
  const lineStart = starts[lineOf(starts, from) - 1];
  return {
    startLine: lineOf(starts, from) + base,
    endLine: lineOf(starts, Math.max(from, to - 1)) + base,
    body,
    ownLine: text.slice(lineStart, from).trim() === '',
  };
}

let typescript;
function ts() {
  typescript ??= createRequire(import.meta.url)('typescript');
  return typescript;
}

function scanScript(text, flavour, base = 0) {
  const t = ts();
  const kind = { ts: t.ScriptKind.TS, tsx: t.ScriptKind.TSX, js: t.ScriptKind.JS, jsx: t.ScriptKind.JSX }[flavour];
  const source = t.createSourceFile(`file.${flavour}`, text, t.ScriptTarget.Latest, false, kind);
  const ranges = new Map();
  const jsxText = [];
  const collect = pos => {
    for (const range of [...(t.getLeadingCommentRanges(text, pos) ?? []), ...(t.getTrailingCommentRanges(text, pos) ?? [])]) {
      ranges.set(range.pos, range);
    }
  };
  const visit = node => {
    if (node.kind === t.SyntaxKind.JsxText) jsxText.push([node.pos, node.end]);
    collect(node.pos);
    collect(node.end);
    for (const child of node.getChildren(source)) visit(child);
  };
  visit(source);
  const starts = lineStarts(text);
  return [...ranges.values()]
    .filter(range => !jsxText.some(([from, to]) => range.pos >= from && range.pos < to))
    .sort((a, b) => a.pos - b.pos)
    .map(range => {
      const raw = text.slice(range.pos, range.end);
      const body = range.kind === t.SyntaxKind.SingleLineCommentTrivia ? raw.slice(2) : raw.slice(2, -2);
      return makeComment(text, starts, range.pos, range.end, body, base);
    });
}

// Block comments and line comments for C-like syntax. Strings are skipped.
function scanCLike(text, { lineComments, textBlocks = false }, base = 0) {
  const starts = lineStarts(text);
  const out = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (textBlocks && text.startsWith('"""', i)) {
      const end = text.indexOf('"""', i + 3);
      i = end < 0 ? text.length : end + 3;
    } else if (c === '"' || c === "'") {
      i++;
      while (i < text.length && text[i] !== c && text[i] !== '\n') i += text[i] === '\\' ? 2 : 1;
      i++;
    } else if (text.startsWith('/*', i)) {
      const end = text.indexOf('*/', i + 2);
      const stop = end < 0 ? text.length : end + 2;
      out.push(makeComment(text, starts, i, stop, text.slice(i + 2, end < 0 ? text.length : end), base));
      i = stop;
    } else if (lineComments && text.startsWith('//', i)) {
      let end = text.indexOf('\n', i);
      if (end < 0) end = text.length;
      out.push(makeComment(text, starts, i, end, text.slice(i + 2, end), base));
      i = end;
    } else i++;
  }
  return out;
}

const scanCss = (text, base = 0) => scanCLike(text, { lineComments: false }, base);
const scanJava = text => scanCLike(text, { lineComments: true, textBlocks: true });

const WORD_BREAK = new Set([' ', '\t', '\n', ';', '&', '|', '(', ')', '<', '>']);

// Shell: '#' starts a comment only at the start of a word and outside quotes. Here-documents are skipped.
function scanShell(text, base = 0) {
  const starts = lineStarts(text);
  const out = [];
  const heredocs = [];
  let quote = null;
  let i = text.startsWith('#!') ? text.indexOf('\n') : 0;
  if (i < 0) return out;
  while (i < text.length) {
    const c = text[i];
    if (c === '\n' && heredocs.length && !quote) {
      i++;
      while (heredocs.length && i < text.length) {
        const { tag, strip } = heredocs[0];
        let end = text.indexOf('\n', i);
        if (end < 0) end = text.length;
        const line = text.slice(i, end);
        if ((strip ? line.replace(/^\t+/, '') : line) === tag) heredocs.shift();
        i = end + 1;
      }
      continue;
    }
    if (quote === "'") {
      if (c === "'") quote = null;
      i++;
    } else if (c === '\\') {
      i += 2;
    } else if (quote === '"') {
      if (c === '"') quote = null;
      i++;
    } else if (c === "'" || c === '"') {
      quote = c;
      i++;
    } else if (text.startsWith('<<', i) && text[i + 2] !== '<') {
      const match = /^<<(-?)[ \t]*(?:'([^'\n]+)'|"([^"\n]+)"|\\?([A-Za-z_][A-Za-z0-9_]*))/.exec(text.slice(i));
      if (match) {
        heredocs.push({ strip: match[1] === '-', tag: match[2] ?? match[3] ?? match[4] });
        i += match[0].length;
      } else i += 2;
    } else if (c === '#' && (i === 0 || WORD_BREAK.has(text[i - 1]))) {
      let end = text.indexOf('\n', i);
      if (end < 0) end = text.length;
      out.push(makeComment(text, starts, i, end, text.slice(i + 1, end), base));
      i = end;
    } else i++;
  }
  return out;
}

// YAML: line based. Block scalars are not comments, except a `run:` block, which is read as shell.
function scanYaml(text) {
  const lines = text.split('\n');
  const out = [];
  const indentOf = line => line.length - line.trimStart().length;
  for (let n = 0; n < lines.length; n++) {
    const line = lines[n];
    const comment = yamlLineComment(line);
    if (comment !== null) {
      out.push({ startLine: n + 1, endLine: n + 1, body: line.slice(comment + 1), ownLine: line.slice(0, comment).trim() === '' });
    }
    const head = comment === null ? line : line.slice(0, comment);
    const block = /^(\s*)((?:- +)*)(?:([^\s#'"][^#]*?):\s+)?[|>][-+0-9]*\s*$/.exec(head);
    if (!block || (block[3] === undefined && block[2] === '')) continue;
    const keyColumn = block[1].length + (block[3] === undefined ? 0 : block[2].length);
    let end = n + 1;
    while (end < lines.length && (lines[end].trim() === '' || indentOf(lines[end]) > keyColumn)) end++;
    if (block[3]?.trim() === 'run') out.push(...scanShell(lines.slice(n + 1, end).join('\n'), n + 1));
    n = end - 1;
  }
  return out;
}

function yamlLineComment(line) {
  let quote = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quote === '"') {
      if (c === '\\') i++;
      else if (c === '"') quote = null;
    } else if (quote === "'") {
      if (c === "'") quote = null;
    } else if (c === '#' && (i === 0 || line[i - 1] === ' ' || line[i - 1] === '\t')) {
      return i;
    } else if ((c === '"' || c === "'") && /(?:^|[:,[{]|(?:^|\s)-)\s*$/.test(line.slice(0, i))) {
      // A quote only opens a quoted scalar at the start of a value.
      quote = c;
    }
  }
  return null;
}

// HTML and Astro markup: <!-- --> comments, plus script and style bodies read with their own scanner.
function scanMarkup(text, { astro }) {
  const out = [];
  const starts = lineStarts(text);
  let body = text;
  let offset = 0;
  if (astro) {
    const front = /^﻿?\s*---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text);
    if (front) {
      const from = front[0].indexOf(front[1]);
      out.push(...scanScript(front[1], 'ts', lineOf(starts, from) - 1));
      offset = front[0].length;
    }
  }
  body = text.slice(offset);
  const masked = body.split('');
  const blank = (from, to) => { for (let i = from; i < to; i++) if (masked[i] !== '\n') masked[i] = ' '; };
  for (const match of body.matchAll(/<(script|style)\b([^>]*)>([\s\S]*?)<\/\1\s*>/gi)) {
    const inner = match.index + match[0].indexOf('>') + 1;
    const base = lineOf(starts, offset + inner) - 1;
    const content = match[3];
    if (match[1].toLowerCase() === 'style') out.push(...scanCss(content, base));
    else {
      const type = /\btype\s*=\s*["']?([^"'\s>]+)/i.exec(match[2])?.[1]?.toLowerCase();
      if (!type || type === 'module' || type.includes('javascript') || type.includes('typescript')) {
        out.push(...scanScript(content, astro ? 'ts' : 'js', base));
      }
    }
    blank(match.index, match.index + match[0].length);
  }
  const rest = masked.join('');
  const pattern = astro ? /<!--([\s\S]*?)-->|\{\s*\/\*([\s\S]*?)\*\/\s*\}/g : /<!--([\s\S]*?)-->/g;
  for (const match of rest.matchAll(pattern)) {
    const from = offset + match.index;
    out.push(makeComment(text, starts, from, from + match[0].length, match[1] ?? match[2]));
  }
  return out.sort((a, b) => a.startLine - b.startLine);
}

// Python is read by its own tokenizer: `#` comments and docstrings (string statements).
const PYTHON_READER = String.raw`
import io, json, sys, tokenize
SKIP = {tokenize.NL, tokenize.COMMENT}
OPEN = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING}
def read(src):
    tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    out = []
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.COMMENT:
            out.append([tok.start[0], tok.end[0], tok.string[1:], tok.line[:tok.start[1]].strip() == ""])
        elif tok.type == tokenize.STRING:
            prev = next((t for t in reversed(tokens[:i]) if t.type not in SKIP), None)
            nxt = next((t for t in tokens[i + 1:] if t.type not in SKIP), None)
            if (prev is None or prev.type in OPEN) and (nxt is None or nxt.type in (tokenize.NEWLINE, tokenize.ENDMARKER)):
                out.append([tok.start[0], tok.end[0], tok.string, True])
    return out
result = {}
for path, src in json.loads(sys.stdin.buffer.read().decode("utf-8")).items():
    try:
        result[path] = read(src)
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        result[path] = {"error": str(exc)}
sys.stdout.write(json.dumps(result))
`;

export function readPython(files) {
  if (!Object.keys(files).length) return {};
  const run = spawnSync('python3', ['-I', '-c', PYTHON_READER], { input: JSON.stringify(files), encoding: 'utf8', maxBuffer: 1 << 28 });
  if (run.status !== 0) throw new Error(`python3 -I tokenize failed: ${run.stderr || run.error}`);
  const parsed = JSON.parse(run.stdout);
  const out = {};
  for (const [path, value] of Object.entries(parsed)) {
    out[path] = Array.isArray(value)
      ? value.map(([startLine, endLine, body, ownLine]) => ({ startLine, endLine, body, ownLine }))
      : value;
  }
  return out;
}

export function extractComments(path, text, python) {
  switch (languageOf(path)) {
    case 'python': {
      const result = (python ?? readPython({ [path]: text }))[path];
      if (!Array.isArray(result)) throw new Error(`${path}: Python tokenize failed: ${result?.error}`);
      return result;
    }
    case 'ts': case 'tsx': case 'js': case 'jsx': return scanScript(text, languageOf(path));
    case 'css': return scanCss(text);
    case 'java': return scanJava(text);
    case 'shell': return scanShell(text);
    case 'yaml': return scanYaml(text);
    case 'astro': return scanMarkup(text, { astro: true });
    case 'html': return scanMarkup(text, { astro: false });
    default: return [];
  }
}

// ---------------------------------------------------------------- rules

const maskBackticks = body => body.replace(/(`+)[\s\S]*?\1/g, span => span.replace(/[^\n]/g, ' '));

function inspect(path, comment) {
  const errors = [];
  const langOk = [...comment.body.matchAll(/\blang-ok:([^\n]*)/g)].at(-1);
  if (langOk) {
    const reason = langOk[1].replace(/(\*\/|-->|\})\s*$/, '').trim();
    if (reason) return { errors, note: { path, line: comment.startLine + countLines(comment.body, langOk.index), reason } };
    return { errors: [{ path, line: comment.startLine + countLines(comment.body, langOk.index), kind: 'lang-ok', found: [] }] };
  }
  const body = maskBackticks(comment.body);
  body.split('\n').forEach((text, n) => {
    const letters = [...new Set(text.match(TURKISH_LETTERS) ?? [])];
    if (letters.length) errors.push({ path, line: comment.startLine + n, kind: 'letter', found: letters });
  });
  if (errors.length) return { errors };
  const words = [];
  let first = null;
  for (const match of body.toLowerCase().matchAll(/[a-z]+/g)) {
    if (TURKISH_WORDS.has(match[0]) && !words.includes(match[0])) {
      words.push(match[0]);
      first ??= match.index;
    }
  }
  if (words.length >= 2) errors.push({ path, line: comment.startLine + countLines(body, first), kind: 'words', found: words });
  return { errors };
}

const countLines = (text, offset) => text.slice(0, offset).split('\n').length - 1;

// Own-line comments on consecutive lines form one block. A trailing comment is a block on its own.
function blocks(comments) {
  const out = [];
  for (const comment of [...comments].sort((a, b) => a.startLine - b.startLine)) {
    const last = out.at(-1)?.at(-1);
    if (last && comment.ownLine && last.ownLine && comment.startLine <= last.endLine + 1) out.at(-1).push(comment);
    else out.push([comment]);
  }
  return out;
}

export function checkFile(path, text, { changedLines = null, python } = {}) {
  const errors = [];
  const langOk = [];
  for (const block of blocks(extractComments(path, text, python))) {
    const touched = !changedLines || block.some(c => {
      for (let line = c.startLine; line <= c.endLine; line++) if (changedLines.has(line)) return true;
      return false;
    });
    if (!touched) continue;
    for (const comment of block) {
      const result = inspect(path, comment);
      errors.push(...result.errors);
      if (result.note) langOk.push(result.note);
    }
  }
  return { errors, langOk };
}

export function formatError({ path, line, kind, found }) {
  const list = found.map(item => `"${item}"`).join(', ');
  if (kind === 'letter') return `${path}:${line}: Turkish letter ${list} in a comment. Write the comment in English, or add "lang-ok: <reason>" for a name.`;
  if (kind === 'words') return `${path}:${line}: Turkish words ${list} in a comment. Write the comment in English.`;
  if (kind === 'lang-ok') return `${path}:${line}: "lang-ok:" needs a reason, for example "lang-ok: German surname".`;
  return `${path}:${line}: ${found.join(' ')}`;
}

// ---------------------------------------------------------------- configuration

function globToRegExp(pattern) {
  let out = '';
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i];
    if (c === '*' && pattern[i + 1] === '*') {
      if (pattern[i + 2] === '/') { out += '(?:.*/)?'; i += 2; } else { out += '.*'; i++; }
    } else if (c === '*') out += '[^/]*';
    else if (c === '?') out += '[^/]';
    else out += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${out}$`);
}

export function loadConfig(file) {
  const raw = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { exclude: [] };
  const exclude = raw.exclude ?? [];
  if (!Array.isArray(exclude)) throw new Error(`${file}: "exclude" must be a list`);
  for (const entry of exclude) {
    if (typeof entry?.pattern !== 'string' || !entry.pattern) throw new Error(`${file}: every exclusion needs a "pattern"`);
    if (typeof entry.reason !== 'string' || !entry.reason.trim()) throw new Error(`${file}: exclusion "${entry.pattern}" needs a reason`);
  }
  const patterns = exclude.map(entry => globToRegExp(entry.pattern));
  return { exclude, isExcluded: path => patterns.some(pattern => pattern.test(path)) };
}

// ---------------------------------------------------------------- Git

function git(cwd, args, { allowFail = false } = {}) {
  const run = spawnSync('git', ['-c', 'core.quotePath=false', ...args], { cwd, encoding: 'utf8', maxBuffer: 1 << 28 });
  if (run.status !== 0 && !allowFail) throw new Error(`git ${args.join(' ')} failed: ${run.stderr.trim()}`);
  return run.status === 0 ? run.stdout : null;
}

// Parses `git diff --unified=0` into a map of path to the set of added or changed lines.
export function parseDiff(diff) {
  const files = new Map();
  let current = null;
  for (const line of diff.split('\n')) {
    if (line.startsWith('+++ ')) {
      current = line === '+++ /dev/null' ? null : line.slice(6);
      if (current !== null && !files.has(current)) files.set(current, new Set());
    } else if (current !== null && line.startsWith('@@')) {
      const match = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/.exec(line);
      if (!match) continue;
      const start = Number(match[1]);
      const count = match[2] === undefined ? 1 : Number(match[2]);
      for (let n = start; n < start + count; n++) files.get(current).add(n);
    }
  }
  return files;
}

const DIFF = ['diff', '--find-renames', '--unified=0', '--diff-filter=ACMR', '--no-color', '--no-ext-diff', '--no-textconv', '--src-prefix=a/', '--dst-prefix=b/'];

function collect(top, mode) {
  if (mode.kind === 'all') {
    return git(top, ['ls-files', '-z']).split('\0').filter(Boolean)
      .map(path => ({ path, changedLines: null, read: () => readFileSync(join(top, path), 'utf8') }));
  }
  if (mode.kind === 'staged') {
    return [...parseDiff(git(top, [...DIFF, '--cached'])).entries()]
      .map(([path, changedLines]) => ({ path, changedLines, read: () => git(top, ['show', `:${path}`]) }));
  }
  if (mode.kind === 'base') {
    return [...parseDiff(git(top, [...DIFF, mode.base, 'HEAD'])).entries()]
      .map(([path, changedLines]) => ({ path, changedLines, read: () => git(top, ['show', `HEAD:${path}`]) }));
  }
  const tracked = [...parseDiff(git(top, [...DIFF, 'HEAD'])).entries()]
    .map(([path, changedLines]) => ({ path, changedLines, read: () => readFileSync(join(top, path), 'utf8') }));
  const untracked = git(top, ['ls-files', '--others', '--exclude-standard', '-z']).split('\0').filter(Boolean)
    .map(path => ({ path, changedLines: null, read: () => readFileSync(join(top, path), 'utf8') }));
  return [...tracked, ...untracked];
}

function parseArgs(argv) {
  const mode = { kind: 'worktree' };
  let config = null;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--all') mode.kind = 'all';
    else if (arg === '--staged') mode.kind = 'staged';
    else if (arg === '--base' && argv[i + 1]) { mode.kind = 'base'; mode.base = argv[++i]; }
    else if (arg === '--merge-base-with' && argv[i + 1]) { mode.kind = 'merge-base'; mode.ref = argv[++i]; }
    else if (arg === '--config' && argv[i + 1]) config = argv[++i];
    else throw new Error(`unknown argument: ${arg}`);
  }
  return { mode, config };
}

export function main(argv, { cwd = process.cwd(), out = console.log, err = console.error } = {}) {
  let options;
  let top;
  try {
    options = parseArgs(argv);
    top = git(cwd, ['rev-parse', '--show-toplevel']).trim();
    if (options.mode.kind === 'merge-base') {
      options.mode = { kind: 'base', base: git(top, ['merge-base', options.mode.ref, 'HEAD']).trim() };
    }
  } catch (error) {
    err(`comment-language: ${error.message}`);
    return 2;
  }
  const config = loadConfig(options.config ? resolve(cwd, options.config) : join(top, 'scripts/comment-language.config.json'));
  const files = collect(top, options.mode).filter(file => languageOf(file.path) && !config.isExcluded(file.path));
  const texts = new Map(files.map(file => [file.path, file.read()]));
  const python = readPython(Object.fromEntries(files.filter(f => languageOf(f.path) === 'python').map(f => [f.path, texts.get(f.path)])));
  const errors = [];
  const notes = [];
  for (const file of files) {
    try {
      const result = checkFile(file.path, texts.get(file.path), { changedLines: file.changedLines, python });
      errors.push(...result.errors);
      notes.push(...result.langOk);
    } catch (error) {
      errors.push({ path: file.path, line: 1, kind: 'parse', found: [error.message] });
    }
  }
  for (const error of errors) out(formatError(error));
  out(`lang-ok notes: ${notes.length}`);
  for (const note of notes) out(`  ${note.path}:${note.line}: ${note.reason}`);
  out(`comment-language: ${errors.length} problem(s) in ${files.length} file(s) checked.`);
  return errors.length ? 1 : 0;
}

const invoked = process.argv[1] && realpathSync(resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url));
if (invoked) process.exitCode = main(process.argv.slice(2));
