# Bileşenler arası sözleşmeler

Bu dosya backend bileşenlerinin ortak adlarını tutar. İşler paralel yürür. Bu yüzden herkes aynı adları kullanmalıdır. Bir adı değiştirmek gerekirse raporda isteyin. Orkestratör bu dosyayı günceller.

Ayrıntılı istek ve yanıt biçimi `contracts/` klasöründeki OpenAPI dosyalarındadır. OpenAPI, uçları tarif eden belge biçimidir. Her uç sahibi kendi dosyasını yazar:

| Dosya | Sahip iş |
| --- | --- |
| `contracts/platform_core-identity.openapi.yaml` | platform-core-kimlik |
| `contracts/platform_core-shell.openapi.yaml` | platform-core-kabuk |
| `contracts/press_tr.openapi.yaml` | press-tr |
| `contracts/identity_sync.openapi.yaml` | identity-sync |
| `contracts/platform_core-model-gateway.openapi.yaml` | platform-core-gecit |
| `contracts/platform_core-ai.openapi.yaml` | platform-core-yz |

## 1. Marka

- Kimlik markasının adı “Atonota”dır.
- Düğme metni “Atonota ile oturum aç” olur.
- Keycloak'ın üretimdeki adresi `https://id.atonota.net` olur (Proje kaydı O-1).
- Kod marka adını ve alan adını ayardan okur. Kodda sabit yazmayın.

## 2. Keycloak

### Realm ve adresler

- Realm adı `platform` olur.
- Tarayıcının gördüğü adres `keycloak_public_url` ayarıdır.
- Belirteçteki `iss` değeri `<keycloak_public_url>/realms/platform` olur.
- Sunucu Keycloak'a başka adresten ulaşacaksa `keycloak_internal_url` ayarını kullanın. Bu ayar boşsa genel adres kullanılır.
- Realm'in görünen adı “Atonota” olur. Giriş ve e-posta teması `atonota` adını taşır.
- Tema Keycloak'ın kendi tema yapısıyla kurulur (Proje kaydı O-4).
- Varsayılan dil Türkçedir. İkinci dil İngilizcedir.

### İstemciler

İstemci, Keycloak'a bağlanan uygulamadır. Bu turdaki istemciler şunlardır:

| İstemci | Tür | Akış | Dönüş adresi | Çıkış bildirimi |
| --- | --- | --- | --- | --- |
| `site-tenant1` | Gizli sırlı | Yetkilendirme kodu ve PKCE (S256) | `<kiracı adresi>/api/method/platform_core.api.auth.keycloak_callback` | `<kiracı adresi>/api/method/platform_core.api.keycloak_backchannel_logout` |
| `press` | Gizli sırlı | Yetkilendirme kodu ve PKCE (S256) | `<Press adresi>/api/method/press_tr.api.auth.keycloak_callback` | `<Press adresi>/api/method/press_tr.api.keycloak_backchannel_logout` |
| `site-tenant1-service` | Servis hesabı | İstemci kimlik bilgisi | Yok | Yok |
| `identity-sync` | Servis hesabı | İstemci kimlik bilgisi | Yok | Yok |
| `press-service` | Servis hesabı | İstemci kimlik bilgisi | Yok | Yok |
| `mobile-app` | Açık istemci | Yetkilendirme kodu ve PKCE (S256) | `ATONOTA_MOBILE_REDIRECT_URI` | Yok |

- Dönüş adresini tam adresle kaydedin. Joker karakter kullanmayın.
- Çıkış bildiriminde “oturum gerekli” ayarını açın.
- Yeni kiracı için aynı biçimi kullanın. Örneğin `site-kiraci2` yazın.
- Her kiracının iki istemcisi vardır. `site-<kiracı>` yalnız tarayıcı girişi içindir. Servis hesabı kapalıdır ve isteğe bağlı servis kapsamı taşımaz. `site-<kiracı>-service` yalnız servis hesabıdır. Tarayıcı akışı kapalıdır. Kiracının iki istemcisi içinde `aud-identity-sync` kapsamını yalnız servis istemcisi isteyebilir. Böylece tarayıcı girişi servis hedefli belirteç alamaz. Press'teki `press` ve `press-service` ayrımı da böyledir.
- `agent-service`, `ops-bff` ve `site-ops` bu turda yoktur.

### Hedef kapsamları

Hedef kapsamı, belirtece tek bir `aud` değeri ekleyen isteğe bağlı kapsamdır. `aud`, belirtecin hangi uygulama için olduğunu söyler.

| Kapsam | Eklediği `aud` | Kullanan |
| --- | --- | --- |
| `aud-site-tenant1` | `site-tenant1` | `identity-sync`, `press-service`, `mobile-app` |
| `aud-press` | `press` | `identity-sync` |
| `aud-identity-sync` | `identity-sync` | Kiracı sitelerinin servis istemcileri ve `press-service`. Örnek: `site-tenant1-service` |

- Bu kapsamlar varsayılan değildir. İstekte `scope` ile istenir.
- Servisler her uygulama isteği için tek hedef kapsamı ister. Keycloak birleşik kapsam isteğinde birden çok hedef verebilir. Alıcı, birden çok hedef taşıyan belirteci `wrong_audience` ile reddeder. Ayrı yönetim belirteci aşağıdaki kurala uyar.
- Admin API yetkileri kiracıya giden belirtece girmez.
- `identity-sync` Admin API belirtecini ayrı ister. İstekte `scope=admin-api kc-admin-api` olur. Bu belirtecin `aud` değeri `realm-management` ve Admin API adresidir. Keycloak 26.8 Admin API'si bu kapsamı ister.
- `press-service` istemcisi `aud-press` kapsamını isteyemez. Keycloak bu isteği `invalid_scope` ile reddeder.
- `identity-sync` servis hesabı davet ve kuruluş hazırlama için Keycloak'a yazar. Bu yüzden şu rolleri taşır: `view-users`, `query-users`, `manage-users`. Kuruluş ve üyelik için gereken en az ek rol Keycloak 26.8 kaynağında doğrulanır ve realm dosyasına yazılır.
- Bu roller yalnız `scope=admin-api kc-admin-api` ile istenen belirtece girer. Kiracıya ve Press'e giden belirteç bu rolleri taşımaz. Canlı test bunu sınar: kiracı hedefli belirteç Admin API'de reddedilir. Keycloak 26.8.2 bu durumda 401 döner, çünkü önce belirtecin hedefini denetler. Test 401 ya da 403 kabul eder, 2xx kabul etmez.
- Sihirli bağlantı eklentisinin bağlantı üreten yönetim ucu kapalıdır. Bu uç, belirteçteki rolü değil hesabın kayıtlı rolünü denetliyordu. Kapalı olduğu canlı testle (404) gösterilir.

### Politikalar

Keycloak giriş sayfası çerçeve içinde açılamaz. Yanıt `frame-ancestors 'none'` ve
`X-Frame-Options: DENY` taşır. Keycloak yalnız kendi üç oturum denetimi belgesini çerçevede açar.

Keycloak giriş sayfası kendi satır içi betiklerini kullanır. Giriş formu, kullanıcıyı
doğrulanmış istemci adresine yönlendirir. O-40'ın kiracıya özgü betik ve form kuralları
Frappe giriş ve panel sayfalarında uygulanır.

Realm politikaları G-78 ve G-144'ü uygular. Örneğin şu ayarlar vardır:

- e-postayla giriş ve zorunlu e-posta doğrulaması,
- 300 saniyede 5 hatalı denemeden sonra kilit,
- en az 12 karakterli parola, parola geçmişi ve yaygın parola listesi,
- TOTP ve passkey,
- Karar 19 oturum süreleri (Proje kaydı O-25): kiracı sitesi ve telefon istemcileri için 1 saat boşta kalma ve 24 saat toplam süre, Press için 7 gün boşta kalma ve 30 gün toplam süre,
- 5 dakikalık erişim belirteci,
- her kullanımda değişen yenileme belirteci,
- kapalı “Beni hatırla” seçeneği.

