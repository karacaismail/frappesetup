# Yamasız Press denemesi

Press v0.154.1 yamasız açılmadı. O-18 borcu açıktır.
İki Press modülü, Python 3.14 ve Frappe 16 ile hata verir.
Ayrıntılar ve önerilen düzeltmeler [Press önerisindedir](../../docs/press-python314-upstream.md).

## Deneme imajı

`Dockerfile.unpatched`, mevcut `frappe/erpnext:v16.55.0` imajını kullanır.
Bu temel imajda Python 3.14.10 ve Frappe 16.56.0 gözlendi.
Press etiketi `v0.154.1` olarak sabittir. Kaynak commit kodu da denetlenir.
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

Görev C için `fs-pd-press-py314:probe` etiketi bırakılır.
Bu etiket yalnız hata kanıtını yeniden üretir. Çalışan Press ortamı değildir.
Gerekmeyen eski deneme etiketleri silinir. Başka işlerin imajlarına dokunulmaz.

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
