---
title: "Yol haritası"
nav: "Yol haritası"
order: 17
---

Yol haritası sekiz fazdan oluşur (P0–P5, P6 operasyon düzlemi ve P7 {{PRODUCT_NAME}} ürünü); her faz bir yetenek kapısıdır ve sonraki fazın yayın kararı yalnızca çıkış ölçütleri kanıtlandığında verilir. Bir fazın önkoşulu her zaman kendisinden önce teslim edilir ve bağımlılık yalnız ileri yöndedir: P2'nin e-belge ve EFT kabulü P2 içindeki operasyon sitesi finans çekirdeğine, P0'ın kabulü yalnız P0 kalemlerine dayanır; P6 P2 tamamlanınca açılır. Tek ara kapı P1 içindedir. Keycloak girişi, davet, kayıt ve identity-sync (G-12, G-16, G-79, G-81) bitince P2 başlar. Fazlara süre, hafta ya da iş yükü tahmini yazılmaz. Sıra yalnız bağımlılıkla anlatılır. Fazlar bağımlılıkların izin verdiği yerde paralel yürür. `G-nn` ana gereksinim listesine, `SA-nn` Rail 6 gereksinimlerine, `X-nn` çapraz kalemlere işaret eder.

## Faz tablosu

Hedef, çıkış ve sahip `phases.json`, gereksinim kimlikleri `requirements.json` dosyasındaki faz alanından derleme anında üretilir.

<div data-embed="phase-table"></div>

## Faz sırası

Çizim fazların sırasını gösterir. Sütunlar bağımlılık düzeyidir. Oklar önkoşuldan bağımlı faza gider. Takvim tarihi ve süre yoktur.

<div data-embed="timeline"></div>

P2 ticari katman, P1'deki Keycloak adımı bitince başlar. P2 operasyon sitesinin finans çekirdeğini (SA-17, SA-19, SA-35, SA-41) içerir. P3 AI ve P4 HRMS TR ilk dikey dilimden (P1 çıkışı) sonra paralel yürür. P6 operasyon düzlemi P2 tamamlanınca açılır. P5, ilk ödeyen müşteri kapısından sonra gelir. P7 {{PRODUCT_NAME}} ürünü MVP sonrasıdır. P7, P1 ve P2 bitince açılır. P1 Keycloak girişini kurar. P2 ücretli kullanım için tahsilatı kurar (K-61). Bu kapı P2 ve P4 çıkışına bağlıdır.

## MVP kapsamı ve backend durumu

MVP, ürünün ilk kullanılabilir sürümüdür. Backend kodu MVP düzeyinde yazılıyor. Kod yalnız yerelde ve örnek veriyle denendi. Canlı sunucu henüz yoktur (E-10). Bu yüzden hiçbir faz canlıda çalışmıyor.

Backend proje kaydı 23 Kasım 2026 Pazartesi günü MVP kapsamını şöyle çizdi:

- P2 ödeme katmanı MVP'ye girmez (O-45). İlk kullanıcılar ürünü alpha ve beta ortamında dener. Bu ortamlarda ödeme alınmaz. iyzico ve e-fatura işi prod satışından önce biter.
- P4 kendi kendine deneme ve “Etkinleştir” akışı MVP'ye girmez (O-46). MVP'de kiracıyı operatör Press ile açar.
- Telefon paketi MVP'ye girmez (O-49). Telefonun sunucu tarafı MVP düzeyindedir.
- Üç yaşam döngüsü testi prod'dan önce zorunludur (O-50). alpha için bu testler zorunlu değildir.