## 3. Belirteç doğrulama

Bu kuralları `libs/oidc_verify` kitaplığı uygular. `platform_core` ve `press_tr` bu kitaplığı kullanır.

### Servis belirteci

- Yalnız RS256 imzasını kabul edin.
- `iss` değerini tam eşleştirin.
- `aud` tek değer olmalı. Değer, çağrılan sitenin istemcisi olmalı.
- `azp` değeri ucun izin listesinde olmalı. `azp`, belirteci alan istemcidir.
- `exp` zorunludur. Saat payı 30 saniyedir.
- Anahtar listesini 10 dakika saklayın. Bilinmeyen `kid` gelirse listeyi bir kez yenileyin.
- İstekte `cmd` alanı varsa isteği reddedin.
- İstek hem geçerli bir kullanıcı oturumu çerezi hem belirteç taşıyorsa isteği reddedin. Misafir çerezi oturum sayılmaz (AU-5).

### Çıkış belirteci

Keycloak çıkışta `logout_token` gönderir. Doğrulamada şunları denetleyin:

- imza, `iss` ve `aud`,
- `iat` değeri,
- `events` içindeki `http://schemas.openid.net/event/backchannel-logout` anahtarı,
- `sid` ya da `sub` değerinin varlığı,
- `nonce` alanının yokluğu.

### Telefon kimliği

Telefon uygulaması giriş isteğinde `scope=openid aud-site-tenant1 mobile` gönderir.
Keycloak, erişim belirtecine `aud=site-tenant1` ve `scope` alanına `mobile` ekler.

Telefon belirteci doğrulanınca kimlik modülü isteğe `frappe.local.mobile_identity` değerini yazar. Değer şu alanları taşıyan bir sözlüktür:

| Alan | Tür | Not |
| --- | --- | --- |
| `account` | metin | Frappe kullanıcısının adı |
| `scope` | metin | Her zaman `mobile` |
| `site` | metin | İsteğin geldiği site |
| `installation` | metin | Telefon kurulumunun kimliği. Telefon bu değeri `X-Platform-Installation` başlığında gönderir. |
| `sid` | metin | Keycloak oturum kimliği |
| `auth_time` | tamsayı | Belirteçteki son kimlik doğrulama zamanı (Unix saniyesi) |

Kabuk ve mobil modülü bu değeri okur. Değer yoksa ya da biçimi tutmazsa istek telefon isteği sayılmaz.
Kabuk, `installation` ve `sid` alanlarında boş olmayan metin ister.
Yalnız boşluk içeren metin de geçersizdir.

`X-Platform-Installation` başlığı yalnız harf, rakam, `_` ve `-` taşır. Uzunluğu 1 ile 128 karakter arasındadır. Başlık yoksa ya da biçimi tutmazsa `installation` boş metin olur. Başlık yetki vermez. Mobil modülü kurulumu kendi kaydıyla karşılaştırır.

- Kiracı sitesinde ve telefon paketinde bütün kullanıcılar çalışan süresini alır: 1 saat boşta kalma, 24 saat toplam süre. Realm bu istemcilerde `employee` düzeyini ister. Müşteri süreleri yalnız Press'e uygulanır.
- Sunucu boşta kalma sayacını `auth_time` değeri sayaç başlangıcından yeni olunca sıfırlar. Böylece aynı `sid` ile yeniden giriş de telefonu açar.
- Süre dolunca sunucu 401 durumunu ve `reauthentication_required` kodunu döndürür.
- Uygulama bu yanıtı alınca eşitlemeyi durdurur. Kullanıcıdan Keycloak ile yeniden giriş ister.
- Uygulama yeni belirteçle aynı kurulumu kaydeder. Ardından bekleyen işlemleri aynı kimliklerle yeniden gönderir.
- Oturum kimliği değişirse uygulama önce kurulumu kaydeder. Kayıttan önce eşitleme 403 ve `installation_unavailable` döndürür.

### Kitaplığın arayüzü

`press_tr` ve `platform_core` kitaplığı aynı anda kullanacak. Bu yüzden arayüz önceden belirlendi. Kitaplık Python 3.11 ve sonrasında çalışır. Frappe 16 Python 3.14 kullanır. Kitaplık Frappe'ye bağlı değildir.

```python
from oidc_verify import (
    JwksCache,
    TokenError,
    verify_access_token,
    verify_id_token,
    verify_logout_token,
)

cache = JwksCache(jwks_url, ttl_seconds=600)
claims = verify_access_token(token, cache=cache, issuer=iss, audience="site-kiraci1", allowed_azp={"identity-sync"}, leeway=30)
claims = verify_id_token(token, cache=cache, issuer=iss, client_id="press", nonce=nonce, leeway=30)
claims = verify_logout_token(token, cache=cache, issuer=iss, client_id="press", leeway=30)
```

- Her işlev geçerli belirtecin alanlarını sözlük olarak döner.
- Geçersiz belirteçte `TokenError` yükseltir. Hatanın `code` alanı nedeni söyler.
- `code` değerleri şunlardır: `malformed`, `invalid_signature`, `unknown_kid`, `wrong_issuer`, `wrong_audience`, `wrong_azp`, `expired`, `not_yet_valid`, `wrong_nonce`, `not_logout_token`.
- Anahtar listesi alınamazsa ve önbellekte güvenilir anahtar kalmadıysa kitaplık `JwksUnavailable` yükseltir. Bu hata `TokenError` değildir. Geçici bir hizmet sorunudur. Çağıran uç bu hatayı 503 gibi açık bir geçici hata olarak döner. Belirteci geçersiz saymaz.
- Kitaplık kimlik doğrulama sonucunu günlüğe yazmaz. Belirteci hiçbir yere yazmaz.

## 4. Kimlik bağı

Kullanıcının kalıcı anahtarı `(iss, sub)` çiftidir (G-120). E-posta yalnız iletişim bilgisidir.

| Uygulama | DocType | Alanlar |
| --- | --- | --- |
| `platform_core` | `Platform Identity Link` | `issuer`, `subject`, `user` |
| `press_tr` | `Press Identity Link` | `issuer`, `subject`, `user` |

- `issuer` ve `subject` zorunludur. İkisi birlikte veritabanında tekildir.
- `user` alanı bir kullanıcıya bağlanır ve tekildir.
- İlk bağı yalnız doğrulanmış e-postayla kurun (AU-4).
- Bağ farklıysa oturum açmadan reddedin.
- Keycloak oturum kimliğini (`sid`) Frappe oturumuyla eşleştirin. Çıkış belirteci bu eşleşmeyle oturumu kapatır.

## 5. `platform_core` uçları

Adres biçimi `/api/method/<yol>` olur.

