# frappesetup — ajan talimatları

Astro 7 + React 19 + Mantine 9 statik dokümantasyon sitesi; GitHub Pages'te `https://karacaismail.github.io/frappesetup/` (`base: /frappesetup`, `trailingSlash: always`). Node ≥ 22.23.4 (astro 7.4 alt sınırı; yerelde ve CI'da 24). Site, kapalı SaaS ürününün tasarım ve karar çerçevesidir; SaaS henüz kurulmadı: sayfalardaki kontroller gereksinimdir, uygulanmış güvenlik gibi sunulmaz.

## Komutlar

- Geliştirme sunucusu: `astro dev --background` (durdur/izle: `astro dev stop`, `astro dev status`, `astro dev logs`).
- Üretim: `npm run build` → `dist/`; `npm run preview`.
- Testleri `npm run build && npm run test:e2e` komutuyla çalıştırın. Playwright, Chromium ve WebKit kullanır. Testler 320, 360, 375 ve 390 piksel genişliklerini kapsar. Yatay telefon, tablet ve masaüstü de denenir. iPhone 13 emülasyonu yalnız `@touch` senaryolarında çalışır. 4329 portu doluysa `PW_PORT=<port> npm run test:e2e` kullanın. Tarayıcılar eksikse `npx playwright install chromium webkit` çalıştırın.
- `npm run test:e2e` Playwright'ı `scripts/agir-test` ile çalıştırır. Bu betik ortak test kilidini alır. Aynı anda en çok 2 ağır test koşar. Doğrudan `npx playwright test` komutu yerelde hata verir. `GITHUB_ACTIONS=true` iken kilit gerekmez. Yerelde kök ayar en çok 4 işçi açar. Bu bağın testlerini `node --test scripts/tests/agir-test-bagla.test.mjs` komutuyla çalıştırın.
- Firefox testi yalnız bu iş için açık kullanıcı talimatıyla çalışır. Varsayılan yerel testler ve CI, Firefox çalıştırmaz. Eski test kayıtları korunur.
- Görsel regresyon: `tests/visual.spec.ts` yalnız Linux'ta koşar (yazı işleme işletim sistemine göre değişir; macOS'ta atlanır, yerel geçiş görsel kapının kanıtı değildir). Referanslar `tests/__screenshots__/<proje>/` altındadır ve yalnız GitHub'ın `ubuntu-24.04` koşucusunda üretilir (test işleri bu etikete sabitlidir; `ubuntu-latest` 19 Ekim 2026'da Ubuntu 26'ya geçer; koşucu imajı ya da Playwright sürümü değişince referanslar aynı prosedürle yeniden üretilip onaylanır): dalı push et, `gh workflow run deploy.yml --ref <dal> -f visual_baseline=true` (bu kip yalnız referans artifact'ı üretir; deploy işi ve Pages adımları main dışında ve bu kipte koşmaz), artifact'ı indir, uygulayıcıdan bağımsız salt okunur görsel onaydan sonra commit et, sonra aynı dalda `visual_baseline=false` ile gerçek karşılaştırmayı koştur. Referans eksikse Linux kapısı başarısız olur; referanslar sessizce veya toplu güncellenmez. Diyagram görüntülerinde sabit başlık `tests/visual-hide-chrome.css` ile gizlenir (`stylePath`). `deploy.yml` eşzamanlılık grubu main dışındaki ref'lerde ayrıdır; dal koşusu bekleyen main dağıtımını iptal ettiremez.
- Diyagramlar: `python3 scripts/gen-diagrams.py` (`Rails.astro`, `Timeline.astro`; faz sırası çizimi `phases.json`'daki `after` bağımlılıklarından üretilir; elle düzenlenmez).
- Markdown eklentisi (`src/lib/satteri-table-wrap.mjs`) değişince içerik önbelleğini temizleyin: `rm -rf node_modules/.astro`.
- Tip denetimi için ayrı bir `astro check` kurulumu yok; derleme ve testler kapıdır.

## Mimari kararlar

- Site marka ayarını `backend/brand.env` dosyasından okur. Dosyada gizli bilgi bulunmaz.
- `src/data/site.ts`, `PRODUCT_NAME` ve `BRAND_DOMAIN` değerlerini verir. Ortak ayrıştırıcı `src/lib/brand.mjs` dosyasındadır.
- Güncel Markdown metinleri `{{PRODUCT_NAME}}` ve `{{BRAND_DOMAIN}}` işaretlerini kullanır. Sätteri eklentisi bu işaretleri derlemede doldurur.
- Eklenti adı marka ayarından üretilen bir özet taşır. Ayar değişince Astro eski içerik önbelleğini bırakır.
- Başlıkları, gezinme adlarını ve JSON metinlerini gösteren bileşenler aynı ayarı kullanır. Teknik adresler ve gereksinim kimlikleri değişmez.
- Tarihsel sayfalar `acik-kararlar.md`, `karar-katalogu.md` ve `izlenebilirlik.md` dosyalarıdır. `task-board.json` içindeki geçmiş notlar da korunur. Tam liste `backend/brand-exclusions.txt` dosyasındadır.
- Diyagram üreticisi marka değerini çıktıya yazmaz. Üretilen Astro bileşeni marka değerini site ayarından alır. Marka değişince yalnız siteyi derlemek yeterlidir.
- Diyagram etiketi, gerçek yazı genişliğini ölçer. Ad kutuya sığmazsa etiket “Giriş ürünü” olur. Tam ad, diyagram açıklamasında görünür kalır. Yazı küçültülmez.
- `npm run build`, önce `npm run test:brand` kontrolünü çalıştırır. `npm run test:brand-build`, farklı ayarla ayrı çıktı üretir. Bu kontrol geçici olarak marka dosyasını değiştirir. Kontrol bitince dosya geri yüklenir. Bu kontrolü aynı klasördeki diğer derlemelerle birlikte çalıştırmayın.
- Ürün adı yer tutucusundan sonra kesme işaretiyle ek yazılmaz. Cümlede örneğin `{{PRODUCT_NAME}} ürününü` kullanılır. Site taraması bu kuralı denetler. Derleme testi dört sayfayı farklı ürün adlarıyla denetler.
- Marka derleme testi, Chromium ile uzun adı ve diyagram işaretlerini denetler. Mevcut CI akışları testi ilk tarayıcı parçasında çalıştırır.

- İçerik `src/content/docs/*.md` (glob loader, şema: `title`, `nav`, `order`). Başlıklar `##`/`###`; `<`/`>` kod dışında kaçışlı.
- `src/data/requirements.json` gereksinimlerin tek doğruluk kaynağıdır (G ve SA serileri, kimlikler korunur, yeni kalem sona eklenir). Gezgin, dağılım özeti (`RequirementSummary.astro`) ve faz tablosundaki kimlik listesi (`PhaseTable.astro`) derleme anında bundan üretilir; markdown'da elle tablo kopyası tutulmaz. `tests/consistency.spec.ts` kimlik bütünlüğünü, G/SA/K atıflarını, iç bağlantıları ve rapor faz kararlarını denetler.
- `src/data/task-board.json` görev panosunun sunum verisidir. Dosyada epic listesi, durum kuralları ve olgunluk düzeyi kuralları vardır. Her gereksinimin epiği, durumu ve düzeyi de bu dosyadadır. Durumlar `done`, `in-progress`, `not-started` ve `unverified` değerleridir. Düzeyler `poc`, `mvp`, `post-mvp`, `scale` ve `enterprise` değerleridir. `requirements.json` kayıtlarına dokunulmaz. "Bitti" yalnız kanıtla yazılır: commit ve depoda var olan test dosyası. Düzey elle seçilmez: faz eşlemesi ve adı yazılı istisna listesinden türer. `tests/consistency.spec.ts` kapsamayı, kuralları ve kanıtı denetler. Gezgin aynı veriyi tablo ve gruplu (faz, sonra epic) görünümde gösterir. Kurallar tablosu `TaskBoardRules.astro` ile `task-rules` yer tutucusuna derlenir.
- Görev panosu güncel kalır. Bir gereksinimi bitiren ya da ilerleten dal, aynı dalda `task-board.json` kaydını da günceller. Dal kaydın `status` alanını değiştirir. "Bitti" için `evidence` alanına commit ve test dosyasını yazar. Dal `update` bloğunu da günceller. Blokta tarih, commit, `release`, not ve `reviewed` listesi vardır. Commit, güncellemenin dayandığı son birleşmedir. `reviewed` listesinde yalnız denetim dışında kalan ve güncellemenin okuduğu kalemler bulunur. Örnek: G-155 bir P3 kalemidir ama denetimden sonra eklendi. Bu kalem ancak `reviewed` listesindeyse durum alabilir. Sayfa tarihi ve commit'i "Durumlar … günü backend dalındaki … commit'ine göre güncellendi." cümlesiyle gösterir. Canlı sunucuda denenmemiş dağıtım işi "Bitti" olmaz, "Sürüyor" kalır.
- Kanıt commit'leri `backend` dalındadır. Bu dal GitHub'a gitmez. `main` dalına her yayın tek commit olarak girer. Bu yüzden `audit`, `update` ve her `evidence` kaydında `release` alanı vardır. Alan `{ "pr": <numara>, "commit": "<main yayın commit'i>" }` biçimindedir. Commit henüz yayımlanmadıysa alan `null` olur. Alan doluysa sayfa PR bağlantısını gösterir. Alan `null` ise sayfa "henüz yayımlanmadı" yazar. Eşlemeyi git kaydından çıkarın. `main` yayın commit'i metninde "Birleşmeler" listesini ve "Kaynak:" satırını taşır. Kanıt commit'inin kısa adı bu listede geçer. PR numarası yayın commit'ini birleştiren PR'dır. Örnek komut: `gh pr list --state merged --json number,mergeCommit`. Yayın birleşince sonraki pano güncellemesi `null` alanları doldurur.
- `tests/consistency.spec.ts` kanıt commit'lerini her kopyada denetler. Denetim kopyanın türüne göre ayrılır:
  1. Commit yerelde varsa `HEAD` geçmişinde olmalıdır. `release` doluysa yayın commit'i de yerelde olmalıdır. Yayın commit'i metninde kanıt commit'ini adlandırmalıdır. `release` alanı `null` ise `origin/main` dalındaki hiçbir yayın commit'i onu adlandırmamalıdır.
  2. Backend geçmişi yerelde varsa eksik commit hatadır. Örneğin `refs/heads/backend` varsa uydurma commit kodu testi düşürür. Yayın commit'inin "Kaynak:" satırındaki commit yerelde varsa da backend geçmişi var sayılır.
  3. Tam geçmişli `main` kopyasında backend commit'leri yoktur. `release` doluysa yayın commit'i `HEAD` geçmişinde olmalı ve kanıt commit'ini adlandırmalıdır. `release` alanı `null` ise `HEAD` geçmişindeki bir yayın commit'i onu adlandırmalıdır. Bu yayın, dosyayı `main` dalına getiren yayındır.
  4. CI kopyası sığdır. Sığ kopyada yayın commit'i yerelde varsa kanıt commit'ini adlandırmalıdır. Yoksa yalnız alan biçimi denetlenir. `release` alanı `null` ise kayıt "henüz yayımlanmadı" sayılır.
  `update.commit`, iki commit de yerelde varsa `audit.commit` commit'inin torunu olmalıdır.
- `src/data/phases.json`: faz hedefi, çıkış ölçütü, sahip ve `after` önkoşul listesi (yalnız P2'de `entryGate`); yol haritası tablosu, ana sayfa kartları ve faz sırası çizimi aynı kaynaktan.
- Fazlara ve görevlere süre, hafta, story point ya da efor tahmini yazılmaz. Sıra yalnız bağımlılıkla anlatılır. `tests/consistency.spec.ts` site dosyalarını denetler. Ürün kuralı olan süreler (log saklama, deneme sitesi, oturum, K-26 yama hedefleri, yasal süreler, yedek sıklığı) bu yasağın dışındadır.
- `DocumentContent.astro`, Markdown'daki `<div data-embed="ad">` yer tutucularını derleme sırasında Astro bileşenleriyle değiştirir (`rails`, `timeline`, `phase-table`, `task-rules`, `dl-*`). Bileşenler `src/pages/[slug].astro` dosyasında slot olarak tanımlanır. Gereksinim dağılımı doğrudan sayfanın sonunda üretilir. Bilinmeyen yer tutucu derlemeyi durdurur. Aynı yer tutucu yinelenirse derleme durur. Playwright betiksiz sayfada blokların sırasını ve kabuk düğmelerini denetler.
- Mermaid blokları Shiki dışında bırakılır (`excludeLangs: ['mermaid']`) ve `Mermaid.tsx` adasında çizilir; mermaid yalnızca ilgili sayfada dinamik import ile yüklenir. Figür adları sayfada benzersizdir.
- Diyagramlar statik SVG; renkler yalnız `--fs-*` / `--mantine-*` CSS değişkenlerinden. Kaydırma bölgesi (`role=region`, `tabindex=0`) figürün içindeki `div.diagram-scroll`'dur; figcaption'lı `<figure>` role=region almaz.
- Mantine `Shell.tsx` tek `client:load` adasıdır; markdown içeriği statik HTML olarak slot'tan geçer. Kabuk JS bütçesi için kabukta yalnız gerekli Mantine bileşenleri kullanılır: gezinme bağlantıları ve simge düğmeleri sade `a`/`button` öğeleridir ve `global.css`'teki token kurallarıyla çizilir (Tooltip, ScrollArea, NavLink, ActionIcon yok). Gezgin adası ikinci bir `MantineProvider` kullanır ama CSS değişkeni/global sınıf enjekte etmez (`withCssVariables={false}`) ve renk şemasını `html[data-mantine-color-scheme]` özniteliğinden `forceColorScheme` ile izler.
- Sunucu tek gereksinim tablosu gönderir. Dar kapsayıcıda CSS satırları kart biçiminde gösterir. JavaScript kapalıyken de metin okunur. Kutu yalnız yatay taşınca Tab sırasına girer. Ekran genişliği değişince arama ve süzgeçler korunur.
- Sayfa içi gereksinim bağlantısını tarayıcı kaydırır. Gezgin yalnız ilk açılışta satıra odak verir. Satırda ayrı odak işareti gösterilmez. Tab tuşu hedef satırdan devam eder.
- Gezgin ada JS'i inmeden yazılan arama metnini ve anahtar durumunu bağlanınca duruma alır (React 19.3 hidrasyonda erken girdiyi yeniden oynatmaz); durum tutmayan düğmelere hidrasyondan önce yapılan tıklama işlem yapmaz (veri kaybı yok, bilinçli kabul).
- Yazı tipleri kendinden barındırılır (`@fontsource-variable/outfit`, `@fontsource/jetbrains-mono`; SIL OFL 1.1); üçüncü taraf font isteği yoktur (KVKK). Varsayılan arayüz ve belge fontu Outfit'tir (başlık, gövde, diyagram; `src/theme.ts`, `scripts/gen-diagrams.py`, `Mermaid.tsx` yedeği), kod JetBrains Mono. Outfit latin + latin-ext ile gelir (Türkçe harfler dahil); Yunanca gibi diğer betikler sistem yedeğinden çizilir.
- Genel sabitler (`AS_OF`, `REPO_URL`, karar ve ray sayısı) `src/data/site.ts`; bölüm üst verisi ve gruplar (Çerçeve, Raylar, Sözleşmeler, Teslim) `src/data/sections.ts`.
- Kenar çubuğunda `AI` grubu (`ai-*` sayfaları: genel bakış, MCP, skills, agents, Press yetkinliği, geliştirme planı, ProPR, sağlayıcı bağlantısı) açılır-kapanır tek üst öğedir (`COLLAPSIBLE_GROUPS` → `Shell.tsx` `CollapsibleGroup`: gerçek `<button aria-expanded>` + `hidden` panel; bağlantılar kapalıyken de HTML'dedir; kabuk bağlanana kadar düğme devre dışıdır. İlk görünümde yalnız AI sayfaları grubu açık tutar. Betiksiz masaüstü görünümünde `noscript` stili bağlantıları açar). AI sayfalarının içeriği depo incelemesine dayanır; kanıt tarihi ve "bulunamadı" ifadesi korunur, doğrulanmamış yetenek "çalışıyor" diye yazılmaz.
- Betiksiz masaüstü görünümünde AI bağlantıları adlandırılmış bir grupta kalır. Betiksiz telefonda “Doküman bölümlerini aç” bağlantısı ana sayfadaki bölüm listesine gider.
- Renk şeması: `ColorSchemeScript defaultColorScheme="auto"` + `data-mantine-color-scheme`; koyu tema tokenları `global.css` içinde yeniden tanımlanır.

## AI paketi (`packages/press-ai`)

- Press operasyonları ve Frappe uygulama geliştirme için stdio MCP sunucusu (`press-ai`, 14 araç), operasyon kontratı (`contracts/`), skills, agents. Python 3.9+ yalnız stdlib; site derlemesinden bağımsızdır. Arayüz sözleşmesi `packages/press-ai/INTERFACE.md`; işlem kimlikleri ve araç adları oradan değişir.
- Yetki: kullanıcının kendi Press API anahtarı (keychain/0600 dosya); `team` (Dashboard API) ve `operator` (Desk, System User) rolleri. Mutasyonlar yapılandırmada açılmadıkça kapalı, her biri öneri → ayrı terminalde insan onayı (`server.py approve`, TTY) → tek seferlik yürütme → `press_track`. Onay aracı yok; onay aynı OS hesabıyla yazılır ve yalnız hız kesicidir (güvenlik sınırı değildir; ayrı onaylayıcı hesabı desteklenmez, `approval.approver_uid` reddedilir). Shell/SSH/Server Script yok; eski yerel SSH MCP'si ayrı kalır ve değiştirilmez.
- Orijinal core dosyaları (resmi uygulamalar, `press` dahil) varsayılan olarak reddedilir: ilk istek uyarı döner, kullanıcı aynı değişikliği açıkça yinelerse öneri `CORE <uygulama>` ifadeli çift onayla oluşur; mutlak yasak değildir. Özel uygulama dosyaları bu kurala girmez ve normal yetkili akıştadır: özel DocType izinleri, izin/rol fixture'ları ve özel koddaki resmi modül yaması engellenmez (önizlemede not/uyarı). Secret, `.git`/gizli yol ve Git yazar koruması sınırları mutlaktır.
- Kontrat ile runtime birbirine testle bağlıdır: `implemented` statüsü, params şeması ve makine ön koşulları runtime'daki kod izin listesine eşit olmalı. Kontrat değişince `python3 -I packages/press-ai/server.py check-contract --guide <pressguide>/src/data/guide.json --sitemap <pressguide>/src/data/press-sitemap.json` 0 hata vermeli ve `ai-press-yetkinlik.md` kapsam bloğu `server.py coverage-markdown` ile yeniden üretilmeli.
- Kontroller: `python3 -I -m unittest discover -s packages/press-ai/tests` (sahte Press ve fixture uygulamalarla) ve `python3 -I packages/press-ai/server.py check-contract`; ikisi `ci.yml` ve `deploy.yml` içinde ayrı `press-ai` işinde koşar; toplayıcı iş (`build-and-test` / `Build and test`) bu işin geçmesini de bekler (koşucunun python3'ü, pressguide verisi olmadan). `PRESSGUIDE_DATA` verilmezse kılavuz sırası/sitemap kimlik denetimi atlanır. Canlı Press ve gerçek MCP istemci oturumu `not_run`.

## Arayüz kuralları (kalıcı)

- Site, WCAG 2.2 AA standardını izler. Ortak arayüz kararları `~/.claude/skills/coding-standards/references/ai-first-ui.md` dosyasındadır. Bu site Outfit kullanır. Gövde 1rem büyüklüğündedir. Gövde metninin satır yüksekliği yazı boyutunun 1,5 katıdır. Sayfa başlıkları 1,75 ile 2rem arasındadır. 320 pikselde sayfa başlığı bölüm başlığından en az 4 piksel büyüktür. Site, otomatik denetimde axe 4.13.0 kullanır. Araç, WCAG 2.2 ile gelen kurallardan yalnız `target-size` kuralını denetler. Diğer 2.2 ölçütleri elle denetlenir.
- Tasarım tokenları: `src/theme.ts` (Mantine) ve `src/styles/global.css` (`--fs-ink`, `--fs-quiet`, `--fs-line`, `--fs-grid`, `--fs-surface*`, `--fs-accent*`, `--fs-tint`, `--fs-focus`). Bileşen içinde sabit renk/boyut yazılmaz.
- Okunabilir metin en az 1rem olur. Mantine, `fontSizes.xs`, `fontSizes.sm` ve `fontSizes.md` için 1rem kullanır. Sabit SVG çizimlerinde yazı en az 16 birimdir. Çizimin en az 65rem genişliği, ölçeği 1'in altına düşürmez. Mermaid çizimleri `Mermaid.tsx` içinde doğal genişliklerinde kalır. Okur gerektiğinde çizimin kutusunu yatay kaydırır. Kök yazı %125 veya %200 olunca metin yeni 1rem'in altına inmez. Sayfa yatay taşmaz. Ana sayfa sütunları kapsayıcı genişliğine göre değişir. Dar kapsayıcıda numara ve metin alt alta gelir. 320 pikselde ve %100 kök yazıda marka adı fare ve dokunma girişinde tam görünür. Kök yazı %125 veya %200 olunca marka adı kısalır. Eylem düğmeleri görünür kalır. Kenar düğmelerinde `--fs-icon-box` görünen kutunun boyutunu belirler. `--fs-hit` ise tıklama ve dokunma alanını belirler. `cssVariablesResolver`, ikincil metin rengini `gray-7` veya `dark-1` yapar. Açık temada vurgu rengi `sea-8` olur. Bağlantı içindeki kod `--fs-accent-ink` kullanır. Rozetler zemin dolgusu ve `autoContrast` kullanır.
- Tek odak göstergesi: yalnız `:focus-visible`, `outline: 2px solid var(--fs-focus)` (`--fs-focus` = Mantine birincil dolgu rengi); global `:focus { outline: none }` ve odakta `border-radius` yazılmaz; kapsayıcıya `:focus-within` çerçevesi verilmez. Mantine girişlerinde odakta kenarlık rengi değişmez (`--input-bd-focus` dinlenme kenarlığına eşit), gösterge yalnız outline'dır; hata/başarı kenarlıkları korunur. Gereksiz `tabindex="0"` eklenmez; yalnız klavyeyle kaydırma için gerekli odaklanabilirlik (tablo sarmalayıcısı `.table-wrap`, `div.diagram-scroll`, taşan satır içi kod kutusu) korunur.
- Gereksinimler kutusu klavye odağını üst kenarda tek çizgiyle gösterir. Bu kural yalnız gezginin kaydırma kutusunda çalışır. Diğer kutuların odak düzeni ayrı bir işte ele alınır. Kutu daralınca mevcut odak korunur. Kullanıcı kutudan çıkınca gereksiz Tab durağı kaldırılır.
- Etkili dokunma alanı görsel boyuttan ayrı tokendır: `--fs-hit` (ince işaretçi 44 px, `any-pointer: coarse` iken 48 px). Tek başına duran her kontrol (gezinme ve içindekiler bağlantıları, simge ve menü düğmeleri, sayfa geçişleri, ana sayfa bağlantı/kartları, gezginin düğme, özet, anahtar ve arama alanı, Mermaid kaynak özeti) bu alanı karşılar; metin içi bağlantılar açık istisnadır. `tests/smoke.spec.ts` 'touch targets' iki profilde ölçer.
- Tema düğmesi `useComputedColorScheme` ile adlanır: kayıtlı tercih yokken (`auto`) işletim sistemi şeması esas alınır.
- Satır kırılımı. Metin boşluklarda, tirelerde ve doğal kırılma yerlerinde sarılır. `overflow-wrap: anywhere` ve `word-break: break-all` kullanmayın. Bu kurallar sığan sözcükleri de böler. `.page` yalnız satırdan uzun dizgiler için `overflow-wrap: break-word` kullanır. Kod sığarsa boşluklardan sarılabilir. Gezgin kesintisiz kodu bütün tutar. `[slug].astro` sığmayan kodu ölçer. Gerçekten taşan kutu tek satırda yatay kayar. Yalnız bu kutular Tab sırasına girer. WebKit bu kutuları kendiliğinden odaklamaz. Betik kutuya `role="group"` verir. Kutu adı “Kaydırılabilir kod” olur. Kod metni kutunun içinde kalır. Test 320 CSS px genişlikte en çok 186 kod durağına izin verir. Testte kök yazı %100 kalır. Betik çalışana kadar `break-word` yedek kuralı geçerlidir. Metne `<wbr>` veya ZWSP eklemeyin.
- Tablolar kendi kapsayıcısında yatay kayar (Sätteri hast eklentisi `src/lib/satteri-table-wrap.mjs` → `div.table-wrap[tabindex=0][role=region]`, ad sayfada benzersiz: önceki başlık + sıra; gezginde Mantine `Table.ScrollContainer`, ayrıntı hücresi `contain: inline-size` ile 1280/1366 px'te sığar); hücrelerde `word-break: normal`, kelime ortasından bölünmez; `body` yatay taşmayı gizlemez, testler `scrollWidth` ile yakalar.
- Açılır listeler Mantine `Select` ile yapılır (native `<select>` yok). Gezginin faz/ray/kaynak süzgeçleri açılır liste değil `aria-pressed` düğme gruplarıdır (yerel `<details>` içinde); açılır panel kodu adayı bütçeden taşırdı.
- Mobil öncelik: 320 px'ten başlar; test matrisi `tests/smoke.spec.ts` içinde: taşma + ≥1rem + sözcük bölünmesi (satırına sığan sözcük iki harf arasından bölünmez, zorlayıcı kırma kuralı yok) tüm sayfalarda 320'de, 6 sayfada 7 viewport; uzun satır içi kod (kendi kutusunda kayar, yalnız taşan kutu Tab sırasında, üç motor); %125/%200 kök yazı; odak (tek görünür outline yalnız odaklanan öğede ya da görünmez Switch girdisinin izinde; kenarlık/gölge ikinci çerçeve yok; Tab/Shift+Tab); süzgeç düğmeleri klavye; hidrasyon öncesi tek yazım (masaüstü ve 320 `@touch`); yön değişimi; reduced-motion; axe (tüm sayfalar × açık/koyu; WCAG 2.0/2.1/2.2 A-AA + best-practice; her etki düzeyi başarısızlık; otomatik kural kapsamıdır, tam AA uyumu iddiası değildir); ağ bütçesi; iPhone 13 dokunma profili. Yeni bileşen bu testlere eklenmeden teslim edilmez. Gerçek macOS/iOS Safari ve Android ayrı raporlanır; çalıştırılmayan kontrol `not_run` yazılır.

## Performans bütçesi (ölçüm: `npm run build` + Playwright ağ testi, gzip zlib varsayılan düzey, 22 Kasım 2026, astro 7.4.7 ve mermaid 12.2.0)

| Varlık | Ölçülen (gzip) | Bütçe |
| --- | --- | --- |
| Kabuk JS: ilk görünümde gereken tüm parçalar (React/ReactDOM `client`, `Shell`, paylaşılan Mantine/tema ve React parçaları) | 97,4 KB (giriş parçaları `client` + `Shell` 78,5 KB, ayrıca raporlanır) | ≤ 100 KB |
| Gezgin adası: Gereksinimler sayfasının kabuğa ek indirdiği JS | 19,0 KB (görev panosuyla, 23 Kasım 2026) | ≤ 30 KB |
| Mermaid yükleyici (`Mermaid`); mermaid çekirdeği yalnız diyagramlı sayfada dinamik | 2,1 KB (+ mermaid parçaları isteğe bağlı; `rail-4-keycloak` sayfasında kabuğa ek 196,4 KB, KaTeX inmez) | — |
| CSS (Mantine + global + fontsource bildirimleri) | 55,8 KB toplam (23 Kasım 2026) | ≤ 70 KB |
| Yazı tipleri (Outfit Variable latin + latin-ext; JetBrains Mono 400/600) | ilk görünümde 88,0 KB (Inter ile 172,2 KB) | ≤ 200 KB |
| HTML: ana sayfa / Kararlar / Gereksinimler | 20,6 KiB / 14,9 KiB / 155,8 KiB (25 Kasım 2026, site karar farkları taşındıktan sonra) | 25 / 25 / 180 KiB |
| HTML: Ölçüm ve gözlem | 24,2 KiB (25 Kasım 2026) | 25 KiB |

Kabuk bütçesi ilk görünümde inen tüm JavaScript dosyalarını kapsar. Giriş parçaları ayrıca ölçülür. Eski 85 KB hesabı yalnız giriş parçalarını saymıştı. Aynı derlemenin toplamı 125,2 KB idi. Kabuktan Tooltip, ScrollArea, NavLink ve ActionIcon çıktı. Gezgin süzgeçleri düğme grubuna geçti. Kabuk 96,7 KB oldu. Tema ve gezinme düzeltmelerinden sonra 96,9 KB ölçüldü. Astro 7.4.7 sürümü satır içi betiğe yaklaşık 0,2 KB gzip ekledi. Astro 7.3.7 ile eski HTML ölçümü 199,6 KB idi. Önceki sürüm, sunucuda kartları hazırlardı. Tarayıcı geniş ekranda boşta kaldığında tabloyu kurardı. Okur kartlara kaydırınca veya bir kart odaktayken görünüm değişmezdi. Bu dalda sunucu tek tablo gönderir. CSS, kapsayıcı genişliğine göre görünümü değiştirir. Gezgin, alan adları tekrarlanmayan kısa bir JSON dizisi alır. JSON, veriyi yazıyla taşıyan bir biçimdir. Bütçe aşımı teslimi durdurur.

## Teslim ve Git

- Git yazarı/committer: `karacaismail <35493655+karacaismail@users.noreply.github.com>`; AI/bot `Co-Authored-By` veya üretim imzası eklenmez; yazar koruma hook'ları atlanmaz.
- Depo public ve açık kaynaktır: kod MIT (`LICENSE`), içerik CC BY 4.0 (`LICENSE-CONTENT`); bu seçimin onay kaydı açık karardır (K-32). Secret, gerçek `.env`, kişisel veri eklenmez.
- Dağıtım: `main`'e push → `.github/workflows/deploy.yml` önce `npm ci`, derleme ve Playwright koşar; testler geçmeden Pages artifact'ı yüklenmez. `ci.yml` pull request'lerde aynı kapıyı çalıştırır. Playwright HTML raporu her koşuda artifact olarak yüklenir.
- CI yapısı (23 Kasım 2026): derleme bir kez yapılır (`dist` artifact'ı) → Playwright 4 parçalı matris (`e2e (n/4)`, `--shard`, `fail-fast: false`, parça başına blob raporu, `PW_BLOB=1`) → toplayıcı iş `needs.*.result` değerlerinin hepsi `success` değilse başarısız olur ve blob raporlarını tek `playwright-report` artifact'ına birleştirir. ProPR'ın beklediği denetim adı `build-and-test` toplayıcıdır; ad değişmez, toplayıcı `if: always()` ile koşar (atlanan zorunlu denetim yeşil sayılmasın diye). `deploy.yml` toplayıcısı (`build`, ad "Build and test") Pages artifact'ını test edilen aynı `dist`'ten yükler. Tarayıcı ve apt kurulumu `.github/actions/playwright-browsers` bileşik action'ıdır: `~/.cache/ms-playwright` Playwright sürümüyle, `.deb` paketleri Playwright sürümü + koşucu imajı sürümüyle (`ImageOS`-`ImageVersion`, anahtarın sonunda) önbelleğe alınır; önbellek varsa `apt-get update` çalışmaz. Tam anahtar yoksa aynı işletim sisteminin en yeni eski imaj paketleri denenir (`restore-keys`). Önbellekteki dosyalar önce `/var/cache/apt/archives` klasörüne kopyalanır: `apt-get install --no-download` bu klasör dışındaki dosyaları kurmaz (24 Kasım 2026 bulgusu, AJA-364; o güne kadar önbellek hiç kullanılmamıştı). Önbellekten kurulum olmazsa ağdan kurulur. Ağ denemesinin süre sınırı 240 sn, deneme sayısı 3'tür; her başarısız denemeden sonra `/etc/apt/apt-mirrors.txt` içindeki ilk ayna sona alınır (yavaş ama yanıt veren aynaya apt kendiliğinden hata vermez). Ölçüm: eski tek iş akışında `playwright install --with-deps` 42–1453 sn (apt ayna hızı), testler 2 işçiyle 553–902 sn sürüyordu. Parça sayısı değişirse `--shard` toplamı `npx playwright test --list` toplamıyla karşılaştırılır. Action'lar tam commit SHA'sına sabitlidir (yorumda sürüm); güncellemede etiket→SHA eşleşmesi `gh api repos/<owner>/<repo>/commits/<etiket>` ile doğrulanır. Gerçek macOS/iOS Safari doğrulaması emülasyondan ayrı raporlanır.

### Ortak bitti tanımı: test ortamını kapatma ve paralel test sınırı

Kural A Takımı, B Takımı ve SAFe ekibi için ortaktır. Kural 27 Kasım 2026 Cuma günü yazıldı. Kaynak işler AJA-1799, AJA-1807 ve AJA-1804 kayıtlarıdır.

Bu kuralın bir nedeni var. 27 Kasım 2026 Cuma günü Mac aşırı yüklendi. Yük ortalaması 450 oldu. Makinede 18 işlemci var. 70 eski test kapsayıcısı açık kalmıştı. 40'tan fazla test tarayıcısı aynı anda açıktı.

#### Kural 1: İş bitince kendi ortamınızı kapatın

Ajan bir işi "bitti" saymadan önce şu adımları yapar:

1. Açtığınız `astro dev` sunucusunu kapatın. Komut `astro dev stop` olur.
2. Açtığınız `astro preview` sürecini kapatın. Yalnız kendi başlattığınız süreci kapatın.
3. Açtığınız `fs-dev-ortam-*` kapsayıcılarını kapatın. Adın sonundaki port sizin portunuz olmalıdır.
4. Açtığınız `fs-e2e-*` kapsayıcılarını kapatın. Yalnız kendi işinizin ortamını kapatın.
5. Kapsayıcının kapandığını `docker ps` ile denetleyin.
6. İş kaydına kısa bir not yazın. Örnek: "Ortamlarım kapalı: fs-dev-ortam-43820."

Veri birimlerini silmeyin. Kapatma ile silme ayrı işlerdir.

#### Kural 2: Ortamı bilerek açık bırakırsanız nedenini yazın

Bazen ortam bir sonraki iş için açık kalmalıdır. Bu durumda iki bilgiyi kendi iş kaydınıza yazın:

- Ortamın tam adını yazın. Örnek: `fs-e2e-7150-8ceae9a08e8e3b85fd78`.
- Açık kalma nedenini ve ortamı kimin kapatacağını yazın.

Neden yazılmazsa iş "bitti" sayılmaz.

#### Kural 3: Aynı anda en çok 2 ajan ağır test koşar

Ağır test komutları ortak bir kilitle koşar. Kilidin 2 yeri vardır. Üçüncü ajan bir yer boşalana kadar bekler.

Ağır testler şunlardır:

- `npm run test:e2e` komutu ve her Playwright koşusu,
- `backend/e2e` altındaki uçtan uca test yığını.

Backend yığınının açılışı, testi ve kapanışı aynı kilidin içindedir. İki test türü aynı kilidi paylaşır. `metafrappe` deposu da ağır test koşarsa aynı kilidi kullanır.

Kilit yöntemi şöyledir:

1. Sarmalayıcı betik `scripts/agir-test` dosyasıdır. Betik kilidi alır ve sonra testi çalıştırır.
2. Kilit klasörü `~$(id -un)/.cache/frappesetup-test-kilidi` olur. Betik klasörü kullanıcı adından bulur. Betik `HOME` değişkenine bakmaz. Bazı ajanlar ayrı `HOME` ile koşar.
3. Klasörde iki dosya vardır: `yer-1` ve `yer-2`. Klasörün adı ve yer sayısı değişmez.
4. Betik önce `yer-1` dosyasını dener. Bu yer doluysa `yer-2` dosyasını dener.
5. Kilit macOS'taki `/usr/bin/lockf` aracıyla alınır. Komut `lockf -k -s -t 0` olur. Bu Mac'te `flock` aracı yoktur.
6. İki yer de doluysa betik 10 ile 20 saniye bekler. Sonra yeniden dener. Beklerken ekrana "Test sırası bekleniyor" yazar.
7. Kilidi alan betik `AGIR_TEST_YER` değişkenini koyar. Bu değişken varsa iç içe çağrı yeni kilit almaz.
8. Test bitince kilidi işletim sistemi bırakır. Süreç çökse bile kilit kalmaz.
9. GitHub CI işlerinde kilit atlanır. Betik bunu `GITHUB_ACTIONS=true` değerinden anlar. `CI` değişkeni kilidi atlatmaz.

Doğrudan `npx playwright test` komutu yerelde hata verir. Yerelde her zaman `npm run test:e2e` komutunu kullanın.

Yerel Playwright işçi sayısı 4 olur. CI'daki işçi sayısı değişmez.

Kilidi atlatmayın. Kilit dosyasını elle silmeyin.

#### Sınırlar

- Başka ajanın ortamını kapatmayın. Yalnız kendi açtığınız ortamı kapatın.
- Temizlik için cron, rutin veya zamanlanmış iş kurmayın. Temizlik her işin son adımıdır.
- Canlı sunucuya dokunmayın.
