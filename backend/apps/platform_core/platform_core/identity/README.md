# Kimlik modülü

Bu modül kiracı sitesinde Keycloak ile girişi ve çıkışı kurar. Servis belirtecini doğrular. identity-sync için kullanıcı uçlarını verir. Sahibi platform-core-kimlik işidir. Uçların sözleşmesi `backend/contracts/platform_core-identity.openapi.yaml` dosyasındadır.

## Dosyalar

| Dosya | İşi |
| --- | --- |
| `helpers.py` | Frappe'ye bağlı olmayan yardımcılar. Adres üretir, yönlendirmeyi ve yolu denetler. |
| `site_settings.py` | Site ayarlarını okur. Eksik ayarı açık hatayla bildirir. |
| `provider_setup.py` | Keycloak için “Social Login Key” kaydını kurar. İki kez çalışınca zarar vermez. |
| `sign_in.py` | Kendi dönüş ucu: giriş adresi, tarayıcı çerezi, PKCE, `nonce`, kullanıcı eşleme. |
| `sign_out.py` | Çıkış ve Keycloak arka kanal çıkışı. Tekrar koruması vardır. |
| `service_token.py` | `auth_hooks` kancası. Servis belirtecini `oidc_verify` ile doğrular. |
| `provisioning.py` | identity-sync için kullanıcı açma, kapatma ve e-posta değiştirme. |
| `reconciliation.py` | Bağlı kimlikleri sayfa sayfa listeler. |
| `login_policy.py` | Yerel girişi kapatan kapı ve portal sayfalarının kapatılması. |
| `jwks.py` | Anahtar listesi önbelleği. |
| `session_policy.py` | Oturum 1 saat işlem olmazsa kapanır. Eski girişli çalışan yeniden kimlik doğrular (O-25). |
| `anonymization.py` | Hesap silme: kullanıcıyı kapatır ve kişi alanlarını anonim yapar (O-27, karar notu 0013). |
| `anonymization_scope.py` | Silmenin kapsamı: kişinin kendi kayıtları ile ortak kayıtları ayırır. |
| `safe_errors.py` | Kimlik, giriş ve çıkış uçlarında hata kaydına yalnız güvenli alanları yazar. |
| `exceptions.py` | Uçların hata sınıfları. Sınıf adı yanıtta `exc_type` olur. |
| `api.py` | Telefon belirtecini doğrulayan açık işlevler. |
| `atonota/verification_api.py` | Dış doğrulama bildirimini alır. İmzayı ham gövdede denetler. İşlemeyi kuyruğa verir (G-164). |
| `doctype/plt_verification_notice/` | Dış doğrulama bildirimi. Sağlayıcının olay numarası tekildir. Ham belge ve yüz verisi tutulmaz. |
| `doctype/plt_verification_case/` | Doğrulama vakası. En yeni denemeyi ve o denemenin sonucunu tutar. |
| `doctype/platform_identity_link/` | Kimlik bağı kaydı. `issuer` ve `subject` çifti tekildir. |
| `doctype/platform_identity_deletion/` | Silme kaydı. Ham kimliği değil, `(iss, sub)` çiftinin özetini tutar. |
| `../www/login.py`, `../www/login.html` | Kiracının `/login` sayfası. |
| `../public/kimlik/` | Giriş sayfasının CSS, betik ve yazı tipi dosyaları. |
| `tests/e2e/` | Giriş sayfasının Chromium ve WebKit tarayıcı testleri. |

## Giriş akışı

1. Uygulama `get_login_url` ucunu çağırır. Sunucu rastgele bir tarayıcı değeri üretir. Değer `HttpOnly` çerezde durur. Sunucu `state`, PKCE doğrulayıcısı ve `nonce` değerlerini 600 saniye saklar.
2. Tarayıcı Keycloak'ta oturum açar. Keycloak `platform_core.api.auth.keycloak_callback` ucuna döner.
3. Dönüş ucu `state` kaydını tek işlemle okur ve siler. Çerezdeki değerin özeti kayıtla eşleşmezse giriş reddedilir.
4. Dönüş ucu kodu PKCE doğrulayıcısıyla değiştirir. Kimlik belirtecini `oidc_verify.verify_id_token` ile doğrular. `nonce` değerini denetler.
5. Kullanıcı `(iss, sub)` çiftiyle bulunur. İlk bağ yalnız doğrulanmış e-postayla kurulur. Bilinmeyen e-posta ile kayıt açılmaz.
6. Frappe oturumu açılır. Keycloak oturum kimliği ve CSRF belirteci oturuma yazılır. Tarayıcı `redirect_to` yoluna döner.