| Yol | Yöntem | Kimlik | İşi |
| --- | --- | --- | --- |
| `platform_core.api.auth.get_login_url` | POST | Misafir, istek sınırlı | Keycloak giriş adresini üretir. `state` sunucuda üretilir. `redirect_to` yalnız aynı kökende göreli yol olabilir. |
| `platform_core.api.auth.keycloak_callback` | GET | Misafir, `state`, kod ve tarayıcı çerezi | Kodu belirteçle değiştirir. Kullanıcıyı `(iss, sub)` ile bulur. Oturum açar ve `sid` değerini oturuma yazar. |
| `platform_core.api.auth.logout` | POST | Oturum | Frappe oturumunu kapatır. Keycloak çıkış adresini döner. |
| `platform_core.api.keycloak_backchannel_logout` | POST | Misafir, çıkış belirteci | Eşleşen Frappe oturumlarını kapatır. |
| `platform_core.api.identity.provision` | POST | Servis belirteci, `azp=identity-sync` | Kullanıcıyı açar ya da günceller. Aynı istek iki kez gelirse aynı sonucu döner. |
| `platform_core.api.identity.set_enabled` | POST | Servis belirteci, `azp=identity-sync` | Kullanıcıyı açar ya da kapatır. |
| `platform_core.api.identity.change_email` | POST | Servis belirteci, `azp=identity-sync` | E-postayı `rename_doc` ile değiştirir. |
| `platform_core.api.shell.get_bootstrap` | GET | Oturum | Kullanıcıyı, rolleri, kurulu uygulamaları ve kenar çubuğunu döner. |
| `platform_core.api.meta.get_doctype` | GET | Oturum | Kullanıcının görebildiği DocType tanımını döner. `ETag` başlığı taşır. |
| `platform_core.api.mobile.revoke_user_installations` | POST | Servis belirteci, `azp=identity-sync` | Bir kullanıcının bütün telefon kurulumlarını iptal eder ve bildirim bağlarını siler (CK-7). Aynı istek iki kez gelirse aynı sonucu döner. Sahibi platform-core-mobil işidir. |
| `platform_core.api.identity.anonymize_user` | POST | Servis belirteci, `azp=identity-sync` | Kiracıdaki kullanıcıyı kapatır ve kişiyi gösteren alanları anonim yapar. İş kayıtlarını silmez (Proje kaydı O-27). Frappe 16'nın hazır kişisel veri silme yolu uygunsa o kullanılır. Sahibi platform-core-kimlik işidir. |

- Kiracı girişi kendi dönüş ucunu kullanır. Frappe'nin hazır `login_via_keycloak` ucu kullanılmaz. Nedeni şudur: hazır uç `state` değerini tarayıcıya bağlamaz. Ayrıca kimlik belirtecini saklamaz, bu yüzden `sid` bulunmaz.
- `get_login_url` rastgele bir tarayıcı değeri üretir. Değer `HttpOnly`, `Secure` ve `SameSite=Lax` çerezinde durur. Üretimde çerez adı `__Host-` önekini taşır.
- Sunucu `state` kaydında bu değerin özetini, PKCE doğrulayıcısını, `nonce` değerini ve dönüş yolunu saklar. Kayıt 600 saniye yaşar.
- Dönüş ucu kaydı tek bölünmez işlemle okur ve siler. Örneğin Redis `GETDEL` kullanılır. Çerezdeki değer kayıttaki özetle eşleşmezse giriş reddedilir.
- Dönüş ucu kimlik belirtecindeki `nonce` değerini denetler. Belirteç `oidc_verify.verify_id_token` ile doğrulanır.
- `kimlik_yalniz_keycloak` ayarı açıkken Frappe'nin yerel giriş işlevleri kapanır. Kapatma adrese değil, çağrılan işleve uygulanır. `override_whitelisted_methods` kancası kullanılır. Kapsam şudur: parola girişi, parola sıfırlama ve güncelleme, e-posta bağlantısıyla giriş ve hazır sosyal giriş uçları. `/api/method`, `/api/v1/method`, `/api/v2/method` ve `cmd` biçimlerinin hepsi 403 alır.
- Yönetici kurtarma yolu yalnız site ayarıyla açılır. Ayarı sunucuya erişen yönetici yazar. Yol README'de anlatılır.
- `/panel` sayfası `platform_core/www/` altında durur. Sayfa CSRF belirtecini taşır (G-45). Sahibi platform-core-kabuk işidir.

### Kabuk yanıt boyutu

- Açılış ve DocType tanımı uçları en çok 262.144 bayt döner.
- Sunucu, sıkıştırılmamış JSON gövdesini ölçer. Frappe'nin eklediği alanları da sayar.
- Tam yanıt sınırı aşarsa sunucu HTTP 200 ve `truncated: true` döner.
- Kısa açılış yanıtında kullanıcı kimliği ve biçim ayarları kalır.
- Sunucu rol, uygulama ve menü listelerini boş olarak gönderir.
- Kısa tanımda DocType kimliği ve sürüm bilgileri kalır.
- Sunucu alanları ve alt tablo tanımlarını çıkarır. Telefon bu tanımı çevrimdışı saklayamaz.
- Sunucu `ETag` değerini dönecek veriden üretir.

### Website User için yöntem izin listesi

- Website User yalnız izin listesindeki yöntemleri çağırabilir. Öteki her yöntem 403 döner. Kural `/api/method`, `/api/v1/method`, `/api/v2/method` ve `cmd` biçimlerinin hepsine uygulanır.
- Denetim adrese değil, Frappe'nin çözdüğü işleve uygulanır. Böylece takma yol da aynı kurala takılır.
- Liste `website_user_allowed_methods` kancasından gelir. Her uygulama yalnız kendi yöntemlerini ekler. Örneğin `platform_core.api.shell.get_bootstrap` ve `platform_core.api.meta.get_doctype` bu listededir.
- Frappe'nin yöntemlerinden yalnız şunlar listededir: `frappe.auth.get_logged_user`, `logout` ve kurallı aramayı saran `frappe.desk.search.search_link`. Yeni bir Frappe yöntemi listeye ancak testle girer.
- REST kayıt uçları (`/api/resource`, `/api/v2/document`) bu kuralın dışındadır. Bu uçlar Frappe'nin kayıt izinleriyle ve erişim kuralı motoruyla denetlenir.
- `/api/v2/document/<doctype>/<name>/method/<method>/` yolu ve eski `run_method` biçimi yöntem izin listesinin dışındadır. Frappe bu çağrılarda belge izinlerini denetler.
- Sahibi platform-core-kabuk işidir. Masaüstü kullanıcısı bu kuraldan etkilenmez.
- `api/__init__.py`, `api/auth.py` ve `api/identity.py` dosyaları platform-core-kimlik işinindir.
- `api/shell.py` ve `api/meta.py` dosyaları platform-core-kabuk işinindir.
- Uç dosyası ince kalır. İş kuralı modül klasöründe durur.

`provision` isteğinin alanları şunlardır:

| Alan | Tür | Not |
| --- | --- | --- |
| `issuer` | metin | Zorunlu |
| `subject` | metin | Zorunlu |
| `email` | metin | Zorunlu |
| `email_verified` | doğru ya da yanlış | Yanlışsa ilk bağ kurulmaz. |
| `first_name`, `last_name` | metin | İsteğe bağlı |
| `enabled` | doğru ya da yanlış | Zorunlu |
| `role_profiles` | metin listesi | İsteğe bağlı |

Açılan kullanıcının türü “Website User” olur (Proje kaydı D-5).

## 6. `press_tr` uçları

| Yol | Yöntem | Kimlik | İşi |
| --- | --- | --- | --- |
| `press_tr.api.auth.get_login_url` | POST | Misafir, istek sınırlı | Keycloak giriş adresini üretir. |
| `press_tr.api.auth.keycloak_callback` | GET | Misafir, `state` ve kod | Kodu belirteçle değiştirir. Kullanıcıyı `(iss, sub)` ile bulur. Takım yoksa açar (G-12). |
| `press_tr.api.keycloak_backchannel_logout` | POST | Misafir, çıkış belirteci | Eşleşen Press oturumlarını kapatır. |
| `press_tr.api.identity.ensure_team` | POST | Servis belirteci, `azp=identity-sync` | Takımı ve üyeliği hazırlar. Aynı istek iki kez gelirse aynı sonucu döner. |
| `press_tr.api.identity.remove_team_member` | POST | Servis belirteci, `azp=identity-sync` | Üyeliği kaldırır. |
| `press_tr.api.identity.anonymize_user` | POST | Servis belirteci, `azp=identity-sync` | Press kullanıcısını kapatır, API anahtarlarını geçersiz kılar ve kişiyi gösteren alanları anonim yapar. Fatura gibi iş kayıtları silinmez. |

### Kuruluş ile takım eşlemesi

Keycloak'taki “Organization” kaydı Press'teki “Team” kaydına karşılık gelir (Rail 4). Bağ Press tarafında “Team” kaydının `keycloak_org_id` alanında durur. Bu alanı `press_tr` ekler.

