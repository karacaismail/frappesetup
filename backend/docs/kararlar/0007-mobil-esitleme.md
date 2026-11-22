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
Kanca, istek sırasında çalışan bir işlevdir.
Mobil uçlar, kancanın bu istek için doğruladığı hesap ve site bağını kullanır.
Bu uçlar, kimlik sunucusunun doğruladığı sonucu arar.
Yalnız Frappe kullanıcı adının dolu olması yeterli olmaz.
Kanca izinli adres listesini tam adresle eşler.
Kanca doğrulamadan sonra `frappe.local.mobile_identity` alanını doldurur.
Bu alan `site`, `account`, `issuer`, `subject`, `scope`, `iat` ve `sid` değerlerini taşır.
`iat`, belirtecin verildiği anı saniye olarak gösterir.
`account`, Frappe kullanıcısıdır. `scope` bu uçlarda `mobile` olur.
Sistem hesap anahtarını sabit veren ve kullanıcı kimliğinden üretir.
E-posta değişse de bu anahtar aynı kalır.
Sunucu bir kurulumu iptal edince iptal anını hesapta saklar.
Sunucu kurulum ve iptal işlemlerini aynı mobil hesap kaydıyla sıraya alır.
İlk mobil hesap kaydı açılırken sunucu kullanıcı satırını kilitler.
Bu denetim, silinmiş hesabın eski okuma bilgisiyle yeniden açılmasını önler.
Sonraki eşitlemeler mobil hesap kaydındaki kilidi kullanır.
Bütün kurulumları iptal eden istek de bu anı saklar.
Yeni kurulum, iptal sınırından sonra verilen belirteci ister.
Sunucu belirtecin verildiği saatte 30 saniye ileriye izin verir.
Bu pay, iki sunucunun saat farkı içindir.
Sunucu iptal sınırına da 30 saniye ekler.
Sınır anında verilen belirteç de reddedilir.
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

### Kod denetimi istisnaları

Semgrep, kodda belirli kalıpları arayan denetim aracıdır.
Semgrep, uçların çağırdığı ortak izin işlevini izleyemez.
Beş uçta yalnız bu denetim için dar istisna vardır.
Gerçek HTTP testleri korunan işlemlere izinsiz erişimi sınar.

İç kayıt türleri genel kayıt uçlarına açılmaz.
Sunucu, işlem iznini denetledikten sonra kendi takip kaydını ekler.
Bu ekleme yalnız mobil modülünün beş iç kayıt türünde çalışır.
Ekleme bitince geçici izin bayrağı eski değerine döner.
Semgrep istisnası yalnız bu ekleme satırını kapsar.
İş kayıtlarında Frappe izinleri uygulanır.

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
Sahte komutlar yalnız ayrı deneme sitesine bağlanır.
Mobil uç, deneme araçlarını yalnız `allow_tests` açıkken okur.
Deneme kancası araçları isteğin sunucu belleğine yerleştirir.
İstek gövdesi ve başlıkları bu araçları doğrudan belirleyemez.
Canlı site bu ayarı kapalı tutar.

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
Telefonun kayıt UUID'si ayrı bir alanda kalır (AU-9).
Sunucu UUID, hesap ve kayıt türünden tekil arama anahtarı üretir.
Kayıt yoksa veya başka hesaba aitse sunucu aynı yanıtı verir.

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
Sunucu tekrar isteğini yalnız etkin kurulumdan ve aynı hesaptan kabul eder.
Sonuç yalnız işlem kimliğini ve işlemin uygulandığı bilgisini taşır.
Sunucu bu yanıtta iş kaydının içeriğini göstermez.
Bir işlem başarısız olursa sunucu gruptaki bütün yazmaları geri alır.

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
Sunucu imleci AES-GCM ile şifreler.
Şifreli imleç sıra numaralarını gizler ve değişikliği algılar.
Eski biçimdeki imleç `410` döner. Telefon yeni bir ilk kopya alır.
İmleç biçimi siteye, hesaba, kuruluma, kapsama ve sözleşme sürümüne bağlıdır.
Sunucu başka bir bağ için üretilen veya süresi dolan imleci reddeder.
Telefon bu durumda ilk kopyayı yeniden alır.
Telefon bu sırada gönderilmemiş işleri korur.

