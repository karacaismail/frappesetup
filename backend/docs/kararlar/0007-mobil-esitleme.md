# Telefon eşitlemesi

Bu not tasarım kararını anlatır. Canlı uç testi ikinci kontrol noktasında yapılır.

## Kapsam ve sahiplik

`mobil` modülü telefonun kurulumunu ve eşitleme kayıtlarını yönetir.
Telefon yalnız açıkça tanımlanmış eşitleme uçlarını çağırır.
Uçların tam adresleri sürümlü OpenAPI dosyasında yer alır.
İlk sürüm `/api/method/platform_core.api.mobile.v1_*` adlarını kullanır (AU-1).

- `v1_register` bir telefon kurulumunu hesaba bağlar.
- `v1_revoke` bir kurulumu veya hesaba bağlı bütün kurulumları kapatır.
- `v1_push` telefondaki işlemleri sırayla alır.
- `v1_pull` ilk kopyayı veya son eşitlemeden sonraki değişiklikleri verir.
- `v1_cleanup` süreyi aşan kaldırma işaretlerini yetkili görevli için temizler.

Kimlik modülünün `auth_hooks` kancası erişim belirtecini doğrular.
Mobil uçlar, kancanın bu istek için doğruladığı hesap ve site bağını kullanır.
Bu uçlar, kimlik sunucusunun doğruladığı sonucu arar.
Yalnız Frappe kullanıcı adının dolu olması yeterli olmaz.
Kanca izinli adres listesini tam adresle eşler.
Sistem `cmd` alanını, boş bile olsa, gövdede ve adres parametrelerinde reddeder.
Sistem etkin oturum çereziyle belirteç birlikte gelirse isteği reddeder.
Misafir çerezi etkin oturum sayılmaz.
Tarayıcının ön denetim isteği belirteç istemez.
Site yalnız izinli kaynak adreslerini açar.
Sistem mevcut sahte istek korumasını korur.

Sistem kayıt iznini Frappe üzerinden denetler.
Canlı uçlar için uygulama iskeleti ve kimlik kancası gerekir.
Erişim kuralı motoru bağlanınca motorun ret yolu da HTTP üzerinden sınanır.
Erişim kuralı motoru mevcut Frappe izin kancalarından çalışır.
Mobil modülü bu motoru doğrudan çağırmaz.
Modül sınırı denetimi başka modüllere doğrudan yazmayı yakalar.
Mobil uçlar genel kayıt uçlarını veya telefonun seçtiği kayıt türlerini açmaz.

## Açılacak komutlar

Sunucu tek bir komut izin listesi tutar (AU-2).
Liste bir komuta izinli kayıt türünü, alanları ve varsa ekleri bağlar.
Oluşturma, güncelleme ve silme ayrı komutlardır.
Her komut ayrıca kullanıcının kayıt ve alan izinlerini denetler.
Telefonun ekran tanımı ve veri alanları izin listesini genişletemez.

Başlangıçta gerçek iş kaydı listesi boş kalır.
İlk sürüm hiçbir iş alanını ve hiçbir eki telefona açmaz.
Bir iş kaydı açılırsa sahibi kayıt türü için önce tam plan yazar (AU-18).
Plan bağlı kayıtları, izinleri ve geçerli durum değişimlerini belirtir.
Plan ayrıca alanları, ekleri, çevrimdışı okuma süresini ve taslak ömrünü belirtir.
Testler sahte kayıt türüyle sözleşme davranışını sınar.
Sahte komutlar çalışan siteye yüklenmez.

## Sunucudaki kayıtlar

- Kurulum kaydı, cihaz kimliğini siteye, hesaba ve izin kapsamına bağlar.
- İşlem kaydı, işlem kimliğiyle isteğin özetini ve ilk sonucu saklar.
- Değişiklik kaydı, kayıt kimliğini ve sunucunun verdiği sıra numarasını saklar.
- Kaldırma işareti, telefonun yerel kopyadan çıkaracağı kayıt kimliğini taşır.
- Görünürlük kaydı, kurulumun daha önce alabildiği kayıtların kimliklerini tutar.
- Sıra kaydı, site için son kesinleşen değişiklik numarasını tutar.

Bu kayıtlar mobil modülüne aittir.
Kurulum aktiftir veya iptal edilmiştir.
İptal edilen kurulum eski kimliğiyle yeniden açılmaz.
Her cihaz isteği, etkin kurulumun hesap ve kapsam bağını denetler.
Sunucu hesap ve kapsam bilgisini doğrulanan kimlikten alır.
Tek kurulum ya da bütün kurulumlar aynı hesap bağı içinde iptal edilir.

## Yazma ve yeniden gönderme