`ensure_team` isteğinin alanları şunlardır:

| Alan | Tür | Not |
| --- | --- | --- |
| `issuer` | metin | Zorunlu |
| `subject` | metin | Zorunlu |
| `email` | metin | Zorunlu |
| `email_verified` | doğru ya da yanlış | Zorunlu. Yanlışsa Press ilk bağı kurmaz. |
| `organization_id` | metin | Zorunlu. Keycloak'taki kuruluşun kimliğidir. |
| `organization_name` | metin | İsteğe bağlı. Yeni takımın görünen adı olur. |

- Press takımı `keycloak_org_id` alanıyla arar. Takım yoksa açar ve alana kimliği yazar.
- `keycloak_org_id` alanı veritabanında tekildir (V-8).
- Girişte Press, kullanıcının hiç takımı yoksa takım açar. Kullanıcı başka bir takımın üyesiyse yeni takım açılmaz.
- Takıma `free_account` bayrağı yazılmaz. Bu bayrak yalnız iç ve deneme siteleri içindir (G-24).
- Yanıt `team` ve `created` alanlarını taşır. `team`, Press'teki takımın adıdır.
- `remove_team_member` isteği `issuer` ve `subject` alanlarını taşır. İstek ayrıca şu iki alandan yalnız birini taşır:
  - `organization_id`: Press üyeyi yalnız bu kuruluşun takımından çıkarır.
  - `all_organizations: true`: Press üyeyi `keycloak_org_id` alanı dolu olan bütün takımlardan çıkarır. Bu biçim Keycloak'ta kapatılan ve silinen kullanıcı içindir. Silinen kullanıcının kuruluşları Keycloak'tan artık okunamaz. Press bu istekte kullanıcıyı da kapatır ve API anahtarlarını geçersiz yapar.
- İki alan birlikte gelirse ya da ikisi de gelmezse Press 400 döner. Boş `organization_id` değeri “bütün takımlar” anlamına gelmez, 400 döner.
- `keycloak_org_id` alanı boş takımlara `remove_team_member` dokunmaz. Bu takımlar Keycloak dışında elle açılmıştır.
- Aynı `remove_team_member` isteği iki kez gelirse ikinci istek de 200 döner ve bir şey değiştirmez.
- Takım adı istekte gelmez. Takım adını Press üretir.

### Press kullanıcısını anonim yapma

- `anonymize_user` isteği `issuer` ve `subject` alanlarını taşır. İki alan da zorunludur.
- İş geri alınamaz. Uç bunu açıklamasında yazar.
- Yanıt 200 döner ve `anonymized` ile `found` alanlarını taşır. Kimlik bulunamazsa `found: false` olur. Tekrar çağrı aynı yanıtı alır.
- Kilit çakışması ya da zaman aşımı 409 döner. identity-sync isteği yeniden dener.
- Anonim yapma kuralları 7. bölümdeki ortak kurallardır.

- Press de Frappe 16 üzerinde çalışır (Proje kaydı D-7). press-tr işi `on_social_login` kancasını kaynakta doğrular. Sonra kancayı ya da kendi dönüş ucunu seçer. Yukarıdaki dönüş adresi bu seçime göre değişebilir.
- G-12'deki Press giriş, kayıt ve parola uçları 403 döner.
- Press'te misafir için izin listesi uygulanır. Misafir yalnız listedeki yöntemleri çağırabilir. Liste şudur: `ping`, `press_tr.api.auth.get_login_url`, `press_tr.api.auth.keycloak_callback`, `press_tr.api.keycloak_backchannel_logout`. Öteki bütün yöntemler misafire 403 döner.
- Denetim yöntemin adına değil, çağrılan işleve uygulanır. Böylece başka modülün içe aktardığı aynı işlev de kapanır. `/api/method`, `/api/v1/method`, `/api/v2/method` ve `cmd` biçimlerinin hepsi aynı denetimden geçer.
- Takım üyeliği yalnız Keycloak kuruluşundan gelir. Press'in kendi takım davet ve davet kabul uçları kapanır.
- G-12'deki yerel giriş, kayıt, parola, tek kullanımlık kodla giriş ve bağlantıyla giriş uçları her çağırana kapalıdır. Misafir de, oturum açmış kullanıcı da 403 alır. Denetim işlev nesnesiyle yapılır.
- Press'in makineden makineye çağrılan misafir uçları açık kalır. Bunlar ajan geri bildirimi, ödeme sağlayıcısı, GitHub, izleme, e-posta ve yedek uçlarıdır. Her biri kendi imzasını ya da anahtarını denetler. Liste sözleşmenin Press OpenAPI dosyasında tek tek yazılır. Bir uç listeye ancak kendi kimlik denetimi testle gösterilince girer.
- Takım sahibi kapatılınca takım silinmez. Kuruluşa yeni üye eklenebilir. Sahipliği yönetici elle devreder. Sahibi kapalı takım için `ensure_team` 200 döner ve yanıtta `owner_disabled: true` taşır.
- Kullanıcı Keycloak'ta kapatılınca ya da silinince Press kullanıcıyı da kapatır. Kullanıcının Press API anahtarları geçersiz olur.
- Misafir istek sınırı istemcinin gerçek adresine bağlıdır. Üretimdeki ara sunucu `X-Forwarded-For` başlığının üzerine yazar. Ara sunucu ayarı depoda durur.

## 7. `identity_sync`

- Keycloak olaylarını alır. Olay kaynağı şudur: Keycloak'a bir olay dinleyici eklentisi kurulur. Eklenti kullanıcı ve yönetim olaylarını imzalı olarak `identity_sync` servisinin `/v1/events` ucuna gönderir. Eklentinin lisansı Apache-2.0 ya da MIT olur. Seçim T-2 karar notuna yazılır (Proje kaydı O-11).
- Olay kaybolabilir. Bu yüzden elle başlatılan mutabakat komutu yedek yoldur. Komut farkları bulur ve önizleme ile onay akışından geçirir. Zamanlanmış iş yoktur.
- Belirteci Keycloak'tan istemci kimlik bilgisiyle alır.
- `press_tr.api.identity.*` ve `platform_core.api.identity.*` uçlarını çağırır.
- Kiracı listesini ayardan okur. Geliştirmede tek kiracı `kiraci1` vardır.
- Her işlem tekrar edilebilir olmalıdır. Aynı olay iki kez gelirse sonuç değişmez.
- Başarısız olay ayrı kuyrukta bekler.
- Mutabakat elle başlatılan bir komuttur. Komut farkları raporlar.
- `POST /v1/sessions/revoke` ucu bir Keycloak oturumunu kapatır. Gövde `{"sid": "<oturum kimliği>", "subject": "<kullanıcı>"}` olur. Ucu yalnız `platform_core` servis belirteci çağırır. identity-sync önce oturumun bu kullanıcıya ait olduğunu Keycloak Admin API'den doğrular. Sonra kullanıcının çağıran kiracının kuruluşuna üye olduğunu doğrular. Kiracı, belirtecin `azp` değerinden kiracı listesiyle bulunur. Kullanıcı bu kuruluşa üye değilse uç 403 döner. Oturum bu kullanıcıya ait değilse identity-sync hiçbir oturumu silmez ve 200 döner. Telefon istemcisi `subject` değerini kendi kurulum kaydından alır. identity-sync, Keycloak Admin API ile o oturumu siler. Oturum silinince yenileme belirteci de geçersiz olur. Uç tekrar edilebilir: kapalı oturum için de 200 döner.
- Telefon kurulumu kayıt anında belirteçteki `sid` değerini saklar. Kurulum iptal edilince `platform_core` bu ucu çağırır. Aynı `sid` ile gelen belirteç de reddedilir (Proje kaydı O-25).
- `POST /v1/account-deletions` ucu hesap silme isteğini kaydeder (Proje kaydı O-27). Ucu yalnız Press çağırır. Belirteç `azp=press-service` ve `aud=identity-sync` taşır. Gövde `issuer`, `subject` ve `reauthenticated_at` alanlarını taşır.
- Müşteri silme isteğini Press'te verir. Press önce kullanıcıyı Keycloak'ta yeniden doğrular (`prompt=login`, `max_age=0`). `reauthenticated_at` bu doğrulamanın zamanıdır. identity-sync 300 saniyeden eski doğrulamayı reddeder.
- Keycloak'ın kendi `delete_account` eylemi kapalıdır. Bu eylem kullanıcıyı ilk adımda siler. Hesap ekranındaki silme bağlantısı Press'teki silme sayfasına gider.
- Yönetici kullanıcıyı Keycloak yönetim ekranından silerse olay dinleyici olayı gönderir. identity-sync 2., 3. ve 4. adımları yine çalıştırır. Olay kaybolursa elle başlatılan mutabakat komutu silinmiş kullanıcıyı bulur. Komut önce önizleme gösterir. İnsan onay verirse komut kalan silme adımlarını sırayla çalıştırır. Yerel hesap önceden kapalı olsa da bu adımlar çalışır.
- Press isteği ve Keycloak silme olayı aynı hesap işine bağlanır. İş kimliği hesabın özetidir. Tamamlanan adım yeniden çağrılmaz. Yeniden deneme yanıtı hesap kimliğini değil iş kimliğini gösterir.
- Akış sırası şudur:
  1. Keycloak kullanıcısı kapanır.
  2. Press kullanıcısı kapanır ve API anahtarları geçersiz olur (`remove_team_member`, `all_organizations: true`).
  3. Kiracı sitelerindeki kullanıcı kapanır. Telefon kurulumları ve bildirim bağları silinir.
  4. Kişiyi gösteren alanlar anonim yapılır. İş kayıtları silinmez.
  5. Keycloak kullanıcısı silinir. İstek kaydı anonim yapılır.
