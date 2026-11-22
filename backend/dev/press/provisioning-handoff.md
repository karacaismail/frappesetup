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

1. Yerel geliştirme ayarlarını yükleyin. `PANE_PORT` değerini çalışma alanınızdan alın.
2. `fs-pd-press-provision` projesinde `press.localhost` sitesini hazırlayın.
   Site kurulumu için [Press geliştirme adımlarını](README.md) izleyin.
3. Aşağıdaki komutla Ubuntu 22.04 hedefini aynı ağa ekleyin.

```sh
provision_compose() {
  backend/dev/press/compose.sh --project-name fs-pd-press-provision \
    --file "$PWD/backend/dev/press/compose.provisioning.yaml" "$@"
}
provision_compose up -d --build target
```

Hedef imajının Ubuntu tabanı sabit özetle doğrulanır.
Hedef, bilgisayara port açmaz. Betik hedefin ağ yolunu değiştirebilir.
`FS_COLIMA_PROFILE` değeri `factory` veya `default` olabilir.
Değer boşsa betik `factory` profilini kullanır.

Yeni ortamda aşağıdaki komutları bir kez çalıştırın.
Komutlar tek kullanımlık anahtar üretir ve yalnız açık anahtarı hedefe taşır.
Press, hedefin kimliğini doğrudan hedefteki açık anahtar dosyasından alır.

```sh
provision_compose exec -T web sh -eu -c '
  install -d -m 0700 "$HOME/.ssh"
  test ! -e "$HOME/.ssh/id_ed25519"
  ssh-keygen -q -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519"
'
provision_compose exec -T web sh -ec 'cat "$HOME/.ssh/id_ed25519.pub"' |
  provision_compose exec -T target sh -eu -c '
    install -d -m 0700 /root/.ssh
    umask 077
    cat > /root/.ssh/authorized_keys
  '
target_ip="$(provision_compose exec -T target hostname -i)"
target_public_key="$(provision_compose exec -T target cat /etc/ssh/ssh_host_ed25519_key.pub)"
printf '%s %s\n' "$target_ip" "$target_public_key" |
  provision_compose exec -T web sh -eu -c '
    umask 077
    cat >> "$HOME/.ssh/known_hosts"
  '
backend/dev/press/provisioning_smoke.sh
```

Betik hedefin dış ağ yolunu kapatır. Paket indirme isteğini hedefin kendi içine yönlendirir.
Press, `self_hosted.yml` dosyasını SSH üzerinden çalıştırır.
Test, paket listesini yenileme hatasının görev kaydına yazılmasını bekler.
Test bittiğinde geçici ortamı ve imajlarını silin. Tek kullanımlık anahtar da silinir.

```sh
provision_compose down --volumes --rmi local
```

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
