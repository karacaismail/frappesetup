---
title: "SaaS admin shell olmazsa olmazları"
nav: "Admin shell"
order: 15
---

Bu kontrol listesi, satılan her uygulamanın (CronHR, CRM, Webshop) içine oturduğu ortak kabuğun asgari kapsamıdır. Her kalem backend kaynağını, uygulama yöntemini (native = Press/Frappe/Keycloak yerleşik; configure = yalnızca ayar/kayıt; develop = özel kod, yaşadığı uygulama parantezde) ve bağlı gereksinimi gösterir. Liste aynı zamanda X-09 "Admin Shell Uyumluluk Listesi"nin shell tarafıdır: bir uygulama Marketplace'te yayımlanmadan önce bu kalemlerin tamamı kabul testinden geçmiş olmalıdır.

## 1. Yerleşim, gezinme ve arama

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| AntD Layout: üst bar (takım/site değiştirici, arama, bildirim sayacı, AI düğmesi, hesap menüsü), sol sidebar (320 px'te Drawer), içerik, sağ AI paneli | `platform_core.api.shell.get_bootstrap` tek çağrı | develop (platform\_core, `@platform/shell`) | G-63, G-93 |
| Metadata sidebar: kurulu uygulama → üst öğe, çocuklar Workspace Sidebar kayıtları, rol/yetki filtresi, elle kodlanmış menü yok | `frappe.get_installed_apps`, Workspace Sidebar doctype, Marketplace App ikon/ad | native (veri) + develop (türetme) | G-94 |
| Global arama ve komut paleti (navigasyon + aksiyon + AI prompt) | `frappe.utils.global_search.search`, `frappe.desk.search.search_link` | native (API) + develop (UI) | G-93 |
| Takım/site değiştirici, çok siteli kullanıcı | `press.api.account.switch_team`, Team üyeliği | native | G-16, X-11 |
| Meta önbelleği: ETag/hash anahtarı, Site Update Success ve Customize Form kaydında geçersizleme | meta hash, realtime `meta_changed` olayı | develop (platform\_core) | G-63, X-12 |

| İnsan odaklı URL, derin bağlantı, Paylaş düğmesi ve oturumsuz güvenli önizleme | Rota kalıbı, DocShare, platform\_core www | develop | G-130, G-131, G-132, G-133 |
| Ölçüm adapterları ve rıza tercih merkezi | Adapter kaydı, Legal Document Acceptance | develop | G-134, G-135, G-154 |

## 2. Kimlik, oturum ve hesap

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| Keycloak SSO girişi; her site kendi OIDC dönüşüyle (kod sunucuda), tarayıcıya belirteç verilmez (K-25) | Social Login Key provider 'Keycloak' (Press v15, kiracı v16) | configure | G-12, G-44, G-77 |
| Tekli çıkış: RP-initiated + back-channel | `on_logout`, `keycloak_backchannel_logout`; press\_tr aynı mekanizma | develop (platform\_core, press\_tr) | G-58 |
| Host'a bağlı oturum çerezi, CSRF token enjeksiyonu; CORS yok (G-119) | `www/<panel>.py` csrf\_token; Release Group common\_site\_config (Hüseyin Cengiz) | develop + configure | G-13, G-45, G-75 |
| Profil (ad, avatar, dil, saat dilimi); parola/MFA/passkey/oturumlar Keycloak Account Console'a markalı yönlendirme (doğrulanacak: v3 tema desteği) | Frappe User, Keycloak Account Console | native | G-78, G-99 |
| "Hesabımı sil" → KVKK talebi | Personal Data Deletion Request, Team Deletion Request | native | G-52, G-116 |

## 3. Uygulama mağazası ve aktivasyon

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| TRY fiyatlı katalog ve uygulama detayı | `press.api.marketplace.get_apps_with_plans` + `press_tr.api` sarmalayıcı | develop (press\_tr) | G-10, G-95 |
| Etkinleştir → plan → ödeme yöntemi kontrolü → `install_app` → Agent Job realtime → sidebar yenileme; Site Active değilken kuyruk | `press.api.site.install_app`, `agent_job_update` | native | G-30, G-95 |
| Kaldırma (geri bildirimli) ve plan değişimi önizle+onayla | `press.api.client.run_doc_method(Site.uninstall_app)`, `change_app_plan`, `change_plan` | native | G-30 |
| Özellik kapıları UI + sunucu aynı kaynaktan | `get_subscription_info` → `platform_core.subscription.has_feature` | native + develop | G-35, G-106 |
| Kurulum sonrası tur, görev listesi ve demo veri seçeneği | Tur motoru (kullanıcı başına sürümlü ilerleme); Form Tour ve Module Onboarding içerik kaynağı (doğrulandı; tamamlanma bayrakları site düzeyinde olduğu için ilerleme kaynağı değil) | develop | G-95, G-139 |

## 4. Abonelik ve faturalama

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| Site/uygulama planı, kullanım (cpu/disk/db) | `press.api.site.get_plans`, `current_plan` | native | G-96 |
| Fatura listesi, yaklaşan fatura, GİB onaylı PDF indirme | Invoice, `get_upcoming_invoice`, `fetch_invoice_pdf` override | develop (press\_tr, press\_tr\_finance) | G-20, G-22, G-96 |
| Ödeme yöntemleri: iyzico saklı kart ekle/sil/varsayılan, 3DS | Iyzico Stored Card, Iyzico Payment Record | develop (press\_tr) | G-19 |
| Kredi bakiyesi/satın alma, Havale/EFT yönergesi (değer NEFT, etiket panelde) | Balance Transaction, Invoice.payment\_mode | native + develop | G-19 |
| Askıya alma durumu ve ödeme ile açma | SUSPENSION\_DAYS sabitleri, `unsuspend_sites_if_applicable` | configure | G-24 |
| Harcama limiti, bütçe uyarısı, tahmin | `check_budget_alerts`, `billing_forecast` | configure | G-25 |
| Sözleşme/aydınlatma/ticari ileti onay geçmişi | Team `consent_*` Custom Field'ları | develop (press\_tr) | G-23 |
| Özel alan adı: müşteri kendi DNS'inde CNAME, panel `check_dns` sonucunu gösterir | `add_domain`, `set_host_name`, certbot webroot | native | G-26 |
| Görünürlük Press Role `allow_billing` ile | Press Role | configure | G-16 |

## 5. Ayarlar, özelleştirme ve veri

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| System Settings güvenli alt kümesi (dil, saat dilimi, biçimler, oturum süresi), uygulama ayar doctype'ları meta-driven form | System Settings whitelisted sarmalayıcı | develop (platform\_core) | G-41, G-97 |
| Kiracı e-posta domaini/hesabı (relay: Hüseyin Cengiz; DNS kayıtları GoDaddy'de: Asistan Hüseyin) | Email Domain, Email Account | configure | G-47 |
| Tenant Branding (logo, birincil renk) token katmanında | Tenant Branding doctype → AntD ConfigProvider | develop (platform\_core, `@platform/design-tokens`) | G-67, G-97 |
| Alan ekleme/gizleme/yeniden adlandırma, Workspace düzenleme | Customize Form, Custom Field, Property Setter, Custom Workspace | native (API) + develop (UI) | G-40, G-97 |
| Veri içe/dışa aktarma, göç şablonları | Data Import, `reportview.export_query` | native | G-97, X-15 |
| KVKK kişisel veri indirme talebi | Personal Data Download Request | native | G-52 |

## 6. Kullanıcı, rol ve yetki

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| Takım üyeleri ve davet (Keycloak kullanıcı + Press Team + Frappe System User tek akışta) | `press_tr.api.team.invite`, identity-sync | develop (press\_tr, platform\_core) | G-16, G-79, G-81 |
| Press Role bayrakları ve kaynak kısıtı | Press Role, Press Role Permission | configure | G-16 |
| Role Profile atama ve rol matrisi (doctype × izin × permlevel) | `permission_manager` API'leri | native | G-62, G-98 |
| Access Rule editörü: kapsam, filtre oluşturucu, önizleme | Access Rule doctype, `permission_query_conditions`/`has_permission` | develop (platform\_core) | G-60, G-98 |
| Alan düzeyi yetki ve efektif meta | permlevel + Custom DocPerm; `api.meta.get_doctype` | native + develop | G-61 |
| "Neden göremiyorum" açıklaması ve Permission Log | `explain_permission` | develop (platform\_core) | G-62 |

## 7. AI sağ paneli

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| `@ant-design/x` Bubble/Sender/Conversations/Prompts/ThoughtChain/Actions, SSE akışı, 320 px'te Drawer | agent servisi (Claude Agent SDK) | develop (`@platform/ai-sidebar`, agent) | G-83, G-88 |
| Sayfa bağlamı ve uygulamanın tek tık Prompts manifesti | `AppModule` AI sözleşmesi, `ai_tools` hook | develop | G-88, G-105 |
| Yetki eşitliği: kullanıcının Keycloak token'ı ve Press bearer'ı | `auth_hooks` adaptörü, Press OAuth Client | develop + configure | G-59, G-82, G-85 |
| Önizle+onayla, yıkıcı/ücretli sınıflandırma | confirm bayrağı + önizleme hash'i | develop (agent, press\_tr MCP) | G-27, G-86 |
| AI Action Log, kullanım ve kota göstergesi, takım düzeyinde AI kapatma | AI Action Log doctype, App Plan features | develop | G-64, G-87, G-90, G-92 |

## 8. Bildirim, denetim ve destek

| Kalem | Backend kaynağı | Yöntem | G-id |
| --- | --- | --- | --- |
| Birleşik bildirim merkezi ve realtime sayaç | Notification Log + `press.api.notifications.*` | native | G-100 |
| Duyuru bandı (bakım penceresi) | Dashboard Banner, `get_user_banners` | native | G-100 |
| Denetim görüntüleyici: Activity Log, Version farkı, Permission Log, AI Action Log, Site Activity | ilgili doctype'lar, filtre + dışa aktarım | native + develop | G-64, G-101 |
| Support Access onayı ve süre verme | Support Access doctype, `expire_pending_requests` | native | G-18, G-101 |
| Yedek indirme ve "verimi al" | `press.api.site.backup`, `get_backup_links` | native | G-37 |
| Yardım kulakçığı ve kendi kendine destek modu; dokümantasyon, durum sayfası, destek talebi | X-08 destek süreci, Incident doctype, Helpdesk widget'ı (SA-30) | develop | G-101, X-08 |

## 9. Ortak zemin: meta-driven CRUD çekirdeği

Her bölüm yukarıdaki ekranları aynı katmandan üretir; bu katman olmadan shell tamamlanmış sayılmaz:

- `@platform/frappe-sdk`: /api/v2 CRUD, CSRF, hata eşlemesi, realtime, Press için ikinci base URL (G-68).
- Field type → AntD eşlemesi, `depends_on`/`fetch_from`/permlevel değerlendirmesi, per-doctype override registry, çekirdek doctype codegen (G-69).
- Liste: TanStack Table, sunucu taraflı filtre/sıralama, kayıtlı görünümler, toplu aksiyon, kanban/takvim (G-70).
- Form: Section/Column/Tab Break yerleşimi, docstatus ve Workflow aksiyonları, child table, belge yan paneli (G-71).
- Rapor/dashboard/yazdırma: `query_report.run`, Dashboard Chart, `download_pdf` (G-72).
- i18n: `trTR`, dayjs 'tr', System Settings biçimleri, Frappe çevirileri (G-73).

## 10. Rail 6 eklemeleri: destek, kredi, faturalama ve operatör modu

| Kalem | Backend kaynağı | Yöntem | Gereksinim |
| --- | --- | --- | --- |
| Uygulama içi destek widget'ı: site/ürün/sürüm/kullanıcı bağlamını toplar, agent servisi üzerinden HD Ticket açar, ticket durumunu listeler, aydınlatma metnini gösterir | Frappe Helpdesk `HD Ticket` (operasyon sitesi), agent servisi relay | develop (`@platform/shell`, agent servisi) | SA-30 |
| Destek rızası bandı: Pending Support Access talebini (operatör, reason, allowed\_for, kapsam) gösterir; Accept/Reject yalnız takım yöneticisine açık | Press `Support Access` (`press.api.access.status`, `run_doc_method`) | develop (`@platform/shell`) | SA-27 |
| Aktif destek oturumu göstergesi: operatör presence avatarları, 'görüntülüyor/takip ediyor' durumu, uzaktan kontrol teklifi için 'İzin ver / Reddet', her an 'Oturumu bitir' | platform\_core `Support Session`, Hocuspocus awareness | develop (`@platform/support-session`) | SA-27, SA-29 |
| Hocuspocus provider ve awareness katmanı: çoklu imleç, seçim ve route paylaşımı; yalnız aktif Support Session varken dinamik import | Hocuspocus (`onAuthenticate` site bileti, G-148); paylaşılan ekran durumu ve kaynakta maskeleme (SA-43) | develop (`@platform/support-session`) | SA-29 |
| AI kredi sayacı: bakiye, `spending_limit`/uyarı eşiği, düşük bakiyede ücretli araçların kilitli olduğu durum, iyzico ile 'Kredi yükle' | Press `Team.get_balance`, `Balance Transaction`, `press_tr.api.billing.buy_credits_iyzico` | native (veri) + develop (UI) | SA-6, SA-15 |
| Faturalama sayfası: geçmiş faturalar + e-Arşiv PDF'i, yaklaşan fatura, EFT talimatı (ödeme referans kodu PRS-… ve IBAN), iyzico Checkout Form, ödeme yöntemi değiştirme | `press.api.billing.past_invoices`, `invoice_pdf`, `upcoming_invoice`, `press_tr.api.billing.*` | native (API) + develop (UI) | SA-4, SA-8, G-96 |
| Sürümlü yasal belge onay kapısı: aydınlatma, açık rıza, çerez ve abonelik sözleşmesi sürümü değişince yeniden onay | platform\_core `Legal Document Acceptance` (belge, sürüm, hash, kullanıcı, zaman) | develop (platform\_core, `@platform/shell`) | SA-36, G-23 |
| Bildirim merkezi ek türleri: Security Alert (impersonation), Support Access durum değişimi, ödeme hatırlatma ve askıya alma uyarıları | Frappe Notification Log, Press Notification | configure + develop (UI) | SA-28, SA-13, G-100 |
| Operatör modu anahtarı: Keycloak `ops-*` rolü için aynı kabuk operatör navigasyonunu (Müşteri 360, Tahsilat ve kredi, Abonelik ve modüller, Destek, Tahsilat aşaması, KVKK denetim raporu, gece mutabakat farkları) açar; tenant verisi ile operatör verisi aynı ekranda karışmaz | `platform_core.api.ops.customer_360`, `press.api.client.*`, `press_tr.api.ops` (BFF) | develop (`@platform/shell`, BFF) | SA-24, SA-25 |
| Modül aktivasyon durumu: Marketplace App Subscription durumuna göre Workspace/modül görünürlüğü ve 'Modül satın al / plan değiştir' eylemi | Press `Marketplace App Subscription`, `press.api.marketplace.change_app_plan`, `get_subscription_info` | native (API) + develop (UI) | SA-16, G-30, G-95 |

## 11. Kabul ölçütleri

- Playwright matrisi: Chromium/Firefox/WebKit × 320, 360, 375, 390, tablet ve masaüstü; giriş, sidebar, liste, form, aktivasyon, ödeme, destek rızası yolculukları; gerçek Safari/iOS ayrı raporlanır (G-74, X-20).
- Tasarım tokenları, tek `:focus-visible` göstergesi, ≥1rem metin, markalı Select (G-67).
- Performans bütçesi: ilk yük JS ≤ 300 KB gzip, LCP ≤ 2,5 s 4G, Lighthouse CI'da (G-66, X-13); destek oturumu paketi yalnız aktif oturumda yüklenir.
- Uygulama modülleri yalnızca kurulu uygulamalar için dinamik import (G-66, G-103).
- Uygunluk betiği `docs/app-conformance.md` maddelerini CI'da denetler; Marketplace App yayımı bu listeye bağlıdır (X-09).