- Her adım tekrar edilebilir. Bir adım başarısız olursa istek hata kuyruğuna girer ve elle yeniden denenir.

### Anonim yapma kuralları

Bu kurallar kiracı sitesinde (`platform_core.api.identity.anonymize_user`) ve Press'te (`press_tr.api.identity.anonymize_user`) aynıdır. Kararın kaynağı proje kaydındaki O-27'dir.

1. Silme iki adımdır. Birinci adım hesabı kapatır, oturumları sayfalayarak kapatır, API anahtarlarını iptal eder ve silme durumunu kaydeder. İkinci adım kişisel veriyi anonim yapar. İki adım da tekrar güvenlidir.
2. Silme kaydı ham kimliği tutmaz. Kayıt `(iss, sub)` çiftinin HMAC-SHA256 özetini tutar. Anahtar site ayarındaki gizli değerdir. Kimlik bağındaki ham `sub` silinir.
3. Hesap açma, durum değiştirme ve e-posta değiştirme uçları önce silme kaydını denetler. Silinmiş kimlik yeniden açılamaz. Bu uçlar aynı satır kilidini kullanır.
4. Kapsam Frappe'nin `user_data_fields` kancasından türer. Ek olarak şunlar temizlenir ya da anonim yapılır:
   - kullanıcıya bağlı “Contact” ve adres kayıtları,
   - “Activity Log” kayıtlarındaki ad ve IP adresi,
   - kiracıda “User” ve kişiye ait “Contact” geçmişi ile kullanıcının yazdığı “Version” kayıtlarındaki ad ve e-posta,
   - profil fotoğrafı ve kişiye ait “User” veya “Contact” kayıtlarına bağlı dosyalar,
   - “Communication” ve e-posta kuyruğundaki adresler,
   - iki adımlı doğrulama anahtarları, varsayılan değer satırları, sosyal giriş ve ek e-posta satırları,
   - Press'te takımın fatura adı ve telefonu, SSH anahtarları ve sertifikaları.

   Kiracıda `clear_fields` içindeki zorunlu olmayan alan boşaltılır. Zorunlu alan bu listeye yazılamaz.
   Bu seçenek yalnız `redact_fields` içinde bulunan alanlar için geçerlidir.
   Kod, listeye yazılmış zorunlu alanda olağan anonim değeri kullanır.

5. Frappe'nin tam adı bütün satırlarda arayan değiştirmesi kullanılmaz. Yalnız kullanıcıya bağlı alanlar değişir. Böylece aynı adı taşıyan başka bir kişinin verisi değişmez.
6. Fatura kayıtları değişmez. Fatura yasal kayıttır ve kesildiği hâliyle saklanır. Bu istisna proje kaydında yazılıdır.
7. Kullanıcı bir takımın tek üyesiyse takım kapatılır ve siteleri askıya alınır. Siteler silinmez.
- `/v1/sessions/revoke` ucunu kiracı sitesi kendi servis istemcisiyle çağırır. Belirteç `aud-identity-sync` kapsamıyla istenir. İzinli istemciler `IDENTITY_SYNC_SESSION_AZP` ayarındadır. Listede yalnız `site-<kiracı>-service` istemcileri bulunur.
- Onaylı işlem yürütme ucunu da kiracı sitesinin servis istemcisi çağırır. Onay kiracı sitesindeki yapay zekâ katmanında verilir. Bu yüzden `IDENTITY_SYNC_EXECUTE_AZP` ayarı kiracı servis istemcilerinin listesidir. Liste `IDENTITY_SYNC_SESSION_AZP` ile aynı istemcileri taşır.
- Kiracı servis istemcisi yalnız kendi kuruluşu için iş yürütür. `POST /v1/invitations` isteği yalnız istemcinin kendi kuruluşuna kullanıcı ekler. `/v1/operations/{operation_id}/resolve` isteği yalnız kendi kuruluşunun işlemini sonuçlandırır. Başka kuruluşun işlemi için yanıt 403 olur.
- Bütün platformu etkileyen uçları yalnız operatör istemcisi çağırır. Bu uçlar `POST /v1/reconcile`, `POST /v1/dead-letters/replay`, `GET /v1/dead-letters` ve `GET /v1/operations` uçlarıdır. İzinli istemciler `IDENTITY_SYNC_OPERATOR_AZP` ayarındadır. Kiracı istemcisi bu uçları çağırırsa yanıt 403 olur.
- `IDENTITY_SYNC_OPERATOR_AZP`, `IDENTITY_SYNC_PREVIEW_AZP` ve `IDENTITY_SYNC_DELETION_AZP` listelerinde `site-` ile başlayan istemci bulunmaz. Bu üç liste birbirinden ve kiracı listelerinden ayrıdır. Servis kuralı bozan ayarla açılmaz.
- Mutabakat için Press ve kiracı sitesi `list_identities` ucunu sunar. Uç yalnız identity-sync servis belirtecini kabul eder. Yanıt sayfalıdır ve her satırda yalnız `issuer`, `subject` ve hesabın açık ya da kapalı durumu bulunur. E-posta ve ad dönmez. Uç adları `press_tr.api.identity.list_identities` ve `platform_core.api.identity.list_identities` olur.
  - Uç `GET` ile çağrılır. İstek `start` ve `page_length` sorgu alanlarını alır. `cursor` ve `limit` alanları kullanılmaz. `start` varsayılan 0 olur. `page_length` en çok 500, varsayılan 500 olur. Sıra `subject` değerine göre artandır.
  - Yanıt `{"identities": [...], "has_next_page": true|false}` biçimindedir.
  - identity-sync bütün sayfaları toplar. Farkları ancak son sayfadan sonra hesaplar.
- identity-sync, Keycloak'ta istemci açmaz. Servis hesabı `manage-clients` rolünü almaz. Yeni kiracının Keycloak istemcisini kimlik-realm işinin elle başlatılan komutu açar. Komut insan onayıyla çalışır.
- Hesap silme akışının 3. ve 4. adımı şu uçları çağırır: `platform_core.api.mobile.revoke_user_installations`, `platform_core.api.identity.anonymize_user` ve `press_tr.api.identity.anonymize_user`.

