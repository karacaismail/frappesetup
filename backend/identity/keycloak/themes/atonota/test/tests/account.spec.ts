import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type ElementHandle, type Page } from '@playwright/test';
import { diffBox, focusDiff, PAD } from './focus-diff';
import { createUser, KC, REALM, submitPassword } from './helpers';

// Tests of the Atonota account console theme.
// The console is the stock Keycloak React application. The theme only adds styles, a focus script and messages.

const accountCssPath = fileURLToPath(new URL('../../account/resources/css/atonota-account.css', import.meta.url));
const loginCssPath = fileURLToPath(new URL('../../login/resources/css/atonota.css', import.meta.url));
const EASE = 'cubic-bezier(0.65, 0, 0.35, 1)';

type AccountPage = { name: string; path: string; ready: string };

const pages: AccountPage[] = [
  { name: 'personal-info', path: '', ready: '#save-btn' },
  { name: 'signing-in', path: 'account-security/signing-in', ready: '.pf-v5-c-data-list' },
  { name: 'device-activity', path: 'account-security/device-activity', ready: '#refresh-page' },
  { name: 'applications', path: 'applications', ready: '.pf-v5-c-data-list' },
];

const byName = (name: string) => pages.find((item) => item.name === name)!;

/** Signs in a fresh sample user and opens one account console page. */
async function openAccount(page: Page, target: AccountPage): Promise<string> {
  const email = await createUser();
  await page.goto(`${KC}/realms/${REALM}/account/${target.path}`);
  await submitPassword(page, email);
  await expect(page.locator(target.ready).first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  return email;
}

// WebKit leaves links out of the Tab order. Option+Tab is the Safari equivalent.
const tabKey = (browserName: string) => (browserName === 'webkit' ? 'Alt+Tab' : 'Tab');

const settle = (page: Page) =>
  page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished.catch(() => undefined))));

