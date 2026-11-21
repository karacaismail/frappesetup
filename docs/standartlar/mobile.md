# Mobil uygulama standartları: PWA ve Capacitor

Bu kuralları telefon uygulaması yazan ajan uygular. Uygulama aynı arayüz kodundan iki biçimde çıkar. PWA, tarayıcıdan ana ekrana eklenen web uygulamasıdır. Capacitor, web arayüzünü telefon uygulaması olarak paketler. Arayüz kodunda [ayrı arayüz belgesini](headless-frontend-standartlari.md) izleyin. Sunucuda [Python belgesini](frappe-python-standartlari.md) ve [Python dışı belgeyi](frappe-python-disi-standartlari.md) izleyin. Bu belge yalnız telefona özgü kuralları ekler.

## 1. İşe başlamadan önce

Kuralları okuyun ve işe uyanları uygulayın. **ZORUNLU** kuralda engeli koduyla bildirin. Etiketsiz kural her seviyede geçerlidir. Koşullu etiket kuralın geçerli olduğu durumu söyler. Görsel dil kuralları bu belgede yoktur. Görsel dilde ve erişilebilirlikte proje sahibinin kalıcı arayüz talimatlarını uygulayın.

Otomatik denetimi mevcut proje denetimine bağlayın. Git kancası için açık onay alın. Zamanlanmış işte V-9'u uygulayın.

### Terimler

- “Paket” bu belgede yalnız Capacitor paketidir. Projeye eklenen hazır koda “eklenti” denir.
- Yerel kod, telefonun kendi diliyle yazılan koddur. Örneğin Swift ve Kotlin.
- Yerel veri, telefonda saklanan veridir.
- Eşitleme, telefondaki ve sunucudaki veriyi uyumlu hâle getirir.
- Taslak, henüz sunucuya gitmemiş kullanıcı girdisidir.
- Giden kutusu, sunucuya gönderilmeyi bekleyen işlerin yerel kuyruğudur.
- Kapsam, telefonun o anda çalıştığı hesap ve sitedir. Gerekirse kiracı ya da şirket de kapsama girer.

### Proje sahibinin kararları

- Uygulamayı şirket çalışanları ve müşteriler kullanır.
- Aynı arayüz kodu PWA ve paket olarak çıkar.
- Hedef telefonlar iPhone, Android ve Huawei'dir.
- Yerel ekran yazılmaz. Yalnız hazır Capacitor eklentileri kullanılır.
- Uygulama her işi internet yokken de yapabilsin.
- Telefondaki veri SQL ile saklanır.
- Çakışmada uygulama farkı gösterir ve kullanıcıya sorar.
- Giriş önce Keycloak kimlik sunucusundan geçer.
- Giriş yolları e-posta ve parola, sihirli bağlantı, Google, Apple ve passkey'dir.
- Uygulama bildirim, kamera, barkod, konum ve biyometrik giriş kullanır.
- Küçük ekran düzeltmeleri ve yeni sayfalar mağazayı beklemeden gitsin.
- Eski sürüm çalışmaya devam etsin.
- Fiziksel ürün ya da hizmet için ödeme alınır.
- Çökme kaydı ve kullanım ölçümü toplanır.
- Uygulama PoC seviyesinde başlar.
- Elde gerçek iPhone ve Android telefon vardır.

Sihirli bağlantı, e-postaya gelen tek kullanımlık giriş bağlantısıdır. Passkey, parmak izi, yüz ya da telefonun kilit koduyla açılan parolasız giriştir. Dış servis, lisans ve ödeme sağlayıcısı proje kararı ister. Mağaza yayını da proje kararı ister. Eksik karar işi etkilerse KR-3 ile sorun.

### Değişiklikte izlenecek sıra

1. Proje kaydından seviyeyi, hedef telefonları ve iş listesini okuyun.
2. İşin çevrimdışı sınıfını ES-1 ile belirleyin.
3. Hazır eklentiyi ve ortak katmanı HZ-1 ile arayın.
4. Sunucu sözleşmesini okuyun. Eksik uç için AU kurallarıyla öneri yazın.
5. Kod yazmadan önce TE-1 kuralını uygulayın.
6. En küçük değişikliği yapın.
7. Paketi ve PWA'yı MT kurallarıyla sınayın. Sonucu KR-1 ile raporlayın.

## 2. Kapsam, telefonlar ve seviye

“Huawei” tek bir hedef değildir. Hedefler şunlardır:

| Hedef | Yol |
|---|---|
| iPhone | Paket ve PWA |
| Google servisli Android | Paket ve PWA |
| Android paketi çalıştıran Huawei | Aynı koddan ayrı Huawei paketi. Her yetenek Google servisi olmadan sınanır. |
| Android paketi çalıştırmayan Huawei | Aynı arayüzün tarayıcı yolu. Kurulum, ağsız açılış ve giriş ayrı sınanır. İlk yayın kapsamı proje kararıdır. |

**KP-1 (ZORUNLU).** Desteklenen hedefleri proje kaydına yazın. Huawei hedefini kayıttan çıkarmayın.

**KP-2 (ZORUNLU).** Google servisine bağlı özelliği isteğe bağlı kurun. Servis yoksa uygulama açılsın. Ana iş yine çalışsın.

**KP-3 (ZORUNLU).** Özelliğin varlığını çalışma anında sınayın. Telefon markasına göre karar vermeyin.

**KP-4 (ZORUNLU).** Gerçek telefonda kanıtlanmayan hedef için destek bildirmeyin. Yapılmayan deneyi `not_run`, başarısız deneyi `fail` yazın.

**KP-5 (ZORUNLU).** Ekranı role göre gizlemek yetki değildir. Her istekte siteyi, üyeliği, rolü ve veri yetkisini sunucuda doğrulayın. Telefona yalnız izinli veriyi indirin.

