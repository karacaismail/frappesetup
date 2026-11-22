// ProPR'ın yerel servislerini ProPR'ın kendi başlatma koduyla yeniden kurar.
// .env dosyası değişince bu betiği çalıştırın. `docker restart` bazı ayarları okumaz.
// Belge ve tünel servisleri kapalı kalır.
import { homedir } from 'node:os';
import { join } from 'node:path';

const resources = '/Applications/propr-desktop.app/Contents/Resources';
const home = homedir();
process.env.DOCKER_HOST ??= `unix://${join(home, '.colima/propr/docker.sock')}`;
process.env.DOCKER_CONFIG ??= join(home, '.config/propr-docker');

const { resolveHostConfig, startStack } = await import(join(resources, 'orchestrator.mjs'));
const rootDir = join(home, 'Library/Application Support/ProPR Desktop/local-runtime');
const cfg = resolveHostConfig({ rootDir, env: process.env, manifestPath: join(resources, 'manifest.json') });
await startStack(cfg, { docs: false, tunnel: false, onLog: (m) => console.log(String(m).slice(0, 200)) });
console.log('ProPR servisleri yeniden kuruldu.');