for (const target of pages) {
  test(`@matris account ${target.name}: overflow, text size, font and control size`, async ({ page }) => {
    const requests: string[] = [];
    page.on('request', (request) => requests.push(request.url()));
    await openAccount(page, target);

    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll, 'horizontal overflow').toBeLessThanOrEqual(overflow.client);

    // The console scrolls inside its own main region, which hides horizontal overflow from the document.
    // So every visible element is also checked against the viewport edge.
    const beyondEdge = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('body *')]
        .filter((element) => element.checkVisibility() && !element.closest('.pf-v5-c-page__sidebar.pf-m-collapsed, svg'))
        .filter((element) => {
          const box = element.getBoundingClientRect();
          return box.width > 0 && box.height > 0 && (box.right > innerWidth + 1 || box.left < -1);
        })
        .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 40)} ${Math.round(element.getBoundingClientRect().left)}..${Math.round(element.getBoundingClientRect().right)}`)
        .slice(0, 8),
    );
    expect(beyondEdge, 'element beyond the viewport edge').toEqual([]);

    const text = await page.evaluate(() => {
      const small: string[] = [];
      const wrongFont: string[] = [];
      const forcedBreak: string[] = [];
      const seen = new Set<Element>();
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode;
        const element = node.parentElement;
        if (!element || seen.has(element) || !node.textContent?.trim()) continue;
        if (element.closest('script, style, noscript')) continue;
        if (!element.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        seen.add(element);
        const style = getComputedStyle(element);
        const label = `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 40)} "${node.textContent.trim().slice(0, 30)}"`;
        if (Number.parseFloat(style.fontSize) < 14) small.push(`${label} ${style.fontSize}`);
        if (!element.closest('pre, code, kbd, samp') && !/^"?Outfit/.test(style.fontFamily)) wrongFont.push(`${label} ${style.fontFamily}`);
        if (style.overflowWrap === 'anywhere' || style.wordBreak === 'break-all') forcedBreak.push(label);
      }
      for (const control of document.querySelectorAll<HTMLElement>('input:not([type=hidden]), button, textarea')) {
        if (!control.checkVisibility()) continue;
        const style = getComputedStyle(control);
        if (Number.parseFloat(style.fontSize) < 14) small.push(`${control.tagName}#${control.id} ${style.fontSize}`);
        if (!/^"?Outfit/.test(style.fontFamily)) wrongFont.push(`${control.tagName}#${control.id} ${style.fontFamily}`);
      }
      return { small, wrongFont, forcedBreak, outfitLoaded: document.fonts.check('16px "Outfit Variable"', 'Şifre ığüşöç') };
    });
    expect(text.small, 'text below 14px').toEqual([]);
    expect(text.wrongFont, 'font other than Outfit').toEqual([]);
    expect(text.forcedBreak, 'forced word breaking').toEqual([]);
    expect(text.outfitLoaded, 'Outfit is loaded').toBe(true);

    // Every request stays on the Keycloak origin. No third-party font or script.
    const external = requests.filter((url) => !url.startsWith(KC) && !url.startsWith('data:') && !url.startsWith('blob:'));
    expect(external, 'external request').toEqual([]);
    // Only the theme font and the stock icon fonts may be requested.
    // One stock text font file was seen in rare runs at page start. The network trace shows the theme stylesheet and
    // the stock stylesheet requested together, and the cause of that one request was not confirmed. It is allowed by
    // name. Any other font request fails this test.
    const fonts = requests.filter((url) => /\.(woff2?|ttf|otf|eot)(\?|$)/.test(url));
    const allowed = /\/(outfit-latin(-ext)?-wght-normal|fa-solid-900|pficon|RedHatText-Medium-[\w-]+)\.woff2?(\?|$)/;
    expect(fonts.filter((url) => !allowed.test(url)), 'font request outside the allow list').toEqual([]);

    await expect(page.locator('select')).toHaveCount(0);

    // A standalone control has an effective area of at least 44px (48px with a coarse pointer).
    const minimum = await page.evaluate(() => (matchMedia('(any-pointer: coarse)').matches ? 48 : 44));
    const smallTargets = await page.evaluate((min) => {
      const found: string[] = [];
      const selector = 'button:not(.pf-m-inline), a[class*="c-button"]:not(.pf-m-inline), input:not([type=hidden]):not([type=checkbox]):not([type=radio]), a.pf-v5-c-nav__link, a.pf-v5-c-masthead__brand, a.pf-v5-c-jump-links__link, [role="button"], summary';
      for (const control of document.querySelectorAll<HTMLElement>(selector)) {
        if (!control.checkVisibility()) continue;
        const box = control.getBoundingClientRect();
        if (control.closest('.pf-v5-c-page__sidebar.pf-m-collapsed')) continue; // off-canvas sidebar
        const narrow = control.tagName !== 'A' && box.width < min - 0.5;
        if (box.height < min - 0.5 || narrow) {
          found.push(`${control.tagName.toLowerCase()}#${control.id}.${String(control.className).slice(0, 40)} ${Math.round(box.width)}x${Math.round(box.height)}`);
        }
      }
      return found;
    }, minimum);
    expect(smallTargets, 'small touch target').toEqual([]);
  });
}

test('account console is branded: realm name, own logo and favicon', async ({ page }) => {
  await openAccount(page, byName('personal-info'));
  const brand = page.locator('.pf-v5-c-masthead__brand img');
  await expect(brand).toHaveAttribute('src', /\/account\/atonota\/img\/logo\.svg$/);
  await expect(page.locator('link[rel=icon]')).toHaveAttribute('href', /\/account\/atonota\/img\/favicon\.svg$/);
  // The brand image is decorative text-free artwork. The accessible name comes from the theme, not from Keycloak.
  expect(await brand.getAttribute('alt')).not.toMatch(/keycloak/i);
});

test('account console speaks plain Turkish by default', async ({ page }) => {
  await openAccount(page, byName('personal-info'));
  await expect(page.locator('html')).toHaveAttribute('lang', 'tr');
  await expect(page.locator('#save-btn')).toHaveText('Kaydedin');
  await expect(page.locator('#cancel-btn')).toHaveText('Vazgeçin');
  await expect(page.locator('.pf-v5-c-nav__link').first()).toHaveText('Kişisel bilgiler');
  await expect(page.locator('body')).not.toContainText(/şifre/i);
});

