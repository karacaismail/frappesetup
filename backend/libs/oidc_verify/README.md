# oidc_verify

Keycloak belirteçlerini doğrulayan ortak kitaplık. `platform_core` ve `press_tr` aynı kodu kullanır. Kitaplık Frappe'ye bağlı değildir. Python 3.11 ve sonrasında çalışır.

Arayüz `backend/docs/sozlesmeler.md` dosyasının 3. bölümünde sabitlendi:

```python
from oidc_verify import JwksCache, TokenError, verify_access_token, verify_id_token, verify_logout_token

cache = JwksCache(jwks_url, ttl_seconds=600)
# İsteğe bağlı anahtar kelimeler: max_stale_seconds=3600, max_bytes=1_048_576, total_timeout=10.0, wait_timeout=11.0
claims = verify_access_token(token, cache=cache, issuer=iss, audience="site-kiraci1", allowed_azp={"identity-sync"}, leeway=30)
claims = verify_id_token(token, cache=cache, issuer=iss, client_id="press", nonce=nonce, leeway=30)
claims = verify_logout_token(token, cache=cache, issuer=iss, client_id="press", leeway=30)
```

## Kurallar

- Yalnız RS256 imzası kabul edilir. `none` ve öteki algoritmalar `invalid_signature` verir.
- `iss` tam eşleşir. `aud` tek değerdir ve beklenen istemcidir. `azp` izin listesinde olmalıdır.
- `exp` zorunludur. Saat payı varsayılan 30 saniyedir.
- `exp`, `iat` ve `nbf` alanları sayı olmalıdır. Liste, metin, `true` ya da sonsuz değer `malformed` verir.
- Her işlev belirtecin türünü denetler. Belirteçteki `typ` alanı servis belirtecinde `Bearer`, kimlik belirtecinde `ID`, çıkış belirtecinde `Logout` olmalıdır. `typ` alanı yoksa belirteç kabul edilir. Yanlış `typ` değeri servis ve kimlik doğrulamasında `malformed` verir. Çıkış doğrulamasında `not_logout_token` verir. Metin olmayan `typ` her yerde `malformed` verir.
- Servis ve kimlik belirtecinde `events` alanı bulunamaz. Bulunursa `malformed` verir. Böylece çıkış belirteci başka bir uçta kullanılamaz.
- Anahtar listesi `ttl_seconds` süresince saklanır. Bilinmeyen `kid` gelince liste bir kez yenilenir. Art arda gelen bilinmeyen `kid` istekleri listeyi 5 saniyede en çok bir kez yeniletir.
- Liste çekilemezse önbellekteki eski anahtarlar kullanılmaya devam eder. Yeni deneme en erken 5 saniye sonra yapılır. Listedeki tek bir bozuk anahtar kaydı atlanır, öteki anahtarlar yüklenir.
- Eski anahtarlar sınırsız süre kullanılmaz. Son başarılı çekimden sonra `ttl_seconds + max_stale_seconds` saniye geçince eski anahtarlar da reddedilir. Bu durumda `JwksUnavailable` yükselir. Yeni bir çekim başarılı olunca süre yeniden başlar. `max_stale_seconds` varsayılan 3600 saniyedir ve `JwksCache` kurucusuna anahtar kelimeyle verilir.
- Anahtar listesi yalnız HTTPS ile indirilir (G-13). Düz HTTP yalnız geliştirme adresinde kabul edilir. Geliştirme adresi `localhost`, `.localhost` ile biten bir ad ya da yerel IP adresidir. Örnek: `http://kimlik.localhost:5070`. Başka bir `http` adresi verilirse `JwksCache` kurucusu `ValueError` yükseltir.
- İndirme yönlendirmeyi izlemez. Sunucu yönlendirme yanıtı verirse çekim başarısız olur. Önbellekte güvenilir anahtar yoksa `JwksUnavailable` yükselir.
- `total_timeout`, bir indirme çağrısının süre sınırıdır. Varsayılan 10 saniyedir. Önceki işi bekleme ve adres araması bu süreye girer. Bağlantı, şifreli bağlantı, başlıklar ve gövde de bu süreye girer. Süre dolunca açık bağlantı kesilir.
- Önbellekteki anahtarın süresi geçmiş olabilir. Anahtar güvenilir süre içindeyse çağrı yenilemeyi beklemez. Başka bir çağrı yeniliyorsa önbellekteki anahtarı hemen alır.
- Her önbellek aynı anda en çok bir indirme işi çalıştırır. Önceki iş sürüyorsa yeni iş başlamaz. Çağrı önceki işin bitmesini süre sınırına kadar bekler. Önceki iş zamanında biterse yeni iş kalan süreyi kullanır.
- Çekilen yanıt en çok `max_bytes` bayt okunur. Varsayılan 1 MiB'dir. Daha büyük yanıt hata sayılır ve eski anahtarlar korunur.
- `timeout` tek bir ağ işlemini sınırlar. Varsayılan 5 saniyedir. Sistem adres aramasını kesemez. Adres araması süre dolduktan sonra biterse iş bağlantı açmadan kapanır. [Süre sınırı kararı](../../docs/kararlar/0015-oidc-verify-key-download-limit.md)
- Yenileme bekleyen çağrı en çok `wait_timeout` saniye bekler. Varsayılan `total_timeout + 1` saniyedir. Anahtar önbellekte varsa ve eski anahtar süresi dolmadıysa süre dolan çağrı o anahtarı kullanır. Başka durumda `JwksUnavailable` yükselir. Çekim kilidi her durumda bırakılır. Çekim hata verse ya da süre dolsa bile kilit bırakılır.
- Kimlik belirtecinde `nonce=None` verilirse `nonce` denetimi atlanır. Bu yalnız `nonce` göndermeyen akışlar içindir. Giriş akışı `nonce` gönderdiyse çağıran değeri vermek zorundadır.
- Çıkış belirtecinde imza, `iss`, `aud`, `exp`, `iat`, `jti`, `events` anahtarı, `sid` ya da `sub` varlığı ve `nonce` yokluğu denetlenir. `exp`, `iat` ve `jti` zorunludur. `jti` boş olmayan metin olmalıdır. `events` bir nesne olmalı ve `http://schemas.openid.net/event/backchannel-logout` anahtarının değeri de nesne olmalıdır. `sid` ve `sub` varsa boş olmayan metin olmalıdır.
- Geçersiz belirteçte `TokenError` yükselir. `code` alanı nedeni söyler: `malformed`, `invalid_signature`, `unknown_kid`, `wrong_issuer`, `wrong_audience`, `wrong_azp`, `expired`, `not_yet_valid`, `wrong_nonce`, `not_logout_token`.
- Anahtar listesi alınamazsa ve önbellekte hiç anahtar yoksa `JwksUnavailable` yükselir. Bu hata `TokenError` değildir. Belirteç geçersiz sayılmaz. Çağıran uç bu hatayı 503 benzeri geçici hata yanıtıyla karşılar. `JwksUnavailable` da `oidc_verify` paketinden içe aktarılır.
- Kitaplık belirteci günlüğe yazmaz. Hata mesajı belirteç içeriği taşımaz.

