---
title: "Satılan her app için çerçeve şablonu"
nav: "App çerçevesi"
order: 16
---

Satılan her uygulama (CronHR, CRM, Webshop ve sonrakiler) aynı çerçeveden geçer: ortak admin shell'in içine oturur, aynı yetki/AI/abonelik sözleşmelerini uygular ve Press'e aynı zincirle kaydolur. Çerçeve bir manifesttir; uygulama ekibi her kalemi doldurur, CI ve X-09 uyumluluk betiği doğrular, Marketplace App yayımı bu listenin tamamlanmasına bağlıdır.

## App Frame manifesti (kontrol listesi)

| # | Katman | Zorunlu çıktı | Gereksinim |
| --- | --- | --- | --- |
| 1 | Backend iskelet | `bench new-app` şablonu; `pyproject.toml` + `[tool.bench.frappe-dependencies] frappe = ">=16.0.0 <17.0.0"`; `hooks.py` (idempotent `after_install`, `setup_wizard_complete`, `after_migrate`, `fixtures` ön ek filtresi, `user_data_fields`); Module Def; `locale/main.pot` + `tr.po`; `bench run-tests` + ruff; CHANGELOG | G-102, G-14, G-52 |
| 2 | Frontend modül | `@apps/<ad>` paketi `AppModule` arayüzüyle: TanStack Router rota ağacı, `overrides/<doctype>.tsx` registry, ikon/çeviri, dashboard widget'ları, yardım konuları, tur ve keşif kuralları (G-141), AI Prompts; yalnızca tasarım tokenları; dinamik import | G-103, G-66, G-67, G-69 |
| 3 | Yetki sözleşmesi | Ön ekli roller (`<App> Admin/Manager/Employee`), Role Profile ve Module Profile fixture'ları, hiyerarşi alanları, varsayılan Access Rule şablonları, hassas alan permlevel şablonu; yetki matrisi testi | G-104, G-60, G-61, G-62 |
| 4 | AI sözleşmesi | `ai_tools` hook'u: araç adı, TR/EN açıklama, şema, gereken rol, `destructive`/`billable` bayrağı, önizleme üretici, birim kredi maliyeti; tek tık akışları Prompts olarak; golden test + yetki negatif testi | G-105, G-84, G-86, SA-15 |
| 5 | Abonelik kapıları | `platform_core.subscription.has_feature(app, feature)` hem whitelisted metot/doc\_events'te hem UI feature flag'inde; deneme/düşürme/askı durumunda salt okunur mod | G-106, G-35 |
| 6 | Fixture ve sidebar | Workspace + Workspace Sidebar `standard=1, app=<uygulama>` modül dosyası; Role/Custom Field/Property Setter/Workflow/Email Template yalnızca ön ek filtreli `hooks.fixtures`; Notification kanalları Email + System Notification | G-107, G-94 |
| 7 | Press kaydı | App + App Source (branch, `versions` = Version 16, `required_apps`), staging/prod Release Group üyeliği, Marketplace App, en az bir enabled App Plan (ücretsiz plan `price_usd=0`), `run_after_install_script=1` | G-29, G-32, G-14 |
| 8 | Shell entegrasyonu | Aktivasyon sonrası sidebar yeniden türetilir; tur ve görev listesi (G-139) + demo veri seçeneği; `user_data_fields` ile KVKK indirme/silme talepleri | G-95, G-97, G-52 |
| 9 | Operasyon kaydı | Helpdesk ürün etiketi + SLA kademesi, `APP-<ad>` Item eşlemesi, Müşteri 360 özet sağlayıcısı, `support_mask_fields`, yaşam döngüsü sinyalleri (aşağıda) | SA-15, SA-19, SA-24, SA-31, SA-36, SA-38 |
| 10 | Kabul | Playwright 320→masaüstü, Chromium/Firefox/WebKit; E2E: trial → Etkinleştir → Agent Job Success → sidebar başlığı; Lighthouse bütçesi | G-74, G-111, G-30 |

## Press'e kayıt zinciri (tüm uygulamalar için ortak)

