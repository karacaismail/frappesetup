# Uçtan uca entegrasyon testleri

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
Birleşen `hooks.py` dosyasında aynı üst düzey ad yeniden atanırsa komut durur.
Rapor, Git çakışması olmasa bile adı ve satırları gösterir.

Canlı koşu, `PANE_PORT`, kurulu Playwright ve varsayılan Colima'yı ister.
Ağır ortam için en az 3 GB kullanılabilir bellek gerekir.
Komut varsayılan Colima'da örnek ortamı açar ve senaryoları koşar.
Model sağlayıcısı yalnız kendi sabit yerel adres listesiyle kaydedilir.
Testten sonra geçici birimler, imajlar, derleme alanı ve worktree kaldırılır.
Rapor ve günlükler komutun yazdığı yerel klasörde kalır.

Yalnız birleşme ve kanca denetimi için şu komutu kullanın.

```sh
backend/e2e/bin/merge-preview --merge-only
python3 -m unittest discover -s backend/e2e/tests -v
```

## Sonuçlar

| Senaryo | Sonuç | Eksik parça |
| --- | --- | --- |
| Atonota girişi kiracı oturumunu açar. | `not_run` | Keycloak, giriş teması ve kiracı girişi. |
| Kullanıcı eşitleme servisi “Website User” açar. | `not_run` | Keycloak, eşitleme servisi ve kiracı kimlik ucu. |
| Keycloak çıkışı kiracı oturumunu 60 saniyede kapatır. | `not_run` | Keycloak ve kiracı çıkış ucu. |
| Aracı belirteci yalnız izinli kayıtları listeler. | `not_run` | Yapay zekâ erişim katmanı. |
| Kayıt yalnız insan onayından sonra değişir. | `not_run` | Yapay zekâ erişim katmanı. |
| Model geçidi 429 yanıtından sonra ikinci adresi kullanır. | `not_run` | Model geçidi. |
| Erişim kuralı liste ve tek kayıt için aynı sonucu verir. | `not_run` | Erişim kuralı motoru. |

Kiracı ortamı açıldı. Kiracı, `ping` isteğine yanıt verdi.
Container içinde Frappe 16.56.0 ve ERPNext 16.55.0 çalıştı.

Playwright 1.64.0 güncel yapılandırmada 21 test buldu.
Chromium ve WebKit ön denemeleri giriş düğmesini bulamadı.
Bu sonuç, kiracı girişi henüz birleşmediği için bekleniyordu.

Önizlemedeki yapay zekâ sözleşmesi, `list_documents` sonucunda `documents` alanını tanımlar.

Sahte sağlayıcı **429** ve **200** sırasını doğruladı.
Kiracı ağı da sahte sağlayıcıya ulaştı.

| İlgili dal | Birleştirme notu |
| --- | --- |
| `kimlik-realm`, `press-tr` | Dosyalar birleşince ana Compose dosyasına ekleyin. Açma betiği için servis ve port adlarını doğrulayın. |
| `platform-core-kimlik`, `platform-core-kabuk` | Tarayıcı ön denemesi `/panel` sayfasında “Atonota ile oturum aç” düğmesini bulamadı. Bu akışı dallar birleşince tekrar sınayın. |
| `identity-sync`, `platform-core-yz`, `platform-core-gecit`, `erisim-kurali` | İlgili uçlar birleşince örnek veriyi hazırlayın. Sonra testleri çalıştırın. |

## Çalıştırma

Komutları depo kökünden ve kendi Pane ortamınızda çalıştırın.
Pane, `PANE_PORT` değişkeniyle bu çalışma alanına port ayırır.

### Colima profilleri

- **Mevcut Factory ortamı.** Betik yalnız mevcut imajı ve siteyi yeniden kullanır. Factory diskinde en az 5 GiB boş alan gerekir.
- **Yeni ortam.** `FS_COLIMA_PROFILE=default` kullanın. Betik açmadan önce `colima ssh -- free -g` ile belleği ölçer. Alt sınır 2 GB'tır.
- **Press ortamı.** `FS_COLIMA_PROFILE=default` ile `environment.sh --press up` komutunu kullanın. Alt bellek sınırı 3 GB'tır. Press ve Keycloak birleşene kadar betik ölçümden sonra durur.

