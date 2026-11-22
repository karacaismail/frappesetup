# Keycloak geliştirme ortamı

Bu klasör Atonota kimlik servisinin geliştirme kurulumunu tutar. Atonota, Keycloak üzerinde çalışır. Sahibi kimlik-realm işidir.

## Dosyalar

| Yol | İçerik |
| --- | --- |
| `../../dev/compose.keycloak.yaml` | Keycloak 26.8.2, PostgreSQL 17.12 ve Mailpit 1.34.0 servisleri |
| `realm/platform-realm.json` | `platform` realm'inin tanımı. Keycloak açılışta içe alır. |
| `realm/dev-users/platform-users-0.json` | Örnek kullanıcılar. Yalnız geliştirmede yüklenir. Alan adı `example.test`. |
| `realm/password-blacklists/yaygin-parolalar.txt` | Parola politikasının yaygın parola listesi. Kaynağı `KAYNAK.md` dosyasındadır. |
| `.env.example` | Geliştirme ortamının değişkenleri ve sahte değerler |
| `production.env.example` | Üretim değişkenlerinin örneği. Değerler sahtedir. Güvenlik ayarları gerçek değerdir. |
| `conf/` | İmajın varsayılan Keycloak ayarı (`keycloak.conf`) ve geliştirmedeki düz HTTP adres listesi |
| `event-listener/` | Olay dinleyici eklentisi. `sashyo/keycloak-webhook-listener` çatalıdır. Lisans `LICENSE`, kaynak ve değişiklikler `NOTICE` dosyasındadır. |
| `event-sink/` | Olay testlerinin kayıt servisi. Yalnız geliştirmede çalışır. |
| `bin/kc-dev.sh` | Ortamı açan, kapatan ve testleri çalıştıran betik |
| `Dockerfile` | Realm dosyalarını, ayarı ve üç eklentiyi imaja ekler. Keycloak sürümü ve Maven imajı tek yerde yazılıdır. |
| `tests/` | Realm dosyası testleri, canlı Keycloak testleri ve eklenti testleri |

## Komutlar

Komutların hepsi `PANE_PORT` değişkenini ister.

| Komut | Yaptığı iş |
| --- | --- |
| `bin/kc-dev.sh config` | Compose şablonunu gösterir. Gizli değerleri açmaz. |
| `bin/kc-dev.sh config --quiet` | Compose ayarını çıktı vermeden doğrular. |
| `bin/kc-dev.sh up` | Ortamı açar. İmaj varsa yeniden kullanır. |
| `bin/kc-dev.sh build` | İmajı derler. Realm ya da eklenti değişince kullanın. |
| `bin/kc-dev.sh down` | Ortamı ve tüneli kapatır. Birim silinmez. |
| `bin/kc-dev.sh restart` | Servisleri yeniden başlatır. |
| `bin/kc-dev.sh logs` | Servis günlüklerini gösterir. |
| `bin/kc-dev.sh ps` | Servislerin durumunu gösterir. |
| `bin/kc-dev.sh exec` | Bir serviste komut çalıştırır. |
| `bin/kc-dev.sh test` | Bütün testleri çalıştırır. |
| `bin/kc-dev.sh tunel` | Portları ssh tüneliyle bu Mac'e taşır. |
| `bin/kc-dev.sh tunel-kapat` | Tüneli kapatır. |
| `bin/kc-dev.sh prod-check` | Üretim imajını Compose ayarı olmadan açar. Keycloak hazırsa testleri çalıştırır. Sonra geçici container'ları siler. |
| `bin/kc-dev.sh realm-reload --yes` | Realm dosyasını imaj derlemeden yükler. Realm verisini siler. |
| `bin/kc-dev.sh realm-delete-only --yes` | Yalnız realm'i siler. |
| `bin/kc-dev.sh realm-sil --evet` | Realm'i siler ve imajdaki realm dosyasını yeniden içe alır. |

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

