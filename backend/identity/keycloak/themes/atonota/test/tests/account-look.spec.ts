import { expect, test, type Page } from '@playwright/test';
import { createUser, KC, REALM, submitPassword } from './helpers';

// Visual language of the account console (task 7b).
// The account console uses the same design tokens as the new web interface (AJA-997) and the approved draft.
// These tests measure the result in the browser: colours, contrast and touch targets.

type AccountPage = { name: string; path: string; ready: string };

const pages: AccountPage[] = [
  { name: 'personal-info', path: '', ready: '#save-btn' },
  { name: 'signing-in', path: 'account-security/signing-in', ready: '.pf-v5-c-data-list' },
  { name: 'device-activity', path: 'account-security/device-activity', ready: '#refresh-page' },
  { name: 'applications', path: 'applications', ready: '.pf-v5-c-data-list' },
];

/** Signs in a fresh sample customer and opens one account console page. */
async function openAccount(page: Page, target: AccountPage): Promise<void> {
  const email = await createUser({ customer: true });
  await page.goto(`${KC}/realms/${REALM}/account/${target.path}`);
  await submitPassword(page, email);
  await expect(page.locator(target.ready).first()).toBeVisible({ timeout: 20_000 });
  await page.evaluate(() => document.fonts.ready);
}

/**
 * Expected token values. They come from the atonota-web design source (AJA-997, commit d21799c, src/design/).
 * The values are the computed CSS variables of that source.
 */
const expected = {
  light: {
    page: 'rgb(244, 245, 247)', // --color-bg-layout #f4f5f7
    surface: 'rgb(255, 255, 255)', // --color-bg-panel #ffffff
    ink: 'rgb(27, 31, 36)', // --color-text #1b1f24
    link: 'rgb(0, 111, 134)', // --color-link #006f86
    action: 'rgb(0, 170, 204)', // --color-primary #00aacc
    tint: 'rgb(224, 245, 249)', // --color-tint rgba(0,170,204,.12) on the panel
  },
  dark: {
    page: 'rgb(23, 23, 26)', // #17171A
    surface: 'rgb(31, 31, 35)', // #1F1F23
    ink: 'rgb(236, 236, 240)', // #ececf0
    link: 'rgb(22, 177, 208)', // #16b1d0
    action: 'rgb(20, 44, 51)', // --primary-bg #142c33
    tint: 'rgb(27, 50, 59)', // --color-tint rgba(0,170,204,.14) on the panel
  },
} as const;

for (const scheme of ['light', 'dark'] as const) {
  test(`account (${scheme}): the console uses the new design tokens`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await openAccount(page, pages[0]);
    const look = await page.evaluate(() => {
      const style = (selector: string) => {
        const element = document.querySelector(selector);
        return element ? getComputedStyle(element) : undefined;
      };
      return {
        page: style('.pf-v5-c-page')?.backgroundColor,
        masthead: style('.pf-v5-c-masthead')?.backgroundColor,
        mastheadInk: style('.pf-v5-c-masthead')?.color,
        main: style('.pf-v5-c-page__main-section')?.backgroundColor,
        ink: style('.pf-v5-c-title')?.color,
        action: style('#save-btn')?.backgroundColor,
        actionRadius: style('#save-btn')?.borderTopLeftRadius,
        current: style('.pf-v5-c-nav__link.pf-m-current')?.backgroundColor,
        currentInk: style('.pf-v5-c-nav__link.pf-m-current')?.color,
        deletionLink: style('#at-account-deletion-link')?.color,
      };
    });
    const want = expected[scheme];
    expect(look.page, 'page background').toBe(want.page);
    expect(look.masthead, 'the top bar is a surface, not a dark band').toBe(want.surface);
    expect(look.mastheadInk, 'top bar text').toBe(want.ink);
    expect(look.main, 'content surface').toBe(want.surface);
    expect(look.ink, 'title text').toBe(want.ink);
    expect(look.action, 'primary button').toBe(want.action);
    expect(look.actionRadius, 'control radius').toBe('5px');
    expect(look.current, 'current page in the menu').toBe(want.tint);
    expect(look.currentInk, 'current page text').toBe(want.link);
    expect(look.deletionLink, 'deletion link').toBe(want.link);
  });
}

