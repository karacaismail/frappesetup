# Planları ve fiyat değişikliğini doğrulayın

Bu iş G-9 ve G-10 gereksinimidir. İlk parçanın Git dalı `pc/g9-g10-pricing` adını taşır. İkinci parçanın dalı `pc/g9-g10-limits-try` adını taşır.

Bütün plan değerleri `backend/apps/press_tr/press_tr/plans.py` dosyasındadır. Değer değişirse yalnız bu dosyayı değiştirin.

## Planlar

Proje sahibi fiyatları 24 Kasım 2026 Salı günü verdi.

| Plan | Kayıt adı | Fiyat |
| --- | --- | --- |
| Başlangıç | `press-tr-starter` | Aylık 400 dolar |
| Büyüme | `press-tr-growth` | Aylık 750 dolar |
| Kurumsal | `press-tr-enterprise` | Fiyat yazılmaz |
| Deneme | `press-tr-trial` | 14 gün ücretsiz |

Fiyatlar dolar olarak saklanır. Türk lirası fiyatı saklanmaz. Sistem bu fiyatı günlük kurdan hesaplar. Ayrıntı aşağıdaki "Türk lirası kuru" bölümündedir.

Kurumsal plan müşteri listesinde görünmez. Bu planı yalnız yönetici atar. Panel bu plan için "Fiyat için bize ulaşın" yazar.

## Güncellemede olan işler

Frappe güncellemeyi `bench migrate` komutuyla yapar. Güncelleme sonunda `press_tr` şu işleri yapar:

1. G-8 temizliği Press'in hazır planlarını kapatır.
2. `press_tr` fiyat başlangıç alanlarını kurar.
3. `press_tr` eksik planları kapalı olarak ekler.
4. `press_tr` Press ayarındaki deneme planını `press-tr-trial` yapar.
5. Sınırı boş olan her plan için bir uyarı yazılır.

Güncelleme var olan plan kaydını değiştirmez. Fiyat yalnız yeni plan kaydıyla değişir.

## Plan sınırları

Proje sahibi sınırları 24 Kasım 2026 Salı günü verdi.

| Plan | Dosya alanı | Veritabanı | Press'e yazılan değer |
| --- | --- | --- | --- |
| Başlangıç | 5 GB | 5 GB | 5120 MiB |
| Büyüme | 10 GB | 10 GB | 10240 MiB |
| Kurumsal | 20 GB | 20 GB | 20480 MiB |
| Deneme | 1 GB | 1 GB | 1024 MiB |

Press bu iki alanı MiB birimiyle saklar. Alanlar `max_storage_usage` ve `max_database_usage` adını taşır. Birim Press'in `site_plan.json` dosyasında yazılıdır. Bu dosya Press `7a4384d5` sürümündedir. 1 GB 1024 MiB sayılır.

İşlem süresi alanı `cpu_time_per_day` adını taşır. Bu alan boş kalır. DevOps sorumlusu onaylayınca alan yazılır.

Bu yüzden her plan güncellemede "missing limits: cpu_time_per_day" uyarısı verir. Uyarı üç alanı sayar: `max_database_usage`, `max_storage_usage` ve `cpu_time_per_day`.

Press'te bir kural daha vardır. Press boyut sınırlarını siteye yalnız `cpu_time_per_day` sıfırdan büyükse gönderir. Bu kural Press'in `get_plan_config` işlevindedir. Yani işlem süresi yazılana kadar boyut sınırları sitede uygulanmaz.

### Yedek takvimi

Takvim `plans.py` dosyasındaki `BACKUP_SCHEDULE` değişkenindedir. Bütün planlar aynı takvimi kullanır.