İlk kopya başlarken son kesinleşen sıra numarası alınır.
Sunucu ilk kopyayı değişiklik geçmişinden oluşturmaz.
Sunucu kayıt tablolarını kayıt türü ve UUID sırasına göre sayfalar.
Her sayfada kayıtların güncel okuma izni denetlenir.
İlk kopyadan sonra değişiklikler başlangıçtaki sıra numarasından okunur.
Yeni kayıt ilk kopya sınırını aşarsa sonraki değişiklik sayfasında gelir.

Sunucu sıra numarası üretirken site sıra satırını kilitler.
Salt okuma site sıra satırını kilitlemez.
İşlem bu kilidi kesinleşene kadar tutar.
Sistem sıra numarasını değişiklik kaydıyla aynı işlemde yazar (AU-10).
Sonraki yazma ilk yazma kesinleşene kadar yeni sıra numarası alamaz.
Örneğin 8 numaralı kayıt beklerse 9 numaralı kayıt önce kesinleşemez.
Telefon bu yüzden geç kesinleşen 8 numaralı kaydı atlamaz.
Geri alınan yazma kayıt ve sıra ilerlemesini birlikte geri alır.
MariaDB eski okuma görünümünden yeni bir satır kilidine geçişi reddedebilir.
Sunucu bu hatada işlemi geri alır ve en çok üç kez dener.
Sunucu yeniden denemeden önce kısa ve rastgele bir süre bekler.
Üç deneme başarısız olursa sunucu `503` ve `Retry-After` döner.
Kilit bekleme süresi dolarsa sunucu hemen aynı yanıtı döner.
Bu deneme, veritabanı dışında etkisi olan komutu çalıştırmaz.
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
Sunucu bir denetim bitince yenisini en erken 300 saniye sonra başlatır.
Yarım kalan denetim bir sonraki sayfada sürer.
Kayıt yeniden telefona giderse sunucu görünürlük kaydını günceller.
Sunucu her istekte en çok 100 eski teslimi denetler.
Telefon, denetim sürüyorsa `has_more` değeriyle sonraki sayfayı ister.
Yeni bir okuma izni, kayıt değişmese bile bir değişiklik olayı üretmelidir.
Bu kural, telefonun daha önce hiç almadığı kaydı görmesini sağlar.
Bu olay üretimi sınanmadan kayıt türü eşitlemeye açılmaz.
İşaret yalnız kayıt türü ve eski kayıt kimliğini taşır (AU-11).
İzin kaybı bildirimi iş kaydının içeriğini taşımaz.
Frappe'nin yönetici kurtarma kayıtları telefona açılmaz.

Sunucu, işlem sonuçlarını ve değişiklik olaylarını varsayılan 30 gün saklar.
Site bu süreleri ayrı ayrı değiştirebilir.

- `mobile_operation_retention_days` işlem sonuçlarının süresidir.
- `mobile_upsert_retention_days` yeni ve güncel kayıt olaylarının süresidir.
- `mobile_removal_retention_days` kaldırma işaretlerinin süresidir.

Sunucu etkin kurulumların teslim kayıtlarını saklar.
El ile temizlik, iptal edilen kurulumların teslim kayıtlarını da kaldırır.
Önizleme bu kayıtları ayrı sayar.
Kullanıcı silinince sunucu kurulumları, teslimleri ve hedefli olayları temizler.
Bir yanıt kaybolursa telefon aynı imleçle kaldırma işaretini yeniden alabilir.
İşaretin yeniden alınması eski iş kaydını geri getirmez.
İmleç en çok 7 gün geçerlidir.
Temizlikten sonra sunucu eksik değişiklik içeren eski imleçleri reddeder.
Eski imlece dayanan güvenli bir değişiklik listesi kalmazsa ilk kopya istenir.
Yetkili görevli temizliği elle başlatır.
Görevli komut satırında `bench --site <site> execute platform_core.mobil.store.cleanup` komutunu çalıştırır.
Görevli HTTP üzerinden `v1_cleanup` ucunu çağırır.
HTTP ucu Frappe içindeki `System Manager` rolünü arar.
Komut ve HTTP ucu aynı temizlik işlevini kullanır.
`dry_run: true` kaç kayıt silinebileceğini gösterir. Kayıt silmez.
Zamanlanmış bir temizlik işi kurulmaz.