İstek düzeyindeki iki kural kitaplığın dışındadır. Çağıran uç bu iki isteği kendisi reddeder. Birincisi `cmd` alanı taşıyan istektir. İkincisi hem oturum çerezi hem belirteç taşıyan istektir.

## Bağımlılıklar

PyJWT ve `cryptography` Frappe 16 içinde zaten vardır. Aralık iki Frappe 16 kurulumundan doğrulandı (22 Kasım 2026):

| Kurulum | Python | PyJWT | cryptography |
| --- | --- | --- | --- |
| `frappe/erpnext:v16.55.0` imajı, Frappe 16.56.0 | 3.14.10 | 2.15.1 | 50.0.2 |
| Press bench'i, Frappe 16.50.0 | 3.14.8 | 2.13.0 | 50.0.2 |

Seçilen aralık `PyJWT>=2.13.0,<3` ve `cryptography>=50.0.0,<51` biçimindedir.

## Testler

Birim testleri yerelde üretilen RSA anahtarlarını kullanır. Ağ gerekmez.

```bash
cd backend/libs/oidc_verify
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e .
cd tests && ../.venv/bin/python -I -m unittest discover -s .
```

Canlı Keycloak testi `KC_PUBLIC_URL` ve `ATONOTA_IDENTITY_SYNC_SECRET` değişkenlerini ister. Değişkenler yoksa test atlanır. Keycloak ortamı `backend/identity/keycloak/README.md` dosyasında anlatılır.

## Hazır çözümle karşılaştırma

Bu kitaplığın bağımlılığı PyJWT içinde hazır bir anahtar istemcisi vardır: `jwt.PyJWKClient`. Kural A-1 ve A-2 önce bu sınıfın denenmesini ister. İki sürüm kaynağından okundu: PyJWT 2.13.0 ve 2.15.1. Dosya `jwt/jwks_client.py` dosyasıdır.

`PyJWKClient` şunları sağlar: önbellek, önbellek süresi ve soket zaman aşımı. 2.15.1 sürümü yönlendirmeyi reddeder ve kilit kullanır. 2.13.0 sürümü yönlendirmeyi izler.

Kalan fark şudur. Bu yüzden kendi önbelleğimiz kaldı:

- Anahtar sunucusu yanıt vermezse eski anahtar belli bir süre kullanılır. Bu süre `max_stale_seconds` değeridir. `PyJWKClient` önbellek süresi dolunca eski anahtarı bırakır. Sunucu yanıt vermezse hata verir.
- İndirmenin toplam süresi `total_timeout` ile sınırlıdır. Bu süre ad çözümünü ve şifreli bağlantı kurulumunu da kapsar. `PyJWKClient` yalnız soket işlemini sınırlar.
- Yenilemeyi bekleyen çağrı en çok `wait_timeout` bekler.
- Yanıt gövdesi `max_bytes` ile sınırlıdır. `PyJWKClient` gövdenin tamamını okur.
- Düz `http` adresi yalnız geliştirme adresinde kabul edilir. `PyJWKClient` her `http` adresini kabul eder.
- İki PyJWT sürümünde de yönlendirme izlenmez. `PyJWKClient` bunu yalnız 2.15.1 sürümünde yapar.

Geri dönüş koşulu: PyJWT bu farkları kapatırsa `JwksCache`, `PyJWKClient` üzerine kurulur. Dış arayüz değişmez.
