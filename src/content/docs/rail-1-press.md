---
title: "Rail 1 — Press ile SaaS abonelik, plan, marketplace ve ödeme planı"
nav: "Rail 1 · Press"
order: 3
---

Press ticari katmanı yönetir. Frappe 16 denemesindeki Press sürümü KD-05 kaydındadır. Press site planlarını, mağaza uygulamalarını, takım kademelerini ve hazır deneme sitelerini yönetir. Abonelik, kullanım kaydı ve fatura aynı akışa bağlıdır. Dağıtım, App Source kaydından Site Update adımına kadar Press üzerinden yürür.

`press_tr` ödeme, TRY, e-belge ve Türkçe e-posta işlerini Press’e uyarlar (G-7). İzin listesi ve Keycloak giriş sarmalayıcıları da bu uygulamadadır. Uygulama kancalar, kayıt örnekleri, sınıf geçersiz kılma ve özel alanları kullanır. Ekip, Press düzeltmelerini ana projeye ayrı değişiklik olarak önerir.

Press, Frappe 16 üzerinde yamalarla açılır. Sunucu kurma akışı doğrulanmadan üretime çıkılmaz. Kaynak: proje kaydı D-7 ve O-9.

## 1. Aktivasyon akışı (G-29, G-30, G-35, G-95)

```mermaid
sequenceDiagram
    autonumber
    actor K as Kiracı admin
    participant P as Panel SPA (@platform/shell)
    participant PT as press_tr.api
    participant PR as Press (press.api.site)
    participant IY as iyzico
    participant AG as Agent (f1)
    participant S as Kiracı sitesi (ERPNext v16)
    K->>P: Uygulamalar > HRMS TR > Etkinleştir
    P->>PT: get_apps_with_plans (TRY sarmalayıcı)
    PT-->>P: planlar, price_try, features
    K->>P: Plan seç
    P->>PT: ödeme yöntemi durumu (Team)
    alt Saklı kart yok
        P->>IY: ThreedsInitialize (1 TL ön provizyon)
        IY-->>PT: callback → ThreedsPayment, Iyzico Stored Card
        PT->>PR: Team.payment_mode='Card', default_payment_provider='iyzico'
    end
    P->>PT: install_app → öneri ve önizleme (fiyat, KDV, site)
    K->>P: Ayrı insan onayı (onay ucu)
    P->>PR: press.api.site.install_app(site, app, plan)
    PR->>PR: Site Active kontrolü, status=Pending
    PR->>AG: Agent Job "Install App on Site"
    PR->>PR: install_marketplace_conf → Subscription, site_config sk_hrms_tr
    AG->>S: bench install-app hrms_tr
    AG-->>PR: Job Success → after_install_script, Site Active
    PR-->>P: realtime agent_job_update
    P->>S: api.shell.get_bootstrap (installed apps, Workspace Sidebar)
    S-->>P: HRMS TR üst menü + çocuklar
    S->>PR: get_subscription_info(sk_hrms_tr) → özellik kapıları
```

Satın alma ödeme → abonelik → kurulum geçişleri tek durum makinesidir; yinelenen callback, kayıp iş sonucu ve ödeme alınıp kurulumun başarısız olduğu durumların telafisi G-125'tedir. Sabit kurallar: `install_app` yalnızca Site `Active` iken kabul edilir; Pending/Updating durumunda panel düğmeyi pasifler ve isteği kuyruğa alır (G-30). Her Free/Freemium uygulama için `price_usd=0` olan enabled bir Marketplace App Plan ve `run_after_install_script=1` şarttır; aksi halde Subscription ve `sk_<app>` anahtarı yazılmaz (doğrulandı, G-29). Kaldırma `press.api.client.run_doc_method(dt='Site', method='uninstall_app', args={app, create_offsite_backup, feedback})`, plan değişimi `change_app_plan` / `change_plan` + Site Plan Change ile yapılır. Ücret etkili her aksiyon önizle → onayla sözleşmesinden geçer; AI sağ paneli aynı araçları `press_tr.mcp.handler` üzerinden çağırır. Yazan araç işi yapmaz, yalnız öneri açar. İnsan öneriyi ayrı bir onay ucundan onaylar. Modelde onay aracı ve `confirm` alanı yoktur (G-27, [Rail 5](/frappesetup/rail-5-ai/)).

## 2. Plan ve tier modeli (G-9, G-10, G-25)