## İstek sınırları ve sürümler

- Bir okuma sayfası en çok 100 kayıt taşır.
- Bir yazma grubu en çok 20 işlem taşır.
- Bir JSON istek gövdesi en çok 256 KiB olabilir.
- Sistem hesap başına dakikada 60 istek kabul eder.
- Sistem hesap başına en çok 20 etkin kuruluma izin verir.
- İlk sürüm ek kabul etmez. Ek sınırı 0 bayttır.

Gövde sınırı aşılırsa sunucu `413` döner.
Gövde sınırı mobil işlevde de denetlenir.
Frappe, gövdeyi mobil işlevden önce okur.
Ters vekilde mobil adresler için 256 KiB sınırı ayrıca gerekir.
Sıklık sınırı geçilirse sistem `429` ve `Retry-After` başlığını döner.
Ters vekil, tarayıcının bu başlığı okuyabilmesini sağlar.
Ek daha sonra açılırsa sunucu boyutu, gerçek içeriği ve kayıt iznini denetler.
Ek özel saklanır ve yeniden gönderimde aynı işlem kimliğini kullanır (AU-13).

Telefon sürümleri `X-Mobile-App-Version` ve `X-Mobile-Contract-Version` başlıklarında gönderir.
İlk sözleşme sürümünün değeri `1` olur.
Sunucu geçerli sürüm başlıklarına göre istek sayılarını tutar.
Ölçüm yalnız sürümleri ve sayıyı taşır.
Sistem her gün en çok 256 ayrı sürüm birleşimi sayar.
Yeni birleşimler bu sınırdan sonra ortak sayaçta toplanır.
Site, kapatılacak komutları `mobile_disabled_commands` listesine yazar.
Daha önce tamamlanmış işin sonucu yeniden alınabilir (AU-16).
Yayımlanan alanın adı, anlamı ve türü korunur.
Uyumu bozan değişiklik yeni uç sürümünde yapılır.
Eski uç proje kararıyla kapanana kadar bekleyen eski işlemleri kabul eder (AU-15).

Kurulumda site ayarına 32 bayt rastgele veriyle üretilen gizli bir `mobile_cursor_key` eklenir.
Anahtar değişirse telefonlar yeni bir tam kopya alır.
Gövde sınırının sunucuya ulaşmadan da uygulanması için ters vekil ayarı gerekir.
Site, `Retry-After` başlığını izinli tarayıcı kaynaklarına açar.

## Yapay zekâ ile yönetim

Sistem yöneticisi telefon kurulumlarını kullanıcıya göre listeleyebilir.
Liste, kurulum kimliğini ve iptal durumunu gösterir.
Yapay zekâ tek kurulumu veya bütün kurulumları iptal etmek için öneri açar.
Kullanıcı öneriyi onaylayana kadar sunucu hiçbir kurulumu iptal etmez.
Onaydan önce kurulumlar değişirse sunucu yeni bir önizleme ister.
Kurulum, doğrulanmış Keycloak oturum kimliğini `sid` alanından alır.
Eski kurulumlar yeniden kayıt olurken oturum kimliğini bağlar.
Yeni oturum, yeni kurulum kimliği ister.
Sunucu iptal edilen oturumun özetini saklar.
Aynı oturumla gelen mobil istekler reddedilir.