OL-3 ve seviyelerin şu ekleri telefonda geçerlidir:

- **PoC, deneme sürümü.** En riskli işleri örnek veriyle kanıtlayın. Bunlar ağsız açılış, girişten dönüş ve çevrimdışı yazıp eşitlemedir.
- **MVP, ilk kullanılabilir sürüm.** Tam iş listesini ve mağaza koşullarını tamamlayın. Hesap silmeyi, cihaz iptalini ve canlı güncellemeyi kurun.
- **Scale, büyüme sürümü.** Açılış süresini, paket boyutunu ve yerel depoyu ölçün. Ölçümü proje denetimine bağlayın. Eşitlemeyi yük altında ölçün.
- **Enterprise, kurumsal sürüm.** Kayıp telefon tatbikatı yapın. Eski sürümden geçişi sınayın. Geçici çözümlerin hepsini kapatın.

## 3. Paket ve PWA

WebView, paketin içinde ekranı gösteren tarayıcı bileşenidir. Service worker, internet yokken sayfayı sunan tarayıcı betiğidir. Köken (origin), sayfanın protokolü, sunucu adı ve kapı numarasıdır.

**PK-1 (ZORUNLU).** Arayüz kodunu tek tutun. Paket ile tarayıcı farkını tek uyarlayıcı katmanda toplayın.

**PK-2 (ZORUNLU).** Pakette ekran dosyalarını paketin içinden sunun. Üretimde `server.url` ile uzak siteyi yüklemeyin. Düz HTTP kullanmayın.

**PK-3 (ZORUNLU).** Yerel ekran, özel yerel eklenti ve kendi yerel kodunuzu yazmayın. Eklentinin resmî belgesindeki kurulum satırlarını aynen ekleyebilirsiniz. İzin metni ve alan adı bağı gibi yerel ayarları düzenleyebilirsiniz. Eklediğiniz her satırı ve kaynağını proje belgesine yazın. Katalogdaki eklentileri baştan pakete koyun.

**PK-4 (ZORUNLU).** Eklentiyi HZ-4 ile seçin. Önce resmî `@capacitor/` eklentisine bakın. Son sürüm tarihine bakın. Eklentinin Android bağımlılıklarında Google servisini arayın. İzinleri ve gizlilik beyanını yazın. Cordova eklentisini kurmayın.

**PK-5 (ZORUNLU).** Eklenti yoksa hazır web yolunu sınayın. Eksik yeteneği kaydedin. İşi tamamlayamayan hedefin yayın kararını proje sahibine bırakın.

**PK-6 (ZORUNLU).** Eklentinin desteklediği Capacitor sürümlerini doğrulayın.

**PK-7 (ZORUNLU).** PWA'da sürümlü ekran dosyalarını service worker ile saklayın. PWA'ya ayrı alt yol verin. Service worker `scope` değerini bu yolla sınırlayın. Kişiye özel API yanıtını genel önbelleğe almayın. Eski betikle yeni dosyanın karışmasını sınayın. Pakette service worker kaydetmeyin.

**PK-8 (ZORUNLU).** Paketin kökenini gerçek telefonda ölçün ve kaydedin. Capacitor 8'de varsayılan iPhone'da `capacitor://localhost`, Android'de `https://localhost` değeridir.

**PK-9 (ZORUNLU).** Uygulamaya giren bağlantıyı doğrulanmış alan adına bağlayın. Hedef ekranı izin listesiyle seçin. Kaydı açarken sunucu iznini yeniden denetleyin.

**PK-10 (ZORUNLU).** Geri tuşunda ve uygulama arka plana geçince kaydedilmemiş taslağı koruyun.

**PK-11 (ZORUNLU).** Pakette dijital ürün satışının rotasını ve bağlantılarını kapatın. Dijital ürün ödemesini başlatan yolu da kapatın. Yalnız menüyü gizlemek yetmez. Doğrudan girişi sınayın.

## 4. Telefon özellikleri ve izinler

**OZ-1 (ZORUNLU).** Telefon özelliğini tek ortak sarmalayıcıdan çağırın. Sarmalayıcı paketi, PWA'yı ve özelliğin olmadığı telefonu ele alsın.

**OZ-2 (ZORUNLU).** İzni özelliğin kullanıldığı anda isteyin. Açılışta toplu izin istemeyin. Reddedilirse işi başka yolla sürdürün. Örneğin barkod elle yazılsın.

**OZ-3 (ZORUNLU).** İzin metnine gerçek amacı yazın. İş için en dar izni seçin. Örneğin fotoğraf seçiminde geniş medya izni istemeyin.

**OZ-4 (ZORUNLU).** Her eklentinin topladığı veriyi gizlilik bildirimine ve mağaza beyanına işleyin.

| Özellik | PWA'daki karşılığı |
|---|---|
| Bildirim | Web Push. iPhone'da yalnız ana ekrana eklenince çalışır. |
| Kamera ve fotoğraf | Dosya seçme alanı ya da kamera erişimi |
| Barkod ve karekod | Tarayıcı okuyucusu ya da onaylı kitaplık. Yoksa elle giriş. |
| Konum | Tarayıcının konum özelliği |
| Parmak izi ya da yüz | Passkey girişi. Yerel kilit yoktur. |

## 5. Giriş ve oturum

Belirteç, oturumu kanıtlayan gizli değerdir. PKCE, giriş kodunu başlatan uygulamaya bağlayan yöntemdir. Sistem tarayıcı sekmesi, telefonun kendi tarayıcısının uygulama içinde açılan sekmesidir. Güvenli depo, işletim sisteminin şifreli anahtar deposudur.

**GR-1 (ZORUNLU).** Pakette girişi sistem tarayıcı sekmesinde açın. Giriş sayfasını uygulamanın içindeki WebView'de göstermeyin.

