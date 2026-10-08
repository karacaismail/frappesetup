---
title: "Açık kararlar, riskler ve bağımlılıklar"
nav: "Açık kararlar"
order: 14
---

Bu bölüm ürün sahibinin kapatması gereken kararları, planı en çok etkileyen riskleri ve dış sürüm bağımlılıklarını tek yerde toplar. Her karar kapandığında ADR olarak depoya yazılır (X-19); altyapı kalemlerinin uygulayıcısı Hüseyin Cengiz, GoDaddy tarafı Asistan Hüseyin'dir.

## Ürün sahibinden beklenen kararlar

| # | Karar | Seçenekler | Öneri | Faz |
| --- | --- | --- | --- | --- |
| K-1 | Lisans (G-118) | AGPL-3.0 / MIT | AGPL-3.0: Frappe ve ERPNext ile aynı lisans ailesi | P0 |
| K-2 | Route 53 kapsamı (G-2) | Apex alan adının tamamı / yalnızca `app.<marka>.com.tr` alt bölgesi | Yalnızca alt bölge; apex ve MX kayıtları GoDaddy'de kalır. Asistan Hüseyin NS kayıtlarını yazar, Hüseyin Cengiz wildcard sertifikayı doğrular | P0 |
| K-3 | Güvenlik ajanları ve nöbet (G-36, G-115, X-08) | Wazuh/YARA/Malware Scan kapsamı; yedek nöbetçi | Wazuh + auditd P0'da; birincil nöbet Hüseyin Cengiz, yedek kişiyi ürün sahibi atar | P0 |
| K-4 | Yinelenen tahsilat modeli (G-19, G-20) | Press Usage Record + iyzico saklı karttan tahsilat / iyzico Subscription ürünü | Press defteri + saklı kart: ay içi plan değişimi, kredi ve Havale/EFT tek defterde kalır | P1 |
| K-5 | App Release onay kapısı (G-14) | `bypass_automated_audit` + otomatik Approved / App Release Approval Request | Staging'de otomatik, prod Release Group'ta Approval Request zorunlu | P1 |
| K-6 | Keycloak teması (G-80) | Keycloakify / FTL | Keycloakify; tokenlar `@platform/design-tokens`'tan tek kaynak | P1 |
| K-7 | SMTP relay (G-47) | Hetzner'de Postfix / AB bölgeli sağlayıcı | AB bölgeli sağlayıcı (teslimat itibarı), KVKK envanterine eklenir; kurulum Hüseyin Cengiz, DNS değerlerini Asistan Hüseyin uygular | P1 |
| K-8 | Ürün parametreleri | `rounding_method` (G-41), `session_expiry` 8–24 saat (G-43), `track_views` (G-64), `apply_strict_user_permissions` (G-52) | Banker's Rounding, 12 saat, track\_views yalnızca hassas doctype'larda, strict açık | P1 |
| K-9 | GİB özel entegratörü ve e-belge kodu (G-22, G-65) | Hazır Frappe e-belge uygulaması / `tr_edocs` geliştirme; Sovos, Logo, Uyumsoft, eLogo | Entegratör mali müşavirle seçilir; UBL-TR katmanı `tr_edocs`'ta tek kez yazılır, operasyon sitesi ve kiracılar paylaşır | P2 |
| K-10 | Yurt dışı müşteri ve USD (G-10) | iyzico USD/EUR / AB tüzel kişiliğiyle Stripe | P2'de yalnızca TRY; USD yolu P5 sonrasında ayrı ADR | P2 |
| K-11 | P5 kararları (G-33, G-109) | Partner programı açılışı; Webshop vitrini Frappe web sayfası / ayrı SSR | P5 başında kanal talebi ve segment verisiyle | P5 |
| K-12 | Yinelenen iyzico tahsilatı (SA-7) | API + Card Storage (kendi kart formu, PCI SAQ A-EP/D) / iyzico Abonelik ürünü | API + Card Storage: K-4 ile aynı defter mantığı; `X-IYZ-SIGNATURE-V3` aktivasyonu için iyzico desteğine P2 başında başvurulur | P2 |
| K-13 | Kredi muhasebesi (SA-21) | Prepaid Credits = alınan avans (Payment Entry) / satış faturası; KDV yüklemede / tüketimde | Avans + aylık tüketim tahakkuku (Journal Entry); kredi ile kapanan Subscription faturalarını da senkronlayan press\_tr yaması; KDV zamanlaması mali müşavir görüşüyle | P2 |
| K-14 | e-belge entegratörü (SA-35, G-22) | Turkish Delight çatalı v16'ya taşınır / ticari özel entegratör REST API'si `press_tr_finance` içinde sarmalanır | Ticari entegratör + ince sarmalayıcı; mali mühür ve GİB portal yetkisi mali müşavirde, teknik anahtar Hüseyin Cengiz'de (age/sops) | P2 |
| K-15 | Müşteriye sunulan resmi fatura belgesi | Press Invoice PDF'i / operasyon sitesinden geri çekilen e-Arşiv Sales Invoice PDF'i | e-Arşiv PDF'i (`fetch_invoice_pdf` override); upstream kalıp bunu destekler | P2 |
| K-16 | Operatör kimliği köprüsü (SA-1, SA-25) | Yalnız OIDC Social Login / yalnız operatör başına API key + BFF | İkisi birlikte: Press'e OIDC girişi (operatör Press Desk/MCP için), BFF ise operatör başına API key/secret ile `press.api.ops` | P1 |
| K-17 | Frappe CRM ve Helpdesk dalı (SA-17) | `main` (v15/v16 uyumlu) / `develop` (v17, Python 3.14, whatsapp zorunlu) | `main`; v17 geçişi ERPNext v17 kararıyla birlikte (G-33) | P6 |
| K-18 | Hocuspocus barındırma ve kayıt (SA-29) | Press ile aynı düğüm / ayrı servis; imleç akışı saklanır / saklanmaz | Ayrı Node servisi + Redis; imleç/olay akışı saklanmaz, yalnız oturum olayları (başlangıç, kapsam, bitiş) denetim kaydına | P6 |
| K-19 | Login-as kapsamı (SA-27, SA-28) | Yalnız Administrator (`Site.login_as_admin`) / belirli kullanıcı (`user.impersonate`) | Varsayılan Administrator; `user.impersonate` yalnız ayrı rıza kademesiyle ve her kiracı sitede giden Email Account hazırken | P6 |
| K-20 | Tenant ticket yolu (SA-30) | Agent servisi relay / doğrudan Keycloak SSO ile Helpdesk portalı | Relay ile başla; Helpdesk portalına SSO P6 sonunda | P6 |
| K-21 | Customer yaratmanın tek sahibi | Press Team olayı / CRM Deal Won | Press Team olayı (`press_ops_bridge`); Deal Won yalnız Team'i tetikler | P6 |
| K-22 | Banka entegrasyonu (SA-34) | CSV/MT940 manuel içe aktarma / banka API-açık bankacılık / iyzico Korumalı Havale-EFT | CSV/MT940 ile başla; hacim eşiği aşılınca banka API ADR'si | P6 |
| K-23 | Saklama süreleri (SA-36) | VUK/TTK 10 yıl mali kayıt; destek oturumu ve impersonation kayıtları 12 / 24 ay | Mali kayıt 10 yıl; Support Session ve impersonation 24 ay, sonra anonimleştirme; hukuk onayı | P6 |
| K-24 | Press Desk'in operatör kullanımı (SA-39) | Tüm infra eylemleri panelde / infra Press Desk + MCP'de kalır | Infra (bench restart, snapshot, sunucu) Press Desk + Press MCP'de; günlük müşteri operasyonu panelde | P6 |