test('saving personal info still works with the theme', async ({ page }) => {
  await openAccount(page, byName('personal-info'));
  await page.locator('#firstName').fill('Örnek');
  await page.locator('#save-btn').click();
  await expect(page.locator('.pf-v5-c-alert.pf-m-success')).toBeVisible();
  await page.reload();
  await expect(page.locator('#firstName')).toHaveValue('Örnek');
});

test('keyboard focus mode: only Tab turns it on, the pointer turns it off', async ({ page, browserName }) => {
  await openAccount(page, byName('personal-info'));
  const mode = () => page.evaluate(() => document.documentElement.dataset.atFocus ?? '');
  expect(await mode()).toBe('');
  await page.locator('#firstName').click();
  await page.keyboard.type('a');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Escape');
  expect(await mode(), 'typing, arrows and Escape do not turn it on').toBe('');
  await page.keyboard.press(tabKey(browserName));
  expect(await mode()).toBe('keyboard');
  const before = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 120));
  await page.locator(':focus').dispatchEvent('pointerdown', { bubbles: true });
  expect(await mode()).toBe('');
  expect(await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 120)), 'focus stays in place').toBe(before);
});

const focusCases = [
  { name: 'personal-info', scheme: 'light', required: ['#firstName', '#save-btn', '#cancel-btn'] },
  { name: 'personal-info', scheme: 'dark', required: ['#firstName', '#save-btn'] },
  { name: 'signing-in', scheme: 'light', required: ['.pf-v5-c-data-list button.pf-m-secondary'] },
  { name: 'device-activity', scheme: 'dark', required: ['#refresh-page'] },
  { name: 'applications', scheme: 'light', required: ['[id^="toggle-"]'] },
] as const;

/** Screenshots the padded area around an element with the keyboard mode switched off. */
async function shotAround(page: Page, target: ElementHandle<Element>) {
  const box = (await target.boundingBox())!;
  const viewport = page.viewportSize()!;
  const x = Math.max(0, Math.floor(box.x - PAD));
  const y = Math.max(0, Math.floor(box.y - PAD));
  const clip = {
    x,
    y,
    width: Math.min(viewport.width, Math.ceil(box.x + box.width + PAD)) - x,
    height: Math.min(viewport.height, Math.ceil(box.y + box.height + PAD)) - y,
  };
  await page.mouse.move(0, 0);
  const mode = await page.evaluate(() => {
    const previous = document.documentElement.dataset.atFocus ?? '';
    document.documentElement.removeAttribute('data-at-focus');
    return previous;
  });
  const shot = await page.screenshot({ clip, scale: 'css' });
  await page.evaluate((previous) => {
    if (previous) document.documentElement.dataset.atFocus = previous;
  }, mode);
  return shot;
}

