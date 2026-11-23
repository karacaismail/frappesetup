Headless paneli `http://localhost:5180` adresinde `inceleme-panel@example.test` hesabıyla açın. Parola `backend/e2e/review-accounts.json` dosyasının `password` alanındadır.

# Uçtan uca entegrasyon testleri

## Yerel inceleme hesapları

Bu hesaplar yalnız yerel yığında kullanılır.
Yerel yığın, `backend/e2e/stack up` komutunun açtığı Keycloak, kiracı ve Press ortamıdır.
Önce yığını açın.
Sonra depo kökünden bu komutu çalıştırın.
Komut hesapları kurar ya da günceller.

```sh
PANE_PORT=<port> backend/e2e/stack review-accounts
```

Bütün hesapların parolası aynıdır.
Parola tek bir dosyada durur: `backend/e2e/review-accounts.json`.
Parola o dosyanın `password` alanındadır.
Hesap listesi de bu dosyadadır.

| Hesap | Nerede | Ne için |
| --- | --- | --- |
| `inceleme-panel@example.test` | Keycloak `platform` realm'i ve kiracı | Headless paneli inceler. Kiracıda “Employee” ve “HR User” rolleri vardır. Bir örnek çalışan kaydına bağlıdır. |
| `inceleme-yonetici@example.test` | Keycloak `platform` realm'i ve kiracı | Kiracıyı yönetir. Kiracıda “System Manager” rolü vardır. |
| `inceleme-yerel-yonetici` | Keycloak `master` realm'i | Keycloak yönetim konsolunu açar. “admin” rolü vardır. |
| `inceleme-press@example.test` | Keycloak `platform` realm'i ve Press | Press kullanıcısı olarak girer. |

Realm, Keycloak'ta kullanıcıları ve kuralları bir arada tutan alandır.
Keycloak yönetim konsolu `http://identity.localhost:<PANE_PORT>/admin/` adresindedir.

Komut önce yığının adreslerini denetler.
Adres `localhost` ya da `*.localhost` değilse komut durur.

`platform` realm'inin parola kuralı en az 12 karakter ister.
Bu kural üretim kuralıdır ve realm dosyasında değişmez.
Komut çalışırken yalnız yerel Keycloak'ta kısa bir süre 8 karakter kabul edilir.
Bu süre içinde `platform` realm'indeki her kullanıcı 8 karakterlik parola seçebilir.
Aynı parolanın yeniden yazılabilmesi için parola geçmişi kuralı da o süre kapalı kalır.
Parolalar yazılınca komut kuralı geri yükler.
Komut hata verse bile kural geri yüklenir.
Geri yüklenen kural her zaman realm dosyasındaki kuraldır.
Realm dosyası `backend/identity/keycloak/realm/platform-realm.json` dosyasıdır.
Komut kuralı çalışan Keycloak'tan okumaz.
Süreç yarıda ölürse yerel Keycloak gevşek kuralla kalabilir.
Bu durumda komutu yeniden çalıştırın.
Komut sonunda realm dosyasındaki kuralı geri yükler.

Kiracıya ve Press'e parola gitmez.
Giriş her zaman Keycloak üzerinden olur.
Komut kiracıda ve Press'te kimlik bağını kurar.
Kimlik bağı, Keycloak hesabını yerel kullanıcıya bağlayan kayıttır.

## Birleştirme önizlemesi

Resmî birleşme öncesi depo kökünden bu komutu çalıştırın.

```sh
backend/e2e/bin/merge-preview
```

Komut O-19 sırasını `preview/branches.txt` dosyasından okur.
Backend ve işçi commit'lerini başlangıçta sabitler.
Birleşmeleri ayrı bir worktree ve dal içinde yapar.
Çakışma tablosu dosyayı ve iki dalı gösterir.
Komut, tanımadığı bir çakışmada durur ve nedeni rapora yazar.
Werkzeug için onaylı çözüm `Werkzeug~=3.1.9` yazmaktır. Frappe 16.56.0, Werkzeug 3.1.9 kullanır.
Birleşen `hooks.py` dosyasında aynı üst düzey ad yeniden atanırsa komut durur.
Rapor, Git çakışması olmasa bile adı ve satırları gösterir.

