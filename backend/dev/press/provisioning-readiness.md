# Press sunucu kurma yolu

Press v0.154.1, Ansible 3.4.0 ister. Bu paket Python 3.14 üzerinde açılmaz.
Geliştirme ortamı bunun yerine `ansible==14.6.0` ve `ansible-core==2.21.6` kullanır.
Sabit sürümler `ansible-requirements.txt` dosyasındadır. Seçim [karar notundadır](../../docs/decisions/0018-press-ansible-python314.md).

Press'in `runner.py` dosyası yeni Ansible ile tek başına çalışmaz.
`press_tr.ansible_bridge` modülü eksik iki davranışı Press'in dışından tamamlar.
Ayrıntı karar notundadır.

`provisioning_probe.yml` yerel bir Ansible görevi çalıştırır.
Görev bağlantı açmaz ve makinede değişiklik yapmaz.
Bu sonuç Press sunucu kurulumunu doğrulamaz.

```sh
ansible-playbook -i localhost, backend/dev/press/provisioning_probe.yml
```

## Önerilen sıra

1. Press kaynak kodunu sürüm kaydına sabitleyin. Yapıldı: `install.sh` `v0.154.1` etiketini ve `7a4384d` kaydını denetler.
2. Python 3.14 destekleyen bir Ansible sürümü seçin. Yapıldı: Ansible Core 2.21.6.
3. Ansible paketlerini ve koleksiyonlarını sabitleyin. Yapıldı: `ansible-requirements.txt` ve `uv-overrides.txt`.
4. Press'in `Ansible` sınıfını yeni Ansible ile sınayın. Yapıldı: `test_ansible_runner.py` ve `ansible_runner_harness.py`.
5. `server.yml` ve `self_hosted.yml` dosyalarını söz dizimi için sınayın. Yapıldı: `test_ansible_playbook_syntax.py`.
6. DevOps sorumlusu ile tek kullanımlık bir hazırlık sunucusu seçin.
7. Ayrı Frappe 16 sitesinden Press kurulum işini çalıştırın.
8. İş kaydını, görev sonuçlarını ve Agent sağlık yanıtını kontrol edin.
9. Aynı kurulum işini tekrar çalıştırın. Sonucu ve geri alma adımlarını kaydedin.

6. adımdan 9. adıma kadar olan işler gerçek sunucu ister.
Bu işler [devir notunda](provisioning-handoff.md) anlatılır.

## Denetimler

Testler Python 3.14 ve sabit Ansible ister. İki ortam değişkeni gerekir.
`PRESS_TEST_ANSIBLE_PYTHON` değişkeni Ansible kurulu Python yolunu gösterir.
`PRESS_TEST_PRESS_SOURCE` değişkeni temiz Press kaynağını gösterir.
Değişkenler yoksa testler atlanır.

```sh
PRESS_TEST_ANSIBLE_PYTHON=/path/to/venv/bin/python PRESS_TEST_PRESS_SOURCE=/path/to/press \
  python3.14 -B -m unittest discover -s backend/dev/press -p 'test_ansible_*.py'
```

Testler şunları gösterir:

- Press tek başına kurulum dosyasını okuyamaz. Köprü olmadan `ansible.builtin.command` bulunamaz.
- Köprü ile görev sonuçları "Ansible Task" kaydına yazılır. Başarılı, atlanan ve başarısız görev denendi.
- Köprü Ansible'dan önce de sonra da etkinleştirilebilir.
- `async` görevler Press tarafında hâlâ düşer. Test bunu beklenen hata olarak kaydeder.

Press, Ansible yürütücüsünü ve görev geri çağrılarını Python içinde kullanır.
Bu nedenle yalnız komut satırı testi yeterli değildir.

Üretime geçiş için hazırlık sunucusunda Press kurulum işi bitmelidir.
Press, ilk kurulumdan sonra Agent sağlık yanıtını görmelidir.
DevOps sorumlusu hazırlık ortamını ve geri alma adımlarını doğrular.

[Ansible sürüm ve Python desteği](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html)