| Yedek türü | Ne zaman alınır | Kaç yedek saklanır |
| --- | --- | --- |
| Anlık | İstenince | Son 1 yedek |
| Günlük | Her gün | Son 1 yedek |
| Haftada iki | Çarşamba ve cumartesi | Son 2 yedek |
| İki haftada bir | İki haftada bir | Son 1 yedek |
| Aylık | Her ay | Son 1 yedek |
| Üç ayda bir | Üç ayda bir | Son 1 yedek |
| Altı ayda bir | Altı ayda bir | Son 1 yedek |
| Yıllık | Her yıl | Son 1 yedek |

Bu dal takvimi yalnız veri olarak tutar. Yedeği alan ve kopyalayan iş G-5'tedir. Bu dal G-5 dosyalarına dokunmadı.

### Roller ve uygulamalar

Her planda dört rol vardır. Rollerin sayı sınırı yoktur. Rol adları `plans.py` dosyasındaki `TENANT_ROLES` değişkenindedir.

| Rol | Kodda kullanılan ad |
| --- | --- |
| Kiracı yöneticisi | `Tenant Admin` |
| Kiracı yöneticisi yardımcısı | `Tenant Admin Assistant` |
| Bayi yöneticisi | `Reseller Admin` |
| Bayi yöneticisi yardımcısı | `Reseller Admin Assistant` |

Bu roller henüz Frappe rol kaydı değildir. Rolleri G-62 tanımlar.

Uygulama sayısında sınır yoktur. Özel uygulama yalnız Kurumsal planda olur. Bu kural Press'in `private_benches` alanına yazılır. Kurumsal planda alan 1 olur. Diğer planlarda alan 0 olur.

Diğer planlarda özel uygulama kurmayı engelleyen bir denetim bu dalda yoktur. Bu engel için ayrı bir iş gerekir.

Planlar kapalı eklenir. Yönetici planı yönetim ekranında açar.

## Türk lirası kuru

Proje sahibi 24 Kasım 2026 Salı günü karar verdi. Türk lirası fiyatı dolar kurundan hesaplanır. Kod `press_tr/exchange_rates.py` dosyasındadır.

### Kaynaklar

1. Ana kaynak TCMB'dir. Adres `https://www.tcmb.gov.tr/kurlar/today.xml` şeklindedir. Sistem dolar satırındaki "döviz satış" değerini kullanır. Bu değer `ForexSelling` alanıdır.
2. TCMB yanıt vermezse sistem ECB'yi dener. Adres `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` şeklindedir. ECB kuru avro üzerinden verir. Sistem lira değerini dolar değerine böler.
3. Google kullanılmaz.

ECB değeri bir satış kuru değildir. ECB değeri bir referans kurdur. Bu yüzden ECB yalnız yedek kaynaktır.

### Kurallar

- Frappe'nin kendi zamanlayıcısı kuru günde bir kez çeker. Bu Mac'te cron ya da launchd kurulmadı.
- Zamanlayıcı satırı `hooks.py` dosyasındadır: `scheduler_events = {"daily": ["press_tr.exchange_rates.update_rate"]}`. Bu satır dalın son commit'indedir.
- Depodaki `ai-readiness` kapısı her `scheduler_events` satırını reddeder. Kural `backend/dev/ai_readiness/gate.py` dosyasındadır. Satırın kalması için bu kurala onaylı bir istisna gerekir. İstisna verilmezse son commit çıkarılır. O durumda yönetici kuru `bench execute` komutuyla çeker.
- TCMB hafta sonu ve tatilde kur yayımlamaz. O günlerde TCMB dosyası son bülteni verir. Sistem o bültenin tarihini kullanır ve kaydı ikinci kez yazmaz.
- İki kaynak da yanıt vermezse son bilinen kur kullanılır. Sistem hata kaydı yazar. Sistem "System Manager" rolündeki kullanıcılara e-posta da gönderir.
- Kur 3 günden eskiyse `public_plans` yanıtında `rate_warning` alanı dolar. Kur hiç yoksa da bu alan dolar.
- Aynı günde iki kaynak varsa TCMB değeri seçilir.
- Türk lirası fiyatı Commercial Rounding kuralıyla iki basamağa yuvarlanır. Bu kuralda yarım değer sıfırdan uzağa yuvarlanır. Örneğin 12,345 değeri 12,35 olur.
- Kullanılan her kur `PTR Exchange Rate` kaydına yazılır. Kayıtta tarih, kaynak ve değer vardır. Kaydı yalnız "System Manager" rolü okur. Kayıt AI yazmasına kapalıdır.