Frappe'nin hazır `login_via_keycloak` ucu kullanılmaz. “Social Login Key” kaydı kapalı durur. Kayıt yalnız istemci bilgisini Frappe'nin olağan yerinde tutar.

## Site ayarları

Ayarlar `site_config.json` dosyasında durur. Sır depoya girmez.

| Anahtar | Zorunlu | Açıklama |
| --- | --- | --- |
| `keycloak_public_url` | Evet | Tarayıcının gördüğü Keycloak adresi |
| `keycloak_internal_url` | Hayır | Sunucunun ulaştığı adres. Boşsa genel adres kullanılır. |
| `keycloak_realm` | Hayır | Varsayılan `platform` |
| `keycloak_client_id` | Evet | Bu sitenin istemcisi, örneğin `site-tenant1` |
| `keycloak_client_secret` | Evet | Tarayıcı istemcisinin sırrı |
| `keycloak_service_client_id` | Servis çağrısında | Servis istemcisi. Örnek `site-tenant1-service`. |
| `keycloak_service_client_secret` | Servis çağrısında | Servis istemcisinin sırrı |
| `mcp_oauth_enabled` | İsteğe bağlı | Dış MCP erişimini açar. Bu erişim varsayılan olarak kapalıdır. |
| `mcp_oauth_resource` | Dış MCP erişiminde | MCP ucunun tam HTTPS adresi. |
| `mcp_oauth_client_ids` | Dış MCP erişiminde | İzin verilen açık Keycloak istemcilerinin kimlik listesi. |
| `mcp_oauth_introspection_secret` | Dış MCP erişiminde | Keycloak belirtecini denetleyen istemcinin sırrı. Yalnız site ayarında saklanır. |
| `mobile_identity_sync_url` | Giriş ürünü okumasında | identity-sync kök adresi. Adres HTTPS olmalıdır. Telefon oturumu kapatma da bu adresi kullanır. |
| `keycloak_organization_id` | Kullanıcı davetinde | Kiracının Keycloak kuruluş kimliği. Davet ucu bu değeri identity-sync servisine gönderir. Değer istekten gelmez. Değer boşsa davet ucu 503 döner. |
| `identity_brand_name` | Evet | Ürünün görünen adı. Düğme metni ve uyarı iletisi bu değeri kullanır. Değer `backend/brand.env` dosyasındaki `PRODUCT_NAME` değeridir. |
| `platform_panel_url` | Evet | Girişten ve çıkıştan sonra dönülen adres |
| `identity_keycloak_only` | Hayır | `1` ise Frappe'nin yerel giriş yolları kapanır |
| `identity_service_azp` | Hayır | Servis belirtecinde izinli `azp` listesi. Varsayılan `["identity-sync"]` |
| `atonota_verification_secret` | Hayır | Dış doğrulama bildiriminin imza sırrı. En az 32 bayt olur. Yalnız site ayarında saklanır. Yoksa bildirim 503 alır. |
| `kimlik_mobil_azp` | Hayır | Telefon belirtecinde izinli `azp` listesi. Varsayılan `["mobile"]` |
| `kimlik_deletion_hmac_key` | Evet | Silme kaydındaki özetin gizli anahtarı. Yoksa kimlik değiştiren uçlar 503 döner. |
| `mcp_oauth_enabled` | Hayır | Dış MCP erişimi başlangıçta kapalıdır. Açmak için `true` veya `1` yazın. |
| `mcp_oauth_resource` | Dış MCP açıksa | MCP ucunun tam HTTPS adresi. Örnek `https://tenant.example.test/api/method/platform_core.api.ai.mcp`. |
| `mcp_oauth_client_ids` | Dış MCP açıksa | İzinli Keycloak istemcilerinin kimlik listesi. Örnek `["mcp-external"]`. |
| `mcp_oauth_introspection_secret` | Dış MCP açıksa | Sunucu bu sırla Keycloak'a belirtecin hâlâ geçerli olup olmadığını sorar. |

MCP, dış araçların bu siteye bağlanmak için kullandığı bir protokoldür.
Dış MCP erişimi açıkken Keycloak adresleri HTTPS kullanır.
İzinli dış istemciler, yetki koduyla giriş yapar.
İstemci kodu S256 PKCE yöntemiyle korur.
Sunucu, belirteci denetlemek için ayrı bir Keycloak istemcisi kullanır.
Bu istemcinin kimliği MCP ucunun tam adresidir.
Belirteç tek bir hedef taşır.
Hedef ve imzalı `mcp_resource` alanı MCP adresiyle eşleşir.
Sunucu, istemci sırrını yalnız `site_config.json` dosyasından okur.

