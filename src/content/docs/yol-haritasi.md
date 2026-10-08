---
title: "Yol haritası"
nav: "Yol haritası"
order: 17
---

Yol haritası yedi fazdan oluşur (P0–P5 ve P6 operasyon düzlemi); her faz bir yetenek kapısıdır ve sonraki fazın yayın kararı yalnızca çıkış ölçütleri kanıtlandığında verilir. Bir fazın önkoşulu her zaman kendisinden önce teslim edilir ve bağımlılık yalnız ileri yöndedir: P2'nin e-belge ve EFT kabulü P2 içindeki operasyon sitesi finans çekirdeğine, P0'ın kabulü yalnız P0 kalemlerine dayanır; P6 P2 tamamlanınca açılır. Tek ara kapı P1 içindedir: Keycloak girişi, davet, kayıt ve identity-sync (G-12, G-16, G-79, G-81) 14. haftada biter ve P2 bu kapıdan başlar. Süreler göreli haftadır ve ekip kapasitesiyle doğrulanmamış tahmindir; fazlar bağımlılıkların izin verdiği yerde paralel yürür. `G-nn` ana gereksinim listesine, `SA-nn` Rail 6 gereksinimlerine, `X-nn` çapraz kalemlere işaret eder.

## Faz tablosu

Hedef, çıkış ve sahip `phases.json`, gereksinim kimlikleri `requirements.json` dosyasındaki faz alanından derleme anında üretilir.

<div data-embed="phase-table"></div>

## Zaman çizelgesi (göreli)

Eksen hafta cinsindendir; çubuklar bağımlılıkla zincirlenir, takvim tarihi yoktur.

<div data-embed="timeline"></div>

P2 ticari katman P1'in Keycloak ara kapısından (14. hafta) başlar ve operasyon sitesinin finans çekirdeğini (SA-17, SA-19, SA-35, SA-41) içerir; P3 AI ve P4 CronHR ilk dikey dilimden (P1 çıkışı) sonra paralel yürür; P6 operasyon düzlemi P2 tamamlanınca (26. hafta) açılır; P5 ilk ödeyen müşteriden sonra gelir.

## İlk dikey dilim: İzin talebi (Leave Application)

P1 çıkışında bir HR ekranı tüm katmanlardan uçtan uca geçer. AI ve destek adımları **staging prototipidir**: kendi kabul satırları vardır ve P3/P6'daki tam teslimlerin yerine geçmez.

| Adım | Mekanizma | Gereksinim |
| --- | --- | --- |
| 1. Giriş | Keycloak yönlendirmesi (`site-<kiracı>` istemcisi, kod sunucuda değişir) → önceden provizyonlu System User, `(iss, sub)` eşlemesi, host'a bağlı oturum | G-44, G-57, G-119, G-120 |
| 2. Shell | `api.shell.get_bootstrap`; sidebar HR Workspace Sidebar + kurulu hrms'ten türer | G-63, G-94 |
| 3. Liste/form | `Leave Application` meta'dan TanStack Table + Form; adres `/ik/izin-talebi/<kimlik>`; 320 px'te belge yan paneli Drawer | G-69..G-71, G-132 |
| 4. Yetki | Access Rule: Employee kendi kayıtlarını, yönetici `reports_to` ekibini görür; `leave_balance` permlevel ile kısıtlı; liste, belge, rapor ve dışa aktarım aynı sonucu verir | G-60, G-61, G-104, G-121 |
| 5. AI prototipi | "Bu izni onayla": tek araç `cronhr.approve_leave` site aracı belirteciyle; önizleme + sunucuda bağlanan onay; AI Action Log. Sınıflandırıcı, kredi ölçümü ve müşteriye açılış yok | G-129 (tam teslim P3: G-59, G-84..G-86) |
| 6. Destek prototipi | Support Access → Support Session (yalnız görüntüle) → tek oda; rota, imleç, filtre paylaşılır, alan değeri paylaşılmaz; Revoke bağlantıyı 2 sn içinde keser | SA-40 (tam teslim P6: SA-42..SA-44) |
| 7. Kabul | Playwright: 320/360/375/390/tablet/masaüstü × Chromium/Firefox/WebKit; Tab/Shift+Tab odak, Escape, yön değişimi; gerçek Safari ayrı raporlanır; pass/fail/not\_run kayıtlı | G-74, X-20 |

## Bağımlılıklar ve kritik yol

