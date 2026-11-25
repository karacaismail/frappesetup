# Canlı deneme listeleri

Bu belge DevOps sorumlusu içindir. DevOps sorumlusu kıdemli DevOps mühendisidir. Belgeyi A Takımı DevOps 25 Kasım 2026 Çarşamba günü yazdı.

Belgede üç liste var:

1. Üretimde yalnız Keycloak girişi (AJA-419).
2. G-13 panel oturumu ve anlık olay.
3. AtonotA Login giriş adresi `api.login.atonota.net`.

Kodu ve yerel testleri ekip bitirdi. Canlı denemeyi DevOps sorumlusu yapar. Bu belgeyi yazan ajan sunucuya bağlanmadı.

## Okumadan önce

- Her satırda üç bilgi var: gereken ayar, komut ve kabul ölçütü.
- Değerler depodaki kod, test ve belgelerden alındı. Kaynak her satırda yazılıdır.
- Depoda bilgi yoksa satırda "bilinmiyor" yazar.
- Belgede parola, token ya da anahtar değeri yoktur.
- DNS işini alan adı sorumlusu GoDaddy'de yapar. DNS satırları ayrı yazıldı.
- Uzak sunucudaki her değişiklik onaylı değişikliktir. Önce ortamın sorumlusundan onay alın.

### Ortak adlar

Prod adları `backend/deploy/environments/prod.env` dosyasındadır:

| Ad | Değer |
| --- | --- |
| Sunucu takma adı (SSH) | `atonota-prod` |
| Giriş adresi | `api.login.atonota.net` |
| Press adresi | `press.atonota.net` |
| İlk kiracı sitesi | `demo.app.atonota.net` |
| Press anahtarı | `ATONOTA_PRESS_ENABLED=0` |

rc ortamında adlar `rc.atonota.net` tabanıyla kurulur. Örneğin giriş adresi `api.login.rc.atonota.net` olur. Harita `backend/docs/dagitim/ortamlar.md` dosyasındadır.

### Sunucuda bench komutu

Kiracı sitesinde `bench` komutu kapsayıcının içinde çalışır. Komutun biçimi `backend/deploy/remote/common.sh` içindeki `stack` işlevinden gelir.

Önce sunucuda şu kısaltmayı tanımlayın:

```bash
B=/srv/atonota/prod/backend-current
stack() { COMPOSE_PROFILES="$(sed -n 's/^COMPOSE_PROFILES=//p' "$B/release.env")" docker compose --project-name atonota-prod --env-file "$B/host.env" --env-file "$B/release.env" --file "$B/stack.yaml" "$@"; }
```

Kısaltma `COMPOSE_PROFILES` değerini `release.env` dosyasından okur. Asıl işlev de aynısını yapar.

Belgedeki `stack exec -T tenant-web bench ...` komutları bu kısaltmayı kullanır.

`/srv/atonota` yolu betiğin varsayılanıdır. Sunucuda `ATONOTA_ROOT` başka bir değerse yolu ona göre değiştirin.

## 1. Liste: üretimde yalnız Keycloak girişi (AJA-419)

### Bugünkü durum

- `identity_keycloak_only` ayarı kodda vardır. Kod `platform_core/identity/site_settings.py` dosyasındadır.
- Ayar `1` olunca parola girişi kapanır. Bunu `identity/tests/test_login_policy.py` testi gösterir.
- rc ve prod dağıtımının bu ayarı denetlemesi AJA-422 işidir. Bu iş henüz kodlanmadı. Bugün dağıtım ayarı denetlemez.
- Acil giriş belgesi AJA-423 işidir. Belge `pc/aja-419-acil-giris-belgesi` dalındadır. Dal henüz `backend` dalına birleşmedi.

### Ön koşul

1. Ön koşul: bir yönetici Keycloak ile girebilmeli.
   - Ayar: kiracı sitesinde Keycloak ayarları dolu olmalı. Zorunlu anahtarlar `keycloak_public_url`, `keycloak_client_id`, `keycloak_client_secret`, `identity_brand_name` ve `platform_panel_url` anahtarlarıdır. Kaynak `site_settings.py` dosyasıdır.
   - Komut: tarayıcıda `https://demo.app.atonota.net/login` adresini açın. Marka düğmesine basın. Bir System Manager kullanıcısıyla Keycloak'ta girin.
   - Kabul: tarayıcı panele döner. Kullanıcı System Manager yetkisiyle girmiş olur. Bu adım geçmeden 2. adıma geçmeyin.

### Deneme adımları