| Katman | Press nesnesi | Karar |
| --- | --- | --- |
| Site planı | Site Plan: Trial (is\_trial\_plan=1, 14 gün), Başlangıç, Büyüme, Kurumsal | cpu\_time\_per\_day, max\_database\_usage, max\_storage\_usage, offsite\_backups=1, release\_groups = ERPNext v16 TR, roles ile görünürlük |
| Uygulama planı | Marketplace App Plan (HRMS TR, CRM, Webshop) | interval Monthly, available\_on\_versions 'Version 16', features listesi (AI kotası dahil, G-92), her uygulamada bir ücretsiz plan |
| Para birimi | `price_try` Custom Field + USD karşılığı | `Team.before_insert` country='Türkiye' → currency='TRY'; `get_price_per_day` override TRY seçer; ücretli-uygulama kapıları `price_usd` okuduğu için her TRY planına USD karşılığı yazılır (doğrulandı) |
| Harcama sınırı | Team Tier, spending\_limit (USD eşdeğeri), apply\_limits=1 | `check_budget_alerts` eşiği panelde TRY ile ayarlanır; `billing_forecast` faturalama ekranında |
| Fiyat değişikliği | Yeni Site Plan kaydı; eski plan legacy\_plan=1 + allow\_downgrading\_from\_other\_plan | Fiyat anında yürürlüğe girer (doğrulandı); 30 gün önce e-posta + Press Notification, zamanlanmış Site Plan Change |

Faturalama defteri Press'in yerel zinciridir: Subscription → `create_usage_records` → taslak Invoice → günlük `finalize_monthly_draft_invoices`. Dunning sabitleri (ayın 15'inden sonra askıya alma, 21 gün sonra arşiv, 6 ay yedek saklama, ödemede `unsuspend_sites_if_applicable`) sözleşmeye aynı sayılarla yazılır; erteleme Payment Due Extension ile yapılır (G-24). Rail 6 bu zinciri yapılandırılabilir ve Türkçe hale getirir (SA-13).

## 3. iyzico entegrasyon planı (G-11, G-19, G-20)

Tahsilat modeli: Press abonelik defteri + iyzico saklı karttan tahsilat (ay içi plan değişimi ve kredi modeliyle uyumlu).

1. **Doctype'lar (`press_tr`)**: Iyzico Settings (sandbox/prod anahtarları Password tipli), Iyzico Payment Record, Iyzico Webhook Log, Iyzico Stored Card (Team başına `cardUserKey/cardToken`); Payment Gateway kaydı gateway='iyzico'.
2. **Kart ekleme**: ThreedsInitialize → callback → ThreedsPayment ile 1 TL ön provizyon ve iptal; başarıda `Team.payment_mode='Card'` ve `default_payment_provider='iyzico'` yazılır, çünkü `can_install_paid_apps`/`can_create_site` bu alana bakar (doğrulandı). 3DS ticari tahsilatta standart akıştır (doğrulanacak: mevzuat metni).
3. **Invoice override**: `finalize_invoice` Card dalı `default_payment_provider`'a göre dallanır; iyzico başarı → status Paid, payment\_date, transaction\_\*, submit → unsuspend; başarısızlık → Unpaid, günlük `finalize_unpaid_card_invoices` yeniden dener (doğrulandı). `apply_taxes_if_applicable` TRY + Türkiye → %20 KDV (oran kaynağı Press `Settings.gst_percentage`, etiket 'KDV'), yurt dışı → 0 hizmet ihracı istisnası (mali müşavir teyidi). `transaction_amount` her ödeme yolunda ve Team para birimiyle dolar; aksi halde operasyon sitesine fatura senkronu tetiklenmez (SA-11).
4. **Diğer yollar**: InstallmentInfo taksit; Refund → Invoice.status='Refunded' + Balance Transaction; itiraz → Payment Dispute; kredi yükleme `press_tr.api.billing.create_iyzico_checkout_form` (Checkout Form, SA-6) → Prepaid Credits Invoice; Havale/EFT için payment\_mode değeri 'NEFT' korunur, 'Havale/EFT' etiketi panelde gösterilir, ödeme referans kodu (PRS-…) faturada yer alır ve mutabakat Rail 6'da yapılır (SA-8, SA-34).
5. **Erişim**: `before_request` kancası iyzico callback/webhook yollarını ve `press_tr.api.` wildcard'ını her istekte idempotent olarak allowlist'e ekler; Iyzico doctype'ları `ALLOWED_DOCTYPES` + takım filtreli `get_list_query` ile panele açılır; webhook imzası (`X-IYZ-SIGNATURE-V3`) doğrulanır.