**GR-2 (ZORUNLU).** Yetkilendirme kodu akışını PKCE S256 ile kurun. Pakete istemci sırrı ve API anahtarı koymayın.

**GR-3 (ZORUNLU).** Dönüş adresini kimlik sunucusuna tam adresle kaydedin. Doğrulanmış HTTPS bağlantısını tercih edin. `state` değerini doğrulayın. Kimlik belirteci kullanıyorsanız `nonce` değerini de doğrulayın.

**GR-4 (ZORUNLU).** Erişim belirtecini kısa ömürlü tutun ve bellekte saklayın. Yenileme belirtecini güvenli depoda saklayın. Kimlik sunucusu yenileme belirtecini her kullanımda değiştirsin. Belirteçli isteğe oturum çerezi eklemeyin.

**GR-5 (ZORUNLU).** Giriş yöntemini kimlik sunucusunda açın. Uygulamaya ayrı parola ekranı yazmayın. Kimlik sunucusu eklentisi için HZ-4 ve proje kararı alın.

**GR-6 (ZORUNLU).** Apple ile girişi kimlik sunucusu üzerinden sunun. Bütün kanallarda aynı giriş yollarını açın.

**GR-7 (ZORUNLU).** Biyometrik girişi kimlik sunucusunda passkey olarak açın. Yerel kilitte biyometrik onayı güvenli depodaki anahtara bağlayın. Biyometri yoksa telefonun kilit kodunu kullanın. Yerel kilidi sunucu oturumu saymayın. Pakette ağsız soğuk açılışta veriyi yerel kilitle açın.

**GR-8 (ZORUNLU).** Süreleri proje kaydından alın. Kimlik sunucusunun boşta kalma ve toplam süresini ayrı okuyun. Frappe çerez, yerel kilit ve bağlantısız erişim süresini de okuyun. Süreleri paket ve PWA için ayrı uygulayın. Bağlantısız erişim süresi dolunca özel veriyi kilitleyin.

**GR-9 (ZORUNLU).** Oturum bitince giden kutusunu durdurun. Giden kutusunu silmeyin. Sürdürmeden önce oturumu ve izinleri yeniden doğrulayın.

**GR-10 (ZORUNLU).** PWA'yı sunucuyla aynı kökenden sunun. PWA'da çerezli oturumu SZ-7 ile kullanın. Tarayıcı deposuna belirteç yazmayın (GV-4).

## 6. Telefondaki veri

**VR-1 (ZORUNLU).** Pakette kalıcı iş verisini şifreli SQLite'ta saklayın. SQLite, telefonda çalışan SQL veritabanıdır. WebView deposunu kalıcı saymayın.

**VR-2 (ZORUNLU).** Veritabanı anahtarını güvenli depoda saklayın. `@capacitor/preferences` eklentisine gizli değer yazmayın.

**VR-3 (ZORUNLU).** Yerel veriyi tek veri katmanından okuyun ve yazın. Bileşenden doğrudan SQL çalıştırmayın. PoC'de PWA için SQLite'ı hedef tarayıcılarda sınayın. Çalışmazsa yedek depoyu proje kararıyla seçin.

**VR-4 (ZORUNLU).** Yerel şema değişince geçiş yazın. Geçişi desteklenen en eski sürümün verisiyle sınayın.

**VR-5 (ZORUNLU).** Yerel veriyi ve anahtarı kapsama göre ayırın. Giden kutusunu, eki ve imleci de ayırın. Belirteci ve bildirim bağını da ayırın.

**VR-6 (ZORUNLU).** Telefona yalnız onaylı kayıt türlerini ve alanları indirin. Listeyi ve okuma süresini proje kaydından alın.

**VR-7 (ZORUNLU).** Yüksek gizlilikli yerel veriyi işletim sisteminin yedeğine bırakmayın. Hazır yol yoksa eksikliği kaydedin.

**VR-8 (ZORUNLU).** PWA deposunda belirteç ve ödeme verisi saklamayın. Yüksek gizlilikli alanı da saklamayın. Bu alanları proje kaydında işaretleyin. İzinli iş verisini yalnız gerekli alanlarla tutun.

**VR-9 (ZORUNLU).** Tarayıcı destekliyorsa PWA'da kalıcı saklama izni isteyin. Sonucu denetleyin ve kullanıcıya gösterin. Depo silinirse izinli veriyi yeniden alın. Kaybı fark ederseniz kullanıcıya bildirin.

**VR-10 (ZORUNLU).** Depo dolunca formu açık tutun. Girdiyi kaybetmeyin ve kullanıcıyı uyarın.

## 7. İnternet yokken çalışma ve eşitleme

İşlem kimliği, aynı işin iki kez işlenmesini önleyen tekil değerdir. İmleç, sunucunun “buraya kadar aldın” işaretidir.

| Sınıf | Davranış | Örnek |
|---|---|---|
| Yalnız telefonda | İş sunucuya gitmez. | Okuma, arama, taslak hazırlama |
| Kuyruğa girer | Sonuç giden kutusuna girer. Sunucu bağlantı gelince onaylar ya da reddeder. | Sipariş, ziyaret kaydı, not, fotoğraf |
| İnternet ister | Hazırlık telefonda yapılır. Son adım bağlantı ister. | İlk giriş, kart doğrulaması |

**ES-1 (ZORUNLU).** Her işin sınıfını proje kaydına yazın. “İnternet ister” sınıfı için gerekçe yazın. Bu sınıfa iş eklemek proje kararı ister. Öteki işler internet yokken tamamlanmalı ya da kuyruğa girmelidir.

