# HRMS TR

HRMS TR, izin taleplerini Frappe ve HRMS üzerinde yönetir.
Uygulama GPL-3.0 lisansını kullanır.

## Kayıt saklama temizliği

Hukuk sorumlusu süreyi belirleyince site ayarında `hrms_tr_retention_days` değerini sayı olarak girin.
Bu ayar yoksa komut durur. Varsayılan saklama süresi yoktur.
Komut, işten ayrılma tarihi sınırdan eski olan çalışanları seçer.
İzin kaydının bitiş tarihi sınıra eşit veya daha yeniyse çalışan ve izinleri kalır.

Önce yedek alın. Sonra komutun göstereceği kayıt sayılarını kontrol edin.

```sh
bench --site <site> execute hrms_tr.retention.purge
```

Bakım sırasında bu kayıtlara yazan web ve kuyruk süreçlerini durdurun.
Sayıları kontrol ettikten sonra silme komutunu çalıştırın.

```sh
bench --site <site> execute hrms_tr.retention.purge --kwargs '{"dry_run": False}'
```

Komut, gönderilmiş izin kayıtlarını Frappe üzerinden iptal eder ve kalıcı siler.
Frappe bir bağlantı veya iptal kuralı nedeniyle işlemi durdurabilir.
Bu durumda komut hata verir. Geri dönüş için veritabanı yedeği kullanılır.

Komut yalnız çalışan ve izin kayıtlarını kapsar.
Kullanıcı hesapları, denetim kayıtları ve yedekler bu işlemin kapsamı dışındadır.
