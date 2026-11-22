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
| Y-01 | P2'nin P6 çıktısına bağımlılığı | Kapatıldı: operasyon sitesi finans çekirdeği P2'ye alındı (SA-17, SA-18, SA-19, SA-21, SA-22, SA-23, SA-34, SA-35); P6 P2 tamamlanınca başlar; faz sırası tutarlılık testinde | [Yol haritası](/frappesetup/yol-haritasi/) |
| Y-02 | P1 dilimi ve P0 kabulünün sonraki faz kalemlerine bağımlılığı | Kapatıldı: AI ve destek adımları ayrı kabullü prototip (G-129, SA-40); P0 çıkışı yalnız P0 kalemlerine dayanır | [Yol haritası](/frappesetup/yol-haritasi/) |
| Y-03 | SSO ile site oturumunun karışması, origin | Kapatıldı: host'a bağlı oturum ve origin tablosu, CORS yok (G-119); tarayıcı belirteç modeli önerisi | [Rail 4](/frappesetup/rail-4-keycloak/); karar bekliyor K-25 |
| Y-04 | DNS delegasyonu ile kiracı adresi | Kapatıldı: kiracılar `<kiracı>.app.atonota.net` adresindedir (backend ad haritası). MVP'de NS devri yoktur, kayıtlar GoDaddy'dedir | [Raylar](/frappesetup/raylar/), K-2 |
| Y-05 | Fatura senkronu için birden fazla olay modeli | Matris kapatıldı (SA-41); vergi ve belge zamanlaması karar bekliyor | [Rail 6](/frappesetup/rail-6-operasyon/), K-13 |
| Y-06 | AI yazma onayı | Kapatıldı: her yazma önizle + onayla; risk sınıfı manifest ve sunucuda (G-86) | [Rail 5](/frappesetup/rail-5-ai/) |
| Y-07 | "Veri Hetzner'de" ile AI aktarımı, maskeleme sırası | Kapatıldı: saklama, işleme, aktarım ayrı; ilk dış çağrıdan önce yerel maskeleme (G-90); aktarım mekanizması hukuk kararı | [Rail 5](/frappesetup/rail-5-ai/), G-116 |
| Y-08 | Lisans gerekçesi | Gerekçe düzeltildi (Frappe MIT, ERPNext GPL-3.0); seçim karar bekliyor; bu deponun onay kaydı karar bekliyor | K-1, K-32 |
| Y-09 | WBS yerine teknik ağaç | Kapatıldı: kod ağacı, çalışma/veri ağacı ve teslim WBS'si | [Raylar](/frappesetup/raylar/), [Yol haritası](/frappesetup/yol-haritasi/) |
| Y-10 | Hidrasyon düzeltmesinin testte kalması | Kapatıldı: ürün kök neden düzeltmesi + yinelemesiz regresyon testi; ara yayın `692a380` main'de ([CI koşusu](https://github.com/karacaismail/frappesetup/actions/runs/37760273507): Ubuntu'da 230 passed, Pages dağıtımı başarılı) | Bu depo |
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

Dış depo kayıtları 8 Ekim 2026 tarihinde doğrulandı. Backend kaynakları 22 Kasım 2026 Pazar günü okundu. Hareketli dal tek başına kanıt sayılmaz. Ekip sürüm değişince satırı yeniden doğrular (G-128).

