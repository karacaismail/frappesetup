# Keycloak geliştirme ortamı

Bu klasör Atonota kimlik servisinin geliştirme kurulumunu tutar. Atonota, Keycloak üzerinde çalışır. Sahibi kimlik-realm işidir.

## Dosyalar

| Yol | İçerik |
| --- | --- |
| `../../dev/compose.keycloak.yaml` | Keycloak 26.8.2, PostgreSQL 17.12 ve Mailpit 1.34.0 servisleri |
| `realm/platform-realm.json` | `platform` realm'inin tanımı. Keycloak açılışta içe alır. |
| `realm/dev-users/platform-users-0.json` | Örnek kullanıcılar. Yalnız geliştirmede yüklenir. Alan adı `example.test`. |
| `realm/password-blacklists/yaygin-parolalar.txt` | Parola politikasının yaygın parola listesi. Kaynağı `KAYNAK.md` dosyasındadır. |
| `.env.example` | Gerekli ortam değişkenleri ve sahte değerler |
| `bin/kc-dev.sh` | Ortamı açan, kapatan ve testleri çalıştıran betik |
| `Dockerfile` | Realm dosyalarını, Apple eklentisini ve derlenen sihirli bağlantı eklentisini imaja ekler |
| `tests/` | Realm dosyası testleri, canlı Keycloak testleri ve eklenti testleri |

## Çalıştırma

Komutları bu klasörde çalıştırın. `PANE_PORT` değişkeni zorunludur. Keycloak bu portu, Mailpit ekranı bu portun 6 fazlasını alır.

```bash
export PANE_PORT=5070
bin/kc-dev.sh up
```

Betik `.env` dosyası yoksa `.env.example` dosyasından üretir. Üretirken “degistir-” ile başlayan değerleri rastgele değerle doldurur. `.env` Git'e girmez.

Keycloak adresi `http://kimlik.localhost:<PANE_PORT>` olur. Yönetim konsolu aynı adreste `/admin/` yolundadır. Giriş bilgisi `.env` dosyasındaki `KC_BOOTSTRAP_ADMIN_*` değerleridir.

## Testler

```bash
bin/kc-dev.sh test
```

Betik `.env` değerlerini yükler. Sonra `tests/` klasöründeki testleri çalıştırır. Keycloak çalışmıyorsa canlı testler atlanır. Yalnız dosya testleri için şu komut yeter:

```bash
cd tests && python3 -I -m unittest discover -s . -p 'test_realm_dosyalari.py'
```

## Realm'i yeniden içe almak

Keycloak var olan realm'i yeniden içe almaz. Realm dosyası değişince şu komut realm'i siler ve Keycloak'ı yeniden başlatır:

```bash
bin/kc-dev.sh realm-sil --evet
```

Bu komut geliştirme realm'indeki bütün veriyi siler. `--evet` bayrağı olmadan çalışmaz. Yalnız geliştirme ortamında kullanın.

## Ana makineden erişim

Compose portu `127.0.0.1` adresine açar. Bu Mac'te Colima'nın factory profili yeni portları ana makineye taşımıyor. Bu durumda şu komut ayrı bir ssh tüneli açar:

```bash
bin/kc-dev.sh tunel
```

Tünel Colima'nın kendi bağlantısına dokunmaz. `bin/kc-dev.sh down` tüneli de kapatır.

## Realm dosyaları imajın içindedir

Colima'nın factory profili depo klasörünü sanal makineye bağlamaz. Bu yüzden compose dosyası bind mount kullanmaz. `Dockerfile` realm dosyasını ve parola listesini imaja kopyalar. `dev` hedefi örnek kullanıcıları da ekler. Üretim imajı `prod` hedefinden alınır. `bin/kc-dev.sh up` her çalışmada imajı yeniden derler. İmaj etiketi `fs-keycloak-atonota:dev-<PANE_PORT>` biçimindedir. Böylece paralel Pane'ler birbirinin imajını ezmez.

## Eklentiler

İki eklenti imaja eklenir. Seçim gerekçesi `backend/docs/kararlar/0003-keycloak-eklentileri.md` notundadır.

- Sihirli bağlantıyı `cloudflightio/keycloak-magic-link` eklentisi sağlar. Eklenti imaj derlemesinde sabit bir commit'ten derlenir. Bağlantı akışın adımıdır. Tıklamadan sonra ikinci adım sorulur. Bağlantı yalnız isteyen tarayıcıda, 300 saniye ve tek kullanım geçerlidir. Çapraz cihaz ucu kapalıdır.
- Apple ile girişi `klausbetz/apple-identity-provider-keycloak` 1.17.0 eklentisi sağlar. Sağlayıcı realm'de kapalıdır. Gerçek anahtar gelince `.env` dosyasındaki `ATONOTA_APPLE_*` değerleri doldurulur. Sonra sağlayıcı açılır.

## İmaj çekme hatası

Bu Mac'te Docker istemcisi `osxkeychain` yardımcısını arar ama yardımcı kurulu değil. İlk çekimde “error getting credentials” hatası çıkar. Çözüm için boş bir Docker ayar klasörü açın. İçine `contexts` ve `cli-plugins` klasörlerini kopyalayın. Sonra çekimi `DOCKER_CONFIG=<klasör>` ile yapın. İmaj yerelde olunca `kc-dev.sh up` normal çalışır.

## Kapatma

```bash
bin/kc-dev.sh down
```

Bu komut container'ları kapatır. Veritabanı birimini silmez.

## Sırlar

Realm dosyası sır taşımaz. Sır alanları `${ATONOTA_...}` yer tutucusudur. Keycloak `--import-realm` ile açılır. Açılışta yer tutucuları ortam değişkenlerinden doldurur. Bu davranış Keycloak 26.8.2 kaynağında doğrulandı:

- `model/storage-services/src/main/java/org/keycloak/exportimport/AbstractFileBasedImportProvider.java` 33 ve 42. satırlar: yer tutucu `System.getenv` ile çözülür.
- `services/src/main/java/org/keycloak/exportimport/ExportImportManager.java` 79 ve 81. satırlar: açılıştaki içe alım yer tutucu değişimini açar.