**ES-2 (ZORUNLU).** Çevrimdışı çalışmayı tek ortak eşitleme katmanıyla kurun. Katmanı sürümlü mobil sözleşmeye bağlayın. Ham DocType tanımına bağlamayın. Ekran başına ayrı eşitleme kodu yazmayın.

**ES-3 (ZORUNLU).** Değişikliği ve giden kutusu kaydını aynı yerel işlemde yazın. Uygulama kapanıp açılınca kuyruk sürsün. Bağlı işleri sırayla gönderin. Kalıcı hatalı işi ayrı bekletin.

**ES-4 (ZORUNLU).** İlk gönderimden önce işe sabit bir işlem kimliği verin. Yeniden gönderimde aynı kimliği kullanın.

**ES-5 (ZORUNLU).** Çevrimdışı açılan kayda kimliği telefonda verin. Kimlik UUID olsun. İş numarasını sunucudan bekleyin.

**ES-6 (ZORUNLU).** Kaydı güncellerken ve silerken okuduğunuz sürümü gönderin. Sürümü değiştirmeden geri gönderin. Çakışmada iki hâli ve farkı gösterin. Seçimi kullanıcıdan alın. Seçimi yeni bir yazma olarak gönderin. Cihaz saatine göre karar vermeyin.

**ES-7 (ZORUNLU).** Kuyruktaki işi kesinleşmiş göstermeyin. Durumu açıkça gösterin. Sunucu reddederse nedeni gösterin. Kullanıcının girdisini koruyun.

**ES-8 (ZORUNLU).** Eşitlemeyi açılışta, öne dönüşte, ağ gelince ve kullanıcı isteyince deneyin. PWA'da aynı anda tek sekme eşitlesin. Arka plan görevini yalnız ek fırsat sayın. Geçici hatada ve 429 yanıtında aralığı artırın. 413 yanıtını ve yetki hatasını yinelemeyin.

**ES-9 (ZORUNLU).** Değişenleri sunucunun imleciyle çekin. İmleci değiştirmeden saklayın. İmleci, gelen sayfayla aynı yerel işlemde ilerletin. İmleç geçersizse yetkili tam kopya alın. Önce giden kutusunu koruyun.

**ES-10 (ZORUNLU).** Sunucuda silinen kaydı yerelden kaldırın. Gönderilmemiş değişikliği varsa bunu çakışma olarak gösterin. Silinen kaydı kendiliğinden yeniden oluşturmayın. Yetkisi kalkan kaydın sunucu verisini silin. Kullanıcının girdisini ayrı taslakta koruyun.

**ES-11 (ZORUNLU).** Son eşitleme zamanını gösterin. Tazeliği sunucu zamanıyla hesaplayın. Okuma süresi dolan kaydı göstermeyin. Süresi dolmuş veriye dayanan işi göndermeyin. Taslağı saklayın ve yeniden onay isteyin. Teslim süresi dolan taslağı onaysız göndermeyin.

**ES-12 (ZORUNLU).** Pakette eki uygulamanın kalıcı veri klasöründe şifreli saklayın. Anahtarı güvenli depoda tutun. PWA'da yalnız izinli eki saklayın. Eki kayıttan sonra gönderin. Ek hazır olmadan işi gönderilmiş göstermeyin. Yarım kalan yüklemeyi güvenle yeniden başlatın. İş ve dosya kimliğini değiştirmeyin.

**ES-13 (ZORUNLU).** Ödemeyi ve kart verisini kuyruğa almayın.

**ES-14 (ZORUNLU).** Kalıcılığı kanıtlanmayan ortamda geri alınamaz işi tek yerel kopyaya bırakmayın. Bu işi bağlantı gelince hemen gönderin. PWA'da gönderilmemiş kayıt varken kullanıcıyı uyarın.

## 8. Çıkış, hesap ve cihaz

**CK-1 (ZORUNLU).** Çıkış seçimi açılınca ES-14 dahil kendiliğinden gönderimi duraklatın. Bekleyen iş sayısını gösterin. Ertelemeyi ve silmeyi sunun. Ağ varsa göndermeyi de sunun. Saklamada CK-3'ü uygulayın. Sormadan silmeyin.

**CK-2 (ZORUNLU).** Çıkışta yerel erişimi hemen kapatın. Belirteci ve özel önbelleği silin. Saklanan taslak ve ekleri dışındaki yerel veriyi silin. Yarım kalan temizliği açılışta tamamlayın. Çıkıştan sonra sessizce eşitlemeyin.

**CK-3 (ZORUNLU).** Çıkıştan sonra taslağı yalnız kişisel telefondaki pakette saklayın. Saklanan taslağı şifreli depoda tutun. Saklama süresini proje kaydından alın.

**CK-4 (ZORUNLU).** Saklanan taslağı yalnız aynı hesap ve kapsamla açın. Kaydı başka kullanıcı adına göndermeyin.

**CK-5 (ZORUNLU).** Ağ varsa sunucu oturumunu kapatın. Pakette belirteci silmeden önce iptal edin. Bağlantı yoksa yerel çıkışı ve iptal durumunu ayrı bildirin.

**CK-6 (ZORUNLU, MVP ve üstü, hesap açılabiliyorsa).** Uygulamaya hesap silme yolunu koyun. Silme için bir web adresi de verin. Silme talebini sunucuda kaydedin. Kimlik sunucusundaki kayıt bağlantısını da hesap açma sayın. İlk girişte kendiliğinden açılan hesap da buna girer.

**CK-7 (ZORUNLU, MVP ve üstü).** Hesap silinince cihaz kaydını ve bildirim bağını silin. Yerel veriyi de silin. Tek siteden ayrılmayı hesabı silmekle karıştırmayın.

**CK-8 (ZORUNLU, MVP ve üstü).** Cihaz iptalinde sunucu erişimini ve bildirim bağını kapatın. Telefon iptali öğrenince proje kaydındaki silme kuralını uygulayın.

