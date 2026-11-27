#!/usr/bin/env node
// Ortak kural klasöründeki kopyaları depodaki docs/standartlar/ dosyalarıyla karşılaştırır.
// Yalnız iki tarafta da bulunan dosyalar karşılaştırılır.
// Çıkış kodu: 0 hepsi aynı, 1 fark var, 2 komut hatası.
//
// Kullanım:
//   node scripts/check-shared-standards.mjs [--ref origin/main] [--dir <ortak klasör>]
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
function option(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}

const ref = option('--ref', 'origin/main');
const dir = option('--dir', join(homedir(), '.claude/skills/coding-standards/references'));
const repoDir = 'docs/standartlar';

function git(gitArgs, encoding = 'utf8') {
  return execFileSync('git', gitArgs, { encoding, maxBuffer: 64 * 1024 * 1024 });
}

let names;
try {
  names = git(['ls-tree', '--name-only', `${ref}:${repoDir}`])
    .split('\n')
    .filter(Boolean);
} catch (error) {
  console.error(`HATA: ${ref}:${repoDir} okunamadı. ${error.message}`);
  process.exit(2);
}
if (!existsSync(dir)) {
  console.error(`HATA: ortak klasör yok: ${dir}`);
  process.exit(2);
}

const shared = names.filter((name) => existsSync(join(dir, name)));
if (shared.length === 0) {
  console.error('HATA: karşılaştırılacak ortak dosya bulunamadı.');
  process.exit(2);
}

let failed = 0;
for (const name of shared) {
  const repoBytes = git(['show', `${ref}:${repoDir}/${name}`], 'buffer');
  const localBytes = readFileSync(join(dir, name));
  if (Buffer.compare(repoBytes, localBytes) === 0) {
    console.log(`AYNI   ${name}`);
  } else {
    failed += 1;
    console.log(`FARKLI ${name}`);
  }
}

console.log(`Kaynak: ${ref}:${repoDir}`);
console.log(`Ortak klasör: ${dir}`);
console.log(`${shared.length} dosya karşılaştırıldı. ${failed} dosya farklı.`);
process.exit(failed > 0 ? 1 : 0);
