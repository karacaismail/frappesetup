# Yerel geliştirme ortamı

Bu ortam kiracı sitesini, Keycloak giriş sunucusunu ve Press sitesini birlikte açar.
Compose, bu servisleri tek proje altında yönetir. Projenin adı `fs-e2e-ortam` olur.
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

3. Bütün ortamı açın.

   ```sh
   backend/e2e/stack up
   ```

   Betik önce boş disk alanını ve kullanılabilir belleği ölçer.
   Başlatma için en az 10 GiB disk ve 3 GiB bellek gerekir.
   Betik mevcut imajları yeniden kullanır. Eksik imajları derler.
   Kiracıya ERPNext ve `platform_core` kurulur. Press sitesine `press_tr` kurulur.
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
| Yerel e-posta kutusu | `http://127.0.0.1` | P + 6 |

Colima portları bilgisayara taşımıyorsa ayrı bağlantıyı açın.
Bu bağlantı Colima'yı veya başka servisleri yeniden başlatmaz.

```sh
backend/dev/bin/tunnel open "$PANE_PORT" "$((PANE_PORT + 1))" \
  "$((PANE_PORT + 2))" "$((PANE_PORT + 3))" \
  "$((PANE_PORT + 4))" "$((PANE_PORT + 6))"
```

## Denetleyin ve kapatın

Servislerin gerçek yanıtlarını yeniden denetleyin.

```sh
backend/e2e/stack check
backend/e2e/stack resources
```

`check` kapalı servisleri açmaz. Eksik veya sağlıksız servis varsa başarısız olur.
Bu denetim giriş senaryolarının tamamını doğrulamaz.
Keycloak olayları yerel kayıt servisine gider. Gerçek sağlayıcılara istek gönderilmez.

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

## Kod denetimleri

Bu komutlar modül sınırlarını, yapay zekâ kurallarını ve betik testlerini denetler.

```sh
backend/dev/bin/module-boundaries
backend/dev/bin/ai-readiness
python3.14 -B -m unittest discover -s backend/dev/tests
```

Ortak ortam testi gerçek Compose yapılandırmasını çözer. Servisleri başlatmaz.
Tarayıcı testleri ayrı görevde yürütülür.
