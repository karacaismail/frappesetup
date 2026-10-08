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
- Mantine `Shell.tsx` tek `client:load` adasıdır; markdown içeriği statik HTML olarak slot'tan geçer. Gezgin adası ikinci bir `MantineProvider` kullanır ama CSS değişkeni/global sınıf enjekte etmez (`withCssVariables={false}`) ve renk şemasını `html[data-mantine-color-scheme]` özniteliğinden `forceColorScheme` ile izler.
- Yazı tipleri kendinden barındırılır (`@fontsource-variable/inter`, `@fontsource/jetbrains-mono`); üçüncü taraf font isteği yoktur (KVKK).
- Genel sabitler (`AS_OF`, `REPO_URL`, hafta sayısı) `src/data/site.ts`; bölüm üst verisi `src/data/sections.ts`; faz listesi (P0–P6) `src/data/phases.json`.
- Renk şeması: `ColorSchemeScript defaultColorScheme="auto"` + `data-mantine-color-scheme`; koyu tema tokenları `global.css` içinde yeniden tanımlanır.

## Arayüz kuralları (kalıcı)

- Tasarım tokenları: `src/theme.ts` (Mantine) ve `src/styles/global.css` (`--fs-ink`, `--fs-quiet`, `--fs-line`, `--fs-grid`, `--fs-surface*`, `--fs-accent*`, `--fs-tint`, `--fs-focus`). Bileşen içinde sabit renk/boyut yazılmaz.
- Okunabilir metin ≥ 1rem: Mantine `fontSizes.xs/sm = 1rem`; statik SVG diyagramlarda yazı 16+ birim ve `min-width: 65rem` ile ölçek ≥ 1; Mermaid SVG'leri `Mermaid.tsx` içinde doğal genişliğe (rem) sabitlenir, figür yatay kayar. Kontrast: ikincil metin `--mantine-color-dimmed` → gray-7 / dark-1 (`cssVariablesResolver`), vurgu açık temada sea-8; rozetler dolgulu + `autoContrast`.
- Tek odak göstergesi: yalnız `:focus-visible`, `outline: 2px solid var(--fs-focus)` (`--fs-focus` = Mantine birincil dolgu rengi); global `:focus { outline: none }` ve odakta `border-radius` yazılmaz; kapsayıcıya `:focus-within` çerçevesi verilmez. Gereksiz `tabindex="0"` eklenmez; yalnız klavyeyle kaydırma için gerekli odaklanabilirlik (tablo sarmalayıcısı `.table-wrap`) korunur.
- Tablolar kendi kapsayıcısında yatay kayar (Sätteri hast eklentisi `src/lib/satteri-table-wrap.mjs` → `div.table-wrap[tabindex=0][role=region]`; gezginde Mantine `Table.ScrollContainer`); hücrelerde `word-break: normal`, kelime ortasından bölünmez; `body` yatay taşmayı gizlemez, testler `scrollWidth` ile yakalar.
- Açılır listeler Mantine `Select` (native `<select>` yok).
- Mobil öncelik: 320 px'ten başlar; test matrisi `tests/smoke.spec.ts` içinde (taşma + ≥1rem tüm sayfalarda 320'de, 6 sayfada 7 viewport; odak/Tab/Shift+Tab; Select klavye; yön değişimi; 125 % kök yazı; reduced-motion; axe açık/koyu; iPhone 13 dokunma profili). Yeni bileşen bu testlere eklenmeden teslim edilmez.

## Performans bütçesi (ölçüm: `astro build`, gzip -c, 8 Ekim 2026)

| Varlık | Ölçülen (gzip) | Bütçe |
| --- | --- | --- |
| Kabuk JS (React/ReactDOM `client` + `Shell`) | 65 KB + 20 KB = 85 KB | ≤ 100 KB |
| Gezgin adası (`RequirementsExplorer`, yalnız Gereksinimler sayfası) | 23 KB | ≤ 30 KB |
| Mermaid yükleyici (`Mermaid`); mermaid çekirdeği yalnız diyagramlı sayfada dinamik | 2 KB (+ mermaid chunk'ları isteğe bağlı) | — |
| CSS (Mantine + global + fontsource bildirimleri) | 54 KB + 2 KB | ≤ 70 KB |
| Yazı tipleri (Inter Variable latin 48 KB + latin-ext 85 KB; JetBrains Mono 400/600 ≈ 22 KB × 2) | ilk görünümde ≈ 155 KB | ≤ 200 KB |
| HTML: ana sayfa / tipik bölüm / Gereksinimler (157 kayıt × markdown tablo + SSR tablo + ada props) | 17 KB / 13 KB / 177 KB | 25 / 25 / 200 KB |

Bütçe aşımı bir teslim engelidir; Gereksinimler sayfası üç kopya taşıdığı için büyümesi önce burada ele alınır (ör. markdown tabloyu gezginden türetmek).

## Teslim ve Git

- Git yazarı/committer: `karacaismail <35493655+karacaismail@users.noreply.github.com>`; AI/bot `Co-Authored-By` veya üretim imzası eklenmez; yazar koruma hook'ları atlanmaz.
- Depo public ve açık kaynaktır: kod MIT (`LICENSE`), içerik CC BY 4.0 (`LICENSE-CONTENT`). Secret, gerçek `.env`, kişisel veri eklenmez.
- Dağıtım: `main`'e push → `.github/workflows/deploy.yml` önce `npm ci`, derleme ve Playwright koşar; testler geçmeden Pages artifact'ı yüklenmez. `ci.yml` pull request'lerde aynı kapıyı çalıştırır. Gerçek macOS/iOS Safari doğrulaması emülasyondan ayrı raporlanır.