Canlıya çıkışın önündeki engeller [Rail 6](/frappesetup/rail-6-operasyon/#canlıya-çıkışın-önündeki-engeller) sayfasındadır.

## İlk dikey dilim: İzin talebi (Leave Application)

P1 çıkışında bir HR ekranı tüm katmanlardan uçtan uca geçer. AI ve destek adımları **beta ortamında prototiptir**: kendi kabul satırları vardır ve P3/P6'daki tam teslimlerin yerine geçmez.

| Adım | Mekanizma | Gereksinim |
| --- | --- | --- |
| 1. Giriş | Keycloak yönlendirmesi (`site-<kiracı>` istemcisi, kod sunucuda değişir) → önceden provizyonlu kullanıcı (son kullanıcının türü “Website User” olur, backend O-3), `(iss, sub)` eşlemesi, host'a bağlı oturum | G-44, G-57, G-119, G-120 |
| 2. Shell | `api.shell.get_bootstrap`; sidebar HR Workspace Sidebar + kurulu hrms'ten türer | G-63, G-94 |
| 3. Liste/form | `Leave Application` meta'dan TanStack Table + Form; adres `/ik/izin-talebi/<kimlik>`; 320 px'te belge yan paneli Drawer | G-69..G-71, G-132 |
| 4. Yetki | Access Rule: Employee kendi kayıtlarını, yönetici `reports_to` ekibini görür; `leave_balance` permlevel ile kısıtlı; liste, belge, rapor ve dışa aktarım aynı sonucu verir | G-60, G-61, G-104, G-121 |
| 5. AI prototipi | "Bu izni onayla": tek araç `hrms_tr.approve_leave` site aracı belirteciyle; önizleme + sunucuda bağlanan onay; AI Action Log. Sınıflandırıcı, kredi ölçümü ve müşteriye açılış yok | G-129 (tam teslim P3: G-59, G-84..G-86) |
| 6. Destek prototipi | Support Access → Support Session (yalnız görüntüle) → tek oda; rota, imleç, filtre paylaşılır, alan değeri paylaşılmaz; Revoke bağlantıyı 2 sn içinde keser | SA-40 (tam teslim P6: SA-42..SA-44) |
| 7. Kabul | Playwright: 320/360/375/390/tablet/masaüstü × Chromium/Firefox/WebKit; Tab/Shift+Tab odak, Escape, yön değişimi; gerçek Safari ayrı raporlanır; pass/fail/not\_run kayıtlı | G-74, X-20 |

## Bağımlılıklar ve kritik yol

- G-2 DNS kayıtları (değeri DevOps sorumlusu hazırlar, alan adı sorumlusu GoDaddy'de uygular) → TLS sertifikası (DevOps sorumlusu doğrular) → ilk test sitesi `demo.app.alpha.{{BRAND_DOMAIN}}`. Bu zincir P0'ın ilk işidir. MVP'de Route 53 ve NS devri yoktur. Sertifika her ad için ayrı alınır.
- G-76 Keycloak HA ve G-144 sertleştirme P0'da; G-12 Press girişi, G-16 davet, G-79 kayıt ve G-81 identity-sync P1'dedir (P0 çıkışı Press girişini şart koşmaz).
- G-5 Agent `upload_offsite_backup` yaması ilk prod kiracıdan önce; G-55 binlog kurtarma tatbikatı P0 çıkışında koşar.
- G-119 host'a bağlı oturum, G-45 CSRF enjeksiyonu ve G-75 yerleşimi SPA'nın ilk kiracı isteğinden önce hazırdır; G-120 kalıcı kimlik eşlemesi ilk girişten önce.
- G-148 aracı belirteci + G-59 adaptörünün asgari hali (P1: G-129 ve SA-40 prototipleri; SA-40 için G-82'nin asgarisi: `press-service` audience kapsamı, `ops-bff` girişi ve token exchange daraltması) → tam G-59/G-82/G-85 (P3); `frappe/mcp` deposu arşivlendi. Kiracı MCP katmanını `platform_core.ai` kurar (backend karar notu 0002).
- G-42 başsız setup wizard → G-41 TR temel çizgisi → G-31 Product Trial yükü.
- G-19 iyzico + G-20 Invoice override + G-125 durum makinesi → G-29 ücretli App Plan → G-30 aktivasyon → G-95 mağaza UX.
- SA-17/SA-19/SA-35 operasyon sitesi finans çekirdeği + SA-41 matrisi (K-13, mali müşavir) → P2 çıkışındaki e-belge kabulü; SA-6/SA-8 → SA-21/SA-34 (P2) → SA-33 hak ediş mutabakatı (P6); SA-21 (P2) → SA-15 (P3): AI tüketim ölçümü P2'deki tahakkuk kuralını kullanır.
- G-35 `get_subscription_info` → G-106 özellik kapıları → G-127 uygulama durum modeli → HRMS TR plan farklılaştırması.
- G-102..G-107 ve G-141 sözleşmeleri P4'te HRMS TR, P5'te CRM/Webshop ile aynı X-09 uyumluluk listesinden geçer.
- SA-1/SA-2 operatör kimliği (P1) → SA-25 → SA-24 Müşteri 360; SA-40 destek prototipi (P1) → SA-27/SA-28 → SA-42..SA-44 kapsam modeli → SA-29 Hocuspocus (DevOps sorumlusu).
- X-02 ortam matrisi (Colima yalnız geliştirme içindir, canlıda alpha, beta, rc ve prod vardır) ve X-03 Jenkins dağıtım hattı P0 içinde, canlıya çıkıştan önce DevOps sorumlusu tarafından kurulur ([Rail 6](/frappesetup/rail-6-operasyon/#canlı-ortamlar-ve-dağıtım-hattı)). Ekip her fazda kurtarma tatbikatını ve uçtan uca zincir testini çalıştırır (X-06, X-20).

## Teslim WBS'si

İş paketleri faz tablosundaki gereksinimleri teslim birimlerine böler. Sıra yalnız önkoşul sütunuyla anlatılır.

| İş paketi | Faz | Çıktı | Önkoşul | Sahip | Repo / app | Kabul ve kanıt |
| --- | --- | --- | --- | --- | --- | --- |
| WP-01 | P0 | Hetzner sunucuları, Jenkins hattı, alpha, beta, rc ve prod ortamları, ilk Deploy Candidate | Ön koşul yok | DevOps sorumlusu | Press, Agent | Test sitesi Active olur. Press envanter kayıtlarını tutar. |
| WP-02 | P0 | GoDaddy DNS kayıtları ve ad başına TLS (MVP'de Route 53 yok) | WP-01 | DevOps sorumlusu (değer, doğrulama), alan adı sorumlusu (GoDaddy) | GoDaddy | Ekip `dig` çıktısını doğrular. Sertifika Active olur. |
| WP-03 | P0 | Keycloak HA ve sertleştirme | WP-01 | DevOps sorumlusu | Keycloak, nginx | Genel adresteki yönetim uçları 403 döner. Ekip Keycloak ayarlarını dışa aktarır. |
| WP-04 | P0 | Yedek, DR, kaynak defteri, danışmanlık karar kaydı | WP-01 | DevOps sorumlusu + Platform ekibi | Agent yaması, defter | Geri yükleme tatbikatı kaydı |
| WP-05 | P1 | platform\_core iskeleti, host'a bağlı oturum, `(iss, sub)` | WP-03 | Platform ekibi | platform\_core, press\_tr | G-119/G-120 negatif test raporu |
| WP-06 | P1 | Access Rule ve veri yüzeyi kapsama matrisi | WP-05 | Platform ekibi | platform\_core | G-121 testleri CI'da kırmızı/yeşil kanıtla |
| WP-07 | P1 | Meta API, bootstrap, iki katmanlı önbellek | WP-05 | Platform ekibi | platform\_core | İki kullanıcı ve izin değişimi testi |
| WP-08 | P1 | Panel kabuğu, URL sözleşmesi, yardım katmanı | WP-07 | Frontend ekibi | panel monorepo | Playwright matrisi raporu |
| WP-09 | P1 | AI ve destek prototipleri (beta) | WP-06, WP-08 | Platform + Frontend ekibi | agent, platform\_core, Hocuspocus | G-129 ve SA-40 kabul satırları |
| WP-10 | P2 | iyzico, ödeme–kurulum durum makinesi | WP-05 | Platform ekibi | press\_tr | G-125 senaryoları sandbox kaydı |
| WP-11 | P2 | Operasyon sitesi finans çekirdeği ve olay–belge matrisi | WP-01 | DevOps sorumlusu + Platform ekibi + Finans | press\_tr\_finance, ops sitesi | E-belge PDF olarak açılır. Ekip çift ve eksik kayıtları sınar (SA-41). |
| WP-12 | P2 | Ölçüm adapterları, rıza kapısı, atıf sözleşmesi | WP-08 | Frontend ekibi | panel monorepo | Rıza yokken satıcıya istek yok (ağ kanıtı) |
| WP-13 | P3 | Agent servisi, MCP, önizle+onayla, kredi rezervasyonu | WP-09 | Platform + AI ekibi | agent, platform\_core, press\_tr | G-86 negatif testleri, SA-15 eşzamanlılık testi |
| WP-14 | P4 | HRMS TR, uygulama durum modeli, paylaşım/önizleme, tur | WP-10, WP-08 | App ekibi + Frontend ekibi | hrms_tr, panel | E2E aktivasyon; oturumsuz önizlemede veri yok |
| WP-15 | P6 | Operatör modu, CRM/Helpdesk, destek kapsamları, BI | WP-11, WP-09 | Platform ekibi, Frontend ekibi ve DevOps sorumlusu | ops sitesi, panel, Hocuspocus, Metabase | İptal en çok 2 saniye sürer. Maskeli alan ağ kaydında görünmez. |
| WP-16 | P5 | CRM/Webshop, ilişki kataloğu, izolasyon kademeleri | WP-14 | Platform + App ekibi | crm, webshop | G-122 matrisi testleri |

Faz kapısı toplantısında ürün sahibi çıkış ölçütlerinin kanıtını (test raporu, ekran görüntüsü, ağ izi) görür ve sonraki fazın yayın kararını verir.