2. Ayarı açın.
   - Ayar: `identity_keycloak_only` değeri `1` olur.
   - Komut: `stack exec -T tenant-web bench --site demo.app.atonota.net set-config identity_keycloak_only 1`
   - Kabul: komut hatasız biter. Yeniden başlatma gerekmez. Kaynak kimlik modülünün `README.md` dosyasıdır.

3. Parolalı girişi deneyin.
   - Ayar: 2. adımdaki ayar açık kalır.
   - Komut: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://demo.app.atonota.net/api/method/login -d usr=<kullanıcı> -d pwd=<parola>`. Parolayı komut geçmişine yazmamak için deneme hesabı kullanın.
   - Kabul: yanıt `401` olur. Kaynak `test_login_policy.py` testidir.

4. `cmd` biçimini deneyin.
   - Ayar: ayar açık kalır.
   - Komut: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://demo.app.atonota.net/ -d cmd=login -d usr=<kullanıcı> -d pwd=<parola>`
   - Kabul: yanıt `401` olur. Kaynak kimlik modülünün `README.md` dosyasıdır.

5. Parola sıfırlamayı deneyin.
   - Ayar: ayar açık kalır.
   - Komut: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://demo.app.atonota.net/api/method/frappe.core.doctype.user.user.reset_password -d user=<e-posta>`
   - Kabul: yanıt `403` olur.

6. Kayıt açmayı deneyin.
   - Ayar: ayar açık kalır.
   - Komut: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://demo.app.atonota.net/api/method/frappe.core.doctype.user.user.sign_up -d email=<e-posta> -d full_name=Deneme`
   - Kabul: yanıt `403` olur.

7. E-posta bağlantısıyla girişi deneyin.
   - Ayar: ayar açık kalır.
   - Komut: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://demo.app.atonota.net/api/method/frappe.www.login.send_login_link -d email=<e-posta>`
   - Kabul: yanıt `403` olur. Kaynak `test_login_policy.py` testidir.

8. `/login` sayfasını oturumsuz açın.
   - Ayar: ayar açık kalır.
   - Komut: `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://demo.app.atonota.net/login`
   - Kabul: yanıt `302` olur. Yönlendirme `/api/method/platform_core.api.auth.start_login` yoluna gider. Kaynak `www/login.py` dosyasıdır.
   - Not: kimlik `README.md` dosyası "sayfada yalnız marka düğmesi vardır" der. Kod ise sayfayı hiç çizmez ve yönlendirir. Kod esastır.

9. Keycloak girişinin hâlâ çalıştığını deneyin.
   - Ayar: ayar açık kalır.
   - Komut: tarayıcıda yeni gizli pencere açın. `https://demo.app.atonota.net/panel` adresine gidin. Keycloak'ta girin.
   - Kabul: tarayıcı panele döner. Kapatma Keycloak dönüş ucunu etkilemez.

### Acil giriş denemesi

10. Ayarı kısa süre kapatın.
    - Ayar: `identity_keycloak_only` değeri `0` olur.
    - Komut: `stack exec -T tenant-web bench --site demo.app.atonota.net set-config identity_keycloak_only 0`
    - Kabul: 3. adımdaki komut artık `401` dönmez. `/login` sayfasında parola alanı görünür. Yeniden başlatma gerekmez.

11. Ayarı yeniden açın.
    - Ayar: `identity_keycloak_only` değeri `1` olur.
    - Komut: `stack exec -T tenant-web bench --site demo.app.atonota.net set-config identity_keycloak_only 1`
    - Kabul: 3. adım yine `401` döner. 8. adım yine `302` döner.

12. Ne yaptığınızı kayda yazın.
    - Ayar: yok.
    - Komut: yok.
    - Kabul: kayıtta hangi saatte `0` ve `1` yapıldığı yazar. Kayıtta parola, token ya da anahtar yoktur.

### Dağıtım denetimi (AJA-422)

13. Ayar `0` iken rc dağıtımının durduğunu deneyin.
    - Ayar: rc kiracı sitesinde `identity_keycloak_only` değeri `0` olur.
    - Komut: bilinmiyor. Denetim AJA-422 işiyle gelecek. Kod henüz yok.
    - Kabul: AJA-422 kabul ölçütüne göre dağıtım durur. Hata iletisi ayarın adını ve beklenen `1` değerini yazar. İleti site değerini yazmaz.
    - Bu satırı AJA-422 birleşmeden denemeyin.

## 2. Liste: G-13 panel oturumu ve anlık olay

### Bugünkü durum