## Kurulum adımı

Site ayarlarını yazdıktan sonra şu komut “Social Login Key” kaydını kurar:

```bash
bench --site <site> execute platform_core.identity.provider_setup.ensure_social_login_key
```

Aynı iş HTTP ile de yapılır. Uç `platform_core.api.auth.setup_keycloak_login` olur. Yalnız System Manager çağırır.

Komut iki kez çalışınca zarar vermez. Kayıt adı `keycloak` kalır. Görünen ad `identity_brand_name` ayarından gelir.

Keycloak istemcisinin dönüş adresi `<site>/api/method/platform_core.api.auth.keycloak_callback` olmalıdır. Realm tanımı kimlik-realm işinindir.

## Yalnız Keycloak ile giriş

Keycloak girişi yöneticide de çalışınca yerel girişi kapatın. Önce bir System Manager kullanıcısının Keycloak bağının çalıştığını deneyin. Sonra şu komutu çalıştırın:

```bash
bench --site <site> set-config identity_keycloak_only 1
```

Bu ayar açıkken şunlar reddedilir:

- `/api/method/login` ve `cmd=login` ile parola girişi (401),
- parola sıfırlama ve güncelleme: `reset_password`, `update_password` (403),
- kayıt: `sign_up` (403),
- e-posta bağlantısıyla giriş: `send_login_link`, `login_via_key`, `login_via_token` (403),
- Frappe'nin hazır sosyal giriş uçları: `frappe.integrations.oauth2_logins.*` (403).

Kapatma çağrılan işleve uygulanır. `/api/method`, `/api/v1/method`, `/api/v2/method` ve `cmd` biçimlerinin hepsi kapsamdadır. Keycloak dönüş ucu etkilenmez.

### Geri açma yolu

Yönetici erişimi kaybolursa sunucu kabuğundan ayarı kapatın:

```bash
bench --site <site> set-config identity_keycloak_only 0
```

Ayar kapanınca yerel giriş hemen açılır. Yeniden başlatma gerekmez.

## Hesap silme sırasında bozuk geçmiş kaydını onarma

Hesap silme HTTP 417 dönebilir. Hata iletisi bir “Version” kaydının adını verirse hesap kapalı kalır. Veri temizliği tamamlanana kadar istek açık kalır.

1. Hata iletisindeki kayıt adını alın. Bu adımları yalnız yetkili yönetici uygular.
2. “Version” kaydını bulun. Kaydın belge türünü ve belge adını doğrulayın.
3. `data` alanını güvenilir bir kopyayla karşılaştırın. JSON verisi bir nesne olmalıdır. `changed` alanı varsa bir liste olmalıdır. Her satır üç değer taşımalıdır. Sıra alan adı, eski değer ve yeni değerdir. Alan adı metin olmalıdır.
4. Geçerli geçmişi koruyarak yalnız bozuk veriyi onarın. Güvenilir kopya yoksa kayıt sahibine ve veri sorumlusuna başvurun. Geçmiş değerlerini tahmin etmeyin.
5. Hesabı kapalı tutun. Eşitleme hizmetindeki bekleyen silme işini yeniden çalıştırın.
   [Yeniden çalıştırma adımları](../../../../identity/identity_sync/README.md#komutlar)
6. Silme isteğinin tamamlandığını doğrulayın. Kayıt geçmişinde eski e-posta adresini arayın.

Geçmiş verisini destek kaydına veya günlüğe kopyalamayın. Sorunu izlemek için “Version” kaydının adını kullanın.

## Bilinen sınırlar

- Çıkış adresinde `id_token_hint` yoktur. Kimlik belirteci girişten sonra saklanmaz. Keycloak çıkış onay ekranı gösterebilir.
- Arka kanal çıkışında `sid` eşleşmezse `sub` yedeği devreye girer. Yedek yalnız belirteçten önce açılmış oturumları kapatır.
- Kimlik servis belirteci beş kimlik ucunda ve `revoke_user_installations` ucunda geçerlidir.
- `list_identities` yalnız identity-sync belirtecini kabul eder. Her sayfa en çok 500 kimlik döner.
- Her satır kimliği veren sunucuyu, kullanıcı kimliğini ve hesabın açık olup olmadığını içerir.
- `identity_keycloak_only` açıkken `/login` sayfasında yalnız marka düğmesi vardır. Parola girişi yine de doğrudan çağrılırsa 401 alır.