for (const { name, scheme, required } of focusCases) {
  test(`account ${name} (${scheme}): focus indicator is visible and does not surround the element`, async ({ page, browserName }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await openAccount(page, byName(name));
    if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
    // The caret and the text selection are hidden. They are not focus indicators and would add noise.
    await page.addStyleTag({ content: '* { caret-color: transparent !important; } ::selection { background: transparent !important; color: inherit !important; }' });
    await page.locator('body').click({ position: { x: 1, y: 1 } });
    const checked: string[] = [];
    const reached = new Set<string>();
    // The loop runs until focus wraps around to an element it has already measured.
    for (let step = 0; step < 60; step += 1) {
      await page.keyboard.press(tabKey(browserName));
      const current = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement | null;
        if (!element || element === document.body) return 'body';
        const index = [...document.querySelectorAll(element.tagName)].indexOf(element);
        return `${element.tagName.toLowerCase()}[${index}]#${element.id}`;
      });
      if (current === 'body' || checked.includes(current)) break;
      checked.push(current);
      const focused = page.locator(':focus');
      for (const selector of required) {
        if (await focused.evaluate((element, value) => element.matches(value), selector)) reached.add(selector);
      }
      await focused.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await settle(page);

      // No outline on the element or on any of its ancestors.
      const outlined = await focused.evaluate((element) => {
        const found: string[] = [];
        for (let node: Element | null = element; node; node = node.parentElement) {
          const style = getComputedStyle(node);
          if (style.outlineStyle !== 'none' && style.outlineWidth !== '0px') found.push(node.tagName);
        }
        return found;
      });
      expect(outlined, `${current}: no outline on the element or its ancestors`).toEqual([]);

      const { diff, rect } = await focusDiff(page, focused);
      expect(diff.count, `${current}: visible focus indicator`).toBeGreaterThanOrEqual(24);
      expect(diff.contrast, `${current}: indicator contrast`).toBeGreaterThanOrEqual(3);
      // The indicator sits in the lower half of the element or below it. It never wraps the top or the sides.
      expect(diff.minY, `${current}: no line on the top edge`).toBeGreaterThanOrEqual(rect.top + rect.height / 2);
      expect(diff.minX, `${current}: no line on the left edge`).toBeGreaterThanOrEqual(Math.floor(rect.left));
      expect(diff.maxX, `${current}: no line on the right edge`).toBeLessThanOrEqual(Math.ceil(rect.left + rect.width));
      expect(diff.maxY - diff.minY, `${current}: the indicator is one straight line`).toBeLessThanOrEqual(6);

      // A stock indicator drawn with plain :focus or :focus-within would not depend on the keyboard mode.
      // So the focused element (mode off) is also compared with the same element after focus has moved on.
      // With the mode off, focus must change nothing on screen.
      const handle = (await focused.elementHandle())!;
      const focusedShot = await shotAround(page, handle);
      // Moving focus may scroll the page. The exact scroll position is restored, so both images show the same pixels.
      // Which element scrolls differs between engines, so every ancestor is recorded.
      const scroll = await handle.evaluate((element) => {
        const tops: number[] = [];
        for (let node = element.parentElement; node; node = node.parentElement) tops.push(node.scrollTop);
        return { tops, window: window.scrollY, y: element.getBoundingClientRect().y };
      });
      await page.keyboard.press(tabKey(browserName));
      const moved = await handle.evaluate((element) => document.activeElement !== element);
      if (moved) {
        // WebKit may finish its own focus scroll a moment later, so the position is restored until it holds.
        await expect(async () => {
          const y = await handle.evaluate((element, saved) => {
            let index = 0;
            for (let node = element.parentElement; node; node = node.parentElement) {
              node.scrollTop = saved.tops[index];
              index += 1;
            }
            window.scrollTo(0, saved.window);
            return element.getBoundingClientRect().y;
          }, scroll);
          await page.waitForTimeout(50);
          expect(await handle.evaluate((element) => element.getBoundingClientRect().y)).toBe(y);
          expect(y).toBe(scroll.y);
        }).toPass({ timeout: 3000 });
        const idleShot = await shotAround(page, handle);
        if (idleShot.length > 0 && focusedShot.length > 0) {
          const stray = await diffBox(page, idleShot, focusedShot);
          expect(stray.count, `${current}: focus changes nothing while the keyboard mode is off`).toBe(0);
        }
        await page.keyboard.press(browserName === 'webkit' ? 'Alt+Shift+Tab' : 'Shift+Tab');
        await handle.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      }
    }
    expect(checked.length, `measured elements: ${checked.join(', ')}`).toBeGreaterThanOrEqual(4);
    expect([...reached].sort(), `required elements reached, measured: ${checked.join(', ')}`).toEqual([...required].sort());
  });
}

