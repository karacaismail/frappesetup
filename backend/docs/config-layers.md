# G-38 ayar katmanları

Bench, birden çok Frappe sitesini çalıştıran ortamdır.
Ortak ayarlar `sites/common_site_config.json` dosyasındadır.
Site ayarları `sites/<site>/site_config.json` dosyasındadır.

| Katman | Ayar | Açıklama |
| --- | --- | --- |
| Ortak bench | `mail_*` | Siteler ortak posta ayarlarını kullanır. |
| Ortak bench | `workers`, `background_workers`, `gunicorn_workers` | Bu değerler bench'in işlem sayısını belirler. |
| Ortak bench | `redis_cache`, `redis_queue`, `redis_socketio` | Siteler ortak Redis bağlantılarını kullanır. |
| Ortak bench | `socketio_port`, `webserver_port` | Bu değerler bench'in bağlantı noktalarını belirler. |
| Site | `db_name`, `db_password`, `db_type`, `db_user` | Her site kendi veritabanı ayarlarını tutar. |
| Site | `encryption_key`, `backup_encryption_key`, `keycloak_client_secret`, `sk_*` | Her site kendi gizli değerlerini tutar. |
| Site | `host_name`, `plan_limit` | Her site kendi adresini ve plan sınırını tutar. |
| Site | `allow_tests`, `developer_mode`, `mute_emails` | Yerel hazırlık betiği bu değerleri siteye yazar. |
| Her iki katman | `db_host`, `pause_scheduler`, `disable_scheduler`, `server_script_enabled` | Site bir değer verirse Frappe o değeri kullanır. |
| Yasak | `allow_cors` | G-119 bu ayarı iki katmanda da yasaklar. |

Frappe, site kurulurken verilen `db_host` değerini site dosyasına yazabilir.
Yerel hazırlık betiği zamanlayıcıyı iki katmanda da kapatır.
Denetim, tablonun dışında kalan ayarları değiştirmez veya reddetmez.

## Denetim

Depo kökünden şu komutu çalıştırın.

```sh
python3 backend/dev/config_layers.py <bench-sites-directory>
```

Betik ortak dosyayı ve alt klasörlerdeki site dosyalarını okur.
Yanlış katmanda bir ayar bulursa 1 koduyla çıkar.
Çıktı dosya adını ve ayar adını gösterir. Ayarın değeri yazılmaz.

## Yerel test

Depo kökünden `backend/dev/bin/verify-config-layers` komutunu çalıştırın.
Komut, yerelde bulunan sabit sürümlü imajı kullanır.
Komut ağ erişimi kapalı, geçici bir ortam açar.
Test iki site ayar dosyası oluşturur.
Test ortak `mail_port` değerini 2525'ten 2526'ya çıkarır.
`bench show-config` iki sitede de yeni değeri göstermelidir.
Test iki site dosyasının aynı kaldığını da doğrular.
