# G-37 sunucu devri

Teknik sorumlu DevOps sorumlusudur.
Bu not yerel kod ile sunucuda yapılacak işi ayırır.
Bu görev canlı sunucuya ve canlı veriye dokunmaz.
Bu görev cron, zamanlayıcı veya launchd kurmaz.

## Yerel teslim

[İndirme sözleşmesi](../contracts/backup-export.md) yerel aracın sınırlarını açıklar.
Araç müşterinin Press kimliğiyle üç yedek parçasını indirir.
Şifre çözme kontrolü geçmeyen parçaları teslim etmez.
Anahtar içerebilen site ayarı dosyası indirmeye eklenmez.
Panel bağlantısı bu yerel teslimin dışında kalır.

Press kaynağı `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` commit'inde incelendi.
İndirme işlevi `press.api.site.get_backup_link` adını taşır.
`press.api.site.get_backup_links` başka siteden yedek alır.
Bu iki işlev aynı amaçla kullanılmaz.

Yerel Frappe kaynağında `frappe/utils/backups.py:228` şifreleme işini başlatır.
Şifreleme hatası, aynı dosyanın 251. satırında bildirilir.
Bu durumda dosya şifresiz kalabilir.
Bu yüzden dosya adı şifreleme kanıtı sayılmaz.

## Ön koşullar

1. DevOps sorumlusu deneme ortamını ve uydurma veriyi hazırlar.
2. DevOps sorumlusu Press sürümünü ve izin davranışını kaydeder.
3. DevOps sorumlusu G-49 şifreleme ayarını doğrular.
4. DevOps sorumlusu G-5 dış kopyasının tamamlandığını doğrular.
5. DevOps sorumlusu anahtarların ayrı güvenli yerde bulunduğunu doğrular.
6. DevOps sorumlusu deneme ortamına GnuPG erişimini sağlar.

DevOps sorumlusu her sitenin ayrı `backup_encryption_key` kullandığını doğrular.
Ortak `common_site_config.json` dosyasında bu anahtar bulunmamalıdır.
DevOps sorumlusu anahtarı yalnız doğrulanmış site sahibine verir.
DevOps sorumlusu güvenli aktarım kanalını sunucu kurulumunda belirler.
Kanal seçilip denenmeden müşteriye indirme açılmaz.
Anahtar e-posta, görev yorumu veya indirme bağlantısıyla birlikte gönderilmez.

G-49, yedek şifrelemesini ve anahtar yönetimini kapsar.
G-5, başka konumdaki yedek kopyasını kapsar.
Press veritabanı yedeği müşteri yedeğinden ayrı tutulur.
Anahtarlar, parolalar ve imzalı indirme adresleri rapora yazılmaz.

## Veri kaybı sınırı

DevOps sorumlusu yedek aralığını ve tamamlanma süresini ölçer.
RPO, kaybedilebilecek en uzun veri aralığıdır.
Yedek aralığına yeniden deneme ve tamamlanma payı eklenir.
Toplam en fazla 24 saat olmalıdır.
Son başarılı dış kopyanın veri zamanı ayrıca denetlenir.
Kopyanın bitiş zamanı, yedeğin veri zamanı yerine kullanılmaz.
Başarısız bir yedek son başarılı zamanı ilerletmez.

Yerel denetim komutu şöyledir:

```sh
python3.14 -B backend/deploy/backup_export.py policy --evidence /secure/backup-evidence.json
```

Örnek kanıtın alanları şöyledir:

```json
{
  "interval_hours": 20,
  "completion_hours": 2,
  "retry_hours": 2,
  "data_time": "2026-11-23T00:00:00+00:00",
  "backup_success": true,
  "offsite_complete": true
}
```

Bu örnek gerçek başarı kaydı değildir.
DevOps sorumlusu gerçek kanıtı sunucudan üretir.
`backup_interval`, Press'te alt aralık ayarıdır.
Bu ayar tek başına günlük başarıyı garanti etmez.
Eksik yedek uyarısı ve gerçek tamamlanma kaydı ayrıca sınanır.
Zamanlı çalıştırma kurulumu ayrı yetkili sunucu işidir.
Bu not zamanlı iş kurulumu için onay değildir.

## Müşterinin yedeğini indirmesi

1. DevOps sorumlusu farklı takımlarda iki deneme müşterisi hazırlar.
2. DevOps sorumlusu dosyaları içeren şifreli dış yedek oluşturur.
3. İlk müşteri kendi yedeğini yerel araçla indirir.
4. İkinci müşteri ilk müşterinin yedeğini indirmeyi dener.
5. DevOps sorumlusu ikinci müşterinin reddedildiğini doğrular.
6. DevOps sorumlusu süresi dolmuş kimliğin reddedildiğini doğrular.
7. DevOps sorumlusu yanlış anahtarın çıktıyı engellediğini doğrular.
8. DevOps sorumlusu eksik yedek parçasının çıktıyı engellediğini doğrular.

