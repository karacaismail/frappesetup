// press-ai indirme dosyalarını üretir: beyaz listeli, deterministik ZIP'ler ve tekil skill/agent dosyaları.
// Çıktı public/downloads/press-ai/ altına yazılır (gitignore'da); Astro onu derlemede dist'e kopyalar.
// ZIP yerleşimi depo yollarını izler: kökte LICENSE, LICENSE-CONTENT ve packages/press-ai/... Böylece belgelerdeki
// `python3 -I packages/press-ai/server.py ...` ve `--plugin-dir packages/press-ai` komutları açılan dizinde çalışır.
// Bağımlılık yok: deflate ve CRC-32 Node'un zlib modülünden (Node >= 22.2).
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { crc32, deflateRawSync } from 'node:zlib';

const PACKAGE_DIR = 'packages/press-ai';
const LICENSES = ['LICENSE', 'LICENSE-CONTENT'];
export const OUT_DIR = 'public/downloads/press-ai';

// Beyaz liste (pakete göre göreli). Listede olmayan hiçbir dosya yayımlanmaz; yeni dosya türü bilinçli eklenir.
const FULL = [
  'README.md',
  'INTERFACE.md',
  'server.py',
  '.claude-plugin/plugin.json',
  'press_ai/*.py',
  'contracts/*.json',
  'contracts/*.md',
  'contracts/press/*.json',
  'config/*.example.json',
  'skills/*/SKILL.md',
  'skills/*/references/*.md',
  'agents/*.md',
  'references/*.md',
  'tests/*.py',
  'tests/fixtures/**/*.{py,json,toml,txt,md}',
];
const MCP = [
  'README.md',
  'INTERFACE.md',
  'server.py',
  'press_ai/*.py',
  'contracts/*.json',
  'contracts/*.md',
  'contracts/press/*.json',
  'config/*.example.json',
];
const SKILL = (name) => [`skills/${name}/SKILL.md`, `skills/${name}/references/*.md`, 'references/*.md'];
// Hiçbir koşulda paketlenmeyen yollar (beyaz liste yanlış genişlese bile).
const NEVER = /(^|\/)(\.git|\.github|\.env[^/]*|__pycache__|node_modules|\.pytest_cache|\.DS_Store)(\/|$)|\.(pyc|pyo|key|pem)$/;

