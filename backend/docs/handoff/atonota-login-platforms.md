# AtonotA Login giriş platformlarının dış işi

Bu not DevOps sorumlusu içindir. Not 23 Kasım 2026 Pazartesi günü yazıldı. Not her platformun kendi panelinde yapılacak işi anlatır.

Platform, kullanıcının oturum açtığı dış hizmettir. Örneğin Google bir platformdur. Platformun paneli, o hizmetin geliştirici ekranıdır.

## Her platformda aynı olan adımlar

1. DevOps sorumlusu platformun panelinde bir istemci açar. İstemci, AtonotA Login'in o platformdaki kaydıdır.
2. DevOps sorumlusu dönüş adresini panele tam adres olarak yazar. Yıldız ya da yol parçası yazılmaz.
3. Platform bir istemci kimliği ve bir istemci sırrı verir.
4. DevOps sorumlusu iki değeri sunucudaki `keycloak.env` dosyasına yazar. Dosya `/etc/atonota/<ortam>/keycloak.env` yolundadır. Değerler Git'e girmez.
5. DevOps sorumlusu Keycloak'ı yeni değerlerle başlatır.
6. DevOps sorumlusu `atonota-login apply` komutunu çalıştırır. Komut, değerleri dolu olan platformu açar.

Açma komutunun biçimi şudur:

```bash
KC_PUBLIC_URL=https://api.login.atonota.net \
  backend/identity/atonota_login/bin/atonota-login apply --from-env --remote-host api.login.atonota.net
```

Komut yönetici adını ve parolasını `KC_BOOTSTRAP_ADMIN_USERNAME` ve `KC_BOOTSTRAP_ADMIN_PASSWORD` değişkenlerinden okur. Platform sırlarını da ortamdan okur. Komut hiçbir sırrı ekrana yazmaz. Uzak sunucuda bu komut onaylı bir değişikliktir. Önce ortamın sorumlusundan onay alın.

Bir platformu kapatmak için iki yol vardır:

- Platformun değerlerini `keycloak.env` dosyasından silin. Sonra komutu yeniden çalıştırın.
- Platform kaydına `"active": false` yazın. Bu yol bütün ortamlarda platformu kapatır.

## Dönüş adresleri

Dönüş adresi her ortamda değişir. Adres şu biçimdedir:

```text
https://api.login.<ortam tabanı>/realms/platform/broker/<platform>/endpoint
```

Prod ortamında ortam tabanı `atonota.net` olur. alpha ortamında `alpha.atonota.net` olur. Bütün adresleri şu komut yazar:

```bash
backend/identity/atonota_login/bin/atonota-login redirects --env all
```

Her ortam için platform panelinde ayrı istemci açın. Böylece alpha'nın sırrı prod'da çalışmaz.

## Platformlar

### Google: `google`

- Tarayıcı Google'ın `accounts.google.com` adresine gider.
- Panel Google Cloud Console'dur. "APIs & Services" bölümünde "OAuth consent screen" ekranını doldurun.
- "Credentials" bölümünde "OAuth client ID" açın. Tür olarak "Web application" seçin.
- "Authorized redirect URIs" alanına dönüş adresini yazın. Prod adresi `https://api.login.atonota.net/realms/platform/broker/google/endpoint` olur.
- Değerler `ATONOTA_GOOGLE_CLIENT_ID` ve `ATONOTA_GOOGLE_CLIENT_SECRET` değişkenlerine yazılır.

### Apple: `apple`

- Tarayıcı Apple'ın `appleid.apple.com` adresine gider.
- Panel Apple Developer hesabıdır. Bir "Services ID" kaydı açın.
- Bu kayıtta "Sign in with Apple" özelliğini açın.
- "Return URLs" alanına dönüş adresini yazın. Prod adresi `https://api.login.atonota.net/realms/platform/broker/apple/endpoint` olur.
- Bir anahtar üretin ve `.p8` dosyasını indirin.
- Apple dört değer ister. Değerler `ATONOTA_APPLE_CLIENT_ID`, `ATONOTA_APPLE_TEAM_ID`, `ATONOTA_APPLE_KEY_ID` ve `ATONOTA_APPLE_P8_KEY` değişkenlerine yazılır.

### Facebook: `facebook`

- Tarayıcı Facebook'un `graph.facebook.com` adresinden giriş ekranına gider.
- Panel Meta for Developers sitesidir. Bir uygulama açın ve "Facebook Login" ürününü ekleyin.
- "Valid OAuth Redirect URIs" alanına dönüş adresini yazın. Prod adresi `https://api.login.atonota.net/realms/platform/broker/facebook/endpoint` olur.
- Uygulama yayına alınmadan yalnız test kullanıcıları girebilir. Yayın için Meta'nın uygulama incelemesi gerekir.
- Değerler `ATONOTA_FACEBOOK_CLIENT_ID` ve `ATONOTA_FACEBOOK_CLIENT_SECRET` değişkenlerine yazılır.

### LinkedIn: `linkedin`

- Tarayıcı LinkedIn'in `www.linkedin.com` adresine gider.
- Panel LinkedIn Developers sitesidir. Bir uygulama açın.
- Uygulamaya "Sign In with LinkedIn using OpenID Connect" ürününü ekleyin.
- "Authorized redirect URLs" alanına dönüş adresini yazın. Prod adresi `https://api.login.atonota.net/realms/platform/broker/linkedin/endpoint` olur.
- Uygulama bir LinkedIn şirket sayfasına bağlanmalıdır. Sayfayı ürün sahibi seçer.
- Değerler `ATONOTA_LINKEDIN_CLIENT_ID` ve `ATONOTA_LINKEDIN_CLIENT_SECRET` değişkenlerine yazılır.

### X: `x`

- Tarayıcı X'in `api.twitter.com` adresine gider. X bu adresi kendi adresine yönlendirebilir.
- Panel X Developer Portal'dır. Bir uygulama açın ve "User authentication settings" ekranını doldurun.
- "Callback URI" alanına dönüş adresini yazın. Prod adresi `https://api.login.atonota.net/realms/platform/broker/x/endpoint` olur.
- Keycloak 26.8.2'nin X sağlayıcısı OAuth 1.0a kullanır. Bu yüzden "API Key" ve "API Key Secret" değerleri gerekir. OAuth 2.0 istemci değerleri bu sağlayıcıda çalışmaz.
- X, OAuth 1.0a girişini kapatırsa kayıt genel OIDC sağlayıcısına geçer. Bu geçiş yalnız kayıt dosyasını değiştirir.
- Değerler `ATONOTA_X_CLIENT_ID` ve `ATONOTA_X_CLIENT_SECRET` değişkenlerine yazılır.

## Alan adı işi

Giriş adresinin DNS kaydını DevOps sorumlusu hazırlar. Alan adı sorumlusu kaydı `atonota.net` bölgesine yazar. Kayıtların listesi `docs/dagitim/ortamlar.md` dosyasındadır.

## Kabul

- Giriş sayfasında yalnız açılan platformların düğmesi görünür.
- Düğmeye basınca tarayıcı platformun kendi adresine gider.
- Platform işini bitirince tarayıcı `api.login.<ortam tabanı>` adresine döner.
- Panelde kayıtlı olmayan dönüş adresini platform reddeder.
