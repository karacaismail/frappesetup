import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import { screen } from './helpers';

const EASE = 'cubic-bezier(0.65, 0, 0.35, 1)';
const readCss = () => readFileSync(fileURLToPath(new URL('../../login/resources/css/atonota.css', import.meta.url)), 'utf8');
/** Duration of every transition: the central --at-motion-duration-fast token, in seconds. */
const tokenSeconds = () => Number.parseFloat(/--at-motion-duration-fast:\s*(\d+)ms/.exec(readCss())![1]) / 1000;

/** Süresi sıfırdan büyük her geçiş ve animasyonu, öğeler ve sözde öğeler için toplar. */
const collectMotion = (page: Page) =>
  page.evaluate(() => {
    const found: { where: string; easing: string; seconds: number; property: string }[] = [];
    const seconds = (value: string) => Math.max(...value.split(',').map((part) => Number.parseFloat(part) * (part.trim().endsWith('ms') ? 0.001 : 1)));
    for (const element of document.querySelectorAll('body, body *')) {
      for (const pseudo of [null, '::before', '::after']) {
        const style = getComputedStyle(element, pseudo);
        if (pseudo && style.content === 'none') continue;
        const where = `${element.tagName.toLowerCase()}#${element.id}.${String(element.className).slice(0, 40)}${pseudo ?? ''}`;
        const transition = seconds(style.transitionDuration);
        if (transition > 0) found.push({ where, easing: style.transitionTimingFunction, seconds: transition, property: style.transitionProperty });
        const animation = seconds(style.animationDuration);
        if (animation > 0 && style.animationName !== 'none') found.push({ where, easing: style.animationTimingFunction, seconds: animation, property: `animation ${style.animationName}` });
      }
    }
    return found;
  });

for (const name of ['sign-in', 'totp-setup', 'passkey-sign-in', 'sign-in-method']) {
  test(`${name}: her geçiş onaylı eğriyi ve sınırlı süreyi kullanır`, async ({ page }) => {
    await screen(name).open(page);
    const motion = await collectMotion(page);
    const wrong = motion.filter((item) => item.easing.split(/,(?![^(]*\))/).some((part) => part.trim() !== EASE));
    expect(wrong, 'onaysız eğri').toEqual([]);
    // Süre merkezi tokena eşittir (--at-motion-duration-fast). Temel temadan başka süre ve "transition: all" sızmaz.
    expect(tokenSeconds()).toBeGreaterThan(0);
    expect(motion.filter((item) => Math.abs(item.seconds - tokenSeconds()) > 0.001), 'token dışı süre').toEqual([]);
    expect(motion.filter((item) => item.property.split(',').some((part) => part.trim() === 'all')), 'transition: all').toEqual([]);
    // Ana düğmenin rengi iki yönde de yumuşak değişir. Geçiş temel kuraldadır, yalnız hover dalında değildir.
    const button = motion.filter((item) => item.where.includes('pf-m-primary') || item.where.includes('at-choice'));
    expect(button.length, 'ana düğmede geçiş var').toBeGreaterThan(0);
  });
}

test('azaltılmış hareket tercihinde geçiş ve animasyon kalkar', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await screen('sign-in').open(page);
  const motion = await collectMotion(page);
  expect(motion.filter((item) => item.seconds > 0.011)).toEqual([]);
});

test('stil kaynağı: hareket yalnız merkezi değişkenlerden gelir', () => {
  const body = readCss().replace(/\/\*[\s\S]*?\*\//g, '');
  expect(body.match(/transition\s*:\s*all/g) ?? [], 'transition: all yasak').toEqual([]);
  const declarations = body.match(/(transition|animation)(-timing-function|-duration)?\s*:[^;]+;/g) ?? [];
  const local = declarations.filter((line) => /\b(ease|ease-in|ease-out|ease-in-out|linear|steps)\b|\d+m?s\b/.test(line.replace(/var\([^)]*\)/g, '')));
  expect(local, 'yerel eğri ya da süre').toEqual([]);
  expect(body).toContain('--at-motion-easing-standard: cubic-bezier(.65, 0, .35, 1)');
});

test('stil kaynağı: yuvarlak kutuya renkli kenar çizgisi ve çevreleyen odak yok', () => {
  const body = readCss().replace(/\/\*[\s\S]*?\*\//g, '');
  // Tek kenara renk veren kural yoktur. Kenarlık ya dört kenardadır ya da hiç yoktur.
  const oneSide = body.match(/border-(left|right|top|bottom|inline|block)(-start|-end)?(-color|-width|-style)?\s*:\s*(?!0|none)[^;]+;/g) ?? [];
  expect(oneSide, 'tek kenarlı çizgi').toEqual([]);
  expect(body.match(/box-shadow\s*:[^;]*inset[^;]*;/g) ?? [], 'iç gölge çubuğu').toEqual([]);
  // outline yalnız sıfırlanır. Tek istisna zorlanmış renk dalıdır.
  const outlines = (body.match(/outline\s*:[^;]+;/g) ?? []).filter((line) => !/outline\s*:\s*(0|none)/.test(line));
  expect(outlines).toEqual(['outline: 2px solid CanvasText;']);
  expect(body.match(/:focus-within/g) ?? [], ':focus-within çerçevesi').toEqual([]);
});
