# Yamasız Press denemesi

Press v0.154.1 yamasız açılmadı. O-18 borcu açıktır.
Üç Press modülü, Python 3.14 ve Frappe 16 ile hata verir.
Tam bağımlılık denetimi de başarısızdır.
Ayrıntılar ve önerilen düzeltmeler [Press önerisindedir](../../docs/press-python314-upstream.md).

## Deneme imajı

`Dockerfile.unpatched`, mevcut `frappe/erpnext:v16.55.0` imajını kullanır.
Bu temel imajda Python 3.14.10 ve Frappe 16.56.0 gözlendi.
Varsayılan kaynak `v0.154.1` commit kodudur. Tam kaynak kodu da denetlenir.
`PRESS_REVISION` derleme değişkeni başka bir tam commit kodunu seçebilir.
Test, beklenen kodu `PRESS_TEST_EXPECTED_REVISION` değişkeninden alır.
Bu değer imaja derleme sırasında yazılır. Dal adı kabul edilmez.
[Sürüm taraması](../../docs/press-python314-version-audit.md) son develop denemesini ve kesin kaynakları kaydeder.
`probe-requirements.txt` yalnız ilgili import denemelerinin paketlerini kurar.
Press'in bütün bağımlılıkları bu imajda yoktur.
Press'in `--no-deps` ile kurulması, bağımlılık şartlarının karşılandığını göstermez.
Bu imaj çalışan site veya üretim imajı değildir.
Mevcut geliştirme imajı ve yama akışı değişmedi.

Komutları depo kökünde çalıştırın. Önce kaynakları ölçün.

```sh
export PANE_PORT=47320
colima ssh -p factory -- free -g
colima ssh -p factory -- df -h /var/lib/docker
```

Kullanılabilir bellek 3 GiB altındaysa ortamı açmayın.
Yeterli alan varsa deneme imajını oluşturun.

```sh
docker --context colima-factory build \
  -f backend/dev/press/Dockerfile.unpatched \
  -t fs-pd-press-py314:probe .
```

Aşağıdaki testler ağ erişimi olmadan çalışır. Servis portu açılmaz.
Compose projesinin adı `fs-pd-press-py314` olur.
`pull_policy: never`, eksik yerel etiketi dış kayıttan çekmeyi engeller.
Deneme port açmadığı için Compose, `PANE_PORT` değişkenini zorunlu tutmaz.

```sh
docker --context colima-factory compose \
  -f backend/dev/press/compose.unpatched.yaml run --rm probe
```

### Press Settings ve Telegram

Press Settings açılırken ödeme ve olay kaydı modüllerini de yükler.
Deneme imajı bu yol için `boto3`, `twilio`, `posthog` ve `razorpay` kurar.
Press Settings testi, Telegram paketi kurulu imajda ağ kapalıyken geçti.
Üretim imajında Telegram paketi yoktur. Bu yüzden ekip paketsiz denemeyi de yapar.

Depo kökünde aşağıdaki komutu çalıştırın.
Komut, Telegram paketini yalnız geçici kaptan kaldırır.

```sh
docker --context colima-factory run --rm --network none --pull never \
  fs-pd-press-py314:probe sh -ec '
    uv pip uninstall --python env/bin/python python-telegram-bot-raw
    exec env/bin/python -B /opt/press-probe/test_unpatched_runtime.py \
      UnpatchedRuntimeTest.test_press_settings_prerequisites_import \
      UnpatchedRuntimeTest.test_press_settings_imports
  '
```

Kaynak `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` ile paket yükleme testi geçti.
Press Settings testi `ModuleNotFoundError: No module named 'telegram'` hatası verdi.
Ekip, üretimdeki paket seçimiyle test geçene kadar Telegram yamasını tutar.

### Diğer denemeler

İlk dar kapsamlı denemede altı test geçti. Dört test başarısız oldu.
O sonuç `TypedDict` tanımını ve kaldırılan `init_telemetry` işlevini kapsıyordu.
Genişletilen testler `press.api.cookies` import'unu ve tam bağımlılık uyumunu da denetler.
Çerez modülü, Frappe'de kaldırılan `get_cookie_dict_from_headers` işlevini ister.
`uv pip check`, eksik paketleri ve sürüm çelişkilerini reddeder.

22 Kasım 2026 Pazar günü genişletilen testler başlangıç kaynağıyla çalıştırıldı.
Bu devam denemesi `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` kaynağına sabitlendi.
On üç testin yedisi geçti. Altısı başarısız oldu.
`TypedDict` ve telemetri engelleri ayrı ayrı ikişer testi düşürdü.
Çerez import'u bir testi düşürdü. Bağımlılık denetimi de bir testi düşürdü.
Kaynak bütünlüğü ve yama izi denetimleri geçti.
Bağımlılık denetimi 177 pakette 32 uyumsuzluk buldu.
Test komutunun çıkış kodu 1 olur. Bu sonuç başarı değildir.

Test, Press klasöründe `git diff HEAD` çıktısının boş olduğunu doğrular.
Test, beklenmeyen yeni dosyaları da reddeder.
Test, geliştirme imajının işaret dosyasını ve yama betiğini reddeder.
Bu yollar `/opt/press-local/development-image` ve `/opt/press-local/scripts/patch-py314.sh` olur.
Test, kurulu paketlerde `.orig` yedeklerini ve `press-local:` izlerini reddeder.
Bu iz taraması, paket dosyalarının tam bütünlüğünü kanıtlamaz.
Test, Press dosyalarını veya Python import davranışını değiştirmez.

İş bitince yalnız bu denemenin container ve birimlerini kapatıp silin.

```sh
docker --context colima-factory compose \
  -f backend/dev/press/compose.unpatched.yaml down --volumes --remove-orphans
```

Deneme bitince bu görevin imaj etiketi de silinir.

```sh
docker --context colima-factory image rm fs-pd-press-py314:probe
```

Görev C için çalışan yamasız Press ortamı sağlanamadı.
Başka işlerin imajlarına dokunulmaz.

## Mevcut aday kapısı

`check_unpatched_runtime.sh` ayrı bir tam Bench adayını denetler.
Betik geliştirme yamasını reddeder. Press kaynak farkını da reddeder.
Ardından üç Press modülünü içe aktarır. İlk hatada durur.

```sh
cd /path/to/candidate-bench
sh /path/to/repo/backend/dev/press/check_unpatched_runtime.sh
```

Bu kapının geçmesi, site ve masa başarısını tek başına kanıtlamaz.
Kaynak düzeltmeleri kabul edilince site kurulumu ve tarayıcı kontrolü gerekir.
[Sunucu kurma doğrulaması](provisioning-readiness.md) da ayrı bir iştir.