Mevcut kiracı imajı, son derlemede alınan kodu taşır.
Kiracı kodu değişirse imajı güncelleyin ve sonra testleri çalıştırın.

### Press gerektirmeyen testler

1. Yeni kiracı için `FS_COLIMA_PROFILE=default backend/e2e/environment.sh up` çalıştırın.
2. Aşağıdaki örnek veriyi hazırlayın.
3. İlgili test grubunu çalıştırın.
4. `FS_COLIMA_PROFILE=default backend/e2e/environment.sh down` komutuyla ortamı kapatın.

Varsayılan profilde `down`, bu test ortamının geçici birimlerini siler.
Factory'de `down`, yeniden kullanılan mevcut veri birimlerini korur.
Aynı Pane için bir seferde tek ortam açın.

```sh
npx --no-install playwright test -c backend/e2e/playwright.config.ts --list
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=chromium --project=webkit
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=api
```

## Örnek veri

Yalnız yerel test ortamını kullanın. Gerçek hesap veya veri kullanmayın.
Parolaları, oturum çerezlerini ve anahtarları yalnız yerel ortam değişkenlerine koyun.

- **Tarayıcı.** Keycloak'a doğrulanmış `e2e-user@example.test` hesabını ekleyin. Kiracıya aynı e-postayla bir “Website User” ekleyin. Parolasını `E2E_KEYCLOAK_PASSWORD` değişkenine verin. Kiracı ile Keycloak'ı kendi yerel adreslerinde bağlayın.
- **Kullanıcı eşitleme.** Her koşu için Keycloak'a yeni bir örnek hesap ekleyin. Örneğin `e2e-sync-02@example.test` kullanın. Hesabı Keycloak'ta doğrulanmış olarak işaretleyin. Hesabı `E2E_SYNC_EMAIL` değişkenine verin. Kullanıcı kimliğini `E2E_SYNC_SUBJECT` değişkenine verin. Servis ile teste aynı `IDENTITY_SYNC_WEBHOOK_SECRET` değerini verin. Bu hesap deneme öncesinde kiracıda bulunmamalı.
- **Yetki ve onay.** Örnek kayıt türünü `E2E_DOCTYPE` değişkenine verin. Örnek kayıt adlarını `E2E_VISIBLE_RECORD` ve `E2E_HIDDEN_RECORD` değişkenlerine verin. Okuyucu yalnız ilk kayda erişebilmeli. Yetkili test hesabı iki kaydı da okuyabilmeli. Bu hesap ilk kaydı değiştirebilmeli. Yazılabilir metin alanının adını `E2E_UPDATE_FIELD` değişkenine verin.
- **Oturumlar.** Okuyucu için `E2E_READER_COOKIE` ve `E2E_READER_CSRF` kullanın. Yetkili hesap için `E2E_OPERATOR_COOKIE` ve `E2E_OPERATOR_CSRF` kullanın. CSRF değeri, sitenin yazma isteğini doğruladığı oturum anahtarıdır.
- **Model geçidi.** `backend/e2e/environment.sh provider` komutuyla sahte sağlayıcıyı açın. `e2e-local-only` yoluna iki kimliksiz Ollama uyumlu adres ekleyin. Yol kaydının adını `E2E_MODEL_ROUTE` değişkenine verin. İlk adres `http://e2e-provider:<PANE_PORT+7>/limited` olur. İkinci adres `http://e2e-provider:<PANE_PORT+7>/fallback` olur. İkinci API kaydının adını `E2E_FALLBACK_API` değişkenine verin. Bu yola gerçek sağlayıcı eklemeyin. Tekrar öncesi ilk adresin bekleme süresi dolmalı.

## Sihirli bağlantı ve telefon paketi

Bu iki test grubu, örnek ortam hazır olunca açılır.

