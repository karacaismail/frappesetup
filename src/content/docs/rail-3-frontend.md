---
title: "Rail 3 — Headless frontend geliştirme planı"
nav: "Rail 3 · Frontend"
order: 6
---

Rail 3, tek bir React SPA build'inin her sitenin kendi host'undan sunulmasını sağlar: kiracı host'unda (`https://<kiracı>.app.<marka>.com.tr/panel`, Frappe v16 `/api/v2`) ve Press sitesinin public alan adında (`https://panel.<marka>.com.tr`, `press.api.*` / `press_tr.api.*`, Frappe v15). Her site kendi host'una bağlı oturum ve CSRF belirteciyle çalışır; ortak oturum ve CORS yoktur (G-13, G-45, G-75, G-119); aynı kabuğun operatör (superadmin) modu yalnız özel ağdaki `operator.<marka>.com.tr` origin'inde, operatör BFF'iyle (`ops-bff`) aynı origin'den sunulur (SA-24, G-119). Tüm ekranlar DocType meta'sından üretilir; elle kodlanan tek şey kabuk, eşleme katmanı ve açık override kayıtlarıdır (G-69). Bu bölüm P1 çıkış ölçütlerinin frontend tarafını tanımlar.

## 1. Monorepo ve paket sınırları (G-66, G-103)

| Paket | Sorumluluk | Bağlı gereksinim |
| --- | --- | --- |
| `@platform/design-tokens` | AntD `theme.token`/`theme.components` semantik token seti, light/dark algoritması, Tenant Branding çalışma zamanı katmanı | G-67, G-97 |
| `@platform/frappe-sdk` | `/api/v2` + `press.api.*` istemcisi, CSRF, hata eşlemesi, socket.io, TanStack Query anahtar sözleşmesi | G-68 |
| `@platform/meta-ui` | Field type → AntD eşlemesi, liste/form/CRUD üreticileri, override registry, çekirdek doctype codegen tipleri | G-69, G-70, G-71 |
| `@platform/shell` | Layout, metadata sidebar, komut paleti, bildirim merkezi, ayarlar/yetki/faturalama ekranları, URL sözleşmesi ve paylaşım, yardım kulakçığı, tur ve keşif, ölçüm adapterları ve rıza merkezi, destek rıza bandı, operatör modu | G-93–G-101, G-130–G-135, G-137, G-139, G-140, G-154, SA-24, SA-27 |
| `@platform/ai-sidebar` | `@ant-design/x` sağ panel, SSE akışı, önizle+onayla UI | G-86, G-88 |
| `@platform/support-session` | Hocuspocus provider, awareness/imleç katmanı, takip modu, uzaktan kontrol teklifi; yalnız aktif Support Session varken dinamik yüklenir | SA-29 |
| `@apps/<ad>` | `AppModule` arayüzü: rota ağacı, override'lar, çeviri, Prompts, onboarding | G-103 |

pnpm workspaces + Vite; uygulama paketleri yalnızca `get_bootstrap` kurulu uygulama listesinde geçenler için dinamik import edilir; CI'da Lighthouse bütçesi (ilk yük JS ≤ 300 KB gzip, LCP ≤ 2,5 s 4G) kapı görevi görür (G-66, X-13). Ant Design 6 + `@ant-design/x` 2 ile başlanır (`@ant-design/x` 2.9.0 eş bağımlılığı `antd ^6.1.1`; doğrulandı: npm, 2026-10-08).

**AI-first UI katmanı (karar).**

- **Bileşen ailesi:** Ant Design + Pro Components deterministik iş ve CRUD ekranları, Ant Design X agent etkileşimi, X Cards (A2UI) yapılandırılmış mesaj, katalog içeriği ve artifact yüzeyleri içindir. Registry, runtime ve politikanın yerine geçmez; kurulu sürüm ve uyum doğrulanacak (SUS-05).
- **Semantik yol:** kullanıcı niyeti → UI niyeti → Semantic UI modeli → politika ve doğrulama → bileşen registry'si (`@platform/meta-ui`) → runtime → UI. AI yalnız onaylı katalogdan deklaratif tanım üretir, keyfi React/HTML/CSS/JS üretmez (SEC-10). Kritik CRUD, kayıt düzenleme ve onay controlled UI'dır; dashboard, analiz, rapor ve workspace declarative UI; açık üretken UI yalnız izole, geçici artifact sandbox'ında; MCP Apps harici, araca ait yüzeydir.
- **Rol haritası (aday; hepsi birden kurulmaz):** OpenUI ana GenUI dil ve runtime adayı, satıcıdan bağımsız adaptör; AG-UI/CopilotKit agent ile frontend arası akış, durum, araç, olay ve insan onayı omurgası; A2UI taşınabilir deklaratif sözleşme; json-render, Tambo ve assistant-ui alternatif; Vercel AI SDK model, araç ve akış katmanı. Semantic UI modeli ve registry bu adaptörlerden bağımsızdır.