**CK-9 (ZORUNLU).** Telefon tek etkin kapsamla çalışsın. Kapsam değişmeden önce bekleyen iş için CK-1'i uygulayın. Kapsam değişince eski eşitlemeyi durdurun. Önceki kapsamın geç yanıtını yeni kapsama yazmayın. Önceki kapsamın verisini göstermeyin. Sunucu adresini izinli alan adı listesiyle doğrulayın.

## 9. Bildirim

Bildirim belirteci, telefonun bildirim adresidir.

**BL-1 (ZORUNLU).** PoC'de uygulama içi bildirim listesini kullanın. Telefon bildirimi denemesi proje kararı ister. Dış bildirim servisini proje kararıyla açın.

**BL-2 (ZORUNLU, bildirim varsa).** Bildirim metnine kişisel veri koymayın. İçeriği yetkili istekle sunucudan alın.

**BL-3 (ZORUNLU, bildirim varsa).** Bildirim belirtecini hesaba, kapsama ve sağlayıcıya bağlayın. Belirteci açılışta ve değişince sunucuda yenileyin. Çıkışta ve hesap silinince bağı kaldırın.

**BL-4 (ZORUNLU, bildirim varsa).** Bildirim kaydı başarısız olursa uygulamayı durdurmayın. Tarayıcı destekliyorsa PWA'da ayrı Web Push yolunu kullanın. Bildirim yoksa listeyi erişilebilir tutun. MVP'de her hedefin sağlayıcısını ve teslim kanıtını kaydedin.

**BL-5 (ZORUNLU).** Bildirime güvenerek iş kurmayın. Bildirim gelmese de uygulama açılınca eşitlesin.

## 10. Güncelleme ve eski sürüm

Canlı güncelleme, web dosyalarının mağaza beklemeden pakete indirilmesidir. Kanal, aynı yerel sürüme giden güncelleme hattıdır.

| Sıra | Yol | Koşul |
|---|---|---|
| 1 | Sunucudan gelen metin, çeviri, tema ve sayfa tanımı | Katalogdaki bileşenle çizilir. Kod taşımaz. |
| 2 | PWA'nın web yayını | Form ya da eşitleme ortasında uygulanmaz. |
| 3 | Pakette imzalı canlı güncelleme | MVP ve üstünde iPhone ve Google Play paketinde. Yalnız hata düzeltir. Huawei paketinde kapalıdır. |

**GN-1 (ZORUNLU).** Küçük düzeltmede ilk yolu deneyin. Veriyi sabit şemayla denetleyin. Tanım kod, yetki ve iş akışı kuralı taşımasın. Sayfayı RE-11 ile çizin. Tanımı ve kaydı sabit yerel şemada saklayın. Sunucu VR-6 listesini ve okuma süresini sözleşmeyle göndersin. Gizli özellik koymayın. Eski sözleşmeye zorunlu alan eklemeyin. Eski sürümün kuyruğunu koruyun.

**GN-2 (ZORUNLU).** Güncellemeyi form ya da eşitleme ortasında uygulamayın.

**GN-3 (ZORUNLU, MVP ve üstü).** Canlı güncellemeyi iPhone ve Google Play paketinde kurun. Aracı HZ-4 ile seçin. Dış servis için proje kararı alın. Mağaza kuralını MG-7 ile okuyun. Huawei paketinde mağazanın güncelleme yolunu kullanın.

**GN-4 (ZORUNLU, canlı güncelleme varsa).** Yalnız var olan ekranın hatasını düzeltin. Yeni özelliği, eklentiyi, izni, yerel ayarı ve yerel şemayı mağaza sürümüyle çıkarın.

**GN-5 (ZORUNLU, canlı güncelleme varsa).** Güncelleme dosyasını imzalayın ve imzayı telefonda doğrulayın. Açılış başarısızsa önceki dosyaya dönün. Veri kaybetmeden dönüldüğünü sınayın. Her yerel sürüme ayrı kanal verin. İlk web dosyalarını mağaza sürümüne koyun.

**GN-6 (ZORUNLU).** Her istekte uygulama ve sözleşme sürümünü gönderin. Giden kutusundaki iş, yazıldığı sözleşme sürümünü taşısın.

**GN-7 (ZORUNLU).** “Bu işlem bu sürümde yapılamıyor” yanıtını anlaşılır gösterin. Bu yeteneği ilk sürüme koyun. Bu durumda izinli yerel okumayı ve geçerli taslağı koruyun.

**GN-8 (ZORUNLU).** Bağlantı yokken kullanıcıyı sürüm yüzünden engellemeyin. Genel zorunlu güncelleme koymayın.

## 11. Ödeme

**OD-1 (ZORUNLU, ödeme varsa).** Kart bilgisini uygulamada toplamayın ve saklamayın. Projede onaylı sağlayıcının barındırdığı ödeme sayfasını kullanın.

**OD-2 (ZORUNLU, ödeme varsa).** Ödeme sayfasını sistem tarayıcı sekmesinde açın. Ödeme oturumunu sunucu açsın.

**OD-3 (ZORUNLU, ödeme varsa).** Ödeme sonucunu sunucuda doğrulayın. Telefona dönen bağlantıya güvenmeyin.

**OD-4 (ZORUNLU, ödeme varsa).** Fiziksel üründe mağaza ödemesi kullanmayın. Uygulama dışında tüketilen hizmette de kullanmayın. Uygulama içinde tüketilen dijital hizmeti dış ödemeyle satmayın. Fiziksel ürünle dijital hakkı aynı sepete koymayın.

## 12. Mağaza, çökme kaydı ve ölçüm

