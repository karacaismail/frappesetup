# Yamasız Press denemesi

Press v0.154.1 yamasız açılmadı. O-18 borcu açıktır.
İki Press modülü, Python 3.14 ve Frappe 16 ile hata verir.
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

```sh
PANE_PORT=47320 docker --context colima-factory compose \
  -f backend/dev/press/compose.unpatched.yaml run --rm probe
```

Son denemede altı test geçti. Dört test başarısız oldu.
Başarısızlıklar `TypedDict` tanımı ve kaldırılan `init_telemetry` işlevinden kaynaklandı.
Test komutunun çıkış kodu 1 olur. Bu sonuç başarı değildir.

Test, Press klasöründe `git diff HEAD` çıktısının boş olduğunu doğrular.
Test, beklenmeyen yeni dosyaları da reddeder.
Test, Press dosyalarını veya Python import davranışını değiştirmez.

İş bitince yalnız bu denemenin container ve birimlerini kapatıp silin.

```sh
PANE_PORT=47320 docker --context colima-factory compose \
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