test('account: user menu opens with the keyboard and its items show focus', async ({ page, browserName }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openAccount(page, byName('personal-info'));
  await page.addStyleTag({ content: '* { caret-color: transparent !important; }' });
  const toggle = page.locator('.pf-v5-c-masthead .pf-v5-c-menu-toggle:visible').first();
  await toggle.focus();
  await page.keyboard.press(tabKey(browserName));
  await page.keyboard.press(browserName === 'webkit' ? 'Alt+Shift+Tab' : 'Shift+Tab');
  await expect(toggle).toBeFocused();
  await page.keyboard.press('Enter');
  const item = page.locator('.pf-v5-c-menu__item:visible').first();
  await expect(item).toBeVisible();
  await page.keyboard.press('ArrowDown');
  const focused = page.locator(':focus');
  await expect(focused).toHaveClass(/pf-v5-c-menu__item/);
  // The menu is positioned after it opens. The measurement is retried until the menu has settled.
  await expect(async () => {
    const { diff, rect } = await focusDiff(page, focused);
    expect(diff.count, 'visible focus indicator on the menu item').toBeGreaterThanOrEqual(24);
    expect(diff.minY).toBeGreaterThanOrEqual(rect.top + rect.height / 2);
  }).toPass({ timeout: 5000 });
  await page.keyboard.press('Escape');
  await expect(item).toBeHidden();
  await expect(toggle).toBeFocused();
});

/** Collects every transition and animation with a positive duration, including pseudo-elements. */
const collectMotion = (page: Page) =>
  page.evaluate(() => {
    const found: { where: string; easing: string; seconds: number; property: string }[] = [];
    const seconds = (value: string) => Math.max(...value.split(',').map((part) => Number.parseFloat(part) * (part.trim().endsWith('ms') ? 0.001 : 1)));
    for (const element of document.querySelectorAll('body, body *')) {
      for (const pseudo of [null, '::before', '::after']) {
        const style = getComputedStyle(element, pseudo);
        if (pseudo && style.content === 'none') continue;
        const where = `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 50)}${pseudo ?? ''}`;
        const transition = seconds(style.transitionDuration);
        if (transition > 0) found.push({ where, easing: style.transitionTimingFunction, seconds: transition, property: style.transitionProperty });
        const animation = seconds(style.animationDuration);
        if (animation > 0 && style.animationName !== 'none') found.push({ where, easing: style.animationTimingFunction, seconds: animation, property: `animation ${style.animationName}` });
      }
    }
    return found;
  });

for (const name of ['personal-info', 'signing-in', 'applications']) {
  test(`account ${name}: every transition uses the approved curve and the token duration`, async ({ page }) => {
    await openAccount(page, byName(name));
    const motion = await collectMotion(page);
    expect(motion.filter((item) => item.easing.split(/,(?![^(]*\))/).some((part) => part.trim() !== EASE)), 'unapproved curve').toEqual([]);
    expect(motion.filter((item) => !item.property.startsWith('animation') && Math.abs(item.seconds - 0.16) > 0.001), 'duration outside the token').toEqual([]);
    expect(motion.filter((item) => item.property.split(',').some((part) => part.trim() === 'all')), 'transition: all').toEqual([]);
    expect(motion.filter((item) => item.where.includes('pf-v5-c-button')).length, 'buttons have a transition').toBeGreaterThan(0);
  });
}

test('account: the sidebar slides with the token curve and duration', async ({ page }) => {
  await openAccount(page, byName('personal-info'));
  const sidebar = await page.locator('.pf-v5-c-page__sidebar').evaluate((element) => {
    const style = getComputedStyle(element);
    return { property: style.transitionProperty, duration: style.transitionDuration, easing: style.transitionTimingFunction };
  });
  expect(sidebar.property).toContain('transform');
  expect(sidebar.duration).toBe('0.16s');
  expect(sidebar.easing).toBe(EASE);
});

test('account: reduced motion removes transitions and animations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openAccount(page, byName('personal-info'));
  expect((await collectMotion(page)).filter((item) => item.seconds > 0.011)).toEqual([]);
});

