# frappesetup — ajan talimatları

Astro 7 + React 19 + Mantine 9 statik dokümantasyon sitesi; GitHub Pages'te `https://karacaismail.github.io/frappesetup/` (`base: /frappesetup`, `trailingSlash: always`). Node ≥ 22.12 (yerelde 24).

## Komutlar

- Geliştirme sunucusu: `astro dev --background` (durdur/izle: `astro dev stop`, `astro dev status`, `astro dev logs`).
- Üretim: `npm run build` → `dist/`; `npm run preview`.
- Testler: `npm run build && npm run test:e2e` (Playwright; Chromium, Firefox, WebKit × 320/360/375/390/yatay telefon/tablet/masaüstü). Tarayıcılar yoksa `npx playwright install chromium firefox webkit`.
- Tip denetimi için ayrı bir `astro check` kurulumu yok; derleme ve testler kapıdır.

## Mimari kararlar

- İçerik `src/content/docs/*.md` (glob loader, şema: `title`, `nav`, `order`). Başlıklar `##`/`###`; `<`/`>` kod dışında kaçışlı.
- `src/data/requirements.json` gereksinimlerin tek doğruluk kaynağıdır (157 kayıt); Gereksinimler sayfasındaki gezgin bunu okur.
- Mermaid blokları Shiki dışında bırakılır (`excludeLangs: ['mermaid']`) ve `Mermaid.tsx` adasında çizilir; mermaid yalnızca ilgili sayfada dinamik import ile yüklenir.
- Diyagramlar statik SVG (`Rails.astro`, `Timeline.astro`), renkler yalnız `--fs-*` / `--mantine-*` CSS değişkenlerinden; markdown'daki `<div data-embed="…">` yer tutucusuna sayfa betiğiyle taşınır.
- Mantine `Shell.tsx` tek `client:load` adasıdır; markdown içeriği statik HTML olarak slot'tan geçer. Başka adalar (gezgin) kendi `MantineProvider`'ını sarar.
- Renk şeması: `ColorSchemeScript defaultColorScheme="auto"` + `data-mantine-color-scheme`; koyu tema tokenları `global.css` içinde yeniden tanımlanır.

## Arayüz kuralları (kalıcı)

- Tasarım tokenları: `src/theme.ts` (Mantine) ve `src/styles/global.css` (`--fs-ink`, `--fs-quiet`, `--fs-line`, `--fs-grid`, `--fs-surface*`, `--fs-accent*`, `--fs-tint`, `--fs-focus`). Bileşen içinde sabit renk/boyut yazılmaz.
- Okunabilir metin ≥ 1rem: Mantine `fontSizes.xs/sm = 1rem`; SVG diyagramlarda yazı 16+ birim ve `min-width: 65rem` ile ölçek ≥ 1 korunur.
- Tek odak göstergesi: yalnız `:focus-visible`, `outline: 2px solid var(--fs-focus)`; kapsayıcıya `:focus-within` çerçevesi verilmez; `tabindex="0"` eklenmez.
- Tablolar kendi kapsayıcısında yatay kayar (`.prose table { display:block; overflow-x:auto }`, Mantine `Table.ScrollContainer`); hücrelerde `word-break: normal`, kelime ortasından bölünmez; sayfa gövdesi yatay taşmaz.
- Açılır listeler Mantine `Select` (native `<select>` yok).
- Mobil öncelik: 320 px'ten başlar; test matrisi `tests/smoke.spec.ts` içinde. Yeni bileşen bu testlere eklenmeden teslim edilmez.

## Teslim ve Git

- Git yazarı/committer: `karacaismail <35493655+karacaismail@users.noreply.github.com>`; AI/bot `Co-Authored-By` veya üretim imzası eklenmez; yazar koruma hook'ları atlanmaz.
- Depo public ve açık kaynaktır: kod MIT (`LICENSE`), içerik CC BY 4.0 (`LICENSE-CONTENT`). Secret, gerçek `.env`, kişisel veri eklenmez.
- Dağıtım: `main`'e push → `.github/workflows/deploy.yml`; `ci.yml` derleme + Playwright çalıştırır. Gerçek macOS/iOS Safari doğrulaması emülasyondan ayrı raporlanır.