Testlerin lint denetimi `uvx ruff check tests` komutudur. Ayar `ruff.toml` dosyasındadır.

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

Colima'nın factory profili depo klasörünü sanal makineye bağlamaz. Bu yüzden compose dosyası bind mount kullanmaz. `Dockerfile` realm dosyasını ve parola listesini imaja kopyalar. `dev` hedefi örnek kullanıcıları da ekler. Üretim imajı `prod` hedefinden alınır. `bin/kc-dev.sh up` imaj varsa onu yeniden kullanır. Realm ya da eklenti değişince imajı `bin/kc-dev.sh build` derler. Derlemeden önce boş disk yerini ölçün. Yer azsa `FS_COLIMA_PROFILE=default` ile colima profili seçilir. İmaj etiketi `fs-keycloak-atonota:dev-<PANE_PORT>` biçimindedir. Böylece paralel Pane'ler birbirinin imajını ezmez.

## Eklentiler

Üç eklenti imaja eklenir. Seçim gerekçesi `backend/docs/kararlar/0003-keycloak-eklentileri.md` notundadır.

- Olay dinleyiciyi `keycloak-webhook-listener` çatalı sağlar. Kaynak `event-listener/` klasöründedir. İmaj derlemesinde JUnit testleriyle derlenir. Olayları identity-sync servisine imzalı gönderir. Adres HTTPS olmalıdır. Düz HTTP yalnız `conf/webhook-plain-http-hosts.txt` listesindeki adrese izinlidir. Bu liste yalnız geliştirme imajına girer.

- Sihirli bağlantıyı `cloudflightio/keycloak-magic-link` eklentisi sağlar. Jar adı `keycloak-magic-link` olur. Eklenti imaj derlemesinde sabit bir commit'ten derlenir. Bağlantı akışın adımıdır. Tıklamadan sonra ikinci adım sorulur. Bağlantı yalnız isteyen tarayıcıda, 300 saniye ve tek kullanım geçerlidir. REST ucu ve çapraz cihaz yolu `conf/keycloak.conf` ayarıyla kapalıdır.
- Apple ile girişi `klausbetz/apple-identity-provider-keycloak` 1.17.0 eklentisi sağlar. Jar adı `apple-identity-provider` olur. Sağlayıcı realm'de kapalıdır. Gerçek anahtar gelince `.env` dosyasındaki `ATONOTA_APPLE_*` değerleri doldurulur. Sonra sağlayıcı açılır.

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

## Yeni kiracı için istemci açma

Keycloak, her kiracı sitesini ayrı bir istemci kaydıyla tanır. İstemciyi bir Keycloak yöneticisi açar.

1. Keycloak ve kiracı sitesinin HTTPS adreslerini belirleyin.
2. Komutu önce `--preview` ile çalıştırın. Komut Keycloak'a istek göndermez.

   ```bash
   bin/create-tenant-client.py acme https://tenant.example.test https://identity.example.test --preview
   ```

3. Önizlemede Keycloak adresini ve kiracının dönüş adreslerini kontrol edin.
4. Ayarlar doğruysa aynı komutu `--preview` olmadan çalıştırın.
5. Komut sorunca `CREATE site-acme` yazın.
6. Keycloak yönetim yetkisi olan kısa ömürlü erişim belirtecini girin. Komut girişi gizler.
7. Keycloak 201 dönerse “Clients” ekranında `site-acme` kaydını açın.
8. Keycloak'ın ürettiği istemci sırrını kiracı sitesinin gizli ayarına ekleyin.

Komut, sözleşmenin 7. bölümündeki yönetim işini Keycloak'ın mevcut
`POST /admin/realms/platform/clients` ucuyla yapar. Bu uç yönetim yetkisini denetler.
`identity-sync` hesabına istemci açma yetkisi verilmez.

Keycloak 409 dönerse istemci adı zaten kayıtlıdır. Komut mevcut kaydı değiştirmez.
Bağlantı kesilirse komutu yinelemeden önce “Clients” ekranını kontrol edin.
