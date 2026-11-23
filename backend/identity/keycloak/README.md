# Keycloak geliştirme ortamı

Bu klasör Atonota kimlik servisinin geliştirme kurulumunu tutar. Atonota, Keycloak üzerinde çalışır. Sahibi kimlik-realm işidir.

## Dosyalar

| Yol | İçerik |
| --- | --- |
| `../../dev/compose.keycloak.yaml` | Keycloak 26.8.2, PostgreSQL 17.12 ve Mailpit 1.34.0 servisleri |
| `realm/platform-realm.json` | `platform` realm'inin tanımı. Keycloak açılışta içe alır. |
| `realm/dev-users/platform-users-0.json` | Örnek kullanıcılar. Yalnız geliştirmede yüklenir. Alan adı `example.test`. |
| `realm/password-blacklists/common-passwords.txt` | Parola politikasının yaygın parola listesi. Kaynağı `SOURCE.md` dosyasındadır. |
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
| `bin/kc-dev.sh tunnel` | Portları ssh tüneliyle bu Mac'e taşır. |
| `bin/kc-dev.sh close-tunnel` | Tüneli kapatır. |
| `bin/kc-dev.sh prod-check` | Üretim imajını Compose ayarı olmadan açar. Keycloak hazırsa testleri çalıştırır. Sonra geçici container'ları siler. |
| `bin/kc-dev.sh realm-sync` | Realm dosyasındaki istemci ve kapsamları var olan veritabanına uygular. Veri silmez. |
| `bin/kc-dev.sh realm-reload --yes` | Realm dosyasını imaj derlemeden yükler. Realm verisini siler. |
| `bin/kc-dev.sh realm-delete-only --yes` | Yalnız realm'i siler. |
| `bin/kc-dev.sh delete-realm --yes` | Realm'i siler ve imajdaki realm dosyasını yeniden içe alır. |

## Çalıştırma

Komutları bu klasörde çalıştırın. `PANE_PORT` değişkeni zorunludur. Keycloak bu portu, Mailpit ekranı bu portun 6 fazlasını alır.

```bash
export PANE_PORT=5070
bin/kc-dev.sh up
```

Betik `.env` dosyası yoksa `.env.example` dosyasından üretir. Üretirken “degistir-” ile başlayan değerleri rastgele değerle doldurur. `.env` Git'e girmez.

Keycloak adresi `http://identity.localhost:<PANE_PORT>` olur. Yönetim konsolu aynı adreste `/admin/` yolundadır. Giriş bilgisi `.env` dosyasındaki `KC_BOOTSTRAP_ADMIN_*` değerleridir.

## Testler

```bash
bin/kc-dev.sh test
```

Betik `.env` değerlerini yükler. Sonra `tests/` klasöründeki testleri çalıştırır. Keycloak çalışmıyorsa canlı testler atlanır. Yalnız dosya testleri için şu komut yeter:

```bash
cd tests && python3 -I -m unittest discover -s . -p 'test_realm_files.py'
```

Testlerin lint denetimi `uvx ruff check tests` komutudur. Ayar `ruff.toml` dosyasındadır.

### Dış MCP istemcisi

