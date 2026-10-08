---
title: "Rapor kapanışı ve kaynak defteri"
nav: "İzlenebilirlik"
order: 19
---

Bu sayfa değerlendirme raporundaki her maddenin sonucunu ve bu sürümdeki doğrulanmış iddiaların kaynağını tek yerde izlenebilir kılar; rapor metnini kopyalamaz. Durumlar: **kapatıldı** (doküman veya kod değişti), **karar bekliyor** (açık karar numarasıyla), **açık iş** (gerekçesiyle). Kapatılan mimari maddeler tasarım sözleşmesidir; SaaS henüz kurulmadığı için uygulanmış veya test edilmiş güvenlik sayılmaz.

## Rapor bulguları

| Madde | Konu | Sonuç | Nerede |
| --- | --- | --- | --- |
| T-03 | Araştırmanın kararlara izlenebilir bağlanması | Kapatıldı: kaynak defteri (aşağıda) ve kalıcı kayıt kuralı G-128 | Bu sayfa |
| Y-01 | P2'nin P6 çıktısına bağımlılığı | Kapatıldı: operasyon sitesi finans çekirdeği P2'ye alındı (SA-17, SA-18, SA-19, SA-21, SA-22, SA-23, SA-34, SA-35) | [Yol haritası](/frappesetup/yol-haritasi/) |
| Y-02 | P1 dilimi ve P0 kabulünün sonraki faz kalemlerine bağımlılığı | Kapatıldı: AI ve destek adımları ayrı kabullü prototip (G-129, SA-40); P0 çıkışı yalnız P0 kalemlerine dayanır | [Yol haritası](/frappesetup/yol-haritasi/) |
| Y-03 | SSO ile site oturumunun karışması, origin | Kapatıldı: host'a bağlı oturum ve origin tablosu, CORS yok (G-119); tarayıcı belirteç modeli önerisi | [Rail 4](/frappesetup/rail-4-keycloak/); karar bekliyor K-25 |
| Y-04 | DNS delegasyonu ile kiracı adresi | Kapatıldı: kiracılar `<kiracı>.app.<marka>.com.tr` | [Raylar](/frappesetup/raylar/), K-2 |
| Y-05 | Fatura senkronu için birden fazla olay modeli | Matris kapatıldı (SA-41); vergi ve belge zamanlaması karar bekliyor | [Rail 6](/frappesetup/rail-6-operasyon/), K-13 |
| Y-06 | AI yazma onayı | Kapatıldı: her yazma önizle + onayla; risk sınıfı manifest ve sunucuda (G-86) | [Rail 5](/frappesetup/rail-5-ai/) |
| Y-07 | "Veri Hetzner'de" ile AI aktarımı, maskeleme sırası | Kapatıldı: saklama, işleme, aktarım ayrı; ilk dış çağrıdan önce yerel maskeleme (G-90); aktarım mekanizması hukuk kararı | [Rail 5](/frappesetup/rail-5-ai/), G-116 |
| Y-08 | Lisans gerekçesi | Gerekçe düzeltildi (Frappe MIT, ERPNext GPL-3.0); seçim karar bekliyor; bu deponun onay kaydı karar bekliyor | K-1, K-32 |
| Y-09 | WBS yerine teknik ağaç | Kapatıldı: kod ağacı, çalışma/veri ağacı ve teslim WBS'si | [Raylar](/frappesetup/raylar/), [Yol haritası](/frappesetup/yol-haritasi/) |
| Y-10 | Hidrasyon düzeltmesinin testte kalması | Kapatıldı: ürün kök neden düzeltmesi + yinelemesiz regresyon testi; ara yayın commit'i `692a380` | Bu depo |
| Y-11 | axe ve görsel doğrulamanın kapsamı | axe kapısı tüm sayfalar, tüm etki düzeyleri ve best-practice; görsel regresyon durumu aşağıda | Bu sayfa, QA kanıtı |
| E-01 | Kalıcı kullanıcı kimliği | Kapatıldı: `(iss, sub)` eşlemesi (G-120) | [Rail 4](/frappesetup/rail-4-keycloak/) |
| E-02 | ReBAC kapsamı ve birleşim | Kapatıldı: birleşim kuralı (G-60), ilişki kataloğu P5 (G-122) | [Rail 2 geliştirme](/frappesetup/rail-2-gelistirme/) |
| E-03 | Tüm erişim yollarında yetki | Kapatıldı: veri yüzeyi kapsama matrisi (G-121), API allowlist (G-143) | [Rail 2 geliştirme](/frappesetup/rail-2-gelistirme/) |
| E-04 | Yetkiye bağlı meta önbelleği | Kapatıldı: şema ve izin katmanı ayrı (G-63) | [Rail 2 geliştirme](/frappesetup/rail-2-gelistirme/) |
| E-05 | Headless davranış uyumluluğu | Kapatıldı: uyumluluk matrisi ve güvenli ifade yorumlayıcı (G-123) | [Rail 3](/frappesetup/rail-3-frontend/) |
| E-06 | Özel alan adında kimlik akışı | Kapatıldı: G-124 | [Rail 4](/frappesetup/rail-4-keycloak/) |
| E-07 | AI kredisi atomik rezervasyonu | Kapatıldı: reserve → consume → release (SA-15) | [Rail 5](/frappesetup/rail-5-ai/) |
| E-08 | Onayın işlemle bağlanması | Kapatıldı: G-86 | [Rail 5](/frappesetup/rail-5-ai/) |
| E-09 | Destek rızasının sunucu kapsamı | Kapatıldı: dört kapsam, iptal bağlantıyı ve temsili keser (SA-42, SA-44) | [Rail 6](/frappesetup/rail-6-operasyon/) |
| E-10 | Ortak ekranın neyi paylaştığı | Kapatıldı: paylaşılan durum ve kaynakta maskeleme (SA-43) | [Rail 6](/frappesetup/rail-6-operasyon/) |
| E-11 | Ödeme ve aktivasyon telafisi | Kapatıldı: durum makinesi (G-125) | [Rail 1](/frappesetup/rail-1-press/) |
| E-12 | Özel API'nin sahibi | Kapatıldı: sahiplik kaydı, `press_tr.api.ops` (G-126) | [Rail 2 geliştirme](/frappesetup/rail-2-gelistirme/) |
| E-13 | Kurulu/abone/askıda app ayrımı | Kapatıldı: durum modeli (G-127) | [App çerçevesi](/frappesetup/app-cercevesi/) |
| E-14 | Sürüm iddialarının yeniden doğrulanması | Kapatıldı: kaynak defteri ve G-128 | Bu sayfa |
| E-15 | Doküman–site tutarlılığı | Kapatıldı: gereksinim tablosu, dağılım ve faz tablosu JSON'dan üretilir; tutarlılık testi | [Gereksinimler](/frappesetup/gereksinimler/) |
| Güvenlik, performans, sürdürülebilirlik önerileri | Düzeltilmiş konumlarıyla kısa kurallar | Kapatıldı | [Kalite kuralları](/frappesetup/kalite-kurallari/) |