Kabul (P2): sandbox ve prod'da 3DS ile plan satın alma, saklı karttan aylık tahsilat, iade ve Havale/EFT akışları Invoice durum makinesiyle uçtan uca geçer; Press'te kart verisi yalnızca token olarak bulunur.

## 4. e-Fatura / e-Arşiv konumu (G-21, G-22, G-23)

Press ödenen faturayı `create_invoice_on_frappeio` ile dış ERPNext'e gönderir ve PDF'ini çeker (doğrulandı); bu yerel köprü şirketin kendi ERPNext v16 operasyon sitesine (Rail 6) yönlendirilir:

- Press `Settings.frappe_url` = operasyon sitesi, disable\_frappe\_auth=0. Gönderim tetiği finans olay–belge matrisine göredir (SA-41): Press yerel olarak yalnız ödenmiş faturayı gönderir (doğrulandı); kesinleşmede (Unpaid/Paid) gönderim VUK 231/5 yedi gün yorumuna bağlı bir seçenektir ve mali müşavir kararıyla seçilir (K-13); aynı fatura iki yoldan gönderilmez.
- Operasyon sitesinde (P2 finans çekirdeği) `press_tr_finance` uygulaması `create-fc-invoice` alıcısını, Sales Invoice → GİB özel entegratör (UBL-TR) gönderimini ve eşleme tablosunu uygular: Subscription → Sales Invoice + e-belge; Prepaid Credits → K-13 seçeneğine göre satış faturası veya alınan avans; NEFT → banka mutabakatı; Refunded → iade/Credit Note; Payment Dispute → şüpheli alacak; iyzico hakediş mutabakatı (SA-19, SA-21, SA-33).
- Press Invoice'a e\_invoice\_type, ettn, gib\_status, `e_invoice_pdf/xml` geri yazılır; `fetch_invoice_pdf` override GİB onaylı PDF'i Invoice.invoice\_pdf'e koyar, panel bunu indirir (G-96).
- VKN (10 hane) / TCKN (11 hane) algoritmik doğrulama, vergi dairesi, MERSIS ve e-Fatura mükellefi bayrağı Address Custom Field'larıdır (`doc_events validate: press_tr.api.billing.validate_tax_id`); checkout'ta `Team.billing_address` zorunlu ve Team.country == Address.country doğrulanır (Press ön koşulu, doğrulandı). Kayıtlı e-Fatura mükellefine e-Fatura, diğerlerine e-Arşiv düzenlenir.
- Mesafeli satış, ön bilgilendirme ve KVKK aydınlatma onayları Team üzerinde `consent_version/consent_at/consent_ip` ile; pazarlama onayı ayrı alan + İYS kaydı.

Entegratör seçimi ve yükümlülük takvimi P2 başında ürün sahibi ve mali müşavir tarafından kapatılır (doğrulanacak).

## 5. FC fixture ve kimlik yüzeyi temizliği (G-8, G-11, G-12, G-16, G-17)

`press_tr.after_migrate` her migrate'te çalışır; sync\_fixtures silinen kayıtları geri getirir ve yeni `modified` damgalı upstream fixture yerel değişiklikleri ezer (doğrulandı):