- **Sihirli bağlantı.** `E2E_MAGIC_LINK=1` kullanın. Mailpit, `PANE_PORT + 6` adresinde çalışmalı. Doğrulanmış test e-postasını `E2E_MAGIC_EMAIL` değişkenine verin. İkinci doğrulaması açık hesabı `E2E_MAGIC_OTP_EMAIL` değişkenine verin. Bu hesabın Base32 anahtarını `E2E_MAGIC_OTP_SEED` değişkenine verin. Etkin bağlantı süresini saniye olarak `E2E_MAGIC_TTL_SECONDS` değişkenine verin. Üst sınır 300 saniyedir.
- **Telefon paketi.** `E2E_MOBILE_PKCE=1` kullanın. Keycloak'ta herkese açık test istemcisine PKCE S256 şartı koyun. İstemciyi ve dönüş adresini `E2E_MOBILE_CLIENT_ID` ve `E2E_MOBILE_REDIRECT_URI` ile verin. Dönüş adresi yerel olmalı. İzin kapsamını ve hedefi `E2E_MOBILE_SCOPE` ve `E2E_MOBILE_AUDIENCE` ile verin. CORS için izinli kökeni `E2E_MOBILE_ORIGIN` ile verin. Örnek hesabı ve parolasını `E2E_MOBILE_EMAIL` ve `E2E_MOBILE_PASSWORD` ile verin. Ret denemeleri için `E2E_MOBILE_EXPIRED_TOKEN`, `E2E_MOBILE_WRONG_AUDIENCE_TOKEN` ve `E2E_MOBILE_SESSION_COOKIE` hazırlayın.

Sihirli bağlantı için `magic-link.spec.ts` dosyasını seçin.
Telefon paketi için `mobile-pkce.spec.ts` dosyasını seçin.

## Hesap ve oturum testleri

| Senaryo | Sonuç | Eksik önkoşul |
| --- | --- | --- |
| Müşteri hesabını siler. | `not_run` | Keycloak silme adımı, imzalı olay ve hesap kapatma akışı. |
| Yönetici telefonu iptal eder. | `not_run` | Mobil kimlik doğrulaması ve Keycloak oturumu iptal ucu. |
| Çalışan bir saat boşta kalır. | `not_run` | Çalışan için süre ayarı ve zorunlu yeniden doğrulama. |

Bu senaryoları yalnız ayrı bir yerel test ortamında açın.
Silme ve iptal için her koşuda yeni örnek veri hazırlayın.
Önkoşullar eksikse ilgili ayarı kapalı bırakın. Playwright nedeni test kaydına yazar.

- **Hesap silme.** Press silme sayfası ve silme servisi hazırsa `E2E_ACCOUNT_DELETION=1` kullanın. Test, Press üzerinden başlar. Müşteri Keycloak’ta yeniden giriş yapar ve Press’te silmeyi onaylar. Müşteri e-postası `e2e-delete-` ile başlamalı ve `@example.test` ile bitmeli. `E2E_DELETE_*` ayarlarına müşteri kimliğini, erişim bilgilerini ve örnek iş kaydını verin. `E2E_DELETE_RECORD_ANONYMOUS_VALUE` alanına beklenen değeri JSON olarak verin. Örneğin boş değer için `null` kullanın.
- **Telefon iptali.** `E2E_MOBILE_SESSION_REVOKE=1` kullanın. Telefon hesabı `e2e-revoke-` ile başlamalı ve `@example.test` ile bitmeli. `E2E_REVOKE_*` ayarlarına telefon kurulumunu, belirteçlerini ve yönetici oturumunu verin. `E2E_MOBILE_CLIENT_ID` herkese açık test istemcisini gösterir.
- **Keycloak okuma yetkisi.** İlk iki senaryo `E2E_LIFECYCLE_KEYCLOAK_READER_TOKEN` ayarını ister. Bu belirteç yerel örnek kullanıcı ve oturumlarını okumalıdır.
- **Çalışan oturumu.** `E2E_EMPLOYEE_IDLE=1` kullanın. Çalışan hesabı `e2e-employee-` ile başlamalı ve `@example.test` ile bitmeli. Hesabı `E2E_EMPLOYEE_EMAIL` ile verin. Parolayı `E2E_EMPLOYEE_PASSWORD` ile verin. Test gerçek saatte bir saat bekler. Test bu sırada yalnız Keycloak oturumunu kontrol eder.

`playwright test -c backend/e2e/playwright.config.ts --project=chromium lifecycle.spec.ts` komutunu kullanın.
