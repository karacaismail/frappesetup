import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from '@playwright/test';
import { screens } from './helpers';

// Bağımsız inceleme için ekran görüntüsü üretir. Karşılaştırma yapmaz.
// Yalnız VISUAL=1 ile koşar: VISUAL=1 npx playwright test visual
const out = fileURLToPath(new URL('../reference/', import.meta.url));

for (const scheme of ['light', 'dark'] as const) {
  for (const item of screens) {
    test(`görüntü: ${item.name} (${scheme})`, async ({ page }, info) => {
      test.skip(!process.env.VISUAL, 'Görüntü üretimi yalnız VISUAL=1 ile koşar');
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