## Başlıca riskler ve azaltımlar

| Risk | Etki | Azaltım |
| --- | --- | --- |
| Press semantic-release güncellemesi `press_tr` override'larını kırar (G-1, G-7) | Aktivasyon ve fatura kapanışı durur | Her etiket staging Press'te `bench migrate` + aktivasyon E2E; prod bakım penceresinde; Hüseyin Cengiz |
| FC fixture'ları yerel plan ayarlarını ezer (G-8; doğrulandı) | Yanlış planlar panelde görünür | `press_tr.after_migrate` idempotent; migrate sonrası enabled plan sayısı testi |
| TRY planında `price_usd` boş kalırsa ücretli uygulama ücretsiz sayılır (G-10; doğrulandı) | Gelir kaybı | Her TRY planına USD karşılığı; CI'da `can_install_paid_apps` kapı testi |
| iyzico/EFT yollarında `transaction_amount` boş kalırsa fatura senkronu hiç tetiklenmez (SA-11; doğrulandı) | Operasyon sitesinde Sales Invoice ve e-belge üretilmez | `press_tr` tüm ödeme yollarında alanı Team para birimiyle doldurur; gece mutabakat raporu Paid-ama-senkronsuz faturayı sıfır olarak doğrular |
| Press Support Agent rolü Support Access'siz çapraz-kiracı liste okuyabilir (SA-2, SA-37; doğrulandı) | KVKK ihlali riski | Rol ayrıcalıklı sayılır, yalnız `ops-support` grubuna; her `get_list` çağrısı Operator Audit'e; SA-37 görüntüleme denetimi |
| Hocuspocus odası Support Session kapandıktan sonra açık kalırsa | İzinsiz görüntüleme | `onAuthenticate` her bağlantıda Support Session durumunu doğrular; oturum bitişi odayı siler; `extension-webhook` olayları denetime düşer |
| Agent offsite yaması upstream'e alınmaz (G-5) | Hetzner'e yedek yüklenmez | Yama Agent Update ile sürümlenir; `alert_on_sites_with_missing_backups` açık |
| Press DB `encryption_key` kaybı (G-49) | Tüm Password alanları okunmaz | age ile şifreli yedek iki konumda; çeyreklik geri yükleme tatbikatı (G-114) |
| Frappe Version fixture'ında 'Version 15' default (X-04; doğrulandı) | Yeni Release Group yanlış sürümde açılır | `after_migrate` 'Version 16' default=1 |
| AI agent çağrıları kiracı `cpu_time_per_day` limitini tüketir (G-46, X-13) | Kiracı askıya alınır | Agent kiracı başına çağrı kotası; ağır işler `reports`/`long` kuyruğunda |
| Prompt injection ile yetki aşımı (G-85, G-89) | Veri sızıntısı | Araç çağrısı kullanıcı kimliğiyle; kırmızı takım eval seti CI kapısı |
| Anthropic aktarımı KVKK (G-90) | İdari yaptırım | Veri envanteri + standart sözleşme; PII maskeleme; takım düzeyinde AI kapatma |
| Press host tek hata noktası (G-114) | Kontrol düzlemi kaybı | Binlog ile RPO ≤ 1 saat, RTO ≤ 8 saat runbook; yıllık DR tatbikatı |

