# Planları ve fiyat değişikliğini doğrulayın

Bu iş G-9 ve G-10 gereksinimidir. Git dalı `pc/g9-g10-pricing` adını taşır.

Bütün plan değerleri `backend/apps/press_tr/press_tr/plans.py` dosyasındadır. Değer değişirse yalnız bu dosyayı değiştirin.

## Planlar

Proje sahibi fiyatları 24 Kasım 2026 Salı günü verdi.

| Plan | Kayıt adı | Fiyat |
| --- | --- | --- |
| Başlangıç | `press-tr-starter` | Aylık 400 dolar |
| Büyüme | `press-tr-growth` | Aylık 750 dolar |
| Kurumsal | `press-tr-enterprise` | Fiyat yazılmaz |
| Deneme | `press-tr-trial` | 14 gün ücretsiz |

Fiyatlar dolar olarak saklanır ve gösterilir. Türk lirası alanı yoktur.

Kurumsal plan müşteri listesinde görünmez. Bu planı yalnız yönetici atar. Panel bu plan için "Fiyat için bize ulaşın" yazar.

## Güncellemede olan işler

Frappe güncellemeyi `bench migrate` komutuyla yapar. Güncelleme sonunda `press_tr` şu işleri yapar:

1. G-8 temizliği Press'in hazır planlarını kapatır.
2. `press_tr` fiyat başlangıç alanlarını kurar.
3. `press_tr` eksik planları kapalı olarak ekler.
4. `press_tr` Press ayarındaki deneme planını `press-tr-trial` yapar.
5. Sınırı boş olan her plan için bir uyarı yazılır.

Güncelleme var olan plan kaydını değiştirmez. Fiyat yalnız yeni plan kaydıyla değişir.

## Açık kalan kararlar

Plan sınırları henüz verilmedi. Sınırlar veritabanı boyutu, dosya alanı, yedek sayısı, rol sayısı ve uygulama sayısıdır. Sınırlar boş kalır. Bu yüzden her güncelleme "missing limits" uyarısı verir.

Press'te yalnız iki sınır için alan vardır. Bu alanlar `max_database_usage` ve `max_storage_usage` alanlarıdır. Diğer üç sınır için tasarım kararı gerekir.

Planlar kapalı eklenir. Sınırlar gelince yönetici planı yönetim ekranında açar.

## Fiyat değişikliği

Yönetici fiyatı en az 30 gün önceden değiştirir. Örnek komut şudur:

```bash
bench --site <press-site> execute press_tr.pricing.create_price_revision --kwargs '{"plan": "press-tr-starter", "name": "press-tr-starter-2027", "price_usd": "450", "effective_date": "2027-01-31"}'
```

1. Komut yeni planı kapalı olarak açar.
2. Her abone ekibine e-posta ve Press bildirimi gider.
3. Başlangıç günü yönetici yeni planı elle açar.
4. Aboneler yeni plana geçer.
5. Eski plan eski plan olarak işaretlenir ve kapanır.

Bu işlem HTTP yöntemi değildir. Müşteri bu işlemi çağıramaz.

## Deneme süresi

Deneme planındaki yeni sitenin bitiş günü 14 gün sonrasıdır. Press'te deneme bitince siteyi durduran iş yoktur.

Yönetici şu komutla süresi biten siteleri durdurur:

```bash
bench --site <press-site> execute press_tr.plans.suspend_expired_trials
```

Kiracı ücretli plan seçerse Press siteyi yeniden açar. Bunu Press'in `Site.change_plan` işlemi yapar.

Bu komutu otomatik çalıştırmak zamanlanmış iş ister. Zamanlanmış iş için insan kararı gerekir.

## Ayrı deneme sitesinde yapılacaklar

1. Dalı ayrı bir Press deneme sitesine kurun.
2. `bench --site <test-site> migrate` komutunu çalıştırın.
3. Dört planın kapalı eklendiğini doğrulayın.
4. Press ayarında deneme planının `press-tr-trial` olduğunu doğrulayın.
5. Dört sınır uyarısının çıktıda göründüğünü doğrulayın.
6. Fiyat değişikliği komutunu deneme planı dışında bir planla çalıştırın.
7. Bildirimin ve e-postanın oluştuğunu doğrulayın.

Canlı sunucuda ve çalışan 7400 ortamında veri güncellemesi yapılmadı.