Canlı koşu `PANE_PORT`, kurulu Playwright ve çalışan bir Colima profili ister.
Ağır ortam için en az 3 GiB kullanılabilir bellek gerekir.
Komut belleği seçilen Colima profilinde ölçer.
Komut o profilde örnek ortamı açar ve senaryoları çalıştırır.
Model sağlayıcısı yalnız kendi sabit yerel adres listesiyle kaydedilir.
Testten sonra geçici birimler, imajlar, derleme alanı ve worktree kaldırılır.
Rapor ve günlükler komutun yazdığı yerel klasörde kalır.

Yalnız birleşme ve kanca denetimi için şu komutu kullanın.

```sh
backend/e2e/bin/merge-preview --merge-only
python3 -m unittest discover -s backend/e2e/tests -v
node --experimental-strip-types --test backend/e2e/tests/*.test.*
```

Hata kalırsa API denemesi, geçidin hata kodunu ve sahte sağlayıcı yanıtlarını gösterir.
Önizleme, kimlik eşitleme kuyruğundan işlem adını ve HTTP kodunu saklar.

Tarayıcı girişi `site-kiraci1` istemcisini kullanır. Canlı önizleme bu istemcinin servis belirteci isteğini reddettiğini doğrular.
`site-tenant1-service` ayrı bir sır kullanır. Önizleme, bu istemcinin yalnız `identity-sync` hedefli belirteç aldığını doğrular.
Önizleme bu sırrı her koşuda yeniden üretir. Keycloak ve Frappe süreçleri sırrı ortam değişkeninden alır.

## Sonuçlar

Canlı Factory önizlemesi 22 Kasım 2026 Pazar günü çalıştı.
Önizleme kaydı `4f1495a` ile 11 dal birleşti.
Keycloak, Press, kiracı ve kimlik eşitleme sağlık denetimlerini geçti.

| Senaryo | Son Factory koşusu | Önceki sıralı koşu | Son koşudaki engel |
| --- | --- | --- | --- |
| Atonota girişi kiracı oturumunu açar. | `fail` | `pass` | Chromium ve WebKit açılmadı. |
| Eşitleme servisi “Website User” açar. | `not_run` | `pass` | API hazırlığı kiracı adresini çözemedi. |
| Keycloak çıkışı kiracı oturumunu 60 saniyede kapatır. | `fail` | `pass` | Chromium ve WebKit açılmadı. |
| Ajan belirteci yalnız izinli kayıtları listeler. | `not_run` | `pass` | API hazırlığı durdu. |
| Kayıt yalnız insan onayından sonra değişir. | `not_run` | `pass` | API hazırlığı durdu. |
| Model geçidi 429 yanıtından sonra ikinci adresi kullanır. | `not_run` | `fail` | API hazırlığı durdu. |
| Erişim kuralı liste ve tek kayıt için aynı sonucu verir. | `not_run` | `pass` | API hazırlığı durdu. |

Önceki koşuda model geçidi, sahte sağlayıcının yerel adresini reddetti.
Son koşuda bu senaryo uygulama yanıtına ulaşmadı.

## Çalıştırma

Komutları depo kökünden ve kendi Pane ortamınızda çalıştırın.
Pane, `PANE_PORT` değişkeniyle bu çalışma alanına port ayırır.

`e2e/stack up` Keycloak hazır olunca realm eşitleme adımını çalıştırır. Bu adım realm dosyasındaki istemci ve kapsamları korunan veritabanına uygular. Adım kullanıcı ve oturum silmez. Ayrıntı `identity/keycloak/README.md` dosyasının "Korunan veritabanında realm eşitleme" bölümündedir.

Ayrı Vite arayüzü için yerel yığını şu komutla açın.

```sh
PANE_PORT=7400 FS_STACK_VITE=1 backend/e2e/stack up
```

Girişi `http://localhost:5180` üzerinden başlatın.
Vite, giriş ve dönüş isteklerini `http://tenant1.localhost:7401` adresine iletir.
Vite ayarında `VITE_DEV_SITE_NAME=tenant1.localhost` değerini kullanın.
Keycloak aynı Vite adresine döner. Frappe oturum çerezini bu adreste açar.
Frappe girişten sonra `http://localhost:5180/panel` adresine yönlendirir.
`FS_STACK_VITE=1` yoksa giriş kiracı adresini kullanır.
Vite kipi açıkken Frappe, tam bağlantıları Vite adresiyle kurar.
Birleştirme önizlemesi ayrı bir yığında çalışır.

