# oidc_verify

Keycloak belirteçlerini doğrulayan ortak kitaplık. `platform_core` ve `press_tr` aynı kodu kullanır. Kitaplık Frappe'ye bağlı değildir. Python 3.11 ve sonrasında çalışır.

Arayüz `backend/docs/sozlesmeler.md` dosyasının 3. bölümünde sabitlendi:

```python
from oidc_verify import JwksCache, TokenError, verify_access_token, verify_id_token, verify_logout_token

cache = JwksCache(jwks_url, ttl_seconds=600)
claims = verify_access_token(token, cache=cache, issuer=iss, audience="site-kiraci1", allowed_azp={"identity-sync"}, leeway=30)
claims = verify_id_token(token, cache=cache, issuer=iss, client_id="press", nonce=nonce, leeway=30)
claims = verify_logout_token(token, cache=cache, issuer=iss, client_id="press", leeway=30)
```

## Kurallar

- Yalnız RS256 imzası kabul edilir. `none` ve öteki algoritmalar `invalid_signature` verir.
- `iss` tam eşleşir. `aud` tek değerdir ve beklenen istemcidir. `azp` izin listesinde olmalıdır.
- `exp` zorunludur. Saat payı varsayılan 30 saniyedir.
- Anahtar listesi `ttl_seconds` süresince saklanır. Bilinmeyen `kid` gelince liste bir kez yenilenir. Art arda gelen bilinmeyen `kid` istekleri listeyi 5 saniyede en çok bir kez yeniletir.
- Çıkış belirtecinde imza, `iss`, `aud`, `iat`, `events` anahtarı, `sid` ya da `sub` varlığı ve `nonce` yokluğu denetlenir.
- Geçersiz belirteçte `TokenError` yükselir. `code` alanı nedeni söyler: `malformed`, `invalid_signature`, `unknown_kid`, `wrong_issuer`, `wrong_audience`, `wrong_azp`, `expired`, `not_yet_valid`, `wrong_nonce`, `not_logout_token`.
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
