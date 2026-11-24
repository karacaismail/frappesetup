# Keycloak canlı olay kanıtı

Koşu 22 Kasım 2026 Pazar günü yapıldı.
Ortam Colima'nın `factory` profilidir. Port tabanı 7150'dir.
Proje adı `fs-e2e-7150-8ceae9a08e8e3b85fd78` oldu.
Yerel imajlar bu çalışma ağacının proje adıyla derlendi.

## Canlı sonuç

Test, Keycloak yönetim API'siyle örnek bir kullanıcı oluşturdu ve değiştirdi.
Başarılı olayı test göndermedi. Keycloak dinleyicisi olayı gerçek `identity-sync` servisine gönderdi.
Test, Keycloak olay kimliğini alıcının veritabanındaki kayıtla eşleştirdi.

```json
{"source":"Keycloak","event":"USER_UPDATE","event_id":"f123367d-ff35-442b-b0ef-0760989193f6","status":"processed"}
{"case":"bad_signature","http_status":401,"status":"rejected"}
{"case":"stale_timestamp","http_status":401,"status":"rejected"}
```

Test çıkış kodu sıfır oldu.
Eski zaman denemesinde imza doğru sırla hesaplandı. Zaman damgası 600 saniye eskiydi.
İki ret yanıtı da `bad_signature` hatasını taşıdı.
Reddedilen olay, işlenen olaylar tablosuna veya hata kuyruğuna girmedi.
Sır yalnız ortam değişkeninden alındı. Çıktıya parola veya belirteç yazılmadı.

## Komutlar ve kapsam

Komutlar depo kökünde çalıştırıldı.

```sh
PANE_PORT=7150 FS_COLIMA_PROFILE=factory backend/e2e/stack up
PANE_PORT=7150 FS_COLIMA_PROFILE=factory python3.14 backend/e2e/keycloak_delivery.py
PANE_PORT=7150 FS_COLIMA_PROFILE=factory backend/e2e/stack down
```

Yığın açılışı sıfır çıkış koduyla tamamlandı. Bütün sağlık denetimleri geçti.
Olay testi, tamamlanan kurulumun ardından yeniden çalıştırıldı.
Yığın `stack down` ile kapatıldı. Kapatma komutu sıfır çıkış koduyla tamamlandı.
Bu projeye ait container kalmadı. Veri birimleri korundu.
Kurulum sırasında ilk deneme zaman aşımı verdi. Aynı test, sınırları değiştirilmeden tekrar çalıştırıldı.
Yukarıdaki kayıt, kurulumdan sonraki başarılı koşunun çıktısıdır.

Örnek kullanıcının kuruluş üyeliği yoktur. Bu test otomatik olay teslimini ve imza reddini doğrular.
Press ve kiracıdaki kullanıcı değişiklikleri bu testin kapsamına girmez.
CI çalıştırılmadı. Gerçek okurla denenmedi.