`e2e/stack` eski bir `.env` dosyasını da açar. Gizli olmayan eksik anahtarları `.env.example` dosyalarındaki yerel örnek değerle doldurur. Örneğin `ATONOTA_MCP_REDIRECT_URI` ve `ATONOTA_MCP_RESOURCE_URL` böyledir. Betik `.env` dosyasını değiştirmez. Gizli bir anahtar eksikse betik Docker'a dokunmadan durur. Betik eksik anahtarın yalnız adını yazar, değer yazmaz. Örneğin `ATONOTA_MCP_INTROSPECTION_SECRET` böyledir. Eksik anahtarı `.env.example` dosyasından `.env` dosyanıza kopyalayın ve kendi değerinizi yazın.

### Colima profilleri

- **Mevcut Factory ortamı.** Betik yalnız mevcut imajı ve siteyi yeniden kullanır. Factory diskinde en az 5 GiB boş alan gerekir.
- **Yeni ortam.** `FS_COLIMA_PROFILE=default` kullanın. Betik açmadan önce `colima ssh -- free -g` ile belleği ölçer. Alt sınır 2 GB'tır.
- **Press ortamı.** `FS_COLIMA_PROFILE=default` ile `environment.sh --press up` komutunu kullanın. Alt bellek sınırı 3 GB'tır. Betik, Press ve Keycloak dosyaları eksikse ölçümden sonra durur.

Mevcut kiracı imajı, son derlemede alınan kodu taşır.
Kiracı kodu değişirse imajı güncelleyin ve sonra testleri çalıştırın.

### Tarayıcıları Colima içinde çalıştırma

```sh
E2E_BROWSER_RUNTIME=container FS_COLIMA_PROFILE=default backend/e2e/bin/merge-preview
```

Komut mevcut Playwright imajını kullanır. İmaj ve kurulu paket aynı ana ve alt sürümde olmalıdır.
Chromium ve WebKit, geçici ortamın Docker ağında çalışır.
Yerel ağ bağlantısı, tarayıcıdaki site adreslerini ve HTTP başlıklarını korur.
Komut dört tarayıcı dosyasını seçer. Örnek verisi eksik testler `not_run` olarak görünür.
Bu seçenekte ayrı API test grubu çalışmaz.
Varsayılan profilde bellek yetmezse `FS_COLIMA_PROFILE=factory` ile deneyin.

Kalan tarayıcı senaryoları için `E2E_FULL_BROWSER_FIXTURES=1` de ekleyin.
Önizleme, her tarayıcı için ayrı örnek hesaplar açar. Parolaları çalışırken üretir.
Çalışan oturumu testi iki tarayıcıda aynı anda ilerler. Test gerçek saatte bir saat bekler.
Önizleme, telefon iptali için geçici HTTPS sertifikasını çalışırken üretir.
Sertifika yalnız geçici kiracı ortamında güvenilir sayılır. Ortam kapanınca dosyalar silinir.

### Press gerektirmeyen testler

1. Yeni kiracı için `FS_COLIMA_PROFILE=default backend/e2e/environment.sh up` çalıştırın.
2. Aşağıdaki örnek veriyi hazırlayın.
3. İlgili test grubunu çalıştırın.
4. `FS_COLIMA_PROFILE=default backend/e2e/environment.sh down` komutuyla ortamı kapatın.

Varsayılan profilde `down`, geçici birimleri ve bu ortamın imaj etiketini siler.
Factory'de `down`, yeniden kullanılan mevcut veri birimlerini korur.
Aynı Pane için bir seferde tek ortam açın.

```sh
npx --no-install playwright test -c backend/e2e/playwright.config.ts --list
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=chromium --project=webkit
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=api
```