## Dış bağımlılıklar

| Bağımlılık | Mevcut sürüm | İzlenen değişiklik | Kabul kapısı |
| --- | --- | --- | --- |
| frappe/press | v0.154.x; v0.155.2 yayında (doğrulandı) | patches.txt, fixture'lar, auth.py, pyproject pinleri, frappe.io senkron kodu | Staging migrate + E2E (Hüseyin Cengiz) |
| frappe/agent | master | offsite endpoint PR; Agent Update | Staging sunucuda `auto_rollback` |
| frappe/frappe, erpnext | v16 / 16.50 | /api/v2, Social Login Key, Workspace Sidebar meta, `user.impersonate` | Çekirdek meta codegen diff CI |
| frappe/crm, frappe/helpdesk | `main` (frappe &gt;=15,&lt;17) | develop dalının v17/Python 3.14 geçişi, telephony/whatsapp bağımlılıkları | Operasyon sitesi staging Deploy Candidate |
| frappe/mcp | main, "experimental" | v16 uyumu (doğrulanacak) | P3 kurulum testi |
| ueberdosis/hocuspocus | v4.7.x (MIT) | extension-redis/webhook API'si, Yjs sürümü | Destek oturumu E2E |
| Keycloak | 26.x (26.8.0, doğrulandı) | Organizations, token exchange V2, Account Console v3 | Realm regresyon + tema E2E |
| Ant Design / `@ant-design/x` | v5; v6 tek geçiş ADR ile | breaking changes, X bileşen API'si | Playwright görsel regresyon |
| TanStack Query/Router/Table/Form | güncel majör | Router API | Typecheck + E2E |
| Node / Python | 24.x / 3.14 (G-54) | Bench Dependency Version | İlk Deploy Candidate (Hüseyin Cengiz) |
| iyzico iyzipay-python | güncel | 3DS v2, webhook imzası (`X-IYZ-SIGNATURE-V3`), Card Storage, hak ediş SFTP | Sandbox regresyon |
| Hetzner Object Storage | fsn1/nbg1 | zaman aşımı raporları (doğrulanacak) | 5 GB yükleme + indirme testi |
| Anthropic modelleri | claude-sonnet-5-5 / opus-5-5 / haiku-4-5 (doğrulandı) | model kimliği, fiyat | `claude-api` referansı + golden set |
