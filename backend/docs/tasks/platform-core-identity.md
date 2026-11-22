# İş: platform-core-kimlik

Bu iş kiracı sitesinde Keycloak ile girişi ve çıkışı kurar. Servis belirtecini doğrular ve kullanıcı açma uçlarını yazar. Düğme metni “Atonota ile oturum aç” olur.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJECT-RECORD.md`
3. `backend/docs/contracts.md`, özellikle 2, 3, 4, 5 ve 8. bölümler
4. Karar sitesinde `src/content/docs/rail-4-keycloak.md`
5. `docs/standartlar/mobile.md` içindeki AU-3, AU-4, AU-5 ve AU-19 kuralları

## Sahip olduğunuz yerler

- `backend/apps/platform_core/platform_core/identity/`
- `backend/apps/platform_core/platform_core/api/__init__.py`, `api/auth.py`, `api/identity.py`
- `backend/contracts/platform_core-identity.openapi.yaml`
- `hooks.py` içinde yalnız bu işin satırları

## Önkoşullar

- `platform_core` iskeleti dev-ortam işinden gelir.
- Keycloak realm'i ve `oidc_verify` kitaplığı kimlik-realm işinden gelir.
- Orkestratör bunları `backend` dalına birleştirdikten sonra bu iş başlar.

## Kontrol noktası 1: giriş ve çıkış

1. Önce OpenAPI sözleşmesini yazın. Her uca özet ve açıklama verin (D-9).
2. `Platform Identity Link` DocType'ını yazın. Her alana açıklama verin. `issuer` ve `subject` çiftini veritabanında tekil yapın (V-8).
3. Keycloak için “Social Login Key” kaydını site ayarından kuran bir kurulum adımı yazın. Adım iki kez çalışınca zarar vermesin (V-7).
   - `user_id_property` değeri `sub` olsun.
   - `sign_ups` değeri `Deny` olsun.
   - Görünen ad `kimlik_marka_adi` ayarından gelsin.
4. Girişte kullanıcıyı `(iss, sub)` çiftiyle bulun. Frappe 16'daki `on_social_login` kancasını kaynakta doğrulayın ve kullanın (AU-4).
   - İlk bağı yalnız doğrulanmış e-postayla kurun.
   - Bağ farklıysa oturum açmadan reddedin.
5. `get_login_url` ucunu yazın. `state` değeri sunucuda üretilsin. `redirect_to` yalnız aynı kökende göreli yol olsun.
6. Keycloak `sid` değerini Frappe oturumuyla eşleştirin.
7. Çıkış uçlarını yazın:
   - `logout` Frappe oturumunu kapatır ve Keycloak çıkış adresini döner.
   - `keycloak_backchannel_logout` çıkış belirtecini `oidc_verify` ile doğrular ve eşleşen oturumları kapatır.
8. Testleri önce yazın. Testler HTTP isteğiyle şunları göstersin:
   - doğru kullanıcı giriş yapar,
   - doğrulanmamış e-posta ilk bağı kuramaz,
   - farklı `sub` aynı e-postayla giremez,
   - geçersiz çıkış belirteci reddedilir,
   - geçerli çıkış belirteci oturumu kapatır.
9. Canlı Keycloak ile bütünleşme testini yazın.
10. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: servis belirteci ve kullanıcı uçları

1. `auth_hooks` kancasıyla servis belirtecini doğrulayın. Kuralları sözleşmenin 3. bölümü verir.
2. `identity.provision`, `identity.set_enabled` ve `identity.change_email` uçlarını yazın. Uçlar yalnız `identity-sync` belirtecini kabul etsin.
3. Açılan kullanıcı “Website User” olsun (O-3). Masaüstü erişimi açık rol verilmesin (G-16).
4. Son kullanıcıya hazır portal sayfalarını kapatın (O-3).
5. Keycloak girişi yöneticide de çalışınca Frappe'nin parola girişini ve e-posta bağlantısıyla girişi kapatın (AU-19). Kapatmayı bir ayarla yapın. İki girişin reddedildiğini sınayın. Yönetici erişimini kaybetmeyin. Geri açma yolunu README'ye yazın.
6. Testler şunları göstersin:
   - yanlış `aud`, yanlış `azp`, süresi dolmuş ve imzasız belirteç reddedilir,
   - aynı istek iki kez gelince sonuç değişmez,
   - son kullanıcı yönetim ekranına giremez.
7. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Keycloak realm'i kimlik-realm işinindir. Değişiklik gerekirse raporda isteyin.
- Belirteç doğrulamayı kendiniz yazmayın. `oidc_verify` kitaplığını kullanın.
- Ekran ve tema bu işte yoktur.
