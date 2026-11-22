---
title: "Rail 4 — Keycloak kimlik ve erişim planı"
nav: "Rail 4 · Keycloak"
order: 7
---

Keycloak; panel, Press, operasyon sitesi ve tüm kiracı siteleri için tek kimlik sağlayıcısıdır: kimlik doğrulama, MFA, e-posta doğrulama ve Organization üyeliğini taşır. Yetkinin doğruluk kaynağı uygulama tarafıdır (Press Role, Frappe Role Profile, Access Rule; X-10). Bu ray G-76..G-82'yi uygular ve G-12, G-16, G-28, G-44, G-57, G-58, G-59'daki Frappe karşılıklarına bağlanır; operatör kimliği SA-1..SA-3'te tanımlanır.

## 1. Kimlik modeli (G-77)

| Nesne | Keycloak karşılığı | Eşlendiği kayıt |
| --- | --- | --- |
| Realm | `platform`. Her ortamın (alpha, beta, rc, prod) kendi Keycloak'ı vardır ve realm adı her ortamda aynıdır (X-02) | — |
| Müşteri takımı | Organization (alan adı, üyelik, davet) | Press Team `keycloak_org_id` Custom Field (press\_tr) |
| Kullanıcı | User; kalıcı anahtar `(iss, sub)` (G-120), e-posta yalnız iletişim özniteliği | Press User + Team üyesi; kiracı sitede son kullanıcı “Website User” olur (backend O-3; G-57) |
| Operatör (sahibin personeli) | `platform-operator` grubu; realm rolleri `ops-admin`, `ops-billing`, `ops-support`, `ops-finance` | Press System User + Press Ops Billing / Support Agent rolleri; operasyon sitesi rolleri (SA-1, SA-2, SA-3) |
| Panel | Ayrı istemci yok (K-25): panel host'u Press sitesidir ve `press` istemcisiyle oturum açar; tarayıcıya belirteç verilmez | — |
| Press | `press` gizli anahtarlı istemcisidir. | Dönüş ucu `press_tr.api.auth.keycloak_callback` olur (G-12). |
| Kiracı sitesi | `site-<kiracı>` gizli anahtarlı istemcisidir. identity-sync istemciyi ve hedef kapsamını açar. | Dönüş ucu `platform_core.api.auth.keycloak_callback` olur. Sistem kullanıcıyı `(iss, sub)` bağıyla bulur (G-44, G-120). |
| Operasyon sitesi | `site-ops` (confidential) ve audience kapsamı (yalnız `ops-bff`'ye, varsayılan olmayan) | Frappe Social Login Key; yalnız `platform-operator` grubu girer (SA-3) |
| Servisler | `agent-service`, `identity-sync`, `press-service` (service account) | Press OAuth Client + platform\_core `auth_hooks` (G-28, G-59); Hocuspocus Keycloak istemcisi kullanmaz, site biletini doğrular (SA-29, G-148) |
| Operatör BFF'i | `ops-bff` (confidential; servis hesabı yok; standart akış + PKCE ve standart token exchange açık; dönüş ve back-channel logout adresleri yalnız `operator.` üzerinde tam adres) | Operatör başına Press API key (SA-1); hedef sitenin `auth_hooks`'u (G-59) |

Press ve kiracı, kullanıcıyı belirteçteki `(iss, sub)` bağıyla eşler. E-posta iletişim alanıdır. Kiracıdaki hazır `login_via_keycloak` ucu 403 döner (sözleşme 5. bölüm).

## Origin ve oturum sözleşmesi (G-119)

Tek Keycloak SSO oturumu her siteye etkileşimsiz OIDC dönüşüyle ayrı bir site oturumu açtırır; ortak parent-domain `sid` yoktur. Bu tablo tasarım sözleşmesidir; uygulanmadı ve test edilmedi.

Tablodaki adlar backend ad haritasına uyar. Adlar prod adıyla yazıldı. alpha, beta ve rc ortamlarında ortam adı araya girer. Örneğin beta'da giriş adresi `api.login.beta.atonota.net` olur. Tam harita [Rail 6](/frappesetup/rail-6-operasyon/#canlı-ortamlar-ve-dağıtım-hattı) sayfasındadır. Ad haritasında olmayan adlar "MVP sonrası hedef" diye ayrıldı.

İki panel birbirine karışmasın: `panel.` adı Press'in müşteri panelidir, kiracının paneli ise kiracı adresinin `/panel` yoludur (örneğin `demo.app.atonota.net/panel`).

| Host | Sunan | Oturum | CSRF kaynağı | CORS | Realtime / WS kimliği |
| --- | --- | --- | --- | --- | --- |
| `panel.atonota.net` (MVP sonrası hedef. Backend MVP'de bu adı açmaz, `ortamlar.md` madde 4) | Press müşteri paneli (press\_tr www, SPA) | Host'a bağlı `sid` | www sayfası | Yok (aynı origin) | Press socket.io, aynı origin |
| `operator.atonota.net` (MVP sonrası hedef) | Aynı SPA'nın operatör modu ve operatör BFF'i (`ops-bff`), ters vekil arkasında aynı origin; yalnız Tailscale/özel ağ (`press.` ile aynı sınır, Press Desk'ten ayrı origin); satıcı betiği yok (G-134) | BFF'in host'a bağlı HttpOnly sunucu oturumu; Keycloak belirteçleri yalnız bu oturumda (G-148); dönüş ve back-channel logout adresi bu origin'de (G-58) | BFF oturumuna bağlı CSRF belirteci | Yok (aynı origin); tarayıcı `ops.` host'una istek atmaz (K-16) | Operatör bileti: `ops-bff` kiracı sitesinden alır; Hocuspocus yalnız bu origin'den kabul eder |
| `press.atonota.net` | Press Desk (operatör; yalnız Tailscale) | Ayrı `sid` | Desk | Yok | Desk |
| `<kiracı>.app.atonota.net` (ilk kiracı `demo.app.atonota.net`) | Kiracı sitesi (platform\_core www, SPA). Kiracının paneli bu adresin `/panel` yoludur | Host'a bağlı `sid` | `www/<panel>.py` | Yok | Kiracı socket.io, aynı origin |
| Doğrulanmış özel alan adı | Aynı kiracı sitesi; kiracının kayıtlı origin'i (G-119) | O host'a bağlı `sid` | Aynı | Yok | Aynı origin; redirect URI tam adres (G-124) |
| `ops.atonota.net` (MVP sonrası hedef) | Operasyon sitesi (personel Desk); operatör modu buraya yalnız `ops-bff` üzerinden erişir | Host'a bağlı `sid` | Desk / www | Yok | — |
| `agent.` ve Hocuspocus (MVP sonrası hedef) | Agent servisi, Hocuspocus | Çerez yok; aracı belirteci / tek kullanımlık bilet (G-148) | Gerekmez | Aracı belirteci ve müşteri bileti yalnız basan kiracının kayıtlı origin'lerinden (kiracı host'u ve doğrulanmış özel alan adları, G-119), operatör bileti yalnız `operator.` origin'inden (`ops.` listede yok); kimlik bilgisiz | Bilet + aktif Support Session |
| `api.login.atonota.net` (AtonotA Login, K-61) | Keycloak | Yalnız Keycloak SSO oturumu | Keycloak | Yok | — |

## 2. Akışlar

`get_oauth2_authorize_url` whitelisted değildir (doğrulandı); SPA authorize URL'sini `press_tr.api.auth.get_login_url(redirect_to)` ve `platform_core.api.auth.get_login_url` sarmalayıcılarından alır, state sunucuda üretilir.

**Giriş — tek SSO oturumu, host'a bağlı site oturumları**

```mermaid
sequenceDiagram
  autonumber
  participant U as Kullanıcı
  participant P as Press paneli (panel.)
  participant PR as Press
  participant K as Keycloak
  participant T as Kiracı SPA (kiracı host'u)
  participant S as Kiracı sitesi
  U->>P: panel adresi
  P->>PR: press.api.account.get (401)
  P->>PR: press_tr.api.auth.get_login_url
  P-->>U: 302 Keycloak authorize (client press, scope openid)
  U->>K: parola + TOTP/passkey (G-78)
  K-->>U: 302 kod, press_tr.api.auth.keycloak_callback
  PR->>K: token + userinfo
  PR->>PR: (iss, sub) ile User eşle (G-120), Team yoksa press_tr oluşturur (G-12), host'a bağlı sid
  PR-->>P: 302 redirect_to
  U->>T: site bağlantısı (kiracı host'una tam sayfa gezinme)
  T->>S: get_bootstrap (401, aynı origin)
  T->>S: platform_core.api.auth.get_login_url
  S-->>U: 302 Keycloak authorize (client site-kiraci)
  K-->>U: 302 kod, platform_core.api.auth.keycloak_callback
  S->>K: token + userinfo
  S->>S: (iss, sub) ile Website User eşle (G-120), host'a bağlı sid + csrf_token (G-45)
  S-->>T: get_bootstrap (G-63, aynı origin)
```

**Kayıt — yalnızca deneme akışı (G-79, G-31)**

```mermaid
sequenceDiagram
  autonumber
  participant U as Ziyaretçi
  participant P as Panel SPA
  participant K as Keycloak
  participant IS as identity-sync
  participant PR as Press / press_tr
  U->>P: Ücretsiz dene
  P-->>U: 302 /realms/platform/protocol/openid-connect/registrations (client press)
  U->>K: kayıt formu (markalı tema G-80), e-posta doğrulama
  K-->>IS: Event Listener: REGISTER, VERIFY_EMAIL
  IS->>K: Admin API: Organization oluştur, kullanıcıyı ekle
  IS->>PR: press_tr.api.identity.ensure_team(sub, email, org_id)
  U->>P: Giriş akışı (adım 1-9)
  P->>PR: press_tr.api.trial.start(product)
  PR->>IS: site adı
  IS->>K: Admin API: client site-kiraci + secret
  IS->>PR: secret, Site Config keycloak_client_secret (Password, G-39)
  PR->>PR: Product Trial Request, site Active, Keycloak istemcisi açılır
  PR-->>P: Agent Job realtime, yönlendirme
```

**Çıkış — RP-initiated + back-channel (G-58)**

```mermaid
sequenceDiagram
  autonumber
  participant U as Kullanıcı
  participant P as Panel SPA
  participant S as Kiracı sitesi
  participant K as Keycloak
  participant PR as Press
  U->>P: Çıkış
  P->>S: /api/method/logout
  S->>S: platform_core on_logout: id_token_hint oku, oturumu kapat
  S-->>P: end_session URL
  P-->>U: 302 /protocol/openid-connect/logout?id_token_hint&post_logout_redirect_uri
  K->>S: back-channel logout_token, platform_core.api.keycloak_backchannel_logout, clear_sessions
  K->>PR: back-channel logout_token, press_tr karşılığı
  K-->>U: 302 post_logout_redirect_uri (panel giriş)
```

## 3. Belirteç doğrulama stratejisi

| Çağıran → Hedef | Belirteç | Doğrulayan | Denetlenen |
| --- | --- | --- | --- |
| SPA → kiracı site / Press | Host'a bağlı Frappe `sid` (Secure, HttpOnly, SameSite=Lax) + `X-Frappe-CSRF-Token` | Frappe oturum katmanı | aynı origin; CORS yok (G-119, G-45) |
| Agent → kiracı site | Kiracı sitesinin oturumdan bastığı kısa ömürlü aracı belirteci (G-148, K-25) | platform\_core `auth_hooks` (G-59) | imza, `aud` (agent + site), `exp` (dakikalar), `jti` tek kullanım ve iptal, kapsam; kullanıcı `(iss, sub)` ile |
| Agent → Press | Press OAuth Bearer Token (authorization code + PKCE) | Frappe `validate_oauth` (G-28) | Press OAuth Client, kullanıcıya bağlı, kısa ömür |
| Keycloak → site/Press/`ops-bff` | `logout_token` | platform\_core / press\_tr / `ops-bff` (G-58) | JWKS, `events`, `sid`/`sub`; `ops-bff`'de `logout_token` ya da yenileme hatası BFF oturumunu ve elindeki Keycloak ve değiştirilmiş belirteçleri hemen düşürür, Press anahtarı o oturumda kullanılmaz; çıkıştan 60 sn içinde BFF çağrısı 401. Keycloak düğümleri `operator.` back-channel logout yoluna Tailscale üzerinden erişir: Tailscale ACL Keycloak düğümlerinden yalnız `operator.` HTTPS servisine (443) izin verir, yol kısıtı (yalnız back-channel logout) ters vekil/BFF yol izin listesindedir (ağ sahibi DevOps sorumlusu; rc kabulünde sınanır, sunucu değişikliği bu belgeyle yapılmaz) |
| identity-sync → Press/platform\_core | client credentials JWT; kiracıya giden belirteçte `scope` ile yalnız o kiracının audience kapsamı (G-82) | press\_tr / platform\_core `auth_hooks` (G-59) | `azp=identity-sync`, `aud` yalnız hedefin istemcisi (`press` ya da `site-<kiracı>`; ikisi de `scope` ile istenen varsayılan olmayan kapsamdan), IP allowlist (G-81) |
| Servisler → Keycloak Admin/Token API | client credentials | Keycloak | service account rolleri `manage-users`, `manage-clients`, `view-organizations`; bu roller yalnız Admin API için alınan ayrı belirteçte (G-82) |
| Operatör → `ops-bff` (giriş) | Authorization code + PKCE (S256); Keycloak SSO oturumu varsa etkileşimsiz; dönüş adresi `operator.` üzerinde | `ops-bff` (kod sunucuda değişir) | `platform-operator` grubu ve MFA (SA-1); erişim ve yenileme belirteci yalnız BFF sunucu oturumunda tutulur ve orada yenilenir (G-78, G-148); tarayıcıda yalnız HttpOnly oturum + CSRF (G-119); çıkış G-58 |
| Operatör BFF'i (`ops-bff`) → Press | operatör başına Press API key/secret + `X-Press-Team` | Press | Keycloak operatör rolü → Press hesabı eşlemesi; her çağrı Operator Audit'te (SA-1, SA-25) |
| Operatör BFF'i (`ops-bff`) → operasyon sitesi (Müşteri 360 okuması) | Operatörün belirteci çağrı başına standart token exchange V2 ile yalnız `site-ops` audience'lı kısa ömürlü belirtece çevrilir | platform\_core `auth_hooks` (G-59) | `azp=ops-bff`, `aud` yalnız `site-ops`; `(iss, sub)` ile operasyon sitesi kullanıcısı ve rolleri (G-120, SA-3, SA-24) |
| Press → kiracı site (Support Session aç/kapat) | `press-service` client credentials JWT; `scope` ile yalnız o kiracının audience kapsamı (G-82) | platform\_core `auth_hooks` (G-59) | `azp=press-service`, `aud` yalnız bu site, kapsam yalnız Support Session yaşam döngüsü, `exp` |
| Operatör BFF'i (`ops-bff`) → kiracı site (destek bileti, Support Session içinde salt okur görünüm) | Aynı mekanizmayla yalnız `site-<kiracı>` audience'lı kısa ömürlü belirteç (`sub` = operatör) | platform\_core `auth_hooks` (G-59) | `azp=ops-bff`, `aud` yalnız bu site, `(iss, sub)` aktif ve rızalı Support Session'daki operatör, kapsam, `exp`; oturum yoksa ret; kiracı API oturumu açılmaz, ekran durumu Hocuspocus odasından gelir (SA-43) |
| Tarayıcı → Hocuspocus | Kiracı sitesinin bastığı tek kullanımlık bilet (G-148): müşteri kendi site oturumuyla, operatör `ops-bff` üzerinden alır | Hocuspocus `onAuthenticate` → platform\_core | bilet, oda, aktif Support Session ve kapsam; Origin bilet türüne bağlı (müşteri: basan kiracının kayıtlı origin'leri; operatör: yalnız `operator.`); iptalde bağlantı sunucudan kapanır (SA-42) |

Servis JWT'leri için JWKS 10 dakika önbelleklenir ve bilinmeyen `kid` görülünce yenilenir; saat toleransı 30 sn; tüm servis belirteçleri kısa ömürlü ve audience kısıtlıdır (G-82).

**Audience daraltma (doğrulandı: Keycloak 26.8.0, 2026-10-08).** Kiracının ve operasyon sitesinin audience'ı, Audience mapper'lı varsayılan olmayan kapsam `scope` ile istenmedikçe belirtece girmez; bu istemcilerde istemci rolü tanımlanmadığı için Audience Resolve da eklemez ([audience](https://www.keycloak.org/docs/26.8.0/server_admin/index.html#_audience_hardcoded)); client credentials isteği de `scope`'u uygular ([kod](https://github.com/keycloak/keycloak/blob/4246609cf2024c85016d3fb1254c3d2533367c31/services/src/main/java/org/keycloak/protocol/oidc/grants/ClientCredentialsGrantType.java#L105-L132)). Standart token exchange V2 yalnız confidential ve bu özelliği açık istemciye açıktır; istekte bulunan istemci subject token'ın `aud` değerinde olmalıdır, kendi belirtecini değiştiren istemci bundan muaftır; `audience` parametresi yalnız süzer, ekleme `scope` ile yapılır; değiştirilen erişim belirteci subject token iptal edilince iptal olmaz ([token exchange](https://www.keycloak.org/securing-apps/token-exchange#_standard-token-exchange-details)). `ops-bff` operatörün kendi belirtecini değiştirir; `scope` (hedefin kapsamı) ve `audience` (hedefin istemcisi) birlikte verilir, sonuçta `aud` tek değerdir. Servis belirteci tek `aud` taşır: servis hesabına kendi işi dışında istemci rolü atanmaz, `identity-sync`'in Admin API rolleri yalnız Admin API için istenen ayrı kapsamdadır ve kiracıya giden belirtece girmez; varsayılan kapsamlarda audience eşleyicisi yoktur; `identity-sync`'in Press'e giden belirtecindeki `press` audience'ı da `scope` ile istenen varsayılan olmayan kapsamdandır. Başka audience taşıyan belirteci site reddeder (G-59); rc kabulünde her servis belirtecinde `aud` tek değerdir (G-82, SA-40). Kiracı sayısıyla büyüyen kapsam listesinin belirteç üretim süresine etkisi rc ortamında ölçülür (doğrulanacak).

## 4. Provizyon — identity-sync (G-81)

- Kaynak: Keycloak Event Listener SPI (webhook eklentisi; eklenti seçimi doğrulanacak) + elle başlatılan admin event okuma yedeği (zamanlanmış iş yok, backend D-6 ve O-11); olaylar REGISTER, VERIFY\_EMAIL, UPDATE\_EMAIL, DELETE\_ACCOUNT, admin USER create/update/delete, `ORGANIZATION_MEMBERSHIP` (doğrulanacak).
- Hedefler: `press_tr.api.identity.*` (Team/üyelik, `remove_team_member`), `platform_core.api.identity.provision` (Website User, `role_profiles`, `enabled`), Admin API ile `site-<kiracı>` client yaşam döngüsü ve secret'ın Site Config'e Password olarak yazımı (G-39, G-112).
- E-posta değişikliği yalnızca identity-sync üzerinden `rename_doc('User')` ile uygulanır; Keycloak self-service e-posta alanı kapalıdır (G-57). Silme/devre dışı → tüm sitelerde `User.enabled=0` + Press üyeliği kaldırma (X-11).
- Idempotent, yeniden denemeli, ölü-mektup kuyruğu, elle başlatılan mutabakat (Keycloak ↔ Press ↔ kiracı kullanıcı farkı raporu. Zamanlanmış iş yok, backend D-6).
- Davet: `press_tr.api.team.invite` → Admin API kullanıcı/Organization üyeliği + `execute-actions-email` (UPDATE\_PASSWORD, CONFIGURE\_TOTP) + Press Team üyeliği + kiracı provizyonu (G-16, G-79).
- MFA işareti: identity-sync, Press Role `admin_access`/`allow_billing` ve Frappe 'Tenant Admin' atamalarını kullanıcı özniteliği `mfa_required=true` olarak yazar; tarayıcı akışında "Condition - User Attribute" ile koşullu OTP/WebAuthn alt akışı (doğrulanacak). Operatör grubunda MFA her zaman zorunludur (SA-1).

## 5. Rol eşlemesi (X-10)

| Katman | Doğruluk kaynağı | Keycloak'tan taşınan |
| --- | --- | --- |
| Kimlik, MFA, oturum, Organization üyeliği | Keycloak | `sub`, `email`, `email_verified`, `organization` |
| Abonelik/fatura/site yetkisi | Press Role bayrakları (G-16) | yalnızca Team eşlemesi |
| Veri yetkisi | Frappe Role Profile + Access Rule + permlevel (G-60..G-62) | yalnızca kullanıcı kimliği |
| Sidebar ve MCP araç listesi | kiracı `has_permission` (G-94, G-85) | — |
| Operatör modu | Keycloak `ops-*` realm rolleri → Press hesabı + operasyon sitesi rolleri (SA-1) | `ops-*` rolleri (yalnız `platform-operator` grubu) |

Realm rolleri yalnızca servis hesapları ve `platform-operator` grubu için tanımlanır; iş rolleri Press ve kiracı sitede yaşar.

## 6. Press SSO (G-12)

Social Login Key: provider 'Keycloak', `custom_base_url=1`, `base_url=https://api.login.atonota.net/realms/platform`, `/protocol/openid-connect/{auth,token,userinfo}`, `auth_url_data {response_type: code, scope: openid}`, `sign_ups='Allow'`, `user_id_property='sub'`. press\_tr `before_request`: `press.api.account.signup/send_otp/verify_otp/send_login_link/login_using_key/reset_password/enable_2fa/verify_2fa` ve `product_trial.send_verification_code_for_login` → 403; `/login`, `/signup`, `/dashboard/login` → panel. MFA Keycloak'ta, Press User 2FA zorunluluğu kapalı (G-78). Agent delegasyonu Press OAuth Client ile (G-28).

## 7. Realm politikaları (G-43, G-78, G-80)

Sertleştirme (G-144): yönetim konsolu ve Admin REST API public host'ta reverse proxy'de kapalı (ayrı `hostname-admin` tek başına yetmez; doğrulandı: Keycloak hostname rehberi), anonim dinamik istemci kaydı kapalı, redirect URI'leri tam adres, kullanılmayan özellikler (JWT Authorization Grant, stateless mod) kapalı, her minor sürüm Upgrading Guide ile rc ortamında. Politikalar: Login with email, Verify email Required, brute force detection (5 deneme / 300 sn), parola ≥12 + geçmiş + yaygın parola listesi, TOTP + WebAuthn/passkey, oturum süreleri 9. bölümdeki O-25 değerleridir (kiracı boşta 1 saat ve toplam 24 saat, Press 7 gün ve 30 gün), access token 5 dk, refresh token rotation, Remember me kapalı. Tema: Keycloak'ın kendi tema yapısıyla kurulur. Tema `keycloak.v2` temasından türer. Renk ve yazılar CSS değişkeniyle verilir (backend O-4). Keycloakify, panelin tasarım tokenları hazır olunca yeniden değerlendirilir. Giriş sayfası ve panel tasarım tokenlarını bugün iki ayrı dosyada tutar. Bu bir backend borcudur: bir dosyadaki değer değişince öteki eski kalabilir. Türkçe birinci dil, 320 px kabul, Playwright E2E (X-16).

## 8. HA kurulum ve sahipler (G-76)

| İş | Sahip |
| --- | --- |
| 2 Keycloak düğümü (26.x, Docker Engine), Infinispan küme, PostgreSQL streaming replika (sürüm Keycloak uyumluluk matrisinden, doğrulanacak), nginx TLS, admin konsolu yalnızca Tailscale/özel ağ | DevOps sorumlusu |
| `api.login.atonota.net` için A ve AAAA kaydı. alpha, beta ve rc için ad `api.login.<ortam>.atonota.net` olur (K-61). Değerleri DevOps sorumlusu hazırlar. Alan adı sorumlusu kaydı `atonota.net` bölgesine yazar. | DevOps sorumlusu / alan adı sorumlusu |
| Günlük şifreli PostgreSQL yedeği (fsn1 → nbg1), haftalık realm export, RPO ≤ 1 saat (WAL), çeyreklik geri yükleme tatbikatı (G-114) | DevOps sorumlusu |
| Login/admin event'leri Log Server'a (KVKK/5651 saklama, G-117), metrikler Monitor Server'a (X-05) | DevOps sorumlusu |
| identity-sync konteyneri, sırlar age/sops (G-112) | DevOps sorumlusu |
| Realm/client/Organization tanımları realm JSON + identity-sync kodunda sürümlü | platform ekibi |

**Kabul (P0/P1/P2):** Keycloak HA ve public host'ta yönetim uçlarının kapalı olması (P0); Keycloak ile Press'e giriş ve `(iss, sub)` eşleme testleri (P1); özel alan adında giriş-çıkış (P2, G-124); test kiracısında etkileşimsiz SSO; panel çıkışı sonrası Keycloak account console'da oturum yok; 'Sign out all sessions' sonrası Frappe 60 sn içinde 401; davet edilen kullanıcı tek hesapla panel, Press ve kiracı sitede oturum açar; e-posta değişikliği yalnızca identity-sync yoluyla; bir Keycloak düğümü kapatıldığında giriş kesintisiz.

## 9. Oturum süreleri

İlk sürümde kiracı sitesi ve telefon paketi herkese çalışan oturum sürelerini uygular. Keycloak bu istemcilerde çalışan süre profili olan `employee` düzeyini ister. Müşteri oturum süresi yalnız Press için geçerlidir.

| Ayar | Kiracı sitesi ve telefon | Press |
| --- | --- | --- |
| Boşta kalma sınırı | 1 saat | 7 gün |
| Toplam oturum süresi | 24 saat | 30 gün |
| Erişim belirteci süresi | 5 dakika | 5 dakika |

Telefon paketi arka planda 2 dakika sonra kilitlenir. Paket internetsiz erişimi 24 saat açık tutar. Tarayıcıdan kurulan uygulamada bu süre 8 saattir. Frappe çerezi boşta 1 saat sonra kapanır. Uygulama çıkıştan sonra taslakları 7 gün saklar.

Arka plan eşitlemesi oturumu uzatmaz. Süre dolunca uygulama eşitlemeyi durdurur ve Keycloak ile yeniden giriş ister.

Oturum sürelerini proje kaydı O-25 ve sözleşmenin 2. ve 3. bölümleri belirler.

## 10. Hesap silme

Müşteri deneme kaydında hesabını açabilir. Çalışan hesabını davetle açar. Hesap silme ilk sürümün kapsamındadır.

1. Müşteri Press'te silme isteği verir. Keycloak'taki silme bağlantısı bu sayfaya gider. Keycloak'ın kendi hesap silme eylemi kapalıdır.
2. Press, müşteriyi Keycloak'ta yeniden doğrular. identity-sync, 5 dakikadan eski doğrulamayı reddeder.
3. identity-sync isteği kaydeder ve Keycloak hesabını kapatır.
4. identity-sync Press hesabını kapatır. API anahtarları geçersiz olur.
5. identity-sync kiracı hesaplarını kapatır. Telefon kurulumları ve bildirim bağları silinir.
6. Sistem iş kayıtlarındaki kişiyi gösteren alanları anonim yapar. Örneğin izin talebi kalır, çalışanın adı silinir. Faturalar kesildikleri hâliyle saklanır.
7. identity-sync Keycloak hesabını siler. Sistem istek kaydını anonim yapar.

Sistem kimliğin ham değerini siler. Hesabın yeniden açılmasını önlemek için yalnız HMAC özetini saklar. HMAC, gizli anahtarla hesaplanan bir özettir.

Kullanıcı takımın tek üyesiyse sistem takımı kapatır. Sistem siteleri askıya alır ve silmez.

Bir adım başarısız olursa istek hata kuyruğuna girer. Operatör isteği elle yeniden dener. Sistem tamamlanan adımları tekrarlamaz.

Hesap silme sırasını proje kaydı O-27 ve sözleşmenin 7. bölümü belirler.