**MG-1 (ZORUNLU, MVP ve üstü).** İncelemeye giriş ve örnek veri verin. Telefonda biten gerçek bir işi ve katalogdaki telefon özelliklerini gösterin. İnceleme notuna her yeni işlevi ve değişikliği ayrı yazın.

**MG-2 (ZORUNLU, MVP ve üstü).** Mağaza beyanını gerçekten giden veriyle eşleştirin. Kendi sunucunuz beyanı kaldırmaz.

**MG-3 (ZORUNLU).** Çökme kaydına ve ölçüm olayına kişisel veri koymayın. Belirteç ve girilen metin de koymayın. Olaylara izinli alan listesi verin.

**MG-4 (ZORUNLU, ölçüm varsa).** Kullanım ölçümünü kullanıcı onayına bağlayın. Onay geri çekilince bekleyen kullanım olayını silin. Çökme kaydını ve ölçümü projenin kendi toplayıcısına gönderin. Dış ölçüm aracı için proje kararı alın.

**MG-5 (ZORUNLU).** Yüksek gizlilikli veri gösteren ekranda dış ölçüm kodu açmayın. Oturum kaydı da açmayın.

**MG-6 (ZORUNLU, MVP ve üstü).** Çökme ile JavaScript hatasını ayrı sınayın. Sürümü, yerel sembolü ve kaynak haritasını eşleştirin.

**MG-7 (ZORUNLU, MVP ve üstü).** Mağazanın güncel teknik koşullarını yayından önce resmî kaynaktan okuyun. Koşulu bellekten yazmayın.

## 13. Frappe arka ucunda önlemler

Bu bölüm sunucu kodunu yazan ajan içindir.

**AU-1 (ZORUNLU).** Telefon için sürümlü mobil uçlar açın. Uçları onaylı işlerle sınırlayın. Telefon eşitlemesini genel kayıt uçlarına bağlamayın. Bu kural telefonda SZ-6'nın önüne geçer. Ucu DocType alanına doğrudan bağlamayın.

**AU-2 (ZORUNLU).** İzinli eşitleme komutlarını sunucuda tanımlayın. Her komutun kayıt türlerini, alanlarını ve eklerini belirleyin. Ekran tanımından yazma izni üretmeyin. Yetkiyi ve doğrulamayı her komutta uygulayın.

**AU-3 (ZORUNLU).** Paket isteğinde kimlik sunucusunun erişim belirtecini zorunlu tutun. Belirteci `auth_hooks` kancasında doğrulayın. İmzayı yalnız onaylı algoritmayla doğrulayın. Vereni, hedef API'yi ve siteyi denetleyin. Süreyi, izinli istemciyi ve belirtecin izinlerini denetleyin.

**AU-4 (ZORUNLU).** Her girişte kullanıcıyı veren ve kullanıcı kimliği çiftiyle bulun. Bağı paket ve PWA için `social_logins` dışında ortak kayıtta tutun. İlk bağı yalnız doğrulanmış e-postayla kurun. Bağ farklıysa oturum açmadan reddedin. “Social Login Key” girişi her girişte e-postayla eşler. Frappe 16'da bu girişi `on_social_login` kancasıyla denetleyin. Frappe 15'te ya da e-posta değişebiliyorsa kendi dönüş ucunuzu yazın. Hazır girişi de kapatın. Kullanıcının etkin olduğunu her istekte denetleyin. Hesap kimlik sunucusunda kapanınca Frappe kullanıcısını da kapatın. Frappe kayıt iznini uygulayın.

**AU-5 (ZORUNLU).** Kimlik sunucusu belirtecini yalnız mobil uç adreslerinde kabul edin. Bu istekte `cmd` alanı varsa reddedin. Geçerli çerez oturumunu ve belirteci birlikte taşıyan isteği reddedin. Misafir çerezini oturum saymayın. Ön denetim isteğinde belirteç aramayın. Yanlış hedefli, süresi dolmuş ve imzasız belirtecin reddini sınayın.

**AU-6 (ZORUNLU).** `allow_cors` ayarına yalnız gerçek paket kökenlerini tam adresle yazın. `*` yazmayın. Bu ayar yalnız tarayıcıdan gelen çapraz istek içindir. Genel CSRF muafiyeti açmayın. `Retry-After` başlığını nginx gibi ters vekilde tarayıcıya açın.

**AU-7 (ZORUNLU).** Site, hesap ve işlem kimliği tekilliğini veritabanında sağlayın. İçerik özetini, iş etkisini ve sonucu aynı işlemde yazın. Aynı kimlik yeniden gelirse ilk sonucu dönün. Aynı kimlikle farklı içeriği reddedin. Dış işte ve ek tesliminde aynı kimliği koruyun.

**AU-8 (ZORUNLU).** Güncellemede ve silmede telefonun okuduğu sürümü zorunlu alın. Yetkiyi ve sürümü yazmayla aynı kilitli işlemde denetleyin. Silmede bu karşılaştırmayı uçta siz yapın. Çakışmada güncel izinli kaydı dönün. Yeni kayıt için ayrı oluşturma komutu kullanın.

**AU-9 (ZORUNLU).** Telefonun kayıt kimliğinin biçimini ve kapsamını doğrulayın. İş numarasını ve kayıt adını sunucunun adlandırma kuralı belirlesin. Sıra numaralı kayıtta telefon kimliğini ayrı tekil alanda tutun. Hazır API v2 çağrısını UUID doğrulaması saymayın.

**AU-10 (ZORUNLU).** Değişenler için kararlı bir imleç verin. İlk tam kopyayı ve sonraki değişimleri ayrı tanımlayın. İmleç geç kesinleşen değişikliği atlamasın. Yalnız `modified` alanına dayanmayın. Bunu eşzamanlı yazmayla sınayın.

