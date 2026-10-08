---
title: "Güvenlik, performans ve sürdürülebilirlik kuralları"
nav: "Kalite kuralları"
order: 10
---

Her kural düzey (MUST: karar, mevzuat veya güvenlik sınırı; SHOULD: bağlamsal; MAY: isteğe bağlı), sahip, bağımlılık ve kabul ölçütü taşır. "Öneri" sayıları ölçülmüş kapasite veya taahhüt değildir; ilgili açık karar (K-xx) kapanana kadar başlangıç değeridir.

Bu kurallar tasarım sözleşmesidir; SaaS henüz kurulmadı, hiçbir kontrol uygulanmış veya test edilmiş sayılmaz.

## Öncelik sırası

Risk en çok geliştirilecek bağlantı katmanlarındadır: `platform_core`, `press_tr`, identity-sync, metadata motoru, agent yetki devri.

1. **Kimlik ve kiracı sınırı:** `(iss, sub)` eşlemesi, host'a bağlı oturum, kullanıcıya bağlı önbellek, her yüzeyde sunucu yetkisi (G-119, G-120, G-121, G-63).
2. **Ayrıcalıklı işlemler:** operatör (`press_tr.api.ops.*`), AI ve destek erişiminin süreli kapsamı; onay, iptal ve denetim sunucuda (SA-42, G-86, G-148).
3. **Ödeme ve kredi doğruluğu:** atomik kredi rezervasyonu, idempotensi ve telafi (G-125, SA-15, SA-41).
4. **İşletilebilirlik:** yama süreci, geri yükleme tatbikatı, gözlemlenebilirlik (G-142, G-114, G-149).
5. **Ölçülmüş kapasite:** gerçek yolculuklarla yük deneyi, sonra worker, veritabanı, önbellek ve paket ayarı (G-149, G-50).

## Güvenlik kuralları

