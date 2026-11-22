import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { screens } from './helpers';

// axe otomatik kuralları kapsar. Tam WCAG 2.2 AA uyumu iddiası değildir.
const tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];

for (const scheme of ['light', 'dark'] as const) {
  for (const item of screens) {
    test(`${item.name}: axe (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await item.open(page);
      if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
      // Renk geçişi bitmeden ölçülen kontrast yanlış çıkar. Önce geçişlerin bitmesi beklenir.
      await page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined))));
      const results = await new AxeBuilder({ page }).withTags(tags).analyze();
      const summary = results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`);
      expect(summary).toEqual([]);
    });
  }
}