## 8. Site ayarları

Ayarlar `site_config.json` dosyasında durur. Sır taşıyan ayar depoya girmez.

| Anahtar | Örnek | Not |
| --- | --- | --- |
| `keycloak_public_url` | `http://kimlik.localhost:<port>` | Tarayıcının gördüğü adres |
| `keycloak_internal_url` | Boş | Sunucunun ulaştığı adres |
| `keycloak_realm` | `platform` | |
| `keycloak_client_id` | `site-kiraci1` ya da `press` | |
| `keycloak_client_secret` | Sahte değer | Yalnız site ayarında ve `.env` dosyasında |
| `keycloak_service_client_id` | `site-tenant1-service` ya da `press-service` | Servis belirteci için |
| `keycloak_service_client_secret` | Sahte değer | Yalnız site ayarında ve `.env` dosyasında |
| `kimlik_marka_adi` | `Atonota` | Düğme metni bundan üretilir |
| `platform_panel_url` | `http://kiraci1.localhost:<port>/panel` | Çıkıştan sonraki adres |
| `hrms_tr_retention_days` | Ayar verilmez | Hukuk sorumlusu süreyi gün olarak belirler. |

### Kişisel veri silme yolları

Aşağıdaki tablo, HRMS TR kayıtlarında kişisel verinin nasıl silindiğini gösterir.

| Kişisel veri | Silme yolu |
| --- | --- |
| HRMS TR çalışan kartı | `user_data_fields` kancası kartı `user_id` ile bulur. Adlar, e-posta, telefon, acil durum kişisi, yakınlık, adresler ve biyografi anonimleşir. Pasaport numarası ve düzenlenme yeri anonimleşir. Banka adı, hesap numarası, IBAN, sağlık notu, sigorta numarası ve aile bilgisi anonimleşir. Doğum tarihi, pasaport tarihleri, devam cihazı kimliği, kan grubu ve medeni durum alanları boşalır. Fotoğraf alanı boşalır. Karta yüklenen fotoğraf dosyası şimdilik kalır. Çalışan kartının değişiklik geçmişi eski değerleri şimdilik tutar. Eğitim ve önceki iş alt tabloları kalır (O-41). |
| HRMS TR iş kayıtları | Hesap silme kayıtları korur. İzin, devam ve bordrodaki çalışan adı kopyaları değişmez (O-41). `hrms_tr.retention.purge` yalnız süresi dolan taslak ve iptal edilmiş izinleri siler (O-39). |

## 9. Geliştirme ortamı

### Adlar

| Ad | Değer |
| --- | --- |
| Kiracı sitesi | `kiraci1.localhost` |
| Press sitesi | `press.localhost` |
| Keycloak sunucusu | `kimlik.localhost` |
| Compose proje adı | `fs-<iş adı>` |
| Ana compose dosyası | `dev/compose.yaml` |
| Kiracı compose dosyası | `dev/compose.tenant.yaml` |
| Keycloak compose dosyası | `dev/compose.keycloak.yaml` |
| Press compose dosyası | `dev/compose.press.yaml` |
| Örnek kullanıcıların alan adı | `example.test` |

### Portlar

Port tabanı `PANE_PORT` değişkenidir. Kısaca `P` diyelim.

| Port | Servis |
| --- | --- |
| `P` | Keycloak |
| `P+1` | Kiracı sitesinin web sunucusu |
| `P+2` | Kiracı sitesinin anlık bağlantı sunucusu |
| `P+3` | Press'in web sunucusu |
| `P+4` | Press'in anlık bağlantı sunucusu |
| `P+5` | `identity_sync` |
| `P+6` | Test e-posta kutusunun ekranı |

### Önerilen adres yolu

Tarayıcı ve container aynı adresi kullanmalıdır. Yoksa `iss` değeri tutmaz. Önerilen yol şudur:

1. Keycloak container içinde de `P` portunu dinler.
2. Compose, `P` portunu `127.0.0.1:P` adresine açar.
3. Keycloak servisi ağda `kimlik.localhost` takma adını taşır.
4. Tarayıcı `http://kimlik.localhost:P` adresine gider.
5. Container'lar aynı adresle Keycloak'a ulaşır.

Kiracı ve Press sunucuları için de aynı yol geçerlidir. Keycloak çıkış bildirimini bu adreslere gönderir. Bu yolu ilk deneyen iş sonucu raporlar.

## 10. Yapay zekâ erişim katmanı

Proje sahibinin kararı şudur: Her şey yapay zekâyla yönetilebilir olacak. Katman model sağlayıcısından bağımsız olacak (Proje kaydı D-9). Bu bölüm bütün işler için geçerlidir.

### Temel kurallar

1. Her DocType ve her alan yapay zekâ katmanından görünür. Yeni DocType için ayrı kod gerekmez. Araçlar DocType tanımından çalışma anında üretilir.
2. Yapay zekâ kullanıcının kimliğiyle çalışır. Yetki denetimi REST uçlarıyla aynıdır. `ignore_permissions` kullanılmaz (G-85).
3. Yazma işi önce önizleme üretir. Önizlemeyi insan onaylar. Onay sunucuda üretilir ve tek kullanımlıktır (G-86). Model onay veremez.
4. Her çağrı “AI Action Log” kaydına yazılır. Ret de yazılır (G-64).
5. Ham SQL, ham Python, kabuk ve “Server Script” aracı yoktur. Veritabanı yalnız DocType katmanından açılır.
6. Gizli alan hiç dönmez. Örneğin “Password” türündeki alanlar, belirteçler ve anahtarlar böyledir. Press'te okuma açık alan listesiyle yapılır.
7. Kuyruğa alınma başarı sayılmaz. Başarı kaydın son durumundan okunur. Sonucu bilinmeyen iş “unknown” kalır. Aynı hedefe kör tekrar yapılmaz.
8. Frappe uygulamalarına model sağlayıcısı kitaplığı eklenmez. Kodda model adı yazılmaz.
9. Dış arayüz açık standartlardır: MCP ve OpenAPI. MCP, modellerin araç kullandığı açık protokoldür. Her sağlayıcının istemcisi bağlanabilir.

### Araç türleri

| Tür | Örnek | Kaynak |
| --- | --- | --- |
| Tanım | DocType'ı, alanları ve izinleri anlatır | DocType tanımı ve alan açıklamaları |
| Okuma | Liste, kayıt, rapor | Kullanıcının okuma izni |
| Yazma | Oluşturma, güncelleme, onaya gönderme, iptal, silme | Önizleme ve insan onayı |
| Yönetim | Özel alan, alan ayarı, rol ve izin değişikliği | Yalnız yönetici rolü, önizleme ve insan onayı |
| Uygulama aracı | Örneğin izin onayı | Uygulamanın `ai_tools` kancası (G-105) |
| Geliştirme | DocType iskeleti, alan ekleme önerisi | İskelet davranış değildir. İş kuralı tek dosyalık onaylı öneriyle yazılır. Araç kod çalıştırmaz. |

### Her işin uyacağı kurallar

- Yazdığınız her DocType alanına `description` verin. Açıklama İngilizce yazılır. Türkçesi çeviri dosyasındadır. Yapay zekâ alanı bu açıklamadan anlar.
- Yazdığınız her uca OpenAPI dosyasında özet ve açıklama yazın.
- Bir Frappe adresini değiştirirseniz eski adresi hedef işlemin `x-frappe-original` alanına yazın.
- Ucu yıkıcı ya da ücretli bir iş yapıyorsa bunu sözleşmede belirtin.
- Elle başlatılan her komut için bir HTTP ucu da yazın. Böylece yapay zekâ da komutu başlatabilir. Örneğin mutabakat komutu böyledir.
- `press_tr` aynı kuralları uygular. Press işlemleri için depodaki `packages/press-ai` sözleşmesi temel alınır.

