# Press geliştirme ortamı

Bu kurulum ayrı bir yerel Press sitesi açar. Press, kiracı sitelerini yönetir.

Frappe v16.50.0 ve Press v0.154.1 kullanılır. Python sürümü 3.14.10'dir.
Uyum yamaları yalnız yerel Press denemesi içindir.
Sunucu kurma ve Ansible bu kurulumda çalışmaz.

Komutları depo kökünde çalıştırın. Birleşik kaynakta `backend/libs/oidc_verify` bulunmalı.
Press imajı bu kitaplığı bir Python kurulum paketi olarak taşır.
Kurulum betiği paketi Bench ortamına kurar.
Yerel kurulum, Press test paketlerini `apps/press_tr[test]` seçeneğiyle kurar.

Yalnız yerel denemede örnek parolaları kullanın.

```sh
export PRESS_ENV_FILE="$PWD/backend/dev/press/.env.example"
bash backend/dev/press/compose.sh up -d
bash backend/dev/press/compose.sh exec -T --user root web \
  install -d -o frappe -g frappe /home/frappe/benches /home/frappe/benches/source
bash backend/dev/press/compose.sh cp backend/apps/press_tr web:/home/frappe/benches/source/
bash backend/dev/press/compose.sh exec -T web bash -s < backend/dev/press/install.sh
bash backend/dev/press/compose.sh exec -d web bash -lc \
  'cd /home/frappe/benches/frappe-bench && exec bench start > logs/bench-start.log 2>&1'
```

Press web portu `PANE_PORT + 3` olur. Socket.IO portu `PANE_PORT + 4` olur.
Kurulum parolaları Compose gizli dosyalarından okunur. Parolalar komut satırına yazılmaz.
MariaDB içe aktarımı, site parolasını geçici ve özel bir dosyadan okur.

Site ayarları [Press TR kurulumunda](../../apps/press_tr/README.md) yer alır.

Anonim yapma süresini yalnız geçici test sitesinde ölçün.
Betik 50 ayrı hesap kullanır. İlk çağrıların yüzde 95'i 1 saniyede bitmelidir.

```sh
PRESS_TEST_MEASURE_ANONYMIZATION=1 PRESS_TEST_PANEL_URL=http://kiraci1.localhost:3201/panel \
  sh backend/apps/press_tr/tests/run.sh
```

Duman testi, sitenin yanıtını ve kurulu uygulamaları denetler.

```sh
sh backend/apps/press_tr/tests/smoke.sh
```

İş bitince yalnız bu işe ait ortamı kapatın.

```sh
bash backend/dev/press/compose.sh down
```

`patch-py314.sh` Press kaynaklarına uyum yaması uygular.
Bu yama yalnız `development` imajında bulunur ve çalışır (O-18).
`runtime-check` hedefinde yama ve geliştirme işareti yoktur.
Bu hedef dağıtım için hazır bir Press kurulumu içermez.

Birleşik kaynaktan üretim hedefini oluşturup yama engelini sınayın.

```sh
docker --context colima-factory build --target runtime-check \
  -f backend/dev/press/Dockerfile -t press-runtime-check .
PRESS_TEST_RUNTIME_IMAGE=press-runtime-check \
  python3 -B -m unittest discover -s backend/dev/press
```

Üretim kurulumunda paket ve doğrulama özeti onaylı sürümden gelir.
Betik paketi internetten indirmez. Özeti denetleyip belirttiğiniz Python ortamına kurar.

```sh
bash backend/dev/press/install_runtime_oidc.sh /path/to/release-wheels /path/to/bench/env/bin/python
```

Betik `PRESS_OIDC_WHEEL_SHA256` değişkenini okur. Bu değeri güvenilir sürüm bildiriminden alın.
Testte `PRESS_TEST_CLEAN_SOURCE` değerine temiz Press kaynak klasörünü yazın.

Frappe 16.50 içe aktarım sırasında site parolasını komut satırına ekler.
Yerel kurulum betiği yalnız içe aktarım boyunca bu çağrıyı sarar.
MariaDB parolayı geçici dosyadan okur. Üretim kurulumu bu betiği kullanmaz.