Telefon ilk gönderimden önce bir işlem kimliği üretir.
Sunucu kimliği UUID olarak doğrular.
UUID, ayraçlı ve küçük harfli biçimde yazılan tekil kimliktir.
Telefon yeni iş kaydı için ayrı bir UUID üretir.
Sunucu kayıt kimliğinin site, hesap ve izinli tür kapsamını denetler.
Sunucunun adlandırma kuralı kayıt adını ve iş numarasını belirler.
Telefonun kayıt UUID'si ayrı bir tekil alanda kalır (AU-9).

Veri tabanı site, hesap ve işlem kimliği birleşimini tekil tutar (AU-7).
Sunucu normalleştirilmiş isteğin SHA-256 özetini alır.
Özet, isteğin aynı içeriği taşıyıp taşımadığını gösterir.
Özet komut, kayıt kimliği, sürüm şartı ve alan değerlerini kapsar.
Telefonun tekrar gönderme zamanı bu özeti değiştirmez.
Veri tabanı tekillik kuralı kurulum sırasında eklenir.
İstek sırasında tablo yapısı değişmez.

Sunucu aynı kimlikle gelen iki isteği veri tabanında sıraya alır.
İş etkisi, istek özeti ve sonuç aynı veri tabanı işleminde yazılır.
İlk yazma geri alınırsa yeniden gönderim işlemi baştan çalıştırabilir.
İçerik aynıysa sunucu aynı iş sonucunu döner.
İçerik farklıysa sunucu kimlik çakışması döner.
Sunucu, izin kaybından sonra saklı sonucu kullanarak kayıt içeriği göstermez.
Sunucu tekrar oynatmada da güncel hesap ve kayıt izinlerini denetler.

Güncelleme ve silme, telefonun okuduğu sürümü gerektirir (AU-8).
Sunucu kayıt satırını kilitler.
Sunucu izin ve sürüm denetimini kilitli yazma işlemi içinde yapar.
Sürüm eşleşmezse sunucu çakışma döner.
Çakışma, güncel kaydın yalnız okunmasına izin verilen alanlarını taşır.
Silme işlemi de bu karşılaştırmayı açıkça yapar.
Sistem kayıt sürümünü imleç sırası olarak kullanmaz.
Telefon saatine göre karar verilmez.

## İlk kopya ve değişiklikler

İmleç, telefonun nerede kaldığını gösteren sunucu kodudur.
Telefon imleci açmadan saklar ve sonraki istekte aynen gönderir.
Sunucu imleci imzalar.
İmza, kullanıcının imleci değiştirmesini engeller.
İmleç biçimi siteye, hesaba, kuruluma, kapsama ve sözleşme sürümüne bağlıdır.
Sunucu başka bir bağ için üretilen veya süresi dolan imleci reddeder.
Telefon bu durumda ilk kopyayı yeniden alır.
Telefon bu sırada gönderilmemiş işleri korur.

İlk kopya başlarken son kesinleşen sıra numarası alınır.
Sunucu kopyanın sayfalarını sabit sırada verir.
Her sayfada kayıtların güncel okuma izni denetlenir.
İlk kopyadan sonra değişiklikler başlangıçtaki sıra numarasından okunur.
Yeni kayıt ilk kopya sınırını aşarsa sonraki değişiklik sayfasında gelir.

İzinli kaydı değiştiren işlem tek site sıra satırını kilitler.
İşlem bu kilidi kesinleşene kadar tutar.
Sistem sıra numarasını değişiklik kaydıyla aynı işlemde yazar (AU-10).
Sonraki yazma ilk yazma kesinleşene kadar yeni sıra numarası alamaz.
Örneğin 8 numaralı kayıt beklerse 9 numaralı kayıt önce kesinleşemez.
Telefon bu yüzden geç kesinleşen 8 numaralı kaydı atlamaz.
Geri alınan yazma kayıt ve sıra ilerlemesini birlikte geri alır.
Aynı kayıt türünü değiştiren bütün onaylı yollar bu sıraya katılır.
Bu şart sağlanana kadar tür eşitlemeye açılmaz.

## Silme, ad değişikliği ve izin kaybı

Sistem silmede ve ad değişikliğinde eski kimlik için kaldırma işareti yazar.
Telefon işareti alınca eski kaydı yerel kopyadan çıkarır.
Yeni kimlik, güncel izin varsa yeni kayıt olarak gelir.
Yetki kaybında sistem önceki görünürlük kaydını kullanır.
Sunucu gönderilen kayıt kimliklerini sayfayla aynı veri tabanı işleminde saklar.
Telefon en son uyguladığı sayfanın imlecini geri gönderir.
Sunucu silme işaretini geçerli bir imleç yeniden isteyebildiği sürece korur.
Sistem, telefonun daha önce alabildiği kayıtlar için güncel izni yeniden denetler.
Bu denetim, iş kaydı değişmemiş olsa bile çalışır.
İşaret yalnız eski kimliği ve kaldırma nedenini taşır (AU-11).
İzin kaybı bildirimi iş kaydının içeriğini taşımaz.
Frappe'nin yönetici kurtarma kayıtları telefona açılmaz.