### Karar sitesindeki AI kuralları

Karar sitesinin AI bölümü de geçerlidir. Sayfalar `src/content/docs/ai-*.md` dosyalarıdır. Özellikle şu kurallar bu katmana uyar:

- Her yazma insan onaylıdır. Onay özete bağlı, tek kullanımlık ve sürelidir. Modelde onay aracı ya da `confirm` alanı yoktur.
- Yürütme aynı işlem ve hedef için kilit alır. İstekten önce sonucu “unknown” olarak kaydeder.
- Altyapı, DNS, yasal kutu ve ödeme işleri insanda kalır. Yapay zekâ bunlar için yalnız gereksinim metni üretir.
- Resmî uygulamaların dosyası varsayılan olarak değiştirilmez.
- AGPL lisanslı bir bileşen kendi kodumuzla birleşmeden önce lisans uyumu proje sahibine sorulur.

### Sahiplik

- `platform_core` içinde katmanı platform-core-yz işi kurar. Modül klasörü `ai` olur.
- Önce Frappe'nin hazır MCP yolunu inceleyin (T-1). Karar sitesi bunu `frappe_mcp` olarak anar (G-84).
- Ayrıntılı tasarım `docs/decisions/0002-ai-layer.md` dosyasındadır.
- Frappe 16'nın hazır MCP ucu (`/api/v2/mcp`) kiracı sitesinde kapatılır. Bu uç önizleme, onay ve günlük taşımaz.

### Uçlar

| Yol | Yöntem | Kimlik | İşi |
| --- | --- | --- | --- |
| `platform_core.api.ai.mcp` | POST | İnsan oturumu, aracı belirteci veya açıkken OAuth | Araçları listeler ve çağırır. |
| `platform_core.api.ai.mcp_resource_metadata` | GET | Herkese açık | OAuth açıkken Keycloak adresini ve kapsamı bildirir. |
| `platform_core.api.ai.issue_agent_token` | POST | İnsan oturumu | 300 saniyelik, 20 çağrılık aracı belirteci üretir. |
| `platform_core.api.ai.list_proposals` | GET | İnsan oturumu | Kullanıcının önerilerini listeler. |
| `platform_core.api.ai.get_proposal` | GET | İnsan oturumu | Önerinin önizlemesini ve özetini döner. |
| `platform_core.api.ai.approve_proposal` | POST | İnsan oturumu | Öneriyi onaylar ve yürütür. |
| `platform_core.api.ai.reject_proposal` | POST | İnsan oturumu | Öneriyi reddeder. |
| `platform_core.api.ai.resolve_proposal` | POST | İnsan oturumu | Sonucu bilinmeyen öneriyi kapatır. |
| `platform_core.api.ai.purge_logs` | POST | “System Manager” rolü | Saklama süresi dolan günlükleri elle siler. Yıkıcıdır. |

- `list_proposals` yanıtı bir nesnedir: `proposals` ve `has_next_page`. İstek `start` alır. Süzme ve sayfalama veritabanında yapılır.
- Öneri `created_at` ve `expires_at` taşır. Zaman sitenin saat dilimiyle ve farkıyla ISO 8601 biçiminde döner.
- Okuma araçlarının sonucu `as_of`, `site` ve `source` taşır. Sonuç sınırı aşarsa `truncated: true` döner. Alt tablo en çok 200 satır, sonuç verisi en çok 262.144 bayttır.
- OAuth kapalıyken kimliksiz MCP isteği 403 alır. Süresi dolmuş oturum 401 alır.
- OAuth varsayılan olarak kapalıdır. Açıkken kimliksiz MCP isteği 401 alır.
- Sunucu 401 yanıtında keşif adresini `WWW-Authenticate` başlığına yazar.
- Keşif ucu yanıtı doğrudan JSON olarak döner.
- Keşif ucu, bir IP adresinden dakikada en çok 60 istek kabul eder.
- MCP ucu, kullanıcı başına dakikada en çok 120 istek kabul eder.
- MCP ucu, misafirler için bu sınırı IP adresine uygular.
- Sunucu, Keycloak sorgusundan önce IP adresi başına dakikada 120 istek sınırı uygular.
- Kiracı ara sunucusu, `X-Forwarded-For` başlığını doğruladığı istemci adresiyle değiştirmelidir.
- İstemci Keycloak'ta yetki kodu akışını ve PKCE S256 yöntemini kullanır.
- Sunucu `mcp` kapsamını ve tek hedef olarak sitenin tam MCP adresini ister.
- Sunucu her istekte imzalı `mcp_resource` alanını da tam MCP adresiyle karşılaştırır.
- Keycloak dönüş adresini tam eşleşmeyle denetler. Joker, parça işareti ve kullanıcı bilgisi reddedilir.
- Sunucu her çağrıda Keycloak oturumunun açık olduğunu denetler.
- Oturum sorgusu 3 saniyeyi aşarsa sunucu 503 döner.
- Belirteç en çok 300 saniye geçerlidir. Bir belirteç en çok 20 araç çağrısı yapabilir.
- Sayaç veritabanında kalır. Önceki kullanımı gösteren kayıt Redis'te kalır.
- Bu iki kayıt, tek kayıp durumunda belirtecin yeniden hak almasını önler.
- İki kayıt deposu birlikte geri yüklenirse OAuth desteğini 300 saniye kapalı tutun.
- İstemci belirteci yalnız `Authorization` başlığında gönderir.
- OAuth ile yazma aracı öneri açar. İnsan ayrı oturumda onay verir.

#### Kullanım günlüğü temizliğinin modül arayüzü

- “AI Usage Log” kaydının sahibi model geçididir. Temizlik işlevi `platform_core.model_gecidi.api.purge_usage_logs(*, dry_run=False, names=None)` olur.
- İşlev yetkiyi kendisi denetler. Yalnız “System Manager” çağırabilir. Öteki kullanıcı `frappe.PermissionError` alır.
- Süre 365 gündür. Ayar bu süreyi değiştiremez. Kayıtlar O-32'ye göre kalıcı silinir.
- `dry_run=True` iken işlev hiçbir kaydı silmez. `{"eligible": <sayı>, "deleted": 0, "names": [...]}` döner. `names` bu çalıştırmada silinecek kayıtların adlarıdır, en çok 500 tanedir.
- `dry_run=False` iken çağıran taraf önizlemedeki `names` listesini verir. İşlev yalnız bu kayıtları siler. Kayıtları kilit altında yeniden doğrular. Bir kayıt artık uygun değilse ya da listede olmayan bir kayıt seçilirse işlev hiçbir şey silmez ve `frappe.ValidationError` verir. Çağıran taraf yeni önizleme ister.
- Silme tek bir veritabanı işlemi ve geri dönüş noktası içinde yapılır. Bir kayıt silinemezse hiçbir kayıt silinmez ve hata çağırana iletilir. Başarılı yanıt `{"eligible": <sayı>, "deleted": <sayı>, "names": [...]}` olur.
- İşlev önizleme belirteci istemez. İnsan onayını çağıran taraf yönetir. Örneğin `platform_core.api.ai.purge_logs` kendi önizleme ve onay yolunu kullanır ve onaya `names` listesini bağlar. Geçidin kendi HTTP ucu da kendi önizleme belirtecini kullanabilir.


### Genel araçlar

`search_doctypes`, `get_doctype_schema`, `list_documents`, `get_document`, `run_report`, `create_document`, `update_document`, `submit_document`, `cancel_document`, `delete_document` ve `get_proposal`.

