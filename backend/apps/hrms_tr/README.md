# HRMS TR

HRMS TR, izin taleplerini Frappe ve HRMS üzerinde yönetir.
Uygulama GPL-3.0 lisansını kullanır.

## Kayıt saklama temizliği

Hukuk sorumlusu süreyi belirleyince site ayarında `hrms_tr_retention_days` değerini sayı olarak girin.
Bu ayar yoksa komut durur. Varsayılan saklama süresi yoktur.
Komut, işten ayrılma tarihi sınırdan eski olan çalışanların izin kayıtlarına bakar.
Komut, bitiş tarihi sınırdan eski olan taslak veya iptal edilmiş izin kayıtlarını seçer.

Önce yedek alın. Sonra komutun göstereceği kayıt sayılarını kontrol edin.

```sh
bench --site <site> execute hrms_tr.retention.purge
```

Komut bir seferde en çok 500 izin kaydı seçer ve kalan sayıyı gösterir.
Sınırı değiştirmek için `limit` değerini girin.

Bakım sırasında bu kayıtlara yazan web ve kuyruk süreçlerini durdurun.
Sayıları kontrol ettikten sonra silme komutunu çalıştırın.

```sh
bench --site <site> execute hrms_tr.retention.purge --kwargs '{"dry_run": False}'
```

Komut gönderilmiş izin kayıtlarını korur. Bu yüzden iptal e-postası göndermez.
HRMS, iptal sırasında “Leave Ledger Entry” ve “Attendance” kayıtlarını değiştirebilir.
Başka bir “Leave Application” kaydı, düzeltme bağlantısıyla silmeyi durdurabilir.
Özel bağlantılar da Frappe'nin silme denetimine girer.
Bu durumda komut hata verir. Geri dönüş için veritabanı yedeği kullanılır.
Hata çıkarsa ekrandaki ilk hata metnini okuyun.

Komut yalnız izin kayıtlarını siler. Çalışan kaydı kalır.
“Leave Allocation”, “Leave Ledger Entry”, “Attendance”, “Salary Slip” ve “Shift Assignment” kayıtları kalır.
Kullanıcı hesapları, denetim kayıtları ve yedekler bu işlemin kapsamı dışındadır.


## Yeni izin talebi bilgisi

Ekran, `GET /api/method/hrms_tr.api.get_leave_request_context` yolunu çağırır.
Yol yalnız oturum sahibinin etkin personel kaydını okur.
Yöneticiler de bu yoldan başka kişiyi seçemez.
Yol, genel personel okuma yetkisi vermez.

İsteğe bağlı `leave_type` alanı, izin türünün tam kayıt adını alır.
Alan verilmezse yol `Annual Leave` kaydını arar.
Yol, çevrilmiş addan veya benzer kayıttan izin türü tahmin etmez.

Yanıt, personel kimliğini, görünen adı, izin türünü ve kalan günü verir.
Yanıttaki `sources`, her alanın kaynak kayıt türünü gösterir.
Eksik değer ve kaynağı `null` olur.
İzin tahsisi yoksa bakiye `null` olur.
HRMS sıfır gün hesapladıysa bakiye `0` olur.
HRMS hesabı, sitenin bugünkü tarihine kadar olan izinleri kullanır.
Eski bakiye yollarının engelleri korunur.

Sözleşme `backend/contracts/hrms_tr.openapi.yaml` dosyasındadır.
Aşağıdaki test, Frappe ve HRMS kurulu ortamda çalışır.

```sh
python -m unittest hrms_tr.test_api.LeaveRequestContextTest
```

Sözleşme denetimi, depo kökünde şu komutla çalışır.
Komut Frappe, HRMS, PyYAML ve jsonschema paketlerini gerektirir.

```sh
python -m unittest discover -s backend/dev/hrms -p test_contract.py
```