| Kural | Kural metni | Düzey | Sahip | Bağımlılık | Kabul ölçütü |
| --- | --- | --- | --- | --- | --- |
| SEC-01 | Danışmanlıklar izlenir, aşağıdaki yöntemle değerlendirilir. Acil yama rutin takvimi beklemez; hedef süreler öneridir (kritik 72 saat, yüksek 7 gün; K-26). | MUST | Hüseyin Cengiz + Platform ekibi | G-142, K-26 | Her yüksek/kritik danışmanlık için kanıtlı karar kaydı var. |
| SEC-02 | Kullanılan uçların envanteri çıkarılır, gereken Desk uçları `platform_core` sarmalayıcısına alınır, sonra nginx `/api/method/*` için varsayılan ret uygular. Server Script, System Console ve `developer_mode` kapalıdır. | MUST | Platform ekibi + Hüseyin Cengiz (nginx) | G-143, G-40 | Gözlem modundan sonra liste dışı uç 403 döner, mevcut akışlar kırılmaz. |
| SEC-03 | Yönetim konsolu ve Admin REST API public host'ta reverse proxy'de engellenir; `hostname-admin` tek başına yetmez. Redirect URI tam adres, PKCE S256 zorunlu; implicit, parola grant ve anonim DCR kapalı; brute-force koruması ve passkey açık. | MUST | Hüseyin Cengiz + Platform ekibi | G-144, G-77, G-78 | Public host'tan `/admin/realms/*` 403; liste her yükseltmede yeniden koşar. |
| SEC-04 | Her site kendi host'una bağlı `sid` çerezini kullanır: panel `panel.<marka>.com.tr` Press'in kendi alan adıdır, kiracı SPA'sı yalnız kendi sitesine (`<kiracı>.app.<marka>.com.tr` veya özel alan adı) istek atar. Bu yüzden hiçbir Frappe sitesinde `allow_cors` gerekmez; gerekirse tam eşleşmeli liste, `"*"` asla (Frappe origin'i kimlik bilgisiyle yansıtır). | MUST | Platform ekibi + Hüseyin Cengiz (nginx) | G-119, G-45, G-124 | Başka origin'den kimlik bilgili istek CORS izni almaz; çerez başka host'a gitmez. |
| SEC-05 | Önerilen modelde (K-25) tarayıcı kalıcı belirteç tutmaz; agent ve Hocuspocus için site kısa ömürlü, tek siteye ve servise bağlı aracı belirteci basar. HttpOnly XSS'i durdurmaz: HTML sunucuda ve istemcide temizlenir, CSP nonce ve Trusted Types önce rapor, sonra zorunlu modda. | MUST (model K-25'e bağlı) | Platform ekibi + Frontend ekibi | G-148, G-145, K-25 | Tarayıcı depolamasında belirteç yok; XSS yük seti testleri geçer. |
| SEC-06 | Dış URL çeken her yol şema allowlist'i, DNS sonrası özel/yerel/meta veri adres reddi ve her yönlendirmede yeniden denetim uygular. PDF/HTML işleyici ayrı, kısıtlı konteynerdedir; egress allowlist'i yalnız ek savunmadır. | MUST | Platform ekibi + Hüseyin Cengiz | G-146, G-51 | Özel adres, yönlendirme zinciri ve DNS rebinding test yükleri reddedilir. |
| SEC-07 | Release Group ve bench güvenlik sınırı değildir. Kademe veri hassasiyeti ve sözleşmeyle seçilir: paylaşımlı bench; ayrı bench, DB kullanıcısı ve `encryption_key`; ayrı sunucu/VM, ağ ve sırlar. | SHOULD | Hüseyin Cengiz + Ürün sahibi | G-147, K-34 | Kademe 2-3'te başka sitenin dosyası ve veritabanı erişilemez. |
| SEC-08 | API, rapor, arama, dışa aktarım, PDF, dosya, arka plan işi, MCP aracı ve realtime aynı sunucu yetki kararını verir. Kullanıcı yüzeyli kodda `get_all` (izin uygulamaz) ve ham SQL yalnız gerekçeli lint istisnasıyla. | MUST | Platform ekibi | G-121, G-60, G-61 | Her yüzeyde UI'sız doğrudan API negatif testi CI'da koşar. |
| SEC-09 | Actions tam commit SHA'sına sabitlenir; kilit dosyası, OSV/`npm audit` ve sır taraması her PR'da, SBOM her sürümde. Sırlar depoda değil; Press Password alanı, Actions secrets ve age/sops kullanılır. | MUST (SBOM: SHOULD) | Hüseyin Cengiz | G-111, G-112 | Etikete sabitli Action ve depoda sır yok; kararsız yüksek açık derlemeyi durdurur. |
| SEC-10 | AI'ın UI çıktısı yalnız onaylı katalogdaki bileşenler için şemaya uyan deklaratif tanımdır; kod, stil ya da katalog dışı bileşen içeren tanım çizilmez. Açık üretken UI yalnız izole, geçici artifact sandbox'ındadır ve yetki ile onay sınırını kaldırmaz; Frappe REST/RPC modele ham açılmaz, araçlar tipli domain adaptöründen geçer. | MUST | Frontend ekibi + AI ekibi + Platform ekibi | G-84, G-85, G-86, G-145 | Katalog dışı, kod ya da stil içeren tanım reddedilir; sandbox oturum çerezine ve belirtece erişemez; araç çağrısı kullanıcının yetkisiyle sınanır. |

## Performans kuralları