- Yazma araçları yalnız öneri açar. Öneri 10 dakika geçerlidir.
- Uygulama araçlarının adı `<uygulama>_<araç>` biçimindedir. Uygulama araçlarını `ai_tools` kancasıyla bildirir.
- Yönetim araçları şunlardır: `add_custom_field`, `set_field_property`, `set_role_permission`, `assign_role`, `remove_role` ve `purge_action_log`. Yalnız “System Manager” rolü kullanır. “System Manager” rolü yapay zekâ yoluyla verilmez.
- MCP istemcisi konuşma kimliğini `Mcp-Conversation-Id` başlığıyla gönderir. Günlükler bu kimlikle eşleşir.
- Panel, yazan her istekte `X-Frappe-CSRF-Token` başlığını gönderir. Oturumda CSRF belirteci yoksa onay reddedilir.

### Öteki modüllerin araç bildirimi

Her modül elle başlatılan komutlarını ve yazma işlerini `ai_tools` kancasıyla araç olarak bildirir. Bildirim biçimi `contracts/platform_core-ai.openapi.yaml` dosyasının `x-ai-tools-hook` bölümündedir. Yazma araçları önizleme işlevi taşır. Bu bölüm platform-core-yz dalı birleşince geçerli olur.

## 11. Model geçidi ve sağlayıcı kaydı

Altyapı yapay zekâ tabanlıdır. Sisteme n tane sağlayıcı, her sağlayıcıdan n tane hesap ve her hesaptan n tane API eklenebilir (Proje kaydı D-11). Sağlayıcı, model sunan şirket ya da sunucudur. Hesap, o sağlayıcıdaki üyeliktir. API, hesaba bağlı bir adres ve anahtardır.

### DocType'lar

Bütün DocType'lar `model_gateway` modülündedir. Her alan açıklama taşır (D-9).

| DocType | Görevi | Önemli alanlar |
| --- | --- | --- |
| `AI Provider` | Sağlayıcı türü | ad, bağdaştırıcı, varsayılan adres, açık mı |
| `AI Account` | Sağlayıcıdaki hesap | sağlayıcı, hesap adı, kurum ya da proje kimliği, aylık bütçe ve para birimi, açık mı |
| `AI API` | Hesaba bağlı adres ve kimlik bilgisi | hesap, adres, kimlik türü, gizli anahtar, izinli modeller, dakika sınırları, öncelik, ağırlık, sağlık durumu, açık mı |
| `AI Model` | Model ve yetenekleri | sağlayıcı, model kimliği, yetenekler, bağlam boyu, birim fiyatlar |
| `AI Route` | İş türüne göre model sırası | ad, gereken yetenekler, seçme yolu, sıralı model ve API listesi, veri kısıtı |
| `AI Usage Log` | Her çağrının kaydı | zaman, kullanıcı, yol, sağlayıcı, hesap, API, model, token sayıları, maliyet, süre, sonuç |

### Bağdaştırıcılar

Bağdaştırıcı, ortak çağrıyı sağlayıcının biçimine çeviren küçük koddur. İlk bağdaştırıcılar şunlardır:

- OpenAI uyumlu sohbet biçimi,
- Anthropic Messages biçimi,
- Google Gemini biçimi,
- yerel sunucu, örneğin Ollama.

Yeni sağlayıcı eklemek kod istemez. Yeni bir biçim eklemek yalnız yeni bağdaştırıcı ister. Bağdaştırıcılar düz HTTP kullanır. Sağlayıcı kitaplığı eklenmez.

Kimlik türleri şunlardır: API anahtarı, taşıyıcı belirteç, OAuth istemci kimlik bilgisi ve kimliksiz yerel sunucu.

### Ortak çağrı

`model_gateway` dışarıya tek bir işlev açar. İşlev bir yol adı ve mesajları alır. Araç tanımı ve yanıt biçimi isteğe bağlıdır. Yanıt sağlayıcıdan bağımsız tek biçimdedir: metin, araç çağrıları, kullanım ve hangi model ile API'nin kullanıldığı.

### Yönlendirme

1. Yol kaydından aday modelleri ve API'leri alın.
2. Kapalı, yeteneği eksik, bütçesi dolmuş ve devresi açık adayları çıkarın.
3. Adayları yolun seçme biçimine göre sıralayın. Seçme biçimleri öncelik, ağırlık ve en düşük maliyettir.
4. İlk adayı çağırın.
5. 429 ya da 5xx gelirse adayı bir süre dinlendirin ve sıradakine geçin.
   - Zaman aşımında sağlayıcı işi bitirip ücret almış olabilir. Bu yüzden bütçeli hesapta sıradakine geçilmez. Kayıt “unknown” kalır ve kullanıcı 503 alır.
   - Bütçesiz hesapta zaman aşımı sıradakine geçebilir.
   - Modelin çıktı hızı kayıtta durur (`output_tokens_per_second`). Yol süresine sığmayan `limit` değeri, bütçe ayrılmadan önce 400 ile reddedilir.
6. Kimlik hatası gelirse API'yi kapalı sayın ve yönetici kaydına yazın.
7. Her denemeyi “AI Usage Log” kaydına yazın.

Dinlenme süresi önbellekte süreli değerdir. Süre dolunca aday kendiliğinden döner. Zamanlanmış iş yoktur (O-15).

### Güvenlik

- Dış bağlantı (`external`) özel ağ adresine gidemez. Denetim bağlantı anında çözülen adrese yapılır.
- Yerel bağlantı (`local`) yalnız site ayarındaki sabit adres listesine gider. Örnek: `{"kind": "local", "addresses": ["10.0.5.7"]}`. Bağlantı yerel adresler (`169.254.0.0/16`, `fe80::/10`), `0.0.0.0/8` ve çoklu yayın adresleri her zaman reddedilir.
- Şifresiz HTTP yalnız listedeki yerel adrese izinlidir. Açık internetteki adrese şifresiz istek gönderilmez.
- Gizli anahtar “Password” alanında şifreli durur. Hiçbir uç ve hiçbir yapay zekâ aracı anahtarı dönmez.
- Kayıt, günlük ve hata metni anahtarı içermez.
- Kaydı yalnız “AI Manager” rolü ve “System Manager” rolü yönetir.
- Genel yazma araçları AI API ve AI Account kayıtlarına yazamaz (Proje kaydı O-28). Yapay zekâ bu kayıtları yalnız model geçidinin kendi yönetim araçlarıyla değiştirir. Her değişiklik önizleme ve insan onayı ister.
- Yönetim aracı bağlantı adresini değiştirirse kayıtlı anahtar silinir ve bağlantı kapanır. Yeni anahtarı insan Desk ekranında girer. Böylece kayıtlı anahtar yeni adrese gitmez.
- Bağlantı denetimi ücretli bir çağrıdır. Bu yüzden ücretli işaretini taşır.
- Mesaj içeriği varsayılan olarak günlüğe yazılmaz.
- Yol kaydının veri kısıtı, model çağrısından önce veri seçimini ve maskelemeyi ister (G-90).
- Dış sağlayıcıya giden içerik her zaman maskelenir. Yolun veri kısıtını “AI Manager” rolü seçer. Kısıt `masked` ise maskelenmiş içerik dış sağlayıcıya gidebilir. Ayrıca içerik bazında ön onay istenmez.
- Aracı belirteci model ucunda geçmez. Aracı modele `ai` katmanı üzerinden ulaşır. Bu katman `platform_core.model_gateway.api.complete` işlevini çağırır. Böylece belirtecin biçimi tek yerde, `ai` modülünde kalır.
- `model_gateway` modülünün açık çağrı işlevi arka plan işinde de çalışır. İşlev o anki kullanıcının yetkisini denetler. Misafir kullanıcı çağıramaz.

### Uç

| Yol | Yöntem | Kimlik | İşi |
| --- | --- | --- | --- |
| `platform_core.api.model.complete` | POST | İnsan oturumu ya da API anahtarı | Ortak çağrıyı yapar. Yetki ve kota denetlenir. |
| `platform_core.api.model.test_api` | POST | “AI Manager” rolü | Bir API'ye küçük deneme çağrısı yapar. Ücretlidir. |
