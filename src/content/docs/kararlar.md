---
title: "Sabitlenen kararlar ve kapsam"
nav: "Kararlar"
order: 1
---

Aşağıdaki on karar sabittir; dokümandaki her plan bu kararların üzerine kurulur ve hiçbirini yeniden tartışmaz. Ürün sahibi, mali müşavir veya hukuk kararı isteyen konular ve önerilen teknik varsayımlar [açık kararlar](/frappesetup/acik-kararlar/) sayfasında türleriyle ayrıdır.

| # | Karar | Gerekçe | Sonuç |
| --- | --- | --- | --- |
| K1 | Kontrol düzlemi: **Press v0.154.x** (`master` dalı, semantic-release) + **Frappe 16** + Python 3.14 | Bütün uygulamalar Frappe 16 ile yazılır. Press de Frappe 16 üzerinde geliştirilir. Bu karar backend proje kaydındaki D-7, D-15 ve O-9 kararıdır | Press bu sürümde yalnız açık bir yama dizisiyle açılır (O-52). Press'in sunucu kurma akışı Frappe 16'da çalışmadan üretime çıkılmaz. Press kendi sunucusunda çalışır |
| K2 | Müşteri siteleri: **ERPNext v16.50 + Frappe v16**, müşteri başına bir Frappe sitesi | En güncel kararlı ürün hattı; Press v16 siteleri yönetiyor | Siteler Press'in kurduğu Docker bench'lerinde çalışır (n/f/m sunucuları) |
| K3 | Altyapı: **Hetzner bare-metal, self-host** | Maliyet ve veri egemenliği; KVKK için AB içi veri yerleşimi | Press'in ihtiyaç duyduğu tüm sunucu rolleri Hetzner'de kurulur; sahibi DevOps sorumlusu |
| K4 | Frontend: **%100 headless React SPA**; **Ant Design** tek tasarım sistemi; **`@ant-design/x`** AI arayüzlerinde birinci sınıf; **TanStack** (Query, Router, Table) | Tek görsel dil, AI-first bileşenler hazır, veri katmanı olgun | Tasarım kimliği AntD token'larının üstündeki semantik token katmanında kurulur |
| K5 | Frontend **metadata-driven** çalışır; DocType meta'sı çalışma zamanında API'den okunur | Doctype değişikliği frontend'e otomatik yansımalı; tenant'a özel Custom Field'lar siteden siteye farklı meta üretir | Alan tipi → bileşen eşleme motoru + doctype bazlı açık override mekanizması |
| K6 | Sidebar ve navigasyon **Workspace + kurulu app + izin** verisinden türetilir | Modül etkinleşince sidebar kendiliğinden güncellenmeli | Hiçbir menü elle kodlanmaz |
| K7 | Kimlik: **Keycloak** tüm uygulamalar için tek giriş/kayıt sağlayıcısı | Çoklu uygulama (panel, faturalama, gelecek app'ler) için tek kimlik | Frappe ve Press Keycloak'a OIDC ile bağlanır |
| K8 | Erişim: **Zoho/Odoo düzeyinde** rol ve yetki yönetimi (ReBAC/ABAC kayıt kuralları, hiyerarşi, alan düzeyi) | Frappe RBAC tek başına SaaS müşterisinin kendi yönettiği yetki modelini karşılamaz | Platform çekirdek app'inde erişim politikası motoru geliştirilir |
| K9 | **AI-first**: Press ve siteler MCP ile yönetilir. Ajan servisi ve model geçidi sağlayıcıdan bağımsızdır. Panelde sağda AI paneli bulunur. AI eylemleri aynı sunucu izinlerinden geçer. Yazma eylemi önizleme ve onay ister. Her eylem denetim günlüğüne düşer | Tek tıkla aksiyon ve kararlı orkestrasyon. Proje sahibi her şeyin yapay zekâyla yönetilmesini ve sağlayıcıdan bağımsızlığı istedi (D-9, D-11) | Sisteme birden çok sağlayıcı, hesap ve API eklenir. Model adı kodda yazılmaz, model kaydında durur (O-10, O-13). Modelde onay alanı yoktur. Onay insan oturumundaki ayrı uçtan gelir. KVKK uyumu zorunludur |
| K10 | Ürünler ayrı Frappe app'leri olarak satılır: **HRMS TR** önce, sonra **CRM**, **Webshop**; hepsi ortak **admin shell** çerçevesine uyar; modül etkinleştirme **Press Marketplace / App Plan** üzerinden | Zoho/Odoo tarzı "etkinleştir" deneyimi | Her app bu dokümandaki app çerçevesi şablonunu karşılar |

K3 notu: Hetzner'in AB'de olması KVKK yurt dışı aktarım şartlarını tek başına karşılamaz; aktarım mekanizması hukukça belirlenir (G-90, G-116).

K1 ve K9 notu: Bu iki satır 23 Kasım 2026 Pazartesi günü backend proje kaydına göre güncellendi. Kayıt `backend/PROJECT-RECORD.md` dosyasındadır. D ile başlayan kimlikler proje sahibinin kararlarıdır. O ile başlayan kimlikler orkestratörün kararlarıdır. Proje sahibi bu kararları orkestratöre bıraktı.

## Kapsam

- **Kapsam içi:** Press'in self-host yapılandırması ve ticari katmanı (Rail 1), müşteri sitesi backend'inin yapılandırması ve platform çekirdek app'i (Rail 2), headless admin shell ve metadata motoru (Rail 3), Keycloak kimlik katmanı (Rail 4), AI katmanı (Rail 5), operasyon düzlemi (Rail 6), ürün sözleşmeleri (kalite kuralları, URL ve paylaşım, ölçüm, yardım ve tur), gereksinim çerçevesi, app şablonu ve yol haritası.
- **Durum:** Bu doküman tasarım ve karar çerçevesidir; SaaS henüz kurulmadı. Tanımlanan kontroller gereksinimdir, uygulanmış veya test edilmiş güvenlik sayılmaz. Backend kodu `backend/` klasöründe MVP düzeyinde yazılıyor. Kod yalnız yerelde ve örnek veriyle denendi. Canlı sunucu henüz yoktur. Bu yüzden hiçbir iş canlıda çalışmıyor.
- **Kapsam dışı:** Pazarlama web sitesi ve müşteri sitelerinin iş kuralları (bunlar app'lerin kendi dokümanlarında yer alır).

## Roller

| Kişi | Sorumluluk |
| --- | --- |
| Ürün sahibi | Mimari ve ürün kararları, bu dokümandaki açık kararların kapatılması |
| DevOps sorumlusu (kıdemli DevOps mühendisi) | Hetzner sunucuları, Press kurulumu, Keycloak, CI/CD, deploy ve rollback |
| Alan adı sorumlusu | GoDaddy hesabı, domain ve DNS değişiklikleri (teknik gereksinimi DevOps sorumlusu hazırlar) |
| Finans/Muhasebe ve mali müşavir | Vergi ve belge zamanlaması, finans olay–belge matrisi (K-13, SA-41) |
| Hukuk | KVKK, rıza ve aktarım mekanizması, lisans değerlendirmesi (K-1, K-27, K-28) |
