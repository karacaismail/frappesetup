# frappesetup

Frappe üzerinde çok kiracılı SaaS için **mimari karar çerçevesi ve yol haritası** — Press kontrol düzlemi (Frappe v15), ERPNext v16 müşteri siteleri, Keycloak kimlik, Ant Design tabanlı headless React panel, MCP/Claude Agent SDK AI katmanı ve superadmin operasyon düzlemi. On sabit karar, altı ray, 157 numaralı gereksinim (G-1..G-118, SA-1..SA-39) ve yedi fazlı yol haritası.

Yayın: **https://karacaismail.github.io/frappesetup/**

## Yığın

- [Astro 7](https://astro.build) — statik site, içerik koleksiyonları (`src/content/docs/*.md`)
- [Mantine 9](https://mantine.dev) + React 19 — kabuk (AppShell, NavLink, Select, Table), tema ve renk şeması
- [Mermaid 12](https://mermaid.js.org) — markdown içindeki ```` ```mermaid ```` blokları istemcide çizilir
- [Playwright](https://playwright.dev) — Chromium / Firefox / WebKit × 320–1366 px duman testleri
- GitHub Pages — `.github/workflows/deploy.yml` (`withastro/action`), `base: /frappesetup`

## Yapı

```
src/
  content/docs/        14 bölüm (frontmatter: title, nav, order)
  data/requirements.json   157 gereksinim (id, title, detail, rail, priority, phase, source, owner)
  data/phases.json         P0–P5 faz hedef ve çıkış ölçütleri
  components/Shell.tsx     MantineProvider + AppShell adası (navbar, TOC, tema düğmesi)
  components/RequirementsExplorer.tsx   süzülebilir gereksinim tablosu (Gereksinimler sayfası)
  components/Mermaid.tsx   mermaid bloklarını SVG'ye çevirir, temayla yeniden çizer
  components/Rails.astro / Timeline.astro   statik SVG diyagramlar (CSS token renkleri)
  layouts/Site.astro       <head>, ColorSchemeScript, navigasyon, Shell
  pages/index.astro, pages/[slug].astro
  theme.ts                 Mantine createTheme — "sea" birincil palet, Inter, yazı boyutları ≥ 1rem
  styles/global.css        semantik tokenlar (--fs-*), tipografi, tablo, odak göstergesi
tests/smoke.spec.ts        taşma, metin boyutu, odak, menü, tema, gezgin, mermaid testleri
```

## Komutlar

```bash
npm install
npm run dev          # http://localhost:4321/frappesetup/
npm run build        # dist/
npm run preview      # üretim çıktısını yerelde sun
npm run test:e2e     # astro preview'ı kendisi başlatır; önce `npm run build` gerekir
```

İlk Playwright çalıştırmasından önce: `npx playwright install chromium firefox webkit`.

## İçerik kuralları

- Her bölüm `src/content/docs/<slug>.md`; `order` navigasyon sırasını belirler.
- Gereksinim listesi `src/data/requirements.json` dosyasının tek doğruluk kaynağıdır; markdown tabloları metinsel kopyadır.
- Diyagram yer tutucuları: `<div data-embed="rails"></div>` ve `<div data-embed="timeline"></div>`; ilgili Astro bileşeni sayfa yüklenince bu noktaya taşınır.
- Sürüm ve tarih referansları 8 Ekim 2026 itibarıyladır; "(doğrulanacak)" işaretli maddeler teyit bekler.

## Lisans

- Kaynak kod: [MIT](LICENSE)
- İçerik (metin, tablo, diyagram; `src/content/`, `src/data/` ve bunlardan üretilen sayfalar): [CC BY 4.0](LICENSE-CONTENT)