- G-13 görev panosunda "Sürüyor" durumundadır. Kod kanıtı `backend/deploy/tests/test_panel_session.py` dosyasıdır.
- Canlı madde açıktır. Panel adresinde oturum çerezi ve anlık olay denenmedi.
- Panel ayrı bir `panel.` adında değildir. Panel her kiracının `/panel` yoludur. Kaynak `ortamlar.md` dosyasıdır.
- Press rc ve prod'da kapalıdır (`ATONOTA_PRESS_ENABLED=0`, engel E-2). Bu yüzden Press tarafının canlı denemesi bugün yapılamaz.

### Deneme adımları

1. Oturum çerezinin özelliklerini okuyun.
   - Ayar: yok. Dağıtılmış kiracı sitesi yeterlidir.
   - Komut: tarayıcıda `https://demo.app.atonota.net/panel` adresine gidin. Keycloak ile girin. Geliştirici araçlarında "Application" bölümünü açın. Çerezler listesinde `sid` çerezini bulun.
   - Kabul: `sid` çerezinde `Secure` ve `HttpOnly` işaretlidir. `SameSite` değeri `Lax` olur. `Domain` alanında yalnız `demo.app.atonota.net` yazar. Başında nokta yoktur.

2. `Set-Cookie` başlığını okuyun.
   - Ayar: yok.
   - Komut: 1. adımdaki girişte "Network" bölümünü açın. `keycloak_callback` yanıtını seçin. `Set-Cookie` başlığını okuyun.
   - Kabul: `sid` satırında `Domain=` özniteliği yoktur. Satırda `Secure`, `HttpOnly` ve `SameSite=Lax` vardır. Hiçbir çerez `Domain=atonota.net` yazmaz.

3. Anlık olay bağlantısını okuyun.
   - Ayar: yok.
   - Komut: girişli panelde "Network" bölümünde `WS` süzgecini seçin. Sayfayı yenileyin. `socket.io` isteğini bulun.
   - Kabul: istek `wss://demo.app.atonota.net/socket.io/` adresine gider. Ayrı bir alan adı ya da `:9000` portu yoktur. İstek `sid` çerezini taşır. Bağlantı `101` yanıtıyla açılır.

4. Anlık olayın geldiğini görün.
   - Ayar: yok.
   - Komut: bilinmiyor. Depoda panelin hangi olayı dinlediğini anlatan bir deneme yok.
   - Kabul: bilinmiyor. Ürün ekibi bir olay örneği verince satır tamamlanır.

5. Sunucuda port açılmadığını görün.
   - Ayar: yok.
   - Komut: `stack ps --format '{{.Service}} {{.Ports}}'`
   - Kabul: `tenant-web`, `press-web`, `tenant-socket` ve `press-socket` satırlarında yayınlanan port yoktur. Kaynak `test_panel_session.py` testidir.

6. Kenar vekilin şemayı ezdiğini görün.
   - Ayar: yok.
   - Komut: `curl -s -o /dev/null -D - -H 'X-Forwarded-Proto: http' https://demo.app.atonota.net/api/method/ping`
   - Kabul: yanıt `200` olur. Girişli istekte `sid` çerezi yine `Secure` gelir. Caddy dışarıdan gelen başlığı siler.

7. Press tarafını deneyin.
   - Ayar: `ATONOTA_PRESS_ENABLED=1` gerekir. Bu değer rc ve prod'da `0` kalır (E-2).
   - Komut: bilinmiyor. Press açılmadan deneme yapılamaz.
   - Kabul: `not_run` yazın. Press açılınca aynı 1. ile 3. adımlar `press.` adında Tailscale ağından denenir.

## 3. Liste: AtonotA Login `api.login.atonota.net`

### Bugünkü durum

- AtonotA Login Keycloak üzerinde çalışır. Kod `backend/identity/atonota_login/` klasöründedir.
- Açık kayıtlar `google`, `apple` ve `linkedin` kayıtlarıdır. `facebook` ve `x` kayıtları kapalıdır (`"active": false`).
- Platform panellerinin işi `backend/docs/handoff/atonota-login-platforms.md` belgesindedir.
- Gerçek platform hesapları henüz yoktur. Kaynak görev panosunun notudur.

### DNS satırı (alan adı sorumlusu)

1. Giriş adresinin DNS kaydını açın.
   - Ayar: `atonota.net` bölgesinde `api.login` adı. Kayıt türü A kaydıdır. Değer `atonota-prod` sunucusunun genel IP adresidir.
   - Komut: DevOps sorumlusu IP adresini alan adı sorumlusuna yazar. Alan adı sorumlusu kaydı GoDaddy'de girer. IP adresi depoda yoktur: bilinmiyor. IPv6 kaydı gerekip gerekmediği de depoda yoktur: bilinmiyor.
   - Kabul: `dig +short api.login.atonota.net A` komutu sunucunun IP adresini döner.