| No | İddia | Kaynak | Sürüm / SHA | Doğrulama türü |
| --- | --- | --- | --- | --- |
| KD-01 | Frappe Framework MIT | [frappe LICENSE](https://github.com/frappe/frappe/blob/v16.51.0/LICENSE) | v16.51.0, `6b450a1` | Kaynak dosya |
| KD-02 | ERPNext ve HRMS GPL-3.0 | [erpnext](https://github.com/frappe/erpnext/blob/v16.50.0/license.txt), [hrms](https://github.com/frappe/hrms/blob/v16.50.0/license.txt) | v16.50.0 (`7474d9e`, `7c03769`) | Kaynak dosya |
| KD-03 | Press, Agent, CRM, Helpdesk AGPL-3.0 | [press](https://github.com/frappe/press/blob/v0.155.3/license.txt) | press v0.155.3 `8493bf8`; crm v1.86.0; helpdesk v1.30.1 | Kaynak dosya |
| KD-04 | ERPNext destek: v14 31 Ocak 2026'da bitti, v15 2027 sonu, v16 2029 sonu (planlı) | [Supported Versions](https://github.com/frappe/erpnext/wiki/Supported-Versions/304a17ecd1c1e7d12576dc8c1745dda0d0e57c1c) | wiki `304a17e` | Resmi wiki revizyonu |
| KD-05 | Press sürüm aralığı ve Frappe 16 denemesi | [Press sürüm aralığı](https://github.com/frappe/press/blob/8493bf87b8a6c34e7e35e5b06fa7d3f27dd77594/pyproject.toml#L91-L92) ve `backend/PROJE-KAYDI.md` O-9 | Press v0.155.3 beyanı. Yerel deneme Press 0.154.1, kayıt `5c8d7fe`. | Yerel Press yamalarla açıldı. Sunucu kurma akışı açık iş. |
| KD-06 | `allow_cors` tam eşleşme; `"*"` origin'i kimlik bilgisiyle yansıtır | [app.py](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/app.py#L319-L353) | `6b450a1` | Kod okuma |
| KD-06A | Backend kararları ve bilinen sınırlar | `backend/PROJE-KAYDI.md` | `5c8d7fe` | Proje kaydı |
| KD-06B | Kimlik, MCP ve model geçidi sözleşmeleri | `backend/docs/sozlesmeler.md` | `5c8d7fe` | Tasarım sözleşmesi |
| KD-06C | Kiracı yapay zekâ katmanı ve model geçidi | `backend/docs/kararlar/0002-yapay-zeka-katmani.md` ve `backend/docs/kararlar/0004-model-gecidi.md` | `5c8d7fe` | Karar notları |
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
| KD-25 | Pending Support Access 7 gün sonra saatlik `expire_pending_requests` işiyle düşer | [hooks.py](https://github.com/frappe/press/blob/8493bf87b8a6c34e7e35e5b06fa7d3f27dd77594/press/hooks.py#L256-L264), [support\_access.py](https://github.com/frappe/press/blob/8493bf87b8a6c34e7e35e5b06fa7d3f27dd77594/press/press/doctype/support_access/support_access.py#L14) | v0.155.3, `8493bf8` | Kod okuma |
| KD-26 | `press.api.client` Support Access'i tanır; başka takımın belgesi yalnız `system_user` ile açılır | [client.py](https://github.com/frappe/press/blob/8493bf87b8a6c34e7e35e5b06fa7d3f27dd77594/press/api/client.py#L442-L447), [ownership.py](https://github.com/frappe/press/blob/8493bf87b8a6c34e7e35e5b06fa7d3f27dd77594/press/access/ownership.py#L80-L105) | v0.155.3, `8493bf8` | Kod okuma |
| KD-27 | Standart token exchange V2: istekte bulunan istemci confidential ve istemcide açık olmalı; subject token'ın `aud` değerinde olmalı, kendi belirtecini değiştiren istemci muaf; `audience` yalnız süzer, `scope` varsayılan olmayan kapsam ekler; değiştirilen erişim belirteci subject token iptalinde iptal olmaz | [token exchange](https://www.keycloak.org/securing-apps/token-exchange#_standard-token-exchange-details), [StandardTokenExchangeProvider.java](https://github.com/keycloak/keycloak/blob/4246609cf2024c85016d3fb1254c3d2533367c31/services/src/main/java/org/keycloak/protocol/oidc/tokenexchange/StandardTokenExchangeProvider.java#L213-L235) | 26.8.0, `4246609` | Resmi doküman + kod okuma |
| KD-28 | Audience mapper'lı varsayılan olmayan kapsam audience'ı yalnız `scope` ile istenince ekler; istemcinin kendisi `aud`'a kendiliğinden girmez | [Server Admin: hardcoded audience](https://www.keycloak.org/docs/26.8.0/server_admin/index.html#_audience_hardcoded) | 26.8.0 | Resmi doküman |
| KD-29 | Client credentials isteği `scope`'u doğrular ve varsayılan kapsamlara istenen varsayılan olmayan kapsamları ekler | [ClientCredentialsGrantType.java](https://github.com/keycloak/keycloak/blob/4246609cf2024c85016d3fb1254c3d2533367c31/services/src/main/java/org/keycloak/protocol/oidc/grants/ClientCredentialsGrantType.java#L105-L132), [TokenManager.java](https://github.com/keycloak/keycloak/blob/4246609cf2024c85016d3fb1254c3d2533367c31/services/src/main/java/org/keycloak/protocol/oidc/TokenManager.java#L610-L640) | 26.8.0, `4246609` | Kod okuma |
| KD-30 | Meta Pixel HTTP üst bilgileriyle sayfa konumu, belge ve referrer toplar; belgede geçersiz kılma yolu yok (`dl`/`rl` adları belgede geçmez) | [Meta Pixel](https://developers.facebook.com/docs/meta-pixel/) | Güncel doküman | Resmi doküman |
| KD-31 | Meta Pixel `eventID` ile Conversions API `event_id` ve olay adı eşleşirse 48 saat içinde tekilleştirilir | [Meta](https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events) | Güncel doküman | Resmi doküman |
| KD-32 | GA4 `page_location`, `page_referrer`, `page_title` varsayılanları `document.location`, `document.referrer`, `document.title`; `gtag('set')` ya da `config` ile verilir | [GA4 config](https://developers.google.com/analytics/devguides/collection/ga4/reference/config#page_referrer) | Doküman 2026-10-05 | Resmi doküman |
| KD-33 | GA4 aynı `transaction_id`'li satın almaları yalnız web akışında tekilleştirir; kimlik müşteriyi tanıtmaz | [GA4](https://support.google.com/analytics/answer/12313109) | Güncel doküman | Resmi doküman |
| KD-34 | GA4 Enhanced Measurement olayları `link_url`, `search_term`, `form_destination` taşır | [GA4](https://support.google.com/analytics/answer/9216061) | Güncel doküman | Resmi doküman |
| KD-35 | `Referrer-Policy: strict-origin` aynı origin dahil yalnız origin gönderir; varsayılan `strict-origin-when-cross-origin` aynı origin'de tam adres gönderir; `document.referrer` gezinme isteğinin referrer'ıdır | [Referrer Policy](https://w3c.github.io/webappsec-referrer-policy/#determine-requests-referrer), [HTML](https://html.spec.whatwg.org/multipage/document-lifecycle.html#initialise-the-document-object), [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy) | ED 2026-03-20; HTML LS 2026-10-07 | Spesifikasyon + doküman |
| KD-36 | Yandex Metrica `hit` adres, `referer` ve `title` alır; adres verilmezse `window.location.href` | [hit](https://yandex.com/support/metrica/en/objects/hit.html) | Güncel doküman | Resmi doküman |
| KD-37 | Belirteçteki roller istemcinin ve uygulanan kapsamların rol eşlemesiyle sınırlıdır; Audience Resolve belirteçte istemci rolü olan istemciyi `aud`'a ekler | [role scope](https://www.keycloak.org/docs/26.8.0/server_admin/index.html#_role_scope_mappings), [audience resolve](https://www.keycloak.org/docs/26.8.0/server_admin/index.html#_audience_resolve) | 26.8.0 | Resmi doküman |
| KD-38 | Kimlik kararları (KM-01..KM-31); kullanıcının notu | Keycloak + Headless Frappe Kimlik Rehberi ve Yol Haritası, 29 Eylül 2026 | Dosya, 5143 kelime | Kullanıcı notu |
| KD-39 | AI ekosistemi kararları (AI-01..AI-21); GitHub sayıları gecikmeli | Frappe AI Ekosistemi, 4 Ekim 2026 | Dosya, 5954 kelime | Kullanıcı notu |
| KD-40 | Kaizen şartnamesi (KZ-01..KZ-18); uygulanmış sistem değil | Capability-Agent_Kaizen_Kurulum_Sartnamesi, 12 Eylül 2026 | Dosya, 1722 kelime | Kullanıcı notu |
| KD-41 | Kaizen paketi; şablonlar, kurallar, kabul testleri; hiçbir dosya bu depoya eklenmedi | Capability-Agent_Kaizen_Kalite_Paketi | Zip, 3719 kelime | Kullanıcı notu |
| KD-42 | Adaptif arayüz kararları (AU-01..AU-30) | Capability-Adaptive Mobile-First UI Delivery and AI-Driven Cross-Device QA | Dosya, 8501 kelime | Kullanıcı notu |
| KD-43 | Adaptif arayüz, yetenek öncelikli teslimat | Capability-First Adaptive UI 320 CSS px iphone 4 first | Dosya, 3979 kelime | Kullanıcı notu |
| KD-44 | Adaptif arayüz, kapsam ve test matrisi, destek seviyeleri | Capability-First Adaptive UI 320 CSS px iphone 4 first-2 | Dosya, 4196 kelime | Kullanıcı notu |

## Bu sitenin QA kanıtı

Tablo `pass`, `fail` ve `not_run` durumlarını kullanır. Test satırları, denetlenen Git commit kodunu gösterir. Yerel test sonucu GitHub Actions sonucundan ayrıdır. iPhone 13 benzetimi gerçek cihazı kapsamaz.

| Kontrol | Kapsam | Durum |
| --- | --- | --- |
| Derleme | `npm run build` | pass (2ae6364, yerel Linux, Actions değil). 837f2e4 için Actions koşusu 37797285107. |
| Playwright kapısı | Testler 320 ile 1366 px arasındaki ekranları kapsar. iPhone 13 benzetimi yalnız `@touch` testlerini çalıştırır. | pass (6dcb4c5, yerel Linux, Actions değil). Yedi işçide 390 test geçti. 28 test atlandı. Önceki 2596d3e koşusunda 386 test geçti. Önceki 2ae6364 koşusunda 381 test geçti ve 28 test atlandı. Chromium, WebKit ve iPhone 13 benzetimi çalıştı. Bağımsız macOS koşusunda 381 test geçti ve 42 test atlandı. 3bcc006 koşusu Firefox dahil üç motoru kapsadı. 396 test geçti ve 44 test atlandı. c41294c ve e20d576 hedefli denetimlerdi. 837f2e4 kapanışında 262 test geçti ve 20 test atlandı. |
| axe | Tüm sayfalar × açık/koyu tema; WCAG 2.0/2.1/2.2 A ve AA + best-practice kuralları; her etki düzeyi başarısızlıktır | pass (yerel, üç motor; tüm sayfalar 3bcc006, değişen sayfalar c41294c ve 837f2e4); otomatik kural kapsamıdır, tam AA uyumu iddiası değildir |
| Odak | Klavye odağında belgede tek gerçek görünür outline, odaklanan öğede (görünmez Switch girdisinde izdeki görsel vekil); süzgeç bölümü klavyeyle açılır; kenarlık ve gölge ikinci çerçeve üretmez; fare tıklaması gösterge üretmez | pass (yerel, üç motor, 837f2e4) |
| Dokunma hedefi | Tek başına duran kontrollerin etkili alanı ince işaretçide ≥ 44, kaba işaretçide ≥ 48 CSS px (`--fs-hit`); metin içi bağlantılar istisna; 320 px başlıkta marka adı tam görünür, eylem düğmeleri görünür alanda | pass (yerel, üç motor): 44/48 px 3bcc006; 320 px başlık 837f2e4 |
| Satır kırılımı | Satıra sığan sözcük, başlık, kimlik ve model adı ortadan bölünmez. Test `overflow-wrap: anywhere` ve `word-break: break-all` kurallarını reddeder. Satırdan uzun düz metin yalnız satır sonunda kırılır. 320 px genişlikte tüm gereksinim kartları bu yedek kurala ihtiyaç duymadan sığar. | pass (2ae6364, yerel Linux, Actions değil). Temel denetim 837f2e4 kaydında da geçti. |
| Uzun satır içi kod | Boşluklu kod satırlara yayılabilir. Satıra sığmayan kesintisiz kod kendi kutusunda kayar. Yalnız taşan kutu Tab sırasına girer. Kutuyu ok tuşuyla kaydırabilirsiniz. Kodun tüm karakterleri korunur. Gezginin taşan kutusu tek satırda kayar. Kutu “Kaydırılabilir kod” adını alır. Test 320 px genişlikte en çok 194 kod durağına izin verir. Testte kök yazı %100 kalır. | pass (2ae6364, yerel Linux, Actions değil). Temel denetim 837f2e4 kaydında da geçti. |
| WCAG 2.2 | Standart WCAG 2.2 AA. axe-core 4.13.0'da 2.2'ye özgü otomatik kural yalnız `target-size` (wcag22aa); 2.4.11 odak örtülmemesi, 2.5.7, 3.2.6, 3.3.7 ve 3.3.8 elle denetlenir | otomatik kısım axe satırında; elle denetim not\_run |
| Yazı boyutları ve yazı tipi | Okunabilir metin en az 1rem olur. Site önce Outfit yazı tipini dener. | pass (Linux, Chromium ve WebKit, `5dbf79e`). Playwright alt sınırı ve ortak ölçüleri doğruladı. Chromium, Türkçe harfleri ve kullanılan yazı kalınlıklarını Outfit ile gösterdi. Yedek yazı tipleri, WCAG metin aralığı (1.4.12) ve gerçek cihazlar `not_run`. |
| Tema | İşletim sistemi koyu, kayıtlı tercih yokken düğme "Açık temaya geç" der ve tek tıklama açığa geçirir; kayıtlı tercih hidrasyondan önce uygulanır | pass (yerel, üç motor, 3bcc006) |
| Tutarlılık | Gereksinim kimlikleri, G/SA/K atıfları, iç bağlantılar ve derlenmiş HTML'deki çapalar, faz sırası ve zaman çizelgesi, paragrafa dönüşen tablo satırı, eski adlar (kaçışlı yazımlar dahil), README sayıları | pass (Chromium, 837f2e4) |
| Yazı ölçeği | Test kök yazı boyutunu ve 1rem alt sınırını denetler. Test görünür başlık düğmelerini ve yatay taşmayı da denetler. Temel kapsam %100 yazıyı içerir. Test %125 yazıyı 320 px genişlikte denetler. Kapsam %200 yazıda 390 ve 1366 px genişliği içerir. Bu denetim Mermaid hata çıktısını da denetler. Ana sayfa testi %150 yazıyı 320 px genişlikte denetler. Aynı test %200 yazıyı 320, 360 ve 412 px genişlikte denetler. | pass (2ae6364, yerel Linux, Actions değil). Temel kapsam 837f2e4 kaydında da geçti. |
| Ağ bütçesi | İlk açılışta kabuk en çok 100 KB JavaScript indirir. Gezgin en çok 30 KB ek JavaScript indirir. Gereksinimler sayfası en çok 180 KB HTML indirir. Ölçüm sıkıştırılmış dosya boyutuna bakar. Diyagramsız bölüm ek JavaScript indirmez. İstekler tamamlanır. | pass (2ae6364, yerel Linux, Actions değil). Kabuk 97,4 KB ve gezgin 17,4 KB. Gereksinimler HTML 199,0 KB. Yeni macOS derlemesi bu ölçümü 203.759 bayt olarak doğruladı. 837f2e4 ölçümünde ilk açılış yazı tipleri 88,0 KB tuttu. |
| Tek sunucu görünümü | Sunucu kartları gönderir. JavaScript kapalıyken masaüstünde de kartlar okunur. Masaüstü tablosunu tarayıcı hazırlar. Odak bir karttaysa tablo, odak kart listesinden çıkınca açılır. | pass (2596d3e, yerel Linux, Actions değil). Gereksinimler HTML 136,1 KB tuttu. Test sınırı 180 KB. Kabuk 97,4 KB ve gezgin 17,5 KB tuttu. |
| Kod kutusu adı ve görünümü | Taşan belge kod kutuları tek satırda kayar. Kutu adı “Kaydırılabilir kod” ile başlar ve kod metnini içerir. | pass (2596d3e, yerel Linux, Actions değil). Gerçek ekran okuyucu denemesi not\_run. |
| Gezgin geçişi ve performans | Tablo yalnız geniş ekranda ve boşta hazırlanır. Kart okunurken görünüm değişmez. Testte okunan kart en çok 1 CSS px yer değiştirebilir. Dar ekranda tablo çizilmez. | pass (6dcb4c5, yerel Linux, Actions değil). Gereksinimler HTML 136,3 KB, gezgin ek JavaScript 17,9 KB tuttu. |
| Klavye ve kod kutuları | Kutunun adı “Kaydırılabilir kod” olur. Kod metni kutuda kalır. 320 px genişlikte en çok 186 kod durağına izin verilir. Masaüstü tablosu kapanırsa içindeki odak arama alanına geçer. | pass (6dcb4c5, yerel Linux, Actions değil). Chromium 186 durak ölçtü. WebKit ve iPhone 13 benzetimi 167 durak ölçtü. |
| Hidrasyon | Ada JS'i bekletilip bir kez yazılan metin korunur (masaüstü ve 320 px dokunma); düzeltme olmadan test başarısız | pass (yerel, üç motor, 837f2e4) |
| Görsel regresyon | Ubuntu 24.04 ortamında üç tarayıcı için yedişer görüntü karşılaştırılır. | not\_run. GitHub Actions içindeki `deploy.yml` akışı görsel karşılaştırmayı çalıştıracak. Önceki referanslar 3bcc006 ve 837f2e4 için onaylandı. Kanıt Actions koşuları 37792505431 ve 37797285107 içindedir. |
| Gerçek macOS/iOS Safari, Android | — | not\_run |

## Onay bekleyen işler

| İş | Durum | Sonuç |
| --- | --- | --- |
| Yazı boyutları | Sürüyor. Görsel referans onayı bekliyor. | Gövde 1rem. Satır yüksekliği yazı boyutunun 1,5 katı. Sayfa başlığı 1,75 ile 2rem arasında. |
| Dar ekranda büyük yazı | Sürüyor. Görsel referans onayı bekliyor. | Ana sayfa düğmelerinin metni 320 ve 360 pikselde tam görünür. Kök yazı %200 iken sayfa yatay taşmaz. |

## Açık işler

| İş | Gerekçe | Kabul | Sahip |
| --- | --- | --- | --- |
| Gerçek cihaz doğrulaması | WebKit ve iPhone 13 emülasyondur | Gerçek macOS/iOS Safari ve Android'de odak, dokunma, kaydırma ve tema senaryoları `pass/fail` kaydıyla | Depo sahibi |
| 320 px genişlikte %300 yazı | İnceleme, ana sayfanın yatay taştığını gördü. Bu ölçek mevcut kabul aralığı dışında. | Ana sayfa taşmadan okunur. | Depo sahibi |
| Görsel referans kapsamı | Referanslar yedi görünüm içindir; mobil gezinme çekmecesi ve Teslim grubu gezinmesi görüntüde yok (davranış testleri var) | Gerekirse ek referans, bağımsız onayla | Depo sahibi |
| Action güncellemeleri | Action'lar commit SHA'sına sabittir; otomatik güncelleme işi kurulmadı (zamanlanmış iş kurma kararı kullanıcıdadır) | Güncellemede etiket → SHA eşleşmesi doğrulanır, CI geçer | DevOps sorumlusu |
