# AtonotA Login

AtonotA Login bağımsız bir giriş ürünüdür (G-157, O-51). Ürün Keycloak üzerinde çalışır. Keycloak'ın eksik bıraktığı işleri Frappe tamamlar.

Bu klasör ürünün kendi kodunu tutar. Kod MIT lisanslıdır (`LICENSE`). Keycloak ve eklentileri Apache-2.0 lisanslıdır. Bu parçaların listesi `THIRD-PARTY-NOTICES.md` dosyasındadır.

## Ürünün parçaları

| Yol | İçerik |
| --- | --- |
| `platforms/` | Giriş platformlarının kayıtları. Her dosya bir platformdur. |
| `atonota_login/platforms.py` | Kayıtları denetler ve Keycloak kaydına çevirir. |
| `atonota_login/keycloak_apply.py` | Platformları çalışan Keycloak'ta açar ya da kapatır. |
| `atonota_login/decision.py` | Bir işlemin şimdi yapılıp yapılamayacağına karar verir (G-161). |
| `atonota_login/policy/actions.json` | İşlemler, kontroller ve değer bekleyen kurallar (G-166, G-167). Dosya paket verisidir. |
| `pyproject.toml` | Paket tanımı. Kiracı imajı paketi `uv pip install --no-deps` ile kurar. |
| `atonota_login/verification_inbox.py` | Dış kimlik doğrulama bildirimlerinin gelen kutusu (G-164). |
| `bin/atonota-login` | Komut satırı aracı. |
| `tests/` | Ürünün testleri. |

Ürünün öteki parçaları `identity/keycloak/` klasöründedir. Bu klasörün adı ve yeri değişmez (karar 12). Orada realm dosyası, giriş teması, imaj ve geliştirme betiği vardır. `identity/keycloak/event-listener/` klasörü Apache-2.0 lisanslı bir çataldır.

## Giriş platformları

Platform, kullanıcının oturum açtığı dış hizmettir. Örnekler Google, Facebook, LinkedIn ve X'tir. Keycloak'ta her platform bir kimlik sağlayıcıdır.

Platform listesi veridir. Kodda platform adı yoktur. Yeni platform için şu iki adımı yapın:

1. `platforms/` klasörüne `<ad>.json` dosyası ekleyin. Örnek olarak `google.json` dosyasına bakın.
2. `bin/atonota-login render --write` komutunu çalıştırın. Komut yalnız realm dosyasının platform bölümünü yazar.

Kayıt sır taşımaz. Kayıt yalnız sırrı tutan ortam değişkeninin adını yazar. Örneğin `ATONOTA_GOOGLE_CLIENT_ID` böyle bir addır.

Platform şu kurala göre açılır:

- Bütün sır değişkenleri doluysa platform açılır. Düğmesi giriş sayfasında görünür.
- Bir değişken boşsa platform kapalı kalır. Düğmesi görünmez.
- Kayıtta `"active": false` yazıyorsa platform sırla da kapalı kalır.

Açık bir platform e-postanın doğrulandığını bildirmelidir. Kayıt bunun için `email_verified` iddiasını zorunlu kılar. Örnek `google.json` dosyasındadır. Bu kural yoksa biri başkasının e-postasıyla önceden hesap açabilir. Kişi sonra kaydolunca hesap saldırganın olur. Bu saldırıya önceden ele geçirme denir.

Kayıt güvenliği zayıflatan ayarları reddeder. Örneğin imza doğrulamasını kapatan kayıt reddedilir. Platform adresleri https kullanır. Kayıt bütün ortamlara gider. Bu yüzden yerel `http` adresi de reddedilir. Tek istisna geliştirme için yerel Keycloak'a yapılan `apply` işidir. Bu işte `--allow-local-http` seçeneği yerel `http` adresine izin verir. Canlı test bu seçeneği kullanır.

Facebook ve X bu iddiayı Keycloak'a göndermez. Bu yüzden iki kayıt `"active": false` ile gelir. İki platformu açmak için önce ek bir denetim gerekir. Borç satırı proje kaydındadır (O-56).

Açma ve kapama işini `bin/atonota-login apply --from-env` komutu yapar. Geliştirmede `identity/keycloak/bin/kc-dev.sh platforms` komutu aynı işi yapar.