**AU-11 (ZORUNLU).** Silmeyi, ad değişikliğini ve yetki kaybını kaldırma işaretiyle bildirin. Kaldırma işareti, kaydın kaldırılacağını söyleyen kısa kayıttır. İşaretin saklama süresini belirleyin. Yönetici kurtarma tablosunu telefona açmayın.

**AU-12 (ZORUNLU, MVP ve üstü).** Kurulumu hesaba ve kapsama bağlı bir kayıtla izleyin. Her cihaz isteğinde kurulumun iptal durumunu denetleyin. Tek cihaz ve bütün cihazlar için iptal yolu verin. Cihaz kaydını kimliği doğrulanmış yazma ucuyla yönetin.

**AU-13 (ZORUNLU).** Dosyanın içeriğini, boyutunu ve kayıt iznini doğrulayın. Dosyayı özel saklayın. Yinelenen eki işlem kimliğiyle tekilleştirin. Dosya sınırını açıkça ayarlayın.

**AU-14 (ZORUNLU).** Eşitleme sayfasını, yazma grubunu ve dosyayı sınırlayın. Grup boyutunu sözleşmeye yazın. Sıklık sınırı aşılırsa 429 dönün. Gövde büyükse 413 dönün.

**AU-15 (ZORUNLU).** Yayımlanmış mobil sözleşmeden alan silmeyin. Alanın anlamını ve türünü değiştirmeyin. Uyumu bozan değişikliği yeni sürüme koyun. Eski sürümü proje kararı olmadan kapatmayın.

**AU-16 (ZORUNLU).** İstekle gelen uygulama ve sözleşme sürümünü sayın. Güvenlik engelinde yalnız etkilenen işlemi durdurun.

**AU-17 (ZORUNLU, bildirim varsa).** Bildirimi kayıt kesinleştikten sonra gönderin (B-5). Her sağlayıcı için ayrı gönderici yazın. Sağlayıcının geçersiz saydığı belirteci silin. Anlık bağlantıyı yalnız “yeniden çek” işareti sayın.

**AU-18 (ZORUNLU).** Çevrimdışı yazmaya açılan kayıt türü için tam plan yazın (B-8).

**AU-19 (ZORUNLU).** Kimlik sunucusu girişi yöneticilerde de çalışınca Frappe'nin parola girişini kapatın. E-posta bağlantısıyla girişi de kapatın. İki girişin reddedildiğini sınayın.

## 14. Önce test ve gerçek telefon kanıtı

**MT-1 (ZORUNLU).** Her hedefi gerçek telefonda sınayın. Ajan gerçek telefonu kullanamaz. Denemeyi yapacak kişiyi proje kaydından alın. Adımları ve beklenen sonucu yazın. Sonucu KR-5 ile yazın.

**MT-2 (ZORUNLU).** Android paketi hedefinde Google servissiz Android benzetimini deneyin. Huawei modelini ve cihaz erişimini kayıtta doğrulayın. Her modelde Android paketini ve Google servisini sınayın. Uzaktan cihaz hizmeti dış servistir. Bu hizmeti proje kararıyla kullanın.

**MT-3 (ZORUNLU).** Çevrimdışı işi uçak modunda sınayın. Soğuk açılışı, kaydı, eki ve bağlantının dönüşünü deneyin. Yinelenen gönderimi, çakışmayı, silmeyi ve yetki kaybını deneyin. Aynı işlemin eşzamanlı gönderimini ve yanıt kaybını sınayın.

**MT-4 (ZORUNLU).** Çıkışı, başka hesapla girişi ve kapsam değişimini sınayın. Girişten dönüşü, izin reddini ve bağlantısız çıkışı sınayın. Çerezli girişte etkin oturum sınırını ve kalan oturumları sınayın.

**MT-5 (ZORUNLU, MVP ve üstü).** Yayımdaki eski sürümü ve bekleyen eski isteği yeni sunucuda sınayın. Sunucu dağıtımını, web yayınını ve mağaza sürümünü ayrı kaydedin. Tek cihaz ve bütün cihazlar için iptali ayrı sınayın. Çıkıştan sonra bildirimin ne zaman durduğunu ölçün.

**MT-6 (ZORUNLU).** Ana ekrana eklenen PWA'yı Safari sekmesinden ayrı sınayın. PWA'nın ilk çevrimiçi hazırlığından sonra soğuk çevrimdışı açılışı sınayın. Kullanıcı temizliğini ve kotayı ayrı sınayın.

**MT-7 (ZORUNLU, sihirli bağlantı varsa).** Bağlantının kısa ömrünü ve tek kullanımını sınayın. Bağlantının giriş isteğine bağlı olduğunu sınayın. Başka tarayıcıda açılmayı ve yeniden gönderimi deneyin. E-posta önizlemesinin bağlantıyı tüketmediğini sınayın.

**MT-8 (ZORUNLU, Scale ve üstü).** Açılış süresini ve paket boyutunu gerçek telefonda ölçün. Yerel depo boyutunu da ölçün. Sınırı BY-1 ile kayıttan alın.

## Ek A. Proje kaydına yazılacaklar

Ayrı arayüz belgesinin Ek A'sındaki kaydı kullanın. Telefon için şu bilgileri ekleyin. Sorumluyu kişi adıyla değil rolle yazın. Açık kararın sahibini, tarihini ve etkilediği aşamayı yazın.

