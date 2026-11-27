import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';
// site.ts also imports a Vite raw asset; this file-level check runs in Node.
const siteSource = readFileSync(new URL('../src/data/site.ts', import.meta.url), 'utf8');
const AS_OF = /export const AS_OF = '([^']+)'/.exec(siteSource)?.[1] ?? '';

// AS_OF ana sayfada ve kabukta görünen "güncellik" tarihidir. Değer elle yazılır.
// Bu test, içerik sayfaları değiştiği hâlde tarihin eski kalmasını yakalar.
// CI sığ klon yapar (actions/checkout varsayılanı). Sığ klonda son commit tüm dosyaları değiştirmiş görünür;
// bu yüzden git karşılaştırması yalnız tam geçmişte koşar. Biçim denetimi her yerde koşar.
const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
const root = fileURLToPath(new URL('../', import.meta.url));
const git = (...args: string[]) => execFileSync('git', ['-C', root, ...args], { encoding: 'utf8' }).trim();

function parseAsOf(value: string): string {
  const m = /^([1-9]|[12]\d|3[01]) (\S+) (\d{4})$/.exec(value);
  expect(m, `AS_OF "gün ay yıl" biçiminde olmalı: ${value}`).not.toBeNull();
  const month = MONTHS.indexOf(m![2]) + 1;
  expect(month, `AS_OF Türkçe ay adı taşımalı: ${value}`).toBeGreaterThan(0);
  return `${m![3]}-${String(month).padStart(2, '0')}-${m![1].padStart(2, '0')}`;
}

test.describe('as-of date', () => {
  test.beforeEach(({ browserName }) => {
    test.skip(browserName !== 'chromium', 'Dosya düzeyi denetim; tek motorda koşar.');
  });

  test('AS_OF is a Turkish date and not older than the last content commit', () => {
    const asOf = parseAsOf(AS_OF);
    let shallow: string;
    try {
      shallow = git('rev-parse', '--is-shallow-repository');
    } catch {
      test.skip(true, 'git yok; yalnız biçim denetlendi.');
      return;
    }
    test.skip(shallow === 'true', 'Sığ klon; yalnız biçim denetlendi.');
    // %cs: commit'in kendi saat dilimindeki tarih (YYYY-AA-GG).
    const last = git('log', '-1', '--format=%cs', '--', 'src/content/docs');
    expect(last, 'src/content/docs için commit bulunamadı').toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(asOf >= last, `AS_OF (${AS_OF}) son içerik commit'inden (${last}) eski; src/data/site.ts dosyasını güncelleyin`).toBe(true);
  });
});
