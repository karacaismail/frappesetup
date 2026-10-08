---
title: "Açık kararlar, riskler ve bağımlılıklar"
nav: "Açık kararlar"
order: 18
---

Bu bölüm kapatılması gereken kararları, planı en çok etkileyen riskleri ve dış sürüm bağımlılıklarını tek yerde toplar. Kararlar üç türdür ve **Tür** sütununda yazılıdır: sabit kullanıcı kararları [Kararlar](/frappesetup/kararlar/) sayfasındadır (K1–K10); burada **ürün sahibi**, **mali müşavir/finans**, **hukuk** kararı isteyenler ile **teknik varsayımlar** (önerilen varsayılan; onaylanana kadar gereksinimler bu varsayımla yazılır, etkilenen kimlikler satırdadır) ayrılır. Her karar kapandığında ADR olarak depoya yazılır (X-19); altyapı kalemlerinin uygulayıcısı Hüseyin Cengiz, GoDaddy tarafı Asistan Hüseyin'dir. "Öneri" sütunundaki sayılar ölçülmüş kapasite veya kabul edilmiş taahhüt değildir.

## Açık kararlar

| # | Karar | Tür | Seçenekler | Öneri | Faz |
| --- | --- | --- | --- | --- | --- |
| K-1 | Platform uygulamalarının lisansı (G-118) | Ürün sahibi + hukuk | AGPL-3.0 / GPL-3.0 / MIT, uygulama bazında | Öneri yok: bağımlılık lisansları girdidir (Frappe Framework MIT, ERPNext/HRMS GPL-3.0, Press/Agent/CRM/Helpdesk AGPL-3.0); kod ilişkisi ve dağıtım biçimiyle hukuk değerlendirir, ürün sahibi onaylar | P0 |
| K-2 | DNS yetkisi (G-2) | Teknik varsayım | Apex bölgenin tamamı Route 53 / yalnız `app.<marka>.com.tr` alt bölgesi | Alt bölge: kiracılar `<kiracı>.app.<marka>.com.tr`; `panel.`, `press.`, `operator.`, `id.`, `ops.`, `agent.` GoDaddy'de kalır. Hüseyin Cengiz kayıt değerlerini hazırlar, Asistan Hüseyin GoDaddy'de NS kayıtlarını yazar, Hüseyin Cengiz wildcard sertifikayı doğrular | P0 |
| K-3 | Güvenlik ajanları ve nöbet (G-36, G-115, X-08) | Ürün sahibi | Wazuh/YARA/Malware Scan kapsamı; yedek nöbetçi | Wazuh + auditd P0'da; birincil nöbet Hüseyin Cengiz, yedek kişiyi ürün sahibi atar | P0 |
| K-4 | Yinelenen tahsilat modeli (G-19, G-20) | Ürün sahibi | Press Usage Record + iyzico saklı karttan tahsilat / iyzico Subscription ürünü | Press defteri + saklı kart: ay içi plan değişimi, kredi ve Havale/EFT tek defterde kalır | P1 |
| K-5 | App Release onay kapısı (G-14) | Ürün sahibi | `bypass_automated_audit` + otomatik Approved / App Release Approval Request | Staging'de otomatik, prod Release Group'ta Approval Request zorunlu | P1 |
| K-6 | Keycloak teması (G-80) | Teknik varsayım | Keycloakify / FTL | Keycloakify; tokenlar `@platform/design-tokens`'tan tek kaynak; tema Java kodu içermez (G-152) | P1 |
| K-7 | SMTP relay (G-47) | Ürün sahibi | Hetzner'de Postfix / AB bölgeli sağlayıcı | AB bölgeli sağlayıcı (teslimat itibarı), KVKK envanterine eklenir; kurulum Hüseyin Cengiz, DNS değerlerini Asistan Hüseyin uygular | P1 |
| K-8 | Ürün parametreleri | Ürün sahibi | `rounding_method` (G-41), `session_expiry` 8–24 saat (G-43), `track_views` (G-64), `apply_strict_user_permissions` (G-52) | Banker's Rounding, 12 saat, track\_views yalnızca hassas doctype'larda, strict açık | P1 |
| K-9 | GİB özel entegratörü ve e-belge kodu (G-22, G-65) | Mali müşavir + ürün sahibi | Hazır Frappe e-belge uygulaması / `tr_edocs` geliştirme; Sovos, Logo, Uyumsoft, eLogo | Entegratör mali müşavirle seçilir; UBL-TR katmanı tek kez yazılır, operasyon sitesi (`press_tr_finance`) ve kiracılar paylaşır | P2 |
| K-10 | Yurt dışı müşteri ve USD (G-10) | Ürün sahibi | iyzico USD/EUR / AB tüzel kişiliğiyle Stripe | P2'de yalnızca TRY; USD yolu P5 sonrasında ayrı ADR | P2 |
| K-11 | P5 kararları (G-33, G-109) | Ürün sahibi | Partner programı açılışı; Webshop vitrini Frappe web sayfası / ayrı SSR | P5 başında kanal talebi ve segment verisiyle; vitrinde satıcı tarayıcı SDK'sı yalnız ayrı oturumsuz origin seçeneğinde (G-134) | P5 |
| K-12 | Yinelenen iyzico tahsilatı (SA-7) | Ürün sahibi | API + Card Storage (kendi kart formu, PCI SAQ A-EP/D) / iyzico Abonelik ürünü | API + Card Storage: K-4 ile aynı defter mantığı; `X-IYZ-SIGNATURE-V3` aktivasyonu için iyzico desteğine P2 başında başvurulur | P2 |
| K-13 | Finans olay–belge zamanlaması (SA-41, G-22, SA-19, SA-21) | Mali müşavir + Finans | A: kredi yükleme = satış faturası; B: yükleme = alınan avans, tüketim = aylık gelir tahakkuku (JE). Fatura kesinleşmesinde (Unpaid/Paid) e-belge / yalnız ödenmiş fatura (Press yerel davranışı) | Öneri yok: vergi ve belge zamanlaması mali müşavir kararıdır; teknik tasarım iki seçeneği de destekler, seçilen seçenek SA-41 matrisine işlenir ve seçilmeyen yol kapatılır | P2 |
| K-14 | e-belge entegratörü (SA-35, G-22) | Mali müşavir + ürün sahibi | Turkish Delight çatalı v16'ya taşınır / ticari özel entegratör REST API'si `press_tr_finance` içinde sarmalanır | Ticari entegratör + ince sarmalayıcı; mali mühür ve GİB portal yetkisi mali müşavirde, teknik anahtar Hüseyin Cengiz'de (age/sops) | P2 |
| K-15 | Müşteriye sunulan resmi fatura belgesi | Mali müşavir | Press Invoice PDF'i / operasyon sitesinden geri çekilen e-Arşiv Sales Invoice PDF'i | e-Arşiv PDF'i (`fetch_invoice_pdf` override); upstream kalıp bunu destekler | P2 |
| K-16 | Operatör kimliği köprüsü (SA-1, SA-25) | Teknik varsayım | Yalnız OIDC Social Login / yalnız operatör başına API key + BFF | İkisi birlikte: Press'e OIDC girişi (Press Desk/MCP), BFF (`ops-bff`) yalnız özel ağdaki `operator.` origin'inde, operatör moduyla aynı origin'de, operatör başına kimlikle `press_tr.api.ops`; tarayıcı operasyon sitesine doğrudan istek atmaz | P1 |
| K-17 | Frappe CRM ve Helpdesk dalı (SA-17) | Teknik varsayım | `main` (v15/v16 uyumlu) / `develop` (v17, Python 3.14, whatsapp zorunlu) | `main` etiketleri; v17 geçişi ERPNext v17 kararıyla birlikte (G-33) | P6 |
| K-18 | Hocuspocus barındırma ve kayıt (SA-29) | Teknik varsayım | Press ile aynı düğüm / ayrı servis; imleç akışı saklanır / saklanmaz | Ayrı Node servisi + Redis; imleç/olay akışı saklanmaz, yalnız oturum olayları denetim kaydına | P6 |
| K-19 | Login-as ve temsil kapsamı (SA-27, SA-28, SA-44) | Ürün sahibi + hukuk | Administrator (`Site.login_as_admin`) / belirli kullanıcı (`user.impersonate`) / kapsamı daraltılmış destek kullanıcısı | Varsayılan Administrator değil: belirli kullanıcının rızasıyla temsil veya kapsamı daraltılmış destek kullanıcısı; Administrator yalnız ayrı yükseltme rızası ve daha kısa süreyle (SA-42) | P6 |
| K-20 | Tenant ticket yolu (SA-30) | Ürün sahibi | Agent servisi relay / doğrudan Keycloak SSO ile Helpdesk portalı | Relay ile başla; Helpdesk portalına SSO P6 sonunda | P6 |
| K-21 | Customer yaratmanın tek sahibi | Teknik varsayım | Press Team olayı / CRM Deal Won | Press Team olayı (`press_ops_bridge`, P2); Deal Won yalnız Team'i tetikler | P2 |
| K-22 | Banka entegrasyonu (SA-34) | Ürün sahibi + Finans | CSV/MT940 manuel içe aktarma / banka API-açık bankacılık / iyzico Korumalı Havale-EFT | CSV/MT940 ile başla (P2 asgari mutabakat); hacim eşiği aşılınca banka API ADR'si | P2 |
| K-23 | Saklama süreleri (SA-36) | Hukuk | VUK/TTK 10 yıl mali kayıt; destek oturumu ve temsil kayıtları 12 / 24 ay | Mali kayıt 10 yıl; Support Session ve temsil 24 ay, sonra anonimleştirme; hukuk onayı | P6 |
| K-24 | Press Desk'in operatör kullanımı (SA-39) | Ürün sahibi | Tüm infra eylemleri panelde / infra Press Desk + MCP'de kalır | Infra (bench restart, snapshot, sunucu) Press Desk + Press MCP'de; günlük müşteri operasyonu panelde | P6 |
| K-25 | Tarayıcı belirteç modeli (G-148; etkilenen G-59, G-77, G-82, G-85, G-129, SA-29, SA-40) | Teknik varsayım | A: tarayıcıda Keycloak erişim belirteci (public PKCE istemci) / B: BFF, HttpOnly oturum + site tarafından basılan kısa ömürlü aracı belirteci | B: tarayıcıda kalıcı belirteç yok. HttpOnly çerez belirteç çalınmasını azaltır, XSS'in kullanıcı adına işlem yapmasını tek başına önlemez (G-145) | P1 |
| K-26 | Güvenlik yaması hedef süreleri (G-142) | Ürün sahibi + Hüseyin Cengiz | Danışmanlık şiddetine göre hedef süre | Başlangıç önerisi: istismar edilen veya kritik ≤ 72 saat, yüksek ≤ 7 gün; kabul edilene kadar taahhüt değildir | P0 |
| K-27 | Pazarlama etiketleri rıza modeli (G-134, G-135) | Hukuk | Google Consent Mode temel (rıza öncesi etiket yüklenmez) / gelişmiş (rıza öncesi çerezsiz ping) | Temel; adapterlar platformda etkin kalır, aktarım rıza ve yapılandırmayla başlar | P2 |
| K-28 | Kampanya atıf verisinin saklanma dayanağı (G-133) | Hukuk | Kayıt/ödeme anında sunucuda / rızayla cihazda birinci taraf çerez | Sunucuda (Account Request/Team); cihazda saklama rızaya bağlı | P2 |
| K-29 | "Bağlantıya sahip herkes" paylaşımı (G-131) | Ürün sahibi + hukuk | Kapalı / kiracı politikasıyla açılabilir | Varsayılan kapalı; açılırsa tek kayıt, salt okuma, süreli ve iptal edilebilir | P4 |
| K-30 | Metabase kapsamı (G-136) | Ürün sahibi | Yalnız operatör BI (açık kaynak, imzalı gömme) / kiracıya gömülü BI (satır izolasyonu: ticari sürüm veya kiracı başına şema) | Yalnız operatör BI ile başla | P6 |
| K-33 | Destek kapsam süreleri (SA-42) | Ürün sahibi + hukuk | Görüntüle/takip Support Access süresi (3–168 saat); kontrol devri; temsil; Administrator yükseltmesi | Öneri: kontrol devri ≤ 30 dk, temsil ≤ 60 dk, Administrator yükseltmesi ≤ 15 dk; kabul edilene kadar taahhüt değildir | P6 |
| K-34 | Hassas müşteri izolasyon kademesi (G-147) | Ürün sahibi + Hüseyin Cengiz | Paylaşımlı bench / ayrı bench + ayrı DB kullanıcısı ve anahtar / ayrı sunucu-VM | Veri hassasiyeti ve sözleşmeyle seçilir; Release Group tek başına güvenlik sınırı değildir | P5 |
| K-35 | Tur erteleme süresi ve öneri sıklığı (G-139, G-140) | Ürün sahibi | Erteleme bir sonraki oturuma / N güne; oturum başına öneri sayısı | Kullanım ölçümüyle (G-149) belirlenir | P4 |

