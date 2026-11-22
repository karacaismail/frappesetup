# Press sunucu kurulumu devir notu

Bu not DevOps sorumlusu içindir. Not hazırlık sunucusunda yapılacak işi anlatır.
Gerçek sunucu denemesi yapılmadı.

## Ne hazır

- Press geliştirme ortamı `ansible==14.6.0` ve `ansible-core==2.21.6` kullanır.
- Press'in `runner.py` dosyası değişmedi. `press_tr.ansible_bridge` modülü eksik davranışı tamamlar.
- `server.yml` ve `self_hosted.yml` dosyaları söz dizimi testini geçti.
- Press'in görev sonuçlarını kaydetmesi yerel testte doğrulandı.

Ayrıntı [karar notundadır](../../docs/decisions/0018-press-ansible-python314.md).

## Yerel kurulum denemesi

Press, kurulumu iş kuyruğuna ekler. Kuyruk, arka planda çalışacak işleri tutar.
Yerel deneme, Press'in kurulum görevini çalıştırıp sonucunu yazdığını doğruladı.

1. `fs-pd-press-provision` projesinde `press.localhost` sitesini hazırlayın.
2. Aynı ağa `fs-pd-press-provision-target` adlı tek kullanımlık Ubuntu 22.04 container’ı ekleyin.
3. Hedefte Python 3, SSH sunucusu, `sudo` ve `iproute2` hazır olsun.
   Hedef, kendi ağ yolunu değiştirebilmeli.
4. Press container’ında tek kullanımlık SSH anahtarı üretin.
5. Hedefte yalnız açık anahtara izin verin. Press container’ında hedefin SSH kimliğini doğrulayın.
6. Depo kökünde aşağıdaki komutu çalıştırın.

```sh
PANE_PORT=47330 backend/dev/press/provisioning_smoke.sh
```

Betik hedefin dış ağ yolunu kapatır. Paket indirme isteğini hedefin kendi içine yönlendirir.
Press, `self_hosted.yml` dosyasını SSH üzerinden çalıştırır.
Test, paket listesini yenileme hatasının görev kaydına yazılmasını bekler.
Test bittiğinde hedefi ve tek kullanımlık anahtarı silin.

### Yerel sonuç

Press, SSH üzerinden Ubuntu bilgilerini topladı.
Press, “Update APT Cache” görevini “Failure” olarak kaydetti. Görev sonucu doluydu.
Bu hata bekleniyordu. Hedefin dış ağa erişimi kapalıydı.
“Ansible Play” durumu “Failure”, “Server” durumu “Broken” oldu.
Kalan 101 görev “Pending” durumunda kaldı.

### Gerçek sunucuda sınanacak işler

- Paket kurulumu ve kalan 101 görev gerçek sunucuda sınanacak.
- Ağ yönlendirme, disk bağlama ve güvenlik duvarı `server.yml` ile sınanacak.
- SSH ve sistem güvenliği adımları da `server.yml` ile sınanacak.
- Press Agent sağlık yanıtı ve ikinci kurulum gerçek sunucuda doğrulanacak.

## Sizden istenenler

1. Tek kullanımlık bir hazırlık sunucusu açın. Sunucu silinebilir olmalı.
   Press'in kurulum dosyaları Ubuntu içindir. Sunucuya yalnız bu iş bağlansın.
2. Sunucuda `root` kullanıcısı için tek kullanımlık SSH anahtarına izin verin.
   Parola ile girişi kapatın. Press çalışanında SSH bağlantısını doğrulayın.
3. Press sitesinde dört kayıt açın: "Cluster", "Proxy Server", "Database Server", "Server".
   "Server" kaydına sunucunun genel ve özel IP adresini yazın.
4. "Server" kaydında "Setup Server" düğmesine basın. Press `server.yml` dosyasını çalıştırır.
5. "Ansible Play" kaydını açın. Durum "Success" olmalı. Her "Ansible Task" kaydının sonucu dolu olmalı.
6. Press Agent sağlık yanıtını kontrol edin. "Server" kaydında durum "Active" olmalı.
7. Aynı sunucuda "Setup Server" işini bir kez daha çalıştırın. Sonuç yine "Success" olmalı.
8. Sunucuyu silin. Silme adımlarını ve süresini bu nota ekleyin.

## Kabul ölçütü

- İlk kurulum "Success" ile biter. İkinci kurulum da "Success" ile biter.
- "Server" durumu "Active" olur. Press Agent sağlık yanıtı gelir.
- Hiçbir "Ansible Task" kaydı "Pending" kalmaz.

## Bilinen sınırlar

- `async` kullanan Press kurulum dosyaları çalışmaz. `server.yml` bunlardan değildir.
  Örnek: `docker_system_prune.yml`. Düzeltme Press'e gönderilmelidir.
- `bench` komutuyla doğrudan çalıştırılan oyunlarda köprü kendiliğinden açılmaz.
  Bu komutlardan önce şu iki değişkeni verin:

  ```sh
  export ANSIBLE_STDOUT_CALLBACK=press_tr_bridge
  export ANSIBLE_CALLBACK_PLUGINS=/path/to/apps/press_tr/press_tr/ansible_bridge/callback_plugins
  ```

- Ansible Core 2.21 güvenlik düzeltmesini Mayıs 2027'ye kadar alır. O tarihten önce sürüm yükseltilir.
- Press kodundaki yerel geliştirme yaması ayrı bir iştir. Üretim imajında yama yoktur (O-18).

## Geri alma

Hazırlık sunucusu tek kullanımlıktır. Geri alma sunucuyu silmektir.
Press sitesinde "Server" kaydını "Archived" yapın. Sonra sunucuyu sağlayıcıda silin.
Ansible sürümünü geri almak için [karar notundaki](../../docs/decisions/0018-press-ansible-python314.md) adımları izleyin.