### Fatura kuru

Fatura taslaktan çıkınca sistem kuru faturaya yazar. Kur o günün en yeni kurudur. Alanlar şunlardır:

- `try_exchange_rate`
- `try_exchange_rate_date`
- `try_exchange_rate_source`
- `try_total`

Kur yazıldıktan sonra değişmez. Biri kuru değiştirmeye çalışırsa kayıt reddedilir. Lira toplamı faturanın dolar toplamından ve bu sabit kurdan hesaplanır.

Hiç kur yoksa fatura engellenmez. Sistem hata kaydı yazar. Fatura kursuz kalır.

### Güvenlik

- Sistem yalnız iki sabit adrese istek gönderir. Adresler ayardan değiştirilemez. Adresler `SOURCE_URLS` değişkenindedir.
- Bağlantı için 5 saniye, okuma için 10 saniye zaman aşımı vardır. İndirme toplam 20 saniyeyi geçerse durur.
- Yanıt en çok 256 KB olabilir.
- Sistem yönlendirmeyi izlemez.
- Sistem XML metninde `DOCTYPE` ya da `ENTITY` görürse yanıtı reddeder.
- Sistem XML'i Python'un `expat` ayrıştırıcısıyla okur. Ayrıştırıcı `DOCTYPE` ya da entity bildirimi görünce durur. Dış entity çözümü de kapalıdır. Bu yöntem defusedxml paketinin yöntemiyle aynıdır.
- Kod `xml.etree` modülünü kullanmaz. Bu yüzden Bandit yeni bulgu vermez.
- Yalnız UTF-8, ISO-8859-9 ve Windows-1254 kodlaması kabul edilir.

### Açık kalan işler

- `public_plans` işlevi henüz bir ekrana bağlı değildir. Bu yüzden uyarı yalnız veride vardır. Panelde gösterim için ayrı bir iş gerekir.
- Gerçek TCMB ve ECB adresi testlerde çağrılmadı. Testler örnek dosya kullanır. Gerçek çağrıyı orkestratör gerçek arka uç denemesinde yaptırır.

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

Bu komutu otomatik çalıştırmak zamanlanmış iş ister. Zamanlanmış iş için insan kararı gerekir. Kur çekme işi bu kuralın dışındadır. Proje sahibi kurun günde bir kez Frappe zamanlayıcısıyla çekilmesine karar verdi.

## Ayrı deneme sitesinde yapılacaklar

1. Dalı ayrı bir Press deneme sitesine kurun.
2. `bench --site <test-site> migrate` komutunu çalıştırın.
3. Dört planın kapalı eklendiğini doğrulayın.
4. Press ayarında deneme planının `press-tr-trial` olduğunu doğrulayın.
5. Dört sınır uyarısının çıktıda göründüğünü doğrulayın. Uyarıda yalnız `cpu_time_per_day` yazmalıdır.
6. Fiyat değişikliği komutunu deneme planı dışında bir planla çalıştırın.
7. Bildirimin ve e-postanın oluştuğunu doğrulayın.
8. `bench --site <test-site> execute press_tr.exchange_rates.update_rate` komutunu bir kez çalıştırın.
9. `PTR Exchange Rate` kaydının TCMB kaynağıyla oluştuğunu doğrulayın.
10. Bir faturayı taslaktan çıkarın. Faturada kur alanlarının dolduğunu doğrulayın.

Canlı sunucuda ve çalışan 7400 ortamında veri güncellemesi yapılmadı.