### Bu dokümantasyon deposuna ait kararlar

| # | Karar | Tür | Durum | Öneri |
| --- | --- | --- | --- | --- |
| K-31 | Kişi adlarının bu public sitede yayını (Hüseyin Cengiz, Asistan Hüseyin) | Ürün sahibi | Adlar görev sahipliği için yazılı; yayın tercihi kayıtlı değil | Ürün sahibi kaydeder; tercih rol adıysa adlar rol adlarıyla değiştirilir |
| K-32 | Bu deponun lisans onay kaydı (kod MIT, içerik CC BY 4.0) | Ürün sahibi | Lisans dosyaları değiştirilmedi; onayın kaydı depoda yok | Ürün sahibi onayı ADR olarak yazılır; onay yoksa lisans kararı yeniden açılır |
| K-36 | Docs sitesi kabuk JS bütçesinin kapsamı | Ürün sahibi | Kapandı (8 Ekim 2026): kapsam ilk görünümün toplam JS'idir, giriş parçalarıyla daraltılmaz. Önceki "85 KB" bildirimi yalnız giriş parçalarını sayıyordu; aynı derlemenin toplamı 125,2 KB idi | Kabuk hafifletildi: toplam 96,9 KB, giriş parçaları 77,9 KB (ayrı raporlanır; güncel ölçüm İzlenebilirlik QA tablosunda); ağ testi her CI koşusunda toplamı ≤ 100 KB ile denetler |