Silme testinin ayar dosyası yüklüyken iki motorlu genel komutu çalıştırmayın. `E2E_PRESS_DELETION=1` ayarı silme testlerini açar.
Chromium'daki test deneme hesabını tüketir. WebKit'teki test aynı hesapla kalır. Her motor için ayrı `seed-deletion` gerekir.
Komutlar "Press'ten hesap silme ve HRMS TR çalışan kaydı" bölümündedir.

## Örnek veri

Yalnız yerel test ortamını kullanın. Gerçek hesap veya veri kullanmayın.
Önizleme, erişim kuralı örnek verisini `seed_access_fixture()` ile hazırlar.
İşlev bir okuyucu hesabı ve bir erişim kuralı oluşturur.
İşlev iki örnek kayıt ekler.
Okuyucu yalnız kendi kaydını görebilir. İşlev okuyucu için geçici parola üretir.
Parolaları, oturum çerezlerini ve anahtarları yalnız yerel ortam değişkenlerine koyun.

- **Tarayıcı.** Keycloak'a doğrulanmış `e2e-user@example.test` hesabını ekleyin. Kiracıya aynı e-postayla bir “Website User” ekleyin. Parolasını `E2E_KEYCLOAK_PASSWORD` değişkenine verin. Kiracı ile Keycloak'ı kendi yerel adreslerinde bağlayın.
- **Kullanıcı eşitleme.** Keycloak'ta kullanıcı ve kuruluş yazabilen bir servis istemcisi açın. İstemci kimliğini `E2E_SYNC_KEYCLOAK_CLIENT`, sırrını `E2E_SYNC_KEYCLOAK_SECRET` değişkenine verin. Test her koşuda `e2e-sync-<kimlik>@example.test` biçiminde yeni bir örnek hesap üretir ve `tenant1` kuruluşuna ekler. Servis ile teste aynı `IDENTITY_SYNC_WEBHOOK_SECRET` değerini verin.
- **Yetki ve onay.** Örnek kayıt türünü `E2E_DOCTYPE` değişkenine verin. Örnek kayıt adlarını `E2E_VISIBLE_RECORD` ve `E2E_HIDDEN_RECORD` değişkenlerine verin. Okuyucu yalnız ilk kayda erişebilmeli. Yetkili test hesabı iki kaydı da okuyabilmeli. Bu hesap ilk kaydı değiştirebilmeli. Yazılabilir metin alanının adını `E2E_UPDATE_FIELD` değişkenine verin.
- **Oturumlar.** Okuyucu için `E2E_READER_COOKIE` ve `E2E_READER_CSRF` kullanın. Yetkili hesap için `E2E_OPERATOR_COOKIE` ve `E2E_OPERATOR_CSRF` kullanın. CSRF değeri, sitenin yazma isteğini doğruladığı oturum anahtarıdır.
- **Model geçidi.** `backend/e2e/environment.sh provider` komutuyla sahte sağlayıcıyı açın. `e2e-local-only` yoluna iki kimliksiz Ollama uyumlu adres ekleyin. Yol kaydının adını `E2E_MODEL_ROUTE` değişkenine verin. İlk adres `http://e2e-provider:<PANE_PORT+7>/limited` olur. İkinci adres `http://e2e-provider:<PANE_PORT+7>/fallback` olur. İkinci API kaydının adını `E2E_FALLBACK_API` değişkenine verin. Bu yola gerçek sağlayıcı eklemeyin. Tekrar öncesi ilk adresin bekleme süresi dolmalı.

## Sihirli bağlantı ve telefon paketi

Bu iki test grubu, örnek ortam hazır olunca açılır.