1. **App + App Source**: GitHub App entegrasyonuyla depo bağlanır; `branch` ve `versions` tablosunda `Version 16`; `required_apps` ile bağımlılık (örn. CronHR → hrms) bildirilir (doğrulandı: App Source alanları).
2. **Release Group**: `erpnext-v16-tr-staging` (auto deploy) ve `erpnext-v16-tr-prod` (Scheduled Deploy Settings) gruplarına eklenir; bench düzeyinde uygulama kümesi ortaktır, kiracı yalnızca `install_app` ile kurduğunu görür (G-32).
3. **Marketplace App**: `team` = yayıncı takımımız, `status` Published, `frappe_approved=1`, `subscription_type` (Free/Paid/Freemium), `sources` → App Source, `site_config` varsayılanları, `after_install_script` + `run_after_install_script=1`, `after_uninstall_script` karşılığı, `collect_feedback=1`; Türkiye yerelleştirmesi için `localisation_apps` satırı `country='Türkiye'` → `tr_localization` (G-65).
4. **Marketplace App Plan**: `enabled=1`, `interval` Monthly, `price_try` Custom Field + USD karşılığı (`price_usd` kapılar için &gt;0, ücretsiz planda 0), `available_on_versions` Version 16, `features` (AI kotası, e-posta kotası, modül bayrakları), `roles` görünürlük (G-9, G-10, G-92).
5. **Product Trial** (deneme sunan uygulamalar): `apps` listesi, `trial_days=14`, `trial_plan`, `redirect_to_after_login` panel URL'si; TR setup payload'ı press\_tr override'ından gelir (G-31).
6. **Aktivasyon hook'u**: platform\_core `subscription_update_hook` site\_config `sk_<app>`/subscription anahtarlarını okuyup Workspace görünürlüğünü açar/kapar (SA-16).
7. **E2E aktivasyon testi**: `press.api.site.install_app(site, app, plan)` → Agent Job realtime → `get_subscription_info` ile `sk_<app>` doğrulaması → sidebar yeniden çekilir (G-30, G-35).

## Uygulama uzmanlaşmaları

