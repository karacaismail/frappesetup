# Bileşenler arası sözleşmeler

Bu dosya backend bileşenlerinin ortak adlarını tutar. İşler paralel yürür. Bu yüzden herkes aynı adları kullanmalıdır. Bir adı değiştirmek gerekirse raporda isteyin. Orkestratör bu dosyayı günceller.

Ayrıntılı istek ve yanıt biçimi `contracts/` klasöründeki OpenAPI dosyalarındadır. OpenAPI, uçları tarif eden belge biçimidir. Her uç sahibi kendi dosyasını yazar:

| Dosya | Sahip iş |
| --- | --- |
| `contracts/platform_core-kimlik.openapi.yaml` | platform-core-kimlik |
| `contracts/platform_core-kabuk.openapi.yaml` | platform-core-kabuk |
| `contracts/press_tr.openapi.yaml` | press-tr |
| `contracts/identity_sync.openapi.yaml` | identity-sync |

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
| `site-kiraci1` | Gizli sırlı | Yetkilendirme kodu | `<kiracı adresi>/api/method/frappe.integrations.oauth2_logins.login_via_keycloak` | `<kiracı adresi>/api/method/platform_core.api.keycloak_backchannel_logout` |
| `press` | Gizli sırlı | Yetkilendirme kodu | `<Press adresi>/api/method/press_tr.api.auth.keycloak_callback` | `<Press adresi>/api/method/press_tr.api.keycloak_backchannel_logout` |
| `identity-sync` | Servis hesabı | İstemci kimlik bilgisi | Yok | Yok |
| `press-service` | Servis hesabı | İstemci kimlik bilgisi | Yok | Yok |

- Dönüş adresini tam adresle kaydedin. Joker karakter kullanmayın.
- Çıkış bildiriminde “oturum gerekli” ayarını açın.
- Yeni kiracı için aynı biçimi kullanın. Örneğin `site-kiraci2` yazın.
- `agent-service`, `ops-bff` ve `site-ops` bu turda yoktur.

### Hedef kapsamları

Hedef kapsamı, belirtece tek bir `aud` değeri ekleyen isteğe bağlı kapsamdır. `aud`, belirtecin hangi uygulama için olduğunu söyler.

| Kapsam | Eklediği `aud` | Kullanan |
| --- | --- | --- |
| `aud-site-kiraci1` | `site-kiraci1` | `identity-sync`, `press-service` |
| `aud-press` | `press` | `identity-sync` |

- Bu kapsamlar varsayılan değildir. İstekte `scope` ile istenir.
- Servis belirteci yalnız bir `aud` değeri taşır.
- Admin API yetkileri kiracıya giden belirtece girmez.

### Politikalar

Realm politikaları G-78 ve G-144'ü uygular. Örneğin şu ayarlar vardır:

- e-postayla giriş ve zorunlu e-posta doğrulaması,
- 300 saniyede 5 hatalı denemeden sonra kilit,
- en az 12 karakterli parola, parola geçmişi ve yaygın parola listesi,
- TOTP ve passkey,
- 30 dakika boşta kalma ve 12 saat toplam oturum süresi,
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
- İstek hem oturum çerezi hem belirteç taşıyorsa isteği reddedin.

### Çıkış belirteci

Keycloak çıkışta `logout_token` gönderir. Doğrulamada şunları denetleyin:

- imza, `iss` ve `aud`,
- `iat` değeri,
- `events` içindeki `http://schemas.openid.net/event/backchannel-logout` anahtarı,
- `sid` ya da `sub` değerinin varlığı,
- `nonce` alanının yokluğu.

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
| `platform_core.api.auth.logout` | POST | Oturum | Frappe oturumunu kapatır. Keycloak çıkış adresini döner. |
| `platform_core.api.keycloak_backchannel_logout` | POST | Misafir, çıkış belirteci | Eşleşen Frappe oturumlarını kapatır. |
| `platform_core.api.identity.provision` | POST | Servis belirteci, `azp=identity-sync` | Kullanıcıyı açar ya da günceller. Aynı istek iki kez gelirse aynı sonucu döner. |
| `platform_core.api.identity.set_enabled` | POST | Servis belirteci, `azp=identity-sync` | Kullanıcıyı açar ya da kapatır. |
| `platform_core.api.identity.change_email` | POST | Servis belirteci, `azp=identity-sync` | E-postayı `rename_doc` ile değiştirir. |
| `platform_core.api.shell.get_bootstrap` | GET | Oturum | Kullanıcıyı, rolleri, kurulu uygulamaları ve kenar çubuğunu döner. |
| `platform_core.api.meta.get_doctype` | GET | Oturum | Kullanıcının görebildiği DocType tanımını döner. `ETag` başlığı taşır. |

- `/panel` sayfası `platform_core/www/` altında durur. Sayfa CSRF belirtecini taşır (G-45). Sahibi platform-core-kabuk işidir.
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

- Press de Frappe 16 üzerinde çalışır (Proje kaydı D-7). press-tr işi `on_social_login` kancasını kaynakta doğrular. Sonra kancayı ya da kendi dönüş ucunu seçer. Yukarıdaki dönüş adresi bu seçime göre değişebilir.
- G-12'deki Press giriş, kayıt ve parola uçları 403 döner.

## 7. `identity_sync`

- Keycloak olaylarını alır. Olay kaynağı T-2 kararıyla seçilir (Proje kaydı A-10).
- Belirteci Keycloak'tan istemci kimlik bilgisiyle alır.
- `press_tr.api.identity.*` ve `platform_core.api.identity.*` uçlarını çağırır.
- Kiracı listesini ayardan okur. Geliştirmede tek kiracı `kiraci1` vardır.
- Her işlem tekrar edilebilir olmalıdır. Aynı olay iki kez gelirse sonuç değişmez.
- Başarısız olay ayrı kuyrukta bekler.
- Mutabakat elle başlatılan bir komuttur. Komut farkları raporlar.

## 8. Site ayarları

Ayarlar `site_config.json` dosyasında durur. Sır taşıyan ayar depoya girmez.

| Anahtar | Örnek | Not |
| --- | --- | --- |
| `keycloak_public_url` | `http://kimlik.localhost:<port>` | Tarayıcının gördüğü adres |
| `keycloak_internal_url` | Boş | Sunucunun ulaştığı adres |
| `keycloak_realm` | `platform` | |
| `keycloak_client_id` | `site-kiraci1` ya da `press` | |
| `keycloak_client_secret` | Sahte değer | Yalnız site ayarında ve `.env` dosyasında |
| `kimlik_marka_adi` | `Atonota` | Düğme metni bundan üretilir |
| `platform_panel_url` | `http://kiraci1.localhost:<port>/panel` | Çıkıştan sonraki adres |

## 9. Geliştirme ortamı

### Adlar

| Ad | Değer |
| --- | --- |
| Kiracı sitesi | `kiraci1.localhost` |
| Press sitesi | `press.localhost` |
| Keycloak sunucusu | `kimlik.localhost` |
| Compose proje adı | `fs-<iş adı>` |
| Ana compose dosyası | `dev/compose.yaml` |
| Kiracı compose dosyası | `dev/compose.kiraci.yaml` |
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

- `platform_core` içinde katmanı platform-core-yz işi kurar. Modül klasörü `yapay_zeka` olur.
- Önce Frappe'nin hazır MCP yolunu inceleyin (T-1). Karar sitesi bunu `frappe_mcp` olarak anar (G-84).
- Uç adresi ve araç adları o işin raporundan sonra bu dosyaya yazılır.