Yabancı yedek denemesi doğrudan Press isteğini de kapsar.
İkinci müşteri `name` alanına kendi sitesini yazar.
İkinci müşteri `backup` alanına ilk müşterinin yedek kimliğini yazar.
DevOps sorumlusu bu birleşimin reddedildiğini doğrular.
İncelenen Press işlevi sorguda hem siteyi hem yedek kimliğini kullanır.
Sunucu denemesi yine de yapılmalıdır.

Müşteri indirme komutunu kendi güvenilir bilgisayarında çalıştırır:

```sh
python3.14 -B backend/deploy/backup_export.py download \
  --press-url https://press.example.test \
  --storage-origin https://storage.example.test \
  --credential-file /secure/press-credential \
  --passphrase-file /secure/backup-passphrase \
  --site tenant.example.test --backup backup-id \
  --output /secure/exported-backup
```

Adresler ve kimlikler örnektir. Gizli değerler komuta yazılmaz.
Kimlik ve anahtar dosyalarının izni `0600` olur.
Çıktı yolu henüz var olmayan bir klasör olmalıdır.
Varsayılan dosya sınırı 20 GiB olur.
GiB, 1.073.741.824 bayttır.
Gerekirse `--max-bytes` dosya başına açık bir sınır belirler.
GnuPG kontrolü varsayılan olarak 300 saniyede durur.
Büyük dosyalarda `--verification-timeout-seconds` ile uygun sınır verilir.
DevOps sorumlusu gerçek dosya boyutuyla bu süreyi doğrular.
Müşteri çıktıyı APFS veya ext4 gibi desteklenen diske yazar.
Bu araç exFAT ve FAT diskleri desteklemez.
DevOps sorumlusu panel bağlantısını bu izin kurallarıyla bütünleştirir.
Panel tamamlanmadan panelden indirme doğrulandı denmez.

## Arşivden sonra saklama

Yedekler, arşiv anından başlayarak en az 6 takvim ayı saklanır.
DevOps sorumlusu Press temizleme ayarlarını bu kurala göre denetler.
Depolama yaşam döngüsü de aynı alt sınırı korur.
Ay sonunda karşılık gelen gün yoksa hedef ayın son günü kullanılır.
Saklama kilidi veya hukuki bekletme varsa otomatik silme yapılmaz.
Bu yerel araç hiçbir yedeği silmez.

DevOps sorumlusu süreyi şu komutla hesaplar:

```sh
python3.14 -B backend/deploy/backup_export.py retention \
  --archived-at 2026-08-31T09:30:00+00:00
```

Kabul için süre dolmadan yedeğin indirilebildiği gösterilir.
Ay sonu ve artık yıl örnekleri de sınanır.
Süre dolması tek başına silme yetkisi vermez.

## Aylık geri yükleme raporu

DevOps sorumlusu her ay izole ortamda geri yükleme denemesi yapar.
İzole ortamın canlı hizmetlerle bağlantısı bulunmaz.
E-posta, ödeme ve dış bildirim gönderimleri kapalı olur.
Rapor şu bilgileri içerir:

- Kullanılan yedeğin kimliği ve veri zamanı.
- Dış kopyanın tamamlanma zamanı.
- Ölçülen veri kaybı aralığı.
- Şifre çözme ve bütünlük sonucu.
- Veritabanı, genel dosyalar ve özel dosyaların sonucu.
- Uygulama açılışı ve temel kayıt kontrolleri.
- Başarı, başarısızlık ve düzeltme sahibi.

Bu rapor otomatik üretilecekse ayrı kurulum onayı gerekir.
Bu görev zamanlı rapor işi kurmaz.

## Üç aylık tam dönüş denemesi

DevOps sorumlusu her üç ayda bir yeni bench hazırlar.
Bench, Frappe uygulamalarının çalıştığı kurulum klasörüdür.
DevOps sorumlusu şifreli müşteri yedeğini bu yeni kurulumda açar.
Veritabanını, genel dosyaları ve özel dosyaları birlikte yükler.
Gerekli anahtarları ayrı güvenli kanaldan sağlar.
Uygulama sürümlerini ve dosya özetlerini rapora ekler.
Frappe'nin ürettiği yedek biçimini müşteri GnuPG sürümüyle dener.
Bu araç `GOODMDC` bütünlük sonucunu gerektirir.
Farklı şifreleme biçimi bu sonucu vermiyorsa araç yedeği reddeder.
Yeni biçim desteği, kaynak doğrulaması ve ayrı regresyon testi gerektirir.
Giriş, temel kayıt okuma ve dosya indirme akışlarını sınar.
Deneme sonrasında yalnız deneme kaynaklarını temizler.

## Kabul ve kanıt

DevOps sorumlusu sunucu sonuçlarını ayrı kanıt dosyasıyla teslim eder.
Yerel başarı, sunucunun başarılı çalıştığı anlamına gelmez.
G-37 kapanışı aylık raporu ve üç aylık tam dönüşü gerektirir.
Müşteri izin sınaması ve 6 aylık saklama kanıtı da gerekir.
Bu kanıtlar olmadan gereksinim açık kalır.

Gerçek okurla denenmedi.