Platform işini bitirince tarayıcıyı şu adrese döndürür:

```text
https://<giriş adresi>/realms/platform/broker/<platform>/endpoint
```

Giriş adresi prod'da `api.login.atonota.net` olur. alpha, beta ve rc ortamlarında adres `api.login.<ortam>.atonota.net` olur. Her ortamın adreslerini şu komut yazar:

```bash
bin/atonota-login redirects --env all
```

## Hesap bağlama kuralı

Kural G-160 gereksinimidir. Keycloak bu kuralı `atonota-first-broker-login` akışıyla uygular.

1. Dış hesap, platformun adı ve platformdaki değişmeyen kullanıcı numarasıyla bağlanır.
2. Platform e-postanın doğrulandığını bildirmezse giriş reddedilir. Hesap açılmaz.
3. Aynı e-postalı hesap yoksa yeni kullanıcı açılır. Kullanıcı e-posta adresini kendisi yazamaz.
4. Aynı e-postalı hesap varsa Keycloak kullanıcıya sorar. Kullanıcı bağlamayı onaylarsa var olan hesabın parolasıyla yeniden oturum açar.
5. E-posta eşleşmesi tek başına bağ kurmaz. E-postaya gelen bağlantı da bağ kurmaz.

Parolası olmayan kullanıcı bu yolla bağ kuramaz. Örneğin yalnız sihirli bağlantıyla giren kullanıcı böyledir. Bu kişi önce hesabına parola ekler. Bu kısıtlama bilinçlidir. Güvenli olmayan yol açılmaz.

Kuruluş kurumsal girişi zorunlu kılabilir. Bu durumda üyelik katmanı kullanıcıya `enterprise-sso-required` rolünü verir. Rolü olan kullanıcı sosyal platformla giremez.

Kurumsal sağlayıcılar kayıtta yoktur. `apply` komutu onları değiştirmez. Komut her kurumsal sağlayıcıyı şu sırayla denetler (G-160):

1. `trustEmail` açıksa komut hata verir.
2. Sağlayıcıda `email_verified` kuralı varsa sağlayıcı geçer.
3. Kural yoksa sağlayıcının onaylı bir istisna kaydı olmalıdır. Kayıt yoksa komut hata verir.
4. Sosyal platform istisna alamaz.
5. Kayıt bütün kurallara uymalıdır. Kurallar `platform_core/identity/enterprise_rules.py` dosyasındadır.
6. Kayıttaki `issuer` adresi sağlayıcının adresiyle aynı olmalıdır.
7. Kaydın bitiş tarihi geçmemiş olmalıdır.
8. İki giriş akışının adı sabit kalmalıdır.

Komut ilk hatada durur. Komut sağlayıcıyı kapatmaz. Sağlayıcıyı kapatma kararı DevOps sorumlusundadır.

İstisna kaydı Frappe'de `PLT Enterprise IdP Exception` DocType'ında durur. Kayıt onaydan sonra değişmez ve silinmez. Kayıtları DevOps sorumlusu şu iki adımla taşır:

1. `bench --site <site> execute platform_core.identity.enterprise_sync.export_exceptions --kwargs '{"path": "<dosya>"}'` komutu geçerli kayıtları dosyaya yazar.
2. `bin/atonota-login apply --from-env --enterprise-exceptions <dosya>` komutu sağlayıcıları bu dosyayla denetler.

Dosya sır taşımaz. Dosya Git'e girmez. Kalan işler proje kaydının borç satırındadır.

Bağ, ikinci adımdan ve kurumsal giriş denetiminden önce kaydedilir. Bu sıra Keycloak'ın kendi sırasıdır. İkinci adım başarısız olursa bağ yine de kalır. Bağ yine de giriş açmaz, çünkü her girişte iki denetim yeniden çalışır.

## Testler

```bash
cd backend/identity/atonota_login
python3 -I -m unittest discover -s tests -t .
```

Canlı test yerel Keycloak ister. Test sahte bir OIDC sağlayıcı kullanır. Gerçek Google hesabı gerekmez. Ayrıntı `tests/test_live_platforms.py` dosyasının başındadır.
