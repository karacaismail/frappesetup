import { expect, type ElementHandle, type Locator, type Page } from '@playwright/test';

// Shared pixel-difference helpers for the focus indicator tests.

/** Measures the difference between two screenshots with an in-page canvas. No extra package is needed. */
export async function diffBox(page: Page, before: Buffer, after: Buffer) {
  return page.evaluate(
    async ([first, second]) => {
      const load = async (data: string) => {
        const image = new Image();
        image.src = `data:image/png;base64,${data}`;
        await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const context = canvas.getContext('2d')!;
        context.drawImage(image, 0, 0);
        return context.getImageData(0, 0, canvas.width, canvas.height);
      };
      const a = await load(first);
      const b = await load(second);
      let minX = Infinity, minY = Infinity, maxX = -1, maxY = -1, count = 0;
      const lum = (r: number, g: number, bl: number) => {
        const f = (v: number) => (v / 255 <= 0.03928 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4);
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl);
      };
      let best = 1;
      for (let y = 0; y < a.height; y += 1) {
        for (let x = 0; x < a.width; x += 1) {
          const i = (y * a.width + x) * 4;
          const delta = Math.abs(a.data[i] - b.data[i]) + Math.abs(a.data[i + 1] - b.data[i + 1]) + Math.abs(a.data[i + 2] - b.data[i + 2]);
          if (delta < 48) continue;
          count += 1;
          minX = Math.min(minX, x); maxX = Math.max(maxX, x);
          minY = Math.min(minY, y); maxY = Math.max(maxY, y);
          const l1 = lum(a.data[i], a.data[i + 1], a.data[i + 2]);
          const l2 = lum(b.data[i], b.data[i + 1], b.data[i + 2]);
          best = Math.max(best, (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05));
        }
      }
      return { count, minX, minY, maxX, maxY, width: a.width, height: a.height, contrast: best };
    },
    [before.toString('base64'), after.toString('base64')] as const,
  );
}

export const PAD = 14;

/** Captures the area around the focused element with keyboard mode off and on, and returns the difference. */
export async function focusDiff(page: Page, target: Locator) {
  const box = (await target.boundingBox())!;
  const viewport = page.viewportSize()!;
  const clip = {
    x: Math.max(0, Math.floor(box.x - PAD)),
    y: Math.max(0, Math.floor(box.y - PAD)),
    width: 0,
    height: 0,
  };
  clip.width = Math.min(viewport.width, Math.ceil(box.x + box.width + PAD)) - clip.x;
  clip.height = Math.min(viewport.height, Math.ceil(box.y + box.height + PAD)) - clip.y;
  await page.mouse.move(0, 0);
  await page.evaluate(() => document.documentElement.removeAttribute('data-at-focus'));
  const off = await page.screenshot({ clip, scale: 'css' });
  await page.evaluate(() => (document.documentElement.dataset.atFocus = 'keyboard'));
  const on = await page.screenshot({ clip, scale: 'css' });
  const diff = await diffBox(page, off, on);
  return { diff, rect: { left: box.x - clip.x, top: box.y - clip.y, width: box.width, height: box.height } };
}

/** Screenshots the padded area around an element with the keyboard mode switched off. */
async function shotAround(page: Page, target: ElementHandle<Element>): Promise<Buffer> {
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

/**
 * Counts the pixels that change when the element loses focus while the keyboard mode is off.
 * With the mode off, focus must change nothing on screen. A stock indicator drawn with plain
 * :focus or :focus-within would show up here.
 * Focus is moved on with `forward` and brought back with `backward`.
 * Returns null when focus could not be moved away from the element.
 */
export async function strayFocusDiff(page: Page, focused: Locator, forward: string, backward: string): Promise<number | null> {
  const handle = (await focused.elementHandle())!;
  const focusedShot = await shotAround(page, handle);
  // Moving focus may scroll the page. Which element scrolls differs between engines, so every ancestor is recorded.
  const scroll = await handle.evaluate((element) => {
    const tops: number[] = [];
    for (let node = element.parentElement; node; node = node.parentElement) tops.push(node.scrollTop);
    return { tops, window: window.scrollY, y: element.getBoundingClientRect().y };
  });
  const restore = () =>
    handle.evaluate((element, saved) => {
      let index = 0;
      for (let node = element.parentElement; node; node = node.parentElement) {
        node.scrollTop = saved.tops[index];
        index += 1;
      }
      window.scrollTo(0, saved.window);
      return element.getBoundingClientRect().y;
    }, scroll);
  await page.keyboard.press(forward);
  const moved = await handle.evaluate((element) => document.activeElement !== element);
  if (!moved) return null;
  // WebKit may finish its own focus scroll a moment later, so the position is restored until it holds
  // across two animation frames. No fixed waiting time is used.
  await expect(async () => {
    const y = await restore();
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null)))));
    expect(await handle.evaluate((element) => element.getBoundingClientRect().y)).toBe(y);
    expect(y).toBe(scroll.y);
  }).toPass({ timeout: 3000 });
  const idleShot = await shotAround(page, handle);
  const stray = await diffBox(page, idleShot, focusedShot);
  await page.keyboard.press(backward);
  await restore();
  return stray.count;
}
