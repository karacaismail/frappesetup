# frappesetup

Frappe üzerinde çok kiracılı SaaS için **mimari karar çerçevesi ve yol haritası** — Press kontrol düzlemi (Frappe v15), ERPNext v16 müşteri siteleri, Keycloak kimlik, Ant Design tabanlı headless React panel, MCP/Claude Agent SDK AI katmanı ve superadmin operasyon düzlemi. On sabit karar, altı ray, ürün sözleşmeleri (kalite kuralları, URL ve paylaşım, ölçüm, yardım ve tur), 198 numaralı gereksinim (G-1..G-154, SA-1..SA-44) ve yedi fazlı yol haritası. SaaS henüz kurulmadı: sayfalardaki kontroller tasarım sözleşmesidir, uygulanmış güvenlik sayılmaz.

Yayın: **https://karacaismail.github.io/frappesetup/**

## Yığın

- [Astro 7](https://astro.build) — statik site, içerik koleksiyonları (`src/content/docs/*.md`)
- [Mantine 9](https://mantine.dev) + React 19 — kabuk (AppShell), gezgin, tema ve renk şeması
- [Mermaid 12](https://mermaid.js.org) — markdown içindeki ```` ```mermaid ```` blokları istemcide, yalnız ilgili sayfada çizilir
- [Playwright](https://playwright.dev) — Chromium / Firefox / WebKit × 320–1366 px kapıları, axe, ağ bütçesi
- Yazı tipleri: Outfit ve JetBrains Mono (SIL OFL 1.1), fontsource paketleriyle kendinden barındırılır
- GitHub Pages — `.github/workflows/deploy.yml`: `npm ci`, derleme ve Playwright kapısı geçince Pages artifact'ı yüklenir

## Yapı

```
src/
  content/docs/            26 bölüm (frontmatter: title, nav, order)
  data/requirements.json   gereksinimlerin tek kaynağı (id, title, detail, rail, priority, phase, source, owner)
  data/phases.json         P0–P6 faz hedefi, çıkış ölçütü, sahip, başlangıç/bitiş haftası
  data/sections.ts         bölüm grubu, ikon, özet
  components/Shell.tsx     MantineProvider + AppShell adası (gezinme, TOC, tema düğmesi)
  components/RequirementsExplorer.tsx   süzülebilir gereksinim gezgini (Gereksinimler sayfası)
  components/RequirementSummary.astro   dağılım özeti (JSON'dan)
  components/PhaseTable.astro           faz tablosu ve faz başına kimlik listesi (JSON'dan)
  components/Mermaid.tsx   mermaid bloklarını SVG'ye çevirir, temayla yeniden çizer
  components/Rails.astro / Timeline.astro   statik SVG diyagramlar (scripts/gen-diagrams.py üretir)
  layouts/Site.astro, pages/index.astro, pages/[slug].astro
  theme.ts, styles/global.css   tasarım tokenları, tipografi, tablo, odak göstergesi
tests/smoke.spec.ts        taşma, metin boyutu, sözcük bölünmesi, uzun satır içi kod, odak, dokunma hedefi, tema, gezgin, hidrasyon, diyagram, axe, ağ bütçesi
tests/visual.spec.ts       Linux görsel regresyon (referanslar tests/__screenshots__)
tests/consistency.spec.ts  gereksinim/faz/karar/bağlantı tutarlılığı
```

## Komutlar

```bash
npm ci
npm run dev          # http://localhost:4321/frappesetup/
npm run build        # dist/
npm run preview      # üretim çıktısını yerelde sun
npm run test:e2e     # astro preview'ı kendisi başlatır; önce `npm run build` gerekir
PW_PORT=4391 npm run test:e2e   # 4329 doluysa başka port
python3 scripts/gen-diagrams.py # diyagramları phases.json'dan yeniden üretir
```

İlk Playwright çalıştırmasından önce: `npx playwright install chromium firefox webkit`.

## İçerik kuralları

- Her bölüm `src/content/docs/<slug>.md`; `order` navigasyon sırasını belirler.
- Gereksinimler yalnız `src/data/requirements.json` dosyasında tutulur; Gereksinimler sayfasındaki tablo, dağılım özeti ve yol haritasındaki faz başına kimlik listesi derleme anında bundan üretilir. Mevcut kimlikler değiştirilmez; yeni kalem serinin sonuna eklenir.
- Derleme anında üretilen bloklar `<div data-embed="…">` yer tutucusuna taşınır (`rails`, `timeline`, `phase-table`, `req-summary`).
- Sürüm, lisans ve davranış iddiaları [kaynak defterine](https://karacaismail.github.io/frappesetup/izlenebilirlik/) sürüm/commit ve doğrulama türüyle yazılır; "(doğrulanacak)" işaretli maddeler teyit bekler. Tarihler 8 Ekim 2026 itibarıyladır.

## Doğrulama kapsamı

Kapılar ve son durum [İzlenebilirlik](https://karacaismail.github.io/frappesetup/izlenebilirlik/) sayfasındaki QA tablosundadır. Görsel regresyon testleri (`tests/visual.spec.ts`) yalnız Linux CI'da koşar; referans üretimi ve onay adımları `AGENTS.md`'dedir. axe kapısı otomatik kuralların kapsadığını kanıtlar, tam WCAG AA uyumu iddiası değildir; WebKit ve iPhone 13 emülasyondur, gerçek macOS/iOS Safari ve Android doğrulaması `not_run` olarak ayrı raporlanır; yerel geçiş CI geçişi sayılmaz.

## Lisans

- Kaynak kod: [MIT](LICENSE)
- İçerik (metin, tablo, diyagram; `src/content/`, `src/data/` ve bunlardan üretilen sayfalar): [CC BY 4.0](LICENSE-CONTENT)
- Bu seçimin ürün sahibi onay kaydı açık karardır (K-32); lisans dosyaları bu sürümde değiştirilmedi.
