---
title: "Yol haritası"
nav: "Yol haritası"
order: 13
---

Yol haritası yedi fazdan oluşur (P0–P5 ve P6 operasyon düzlemi); her faz bir yetenek kapısıdır ve sonraki fazın yayın kararı yalnızca çıkış ölçütleri kanıtlandığında verilir. Süreler göreli haftadır (tahmin; ekip kapasitesiyle doğrulanacak) ve fazlar bağımlılıkların izin verdiği yerde paralel yürür. `G-nn` ana gereksinim listesine, `SA-nn` Rail 6 gereksinimlerine, `X-nn` çapraz kalemlere işaret eder.

## Faz tablosu

| Faz | Hedef | Çıkış ölçütü | Anahtar G-id | Sahip |
| --- | --- | --- | --- | --- |
| **P0 Altyapı** (≈6 hafta) | Hetzner bare-metal'de Press v0.154.x kontrol düzlemi, n/f/m/registry/monitor/log sunucuları, Keycloak HA, offsite yedek, ağ sertleştirme, ilk Deploy Candidate | Press staging ve prod Active; Route 53 wildcard TLS alınmış; `erpnext-v16-tr-staging` imajı derlenip test sitesi Active; Hetzner bucket'taki yedek geri yüklenmiş; Keycloak realm ile Press'e giriş; izleme uyarıları Telegram/e-postada | G-1..G-6, G-36, G-49, G-50, G-54, G-55, G-76, G-110, G-112, G-113 | Hüseyin Cengiz (sunucular, Route 53/IAM, yedek, Keycloak); Asistan Hüseyin (GoDaddy NS delegasyonu, G-2) |
| **P1 Platform çekirdeği** (≈12 hafta) | press\_tr + platform\_core temeli, Keycloak SSO/SLO, TR temel çizgisi, Access Rule motoru, meta-driven CRUD + shell + metadata sidebar, token sistemi, operatör kimlik modeli | Test kiracısında Keycloak giriş/çıkış; sidebar Workspace Sidebar + installed apps + yetkiden türüyor; çekirdek doctype'larda CRUD meta'dan; kayıt kuralı, hiyerarşi ve alan yetkisi testleri yeşil; CSRF/CORS same-site doğrulanmış; Playwright 320/360/375/390 × Chromium/Firefox/WebKit yeşil; TR System Settings wizard sonrası korunuyor | G-7..G-18, G-37..G-45, G-47, G-52, G-53, G-56..G-58, G-60..G-71, G-73..G-75, G-77..G-81, G-93, G-94, G-97, G-98, G-111, G-114, SA-1..SA-3 | Platform ekibi; Hüseyin Cengiz (CI/CD, DR runbook, SMTP relay G-47, operatör secret'ları SA-1) |
| **P2 Ticari katman** (≈9 hafta) | TRY fiyat, iyzico, KDV, e-Arşiv/e-Fatura, sözleşme/KVKK onayları, dunning, özel alan adı, faturalama ekranları, EFT referans kodu, iade zinciri | Sandbox ve prod'da 3DS satın alma, saklı karttan aylık tahsilat, iade ve Havale/EFT Press Invoice durum makinesiyle E2E; operasyon sitesinde e-belge üretilip PDF panelde; askı/arşiv çizelgesi test edilip sözleşmede; KVKK aktarım bildirimi ve VERBİS onaylı; `transaction_amount` tüm ödeme yollarında dolu | G-19..G-26, G-34, G-46, G-96, G-101, G-115..G-117, SA-4..SA-14 | Platform ekibi; mali müşavir (G-20, G-22, SA-5, SA-13); ürün sahibi + hukuk (G-23, G-116, G-117); Hüseyin Cengiz (log saklama/ILM G-117, sızma testi ortamı G-115, faturalama zamanlayıcı izleme SA-12) |
| **P3 AI** (≈12 hafta) | Claude Agent SDK servisi, Press/press\_tr/kiracı MCP, kullanıcı kimliğiyle delegasyon, önizle+onayla, AI Action Log, @ant-design/x sağ panel, AI kredi ölçümü | En az üç tek-tık akışı prod'da; yıkıcı/ücretli aksiyonlar confirm'siz yalnızca önizleme döner; her araç çağrısı kullanıcının yetkisiyle yürütülüp AI Action Log'da; prompt injection ve yetki aşımı negatif testleri yeşil; Anthropic aktarımı KVKK envanterinde; tüketim Press Usage Record'da | G-27, G-28, G-59, G-82..G-91, SA-15, SA-39 | Platform ekibi; Hüseyin Cengiz (konteyner, PostgreSQL/Redis, TLS, IP allowlist; G-27, G-83) |
| **P4 İlk app CronHR** (≈12 hafta) | App çerçevesinin CronHR ile ilk uygulanması; Marketplace App, App Plan, Product Trial, aktivasyon UX, aktivasyon hook'u | Keycloak kayıt → 14 gün deneme → Etkinleştir → Agent Job → sidebar'da CronHR akışı E2E testte ve ilk ödeyen müşteride; TR bordro kabul senaryoları yeşil; subscription info ile özellik kapıları doğrulanmış | G-29..G-31, G-35, G-72, G-92, G-95, G-102..G-108, SA-16 | Platform ekibi; ürün sahibi (plan/fiyat); mali müşavir (bordro parametreleri) |
| **P6 Operasyon düzlemi** (≈12 hafta; P2'nin iyzico/EFT/kredi adımlarından sonra, P3/P4 ile paralel) | Operasyon sitesi (Release Group 'ops': erpnext@version-16, crm@main, helpdesk@main + telephony, platform core, e-belge köprüsü), `create-fc-invoice`/`delete-fc-team` alıcıları, `press_ops_bridge` ve `press.api.ops`, kredi/tahakkuk/avans muhasebe kuralı, iyzico hak ediş ve EFT mutabakatı, superadmin operatör modu ekranları, iki katmanlı operatör yetkisi + maker-checker + Operator Audit, izinli destek oturumu (Support Access → Support Session → login-as, Hocuspocus), Helpdesk entegrasyonu ve destek widget'ı, KVKK rıza sürümleme/saklama matrisi | Ödenen her Press faturası Sales Invoice + e-belge olarak operasyon sitesinde; gece mutabakat raporunda iyzico/EFT farkı 0; Müşteri 360'tan kredi tahsisi ve plan değişimi Operator Audit'te; destek oturumu rıza → takip → login-as zinciri E2E ve Support Access'siz impersonate reddediliyor; HD Ticket tenant widget'ından açılıp SLA'ya düşüyor | SA-17..SA-31, SA-33..SA-38 | Platform ekibi (backend) + Frontend ekibi; Hüseyin Cengiz (ops sitesi dağıtımı, Hocuspocus, SA-17/SA-29); Asistan Hüseyin (`ops.<marka>` DNS); Finans/Muhasebe (SA-18, SA-21, SA-33, SA-34); Hukuk + ürün sahibi (SA-20, SA-36) |
| **P5 CRM/Webshop** (≈12 hafta) | CRM ve Webshop aynı kontrol listesiyle; tek Release Group'ta çoklu uygulama; ileri Press yetenekleri; e-belgenin kiracıya genişlemesi; CRM huni senkronu | İki uygulama Marketplace App olarak etkinleştirilebiliyor ve yalnızca kurulanlar sidebar'da; ERPNext v17 hazırlığı Version Upgrade ile belgelenmiş; tr\_edocs kararı segment bazında | G-32, G-33, G-109, SA-32 | Platform ekibi; Hüseyin Cengiz (migration/upgrade runbook, G-33) |

## Zaman çizelgesi (göreli)

Eksen hafta cinsindendir; çubuklar bağımlılıkla zincirlenir, takvim tarihi yoktur.

<div data-embed="timeline"></div>

P2 ticari katman P1'in Keycloak adımı biter bitmez başlar; P3 AI ve P4 CronHR ilk dikey dilimden sonra paralel yürür; P6 operasyon düzlemi iyzico/EFT ve kredi modeli (P2) olmadan açılamaz; P5 ilk ödeyen müşteriden sonra gelir.

## İlk dikey dilim: İzin talebi (Leave Application)

P1 çıkışında bir HR modülü tüm katmanlardan uçtan uca geçer; dilim ince tutulur ve P3/P4'ün iskeletini oluşturur. Kapsam: staging kiracısında hrms `Leave Application` doctype'ı.

| Adım | Mekanizma | G-id |
| --- | --- | --- |
| 1. Giriş | Keycloak `panel-spa` PKCE → kiracı Social Login Key → önceden provizyonlu System User | G-44, G-57, G-77 |
| 2. Shell | `api.shell.get_bootstrap`; sidebar HR Workspace Sidebar + kurulu hrms'ten türer | G-63, G-94 |
| 3. Liste/form | `Leave Application` meta'dan TanStack Table + Form; Link alanları `search_link`; 320 px'te belge yan paneli Drawer | G-69..G-71 |
| 4. Yetki | Access Rule: Employee kendi kayıtlarını, yönetici `reports_to` ekibini görür; `leave_balance` alanı permlevel ile kısıtlı | G-60, G-61, G-104 |
| 5. AI aksiyonu | Sağ panelde "bu izni onayla": kiracı MCP aracı `cronhr.approve_leave(name, confirm)` destructive bayraklı; confirm=false bakiye etkisini önizler, confirm=true kullanıcı token'ıyla `apply_workflow` çalıştırır → Version + AI Action Log | G-59, G-64, G-84..G-86, G-88, G-105 |
| 6. Destek | Operatör Support Access ister; kiracı rıza bandından onaylar; operatör 'görüntüle' kademesinde aynı listeyi Hocuspocus awareness ile izler, maskeli alanları görmez | SA-27, SA-29, SA-36 |
| 7. Kabul | Playwright: 320/360/375/390/tablet/masaüstü × Chromium/Firefox/WebKit; Tab/Shift+Tab odak, Escape, yön değişimi; gerçek Safari ayrı raporlanır; pass/fail/not\_run kayıtlı | G-74, X-20 |

Dilimin AI adımı agent servisinin tek araçlı iskeletidir; haiku sınıflandırma ve diğer araçlar P3'te eklenir. Destek adımı P6'nın iskeletidir; Support Session doctype'ı ve Hocuspocus bu dilimde tek odayla kurulur.

## Bağımlılıklar ve kritik yol

- G-2 NS delegasyonu (Asistan Hüseyin) → wildcard TLS (Hüseyin Cengiz doğrular) → ilk test sitesi; P0'ın ilk haftasında başlar, çünkü DNS yayılımı ve sertifika alımı diğer her adımın önündedir.
- G-5 Agent `upload_offsite_backup` yaması ilk prod kiracıdan önce tamamlanır; G-55 binlog kurtarma tatbikatı P0 çıkışında koşar.
- G-12 Press'e Keycloak girişi → G-16 davet akışı → G-79 kayıt; G-81 identity-sync ikisinin ortak zeminidir.
- G-45 `www/<panel>.py` CSRF enjeksiyonu ve G-75 same-site yerleşimi, SPA'nın ilk kiracı isteğinden önce hazırdır.
- G-42 başsız setup wizard → G-41 TR temel çizgisi doğrulaması → G-31 Product Trial yükü.
- G-19 iyzico + G-20 Invoice override → G-29 ücretli App Plan → G-30 aktivasyon sözleşmesi → G-95 mağaza UX.
- G-28 Press OAuth Client ve G-59 JWT auth\_hooks → G-82 token exchange → G-85 yetki eşitliği; frappe\_mcp'nin v16 uyumu P3 başında teyit edilir (doğrulanacak).
- G-35 `get_subscription_info` → G-106 özellik kapıları → CronHR plan farklılaştırması.
- G-102..G-107 sözleşmeleri P4'te CronHR, P5'te CRM/Webshop ile aynı X-09 uyumluluk listesinden geçer.
- SA-6/SA-8/SA-15 (iyzico yükleme, EFT referans kodu, AI kredi ölçümü) → SA-19/SA-21 (Sales Invoice alıcısı, kredi muhasebe kuralı) → SA-33/SA-34 (hak ediş ve EFT mutabakatı); P6 bu zincir olmadan açılmaz.
- SA-1/SA-2 operatör kimliği (P1) → SA-25 iki katmanlı operatör yetkisi → SA-24 Müşteri 360; SA-27 Support Access zinciri → SA-28 impersonate → SA-29 Hocuspocus (Hüseyin Cengiz).
- X-02 ortam matrisi (Colima dev / staging / prod) ve X-03 dört dağıtım hattı (press\_tr, SPA, agent servisi, Press) P1 içinde Hüseyin Cengiz tarafından kurulur; her faz kapısında X-06 DR tatbikatı ve X-20 zincir E2E koşar.

Faz kapısı toplantısında ürün sahibi çıkış ölçütlerinin kanıtını (test raporu, ekran görüntüsü, ağ izi) görür ve sonraki fazın yayın kararını verir.
