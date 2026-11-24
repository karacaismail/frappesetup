# Yerel geliştirme ortamı

Bu ortam kiracı sitesini, Keycloak giriş sunucusunu ve Press sitesini birlikte açar.
Compose, bu servisleri tek proje altında yönetir.
Proje adı `fs-e2e-<port>-<özet>` biçimindedir.
Betik özeti çalışma ağacının tam yolundan ve `PANE_PORT` değerinden üretir.
Her çalışma ağacı ve port birleşimi ayrı veri birimleri kullanır.
Ortak yığında yerel kaynaklardan derlenen imajların adları da ayrıdır.
Ayrı kiracı ve Keycloak betikleri mevcut imaj adlarını korur.
Aynı anda açık yığınların port aralıkları çakışmamalıdır.
Sahiplik koruması başka sahibin verisini kullanmayı veya değiştirmeyi reddeder.
Eski `fs-e2e-ortam` birimleri korunur. Yeni yığın bu verileri kendiliğinden taşımaz.
`stack config` çıktısındaki `name` alanı geçerli proje adını gösterir.
Bu kurulum yalnız yerel geliştirme içindir. Gerçek müşteri verisi kullanmayın.
Press'in sunucu kurma işlemleri bu ortamda desteklenmez.

## Ortamı açın

Komutları depo kökünde çalıştırın. Colima'nın `factory` profili açık olmalıdır.
Python 3.14 ve Docker Compose kurulu olmalıdır.
Pane terminali `PANE_PORT` değerini verir. Bu değeri değiştirmeyin.
İlk kurulum imajları ve uygulama paketlerini indirir.

Kiracı, Keycloak ve Press için ayrı ortamlar da vardır.
Bu ortamlar aynı Pane'de ortak ortamla aynı portları kullanır.
Bu portlardan birini kendi ortamınız kullanıyorsa önce ilgili ortamı kapatın.
Kiracı ortamınızı kapatmak için `backend/dev/bin/stop` komutunu çalıştırın.

1. Colima profilini seçin.

   ```sh
   export FS_COLIMA_PROFILE=factory
   ```

2. Ortak yapılandırmayı denetleyin.

   ```sh
   backend/e2e/stack config
   ```

   Betik yerel parolaları `backend/e2e/.env` dosyasına üretir.
   Dosya yalnız sahibince okunabilir. Git bu dosyayı izlemez.
   Betik mevcut parolaları değiştirmez. Çıktı parolaları içermez.
   `E2E_ENV_FILE` değişkeniyle başka bir özel dosya seçebilirsiniz.
   Bu dosya deponun içinde olmalı. Git de bu dosyayı yok saymalı.
   Betik parolaları önce aynı klasörde geçici bir dosyaya yazar.
   Git bu geçici dosyayı yalnız iki klasörde yok sayar.
   Bu klasörler `backend/e2e/` ve `.pane/` klasörleridir.
   Bu yüzden dosyayı bu iki klasörden birine koyun.
   Örneğin `backend/e2e/.env.production` ya da `.pane/scratch/e2e.env` olabilir.
   Betik depo dışındaki yolu reddeder. Git'in izleyebileceği yolu da reddeder.
   Yol bir sembolik bağsa betik onu da reddeder.

3. Bütün ortamı açın.

   ```sh
   backend/e2e/stack up
   ```

   Betik önce boş disk alanını ve kullanılabilir belleği ölçer.
   Başlatma için en az 10 GiB disk ve 3 GiB bellek gerekir.
   Betik Keycloak ve eşitleme servisini güncel kaynaktan derler.
   Diğer mevcut imajları yeniden kullanır. Eksik imajları derler.
   Kiracıya ERPNext, `platform_core`, HRMS ve `hrms_tr` kurulur. Press sitesine `press_tr` kurulur.
   Kiracı imajı HRMS'yi sabit bir sürümden alır. Bu katman platform kodundan bağımsız önbelleğe girer.
   Betik kiracının Keycloak ayarlarını site ayarına yazar. Ayar anahtarları `platform_core` kimlik belgesindedir.
   Silme kaydı anahtarı sitede bir kez üretilir ve korunur. Betik var olan anahtarı değiştirmez.
   `up`, `press_tr` kaynak kodunu kopyalar.
   Press kurulum işareti varsa `up`, `bench migrate` komutuyla Press veritabanını günceller.
   Betik servislerin yanıtlarını ve bellek kullanımını gösterir.
   Kurulum yarıda kalırsa aynı komutu yeniden çalıştırabilirsiniz.

## Press imajını yeniden derleyin

Press Dockerfile dosyası veya imajın bağımlılıkları değişirse önce `build` komutunu çalıştırın.

```sh
backend/e2e/stack build
```

Bu komut yalnız Press'in `web` imajını yeniden derler.
Derleme tamamlanınca ortamı açın.

```sh
backend/e2e/stack up
```

Kiracı ve Keycloak imajlarını kendi mevcut betikleriyle derleyin.

## Adresler

Aşağıdaki tabloda `P`, Pane'in verdiği `PANE_PORT` değeridir.
Bütün yayınlanan portlar yalnız `127.0.0.1` adresine bağlanır.
Servisler ortak ağda aynı adlarla birbirine ulaşır.

| Servis | Adres | Port |
| --- | --- | --- |
| Keycloak | `http://identity.localhost` | P |
| Kiracı | `http://tenant1.localhost` | P + 1 |
| Kiracı anlık bağlantısı | `http://tenant1.localhost` | P + 2 |
| Press | `http://press.localhost` | P + 3 |
| Press anlık bağlantısı | `http://press.localhost` | P + 4 |
| Kimlik eşitleme servisi | `http://127.0.0.1` | P + 5 |
| Yerel e-posta kutusu | `http://127.0.0.1` | P + 6 |

