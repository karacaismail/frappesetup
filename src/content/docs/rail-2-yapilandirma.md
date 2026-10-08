---
title: "Rail 2 — Frappe backend yapılandırma planı"
nav: "Rail 2 · Yapılandırma"
order: 4
---

Bu ray, kiracı bench'lerinde (Frappe v16 + ERPNext v16) yalnızca ayar ve kayıtla kurulan temel çizgiyi tanımlar; özel kod gereken noktalar `platform_core` (kiracı) veya `press_tr` (Press) adıyla belirtilir ve G-56..G-65'e devredilir. Tüm değerler Press doctype'larından yönetilir (G-38).

## Yapılandırma katmanları (G-38, G-39)

| Katman | Press kaynağı | Yayılma |
| --- | --- | --- |
| Platform varsayılanı | Press Settings.bench\_configuration | Yalnızca yeni bench (doğrulandı) |
| Release Group ortak (allow\_cors, mail\_\*, workers) | common\_site\_config\_table → `update_config` | Mevcut bench'lere yayılır |
| Site'a özgü (encryption\_key, keycloak\_client\_secret, sk\_\&lt;app&gt;) | Site.configuration | Tek site |

Site Config Key tohumlama press\_tr fixture'ıdır: Password → `mail_password`, `encryption_key`, `backup_encryption_key`, `keycloak_client_secret`; internal=1 → `host_name`, `server_script_enabled`, `plan_limit`. Kabul: mevcut bench'te `bench show-config` güncel değeri gösterir.

## Güvenlik, oturum ve yetki sınırı (G-40, G-43, G-44, G-46, G-53)

| Alan | Değer |
| --- | --- |
| Şema kaynağı | developer\_mode=0, server\_script\_enabled=0; DocType değişikliği yalnızca uygulama modül dosyaları ve fixture'lardan |
| Oturum/parola | session\_expiry '12:00', enable\_password\_policy=1, minimum\_password\_score=3, allow\_consecutive\_login\_attempts=5, allow\_login\_after\_fail=300, logout\_on\_password\_reset=1, reset\_password\_link\_expiry\_duration=900, password\_reset\_limit=3; Keycloak SSO Session Idle/Max aynı değerlerle (G-78) |
| Kimlik | Social Login Key provider 'Keycloak', base\_url `https://<idp>/realms/<realm>`, sign\_ups='Deny', user\_id\_property='sub'; Keycloak doğrulandıktan sonra disable\_user\_pass\_login=1, login\_with\_email\_link=0, Website Settings.disable\_signup=1; MFA Keycloak'ta; Administrator break-glass yalnızca Agent set-admin-password ile |
| Oran sınırı | Site Plan.cpu\_time\_per\_day → rate\_limit (duvar saati ölçer, doğrulandı); ağır raporlar 'reports' kuyruğunda; AI ve ödeme uçları `@frappe.rate_limit` |
| Desk sınırı | System Manager yalnızca operatörde; kiracı admin Role Profile + 'Role Permission for Page and Report'; platform\_core `before_request` 'Platform Operator' rolü olmayan /app\* isteklerini SPA'ya yönlendirir; enable\_onboarding=0, Website Settings.home\_page SPA |
| Impersonation | `user_impersonate` izin türü hiçbir role varsayılan verilmez; yalnız Support Session süresince platform\_core tarafından açılır; her kiracı sitede giden Email Account 'Security Alert' için hazır (SA-28) |

## CORS, CSRF ve same-site (G-45, G-13)

- Panel, Press ve kiracı siteleri aynı registrable domain altında; `allow_cors` yalnızca `https://app.<marka>.com.tr` değerini taşır ve Release Group `common_site_config` ile tüm bench'lere yazılır.
- SPA istekleri credentials include + `X-Frappe-CSRF-Token`; çerez SameSite=Lax, Secure.
- CSRF token yalnızca www/desk render'ında üretildiği için (doğrulandı) SPA kabuğu platform\_core `www/<panel>.py` sayfasından servis edilir ve `context.csrf_token` enjekte edilir.
- Kabul: giriş sonrası csrf\_token dolu; tokensiz PATCH 400, tokenli 200.

## Giden e-posta (G-47)

Release Group `common_site_config`: mail\_server, mail\_port=587, use\_tls=1, mail\_login, mail\_password (Password), auto\_email\_id `bildirim@<marka>`, always\_use\_account\_email\_id\_as\_sender=1, always\_use\_account\_name\_as\_sender\_name=1, email\_sender\_name=\&lt;marka&gt;. System Settings: `welcome/reset_password` şablonları platform Email Template'lerine bağlı, `email_footer_address` dolu, disable\_standard\_email\_footer=1, email\_retry\_limit=3. Relay Hetzner'de Postfix veya AB bölgeli sağlayıcı (KVKK envanterine girer): Hüseyin Cengiz relay'i kurar ve SPF/DKIM/DMARC/PTR değerlerini hazırlar, Asistan Hüseyin GoDaddy'de kayıtları uygular, Hüseyin Cengiz teslimatı doğrular. Kiracı kendi gönderici domainini Email Domain + Email Account ile panelden tanımlar; kota App Plan features'a bağlıdır.

## Dosya depolama (G-48)

P1'de dosyalar bench yerel diskinde ('with files' yedekleri kapsar); System Settings max\_file\_size=25, `allowed_file_extensions` beyaz listesi, strip\_exif\_metadata\_from\_uploaded\_images=1, allow\_guests\_to\_upload\_files=0, only\_allow\_system\_managers\_to\_upload\_public\_files=1; kota Site `Plan.max_storage_usage`. P2'de 'ERPNext S3 Integration' Hetzner Object Storage üzerinde tek bucket + site prefix ile pilotlanır (v16 uyumu doğrulanacak).