| Kural | Kural metni | Düzey | Sahip | Bağımlılık | Kabul ölçütü |
| --- | --- | --- | --- | --- | --- |
| PERF-01 | Optimizasyon ölçülen darboğaza göre seçilir: RUM, `Server-Timing`, yavaş sorgu ve RQ bekleme süresi p75/p95 izlenir; k6 sayıları hipotezdir. Keycloak'ta ES256, havuz boyutu ve PgBouncer de yalnız ölçümden sonra seçilir. | MUST (Keycloak ayarı MAY) | Platform ekibi + Frontend ekibi + Hüseyin Cengiz | G-149, G-113 | Her performans değişikliği önce/sonra ölçümüyle birleşir. |
| PERF-02 | Rapor, dışa aktarım ve toplu işler RQ kuyruğuna alınır. Worker türü ve thread birlikte seçilir: `threads` yalnız gthread'i etkiler, eşzamanlılık worker sayısı değildir. | MUST | Hüseyin Cengiz + Platform ekibi | G-50, G-55 | Worker türü, sayısı ve thread ölçüm gerekçesiyle kayıtlı. |
| PERF-03 | Site `rate_limit`'i istek işleme süresinin site geneli toplamıdır; CPU veya kullanıcı kotası değildir. İzolasyon yerine geçmez; uç koruması istek sayan `@frappe.rate_limit` ile yapılır. | MUST | Platform ekibi + Hüseyin Cengiz | G-46, G-34 | Hiçbir belge `rate_limit`'i CPU kotası diye anlatmaz. |
| PERF-04 | Liste uçları açık alan listesi ve sunucu tarafı sayfalama kullanır; büyük alt tablolar sunucuda sayfalanır. İndeks sorgu planına göre seçilir (her Custom Field'a değil); Version ve Activity Log hız için kapatılmaz. | MUST | Platform ekibi + Frontend ekibi | G-150, G-64 | Yeni indeks PR'da önce/sonra planıyla gelir; `track_changes` açık kalır. |
| PERF-05 | Kullanıcıdan bağımsız şema katmanı site + meta hash ile önbelleklenir, IndexedDB'de tutulabilir. İzin katmanı yalnız bellekte, kullanıcı + izin sürümüyle tutulur; çıkışta, kullanıcı veya kiracı değişiminde silinir. | MUST | Frontend ekibi + Platform ekibi | G-63, G-61 | Çıkıştan sonra tarayıcı depolamasında izin verisi kalmaz. |
| PERF-06 | AI, destek ve analitik paketleri yalnız gerektiğinde dinamik import ile yüklenir. Tek frontend bütçesi G-66'dır (ilk yük JS ≤ 300 KB gzip, LCP ≤ 2,5 s 4G). | MUST | Frontend ekibi | G-66, G-134 | İlk yük ağ kaydında bu paketler yok; Lighthouse CI G-66'yı uygular. |

## Sürdürülebilirlik kuralları

| Kural | Kural metni | Düzey | Sahip | Bağımlılık | Kabul ölçütü |
| --- | --- | --- | --- | --- | --- |
| SUS-01 | Destek sonu etiket tarihinden değil resmi tablodan okunur: ERPNext v14 31 Ocak 2026'da bitti, v15 2027 sonu, v16 2029 sonu (planlı); Frappe'nin ayrı tablosu yok. Press Frappe v15'te olduğundan v15 sonu yol haritasında kalemdir. | MUST | Hüseyin Cengiz + Ürün sahibi | G-151, G-1 | Aylık raporda her bileşenin kaynaklı destek sonu tarihi var. |
| SUS-02 | Rutin yükseltme (Frappe/ERPNext ve Press aylık, Keycloak her minor, frontend gruplu) staging E2E ile yürür; acil yama bu takvimi beklemez. Keycloak minor sürümleri hata düzeltmek için kırıcı değişiklik getirebilir; Upgrading Guide her minor'da okunur. | MUST | Hüseyin Cengiz + Platform ekibi | G-151, G-142 | Staging E2E kanıtı olmadan prod yükseltmesi yok. |
| SUS-03 | Realm, client, rol ve akışlar Git'te sürümlenir; elle değişiklik haftalık sapma kontrolünde raporlanır. Özel SPI yazılmaz; tek istisna sözleşme testli identity-sync olay köprüsüdür (ya da yönetici olayı yoklaması). | MUST | Platform ekibi + Hüseyin Cengiz | G-152, G-81 | Sapma raporu sıfır; SPI sözleşme testi yükseltme kapısında. |
| SUS-04 | Geçici upstream yaması bağlantı, sahip ve kaldırma koşuluyla takip edilir; kalıcı uzantılar `press_tr` ve `platform_core` hook'larındadır. Kiracı özelleştirmesi yalnız izinli belge türlerinde, ön ekli ad ve adet sınırıyla açılır. | MUST (kiracı özelleştirmesi SHOULD) | Platform ekibi | G-7, G-126, G-153 | Takipsiz yama yok; izinsiz belge türünde özelleştirme reddedilir. |
| SUS-05 | `@ant-design/x` 2.9.0 `antd ^6.1.1` istediğinden antd 6 ve X 2 birlikte sabitlenir; Pro Components ve X Cards (A2UI) kurulu sürümü ve antd 6 uyumu doğrulanacak. GenUI adaptörleri (OpenUI, AG-UI ve diğerleri) Semantic UI modeli ve registry'nin arkasında değiştirilebilir kalır. Fasad major geçişini tek başına küçültmez; maliyeti tokenlar ve sözleşme testleri düşürür. | MUST | Frontend ekibi | G-66, G-67 | Peer uyarısı yok; major değişimi ADR ve görsel regresyonla yapılır. |
| SUS-06 | Frappe, AntD, Hocuspocus MIT; ERPNext, HRMS GPL-3.0; Press, Agent, CRM, Helpdesk AGPL-3.0; Keycloak Apache-2.0. Matris, kod ilişkisi ve dağıtım biçimiyle karar girdisidir, hukuki hüküm değildir. | MUST | Ürün sahibi + Hukuk | G-118, K-1 | Lisans kararı ürün sahibi onayı ve hukuk görüşüyle kayıtlı. |
| SUS-07 | Yükseltme, geri alma, geri yükleme ve anahtar rotasyonu runbook'tur (G-114 ile MUST). Her rayda bunları uygulayabilen en az iki kişi bulunur. | SHOULD | Hüseyin Cengiz + Ürün sahibi | G-114 | DR tatbikatını runbook yazarından farklı biri yürütür. |
| SUS-08 | AI model kimlikleri kodda değil yönlendirme yapılandırmasındadır. Her model veya prompt değişikliğinde Türkçe değerlendirme seti koşar. | SHOULD | AI ekibi | G-83, G-91 | Değerlendirme raporu olmadan model değişikliği birleşmez. |

## Önceki önerilerin düzeltmeleri

| Önceki iddia | Düzeltilmiş konum | Kural |
| --- | --- | --- |
| Genel CVE listesi projenin zaafıdır | Sürüm, özellik ve maruziyetle uygulanabilirlik kararı | SEC-01 |
| `frappe.desk.*` toptan kapatılsın; ayrı admin hostname yeter | Önce envanter; Admin REST API proxy'de engellenir | SEC-02, SEC-03 |
| "Bearer yalnız agent'ta"; HttpOnly yeter | Tek belirteç modeli (K-25) ve ayrı XSS katmanı | SEC-05 |
| Egress SSRF'yi keser; Release Group izolasyondur | Egress ek savunma; kademeli izolasyon | SEC-06, SEC-07 |
| Rate limit CPU kotası; eşzamanlılık = worker sayısı | Site geneli istek süresi; worker türü + thread | PERF-02, PERF-03 |
| ES256/havuz/PgBouncer ve 100 kullanıcı/site, 50 site/bench, 1,5 s AI genel geçer | Ölçümle seçilir; sayılar hipotezdir | PERF-01 |
| Her Custom Field'a indeks, istemcide alt tablo sayfalama, Version'ı kapatma, meta IndexedDB'de | Plana göre indeks, sunucuda sayfalama, denetim açık, izin katmanı bellekte | PERF-04, PERF-05 |
| "LTS yok"; aylık takvim yamaları kapsar | Resmi destek tablosu; acil yama takvimi beklemez | SUS-01, SUS-02 |
| "Özel SPI yok"; Organizations açık karar | Tek SPI istisnası; Organizations 26.0'dan beri tam destekli | SUS-03, G-77 |
| Fasad major'ı çözer; fork-sıfır mutlak; lisans matrisi hükümdür | antd 6 + X 2 sabit; takipli geçici yama; matris karar girdisidir | SUS-04, SUS-05, SUS-06 |

## CVE uygulanabilirlik yöntemi

Geçmişteki bir açık, planlanan sürümün etkilendiğini göstermez. Her danışmanlık beş adımda değerlendirilir, sonuç G-142 karar kaydına yazılır; örnek tablo kurulmamış sistemin planlanan yapılandırmasını (Keycloak 26.8.0, PostgreSQL, stateless kapalı, JWT Authorization Grant kullanılmıyor) değerlendirir.

1. **Sürüm:** dağıtılan (kurulumdan önce planlanan) tam sürüm ve imaj digest'i.
2. **Aralık:** danışmanlıktaki etkilenen ve düzeltilmiş sürümler.
3. **Önkoşul:** gereken özellik, akış, veritabanı veya ayar açık mı, varsayılanı ne.
4. **Maruziyet:** saldırgan önkoşulu (kimlik bilgisi, ağ konumu, ele geçirilmiş artefakt) karşılanabiliyor mu.
5. **Karar:** yükselt, özelliği kapat veya ayarla; hemen / planlı / uygulanamaz + kanıt.

| Danışmanlık | Etkilenen sürüm ve önkoşul | Planlanan yapılandırmada | Karar |
| --- | --- | --- | --- |
| CVE-2026-90997 (yüksek; replay korumasını aşma) | `>= 26.7.0, < 26.7.4`; stateless mod (26.7'de kapalı önizleme) + MySQL/MariaDB ve ele geçirilmiş tek kullanımlık artefakt gerekir; düzeltme 26.7.4 | 26.8.0 aralık dışında; PostgreSQL; stateless kapalı | Uygulanamaz; stateless kapalı kalır, MySQL/MariaDB ile açılmaz (G-144) |
| CVE-2026-11800 (yüksek; JWT algoritma karışıklığı) | `< 26.6.4`; JWT Authorization Grant akışı, geçerli istemci kimlik bilgisi gerekir; özellik 26.6.0'dan beri varsayılan açık; düzeltme 26.6.4 | 26.8.0 aralık dışında; akış kullanılmıyor | Uygulanamaz; kullanılmayan `jwt-authorization-grant` kapatılır (G-144) |

## Kaynaklar

- Keycloak: [hostname](https://www.keycloak.org/server/hostname) (SEC-03), [Upgrading Guide](https://www.keycloak.org/docs/latest/upgrading/) (SUS-02), [özellikler](https://www.keycloak.org/server/features) (CVE), [ölçekleme](https://www.keycloak.org/getting-started/getting-started-scaling-and-tuning) (PERF-01), [26.0.0](https://www.keycloak.org/2024/10/keycloak-2600-released) (G-77).
- Danışmanlıklar: [GHSA-xpwp-2pcm-8xq3](https://github.com/keycloak/keycloak/security/advisories/GHSA-xpwp-2pcm-8xq3) (CVE-2026-90997), [GHSA-j97h-3f8r-mrjr](https://github.com/keycloak/keycloak/security/advisories/GHSA-j97h-3f8r-mrjr) (CVE-2026-11800).
- Frappe: [app.py CORS](https://github.com/frappe/frappe/blob/v16.51.0/frappe/app.py#L319-L353) (SEC-04), [rate\_limiter.py](https://github.com/frappe/frappe/blob/v16.51.0/frappe/rate_limiter.py#L48-L97) (PERF-03), [Database API](https://docs.frappe.io/framework/user/en/api/database) (SEC-08), [ERPNext Supported Versions](https://github.com/frappe/erpnext/wiki/Supported-Versions) (SUS-01).
- Diğer: [Gunicorn](https://gunicorn.org/reference/settings/) (PERF-02), [@ant-design/x 2.9.0](https://registry.npmjs.org/@ant-design/x/2.9.0) (SUS-05), [GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use) (SEC-09), [OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) (SEC-06), [OWASP oturum](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) (SEC-05); lisanslar GitHub depo kayıtlarından (SUS-06). Doğrulama: 2026-10-08.