Sunucu kaldırma işaretlerini 30 gün saklar.
İmleç en çok 7 gün geçerlidir.
Temizlik, geçerli imlecin ihtiyaç duyduğu değişikliği silmez.
Eski imlece dayanan güvenli bir değişiklik listesi kalmazsa ilk kopya istenir.
Yetkili görevli temizliği elle başlatır.
Komut ve HTTP ucu aynı temizlik işlevini kullanır.
Zamanlanmış bir temizlik işi kurulmaz.

## İstek sınırları ve sürümler

- Bir okuma sayfası en çok 100 kayıt taşır.
- Bir yazma grubu en çok 20 işlem taşır.
- Bir JSON istek gövdesi en çok 256 KiB olabilir.
- Sistem hesap başına dakikada 60 istek kabul eder.
- İlk sürüm ek kabul etmez. Ek sınırı 0 bayttır.

Gövde sınırı aşılırsa sunucu `413` döner.
Ters vekil büyük gövdeyi Frappe okumadan önce durdurur.
Sıklık sınırı geçilirse sistem `429` ve `Retry-After` başlığını döner.
Ters vekil, tarayıcının bu başlığı okuyabilmesini sağlar.
Ek daha sonra açılırsa sunucu boyutu, gerçek içeriği ve kayıt iznini denetler.
Ek özel saklanır ve yeniden gönderimde aynı işlem kimliğini kullanır (AU-13).

Telefon sürümleri `X-Mobile-App-Version` ve `X-Mobile-Contract-Version` başlıklarında gönderir.
İlk sözleşme sürümünün değeri `1` olur.
Sunucu geçerli sürüm başlıklarına göre istek sayılarını tutar.
Ölçüm yalnız sürümleri ve sayıyı taşır.
Güvenlik engeli yalnız etkilenen komutu kapatır (AU-16).
Yayımlanan alanın adı, anlamı ve türü korunur.
Uyumu bozan değişiklik yeni uç sürümünde yapılır.
Eski uç proje kararıyla kapanana kadar bekleyen eski işlemleri kabul eder (AU-15).

## Kaynakta doğrulanan Frappe davranışı

Yerel `frappe/erpnext:v16.55.0` imajında Frappe 16.56.0 bulunur.
Sürüm `frappe/__init__.py:58` satırından doğrulandı.

- `frappe/app.py:114–133` önce kimliği, sonra `cmd` alanını denetler.
  API yolu bu denetimlerden sonra çalışır.
- `frappe/app.py:338–351` JSON gövdesini adres parametrelerinden ayrı işler.
  Bu yüzden kanca her iki kaynağı ayrı denetler.
- `frappe/auth.py:638–650,755–757` yerleşik belirteç yollarından sonra kancayı çağırır.
  İlk Frappe oturumu kancanın onayı yerine geçmez.
- `frappe/app.py:214–220` oturumu belirteç kancasından önce açar.
  `frappe/auth.py:86–102` sahte istek denetimini oturum üzerinden yürütür.
- `frappe/model/document.py:498–528` kilit isteğini kayıt okumasına taşır.
  `frappe/database/database.py:531–587` kilitli alan okumasını destekler.
- `frappe/model/document.py:1355–1383` kaydetmede `modified` değerini karşılaştırır.
  `frappe/model/delete_doc.py:159–177` silmede kilidi ve izni denetler.
  Mobil uç, silmede telefonun sürümünü ayrıca karşılaştırır.
- `frappe/model/naming.py:141–175` kaydı sunucuda adlandırır.
  Sunucu düz UUID biçimini denetlese de telefon kapsamını denetlemez.
- `frappe/app.py:156–162,438–448` fırlatılan hatada yazmayı geri alır.
  Normal POST yanıtında veri tabanı işlemini kesinleştirir.
  Uygulama hatayı yakalayıp yanıt üretirse yarım yazmayı açıkça geri alır.
- `frappe/app.py:294–328` izinli tarayıcı kaynaklarını tam adresle eşler.
  Bu kod `Retry-After` başlığını tarayıcıya açmaz.
- `frappe/database/mariadb/database.py:448–463` tekillik kuralını tabloya ekler.
  Bu işlev tabloyu değiştirmeden önce işlemi kesinleştirir.

Kaynak denetimi canlı HTTP testi yerine geçmez.
İkinci kontrol noktası gerçek istekle izin ve ret yollarını sınar.
