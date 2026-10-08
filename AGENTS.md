# frappesetup — ajan talimatları

Astro 7 + React 19 + Mantine 9 statik dokümantasyon sitesi; GitHub Pages'te `https://karacaismail.github.io/frappesetup/` (`base: /frappesetup`, `trailingSlash: always`). Node ≥ 22.12 (yerelde 24). Site, kapalı SaaS ürününün tasarım ve karar çerçevesidir; SaaS henüz kurulmadı: sayfalardaki kontroller gereksinimdir, uygulanmış güvenlik gibi sunulmaz.

## Komutlar

- Geliştirme sunucusu: `astro dev --background` (durdur/izle: `astro dev stop`, `astro dev status`, `astro dev logs`).
- Üretim: `npm run build` → `dist/`; `npm run preview`.
- Testler: `npm run build && npm run test:e2e` (Playwright; Chromium, Firefox, WebKit × 320/360/375/390/yatay telefon/tablet/masaüstü; iPhone 13 emülasyonu yalnız `@touch`). 4329 portu doluysa `PW_PORT=<port> npm run test:e2e`. Tarayıcılar yoksa `npx playwright install chromium firefox webkit`.
- Görsel regresyon: `tests/visual.spec.ts` yalnız Linux'ta koşar (yazı işleme işletim sistemine göre değişir; macOS'ta atlanır, yerel geçiş görsel kapının kanıtı değildir). Referanslar `tests/__screenshots__/<proje>/` altındadır ve yalnız GitHub'ın `ubuntu-24.04` koşucusunda üretilir (test işleri bu etikete sabitlidir; `ubuntu-latest` 19 Ekim 2026'da Ubuntu 26'ya geçer; koşucu imajı ya da Playwright sürümü değişince referanslar aynı prosedürle yeniden üretilip onaylanır): dalı push et, `gh workflow run deploy.yml --ref <dal> -f visual_baseline=true` (bu kip yalnız referans artifact'ı üretir; deploy işi ve Pages adımları main dışında ve bu kipte koşmaz), artifact'ı indir, uygulayıcıdan bağımsız salt okunur görsel onaydan sonra commit et, sonra aynı dalda `visual_baseline=false` ile gerçek karşılaştırmayı koştur. Referans eksikse Linux kapısı başarısız olur; referanslar sessizce veya toplu güncellenmez. Diyagram görüntülerinde sabit başlık `tests/visual-hide-chrome.css` ile gizlenir (`stylePath`). `deploy.yml` eşzamanlılık grubu main dışındaki ref'lerde ayrıdır; dal koşusu bekleyen main dağıtımını iptal ettiremez.
- Diyagramlar: `python3 scripts/gen-diagrams.py` (`Rails.astro`, `Timeline.astro`; zaman çizelgesi `phases.json`'daki `start`/`end` haftalarından üretilir; elle düzenlenmez).
- Markdown eklentisi (`src/lib/satteri-table-wrap.mjs`) değişince içerik önbelleğini temizleyin: `rm -rf node_modules/.astro`.
- Tip denetimi için ayrı bir `astro check` kurulumu yok; derleme ve testler kapıdır.

## Mimari kararlar

- İçerik `src/content/docs/*.md` (glob loader, şema: `title`, `nav`, `order`). Başlıklar `##`/`###`; `<`/`>` kod dışında kaçışlı.
- `src/data/requirements.json` gereksinimlerin tek doğruluk kaynağıdır (G ve SA serileri, kimlikler korunur, yeni kalem sona eklenir). Gezgin, dağılım özeti (`RequirementSummary.astro`) ve faz tablosundaki kimlik listesi (`PhaseTable.astro`) derleme anında bundan üretilir; markdown'da elle tablo kopyası tutulmaz. `tests/consistency.spec.ts` kimlik bütünlüğünü, G/SA/K atıflarını, iç bağlantıları ve rapor faz kararlarını denetler.
- `src/data/phases.json`: faz hedefi, çıkış ölçütü, sahip ve `start`/`end` haftası; yol haritası tablosu, ana sayfa kartları ve zaman çizelgesi aynı kaynaktan.
- Derleme anında üretilen bloklar markdown'daki `<div data-embed="ad">` yer tutucusuna sayfa betiğiyle taşınır (`rails`, `timeline`, `phase-table`, `req-summary`; tanım `src/pages/[slug].astro`).
- Mermaid blokları Shiki dışında bırakılır (`excludeLangs: ['mermaid']`) ve `Mermaid.tsx` adasında çizilir; mermaid yalnızca ilgili sayfada dinamik import ile yüklenir. Figür adları sayfada benzersizdir.
- Diyagramlar statik SVG; renkler yalnız `--fs-*` / `--mantine-*` CSS değişkenlerinden. Kaydırma bölgesi (`role=region`, `tabindex=0`) figürün içindeki `div.diagram-scroll`'dur; figcaption'lı `<figure>` role=region almaz.
- Mantine `Shell.tsx` tek `client:load` adasıdır; markdown içeriği statik HTML olarak slot'tan geçer. Kabuk JS bütçesi için kabukta yalnız gerekli Mantine bileşenleri kullanılır: gezinme bağlantıları ve simge düğmeleri sade `a`/`button` öğeleridir ve `global.css`'teki token kurallarıyla çizilir (Tooltip, ScrollArea, NavLink, ActionIcon yok). Gezgin adası ikinci bir `MantineProvider` kullanır ama CSS değişkeni/global sınıf enjekte etmez (`withCssVariables={false}`) ve renk şemasını `html[data-mantine-color-scheme]` özniteliğinden `forceColorScheme` ile izler.
- Gezgin ada JS'i inmeden yazılan arama metnini ve anahtar durumunu bağlanınca duruma alır (React 19.3 hidrasyonda erken girdiyi yeniden oynatmaz); durum tutmayan düğmelere hidrasyondan önce yapılan tıklama işlem yapmaz (veri kaybı yok, bilinçli kabul).
- Yazı tipleri kendinden barındırılır (`@fontsource-variable/inter`, `@fontsource/jetbrains-mono`); üçüncü taraf font isteği yoktur (KVKK).
- Genel sabitler (`AS_OF`, `REPO_URL`, hafta sayısı) `src/data/site.ts`; bölüm üst verisi ve gruplar (Çerçeve, Raylar, Sözleşmeler, Teslim) `src/data/sections.ts`.
- Renk şeması: `ColorSchemeScript defaultColorScheme="auto"` + `data-mantine-color-scheme`; koyu tema tokenları `global.css` içinde yeniden tanımlanır.

## Arayüz kuralları (kalıcı)

- Tasarım tokenları: `src/theme.ts` (Mantine) ve `src/styles/global.css` (`--fs-ink`, `--fs-quiet`, `--fs-line`, `--fs-grid`, `--fs-surface*`, `--fs-accent*`, `--fs-tint`, `--fs-focus`). Bileşen içinde sabit renk/boyut yazılmaz.
- Okunabilir metin ≥ 1rem: Mantine `fontSizes.xs/sm = 1rem`; statik SVG diyagramlarda yazı 16+ birim ve `min-width: 65rem` ile ölçek ≥ 1; Mermaid SVG'leri `Mermaid.tsx` içinde doğal genişliğe (rem) sabitlenir, figür yatay kayar. Kök yazı %125 ve %200'e büyütüldüğünde de metin yeni 1rem'in altına inmez ve yerleşim taşmaz: ana sayfa sütunları viewport medya sorgusuyla değil kapsayıcı sorgusuyla değişir; dar kapsayıcıda numara+metin kartları alt alta dizilir; başlık çubuğunda marka adı kısalır, eylem düğmeleri görünür kalır. Kontrast: ikincil metin `--mantine-color-dimmed` → gray-7 / dark-1 (`cssVariablesResolver`), vurgu açık temada sea-8; bağlantı içindeki kod `--fs-accent-ink`; rozetler dolgulu + `autoContrast`.
- Tek odak göstergesi: yalnız `:focus-visible`, `outline: 2px solid var(--fs-focus)` (`--fs-focus` = Mantine birincil dolgu rengi); global `:focus { outline: none }` ve odakta `border-radius` yazılmaz; kapsayıcıya `:focus-within` çerçevesi verilmez. Mantine girişlerinde odakta kenarlık rengi değişmez (`--input-bd-focus` dinlenme kenarlığına eşit), gösterge yalnız outline'dır; hata/başarı kenarlıkları korunur. Gereksiz `tabindex="0"` eklenmez; yalnız klavyeyle kaydırma için gerekli odaklanabilirlik (tablo sarmalayıcısı `.table-wrap`, `div.diagram-scroll`) korunur.
- Etkili dokunma alanı görsel boyuttan ayrı tokendır: `--fs-hit` (ince işaretçi 44 px, `any-pointer: coarse` iken 48 px). Tek başına duran her kontrol (gezinme ve içindekiler bağlantıları, simge ve menü düğmeleri, sayfa geçişleri, ana sayfa bağlantı/kartları, gezginin düğme, özet, anahtar ve arama alanı, Mermaid kaynak özeti) bu alanı karşılar; metin içi bağlantılar açık istisnadır. `tests/smoke.spec.ts` 'touch targets' iki profilde ölçer.
- Tema düğmesi `useComputedColorScheme` ile adlanır: kayıtlı tercih yokken (`auto`) işletim sistemi şeması esas alınır.
- Tablolar kendi kapsayıcısında yatay kayar (Sätteri hast eklentisi `src/lib/satteri-table-wrap.mjs` → `div.table-wrap[tabindex=0][role=region]`, ad sayfada benzersiz: önceki başlık + sıra; gezginde Mantine `Table.ScrollContainer`); hücrelerde `word-break: normal`, kelime ortasından bölünmez; `body` yatay taşmayı gizlemez, testler `scrollWidth` ile yakalar.
- Açılır listeler Mantine `Select` ile yapılır (native `<select>` yok). Gezginin faz/ray/kaynak süzgeçleri açılır liste değil `aria-pressed` düğme gruplarıdır (yerel `<details>` içinde); açılır panel kodu adayı bütçeden taşırdı.
- Mobil öncelik: 320 px'ten başlar; test matrisi `tests/smoke.spec.ts` içinde: taşma + ≥1rem tüm sayfalarda 320'de, 6 sayfada 7 viewport; %125/%200 kök yazı; odak (tek görünür outline yalnız odaklanan öğede ya da görünmez Switch girdisinin izinde; kenarlık/gölge ikinci çerçeve yok; Tab/Shift+Tab); süzgeç düğmeleri klavye; hidrasyon öncesi tek yazım (masaüstü ve 320 `@touch`); yön değişimi; reduced-motion; axe (tüm sayfalar × açık/koyu; WCAG 2.0/2.1/2.2 A-AA + best-practice; her etki düzeyi başarısızlık; otomatik kural kapsamıdır, tam AA uyumu iddiası değildir); ağ bütçesi; iPhone 13 dokunma profili. Yeni bileşen bu testlere eklenmeden teslim edilmez. Gerçek macOS/iOS Safari ve Android ayrı raporlanır; çalıştırılmayan kontrol `not_run` yazılır.

## Performans bütçesi (ölçüm: `npm run build` + Playwright ağ testi, gzip zlib varsayılan düzey, 8 Ekim 2026)

| Varlık | Ölçülen (gzip) | Bütçe |
| --- | --- | --- |
| Kabuk JS: ilk görünümde gereken tüm parçalar (React/ReactDOM `client`, `Shell`, paylaşılan Mantine/tema ve React parçaları) | 96,9 KB (giriş parçaları `client` + `Shell` 77,9 KB, ayrıca raporlanır) | ≤ 100 KB |
| Gezgin adası: Gereksinimler sayfasının kabuğa ek indirdiği JS | 17,3 KB | ≤ 30 KB |
| Mermaid yükleyici (`Mermaid`); mermaid çekirdeği yalnız diyagramlı sayfada dinamik | 2,1 KB (+ mermaid parçaları isteğe bağlı) | — |
| CSS (Mantine + global + fontsource bildirimleri) | 53,1 KB + 1,7 KB | ≤ 70 KB |
| Yazı tipleri (Inter Variable latin + latin-ext; JetBrains Mono 400/600) | ilk görünümde ≈ 155 KB | ≤ 200 KB |
| HTML: ana sayfa / tipik bölüm / Gereksinimler | 18,0 KB / 12,9 KB / 196,5 KB | 25 / 25 / 200 KB |

Kabuk bütçesinin kapsamı ilk görünümün toplam JS'idir; giriş parçalarıyla daraltılmaz. Önceki "85 KB" bildirimi yalnız giriş parçalarını sayıyordu; aynı derlemenin gerçek toplamı 125,2 KB idi. Kabuktan Tooltip/ScrollArea/NavLink/ActionIcon çıkarılıp gezgin süzgeçleri düğme grubuna çevrilince 96,7 KB'a indi (tema ve gezinme düzeltmeleriyle 96,9 KB). Bütçe aşımı bir teslim engelidir. Gereksinimler sayfası sınıra yakındır (196,5 / 200 KB): büyümeden önce SSR'da tek görünüm (kart veya tablo) üretmek ele alınır; açık iş olarak İzlenebilirlik sayfasındadır.

## Teslim ve Git

- Git yazarı/committer: `karacaismail <35493655+karacaismail@users.noreply.github.com>`; AI/bot `Co-Authored-By` veya üretim imzası eklenmez; yazar koruma hook'ları atlanmaz.
- Depo public ve açık kaynaktır: kod MIT (`LICENSE`), içerik CC BY 4.0 (`LICENSE-CONTENT`); bu seçimin onay kaydı açık karardır (K-32). Secret, gerçek `.env`, kişisel veri eklenmez.
- Dağıtım: `main`'e push → `.github/workflows/deploy.yml` önce `npm ci`, derleme ve Playwright koşar; testler geçmeden Pages artifact'ı yüklenmez. `ci.yml` pull request'lerde aynı kapıyı çalıştırır. Playwright HTML raporu her koşuda artifact olarak yüklenir. Action'lar tam commit SHA'sına sabitlidir (yorumda sürüm); güncellemede etiket→SHA eşleşmesi `gh api repos/<owner>/<repo>/commits/<etiket>` ile doğrulanır. Gerçek macOS/iOS Safari doğrulaması emülasyondan ayrı raporlanır.