- **Sihirli bağlantı.** `E2E_MAGIC_LINK=1` kullanın. Mailpit, `PANE_PORT + 6` adresinde çalışmalı. Doğrulanmış test e-postasını `E2E_MAGIC_EMAIL` değişkenine verin. İkinci doğrulaması açık hesabı `E2E_MAGIC_OTP_EMAIL` değişkenine verin. Keycloak kaydındaki ham UTF-8 gizli metnin Base32 karşılığını `E2E_MAGIC_OTP_SEED` değişkenine verin. Etkin bağlantı süresini saniye olarak `E2E_MAGIC_TTL_SECONDS` değişkenine verin. Üst sınır 300 saniyedir.
- **Telefon paketi.** `E2E_MOBILE_PKCE=1` kullanın. Keycloak'ta herkese açık test istemcisine PKCE S256 şartı koyun. İstemciyi ve dönüş adresini `E2E_MOBILE_CLIENT_ID` ve `E2E_MOBILE_REDIRECT_URI` ile verin. Dönüş adresi yerel olmalı. İzin kapsamını ve hedefi `E2E_MOBILE_SCOPE` ve `E2E_MOBILE_AUDIENCE` ile verin. CORS için izinli kökeni `E2E_MOBILE_ORIGIN` ile verin. Örnek hesabı ve parolasını `E2E_MOBILE_EMAIL` ve `E2E_MOBILE_PASSWORD` ile verin. Ret denemeleri için `E2E_MOBILE_EXPIRED_TOKEN` ve `E2E_MOBILE_SESSION_COOKIE` hazırlayın. Test, yanlış hedefli belirteci kullanmadan hemen önce kendisi üretir.

Sihirli bağlantı için `magic-link.spec.ts` dosyasını seçin.
Telefon paketi için `mobile-pkce.spec.ts` dosyasını seçin.

## Press'ten hesap silme ve HRMS TR çalışan kaydı

Bu test MVP testi 2'nin 5e satırını kapatır. Test dosyası `press-deletion.spec.ts` dosyasıdır.
Test ortak yığında çalışır. Yığın, kiracıya HRMS TR kurar ve Keycloak ayarlarını yazar.

Zincir şöyle ilerler:

1. Müşteri Press'te hesabını silmek ister. Press, Keycloak'ta yeni bir giriş ister.
2. Press, isteği kimlik eşitleme servisine gönderir.
3. Servis Press'i ve kiracıyı sırayla kapatır ve anonim yapar.
4. Servis en son Keycloak hesabını siler. Test bu silmeyi bekler.
5. Test kiracıyı yalnız okur. Servisin açtığı silme kaydı “Anonymized” olmalıdır. Eski kullanıcı yok, anonim kullanıcı kapalı olmalıdır. Kimlik bağı silinmiş, çalışan kaydının kişisel alanları temizlenmiş olmalıdır. Bu okumalar geçmeden test ilerlemez.
6. Test en son tekrar çağrı sözleşmesini sınar. Kiracının anonim yapma ucunu servis belirteciyle çağırır. Kiracı 200 ile `anonymized: true`, `found: true`, anonim kullanıcı adı ve “Anonymized” durumunu döner. Yeni silme kaydı açılmaz.

Aynı dosyada bir negatif test vardır. Test taze deneme hesabıyla çalışır. Bu hesapta servis kiracıya hiç dokunmamıştır.
Negatif test 5. adımdaki okumaların bu durumda kaldığını doğrular. Servis kiracıyı atlarsa asıl test aynı yerde kalır.
Negatif test yalnız okur. İki test aynı deneme hesabını sırayla kullanır.

Komutları depo kökünden çalıştırın.

```sh
backend/e2e/stack seed-deletion
set -a; . .pane/scratch/e2e-deletion.env; set +a
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=chromium press-deletion.spec.ts
```

WebKit için komutları yeniden çalıştırın. Önce yeni `seed-deletion`, sonra `--project=webkit` ile test. Bir deneme hesabı tek motor için yeter.
İki motoru tek komutta çalıştırmayın. İkinci motor tüketilmiş hesapla kalır.

`seed-deletion` yeni bir deneme hesabı, bir şirket ve kişisel alanları dolu bir çalışan kaydı açar.
Komut ayrıca yalnız kullanıcı okuyan bir Keycloak istemcisi hazırlar. Test bu istemciyle Keycloak hesabının silindiğini doğrular.
Komut kimlik eşitleme servisinin kısa ömürlü belirtecini de alır. Belirteç 300 saniye yaşar. Testi bu süre içinde çalıştırın.
Her test koşusu için komutu yeniden çalıştırın. Silinen hesap bir daha açılamaz.
Test ayar dosyasını Git'e eklemeyin. Dosya parola, servis belirteci ve iki yönetici oturumu taşır.
Yönetici oturumları kiracıda ve Press'te okuma içindir. Test bitince bu oturumları kapatır. Test hiç çalışmazsa oturumlar süresi dolana kadar açık kalır.