MCP, yapay zekâ istemcisinin araç çağırdığı yöntemdir.
Realm şablonu MCP istemcilerini kapalı tutar. Kabul testleri bitene kadar kapalı bırakın.
Keycloak 26.8.2, kaynak adresini denetlemek için `resource-indicators` özelliğini ister. [Keycloak kılavuzu](https://www.keycloak.org/securing-apps/mcp-authz-server)
İstemci, kiracı çalışanı için 1 saat boşta kalma sınırı uygular.
Çalışan oturumu en çok 24 saat sürer.
Keycloak ilk izin sırasında dış istemcinin adını ve kapsamı gösterir.
Kullanıcı onay verirse Keycloak erişim kodunu üretir.
Dönüş adresini `ATONOTA_MCP_REDIRECT_URI` değerinde tam olarak belirtin.
Keycloak, istekteki adresi kayıtlı adresle birebir karşılaştırır.
Keycloak, adresi kayıtta ve izin isteğinde denetler.
Keycloak, yıldız, kullanıcı bilgisi veya `#` parçası içeren adresleri reddeder.
Keycloak, geliştirme dışında HTTPS ister.
Geliştirmede yalnız sabit portlu yerel adres HTTP kullanabilir.

`ATONOTA_MCP_RESOURCE_URL` sitenin tam MCP adresidir.
İstemci, izin, kod değiştirme ve belirteç yenileme isteklerinde bu adresi gönderir.
Keycloak, erişim belirtecinin hedefini bu adrese bağlar.
Keycloak, belirteç isteğinde adres eksik veya farklıysa isteği reddeder.
Platform, oturumun açık olduğunu Keycloak'a sorar.
Bu sorguda istemci adı olarak tam MCP adresini kullanır.
Sorgu, `ATONOTA_MCP_INTROSPECTION_SECRET` değerini parola olarak kullanır.
Geliştirme betiği eksik MCP ayarlarını ekler ve rastgele parola üretir.
Realm'i doğrudan içe aktarırsanız üç `ATONOTA_MCP_*` değerini önceden verin.

Yeni MCP istemcisini kaydederken `mcp.external-client` değerini `true` yapın.
`mcp.expected-resource` değerine sitenin tam MCP adresini yazın.
İstemciye `mcp` kapsamını ekleyin. Bu kapsam MCP araçlarına erişim isteğini bildirir.

Canlı realm testleri için ayrı bir yerel Keycloak kullanın.
Şablondaki üç MCP istemcisini yükleyin.
`acr`, `basic` ve `mcp` kapsamlarını da yükleyin.
Çalışan doğrulama düzeyini uygulayan giriş akışını yükleyin.
Şablondaki istemci kurallarını ve eklentiyi de yükleyin.
MCP istemcilerini yalnız bu test ortamında açın. Örnek bir kullanıcı oluşturun.
Örnek kullanıcıya ad, soyad ve e-posta adresi verin.
Sunucu adresini `KC_PUBLIC_URL`, portu `KC_PORT` ile verin.
Örnek kullanıcı bilgilerini `KC_MCP_TEST_USER` ve `KC_MCP_TEST_PASSWORD` ile verin.
Yerel yönetici bilgilerini `KC_BOOTSTRAP_ADMIN_USERNAME` ve `KC_BOOTSTRAP_ADMIN_PASSWORD` ile verin.

```bash
KC_MCP_TEST=1 python3 -m unittest discover -s tests -p 'test_mcp_*.py'
```

## Realm'i yeniden içe almak

Keycloak var olan realm'i yeniden içe almaz. Realm dosyası değişince şu komut realm'i siler ve Keycloak'ı yeniden başlatır:

```bash
bin/kc-dev.sh delete-realm --yes
```

Bu komut geliştirme realm'indeki bütün veriyi siler. `--yes` bayrağı olmadan çalışmaz. Yalnız geliştirme ortamında kullanın.

## Ana makineden erişim

Compose portu `127.0.0.1` adresine açar. Bu Mac'te Colima'nın factory profili yeni portları ana makineye taşımıyor. Bu durumda şu komut ayrı bir ssh tüneli açar:

```bash
bin/kc-dev.sh tunnel
```

Tünel Colima'nın kendi bağlantısına dokunmaz. `bin/kc-dev.sh down` tüneli de kapatır.

## Realm dosyaları imajın içindedir

Colima'nın factory profili depo klasörünü sanal makineye bağlamaz. Bu yüzden compose dosyası bind mount kullanmaz. `Dockerfile` realm dosyasını ve parola listesini imaja kopyalar. `dev` hedefi örnek kullanıcıları da ekler. Üretim imajı `prod` hedefinden alınır. `bin/kc-dev.sh up` imaj varsa onu yeniden kullanır. Realm ya da eklenti değişince imajı `bin/kc-dev.sh build` derler. Derlemeden önce boş disk yerini ölçün. Yer azsa `FS_COLIMA_PROFILE=default` ile colima profili seçilir. İmaj etiketi `fs-keycloak-atonota:dev-<PANE_PORT>` biçimindedir. Böylece paralel Pane'ler birbirinin imajını ezmez.

## Eklentiler

Üç eklenti imaja eklenir. Seçim gerekçesi `backend/docs/decisions/0003-keycloak-extensions.md` notundadır.

- Olay dinleyiciyi `keycloak-webhook-listener` çatalı sağlar. Kaynak `event-listener/` klasöründedir. İmaj derlemesinde JUnit testleriyle derlenir. Olayları identity-sync servisine imzalı gönderir. Adres HTTPS olmalıdır. Düz HTTP yalnız `conf/webhook-plain-http-hosts.txt` listesindeki adrese izinlidir. Bu liste yalnız geliştirme imajına girer.
- Hesap ekranı `account-deletion-link-provider` eklentisini kullanır. Keycloak imajı eklentiyi `themes/atonota/account-provider/build.sh` ile derler. Geliştirme örnekleri, yeni kullanıcılarla aynı varsayılan rolü alır.
- İlk kurulumda Keycloak, yerleşik `account-console` istemcisine `roles` kapsamını ekler. Kapsam, hesap rollerini belirtece yazar.
- Önceden kurulmuş `platform` alanında `account-console` istemcisini açın. “Client scopes” sekmesinde `roles` kapsamını “Default” olarak ekleyin. “Full scope allowed” ayarı kapalı kalsın.

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

## Korunan veritabanında realm eşitleme

Keycloak `--import-realm` ile açılır. Realm veritabanında varsa Keycloak dosyayı yeniden içe almaz. Bu yüzden eski bir veritabanı eski istemci ayarlarını korur. Örneğin `mobile-app` istemcisi `mobile` ve `aud-site-tenant1` kapsamlarını almaz. Bu sorun MVP testi 2'de T-11 adıyla bulundu.

`bin/sync-dev-realm.py` betiği bu açığı kapatır. Betik Keycloak yönetim API'sini kullanır. Betik realm dosyasındaki şu ayarları veritabanına uygular:

- istemciler, istemci ayarları ve istemci sırları,
- istemcilerin varsayılan ve isteğe bağlı kapsamları,
- kapsamlar ve kapsamların eşleyicileri,
- realm'in varsayılan kapsamları,
- kapsamların rol eşlemeleri.

Betik yalnız ekler ve düzeltir. Betik istemci, kapsam, kullanıcı ve oturum silmez. Bir kapsam bağı yanlış türdeyse betik bağı doğru türe taşır. Dosyada olmayan bağlar ve eşleyiciler yerinde kalır. Örneğin `create-tenant-client.py` ile eklenen kiracı kapsamı kalır. Betiği tekrar çalıştırmak güvenlidir. Ayarlar eşitse betik hiçbir şey yazmaz.

Betik çıktıya yalnız değişen öğenin adını yazar. Sır değeri yazmaz. Sırlar komut satırına girmez.

Ortak yığın betiği `backend/e2e/stack up` bu adımı kendisi çalıştırır. Adım Keycloak hazır olunca çalışır. Betik yığının ağında, `identity-sync` imajıyla çalışır. Yalnız Keycloak yığınında adımı elle çalıştırın:

```bash
bin/kc-dev.sh tunnel
bin/kc-dev.sh realm-sync
```

### Üretimde realm değişikliği

Bu betik yalnız yerel geliştirme ve test yığınında çalışır. Betik yalnız `localhost`, `127.0.0.1` ve `.localhost` ile biten adresleri kabul eder. Başka adreste betik istek atmadan durur.

Üretimde realm değişikliği ayrı ve onaylı bir iştir. Değişiklik bir değişiklik kaydıyla planlanır. Kimlik ve altyapı sorumlusu değişikliği onaylar. Değişiklik önce bir hazırlık ortamında denenir. Bu betik üretim için kullanılmaz.

## Yeni kiracı için istemci açma

Keycloak, her kiracı sitesini ayrı bir istemci kaydıyla tanır. İstemciyi bir Keycloak yöneticisi açar.

1. Keycloak ve kiracı sitesinin HTTPS adreslerini belirleyin.
   Kiracı adı `-service` ile bitemez.
2. Komutu önce `--preview` ile çalıştırın. Komut Keycloak'a istek göndermez.

   ```bash
   bin/create-tenant-client.py acme https://tenant.example.test https://identity.example.test --preview
   ```

3. Önizlemede Keycloak adresini ve kiracının dönüş adreslerini kontrol edin.
   Hedef kapsamını ve kapsamı alacak servisleri de kontrol edin.
4. Ayarlar doğruysa aynı komutu `--preview` olmadan çalıştırın.
5. Komut sorunca `CREATE site-acme` yazın.
6. Keycloak yönetim yetkisi olan kısa ömürlü erişim belirtecini girin.
   Yönetici tüm istemcileri görebilmeli. Komut girişi gizler.
7. Komut “Ready” yazınca “Clients” ekranında iki istemciyi açın.
8. `site-acme` sırrını `keycloak_client_secret` ayarına kaydedin.
9. `site-acme-service` adını `keycloak_service_client_id` ayarına kaydedin.
10. Servis sırrını `keycloak_service_client_secret` ayarına kaydedin.

Komut, sözleşmenin 7. bölümündeki yönetim işini Keycloak'ın mevcut uçlarıyla yapar.
`aud-site-acme` kapsamı, belirtecin hedefini `site-acme` yapar.
Komut bu kapsamı `identity-sync` ve `press-service` hesaplarına isteğe bağlı olarak bağlar.
Servisler bu hedef için `scope=aud-site-acme` ister. İstemci açma yetkisi Keycloak yöneticisinde kalır.

Kurulum yarıda kalırsa aynı komutu yeniden çalıştırın.
Komut mevcut istemci sırrını korur ve eksik adımları tamamlar.
Mevcut ayar şablonla çelişirse komut durur. Keycloak yöneticisi çelişen ayarı inceleyebilir.

### Var olan kiracı istemcisine yeni dönüş adresi ekleme

Dönüş adresi, Keycloak'ın tarayıcıyı geri gönderdiği adrestir.
Şablon zamanla yeni dönüş adresi alabilir. Örneğin “Başka hesapla oturum aç” bağlantısı için çıkış dönüş adresi eklendi.
Daha önce açılmış kiracı istemcisi bu adresi bilmez. Kullanıcı bu bağlantıya basınca Keycloak hata sayfası gösterir.
Yerel yığın bu adımı kendisi yapar. Üretimde bu adımı Keycloak yöneticisi yapar.

1. Aynı kiracı için komutu `--preview` olmadan yeniden çalıştırın.
2. İstemcide eksik dönüş adresi varsa komut durur. Komut eksik adresleri yazar ve `--update-redirects` seçeneğini önerir.
3. Yazılan adresleri kontrol edin. Adresler kiracı sitesinin adresiyle başlamalıdır.
4. Komutu `--update-redirects` ile yeniden çalıştırın.

   ```bash
   bin/create-tenant-client.py acme https://tenant.example.test https://identity.example.test --update-redirects
   ```

5. Komut sorunca `UPDATE site-acme` yazın.
6. Komut “Added redirect addresses” satırında eklenen adresleri yazar.

Bu seçenek yalnız eksik dönüş adreslerini ekler. İstemcinin öteki ayarlarına ve sırrına dokunmaz.
İstemcide şablonda olmayan bir dönüş adresi varsa komut yine durur. Keycloak yöneticisi bu adresi önce inceler.

Tarayıcı istemcisinin servis hesabı kapalıdır. Servis istemcisinin tarayıcı girişi kapalıdır.
Eski bir kayıt iki akışı birden açıyorsa komut durur. Yönetici bu kaydı önce ayırmalıdır.
