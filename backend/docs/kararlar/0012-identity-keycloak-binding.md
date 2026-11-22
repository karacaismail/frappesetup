# Karar notu 0012: kiracı sitesinin Keycloak bağı

Tarih: 22 Kasım 2026 Pazar. Sahibi: platform-core-kimlik işi. Bu not platform-core-kimlik dalının seçimlerini anlatır. Orkestratör birleştirmede gözden geçirir.

## İhtiyaç

Kiracı sitesinin kullanıcısı Keycloak ile oturum açar. Kullanıcının kalıcı anahtarı `(iss, sub)` çiftidir. Çıkış Keycloak'tan arka kanalla gelir. identity-sync servisi kullanıcıyı servis belirteciyle açar. Telefon uygulaması mobil belirteçle gelir.

## Seçenekler

| Konu | Seçenek A | Seçenek B | Seçim |
| --- | --- | --- | --- |
| Dönüş ucu | Frappe'nin hazır `login_via_keycloak` ucu | Kendi `keycloak_callback` ucumuz | B |
| `state` bağlama | Frappe önbelleği, tarayıcıya bağsız | Tarayıcı çerezi özeti, PKCE S256, `nonce`, tek bölünmez okuma | B |
| Oturum eşlemesi | `tabSessions` metninde LIKE araması | Redis'te `sid` dizini, yedek olarak `sub` | B |
| Servis belirtecinin kullanıcısı | Ayrı servis kullanıcısı | `Administrator`, yalnız servis uçlarında | B |
| Yerel giriş kapısı | Adres denetimi | `override_whitelisted_methods` ile işlev denetimi | B |
| “Social Login Key” | Açık, Frappe düğmesi çalışır | Kapalı, yalnız istemci bilgisi | B |

## Gerekçeler

1. **Kendi dönüş ucu.** Frappe'nin hazır ucu `state` değerini tarayıcıya bağlamaz (`frappe/utils/oauth.py:98`). Kimlik belirtecini de saklamaz. Bu yüzden `sid` bulunamazdı. Kendi ucumuz çerez özetini doğrular, kodu PKCE ile değiştirir ve kimlik belirtecini `oidc_verify.verify_id_token` ile denetler. Güvenlik incelemesi (E1) bunu zorunlu buldu.
2. **Tek bölünmez `state` okuması.** Kayıt Redis `GETDEL` ile okunur ve silinir. İki eşzamanlı dönüş aynı kaydı alamaz.
3. **Dizinli oturum eşlemesi.** Keycloak `sid` değeri Redis'te Frappe oturum kimliklerine eşlenir. Anahtar oturum süresi kadar yaşar. Dizin kaybolursa `sub` yedeği devreye girer. Yedek yalnız belirtecin `iat` değerinden önce açılmış oturumları kapatır. Aynı `jti` ikinci kez kabul edilmez.
4. **Servis belirteci yönetici kimliğiyle yürür.** Frappe, Bearer başlığı taşıyan isteği kullanıcı Guest kalırsa 401 ile keser (`frappe/auth.py:649`). Kanca bir kullanıcı koymak zorundadır. Ayrı servis kullanıcısı MVP için fazla katman olurdu (M-3). Yol kısıtı belirteci servis uçlarına hapseder. Bu uçlar dört identity ucu ve mobil işinin `revoke_user_installations` ucudur.
5. **Kapı işleve uygulanır.** Adres denetimi `cmd` alanı ve `/api/v2/method` biçimleriyle aşılıyordu (inceleme E2). `override_whitelisted_methods` kancası Frappe'nin kendi yoludur (`frappe/__init__.py:1577`).
6. **Kayıt kapalı.** Frappe'nin düğmesi bu uygulamanın bilmediği bir `state` gönderirdi. Kayıt yalnız istemci bilgisini tutar. Giriş sayfası bizim `www/login` sayfamızdır.
7. **Mobil belirteç.** Telefon uçları aynı `auth_hooks` kancasından geçer. Kanca `platform_core.api.mobile.v1_*` yollarında mobil belirteci kabul eder. Kurallar servis belirteciyle aynıdır. Ek olarak `mobile` kapsamı ve `(iss, sub)` bağı aranır. Sonuç `frappe.local.mobile_identity` içinde durur.

## Bilinen sınırlar ve geri dönüş

- Çıkış adresinde `id_token_hint` yoktur. Kimlik belirteci saklanmaz.
- Redis dizini kaybolursa çıkış `sub` yedeğiyle çalışır. Bu durumda kullanıcının eski oturumlarının hepsi kapanır.
- Geri dönüş: `kimlik_yalniz_keycloak` ayarı kapatılınca Frappe'nin yerel girişi açılır. Kendi dönüş ucu kaldırılırsa Frappe'nin hazır ucu yeniden kullanılabilir. O zaman E1 bulgusu geri gelir.

## Bağımlılıklar

- `oidc_verify` kitaplığı `backend/libs/oidc_verify` klasöründedir. Sahibi kimlik-realm işidir. Kitaplığın `JwksUnavailable` sınıfını dışa açması ve çıkış belirtecinde `exp`, `jti` ve olay türünü zorunlu tutması istendi.
- `requests` Frappe 16 ile gelir.
- Realm'deki `site-kiraci1` istemcisinin dönüş adresi `<kiracı adresi>/api/method/platform_core.api.auth.keycloak_callback` olmalıdır.
