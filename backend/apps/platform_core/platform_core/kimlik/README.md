# Kimlik modülü

Bu modül kiracı sitesinde Keycloak ile girişi ve çıkışı kurar. Servis belirtecini doğrular. identity-sync için kullanıcı uçlarını verir. Sahibi platform-core-kimlik işidir. Uçların sözleşmesi `backend/contracts/platform_core-kimlik.openapi.yaml` dosyasındadır.

## Dosyalar

| Dosya | İşi |
| --- | --- |
| `helpers.py` | Frappe'ye bağlı olmayan yardımcılar. Adres üretir, yönlendirmeyi denetler. |
| `site_settings.py` | Site ayarlarını okur. Eksik ayarı açık hatayla bildirir. |
| `provider_setup.py` | Keycloak için “Social Login Key” kaydını kurar. İki kez çalışınca zarar vermez. |
| `sign_in.py` | `on_social_login` kancası. Kullanıcıyı `(iss, sub)` çiftiyle doğrular. |
| `sign_out.py` | Çıkış ve Keycloak arka kanal çıkışı. |
| `service_token.py` | `auth_hooks` kancası. Servis belirtecini `oidc_verify` ile doğrular. |
| `provisioning.py` | identity-sync için kullanıcı açma, kapatma ve e-posta değiştirme. |
| `login_policy.py` | Parola girişini kapatan kapı ve portal sayfalarının kapatılması. |
| `hooks_fragment.py` | `hooks.py` dosyasına eklenecek satırlar. |
| `doctype/platform_identity_link/` | Kimlik bağı kaydı. `issuer` ve `subject` çifti tekildir. |

## Site ayarları

Ayarlar `site_config.json` dosyasında durur. Sır depoya girmez.

| Anahtar | Zorunlu | Açıklama |
| --- | --- | --- |
| `keycloak_public_url` | Evet | Tarayıcının gördüğü Keycloak adresi |
| `keycloak_internal_url` | Hayır | Sunucunun ulaştığı adres. Boşsa genel adres kullanılır. |
| `keycloak_realm` | Hayır | Varsayılan `platform` |
| `keycloak_client_id` | Evet | Bu sitenin istemcisi, örneğin `site-kiraci1` |
| `keycloak_client_secret` | Evet | İstemci sırrı |
| `kimlik_marka_adi` | Evet | Düğme metni bundan üretilir, örneğin `Atonota` |
| `platform_panel_url` | Evet | Çıkıştan sonra dönülen adres |
| `kimlik_yalniz_keycloak` | Hayır | `1` ise parola girişi ve e-posta bağlantısıyla giriş kapanır |
| `kimlik_servis_azp` | Hayır | Servis belirtecinde izinli `azp` listesi. Varsayılan `["identity-sync"]` |

## Kurulum adımı

Site ayarlarını yazdıktan sonra şu komut “Social Login Key” kaydını kurar:

```bash
bench --site <site> execute platform_core.kimlik.provider_setup.ensure_social_login_key
```

Aynı iş HTTP ile de yapılır. Uç `platform_core.api.auth.setup_keycloak_login` olur. Yalnız System Manager çağırır.

Komut iki kez çalışınca zarar vermez. Kayıt adı `keycloak` kalır. Görünen ad `kimlik_marka_adi` ayarından gelir.

## Yalnız Keycloak ile giriş

Keycloak girişi yöneticide de çalışınca parola girişini kapatın. Önce bir System Manager kullanıcısının Keycloak bağının çalıştığını deneyin. Sonra şu komutu çalıştırın:

```bash
bench --site <site> set-config kimlik_yalniz_keycloak 1
```

Bu ayar açıkken şunlar reddedilir:

- `/api/method/login` ile parola girişi,
- `frappe.www.login.send_login_link` ve `login_via_key` ile e-posta bağlantısı girişi.

Keycloak dönüş ucu etkilenmez.

### Geri açma yolu

Yönetici erişimi kaybolursa sunucu kabuğundan ayarı kapatın:

```bash
bench --site <site> set-config kimlik_yalniz_keycloak 0
```

Ayar kapanınca parola girişi hemen açılır. Yeniden başlatma gerekmez.

## Bilinen sınırlar

- Çıkış adresinde `id_token_hint` yoktur. Frappe'nin hazır girişi kimlik belirtecini saklamaz. Keycloak çıkış onay ekranı gösterebilir.
- Arka kanal çıkışında `sid` eşleşmezse kullanıcının bütün oturumları kapanır. Bu, güvenli tarafta kalan seçimdir.
- Servis belirteci yalnız `platform_core.api.identity.*` yollarında kabul edilir. Başka uçta Bearer başlığı 401 alır.
