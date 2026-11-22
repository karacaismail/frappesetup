import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from '@playwright/test';
import { screens } from './helpers';

// Bağımsız inceleme için ekran görüntüsü üretir. Karşılaştırma yapmaz.
// Yalnız GORSEL=1 ile koşar: GORSEL=1 npx playwright test gorsel
const out = fileURLToPath(new URL('../referans/', import.meta.url));

for (const scheme of ['light', 'dark'] as const) {
  for (const item of screens) {
    test(`görüntü: ${item.name} (${scheme})`, async ({ page }, info) => {
      test.skip(!process.env.GORSEL, 'Görüntü üretimi yalnız GORSEL=1 ile koşar');
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
      await item.open(page);
      await page.evaluate(() => document.fonts.ready);
      await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
      const dir = `${out}${info.project.name}`;
      mkdirSync(dir, { recursive: true });
      await page.screenshot({ path: `${dir}/${item.name}-${scheme}.png`, fullPage: true });
    });
  }
}
