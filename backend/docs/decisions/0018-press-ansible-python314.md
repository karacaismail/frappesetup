# T-2. Press sunucu kurulumu için Ansible sürümü

Press sunucu kurulumunu Ansible ile yapar. Press v0.154.1 `ansible==3.4.0` ister.
Bu paket Ansible Base 2.10 taşır. Ansible Base 2.10 Python 3.12 ve üstünde açılmaz.
Press sitemiz Python 3.14 üzerinde çalışır. Bu yüzden sunucu kurulumu hiç başlamıyordu.

## Seçenekler

Üç seçenek değerlendirildi. Sürüm bilgisi PyPI kayıtlarından ve Ansible bakım tablosundan alındı.

| Seçenek | Denetim düğümü Python | Bakım durumu | Sonuç |
| --- | --- | --- | --- |
| `ansible==3.4.0` kalsın | 3.9'a kadar | Bakım bitti | Python 3.14'te açılmaz. Olmaz. |
| `ansible==14.6.0` ve `ansible-core==2.21.6` | 3.12, 3.13, 3.14 | Güvenlik düzeltmesi Mayıs 2027'ye kadar | Seçildi. |
| `ansible==15.0.0` ve `ansible-core==2.22.0` | 3.13, 3.14, 3.15 | 17 Kasım 2026'da çıktı | Çok yeni. Sonraki adım. |

## Karar

Geliştirme ortamı `ansible==14.6.0` ve `ansible-core==2.21.6` kullanır.
Sabit sürümler `backend/dev/press/ansible-requirements.txt` dosyasındadır.
Geliştirme imajı aynı sürümleri `uv-overrides.txt` ile Press'in isteğinin yerine koyar.
Test bu iki dosyanın aynı sürümü taşıdığını denetler.

Sürüm 14.6.0 seçildi. Çünkü bu dizi altı düzeltme sürümü gördü.
Daha önceki hazırlık denemesi de Ansible Core 2.21 ile geçmişti.
Sürüm 15.0.0 ile iki kurulum dosyası söz dizimi testini geçti. Yine de 15.0.0 beş günlüktür.

Koleksiyonlar `ansible` paketinden gelir. Ayrı `requirements.yml` yoktur.
Paket şu sürümleri getirir: `ansible.posix` 2.2.2, `community.general` 13.5.1, `community.mysql` 5.0.2.
Kurulum dosyaları bu üç koleksiyonu ve `ansible.builtin` modüllerini kullanır.

## Press ile üç uyumsuzluk

Press kodu değiştirilmez (M-4). Press'in `runner.py` dosyası Ansible Base 2.10'a göre yazıldı.
Yeni Ansible ile üç sorun bulundu. Sorunlar `backend/dev/press/ansible_runner_harness.py` ile gösterildi.

1. Ansible Core 2.19'dan beri eklenti yükleyicisi kendiliğinden kurulmaz.
   `init_plugin_loader()` çağrısı gerekir. Press bu çağrıyı yapmaz.
   Sonuç: `ansible.builtin.command` bile bulunamaz. Kurulum dosyası okunamaz.
2. Ansible Core 2.19'dan beri `TaskQueueManager._stdout_callback` alanı yoktur.
   Press kendi geri çağrı nesnesini bu alana yazar. Ansible bu nesneyi hiç çağırmaz.
   Sonuç: Her "Ansible Play" kaydı "Pending" kalır. Sunucu "Broken" olur.
3. Ansible Core 2.21'de `TaskExecutor._poll_async_result` imzası değişti.
   Press bu işlevi `result` adlı parametreyle sarar. Ansible artık `utr` adıyla çağırır.
   Sonuç: `async` kullanan görev "unexpected keyword argument 'utr'" ile düşer.

İlk iki sorunu `press_tr.ansible_bridge` modülü Press'in dışından çözer.
Modül Ansible'a `press_tr_bridge` adlı bir çıktı eklentisi tanıtır.
Eklenti her olayı o anda çalışan Press geri çağrısına iletir.
Modül `ansible.plugins.loader` yüklenir yüklenmez `init_plugin_loader()` çağırır.
Modül bunun için `wrapt` paketinin içe aktarma kancasını kullanır. Press de `wrapt` kullanır.
Frappe `before_job` ve `before_request` kancaları modülü etkinleştirir.

Üçüncü sorun açık kalır. `server.yml` ve `self_hosted.yml` dosyalarında `async` görev yoktur.
Press'in 13 başka kurulum dosyası `async` kullanır. Örneğin `docker_system_prune.yml` böyledir.
Bu dosyalar düzeltilene kadar çalışmaz. Düzeltme Press'e gönderilmelidir.
Test `test_async_tasks_still_break_on_press_side` bu durumu beklenen hata olarak kaydeder.

## Lisans ve bakım

`ansible` ve `ansible-core` GPL-3.0-or-later lisanslıdır. Press zaten Ansible'a bağımlıdır.
`press_tr` AGPL-3.0 lisanslıdır (O-8). `platform_core` bu paketleri kullanmaz (O-12).

Ansible Core 2.21 güvenlik düzeltmesini Mayıs 2027'ye kadar alır.
O tarihten önce `ansible==15` dizisine geçiş denenmelidir.
Ansible Core 2.23 `result._result` alanını kaldıracak. Press bu alanı kullanır.
Bu yüzden Core 2.23 öncesinde Press'in `runner.py` dosyası yukarı akışta güncellenmelidir.
`apt_key` ve `apt_repository` modülleri Core 2.25'te kalkacak. Press'in `filebeat` rolü bunları kullanır.

## Geri dönüş

Sabit sürümleri iki dosyadan silin. Press yeniden `ansible==3.4.0` ister.
Bu durumda Python 3.14'te sunucu kurulumu yine çalışmaz.
Köprüyü kapatmak için `before_job` ve `before_request` kancalarından `press_tr.ansible_bridge.activate` satırını çıkarın.

## Denetim komutları

Yerel denetim için Python 3.14 ortamına sabit Ansible kurulur.
`PRESS_TEST_ANSIBLE_PYTHON` ortamı, `PRESS_TEST_PRESS_SOURCE` temiz Press kaynağını gösterir.

```sh
uv venv --python 3.14.10 /tmp/press-ansible
uv pip install --python /tmp/press-ansible/bin/python -r backend/dev/press/ansible-requirements.txt "wrapt~=1.15.0"
PRESS_TEST_ANSIBLE_PYTHON=/tmp/press-ansible/bin/python PRESS_TEST_PRESS_SOURCE=/path/to/press \
  python3.14 -B -m unittest discover -s backend/dev/press -p 'test_ansible_*.py'
```

Geliştirme imajında aynı testler `env/bin/python` ve `apps/press` ile çalışır.
