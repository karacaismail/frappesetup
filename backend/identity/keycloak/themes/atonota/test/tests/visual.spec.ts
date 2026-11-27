import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
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
      // A password never shows in a picture. Every password field is empty when the picture is taken.
      const filled = await page.locator('input[type=password], input[name*=password i]').evaluateAll(
        (fields) => fields.filter((field) => (field as HTMLInputElement).value !== '').length,
      );
      expect(filled, 'filled password field in a picture').toBe(0);
      const dir = `${out}${info.project.name}`;
      mkdirSync(dir, { recursive: true });
      await page.screenshot({ path: `${dir}/${item.name}-${scheme}.png`, fullPage: true });
    });
  }
}