## Hesap ve oturum testleri

| Senaryo | Sonuç | Neden veya önkoşul |
| --- | --- | --- |
| Müşteri hesabını siler. | `fail` (Chromium ve WebKit) | Kiracı yanıtında `anonymized` ve `found` alanları eksik. Sahip iş `platform-core-kimlik`. |
| Yönetici telefonu iptal eder. | `not_run` | Mobil kimlik doğrulaması ve Keycloak oturumu iptal ucu. |
| Çalışan bir saat boşta kalır. | `not_run` | Çalışan için süre ayarı ve zorunlu yeniden doğrulama. |

Bu senaryoları yalnız ayrı bir yerel test ortamında açın.
Birleştirme önizlemesi her senaryo için ayrı bir örnek hesap hazırlar.
Önizleme hesapları kiracıya bağlar. Silme hesabını Press’e de bağlar.
Silme testi, kiracıda kalacak örnek iş kaydını kullanır.
Telefon ve okuma oturumları hazır olmadan ilgili testleri açmayın.
Çalışan testi için tarayıcı ve bir saatlik koşu süresi gerekir.
Silme ve iptal için her koşuda yeni örnek veri hazırlayın.
Önkoşullar eksikse ilgili ayarı kapalı bırakın. Playwright nedeni test kaydına yazar.

- **Hesap silme.** Press silme sayfası ve silme servisi hazırsa `E2E_ACCOUNT_DELETION=1` kullanın. Test, Press üzerinden başlar. Müşteri Keycloak’ta yeniden giriş yapar ve Press’te silmeyi onaylar. Müşteri e-postası `e2e-delete-` ile başlamalı ve `@example.test` ile bitmeli. `E2E_DELETE_*` ayarlarına müşteri kimliğini, erişim bilgilerini ve örnek iş kaydını verin. `E2E_DELETE_RECORD_ANONYMOUS_VALUE` alanına beklenen değeri JSON olarak verin. Örneğin boş değer için `null` kullanın.
- **Telefon iptali.** `E2E_MOBILE_SESSION_REVOKE=1` kullanın. Telefon hesabı `e2e-revoke-` ile başlamalı ve `@example.test` ile bitmeli. `E2E_REVOKE_*` ayarlarına telefon kurulumunu, belirteçlerini ve yönetici oturumunu verin. `E2E_MOBILE_CLIENT_ID` herkese açık test istemcisini gösterir.
- **Keycloak okuma yetkisi.** İlk iki senaryo `E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN` ayarını ister. Bu belirteç yerel örnek kullanıcı ve oturumlarını okumalıdır.
- **Çalışan oturumu.** `E2E_EMPLOYEE_IDLE=1` kullanın. Çalışan hesabı `e2e-employee-` ile başlamalı ve `@example.test` ile bitmeli. Hesabı `E2E_EMPLOYEE_EMAIL` ile verin. Parolayı `E2E_EMPLOYEE_PASSWORD` ile verin. Test gerçek saatte bir saat bekler. Test bu sırada yalnız Keycloak oturumunu kontrol eder.

`playwright test -c backend/e2e/playwright.config.ts --project=chromium lifecycle.spec.ts` komutunu kullanın.

### Press silme sayfası test sözleşmesi

Press, hesap silme formunu `/account-deletion` sayfasında gösterir.
Testler aşağıdaki seçicileri ve değerleri kullanır.

| Seçici | Beklenen davranış |
| --- | --- |
| `#account-deletion` | Form, `POST /api/method/press_tr.api.account.request_deletion` ucuna bağlıdır. |
| `#account-deletion[data-confirm="false"]` | Gönderme düğmesi yeniden giriş akışını başlatır. |
| `#account-deletion[data-confirm="true"]` | Press bu değeri yeniden giriş doğrulandıktan sonra gösterir. |
| `#account-deletion button[type=submit]` | Düğme, formun o adımdaki işlemini başlatır. |

Son gönderim JSON gövdesinde `confirm: true` taşır.
Press başarılı istekte `message.submitted: true` döndürür.
Bu kayıt, Press şablonunun `3f53c3f` sürümüyle denetlendi.