## Bu sürümdeki istekler

| İstek | Sonuç |
| --- | --- |
| Rapor sorunları ve tutarlılık | Yukarıdaki tablo; 41 yeni gereksinim (G-119..G-154, SA-40..SA-44), mevcut kimlikler korundu |
| Performans, sürdürülebilirlik, güvenlik kuralları | [Kalite kuralları](/frappesetup/kalite-kurallari/), G-142..G-153 |
| Kapalı panelde bağlantı önizlemesi | [URL ve paylaşım](/frappesetup/paylasim-url/), G-130, G-131 |
| İnsan odaklı URL ve atıf parametreleri | [URL ve paylaşım](/frappesetup/paylasim-url/), G-132, G-133 |
| Ölçüm adapterları ve gözlemlenebilirlik | [Ölçüm ve gözlem](/frappesetup/olcum-gozlem/), G-134..G-136, G-154 |
| Yardım kulakçığı ve kendi kendine destek | [Yardım ve tur](/frappesetup/yardim-tur/), G-137, G-138 |
| Onboarding, tur ve keşif | [Yardım ve tur](/frappesetup/yardim-tur/), G-139..G-141 |
| Destek imleci ve kiracı adına işlem | [Rail 6](/frappesetup/rail-6-operasyon/), SA-42..SA-44 |
| Kısa kurallar, yığın ayrımı | SaaS: Ant Design 6 + `@ant-design/x` 2 (G-66); bu site Astro + Mantine olarak kaldı |

