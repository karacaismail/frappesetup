---
title: "Sabitlenen kararlar ve kapsam"
nav: "Kararlar"
order: 1
---

Aşağıdaki on karar sabittir; dokümandaki her plan bu kararların üzerine kurulur ve hiçbirini yeniden tartışmaz.

| # | Karar | Gerekçe | Sonuç |
| --- | --- | --- | --- |
| K1 | Kontrol düzlemi: **Press v0.154.x** (`master` dalı, semantic-release) + **Frappe v15** + Python 3.11 | Press'in test edildiği ve Ansible dahil tüm işlevlerinin çalıştığı hat; v15 güvenlik yamaları sürüyor (v15.122.0, 6 Ekim 2026) | Press kendi sunucusunda/VM'inde çalışır; müşteri sitelerinin sürümünden bağımsızdır |
| K2 | Müşteri siteleri: **ERPNext v16.50 + Frappe v16**, müşteri başına bir Frappe sitesi | En güncel kararlı ürün hattı; Press v16 siteleri yönetiyor | Siteler Press'in kurduğu Docker bench'lerinde çalışır (n/f/m sunucuları) |
| K3 | Altyapı: **Hetzner bare-metal, self-host** | Maliyet ve veri egemenliği; KVKK için AB içi veri yerleşimi | Press'in ihtiyaç duyduğu tüm sunucu rolleri Hetzner'de kurulur; sahibi Hüseyin Cengiz |
| K4 | Frontend: **%100 headless React SPA**; **Ant Design** tek tasarım sistemi; **`@ant-design/x`** AI arayüzlerinde birinci sınıf; **TanStack** (Query, Router, Table) | Tek görsel dil, AI-first bileşenler hazır, veri katmanı olgun | Tasarım kimliği AntD token'larının üstündeki semantik token katmanında kurulur |
| K5 | Frontend **metadata-driven** çalışır; DocType meta'sı çalışma zamanında API'den okunur | Doctype değişikliği frontend'e otomatik yansımalı; tenant'a özel Custom Field'lar siteden siteye farklı meta üretir | Alan tipi → bileşen eşleme motoru + doctype bazlı açık override mekanizması |
| K6 | Sidebar ve navigasyon **Workspace + kurulu app + izin** verisinden türetilir | Modül etkinleşince sidebar kendiliğinden güncellenmeli | Hiçbir menü elle kodlanmaz |
| K7 | Kimlik: **Keycloak** tüm uygulamalar için tek giriş/kayıt sağlayıcısı | Çoklu uygulama (panel, faturalama, gelecek app'ler) için tek kimlik | Frappe ve Press Keycloak'a OIDC ile bağlanır |
| K8 | Erişim: **Zoho/Odoo düzeyinde** rol ve yetki yönetimi (ReBAC/ABAC kayıt kuralları, hiyerarşi, alan düzeyi) | Frappe RBAC tek başına SaaS müşterisinin kendi yönettiği yetki modelini karşılamaz | Platform çekirdek app'inde erişim politikası motoru geliştirilir |
| K9 | **AI-first**: Press ve siteler MCP ile yönetilir; Claude Agent SDK tabanlı agent servisi; panelde sağ AI paneli; AI eylemleri aynı sunucu izinlerinden geçer, yazma eylemleri önizleme + onay ister, her eylem audit'e düşer | Tek tıkla aksiyon ve kararlı orkestrasyon | Modeller: `claude-sonnet-5-5` / `claude-opus-5-5` eylem, `claude-haiku-4-5` sınıflandırma; KVKK uyumu zorunlu |
| K10 | Ürünler ayrı Frappe app'leri olarak satılır: **HRMS (CronHR)** önce, sonra **CRM**, **Webshop**; hepsi ortak **admin shell** çerçevesine uyar; modül etkinleştirme **Press Marketplace / App Plan** üzerinden | Zoho/Odoo tarzı "etkinleştir" deneyimi | Her app bu dokümandaki app çerçevesi şablonunu karşılar |

## Kapsam

- **Kapsam içi:** Press'in self-host yapılandırması ve ticari katmanı (Rail 1), müşteri sitesi backend'inin yapılandırması ve platform çekirdek app'i (Rail 2), headless admin shell ve metadata motoru (Rail 3), Keycloak kimlik katmanı (Rail 4), AI katmanı (Rail 5), gereksinim çerçevesi, app şablonu ve yol haritası.
- **Kapsam dışı:** Pazarlama web sitesi ve müşteri sitelerinin iş kuralları (bunlar app'lerin kendi dokümanlarında yer alır).

## Roller

| Kişi | Sorumluluk |
| --- | --- |
| Ürün sahibi | Mimari ve ürün kararları, bu dokümandaki açık kararların kapatılması |
| Hüseyin Cengiz (kıdemli DevOps) | Hetzner sunucuları, Press kurulumu, Keycloak, CI/CD, deploy ve rollback |
| Asistan Hüseyin | GoDaddy hesabı, domain ve DNS değişiklikleri (teknik gereksinimi Hüseyin Cengiz hazırlar) |
