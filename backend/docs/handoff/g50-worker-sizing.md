# G-50 işçi, zamanlayıcı ve kuyruk ayarları

Bu not canlı adımları anlatır. Adımları kıdemli DevOps sorumlusu uygular.
Adımlar önce yetkili deneme ortamında denenir.

## Kaynaklar

- Başlangıç değerleri `backend/dev/worker_sizing.json` dosyasında durur.
- Denetim betiği `backend/dev/worker_sizing.py` dosyasıdır.
- Betik `backend/dev/config_layers.py` dosyasını da kullanır.
- Bu değerler ilk değerlerdir. G-149 yük ölçümünden sonra değerler değişir.

Betik yalnız Python'un kendi parçalarını kullanır. Betik ağa çıkmaz.
Betik yanlış ya da eksik değerde 1 koduyla çıkar.

## Önce bilinmesi gerekenler

- Press, Frappe 15 ve sonrası için yeni gruba 4 thread verir. G-50 değeri 2 thread'dir. Bu yüzden her yeni grupta değeri elle 2 yapın.
- Press, iki kuyruk birleştirme kutusunun birlikte açılmasını reddeder. `merge_all_rq_queues` kapalı kalmalıdır.
- Gunicorn `threads` değerini yalnız gthread işçisinde kullanır.
- Sync işçide thread sayısı 1'den büyükse gunicorn sessizce gthread'e geçer.
- Öteki işçi türleri thread değerini yok sayar.
- `reports` kuyruğunun süre sınırı G-50'de yazmıyor. Süre bilinmiyor. Frappe bu kuyruğa varsayılan 300 saniyeyi verir.

## Betiği nerede koşmalı

Ortak ayar dosyası gizli değerler de taşır. Bu dosyayı sunucudan dışarı taşımayın.

1. Üç dosyayı sunucuda geçici bir klasöre kopyalayın: `worker_sizing.py`, `worker_sizing.json`, `config_layers.py`.
2. Betiği o klasörde `python3 -I worker_sizing.py` ile koşun.
3. İş bitince geçici klasörü silin.

Betik hata satırında yalnız G-50 ayarının değerini yazar. Öteki gizli değerleri yazmaz.

## Canlı adımlar

### 1. Release Group işçi ayarları

- Ayarı Release Group formunun “Config” sekmesinde yapın. Değerler şunlardır:
  - `min_gunicorn_workers` 2, `max_gunicorn_workers` 8,
  - `min_background_workers` 2, `max_background_workers` 6,
  - `gunicorn_threads_per_worker` 2,
  - `use_rq_workerpool` 1, `merge_default_and_short_rq_queues` 1.
- Şu komutlar grubun alanlarını dosyaya yazar ve denetler. Komutları Press bench'inde koşun.

```sh
bench --site <press-sitesi> execute frappe.client.get --kwargs '{"doctype": "Release Group", "name": "<grup>"}' > rg.json
python3 -I worker_sizing.py --release-group rg.json
```

- Betik 0 koduyla çıkarsa adım kabul edilir. Bu durumda betik hiçbir satır yazmaz.

### 2. Bench otomatik işçi ölçeği

- Grubun her etkin Bench kaydında `auto_scale_workers` değerini 1 yapın.
- Şu komutlar Bench kaydını denetler.

```sh
bench --site <press-sitesi> execute frappe.client.get --kwargs '{"doctype": "Bench", "name": "<bench>"}' > bench.json
python3 -I worker_sizing.py --bench bench.json
```

- Betik 0 koduyla çıkarsa adım kabul edilir.

### 3. Gunicorn işçi türü

- Gunicorn gthread işçisiyle ve 2 thread ile çalışmalıdır.
- Bench kabının içinde gunicorn sürecinin komut satırını okuyun. Şu komutları kullanın.

```sh
ps -eo args | grep '[g]unicorn'
python3 -I worker_sizing.py --release-group rg.json --gunicorn-worker-class <okunan-tür>
```

- Komut satırında işçi türü yoksa gunicorn sync türünü kullanır. Bu durumda `sync` yazın.
- Komut satırında gthread türü ve 2 thread görünürse adım kabul edilir. Betik de 0 koduyla çıkmalıdır.
- Betik "sync worker switches to gthread" derse işçi türü açıkça seçilmedi demektir. Bu durumu görev kaydına yazın.

### 4. Ortak zamanlayıcı ve kuyruk ayarları

- Release Group ortak ayar tablosuna iki satır ekleyin.
  - `scheduler_tick_interval` 60.
  - `workers` değeri `{"long": {"timeout": 3000}, "reports": {}}`.
- Press `update_config` işini tamamlar. Sonra değerler bench'in ortak ayar dosyasına iner.
- Şu komut ortak ayar dosyasını denetler.

```sh
python3 -I worker_sizing.py --common-site-config <bench>/sites/common_site_config.json
```

- Betik 0 koduyla çıkarsa adım kabul edilir. Betik G-38 katman kuralını da denetler.

### 5. Her yeni sitede zamanlayıcı açık

- Her yeni sitede `System Settings.enable_scheduler` değeri 1 olmalıdır.
- Her site için değeri şu komutla okuyun. Sonuçları tek bir dosyada toplayın.

```sh
bench --site <site> execute frappe.db.get_single_value --args "['System Settings', 'enable_scheduler']"
```

Dosyanın biçimi `{"<site>": {"enable_scheduler": 1}}` olmalıdır.

```sh
python3 -I worker_sizing.py --system-settings sites.json
```

- Betik 0 koduyla çıkarsa adım kabul edilir. Betik, değeri 1 olmayan siteyi yazar.

## Sonuç kaydı

Sonucu görev kaydına yazın. Tam ayar dosyasını ve gizli değerleri paylaşmayın.
Canlı ortamda bu adımlar henüz denenmedi.

## Yazışma kanalı

Ortak işlerde ekip proje Telegram grubunda yazışır. Bu kural 26 Kasım 2026 Perşembe günü konuldu. Grubun adresi ve kişi adları depoya yazılmaz.
