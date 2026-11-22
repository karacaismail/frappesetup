# Press sunucu kurma yolu

Press v0.154.1, Ansible 3.4.0 ister. Deneme ortamında Ansible Base 2.10.17 çalışır.
Python 3.14 ile eski Ansible yükleyicisi çalışmaz. Yerel Press yaması bu yükleyiciyi kapatır.

`provisioning_probe.yml` yerel bir Ansible görevi çalıştırır.
Görev bağlantı açmaz ve makinede değişiklik yapmaz.
Aynı görev mevcut ortamda kaldı. Python 3.14.10 ve Ansible Core 2.21 ile geçti.
Bu sonuç Press sunucu kurulumunu doğrulamaz.

```sh
ansible-playbook -i localhost, backend/dev/press/provisioning_probe.yml
```

## Önerilen sıra

1. Press kaynak kodunu sürüm kaydına sabitleyin.
2. Python 3.14 destekleyen bir Ansible sürümü seçin.
3. Ansible paketlerini ve koleksiyonlarını sabitleyin.
4. Press'in `Ansible` sınıfını yeni Ansible ile sınayın.
5. `server.yml` ve `self_hosted.yml` dosyalarını söz dizimi için sınayın.
6. Hüseyin Cengiz ile tek kullanımlık bir hazırlık sunucusu seçin.
7. Ayrı Frappe 16 sitesinden Press kurulum işini çalıştırın.
8. İş kaydını, görev sonuçlarını ve Press Agent sağlık yanıtını kontrol edin.
9. Aynı kurulum işini tekrar çalıştırın. Sonucu ve geri alma adımlarını kaydedin.

Press, Ansible yürütücüsünü ve görev geri çağrılarını Python içinde kullanır.
Bu nedenle yalnız komut satırı testi yeterli değildir.
Önce Press'in yükleyici ve görev sonuçlarını işleyen testleri geçmelidir.

Üretime geçiş için hazırlık sunucusunda Press kurulum işi bitmelidir.
Press, ilk kurulumdan sonra Agent sağlık yanıtını görmelidir.
Hüseyin Cengiz hazırlık ortamını ve geri alma adımlarını doğrular.

[Ansible sürüm ve Python desteği](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html)