## Başlıca riskler ve azaltımlar

| Risk | Etki | Azaltım |
| --- | --- | --- |
| Press semantic-release güncellemesi `press_tr` override'larını kırar (G-1, G-7) | Aktivasyon ve fatura kapanışı durur | Her etiket staging Press'te `bench migrate` + aktivasyon E2E; prod bakım penceresinde; Hüseyin Cengiz |
| FC fixture'ları yerel plan ayarlarını ezer (G-8; doğrulandı) | Yanlış planlar panelde görünür | `press_tr.after_migrate` idempotent; migrate sonrası enabled plan sayısı testi |
| TRY planında `price_usd` boş kalırsa ücretli uygulama ücretsiz sayılır (G-10; doğrulandı) | Gelir kaybı | Her TRY planına USD karşılığı; CI'da `can_install_paid_apps` kapı testi |
| iyzico/EFT yollarında `transaction_amount` boş kalırsa fatura senkronu hiç tetiklenmez (SA-11; doğrulandı) | Operasyon sitesinde Sales Invoice ve e-belge üretilmez | `press_tr` tüm ödeme yollarında alanı Team para birimiyle doldurur; gece mutabakat raporu Paid-ama-senkronsuz faturayı sıfır olarak doğrular |
| Press Support Agent rolü Support Access'siz çapraz-kiracı liste okuyabilir (SA-2, SA-37; doğrulandı) | KVKK ihlali riski | Rol ayrıcalıklı sayılır, yalnız `ops-support` grubuna; her `get_list` çağrısı Operator Audit'e; SA-37 görüntüleme denetimi |
| Hocuspocus bağlantısı veya temsil oturumu iptalden sonra açık kalırsa | İzinsiz görüntüleme veya işlem | İptal ve süre dolumunda sunucu açık bağlantıları kapatır, yeniden kimlik doğrulamayı reddeder ve temsil oturumunu sonlandırır (SA-42); kabul: 2 sn içinde kesilme testi |
| Agent offsite yaması upstream'e alınmaz (G-5) | Hetzner'e yedek yüklenmez | Yama Agent Update ile sürümlenir; `alert_on_sites_with_missing_backups` açık |
| Press DB `encryption_key` kaybı (G-49) | Tüm Password alanları okunmaz | age ile şifreli yedek iki konumda; çeyreklik geri yükleme tatbikatı (G-114) |
| Frappe Version fixture'ında 'Version 15' default (X-04; doğrulandı) | Yeni Release Group yanlış sürümde açılır | `after_migrate` 'Version 16' default=1 |
| AI agent çağrıları kiracı `cpu_time_per_day` limitini tüketir (G-46, X-13) | Kiracı askıya alınır | Agent kiracı başına çağrı kotası; ağır işler `reports`/`long` kuyruğunda |
| Prompt injection ile yetki aşımı (G-85, G-89) | Veri sızıntısı | Araç çağrısı kullanıcı kimliğiyle; kırmızı takım eval seti CI kapısı |
| Anthropic aktarımı KVKK (G-90) | İdari yaptırım | Veri envanteri + standart sözleşme; PII maskeleme; takım düzeyinde AI kapatma |
| Tek SSO oturumunun ortak site oturumu sanılması, çapraz kiracı çerez/CSRF hatası (G-119) | Kiracılar arası erişim | Host'a bağlı oturum, CORS yok, negatif testler P1 kapısında |
| Aynı ekonomik olayın iki yoldan kaydı (SA-41) | Çift veya eksik vergi kaydı | Tek olay–belge matrisi, idempotensi anahtarları, gece mutabakatı |
| Yetki kararı veri yüzeylerinde farklı (rapor, dışa aktarım, `get_all`) (G-121) | Yetkisiz veri | Yüzey kapsama matrisi ve UI'sız negatif testler |
| Press host tek hata noktası (G-114) | Kontrol düzlemi kaybı | Binlog ile RPO ≤ 1 saat, RTO ≤ 8 saat runbook; yıllık DR tatbikatı |