- Hedef ülkeler, mağazalar, dağıtım yolu ve uygulama sayısı.
- Desteklenen hedefler, işletim sistemleri, en eski telefon ve doğrulanmış yetenekler.
- Gerçek telefon denemesini yapacak kişi.
- Mağaza incelemesinde gösterilecek tamamlanmış iş.
- Çevrimdışı iş listesi, her işin sınıfı ve “internet ister” gerekçesi.
- Telefona inen kayıt türleri, alanlar ve yüksek gizlilikli alanlar.
- Yerel okuma ve bağlantısız erişim süreleri. Taslak teslimi ve imleç ömrü süreleri.
- Paket ve PWA için oturum süreleri. Yerel kilit ve taslak saklama süresi.
- Telefon türü, hesap değiştirme ve yedekleme kuralı.
- Davetli üyelik, açık kayıt ve hesap silme yolları.
- Cihaz iptalinde yerel verinin silme kuralı.
- Bildirim yolu, ödeme sağlayıcısı ve dış servis kararları.
- Dijital ürün varsa uygulamanın satıştaki rolü.
- Çökme ve ölçüm araçları ve toplanan alanlar.
- Ölçüm saklama süresi ve mağaza beyanı.
- Canlı güncelleme aracı ve güncelleme sunucusu.
- Desteklenen sözleşme sürümleri ve kapatılan işlemler.
- Açılış süresi, paket boyutu ve yerel depo sınırları.
- Ek dosyaların ağı, gönderim zamanı ve boyut sınırı.
- Hesap silinince iş kayıtlarına ne olacağı.
- Mağaza hesaplarının, deneme hesabının ve mağaza yazışmasının sahibi.
- Eklenti için eklenen yerel kurulum satırları ve kaynakları.

## Ek B. Doğrulanan davranışlar

Frappe satırları 15.126.1 ve 16.56.0 kaynaklarına dayanır. Kitaplık sürümleri 21 Kasım 2026 Cumartesi günü kayıt servisinden okundu. Huawei satırları gerçek telefonda sınanmadı. Sürüm değişince yeniden sınayın.

| Konu | Görülen davranış |
|---|---|
| Frappe ve dış belirteç | Frappe “Bearer” belirtecini önce kendi tablosunda arar. Sonra `auth_hooks` kancalarını her istekte çağırır. Kullanıcı boş ya da misafirse iki parçalı başlığı reddeder. Geçerli çerez oturumu varsa istek o kullanıcıyla sürer. |
| İstek yolu | Frappe `cmd` alanını `/api/` yolundan önce işler. Yol denetimi tek başına yetmez. |
| Frappe'nin kendi OAuth sağlayıcısı | PKCE'yi zorunlu kılmaz ve `plain` yöntemini kabul eder. Belirteç ucu istemci sırrını karşılaştırmaz. |
| Frappe CSRF | Denetim belirteç doğrulamasından önce çalışır. Oturumda CSRF değeri yoksa atlanır. Misafir oturumu CSRF değeri taşımaz. |
| Frappe CORS | `allow_cors` gelen kökeni listede tam eşleştirir. İzinli kökene kimlik bilgili yanıt verir. `Retry-After` başlığını tarayıcıya açmaz. |
| Frappe oturumu | `session_expiry` boşta kalma süresidir, toplam süre değildir. Eski oturumların kapanması `deny_multiple_sessions` ayarına ve kullanıcı sınırına bağlıdır. |
| Kayıt sürümü | Güncellemede `modified` karşılaştırılır. İstek bu değeri taşımazsa eski taslak yakalanmaz. Silmede ve yeni kayıtta karşılaştırma yoktur. `modified` kaydetme anında yazılır. |
| Kayıt kimliği | Frappe 16, `autoname: UUID` seçeneğinde istemcinin UUID'sini doğrular. Frappe 15'te bu seçenek yoktur. API v2, verilen adla olağan adlandırmayı ve UUID doğrulamasını atlayabilir. |
| Dosya sınırı | `file_manager` varsayılanı 10 MiB, yükleme ucunun varsayılanı 25 MiB'dir. Öteki isteklerin gövde sınırı site ayarından gelir. |
| Keycloak 26.8.2 | Hazır sosyal sağlayıcı listesinde Google var, Apple yok. Sihirli bağlantı için yerleşik yol doğrulanmadı. |
| Capacitor | Kararlı sürüm 8.6.2'dir. Service worker kaydı `capacitor://` adresinde başarısız oldu. |
| SQLite eklentisi | `@capacitor-community/sqlite` 8.1.1 telefonda SQLCipher ile şifreler. Web sürümü şifrelemez ve veriyi IndexedDB'de tutar. |
| iPhone PWA | Ana ekrana eklenen PWA, Safari'den ayrı kullanım günü sayacı tutar. Bu, kalıcılık güvencesi değildir. |
| iPhone'da Web Push | Yalnız ana ekrandaki uygulamada çalışır. iOS 16.4 gerekir. Apple servisi kullanılır. |
| Huawei telefonlar | Uluslararası Mate 80 Pro ve Pura 90s Pro EMUI kullanır. HarmonyOS NEXT için resmî yayın biçimi `.app` dosyasıdır. Girişten uygulamaya dönüş sınanmadı. |
| Bildirim eklentisi | Android yolu Firebase ve Google Play servisleri ister. Web karşılığı yoktur. iPhone'da `AppDelegate.swift` dosyasına iki hazır işlev ister. |
| Huawei bildirimi | Huawei Capacitor için Cordova eklentisini belgeler. PK-4 bu yolu kapatır. Capacitor 8'de Google servisi olmadan teslim doğrulanmadı. |
| Barkod eklentileri | ML Kit eklentisinin `scan()` yöntemi Google servisi ister. `startScan()` gömülü modeli kullanır. Resmî eklentide ZXing seçeneği vardır. |
| Huawei mağazası | 4.1 kuralı yalnız web sayfası toplayan uygulamayı kabul etmez. 3.9 kuralı özellik değiştiren kodun indirilmesini yasaklar. |
| Mağaza dışı güncelleme | Apple yorumlanan koda koşullu izin verir. Özellik değiştiren kodu yasaklar. Google Play WebView'deki JavaScript'e koşullu istisna tanır. Yerel kod mağaza dışında güncellenemez. |