## 2. Shell yerleşimi (G-93, G-94, G-88)

- **Üst bar**: takım/site değiştirici (`press.api.account.switch_team`), global arama + komut paleti (`frappe.utils.global_search.search`, `frappe.desk.search.search_link`, navigasyon ve AI prompt'ları tek listede), bildirim sayacı, AI panel düğmesi, hesap menüsü.
- **Sol sidebar**: yalnızca G-63 bootstrap'ından türetilir; 320 px'te AntD Drawer olur, odak Drawer içinde tutulur, Escape kapatır.
- **İçerik**: TanStack Router rota ağacı URL sözleşmesine uyar (G-132): `/<uygulama>/<belge-türü>` liste, `/<uygulama>/<belge-türü>/<kimlik>` kayıt, filtre/sıralama/sayfa okunur sorgu parametreleri; iskelet yükleme, boş/hata/çevrimdışı durumları tokenlı bileşenlerle.
- **Yardım kulakçığı**: sağ kenarda yapışkan; kendi kendine destek modu alan, bileşen ve sayfa yardımını açar (G-137, G-138).
- **Sağ yuva (AI paneli veya yardım paneli)**: aynı anda biri açıktır; içerik sütunu ile panel yan yana sığmadığında (eşik içerikten belirlenir) tam ekran çekmece; sayfa bağlamı (doctype, belge, seçili satırlar, filtreler) yapılandırılmış olarak gönderilir (G-88).
- **Destek bandı**: Pending Support Access talebi ve aktif destek oturumu göstergesi (operatör presence, 'takip ediyor' durumu, 'Oturumu bitir') her sayfanın üstünde; uzaktan kontrol teklifi ayrı onay iletişim kutusuyla (SA-27, SA-29).
- **Operatör modu**: Keycloak operatör rolü bootstrap'ta geldiğinde sidebar operatör navigasyonuna (Müşteri 360, Tahsilat, Destek, KVKK raporu) geçer; tenant verisi ile operatör verisi aynı ekranda karışmaz (SA-24).
- Yön değişiminde form verisi, odak ve açık panel korunur; her eylemin klavye ve dokunma yolu vardır.

## 3. Metadata motoru: alan eşleme tablosu (G-69, G-61, G-63)

| Frappe fieldtype | AntD bileşeni | Not |
| --- | --- | --- |
| Data, Small Text, Long Text | `Input`, `Input.TextArea` | `length`, `options` (Email/Phone/URL) doğrulaması |
| Int, Float, Currency, Percent | `InputNumber` | formatter System Settings `number_format`/`currency_precision` |
| Date, Datetime, Time | `DatePicker`, `TimePicker` | dayjs `tr`, `date_format`/`time_format` |
| Select | `Select` | markalı açılır panel, `options` satırları |
| Link, Dynamic Link | `Select showSearch` (async) | `frappe.desk.search.search_link` + meta `filters` |
| Table MultiSelect | `Select mode="multiple"` | child doctype tek Link alanı |
| Table | düzenlenebilir child `Table` | satır ekle/sil, child permlevel |
| Check | `Switch` / `Checkbox` | liste filtresinde `Checkbox` |
| Attach, Attach Image | `Upload` | `upload_file`, `max_file_size` (G-48) |
| Text Editor, Markdown Editor, HTML Editor, Code, JSON | zengin editör / kod editörü | AntD dışı, token katmanına bağlı |
| Color, Rating, Duration, Geolocation, Signature | `ColorPicker`, `Rate`, süre girişi, harita, imza kanvası | Signature/Geolocation ayrı bileşen (doğrulanacak) |
| Section Break, Column Break, Tab Break | `Row`/`Col`, `Tabs`, `Collapse` | form yerleşimi |

Motor her alan için `read_only`, `reqd`, `hidden`, `depends_on`/`mandatory_depends_on`/`read_only_depends_on` ifadelerini, `fetch_from`, `set_only_once` ve efektif permlevel iznini (G-61) değerlendirir; sunucuyla aynı kural UI'da uygulanır. Metadata bütün ekranları kendiliğinden üretmez: temsilî ekranlarda her davranış sunucuda mevcut / metadata ile karşılanan / yeniden geliştirilecek sınıfına yazılır (G-123); `eval:` ifadeleri `eval` veya `new Function` olmadan güvenli ayrıştırıcıyla yorumlanır, desteklenmeyen ifade alanı görünür bırakır ve doğrulamayı sunucuya bırakır. Override registry `overrides/<doctype>.tsx` alan, bölüm, aksiyon ve liste sütunu düzeyinde açık kaçış kapısıdır. Çekirdek doctype tipleri (User, Employee, Sales Invoice gibi) CI'da v16 meta'sından codegen ile üretilir; kalan her şey çalışma zamanı `GET /api/v2/doctype/<doctype>/meta` (doğrulandı: Frappe version-16 `api/v2.py`) + `getdoctype` çıktısından okunur. Önbellek iki katmanlıdır (G-63, X-12): şema katmanı `site + meta hash/ETag` ile anahtarlanır ve IndexedDB'de tutulabilir; kullanıcıya bağlı izin katmanı (site, kullanıcı, `perm_version`) yalnız bellektedir; çıkış ve kiracı değişimi tarayıcı katmanlarını siler; Site Update Success ve Customize Form kaydı `meta_changed` realtime olayıyla önbelleği düşürür.

## 4. Workspace'ten navigasyon (G-94)

Sidebar şu veriden kurulur: kurulu uygulama → üst öğe (Marketplace App ikon/ad, G-95); çocuklar Workspace Sidebar Item kayıtları — `type` (Link / Section Break / Spacer / Sidebar Item Group), `link_type` (DocType / Page / Report / Workspace / Dashboard / URL), `link_to`, `icon`, `child`, `indent`, `collapsible`, `keep_closed`, `filters` ve `route_options` (JSON), `open_in_new_tab`, `default_workspace` (doğrulandı: version-16 `workspace_sidebar_item.json`). `filters`/`route_options` TanStack Router arama parametrelerine çevrilir; `has_permission` ve rol filtresi sunucuda (G-63) uygulanır. Kurulu olmayan uygulamalar yalnızca "Uygulamalar" mağaza girişinde görünür; aktivasyon Agent Job Success sonrası `get_bootstrap` yeniden çekilir (G-30).

## 5. Veri katmanı ve realtime (G-68, G-13, G-15, G-45)

| İşlem | Kiracı (Frappe v16) | Press (v15) |
| --- | --- | --- |
| Liste / sayım | `GET /api/v2/document/<dt>`, `GET /api/v2/doctype/<dt>/count` | `press.api.client.get_list` |
| Belge CRUD | `GET/POST/PATCH/DELETE /api/v2/document/<dt>/<name>` | `press.api.client.get/insert/set_value/delete` |
| Metot | `POST /api/v2/method/<path>`, `/api/v2/method/run_doc_method` | `press.api.client.run_doc_method`, `press_tr.api.*` |
| Meta / bootstrap | `platform_core.api.meta.get_doctype`, `api.shell.get_bootstrap` | `press.api.site.get_plans`, `press_tr.api.billing.*` |
| Operatör modu | `platform_core.api.ops.customer_360` (operasyon sitesi, BFF üzerinden; tarayıcıdan doğrudan istek yok) | `press.api.client.*` + `press_tr.api.ops` (BFF, operatör kimliği) (SA-23, SA-25, K-16) |

SDK kuralları: `credentials: include` + `X-Frappe-CSRF-Token` (token `www/<panel>.py` enjeksiyonundan, G-45); `_server_messages`/`exc_type` eşlemesi — `ValidationError` → alan hataları, `PermissionError` → yetki ekranı + `explain_permission` (G-62), `CSRFTokenError` → token yenile ve bir kez tekrar dene; TanStack Query anahtarları `[site, doctype, 'list'|'doc'|'meta', params]`; mutasyon sonrası ilgili anahtarlar geçersizlenir. Realtime: kiracıda socket.io `doc_subscribe`/`doctype_subscribe` ile `doc_update`, `list_update`, `meta_changed`; Press'te `agent_job_update` (G-15) aktivasyon ilerlemesini ve site durumunu besler; her bağlantı kendi host'unun oturumuyla, aynı origin'den açılır (G-119).

## 6. i18n (G-73)

Türkçe birinci dil, İngilizce ikinci. AntD `trTR` locale, dayjs `tr`, biçimler System Settings'ten. Frappe çevirileri için `frappe.translate.get_all_translations(lang)` v16'da whitelisted değildir (doğrulandı), bu yüzden `platform_core.api.i18n.get_translations(lang)` sarmalayıcısı uygulama `.po` çevirilerini tek sözlükte döner ve dil + uygulama sürümüyle önbelleklenir. Panel metinleri `@platform/shell` kataloğunda; backend Select değerleri (`NEFT` gibi) yalnızca etiket katmanında Türkçeleştirilir (G-19).

## 7. Token sistemi AntD üzerinde (G-67)

- Marka kimliği yalnızca `ConfigProvider theme.token` + `theme.components` ile; her renk, boşluk, radius ve gölge değeri token referansıdır; light/dark algoritma `theme.algorithm`.
- Tek `:focus-visible` göstergesi token olarak (`colorPrimaryBorder` türevi, zeminle ≥3:1); gösterge yalnızca klavye odağındaki kontrolde görünür, kapsayıcılar ve tablo satırları fare/dokunma seçiminde odak göstergesinden bağımsız kalır (G-70).
- Yazı tipi Outfit (başlık ve gövdede font-family listesinin ilk ailesi), kod için monospace; lisans ve dağıtım hakkı doğrulanacak. Tüm okunabilir metin ≥1rem ve semantik ölçekle: gövde, tablo, input ve yardımcı metin 1rem/400; menü, buton ve etiket 1rem/500; bölüm başlığı 1.125–1.25rem/600; sayfa başlığı 1.5–2rem/600. AntD, Pro Components ve X tokenları (`fontFamily`, `fontFamilyCode`, `fontSize`, `fontSizeSM`, `fontSizeHeading*`, satır yüksekliği) birlikte ayarlanır; kök font kullanıcı tercihini korur, kurulu sürümün rem davranışı ölçülür.
- Kenarlık yalnızca işlevsel (form alanı, tablo ızgarası, seçili durum); ayrım boşluk ve yüzey hiyerarşisiyle.
- Select/Dropdown/DatePicker açılır panelleri aynı token setinden markalanır.
- Tenant Branding (logo, birincil renk) `get_bootstrap` ile gelir ve `theme.token.colorPrimary` üzerine çalışma zamanında bindirilir; kontrast denetimi (≥4,5:1 metin) uygulanır.

## 8. Mobil öncelikli kabul ve QA planı (G-74, X-20)

| Katman | Araç | Kabul |
| --- | --- | --- |
| Birim / tip | Vitest, TypeScript strict, `AppModule` sözleşme testi | CI yeşil (G-103) |
| Meta üretimi | Snapshot: v16 çekirdek meta → üretilen form/liste | codegen diff'i boş |
| E2E kritik yolculuk | Playwright: giriş (Keycloak), sidebar, liste, form, aktivasyon, ödeme, destek rızası | Chromium/Firefox/WebKit × 320/360/375/390/yatay/tablet/masaüstü |
| Etkileşim | fare, dokunma, Tab/Shift+Tab, Escape, ok tuşları | tek odak göstergesi, Drawer odak tuzağı |
| Görsel regresyon | Playwright screenshot + DOM/ARIA denetimi | 320'de sayfa genişliği viewport'a eşit, tablo kendi kapsayıcısında kaydırır |
| Performans | Lighthouse CI + Playwright ağ ölçümü | G-66 bütçesi; koşullu yükleme ağ isteğiyle kanıtlanır (G-149) |
| Gerçek cihaz | macOS/iOS Safari, Android Chrome | emülasyondan ayrı pass/fail/not\_run |

Erişilebilirlik ölçütü WCAG 2.2 AA'dır. Uygulama sırası 320 → 360 → 375 → 390 → yatay telefon → tablet → masaüstü; kapsam 320 kabulü sağlandıktan sonra genişler. Yön değişimi, sanal klavye, safe area (`env(safe-area-inset-*)`), zoom %200 ve `prefers-reduced-motion` her kritik yolculukta kontrol edilir. Raporda tarayıcı/OS/viewport/giriş profili, komut ve trace kaydı bulunur; çalıştırılmayan kontrol `not_run` olarak yazılır. P1 çıkışı: çekirdek doctype'larda liste/form/CRUD meta'dan üretilmiş, sidebar bootstrap'tan türemiş, CSRF/CORS sözleşmesi doğrulanmış ve bu matris yeşil.