## Dış bağımlılıklar

| Bağımlılık | Mevcut sürüm | İzlenen değişiklik | Kabul kapısı |
| --- | --- | --- | --- |
| frappe/press | v0.154.x hedef; son sürüm v0.155.3 (2026-10-08); `pyproject` frappe `>=15,<17` beyan eder, v16 çalışma uyumu doğrulanmadı | patches.txt, fixture'lar, auth.py, pyproject pinleri, frappe.io senkron kodu | Staging migrate + E2E (Hüseyin Cengiz) |
| frappe/agent | master | offsite endpoint PR; Agent Update | Staging sunucuda `auto_rollback` |
| frappe/frappe, erpnext | frappe v16.51.0, erpnext v16.50.0 (doğrulandı); destek: ERPNext v15 2027 sonu, v16 2029 sonu (planlı) | /api/v2, Social Login Key, Workspace Sidebar meta, `user.impersonate` | Çekirdek meta codegen diff CI |
| frappe/crm, frappe/helpdesk | `main` (frappe &gt;=15,&lt;17) | develop dalının v17/Python 3.14 geçişi, telephony/whatsapp bağımlılıkları | Operasyon sitesi staging Deploy Candidate |
| frappe/mcp | main, "experimental" | v16 uyumu (doğrulanacak) | P3 kurulum testi |
| ueberdosis/hocuspocus | v4.7.0 (MIT, doğrulandı) | extension-redis/webhook API'si, Yjs sürümü | Destek oturumu E2E |
| Keycloak | 26.x (26.8.0, 2026-10-01, doğrulandı) | Upgrading Guide'daki minor/patch kırıcı değişiklikleri, güvenlik danışmanlıkları (G-142), Account Console v3 | Realm regresyon + tema E2E |
| Ant Design / `@ant-design/x` | antd 6 + X 2 (X 2.9.0 eş bağımlılığı `antd ^6.1.1`, doğrulandı) | breaking changes, X bileşen API'si | Playwright görsel regresyon |
| TanStack Query/Router/Table/Form | güncel majör | Router API | Typecheck + E2E |
| Node / Python | 24.x / 3.14 (G-54) | Bench Dependency Version | İlk Deploy Candidate (Hüseyin Cengiz) |
| iyzico iyzipay-python | güncel | 3DS v2, webhook imzası (`X-IYZ-SIGNATURE-V3`), Card Storage, hak ediş SFTP | Sandbox regresyon |
| Hetzner Object Storage | fsn1/nbg1 | zaman aşımı raporları (doğrulanacak) | 5 GB yükleme + indirme testi |
| Anthropic modelleri | claude-sonnet-5-5 / opus-5-5 / haiku-4-5 (doğrulandı) | model kimliği, fiyat | `claude-api` referansı + golden set |