2. rc için aynı kaydı açın.
   - Ayar: `api.login.rc` adı. Değer `atonota-rc` sunucusunun genel IP adresidir.
   - Komut: Alan adı sorumlusu kaydı GoDaddy'de girer. IP adresi bilinmiyor.
   - Kabul: `dig +short api.login.rc.atonota.net A` komutu rc sunucusunun IP adresini döner.

### Deneme adımları (DevOps sorumlusu)

3. Sertifikayı ve keşif belgesini deneyin.
   - Ayar: DNS kaydı açık olmalı. Prod dağıtımı yapılmış olmalı.
   - Komut: `curl --fail -s https://api.login.atonota.net/realms/platform/.well-known/openid-configuration`
   - Kabul: `curl` sertifika hatası vermez. Yanıttaki `issuer` değeri `https://api.login.atonota.net/realms/platform` olur. Kaynak `ortamlar.md` "Kabul ölçütleri" bölümüdür.

4. Yönetici konsolunun kapalı olduğunu deneyin.
   - Ayar: yok.
   - Komut: `curl -s -o /dev/null -w '%{http_code}\n' https://api.login.atonota.net/admin/` ve `curl -s -o /dev/null -w '%{http_code}\n' https://api.login.atonota.net/realms/master/`
   - Kabul: iki yanıt da `404` olur. Kaynak `site.caddy.template` dosyasıdır.

5. Platform dönüş adreslerini alın.
   - Ayar: yok.
   - Komut: `backend/identity/atonota_login/bin/atonota-login redirects --env prod`
   - Kabul: komut her platform için bir adres yazar. Örnek `https://api.login.atonota.net/realms/platform/broker/google/endpoint` olur.

6. Platform panellerine dönüş adresini yazın.
   - Ayar: her platform için ayrı prod istemcisi açılır. Adımlar `atonota-login-platforms.md` belgesindedir.
   - Komut: platformun kendi panelinde yapılır. Komut yoktur.
   - Kabul: istemci kimliği ve sırrı `/etc/atonota/prod/keycloak.env` dosyasına yazılır. Değerler Git'e girmez. Değişken adları örneğin `ATONOTA_GOOGLE_CLIENT_ID` ve `ATONOTA_GOOGLE_CLIENT_SECRET` adlarıdır.

7. Platformları Keycloak'ta açın.
   - Ayar: `KC_BOOTSTRAP_ADMIN_USERNAME`, `KC_BOOTSTRAP_ADMIN_PASSWORD` ve platform değişkenleri ortamda dolu olmalı. Keycloak yeni değerlerle başlatılmış olmalı.
   - Komut: `KC_PUBLIC_URL=https://api.login.atonota.net backend/identity/atonota_login/bin/atonota-login apply --from-env --remote-host api.login.atonota.net`
   - Kabul: komut hatasız biter. Komut hiçbir sırrı ekrana yazmaz. Bu komut onaylı değişikliktir.

8. Giriş sayfasındaki düğmeleri sayın.
   - Ayar: 7. adım bitmiş olmalı.
   - Komut: tarayıcıda `https://demo.app.atonota.net/login` adresini açın. Marka düğmesine basın.
   - Kabul: tarayıcı `api.login.atonota.net` adresine gider. Sayfada yalnız değeri dolu ve açık platformların düğmesi görünür. `facebook` ve `x` düğmesi görünmez.

9. Bir platformla girişi deneyin.
   - Ayar: en az bir platformun değerleri dolu olmalı. Örneğin `google`.
   - Komut: 8. adımdaki sayfada platform düğmesine basın. Platformda girin.
   - Kabul: tarayıcı önce platformun kendi adresine gider. Örneğin Google için `accounts.google.com` adresine gider. Sonra `api.login.atonota.net` adresine döner. En sonda kiracının paneli açılır.

10. Kayıtsız dönüş adresinin reddedildiğini görün.
    - Ayar: yok.
    - Komut: bilinmiyor. Depoda bu deneme için hazır komut yok.
    - Kabul: platform, panelde kayıtlı olmayan dönüş adresini reddeder. Kaynak `atonota-login-platforms.md` "Kabul" bölümüdür.

11. Sağlık betiğini koşun.
    - Ayar: Jenkins'in prod anahtarları hazır olmalı.
    - Komut: `backend/deploy/bin/health prod <paket klasörü>`
    - Kabul: betik hatasız biter. Press denetimi `not_run` yazar, çünkü `ATONOTA_PRESS_ENABLED=0` değeridir.

## Teslim

Her adımın sonucunu `pass`, `fail` ya da `not_run` olarak yazın. Sonucu ilgili Paperclip işine yorum olarak ekleyin. Yoruma parola, token ya da anahtar yazmayın.