## Kaynak defteri

Her satır 2026-10-08'de doğrulandı. Hareketli dal tek başına kanıt sayılmaz; sürüm değişince satır yeniden doğrulanır (G-128).

| No | İddia | Kaynak | Sürüm / SHA | Doğrulama türü |
| --- | --- | --- | --- | --- |
| KD-01 | Frappe Framework MIT | [frappe LICENSE](https://github.com/frappe/frappe/blob/v16.51.0/LICENSE) | v16.51.0, `6b450a1` | Kaynak dosya |
| KD-02 | ERPNext ve HRMS GPL-3.0 | [erpnext](https://github.com/frappe/erpnext/blob/v16.50.0/license.txt), [hrms](https://github.com/frappe/hrms/blob/v16.50.0/license.txt) | v16.50.0 (`7474d9e`, `7c03769`) | Kaynak dosya |
| KD-03 | Press, Agent, CRM, Helpdesk AGPL-3.0 | [press](https://github.com/frappe/press/blob/v0.155.3/license.txt) | press v0.155.3 `8493bf8`; crm v1.86.0; helpdesk v1.30.1 | Kaynak dosya |
| KD-04 | ERPNext destek: v14 31 Ocak 2026'da bitti, v15 2027 sonu, v16 2029 sonu (planlı) | [Supported Versions](https://github.com/frappe/erpnext/wiki/Supported-Versions/304a17ecd1c1e7d12576dc8c1745dda0d0e57c1c) | wiki `304a17e` | Resmi wiki revizyonu |
| KD-05 | Press son sürüm ve Frappe aralığı beyanı (`>=15,<17`; v16 çalışması doğrulanmadı) | [pyproject](https://github.com/frappe/press/blob/a5abd7d50256a1af98bcec46d7f5bf3ede684669/pyproject.toml#L91-L92) | v0.155.3 (2026-10-08) | Kaynak dosya |
| KD-06 | `allow_cors` tam eşleşme; `"*"` origin'i kimlik bilgisiyle yansıtır | [app.py](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/app.py#L319-L353) | `6b450a1` | Kod okuma |
| KD-07 | Site `rate_limit` istek süresi toplamını site geneli ölçer | [rate\_limiter.py](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/rate_limiter.py#L48-L97) | `6b450a1` | Kod okuma |
| KD-08 | `get_all` izin uygulamaz | [Database API](https://docs.frappe.io/framework/user/en/api/database) | Güncel doküman | Resmi doküman |
| KD-09 | `override_whitelisted_methods` rastgele adı eşler | [handler.py](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/handler.py#L66-L87) | `6b450a1` | Kod okuma |
| KD-10 | Gunicorn `threads` yalnız gthread'i etkiler | [Gunicorn ayarları](https://gunicorn.org/reference/settings/) | 26.2.2 | Resmi doküman + kod |
| KD-11 | Keycloak son sürüm | [26.8.0](https://github.com/keycloak/keycloak/releases/tag/26.8.0) | 2026-10-01 | Sürüm notu |
| KD-12 | CVE-2026-90997 kapsamı (stateless + MySQL/MariaDB) | [GHSA-xpwp-2pcm-8xq3](https://github.com/keycloak/keycloak/security/advisories/GHSA-xpwp-2pcm-8xq3) | düzeltme 26.7.4 | Danışmanlık |
| KD-13 | CVE-2026-11800 kapsamı (JWT Authorization Grant) | [GHSA-j97h-3f8r-mrjr](https://github.com/keycloak/keycloak/security/advisories/GHSA-j97h-3f8r-mrjr) | düzeltme 26.6.4 | Danışmanlık |
| KD-14 | Ayrı `hostname-admin` Admin REST API'yi engellemez | [Hostname rehberi](https://www.keycloak.org/server/hostname) | 26.8.0 | Resmi doküman |
| KD-15 | Organizations 26.0'dan beri tam destekli; standart token exchange 26.2'den beri | [26.0.0](https://www.keycloak.org/2024/10/keycloak-2600-released), [token exchange](https://www.keycloak.org/securing-apps/token-exchange) | 26.0.0, 26.2.0 | Sürüm duyurusu, doküman |
| KD-16 | `@ant-design/x` 2.9.0 eş bağımlılığı `antd ^6.1.1` | [npm](https://www.npmjs.com/package/@ant-design/x) | 2.9.0 | Paket manifesti |
| KD-17 | Hocuspocus 4.7.0 MIT | [npm](https://www.npmjs.com/package/@hocuspocus/server) | 4.7.0 | Paket manifesti |
| KD-18 | React 19.3 hidrasyondan önce yazılan girdiyi yeniden oynatmaz | Bu deponun `node_modules/react-dom` 19.3.0 `initInput` ve regresyon testi | 19.3.0 | Kod okuma + deney |
| KD-19 | WhatsApp önizleme koşulları | [Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/link-previews/) | Güncel doküman | Resmi doküman |
| KD-20 | robots ve noindex erişim kontrolü değildir | [Google](https://developers.google.com/search/docs/crawling-indexing/robots/intro) | Güncel doküman | Resmi doküman |
| KD-21 | Consent Mode türleri ve geri alma | [Google](https://developers.google.com/tag-platform/security/guides/consent) | Güncel doküman | Resmi doküman |
| KD-22 | Çerezlerde açık rıza ölçütleri | [KVKK Çerez Rehberi](https://www.kvkk.gov.tr/SharedFolderServer/CMSFiles/fb193dbb-b159-4221-8a7b-3addc083d33f.pdf) | Temmuz 2025 | Resmi rehber |
| KD-23 | Metabase gömme türleri ve lisansı | [Metabase](https://www.metabase.com/docs/latest/embedding/introduction) | v0.64 | Resmi doküman |
| KD-24 | Frappe Pulse yalnız `pulse_api_key` ile açılır | [client.py](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/utils/telemetry/pulse/client.py#L10-L20) | `6b450a1` | Kod okuma |

## Bu sitenin QA kanıtı

Durumlar: pass, fail, not\_run. Emülasyon gerçek cihaz yerine geçmez; yerel geçiş CI geçişi sayılmaz.

| Kontrol | Kapsam | Durum |
| --- | --- | --- |
| Derleme | `npm run build` | pass (yerel); CI sonucu teslim notunda |
| Playwright kapısı | Chromium, Firefox, WebKit; iPhone 13 emülasyonu yalnız dokunma senaryolarında | Sonuç teslim notunda |
| axe | Tüm sayfalar × açık/koyu tema; WCAG 2.0/2.1/2.2 A ve AA + best-practice kuralları; her etki düzeyi başarısızlıktır | pass; otomatik kural kapsamıdır, tam AA uyumu iddiası değildir |
| Odak | Klavye odağında tek görünür outline yalnız odaklanan öğede (Switch'te görünmez girdinin izinde); kenarlık ve gölge ikinci çerçeve üretmez; fare tıklaması gösterge üretmez | pass (üç motor) |
| Tutarlılık | Gereksinim kimlikleri, G/SA/K atıfları, iç bağlantılar, faz kararları, eski adlar, README sayıları | pass (Chromium) |
| Yazı ölçeği | Kök yazı %125 (320 px) ve %200 (390 ve 1366 px): taşma yok, metin ≥ 1rem, başlık düğmeleri görünür | pass (üç motor) |
| Ağ bütçesi | Kabuğun ilk görünüm toplam JS'i ≤ 100 KB, gezgin adasının ek JS'i ≤ 30 KB, HTML/CSS/yazı tipi, koşullu mermaid | pass (Chromium) |
| Hidrasyon | Ada JS'i bekletilip bir kez yazılan metin korunur; düzeltme olmadan test başarısız | pass |
| Görsel regresyon | Linux referans görüntüleriyle karşılaştırma | Teslim notunda |
| Gerçek macOS/iOS Safari, Android | — | not\_run |