Colima portları bilgisayara taşımıyorsa ayrı bağlantıyı açın.
Bu bağlantı Colima'yı veya başka servisleri yeniden başlatmaz.

```sh
backend/dev/bin/tunnel open "$PANE_PORT" "$((PANE_PORT + 1))" \
  "$((PANE_PORT + 2))" "$((PANE_PORT + 3))" \
  "$((PANE_PORT + 4))" "$((PANE_PORT + 5))" "$((PANE_PORT + 6))"
```

## Denetleyin ve kapatın

Servislerin gerçek yanıtlarını yeniden denetleyin.

```sh
backend/e2e/stack check
backend/e2e/stack resources
```

`check` kapalı servisleri açmaz. Eksik veya sağlıksız servis varsa başarısız olur.
Bu denetim giriş senaryolarının tamamını doğrulamaz.
Keycloak olayları gerçek `identity-sync` servisine gider.
Adres ortak ağda `http://identity-sync.localhost:6115/v1/events` olur.
Sahte kayıt servisi olay dinleyicisinin ayrı testleri için kalır.
Gerçek sağlayıcılara istek gönderilmez.

`up`, Keycloak veritabanından `platform` alanının iç kimliğini okur.
Betik bu kimliği eşitleme servisine ortam değişkeniyle verir.
İki servis aynı `IDENTITY_SYNC_WEBHOOK_SECRET` ortam değişkenini kullanır.
Sır imaja veya kaynak koda yazılmaz.
Önizleme anahtarı aynı sırdan ayrı bir HMAC etiketiyle türetilir.
HMAC, anahtarla hesaplanan doğrulama değeridir. Bu türetme yalnız yerel yığın içindir.
Eşitleme kayıtları `identity-sync-data` biriminde saklanır.

Canlı olay testini çalıştırın.

```sh
python3.14 backend/e2e/keycloak_delivery.py
```

Test, Keycloak'ta yalnız örnek bir hesap oluşturur ve değiştirir.
Test başarılı olayı elle göndermez. Keycloak olayı kendisi gönderir.
Test aynı olay kimliği için `processed` kaydını bekler.
Bozuk imza ve eski zaman damgası için HTTP 401 yanıtını denetler.
Örnek hesap geliştirme veritabanında kalır. Test gerçek müşteri hesabını değiştirmez.
Son koşunun kaydı [canlı olay kanıtı](../e2e/keycloak-delivery-result.md) dosyasındadır.

## Press'ten hesap silme zincirini sınayın

Bu sınama MVP testi 2'nin 5e satırını kapatır. Zincir Press'te başlar ve kiracıdaki çalışan kaydında biter.
Betik önce bir deneme hesabı hazırlar. Hazırlık Keycloak'a, kiracıya ve Press'e yazar.

```sh
backend/e2e/stack seed-deletion
```

Betik test ayarlarını `.pane/scratch/e2e-deletion.env` dosyasına yazar. Dosya yalnız sahibince okunur.
Başka bir yol için `E2E_FIXTURE_FILE` değişkenini kullanın. Yol depo içinde ve Git'in yok saydığı bir yer olmalıdır.
Her çağrı yeni bir deneme hesabı açar. Eski deneme hesapları kiracıda anonim kalır.
Sonra testi çalıştırın. Ayrıntı `backend/e2e/README.md` dosyasının "Press'ten hesap silme" bölümündedir.

İş bitince bu projenin servislerini kapatın.

```sh
backend/e2e/stack down
backend/dev/bin/tunnel close
```

`down` yalnız `fs-e2e-ortam` projesini kapatır. Veri birimlerini silmez.
Yeniden açarken aynı portu, profili ve parola dosyasını kullanın.
Başka bir çalışma aynı proje adını kullanmamalıdır.
Betik çalışma klasörünü, port aralığını ve parola dosyasının yolunu denetler.
Başka bir çalışmanın kayıtları varsa açma ve kapatma işlemlerini reddeder.
`fs-e2e-ortam-owner` birimi bu sahiplik kaydını korur.

## Yalnız kiracıyla çalışın

Mevcut kiracı betikleri `compose.tenant.yaml` dosyasını kullanır.
Bu betikler Keycloak veya Press parolası istemez.

```sh
backend/dev/bin/start
backend/dev/bin/test platform_core
backend/dev/bin/ruff
backend/dev/bin/stop
```

`bin/test` testleri `test-<uygulama>.localhost` adlı ayrı bir sitede koşar. Bu sitede `allow_tests` açıktır. `tenant1.localhost` sitesinde `allow_tests` bilerek kapalıdır. Testler kayıt açar ve siler. Kapalı sitede Frappe'nin `run-tests` komutu "Testing is disabled" yazar ve 0 koduyla biter. Bu davranış Frappe'nin `frappe/commands/testing.py` dosyasındadır. Bu yüzden `bin/test` önce sitenin ayarını okur. `allow_tests` açık değilse komut 3 koduyla durur.

## Kod denetimleri

Bu komutlar modül sınırlarını, yapay zekâ kurallarını ve betik testlerini denetler.

```sh
backend/dev/bin/module-boundaries
backend/dev/bin/ai-readiness
python3.14 -B -m unittest discover -s backend/dev/tests
```

Ortak ortam testi gerçek Compose yapılandırmasını çözer. Servisleri başlatmaz.
Tarayıcı testleri ayrı görevde yürütülür.
