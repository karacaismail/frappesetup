# G-40 ve G-41 devir notu

Bu not iki gereksinimin açık kalan maddelerini sayar. Kod ve testler bu daldadır.

## G-40: geliştirme araçları üretimde kapalı

Kiracı uygulaması iki tür isteği reddeder:

- Geliştirici kipi kapalıysa sistem konsolu isteği reddedilir.
- Test izni kapalıysa test modülüne giden istek reddedilir.

Ret kodu `platform_core/development_access.py` dosyasındadır. Kod `before_request` listesinin başında çalışır. Frappe 16.56.0 sürümünde `make_form_dict` adımı bu listeden önce koşar. Bu yüzden `cmd` alanı ret sırasında doludur.

Dağıtım denetimi üç ayarı denetler: `developer_mode`, `server_script_enabled` ve `allow_tests`. Ayar açıksa dağıtım durur. `server_script_enabled` ayarı ortak bench ayarında da denetlenir.

### Açık maddeler

1. Ayrı bench koşulu 24 Kasım 2026 Salı günü karara bağlandı. Kural [`docs/decisions/0020-dedicated-bench.md`](../decisions/0020-dedicated-bench.md) dosyasındadır. Ayrı bench iki koşulda verilir. Kiracı Kurumsal plandadır ya da özel uygulaması vardır. Fiyat bu kararda yoktur.
2. `platform_core/tests/test_development_access.py` ve `test_schema_source.py` gerçek Frappe ister. Bu testler `bin/test` ile ayrı test sitesinde koşar. Testler bu dalda koşulmadı.
3. API yüzeyinin izin listesiyle daraltılması G-143 işidir. G-40 bu işi yapmaz.

## G-41: Türkiye başlangıç ayarları

Kiracı Türkiye ayarlarıyla açılır. Ayarları `platform_core/config/turkey_setup.py` yazar. İki kanca bu kodu çağırır: `setup_wizard_complete` ve `after_migrate`. Kod yalnız farklı olan değeri yazar. İkinci koşu hiçbir şeyi değiştirmez.

Yazılan değerler şunlardır:

- System Settings içinde on değer yazılır. Örneğin dil `tr`, saat dilimi `Europe/Istanbul` ve para birimi `TRY` olur.
- ERPNext kuruluysa Global Defaults içinde ülke ve para birimi yazılır. TRY para birimi etkinleşir.
- Kod `default_company` değerine dokunmaz. Bu değeri kurulum sihirbazı yazar.

### Kararlar

Üç madde 24 Kasım 2026 Salı günü karara bağlandı. Artık açık madde yoktur.

1. `rounding_method` değeri "Commercial Rounding" oldu. Yarım değer yukarı yuvarlanır. Değer `turkey_setup.py` içindeki `SYSTEM_SETTINGS` sözlüğündedir.
2. Marka adı `identity_brand_name` ayarından gelir. Kod bu değeri System Settings içindeki `app_name` alanına yazar. Ayar boşsa kod `app_name` alanına dokunmaz.
3. Accounts, Selling ve Buying ayarları ERPNext varsayılanında kalır. Kod bu ayarlara yazmaz. Türkiye'ye özel değer ayrı bir gereksinimle gelir.

### Gerçek sitede deneme

`platform_core/tests/test_turkey_setup.py` gerçek site testidir. Test sihirbazın yazdığı `float_precision=3` değerini düzeltir. Sonra ikinci koşuda System Settings kaydının `modified` değerinin değişmediğini denetler. Bu test bu dalda koşulmadı.

G-42 yerel kabul testi bu değerleri yeni kiracıda da denetleyecek.

Dikkat edilecek bir nokta var. `after_migrate` test sitesinde de dili `tr` yapar. İngilizce hata metni bekleyen başka bir test bu yüzden düşebilir. Gerçek arka uç denemesinde bunu izleyin.
