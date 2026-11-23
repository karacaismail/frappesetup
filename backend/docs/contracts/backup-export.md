# G-37 yerel yedek sözleşmesi

Bu sözleşme müşterinin kendi yedeğini indirmesini tanımlar.
Araç elle çalışır. Yeni sunucu ucu açmaz.
Panel bağlantısı ve sunucu denemeleri devir işidir.

## Politika

RPO, kaybedilebilecek en uzun veri aralığıdır.
Yedek aralığı, yeniden deneme payı ve tamamlanma süresi birlikte değerlendirilir.
Toplam en fazla 24 saat olur.
Son başarılı dış kopyanın veri zamanı da denetlenir.
Bu zaman gelecekte olamaz. Veri yaşı en fazla 24 saat olur.
Başarısız veya henüz dışarı kopyalanmamış yedek kabul edilmez.
Plan tek başına çalışan yedek düzeninin kanıtı değildir.

Arşivlenen sitenin yedeği en az 6 takvim ayı saklanır.
Süre arşiv anında başlar. Son ayın günü yoksa son gün kullanılır.
Örneğin 31 Ağustos arşivi, sonraki yılın Şubat ayı sonunda dolar.
Denetim aracı yedek silmez. Saklama kilidi veya hukuki bekletme silmeyi ayrıca engeller.

## İndirme

Müşteri kendi Press API kimliğini kullanır.
API, programların sunucuya istek gönderdiği arayüzdür.
Kimlik dosyası `key:secret` biçimindedir.
Şifre çözme anahtarı başka dosyada bulunur.
Bu anahtar her site için ayrı olur.
Ortak bench anahtarı müşteriye verilmez.
İki dosya da yalnız sahibinin okuyabileceği izinle tutulur.
Araç sembolik bağlantıları ve başkasının sahip olduğu dosyaları reddeder.

Araç `press.api.site.get_backup_link` işlevini çağırır.
Her istekte `name`, `backup` ve `file` alanlarını gönderir.
Press müşterinin site iznini denetler.
Araç seçilen kaydı `press.api.site.backups` yanıtından bulur.
Kayıt başarılı, dosyalı ve dış depoya kopyalanmış olmalıdır.
Her indirilen parçanın boyutu kayıtla eşleşmelidir.
Boş bağlantı veya eksik parça hata sayılır.
Araç `database`, `public` ve `private` parçalarını indirir.
Anahtar taşıyabilen `config` parçasını indirmez.
Bu nedenle çıktı tek başına tam geri yükleme kanıtı değildir.
Gerekli site ayarları ve anahtarlar ayrı güvenli kanaldan aktarılır.

Press ve depolama adresleri HTTPS kullanır.
HTTPS, ağ bağlantısını şifreler.
Depolama adresi önceden izin verilen adreslerle eşleşir.
Araç yönlendirme izlemez. Press kimliği depolama isteğine eklenmez.
Dosya başına boyut sınırı ve her ağ isteğinde bekleme sınırı vardır.
İmzalı bağlantılar, kimlikler ve anahtarlar çıktıya veya günlüğe yazılmaz.

GnuPG, şifreli dosyaları açan programdır.
Araç her parçayı GnuPG ile doğrular.
Anahtar işlem argümanına veya ortam değişkenine yazılmaz.
Açılmış veri diske yazılmaz. GnuPG veriyi boş çıktı aygıtına gönderir.
Şifre çözme ve bütünlük kontrolü birlikte geçmelidir.
Dosya adı veya şifreleme ayarı tek başına yeterli değildir.
Şifresiz gzip ve tar dosyaları reddedilir.
Açılan arşivin yapısı tam geri yükleme denemesinde sınanır.

Üç parça geçince araç şifreli dosyaları teslim eder.
Çıktı klasörü yalnız müşterinin erişebileceği izinle oluşturulur.
Çıktı diski sabit dosya bağlantısını desteklemelidir.
Bu bağlantı, aynı dosyaya ikinci bir ad verir.
Bu araç exFAT ve FAT diskleri desteklemez.
Mevcut klasörün üzerine yazılmaz. Hatalı indirme çıktısı temizlenir.
Başarı çıktısı yalnız dosya adını, boyutunu ve SHA-256 özetini içerir.
SHA-256 özeti, sonradan dosya değişikliğini karşılaştırmaya yarar.
Özet, yedeğin sunucudaki özgünlüğünü tek başına kanıtlamaz.

## Sınırlar

Yerel testler sahte Press ve depolama yanıtlarını kullanır.
Gerçek Press yetkisi ve müşteri paneli ayrıca sınanmalıdır.
Sunucudaki şifreleme, dış kopya ve saklama ayarları ayrıca doğrulanmalıdır.
G-37, bu sunucu kanıtları olmadan tamamen kapanmaz.
GnuPG doğrulama süresi varsayılan olarak 300 saniyedir.
Büyük yedeklerde müşteri `--verification-timeout-seconds` ile sınırı artırabilir.
Süre dolarsa dosyalar teslim edilmez.
Bu sürüm, GnuPG'nin `GOODMDC` bütünlük sonucunu gerektirir.
Farklı şifreleme biçimleri sunucu devrinde ayrıca denenmelidir.