- G-2 NS delegasyonu (değeri Hüseyin Cengiz hazırlar, Asistan Hüseyin GoDaddy'de uygular) → wildcard TLS (Hüseyin Cengiz doğrular) → ilk test sitesi `<kiracı>.app.<marka>.com.tr`; P0'ın ilk haftasında başlar.
- G-76 Keycloak HA ve G-144 sertleştirme P0'da; G-12 Press girişi, G-16 davet, G-79 kayıt ve G-81 identity-sync P1'dedir (P0 çıkışı Press girişini şart koşmaz).
- G-5 Agent `upload_offsite_backup` yaması ilk prod kiracıdan önce; G-55 binlog kurtarma tatbikatı P0 çıkışında koşar.
- G-119 host'a bağlı oturum, G-45 CSRF enjeksiyonu ve G-75 yerleşimi SPA'nın ilk kiracı isteğinden önce hazırdır; G-120 kalıcı kimlik eşlemesi ilk girişten önce.
- G-148 aracı belirteci + G-59 adaptörünün asgari hali (P1: G-129 ve SA-40 prototipleri; SA-40 için G-82'nin asgarisi: `press-service` audience kapsamı, `ops-bff` girişi ve token exchange daraltması) → tam G-59/G-82/G-85 (P3); frappe\_mcp'nin v16 uyumu P3 başında teyit edilir (doğrulanacak).
- G-42 başsız setup wizard → G-41 TR temel çizgisi → G-31 Product Trial yükü.
- G-19 iyzico + G-20 Invoice override + G-125 durum makinesi → G-29 ücretli App Plan → G-30 aktivasyon → G-95 mağaza UX.
- SA-17/SA-19/SA-35 operasyon sitesi finans çekirdeği + SA-41 matrisi (K-13, mali müşavir) → P2 çıkışındaki e-belge kabulü; SA-6/SA-8 → SA-21/SA-34 (P2) → SA-33 hak ediş mutabakatı (P6); SA-21 (P2) → SA-15 (P3): AI tüketim ölçümü P2'deki tahakkuk kuralını kullanır.
- G-35 `get_subscription_info` → G-106 özellik kapıları → G-127 uygulama durum modeli → CronHR plan farklılaştırması.
- G-102..G-107 ve G-141 sözleşmeleri P4'te CronHR, P5'te CRM/Webshop ile aynı X-09 uyumluluk listesinden geçer.
- SA-1/SA-2 operatör kimliği (P1) → SA-25 → SA-24 Müşteri 360; SA-40 destek prototipi (P1) → SA-27/SA-28 → SA-42..SA-44 kapsam modeli → SA-29 Hocuspocus (Hüseyin Cengiz).
- X-02 ortam matrisi (Colima dev / staging / prod) ve X-03 dağıtım hatları P1 içinde Hüseyin Cengiz tarafından kurulur; her faz kapısında X-06 DR tatbikatı ve X-20 zincir E2E koşar.

## Teslim WBS'si

İş paketleri faz tablosundaki gereksinimleri teslim birimlerine böler; süreler tahmindir.

| İş paketi | Faz | Çıktı | Önkoşul | Sahip | Repo / app | Kabul ve kanıt |
| --- | --- | --- | --- | --- | --- | --- |
| WP-01 | P0 | Hetzner sunucuları, Press staging/prod, ilk Deploy Candidate | — | Hüseyin Cengiz | Press, Agent | Test sitesi Active; Press envanter kayıtları |
| WP-02 | P0 | `app.` alt bölge delegasyonu ve wildcard TLS | WP-01 | Hüseyin Cengiz (değer, doğrulama), Asistan Hüseyin (GoDaddy) | Route 53, GoDaddy | `dig NS` çıktısı; sertifika Active |
| WP-03 | P0 | Keycloak HA ve sertleştirme | WP-01 | Hüseyin Cengiz | Keycloak, nginx | Public host'tan yönetim uçları 403; realm export |
| WP-04 | P0 | Yedek, DR, kaynak defteri, danışmanlık karar kaydı | WP-01 | Hüseyin Cengiz + Platform ekibi | Agent yaması, defter | Geri yükleme tatbikatı kaydı |
| WP-05 | P1 | platform\_core iskeleti, host'a bağlı oturum, `(iss, sub)` | WP-03 | Platform ekibi | platform\_core, press\_tr | G-119/G-120 negatif test raporu |
| WP-06 | P1 | Access Rule ve veri yüzeyi kapsama matrisi | WP-05 | Platform ekibi | platform\_core | G-121 testleri CI'da kırmızı/yeşil kanıtla |
| WP-07 | P1 | Meta API, bootstrap, iki katmanlı önbellek | WP-05 | Platform ekibi | platform\_core | İki kullanıcı ve izin değişimi testi |
| WP-08 | P1 | Panel kabuğu, URL sözleşmesi, yardım katmanı | WP-07 | Frontend ekibi | panel monorepo | Playwright matrisi raporu |
| WP-09 | P1 | AI ve destek prototipleri (staging) | WP-06, WP-08 | Platform + Frontend ekibi | agent, platform\_core, Hocuspocus | G-129 ve SA-40 kabul satırları |
| WP-10 | P2 | iyzico, ödeme–kurulum durum makinesi | WP-05 | Platform ekibi | press\_tr | G-125 senaryoları sandbox kaydı |
| WP-11 | P2 | Operasyon sitesi finans çekirdeği ve olay–belge matrisi | WP-01 | Hüseyin Cengiz + Platform ekibi + Finans | press\_tr\_finance, ops sitesi | e-belge PDF; SA-41 çift/eksik kayıt testleri |
| WP-12 | P2 | Ölçüm adapterları, rıza kapısı, atıf sözleşmesi | WP-08 | Frontend ekibi | panel monorepo | Rıza yokken satıcıya istek yok (ağ kanıtı) |
| WP-13 | P3 | Agent servisi, MCP, önizle+onayla, kredi rezervasyonu | WP-09 | Platform + AI ekibi | agent, platform\_core, press\_tr | G-86 negatif testleri, SA-15 eşzamanlılık testi |
| WP-14 | P4 | CronHR, uygulama durum modeli, paylaşım/önizleme, tur | WP-10, WP-08 | App ekibi + Frontend ekibi | cronhr, panel | E2E aktivasyon; oturumsuz önizlemede veri yok |
| WP-15 | P6 | Operatör modu, CRM/Helpdesk, destek kapsamları, BI | WP-11, WP-09 | Platform + Frontend; Hüseyin Cengiz | ops sitesi, panel, Hocuspocus, Metabase | Revoke ≤ 2 sn; maskeli alan ağ kaydında yok |
| WP-16 | P5 | CRM/Webshop, ilişki kataloğu, izolasyon kademeleri | WP-14 | Platform + App ekibi | crm, webshop | G-122 matrisi testleri |

Faz kapısı toplantısında ürün sahibi çıkış ölçütlerinin kanıtını (test raporu, ekran görüntüsü, ağ izi) görür ve sonraki fazın yayın kararını verir.