| Hedef | İşlem |
| --- | --- |
| 686 FC Site Plan | kendi plan seti dışındakiler enabled=0 |
| 6 FC Team Tier | TRY/USD tablosuyla değerler yeniden yazılır |
| Cloud Region / Server Plan | kullanılmayanlar kapatılır |
| Frappe Version | 'Version 16' default=1 (X-04) |
| Scheduler | `press.signup_e2e.run_signup_e2e` devre dışı (kimlik Keycloak'ta) |
| Roller | v0.8.0 yaması Press Admin/Member → Press User; takım içi yetki Press Role bayrakları (admin\_access, allow\_billing, allow\_apps, allow\_site\_creation, allow\_webhook\_configuration, allow\_local\_payment) ve press\_tr rol şablonları; operatör rolleri Rail 6'da (SA-2) |
| Kimlik uçları | Press eski kayıt, parola ve ikinci adım uçlarını 403 ile kapatır. Press giriş adresleri Keycloak’a yönlenir. `press_tr.api.auth.keycloak_callback`, kullanıcıyı `(iss, sub)` bağıyla bulur (G-12). |
| E-posta | 'Frappe Cloud' içeren 29 şablon + 13 string Türkçe markalı set ile değiştirilir; Press host için Email Account + SPF/DKIM |

## 6. Press altyapı envanteri — Hetzner (G-2..G-6, G-36, G-37)

Tablodaki adlar backend ad haritasına uyar. Adlar prod adıyla yazıldı. alpha, beta ve rc ortamlarında ortam adı araya girer. Örneğin rc'de Press `press.rc.atonota.net` adresindedir. Tam harita [Rail 6](/frappesetup/rail-6-operasyon/#canlı-ortamlar-ve-dağıtım-hattı) sayfasındadır. Ad haritasında olmayan adlar "MVP sonrası hedef" diye ayrıldı.

İki panel birbirine karışmasın: `panel.` adı Press'in müşteri panelidir, kiracının paneli ise kiracı adresinin `/panel` yoludur (örneğin `demo.app.atonota.net/panel`).

| Bileşen | Press doctype / ayar | Sahip |
| --- | --- | --- |
| Press host (Frappe 16, Python 3.14, MariaDB, Redis, certbot, docker CLI) | Press Settings (G-4); MVP'de Press `press.atonota.net` adresindedir. Press müşteri paneli için `panel.atonota.net` adı MVP sonrası hedeftir, backend ad haritasında yoktur. Backend MVP'de bu adı açmaz (`ortamlar.md` madde 4). `allow_cors` yok (G-119) | DevOps sorumlusu |
| n1 proxy (nginx, proxysql, wireguard, ssh\_proxy) | Proxy Server | DevOps sorumlusu |
| f1 app + build (x86\_64) | Server use\_for\_new\_sites=1, use\_for\_build=1 | DevOps sorumlusu |
| m1 veritabanı | Database Server (binlog, audit log, replika — G-55) | DevOps sorumlusu |
| r1 registry | Registry Server + Press Settings docker\_registry\_\* | DevOps sorumlusu |
| İzleme / log | Monitor Server (Prometheus/Grafana/Alertmanager), Log Server (ES/Kibana), Incident Settings, Telegram + e-posta. MVP'de yalnız e-posta vardır: Telegram paketi Press üretim imajında yoktur (7. bölüm) | DevOps sorumlusu |
| Yedek | Backup Bucket endpoint `https://fsn1.your-objectstorage.com`, GFS rotasyonu, fsn1→nbg1 `rclone sync --immutable`, Agent endpoint\_url yaması (upstream PR), RPO ≤ 24 s, aylık Backup Restoration Test. MVP'de düzenli yedek yoktur, çünkü zamanlanmış iş yasaktır. Yedek yalnız dağıtımda ve elle alınır. Düzenli yedek için proje sahibinin kararı gerekir (E-7). RPO ve aylık test bu karardan sonra geçerli olur | DevOps sorumlusu |
| Cluster | 'hetzner-fsn1' cloud\_provider='Generic' (bare metal); Hetzner Cloud VM'ler 'Hetzner' | DevOps sorumlusu |
| DNS / TLS | Route 53 hosted zone + sınırlı IAM; Root Domain dns\_provider='AWS Route 53'; wildcard certbot `--dns-route53`. MVP'de Route 53 yoktur: DNS GoDaddy'de kalır, sertifika her ad için ayrı alınır. Route 53 kararı Press sunucu kurma akışı çalışınca yeniden açılır (7. bölüm) | DevOps sorumlusu (Route 53/IAM, sonuç doğrulama) |
| Kiracı adları ve NS delegasyonu | MVP: kiracılar `<kiracı>.app.atonota.net` adresindedir, ilk kiracı `demo.app.atonota.net` olur. Kayıtlar GoDaddy'dedir, NS devri yoktur. GoDaddy'nin çok katlı joker kaydı kabul ettiği doğrulanmadı (E-11). MVP sonrası hedef: `app.atonota.net` NS kayıtları GoDaddy'den Route 53'e devredilir, sabit host'lar GoDaddy'de kalır (K-2) | Alan adı sorumlusu (uygular), DevOps sorumlusu (değer, doğrulama) |
| Operasyon sitesi (Rail 6) | Kendi Team'inde Release Group 'ops'; `ops.atonota.net` (MVP sonrası hedef, backend ad haritasında yok); P2 finans çekirdeği, P6 CRM/Helpdesk (SA-17) | DevOps sorumlusu; DNS alan adı sorumlusu |
| Operatör modu ve `ops-bff` (Rail 6) | `operator.atonota.net` (MVP sonrası hedef, backend ad haritasında yok): aynı SPA'nın operatör modu ve BFF'i, ters vekil arkasında; yalnız Tailscale/özel ağ, `press.` ile aynı sınır, Press Desk'ten ayrı origin (G-119, K-16) | DevOps sorumlusu (kayıt değeri, erişim sınırı, TLS); DNS kaydını alan adı sorumlusu GoDaddy'de uygular |
| Hocuspocus (Rail 6 destek oturumu) | Ayrı Node servisi + Redis, reverse proxy TLS (SA-29) | DevOps sorumlusu |
| Sürüm takibi | v0.155.x+ rc ortamındaki Press'te `bench migrate` + press\_tr testleri + aktivasyon E2E, sonra prod bakım penceresi | DevOps sorumlusu |
| Trace / Analytics (SHOULD) | Trace Server (GlitchTip), Analytics Server (Plausible; birinci taraf ürün analitiği adayı, rıza kapısı ve yüzey kuralları G-134) | DevOps sorumlusu |
| Güvenlik danışmanlığı | Danışmanlık izleme ve karar kaydı; acil yama rutin takvimi beklemez (G-142, K-26) | DevOps sorumlusu |

Kabul (P0): DNS kayıtları GoDaddy'den çözülür, TLS sertifikaları Active, test sitesi Active, offsite yedek bucket'ta listelenir ve geri yüklenir, Grafana/Kibana uyarıları e-postaya düşer. Route 53 açılırsa `dig NS` Route 53 sunucularını döner. Press üretim imajında Telegram paketi yoktur (7. bölüm).

## 7. Backend durumu: Press üretim imajı (O-52, O-18)

Bu bölüm backend'in 23 Kasım 2026 Pazartesi günkü durumunu anlatır. Kaynak `backend/PROJECT-RECORD.md` ve `backend/docs/dagitim/press-imaji.md` dosyalarıdır. Canlı sunucu henüz yoktur. Bu yüzden Press hiçbir ortamda canlıda çalışmıyor.

- **Sürümler.** İmaj Press v0.154.1, Frappe 16.56.0 ve Python 3.14.10 taşır. Taban imaj `frappe/erpnext:v16.55.0` imajıdır.
- **Yama dizisi (O-52).** Press v0.154.1 bu sürümlerle yamasız açılmaz. Bu yüzden üretim imajı beş yama uygular. Yamalar `backend/deploy/images/press-patches/` klasöründedir.
- **Yama kuralı.** Derleme her yamadan önce `git apply --check` çalıştırır. Yama tutmazsa derleme durur. Yamalar yalnız Python 3.14 ve Frappe 16 uyumu içindir. Ürün davranışı `press_tr` uygulamasına yazılır.
- **Bağımlılık kilidi.** Paketler özetli bir kilit dosyasından kurulur. `uv pip check` yalnız iki bilinen satırı bildirebilir. Başka her uyumsuzluk derlemeyi durdurur.
- **Geliştirme yaması (O-18).** `patch-py314.sh` betiği yalnız geliştirme imajında çalışır. Bu betik üretim imajına girmez.
- **Kapanma koşulu.** Press bir düzeltmeyi kabul edip yayımlarsa o yama silinir. Bütün yamalar kalkınca bu istisna kapanır.
- **Çalışmayan özellikler.** Telegram paketi imajda yoktur, bu yüzden Telegram uyarıları çalışmaz. Stripe ödeme akışı ve Marketplace uygulama denetimi sınanmadı.

İmaj yalnız geliştiricinin yerel bilgisayarındaki Colima ortamında denendi. İmaj sunucuda ve amd64 mimarisinde denenmedi. Canlıya çıkışın önünde şu iki engel durur:

1. Press'in sunucu kurma akışı Frappe 16'da çalışmıyor (E-1). MVP'de Press sunucu kurmaz. DevOps sorumlusu ilk kiracı sitesini elle açar.
2. Yedek, geri yükleme ve taşıma betikleri Press sitesini henüz kapsamıyor (E-2). Bu yüzden Press, rc ve prod ortamlarında kapalı kalır.

Adlar `atonota.net` alanındadır. Örneğin prod'da Press `press.atonota.net` adresindedir. Kiracılar `<kiracı>.app.atonota.net` adresindedir. Ortamların tam ad haritası [Rail 6](/frappesetup/rail-6-operasyon/#canlı-ortamlar-ve-dağıtım-hattı) sayfasındadır.