Kurulum iptali tek başına Keycloak oturumunu kapatmaz.
Veritabanı işlemi kesinleşince sunucu `POST /v1/sessions/revoke` çağrısı yapar.
Bu çağrı kimlik servisi için ayrı bir servis belirteci kullanır.
Kimlik servisi oturumu kapatana kadar yenileme belirteci geçerli kalabilir.
Uzak çağrı başarısız olursa yerel iptal geçerli kalır.
Sunucu kapanma doğrulanana kadar bekleyen durumunu saklar.
Toplu iptal yalnız etkin kurulumlardan kapanma isteği çıkarır.
Yönetici bekleyen kapanma için tekli iptali yeniden onaylayabilir.
Başka geçerli oturumdan tekli iptal isteği de yeniden gönderilebilir.
Kapanma sonucu ayrı veritabanı işleminde saklanır.
Yönetici gerekirse oturumu kimlik tarafında ayrıca kapatır.
Eski kurulumda oturum kimliği varsa çağrı yapılır.
Oturuma bağlanmamış eski kurulum için yönetici kimlik tarafını kullanır.

Servis adresi `mobile_identity_sync_url` ayarında bulunur.
Belirteç adresi `mobile_identity_sync_token_url` ayarından okunur.
Servis hesabı `mobile_identity_sync_client_id` ve `mobile_identity_sync_client_secret` kullanır.
Kiracı servis hesabı belirteci `aud-identity-sync` kapsamıyla ister.
Sunucu bu ayarları güvenli site yapılandırmasından okur.
Canlı servis için kimlik ekibi servis hesabını ve kapsamı tanımlar.

O-25 uyarınca erişim belirteci 5 dakika geçerlidir.
Çalışanın Keycloak oturumu 1 saat boşta kalabilir. Toplam süre 24 saattir.
Müşterinin oturumu 7 gün boşta kalabilir. Toplam süre 30 gündür.
Yenileme belirteci her kullanımda değişir.
Bu oturum sürelerini kimlik tarafı uygular.

O-27 uyarınca hesap silme akışını kimlik servisi başlatır.
Kullanıcı silinince mobil kurulumlar ve bağlı teslim kayıtları temizlenir.
Kimlik servisi hesabı kapatırken `revoke_user_installations` ucunu çağırır.
Uç yalnız kimlik kancasının doğruladığı `identity-sync` belirtecini kabul eder.
Uç bütün kurulumları iptal eder ve özel bildirim bağlarını kaldırır.
Aynı istek, kurulum listesi değişmedikçe aynı iptal sayısını verir.
Kimlik kancası bu adresi kesin servis adresleri listesine almalıdır.
Kanca bu yolu mobil belirteç yolundan önce ayırmalıdır.
Tekrar çağrısı, bekleyen kapanmaları sınırlı sayıda yeniden dener.
Daha önce doğrulanan kapanmalar yeniden gönderilmez.
İş kayıtlarının anonim yapılması hesap silme akışının ayrı adımıdır.

Yapay zekâ temizlik denemesini de öneri olarak açar.
Önizleme süresi dolan kayıtların sayısını gösterir.
Sunucu onaydan sonra sayımı tekrar çalıştırır.
Onay ekranında ilk önizlemenin sayıları kalır.
Bu araç kayıt silmez.

## Kaynakta doğrulanan Frappe davranışı

Yerel `frappe/erpnext:v16.55.0` imajında Frappe 16.56.0 bulunur.
Sürüm `frappe/__init__.py:58` satırından doğrulandı.

- `frappe/app.py:114–133` önce kimliği, sonra `cmd` alanını denetler.
  API yolu bu denetimlerden sonra çalışır.
- `frappe/app.py:338–351` JSON gövdesini adres parametrelerinden ayrı işler.
  Bu yüzden kanca her iki kaynağı ayrı denetler.
- `frappe/api/v1.py:35–41` mobil uç çalışmadan önce `cmd` alanını ekler.
  Mobil uç, gelen ham gövdeyi ve adres parametrelerini ayrı denetler.
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
