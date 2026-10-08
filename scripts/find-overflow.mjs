// Yatay taşma avcısı: verilen sayfalarda viewport dışına taşan (sabit konumlu olmayan,
// kaydırılabilir bir atası bulunmayan) öğeleri listeler.
// Kullanım: node scripts/find-overflow.mjs <baseURL> <genişlik> <yol...>
import { chromium } from '@playwright/test';

const [base = 'http://127.0.0.1:4329/frappesetup/', widthArg = '320', ...paths] = process.argv.slice(2);
const width = Number(widthArg);
const browser = await chromium.launch();
for (const path of paths.length ? paths : ['']) {
  const page = await browser.newPage({ viewport: { width, height: 800 } });
  await page.goto(base + path, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  const r = await page.evaluate(() => {
    const w = document.documentElement.clientWidth;
    const skip = (el) => {
      for (let p = el; p && p !== document.body; p = p.parentElement) {
        const cs = getComputedStyle(p);
        if (cs.position === 'fixed') return true;
        if (p !== el && cs.overflowX !== 'visible') return true;
      }
      return false;
    };
    const out = [];
    for (const el of document.querySelectorAll('body *')) {
      if (skip(el)) continue;
      const b = el.getBoundingClientRect();
      if (b.right > w + 1 && b.width > 0) {
        out.push({
          right: Math.round(b.right),
          left: Math.round(b.left),
          width: Math.round(b.width),
          el: `${el.tagName}.${String(el.className).slice(0, 60)}`,
          text: (el.textContent || '').trim().slice(0, 40),
        });
      }
    }
    out.sort((a, b) => b.right - a.right);
    return { w, scrollWidth: document.documentElement.scrollWidth, top: out.slice(0, 6) };
  });
  console.log(`/${path}`, JSON.stringify(r, null, 1));
  await page.close();
}
await browser.close();