for (const scheme of ['light', 'dark'] as const) {
  for (const target of pages) {
    // axe covers the automated rules only. This is not a claim of full WCAG 2.2 AA conformance.
    test(`account ${target.name}: axe (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await openAccount(page, target);
      if (scheme === 'dark') await expect(page.locator('html')).toHaveClass(/pf-v5-theme-dark/);
      await settle(page);
      // Known upstream defect: the stock console renders these overflow-menu toggles without an accessible name.
      // A theme cannot change the console markup. The defect is listed in the README.
      // Only the "button-name" rule is waived, and only for those toggles. Every other rule still applies to them.
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
      const waived = await page.evaluate(() =>
        [...document.querySelectorAll('button.pf-v5-c-menu-toggle.pf-m-plain:not([aria-label])')].map((element) => element.outerHTML.slice(0, 80)),
      );
      const summary = results.violations.flatMap((violation) =>
        violation.nodes
          .filter((node) => !(violation.id === 'button-name' && waived.some((html) => node.html.startsWith(html.slice(0, 60)))))
          .map((node) => `${violation.id}: ${node.target.join(' ')}`),
      );
      expect(summary).toEqual([]);
    });
  }
}

for (const percent of [125, 200]) {
  test(`account: root font size ${percent}% does not overflow`, async ({ page }) => {
    await openAccount(page, byName('personal-info'));
    await page.addStyleTag({ content: `html { font-size: ${percent}% !important; }` });
    const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(size.scroll).toBeLessThanOrEqual(size.client);
    await expect(page.locator('#save-btn')).toBeVisible();
  });
}

test.describe('account style source', () => {
  const strip = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');
  const tokenBlock = (path: string) => {
    const css = readFileSync(path, 'utf8');
    const start = css.indexOf('/* tokens:start */');
    const end = css.indexOf('/* tokens:end */');
    expect(start, `${path}: tokens:start marker`).toBeGreaterThanOrEqual(0);
    expect(end, `${path}: tokens:end marker`).toBeGreaterThan(start);
    return strip(css.slice(start, end)).replace(/\s+/g, ' ').trim();
  };

  test('design tokens are identical in the login and account themes', () => {
    expect(tokenBlock(accountCssPath)).toBe(tokenBlock(loginCssPath));
  });

  test('motion comes from central tokens only', () => {
    const body = strip(readFileSync(accountCssPath, 'utf8'));
    expect(body.match(/transition\s*:\s*all/g) ?? []).toEqual([]);
    const declarations = body.match(/(transition|animation)(-timing-function|-duration)?\s*:[^;]+;/g) ?? [];
    const local = declarations.filter((line) => /\b(ease|ease-in|ease-out|ease-in-out|linear|steps)\b|\d+m?s\b/.test(line.replace(/var\([^)]*\)/g, '')));
    expect(local, 'local curve or duration').toEqual([]);
  });

  test('no accent line on a rounded box and no surrounding focus ring', () => {
    const body = strip(readFileSync(accountCssPath, 'utf8'));
    const oneSide = body.match(/border-(left|right|top|bottom|inline|block)(-start|-end)?(-color|-width|-style)?\s*:\s*(?!0|none)[^;]+;/g) ?? [];
    expect(oneSide, 'one-sided line').toEqual([]);
    expect(body.match(/box-shadow\s*:[^;]*inset[^;]*;/g) ?? [], 'inset shadow bar').toEqual([]);
    const outlines = (body.match(/outline\s*:[^;]+;/g) ?? []).filter((line) => !/outline\s*:\s*(0|none)/.test(line));
    expect(outlines).toEqual(['outline: 2px solid CanvasText;']);
    expect(body.match(/:focus-within/g) ?? []).toEqual([]);
  });
});

// Produces screenshots for an independent review. It compares nothing.
// Runs only with VISUAL=1: VISUAL=1 npx playwright test account -g screenshot
for (const scheme of ['light', 'dark'] as const) {
  for (const target of pages) {
    test(`account screenshot: ${target.name} (${scheme})`, async ({ page }, info) => {
      test.skip(!process.env.VISUAL, 'Screenshots are produced only with VISUAL=1');
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
      await openAccount(page, target);
      // The console scrolls inside its main region. The region is unrolled so the full page fits in one image.
      await page.addStyleTag({
        content:
          '* { caret-color: transparent !important; } html, body, #app, .pf-v5-c-page { height: auto !important; } .pf-v5-c-page__main { overflow: visible !important; }',
      });
      const out = fileURLToPath(new URL(`../referans/${info.project.name}/`, import.meta.url));
      await page.screenshot({ path: `${out}account-${target.name}-${scheme}.png`, fullPage: true });
    });
  }
}
