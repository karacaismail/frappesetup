---
title: "Mimari raylar (Rail 1⁠–⁠6) ve sorumluluk sınırları"
nav: "Raylar"
order: 2
---

Platform altı ray üzerinde kurulur. Her ray kendi alanının tek doğruluk kaynağıdır; diğer raylar o alana yalnızca aşağıda adlandırılan sözleşmelerden (API yolu, olay, token) erişir. Özel kodun evleri sabittir: `press_tr` ve `press_tr_finance` (Rail 1), `platform_core`, `tr_localization` ve satılan uygulamalar (Rail 2), panel monorepo'su (Rail 3), Keycloak tema paketi ve `identity-sync` (Rail 4), agent servisi (Rail 5), `press_ops_bridge` + operasyon sitesi uygulamaları ve superadmin operatör modu (Rail 6).

<div data-embed="rails"></div>

## Ray başına sahiplik, sözleşme ve tüketim

| Ray | Sahip olduğu | Dışa açtığı sözleşme | Tükettiği |
| --- | --- | --- | --- |
| **Rail 1 — Press ticari kontrol düzlemi** (Frappe v15 / Python 3.11, `press.<marka>.com.tr`; sunucu envanteri Hüseyin Cengiz, G-1, G-3) | Team, Site, Site Plan, Marketplace App / App Plan, Subscription, Usage Record, Invoice, Agent Job, Release Group → Deploy Candidate → Bench zinciri, Product Trial, Root Domain/TLS, Backup Bucket; `press_tr` (iyzico, TRY, KDV, e-belge köprüsü, auth allowlist, Türkçe şablonlar) ve `press_tr_finance` (G-7, G-19..G-22) | `/api/method/press.api.site.*` (`new`, `get_plans`, `change_plan`, `install_app`, `add_domain`), `press.api.marketplace.*`, `press.api.billing.*`, `press.api.client.*` (ALLOWED\_DOCTYPES, G-11), `press_tr.api.*` (TRY sarmalayıcıları, `trial.start`, `billing.buy_credits_iyzico`), `press.api.developer.marketplace.get_subscription_info` (G-35), realtime `agent_job_update` (G-15), `press_tr` doc\_events → agent servisine imzalı HTTPS (G-15), `press.mcp.handler` ve `press_tr.mcp.handler` (G-27), Frappe OAuth Client bearer (G-28) | Keycloak OIDC (Social Login Key `press`, G-12), Route 53 (G-2), Hetzner Object Storage (G-5), iyzico API (G-19), finans sitesi `create-fc-invoice` (G-22), GitHub App (G-14), sunuculardaki Agent |
| **Rail 2 — Kiracı Frappe/ERPNext v16 backend** (`<kiracı>.<marka>.com.tr`) | Kiracı başına site ve DB; `platform_core` (Access Rule motoru, shell bootstrap, meta API, AI Action Log, Keycloak SLO ve JWT `auth_hooks`, TR temel çizgisi, `/panel` www sayfası; G-56), `tr_localization` (G-65), satılan uygulamalar; yapılandırma katmanları (G-38) | `/api/v2/document/<DocType>` ve `/api/v2/method/*`, `platform_core.api.shell.get_bootstrap` ve `api.meta.get_doctype` (ETag'li, G-63), `api.identity.*` (G-57), `api.keycloak_backchannel_logout` (G-58), yetki yönetimi uçları (G-62), `platform_core.subscription.has_feature` (G-106), `ai_tools` hook'u ile kiracı MCP (`frappe_mcp`, v16 uyumu doğrulanacak; G-84, G-105), socket.io `doc_update`/`list_update`, CSRF token'lı `/panel` (G-45) | Press site\_config (`sk_<app>`, `plan_limit`, `encryption_key`), Developer API (G-35), Keycloak Social Login Key `site-<kiracı>` ve realm JWKS (G-44, G-59), identity-sync çağrıları (G-81), SMTP relay (G-47) |
| **Rail 3 — Headless panel** (React, Ant Design, `@ant-design/x`, TanStack) | Monorepo paketleri `@platform/shell`, `frappe-sdk`, `meta-ui`, `design-tokens`, `ai-sidebar`, `@apps/*` (G-66); alan tipi → AntD eşlemesi ve override registry (G-69), i18n (G-73), Playwright matrisi (G-74) | `AppModule` TypeScript sözleşmesi (G-103), tasarım tokenları (G-67); UI `https://<kiracı>.<marka>.com.tr/panel` ve `https://panel.<marka>.com.tr` (G-75) | Rail 2 `/api/v2` + bootstrap/meta, Rail 1 `press.api.*`/`press_tr.api.*` + realtime (G-13), Keycloak `panel-spa` PKCE (G-77), agent SSE akışı (G-88) |
| **Rail 4 — Keycloak kimlik** (`id.<marka>.com.tr`; HA kurulum Hüseyin Cengiz, G-76) | Realm `platform`; client'lar `panel-spa`, `press`, `site-<kiracı>`, `agent-service`, `identity-sync` (G-77); Organizations = Press Team eşlemesi (GA durumu doğrulanacak); MFA, parola ve oturum politikaları (G-78); Türkçe markalı tema (G-80); kullanıcı/admin olayları; `identity-sync` servisi (G-81) | OIDC uçları `/realms/platform/protocol/openid-connect/{auth,token,userinfo,logout,certs}`, standart token exchange V2 (G-82), Admin API, Event Listener webhook (G-81), Account Console (G-99), back-channel logout çağrısı (G-58) | `press_tr.api.identity.*` ve `platform_core.api.identity.*` provizyon uçları, SMTP (doğrulama e-postaları) |
| **Rail 5 — AI** (agent servisi; konteyner/DB/TLS Hüseyin Cengiz, G-83) | Claude Agent SDK servisi, PostgreSQL/Redis, model yönlendirme (haiku sınıflandırma, sonnet/opus aksiyon), önizle+onayla hash'i (G-86), PII maskeleme (G-90), kota sayaçları (G-92), eval seti (G-91) | Panel için SSE uç noktası, `press_tr` doc\_events alıcısı (public HTTPS, G-15), kalan kota ucu | `press.mcp.handler` (System User, yalnızca ops), `press_tr.mcp.handler` (kullanıcıya bağlı Press bearer), kiracı `frappe_mcp` (Keycloak token, G-59/G-85), Keycloak token exchange, Anthropic API |
| **Rail 6 — Operasyon düzlemi** (sahibin kendi ERPNext v16 sitesi `ops.<marka>.com.tr` + superadmin operatör modu; dağıtım Hüseyin Cengiz, DNS Asistan Hüseyin, SA-17) | Müşteri cari kartı (`Customer` ↔ Press Team), `Sales Invoice`/`Payment Entry`/GL, e-Fatura/e-Arşiv köprüsü, Frappe CRM (`CRM Lead/Deal`), Frappe Helpdesk (`HD Ticket`, SLA, bilgi bankası), `Support Session` kaydı, operatör denetim raporu, Hocuspocus destek odaları (SA-17..SA-37) | `create-fc-invoice` ve `delete-fc-team` alıcıları (Press'in hazır istemci kodu), `platform_core.api.ops.customer_360`, HD Ticket API (agent servisi relay), Hocuspocus `onAuthenticate`/`extension-webhook` | Press `press_ops_bridge` olayları (Team, Balance Transaction, Marketplace App Subscription, Support Access), `press.api.ops` (System User servis hesabı), Keycloak operatör realm rolleri, iyzico hak ediş CSV (SFTP), banka ekstresi (CSV/MT940) |

## Sınır kuralları

- Yetkinin tek doğruluk kaynağı katmanlıdır: Keycloak kimlik + MFA + Organization üyeliği; Press Role ticari/takım yetkisi (G-16); Frappe Role Profile + User Permission + Access Rule veri yetkisi (G-60, G-61); her MCP aracı çağıran kullanıcının kimliğiyle aynı `has_permission` yolundan geçer (G-85).
- Plan, fatura ve abonelik durumu yalnızca Rail 1'de yazılır; Rail 2 ve Rail 3 bunu `get_subscription_info` ve `has_feature` üzerinden okur (G-35, G-106).
- DocType meta ve sidebar yalnızca Rail 2 bootstrap/meta uçlarından türer; panelde elle kodlanmış menü veya form bulunmaz (G-63, G-94).
- Kiracı verisi Rail 2'den çıkmaz; agent servisi kiracı verisine kullanıcının token'ıyla erişir, konuşma verisi Hetzner'de kalır (G-83, G-90).
- Muhasebe, cari ve ticket kayıtlarının tek doğrusu Rail 6 operasyon sitesidir; Press yalnız ticari defteri (plan, abonelik, kredi, fatura, ödeme kaydı) tutar ve her ödenmiş faturayı `create-fc-invoice` ile oraya iletir; superadmin paneli iki kaynağı birleştirir, yazma her zaman sahibi sisteme gider (SA-19, SA-22, SA-23, SA-25).
- `panel.`, `press.`, `id.`, `ops.` ve `<kiracı>.` ana bilgisayarları aynı kayıtlı alan altında kalır; wildcard kiracı bölgesi bu sabit adları kapsamaz (G-13, G-45). Route 53 NS delegasyonunu Asistan Hüseyin GoDaddy'de uygular, Hüseyin Cengiz doğrular (G-2).

## Modül düzeyindeki geliştirmelerin Rail 1'e yansıması

Satılan her uygulama (CronHR, CRM, Webshop) Rail 2'de geliştirilir ve Rail 1'de şu kayıtlarla ticarileşir:

1. **Kaynak ve dağıtım:** App + App Source (GitHub App), `pyproject.toml` içinde `[tool.bench.frappe-dependencies] frappe = ">=16.0.0 <17.0.0"`, `erpnext-v16-tr-staging` (auto deploy) ve `erpnext-v16-tr-prod` (zamanlanmış, `deploy_hours` UTC) Release Group'ları (G-14, G-54).
2. **Katalog:** Marketplace App (Published, `run_after_install_script=1`) ve Marketplace App Plan'lar — TRY fiyat + USD karşılığı; Free/Freemium için `price_usd=0` plan zorunlu, aksi halde Subscription ve `sk_<app>` yazılmaz (G-10, G-29).
3. **Aktivasyon sözleşmesi:** `press.api.site.install_app(site, app, plan)` → Agent Job → `install_marketplace_conf` → `sk_<app>`; kaldırma `press.api.client.run_doc_method('Site', 'uninstall_app')`; plan değişimi `change_app_plan` (G-30). Panel realtime Success sonrası `get_bootstrap`'ı yeniden çeker ve sidebar yeni üst öğeyi gösterir (G-94, G-95).
4. **Deneme:** Product Trial apps listesi ve `press_tr` Türkçe kurulum payload'ı (G-31).
5. **Özellik kapıları:** Plan `features` → `get_subscription_info` → `has_feature`; AI kotası aynı features alanında (G-35, G-92, G-106).
6. **AI araçları:** uygulamanın `ai_tools` manifesti kiracı MCP'de keşfedilir; ücretli/yıkıcı bayrakları Rail 5 onay akışına, ticari aksiyonlar `press_tr.mcp.handler`'a bağlanır (G-27, G-105).
7. **Yayın kapısı:** Admin Shell uyumluluk listesi (G-102..G-107) ve staging aktivasyon E2E testi geçmeden prod Release Group'a giriş yapılmaz (G-111).

## Raylar arası veri akışı


Tarayıcı tek SPA'yı yükler; aynı shell müşteri panelini ve operatör (superadmin) modunu taşır. SPA müşteri sitelerini ve operasyon sitesini `/api/v2` ile, Press'i `press.api.*` ile, agent servisini sağ panelden çağırır; Press müşteri ve fatura kayıtlarını operasyon sitesine, deploy'u müşteri sitelerine iletir; agent servisi üç tarafı da MCP ile yönetir ve her çağrı Keycloak kimliğini taşır.