function globToRegExp(glob) {
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*' && glob[i + 1] === '*') {
      re += '.*';
      i++;
      if (glob[i + 1] === '/') i++;
    } else if (c === '*') re += '[^/]*';
    else if (c === '{') {
      const end = glob.indexOf('}', i);
      re += `(${glob.slice(i + 1, end).split(',').map((s) => s.replace(/[.+^$()|[\]\\]/g, '\\$&')).join('|')})`;
      i = end;
    } else re += c.replace(/[.+?^$()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${re}$`);
}

function walk(dir, base = dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    const rel = relative(base, full).split('\\').join('/');
    if (NEVER.test(rel)) continue;
    if (statSync(full).isDirectory()) out.push(...walk(full, base));
    else out.push(rel);
  }
  return out;
}

const select = (files, globs) => {
  const res = globs.map(globToRegExp);
  return files.filter((f) => res.some((r) => r.test(f)));
};

// DOS tarih/saat 1980-01-01 00:00 (sabit), Unix 0644 normal dosya, UTF-8 adlar, deflate.
const DOS_DATE = 0x0021;
const MODE = (0o100644 << 16) >>> 0;

/** Sıralı girdilerden deterministik ZIP (yalnız dosyalar; dizinleri açıcı oluşturur). */
export function zip(entries) {
  const locals = [];
  const central = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const nameBuf = Buffer.from(name, 'utf8');
    const comp = deflateRawSync(data, { level: 9 });
    const crc = crc32(data) >>> 0;
    const head = Buffer.alloc(30);
    head.writeUInt32LE(0x04034b50, 0);
    head.writeUInt16LE(20, 4);
    head.writeUInt16LE(0x0800, 6);
    head.writeUInt16LE(8, 8);
    head.writeUInt16LE(0, 10);
    head.writeUInt16LE(DOS_DATE, 12);
    head.writeUInt32LE(crc, 14);
    head.writeUInt32LE(comp.length, 18);
    head.writeUInt32LE(data.length, 22);
    head.writeUInt16LE(nameBuf.length, 26);
    head.writeUInt16LE(0, 28);
    locals.push(head, nameBuf, comp);
    const cd = Buffer.alloc(46);
    cd.writeUInt32LE(0x02014b50, 0);
    cd.writeUInt16LE((3 << 8) | 20, 4);
    cd.writeUInt16LE(20, 6);
    cd.writeUInt16LE(0x0800, 8);
    cd.writeUInt16LE(8, 10);
    cd.writeUInt16LE(0, 12);
    cd.writeUInt16LE(DOS_DATE, 14);
    cd.writeUInt32LE(crc, 16);
    cd.writeUInt32LE(comp.length, 20);
    cd.writeUInt32LE(data.length, 24);
    cd.writeUInt16LE(nameBuf.length, 28);
    cd.writeUInt32LE(MODE, 38);
    cd.writeUInt32LE(offset, 42);
    central.push(cd, nameBuf);
    offset += head.length + nameBuf.length + comp.length;
  }
  const size = central.reduce((n, b) => n + b.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(size, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, ...central, end]);
}

const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');

/** Tüm indirme dosyalarını `root/OUT_DIR` altına yeniden üretir ve manifesti döndürür. */
export function generatePressAiDownloads(root) {
  const pkgDir = join(root, PACKAGE_DIR);
  const out = join(root, OUT_DIR);
  const tree = walk(pkgDir);
  const licenses = LICENSES.map((name) => ({ name, data: readFileSync(join(root, name)) }));
  const fromPackage = (files) => files.map((f) => ({ name: `${PACKAGE_DIR}/${f}`, data: readFileSync(join(pkgDir, f)) }));
  const archive = (files) =>
    zip([...licenses, ...fromPackage(files)].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0)));

  const skills = tree.filter((f) => /^skills\/[^/]+\/SKILL\.md$/.test(f)).map((f) => f.split('/')[1]);
  const agents = tree.filter((f) => /^agents\/[^/]+\.md$/.test(f)).map((f) => f.slice('agents/'.length, -3));
  const plugin = JSON.parse(readFileSync(join(pkgDir, '.claude-plugin/plugin.json'), 'utf8'));

  const artifacts = [
    { kind: 'package', name: 'press-ai', path: 'press-ai.zip', files: select(tree, FULL) },
    { kind: 'mcp', name: 'press-ai', path: 'press-ai-mcp.zip', files: select(tree, MCP) },
    ...skills.map((s) => ({ kind: 'skill-zip', name: s, path: `press-ai-skill-${s}.zip`, files: select(tree, SKILL(s)) })),
    ...skills.map((s) => ({ kind: 'skill-file', name: s, path: `files/skills/${s}/SKILL.md`, save: 'SKILL.md', source: `skills/${s}/SKILL.md` })),
    ...agents.map((a) => ({ kind: 'agent-file', name: a, path: `files/agents/${a}.md`, save: `${a}.md`, source: `agents/${a}.md` })),
  ];

  rmSync(out, { recursive: true, force: true });
  const manifest = { package: plugin.name, version: plugin.version, files: [] };
  for (const a of artifacts) {
    const body = a.files ? archive(a.files) : readFileSync(join(pkgDir, a.source));
    const target = join(out, a.path);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, body);
    manifest.files.push({
      kind: a.kind,
      name: a.name,
      path: a.path,
      save: a.save ?? a.path,
      bytes: body.length,
      sha256: sha256(body),
      ...(a.files ? { entries: a.files.length + licenses.length } : {}),
    });
  }
  const sums = [...manifest.files]
    .sort((a, b) => (a.path < b.path ? -1 : 1))
    .map((f) => `${f.sha256}  ${f.path}`)
    .join('\n');
  writeFileSync(join(out, 'SHA256SUMS'), `${sums}\n`);
  writeFileSync(join(out, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  return manifest;
}

/** Bileşenler için: derlemede üretilmiş manifest (proje kökü = Astro'nun çalışma dizini). */
export function readPressAiManifest(root = process.cwd()) {
  return JSON.parse(readFileSync(join(root, OUT_DIR, 'manifest.json'), 'utf8'));
}

/** Astro entegrasyonu: dev, build ve preview başlarken indirme dosyalarını yeniden üretir. */
export function pressAiDownloads() {
  return {
    name: 'press-ai-downloads',
    hooks: {
      'astro:config:setup': ({ config, logger }) => {
        const m = generatePressAiDownloads(fileURLToPath(config.root));
        logger.info(`${m.files.length} indirme dosyası üretildi (${OUT_DIR})`);
      },
    },
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const m = generatePressAiDownloads(process.cwd());
  for (const f of m.files) console.log(`${f.sha256.slice(0, 12)}  ${String(f.bytes).padStart(7)}  ${f.path}`);
}