| Alan | CronHR (HRMS) | CRM | Webshop |
| --- | --- | --- | --- |
| Upstream bağımlılık | `frappe/hrms` version-16; ayrı `cronhr` app | `frappe/crm` main dalı (version-16 dalı yok; v16 uyumu Deploy Candidate'te doğrulanacak) | `frappe/webshop` + `frappe/payments` version-16 |
| Marketplace App | Paid/Freemium, Product Trial var | Freemium | Paid |
| Hiyerarşi ve kapsam | `Employee.reports_to`, `Department` ağacı; Access Rule şablonu: çalışan kendi kayıtları, yönetici ekibi, İK tümü | Deal/Lead sahibi, Territory, satış ekibi; şablon: temsilci kendi fırsatları, ekip lideri ekibi | Customer Group, Warehouse, Company; şablon: mağaza yöneticisi kendi şirketi |
| Hassas alan permlevel | Maaş bileşenleri, TCKN, IBAN, sağlık/disiplin kayıtları | Telefon, e-posta, görüşme notları (kişisel veri) | Müşteri adresi, sipariş ödeme bilgileri |
| AI tek tık akışları | İzin onayı + yöneticiye bildirim, bordro kontrol özeti, eksik SGK verisi tarama | Lead → Deal dönüştür ve görev aç, e-posta özetinden sonraki adım öner | Stok uyarısından sipariş önerisi, iade talebini Credit Note'a dönüştür (onaylı) |
| Uygulamaya özgü zorunluluk | TR bordro: SGK primleri, gelir vergisi dilimleri, damga vergisi, kıdem/ihbar, 4857 yıllık izin; mevzuat parametreleri yıllık fixture tablosu (mali müşavir teyidi); e-bildirge/APHB dışa aktarım hazırlığı | `Email Account` IMAP yalnızca CRM'de panelden tanımlanır (G-47); headless meta-driven + CRM override'ları | `payments` uygulamasına kiracının kendi hesabıyla iyzico sağlayıcısı (G-109); vitrin SSR kararı ürün sahibinde; kiracı e-Arşiv/e-Fatura ihtiyacı `tr_edocs` ile (P5) |
| Helpdesk / SLA | HD Team 'CronHR'; bordro döneminde (ayın 1–10'u) yükseltilmiş SLA | HD Team 'CRM' | HD Team 'Webshop'; ödeme hataları Billing ekibine |
| Gereksinim | G-108 | G-109 | G-109 |

Her sütundaki kalem manifestin 3–5. maddelerinin uygulamaya özgü doldurulmuş halidir; ortak çerçeve değişmez, yalnızca içerik farklılaşır.

## Rail 6 kayıtları: her app'in operasyon düzlemine bildirdikleri

- **Helpdesk kategorisi ve SLA kademesi:** app, HD Ticket için ürün etiketini (`cronhr`, `crm`, `webshop`), varsayılan `HD Team` atamasını ve plan kademesine göre SLA'yı bildirir (SA-31).
- **Kredi maliyeti tablosu:** app'in `ai_tools` manifestindeki her ücretli araç için birim kredi maliyeti ve kota etiketi; agent servisi bunu `AI Credit Plan` Usage Record'una yazar (SA-15).
- **Faturalama kalemi eşlemesi:** app'in Marketplace App Plan'ı operasyon sitesinde `APP-<ad>` Item'ına ve KDV şablonuna eşlenir; `create-fc-invoice` alıcısı bu eşlemeyle Sales Invoice satırı üretir (SA-19).
- **Müşteri 360 özeti:** app, operatör paneli için salt okur özet sağlayıcısını (`platform_core.api.ops.customer_360` eklentisi: kullanım, son etkinlik, açık onaylar) bildirir; özet aşağıdaki yaşam döngüsü sinyalleriyle aynı outbox yoluyla operasyon sitesine akar, Müşteri 360 kiracı sitesini çağırmaz (SA-24).
- **Destek oturumu kapsamı:** app, ekranlarında maskelenecek hassas alanları (TCKN, IBAN, maaş) `support_mask_fields` ile bildirir; awareness katmanı bu alanları operatöre göstermez (SA-27, SA-36).
- **Yaşam döngüsü sinyalleri:** app, churn/kullanım sinyallerini (`last_activity`, kurulu ama 30 gün kullanılmayan modül) outbox olayı olarak yayınlar; operasyon sitesi bunları CRM Deal/ticket akışına bağlar (SA-38).

## Yayın kabul ölçütü

- Manifestin on kalemi X-09 `docs/app-conformance.md` listesinde işaretli; otomatikleştirilebilen kalemler (pyproject sınırı, fixture filtresi, `AppModule` tip denetimi, `ai_tools` şema doğrulaması, permlevel şablonu varlığı, `support_mask_fields` varlığı) CI'da yeşil.
- Staging Release Group'ta Deploy Candidate Success, ardından test kiracısında `bench --site X install-app <app>` idempotent ikinci çalışma hatasız (G-102).
- Aktivasyon E2E'si 320 px ve masaüstünde geçer; Marketplace App Subscription Active, `site_config` içinde `sk_<app>`, sidebar'da uygulama başlığı ve Workspace çocukları görünür (G-29, G-94, SA-16).
- Yetki matrisi ve AI negatif testleri (yetkisiz doctype, kayıt kuralı dışı belge, permlevel alanı, confirm'siz yıkıcı aksiyon) reddedilir ve AI Action Log'a `denied` düşer (G-85, G-64).
- `user_data_fields` ile Personal Data Download/Deletion talebi uygulamanın tüm kişisel veri doctype'larını kapsar (G-52).
- Türkçe `tr.po` tam; panel metinleri i18n kataloğunda (G-73).
- İlk Paid Invoice operasyon sitesinde `APP-<ad>` satırıyla Sales Invoice olarak görünür (SA-19).

CronHR bu çerçevenin ilk uygulamasıdır (P4); CRM ve Webshop aynı manifestle P5'te yayına alınır, çerçevede değişiklik gerekirse önce manifest güncellenir, sonra üç uygulama birlikte yeniden doğrulanır.