for (const scheme of ['light', 'dark'] as const) {
  for (const target of pages) {
    test(`@matrix account ${target.name} (${scheme}): text contrast is at least 4.5:1`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await openAccount(page, target);
      const result = await page.evaluate(() => {
        type Rgba = [number, number, number, number];
        const parse = (value: string): Rgba => {
          const parts = value.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0, 0];
          return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
        };
        const over = (top: Rgba, bottom: Rgba): Rgba => {
          const alpha = top[3] + bottom[3] * (1 - top[3]);
          if (alpha === 0) return [0, 0, 0, 0];
          const mix = (i: number) => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / alpha;
          return [mix(0), mix(1), mix(2), alpha];
        };
        const background = (element: Element): Rgba => {
          const layers: Rgba[] = [];
          for (let node: Element | null = element; node; node = node.parentElement) {
            layers.push(parse(getComputedStyle(node).backgroundColor));
          }
          // The canvas behind the page is the root background, or white when it has none.
          let colour: Rgba = [255, 255, 255, 1];
          for (const layer of layers.reverse()) colour = over(layer, colour);
          return colour;
        };
        const luminance = ([r, g, b]: Rgba) => {
          const channel = (c: number) => {
            const s = c / 255;
            return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
          };
          return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        const ratio = (a: Rgba, b: Rgba) => {
          const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
          return (x + 0.05) / (y + 0.05);
        };
        const low: string[] = [];
        const primaryText: string[] = [];
        const seen = new Set<Element>();
        let checked = 0;
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const node = walker.currentNode;
          const element = node.parentElement;
          if (!element || seen.has(element) || !node.textContent?.trim()) continue;
          if (element.closest('script, style, noscript, svg, .pf-v5-c-page__sidebar.pf-m-collapsed')) continue;
          if (!element.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
          const box = element.getBoundingClientRect();
          if (box.width === 0 || box.height === 0) continue;
          // WCAG 1.4.3 does not cover inactive controls.
          if (element.closest(':disabled, [aria-disabled="true"], .pf-m-disabled')) continue;
          seen.add(element);
          checked += 1;
          const style = getComputedStyle(element);
          const back = background(element);
          const text = over(parse(style.color), back);
          const value = ratio(text, back);
          const label = `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 40)} "${node.textContent.trim().slice(0, 24)}"`;
          if (value < 4.5) low.push(`${label} ${value.toFixed(2)}:1 ${style.color} on rgb(${back.slice(0, 3).map(Math.round).join(', ')})`);
          if (parse(style.color).slice(0, 3).join(',') === '0,170,204') primaryText.push(label);
        }
        return { low, primaryText, checked };
      });
      expect(result.checked, 'text elements checked').toBeGreaterThan(5);
      expect(result.low, 'text below 4.5:1').toEqual([]);
      if (scheme === 'light') expect(result.primaryText, '#00aacc is never a text colour in the light theme').toEqual([]);
    });
  }
}

test.describe('phone with a touch screen', () => {
  test.use({ hasTouch: true, isMobile: true });

  for (const target of pages) {
    test(`@matrix account ${target.name}: every standalone control is at least 48px high`, async ({ page }) => {
      const size = page.viewportSize();
      test.skip(!size || size.width > 480, 'Phone widths only');
      await openAccount(page, target);
      expect(await page.evaluate(() => matchMedia('(any-pointer: coarse)').matches), 'coarse pointer').toBe(true);

      const measure = () =>
        page.evaluate(() => {
          const found: string[] = [];
          const selector = [
            'button:not(.pf-m-inline)',
            'a[class*="c-button"]:not(.pf-m-inline)',
            'input:not([type=hidden]):not([type=checkbox]):not([type=radio])',
            'a.pf-v5-c-nav__link',
            'a.pf-v5-c-masthead__brand',
            '.pf-v5-c-menu__item',
            'a.at-account-deletion__link',
            '[role="button"]',
            '[role="menuitem"]',
            'summary',
          ].join(', ');
          for (const control of document.querySelectorAll<HTMLElement>(selector)) {
            if (!control.checkVisibility()) continue;
            if (control.closest('.pf-v5-c-page__sidebar.pf-m-collapsed')) continue;
            const box = control.getBoundingClientRect();
            if (box.width === 0 || box.height === 0) continue;
            const narrow = control.tagName !== 'A' && !control.matches('.pf-v5-c-menu__item') && box.width < 47.5;
            if (box.height < 47.5 || narrow) {
              found.push(`${control.tagName.toLowerCase()}#${control.id}.${String(control.className).slice(0, 40)} ${Math.round(box.width)}x${Math.round(box.height)}`);
            }
          }
          return found;
        });

      expect(await measure(), 'small control on the page').toEqual([]);

      // The navigation menu opens from the top bar on a phone.
      const navToggle = page.locator('.pf-v5-c-masthead__toggle button').first();
      if (await navToggle.isVisible()) {
        await navToggle.click();
        await expect(page.locator('.pf-v5-c-page__sidebar.pf-m-expanded')).toBeVisible();
        expect(await measure(), 'small control in the open menu').toEqual([]);
        await navToggle.click();
      }

      // The user menu in the top bar.
      const userMenu = page.locator('.pf-v5-c-masthead .pf-v5-c-menu-toggle').last();
      if (await userMenu.isVisible()) {
        await userMenu.click();
        await expect(page.locator('.pf-v5-c-menu').first()).toBeVisible();
        expect(await measure(), 'small control in the user menu').toEqual([]);
      }
    });
  }
});