## Yedek, şifreleme, veritabanı ve işçiler (G-49, G-50, G-55, G-5, G-37)

Bu bölümün sahibi Hüseyin Cengiz'dir.

- Her sitede System Settings.encrypt\_backup=1 (gpg); `backup_encryption_key` ve Fernet encryption\_key Site.configuration'da Password tipli; anahtar biçimi press\_tr Site validate kancasında doğrulanır (Press'in Fernet doğrulaması ölü kod, doğrulandı). Press DB yedeği ayrı, age/KMS şifreli, iki konumda.
- Database Server doctype'ı: `innodb_buffer_pool_size` ≈ RAM %60-70, max\_connections ≥ Σ worker×thread + background + marj, is\_performance\_schema\_enabled=1, `enable_physical_backup`, `binlog_retention_days` + `enable_binlog_indexing` (point-in-time), `is_replication_setup` DR replikası, is\_database\_audit\_log\_enabled=1, audit\_log\_retention\_days=365. Kabul: binlog'dan 1 saatlik geri kazanım tatbikatı pass.
- İşçiler: Release Group gunicorn 2/8, background 2/6, gunicorn\_threads\_per\_worker=2, use\_rq\_workerpool=1; Bench.auto\_scale\_workers=1; `common_site_config` scheduler\_tick\_interval=60, `workers.long.timeout=3000`, 'reports' kuyruğu; her yeni sitede enable\_scheduler=1 doğrulanır.
- Offsite: Hetzner Object Storage GFS, RPO ≤ 24 saat, `alert_on_sites_with_missing_backups`, aylık Backup Restoration Test (G-5, G-37).

## Lokalizasyon ve ERPNext TR kurulumu (G-41, G-42, G-51, G-54, G-65)

| Adım | Mekanizma |
| --- | --- |
| Türkiye temel çizgisi | country='Türkiye' (v16 anahtarı, doğrulandı), language='tr', time\_zone='Europe/Istanbul', currency='TRY', number\_format '#.###,##', date\_format 'dd.mm.yyyy', time\_format 'HH:mm', first\_day\_of\_the\_week Monday, float\_precision=2, currency\_precision=2. Setup wizard float\_precision=3 yazdığı için (doğrulandı) değerler platform\_core `setup_wizard_complete` + idempotent `after_migrate` ile |
| Başsız setup wizard | press\_tr `override_doctype_class Site` → `Agent.complete_setup_wizard`; args: language 'tr', country 'Türkiye', timezone, currency 'TRY', company\_name/abbr, chart\_of\_accounts 'Turkey - Chart of Accounts', fy 01-01/12-31, enable\_telemetry 0. Kabul: Agent Job Success, setup\_complete=1, G-41 değerleri korunmuş |
| KDV ve TR verisi | `tr_localization`: KDV %20/%10/%1 Taxes and Charges Template, Item Tax Template, Tax Category 'İstisna', il/ilçe, Address VKN/TCKN/vergi dairesi, TCMB today.xml kur işi; `erpnext` Marketplace App'inde Marketplace Localisation App country='Türkiye' |
| Sürüm sabitleri | Bench Dependency Version 'Version 16': PYTHON 3.14, NODE 24.12.0, WKHTMLTOPDF 0.12.6, BENCH 5.31.0; environment\_variables TZ=Europe/Istanbul, LANG=tr\_TR.UTF-8; Frappe Version 'Version 16' default=1 (press\_tr.after\_migrate). Kabul: `node -v` 24.x. Sahip: Hüseyin Cengiz |
| PDF | Print Settings.pdf\_generator='chrome'; headless\_shell imajda hazır (doğrulandı), chromium\_max\_concurrent=2, Noto Sans + fonts-liberation. Kabul: PDF logunda 'downloading' yok |

## Fixture stratejisi (G-8, G-39, G-40, G-107)

- Press: `press_tr.after_migrate` her migrate'te FC Site Plan'larını (kendi setimiz dışında) enabled=0 yapar, Team Tier değerlerini TRY/USD tablosuyla değiştirir, `run_signup_e2e` scheduler kaydını kapatır; sync\_fixtures after\_migrate'ten önce çalışır (doğrulandı).
- Uygulama: `module/is_standard` taşıyan kayıtlar (DocType, Workspace, Workspace Sidebar standard=1, Print Format, Report, Notification) modül dosyasında; Role, Custom Field, Property Setter, Workflow, Role Profile, Email Template `hooks.fixtures` ön ek filtresiyle dışa aktarılır.
- Kiracı Custom Field/Property Setter kayıtları site DB'sinde kalır; meta site başına çalışma zamanında okunur (G-63).
- Sırlar yalnızca Password tipli Site Config Key'lerde yaşar (G-112).

## KVKK denetim ve saklama (G-52, G-64)

enable\_telemetry=0, allow\_error\_traceback=0, log\_api\_requests=1. Logs To Clear: Activity Log 365, Access Log 365, API Request Log 90, Error Log 30, Email Queue 30, Scheduled Job Log 14, View Log 90, Route History 90, Integration Request 90, OAuth Bearer Token 30, Webhook Request Log 30, Prepared Report 14. Permission Log ve Deleted Document platform\_core günlük işiyle 365 günde temizlenir (LogType protokolü dışı, doğrulandı). Personal Data Download/Deletion Request etkin, her uygulama `user_data_fields` tanımlar, satılan doctype'larda track\_changes=1. Saklama/legal hold matrisi ve rıza sürümleme Rail 6'da tanımlanır (SA-36).
