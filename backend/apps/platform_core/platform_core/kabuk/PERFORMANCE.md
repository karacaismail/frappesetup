# O-31 kabuk ölçümü

ERPNext, HRMS ve `platform_core` kurulu bir test sitesi kullanın.
Site adı `perf-` ile başlamalı ve `.localhost` ile bitmeli.
Site ayarında `allow_performance_fixture` değeri 1 olmalı.
Bench kuyrukları boş olmalı.
Çalışan ve izin tablosu boş olmalı.
Komutu Bench klasöründen çalıştırın.

```sh
bench --site perf-kabuk.localhost set-config allow_performance_fixture 1
env/bin/python -m platform_core.kabuk.measure_performance --site perf-kabuk.localhost --status-file /yol/durum.md
```

Komut 200 çalışan ve 2.000 izin kaydı ekler.
Komut ölçüm sonunda eklediği kayıtları tür ve ad çiftiyle siler.
Ölçüm bitince deneme sitesini silebilirsiniz.
İstekler yerel HTTP üzerinden sırayla gider. Hesapta HR User rolü vardır.
DocType ucu `Leave Application` tanımını döner.

Komut her uca önbellekli 50, önbelleksiz 50 istek gönderir.
Önbellekli koşu ölçümden önce uca bir kez gider.
Önbelleksiz koşu her istekten önce Frappe önbelleğini temizler.
Veritabanı ve işletim sistemi önbelleği ölçüm sırasında korunur.
Tüm ölçümler tam HTTP 200 yanıtı kullanır.

Sunucu süresi, isteğin alınmasından yanıt başlıklarının hazır olmasına kadar ölçülür.
p95, sıralı ölçümlerin yüzde 95 konumundaki süredir.
Komut sonuç tablosunu durum dosyasına ekler.
Önbellekli açılış için p95 sınırı 200 ms'dir.
Diğer koşularda p95 sınırı 500 ms'dir.
Bir koşu kendi sınırını aşarsa komut 1 döndürür.
