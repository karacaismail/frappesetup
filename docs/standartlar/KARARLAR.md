# Proje sahibinin kararları

Bu dosya 20 Kasım 2026 Cuma, 21 Kasım 2026 Cumartesi ve 22 Kasım 2026 Pazar günlerinin kararlarını toplar.

Çalışma Frappe için kod standartlarıyla başladı. Sonra mobil uygulamaya ve KVKK uyumuna genişledi.

Kararları proje sahibi verdi. Proje sahibinin sözleri tırnak içinde aynen aktarıldı. Yazım hataları korundu. Kısaltılan alıntıda atlanan yer […] ile gösterildi.

Bazı konuları proje sahibi modellere bıraktı. Bu kararlar “Modellerin kararları” bölümündedir. Modeller Claude, Codex ve Gemini'dir.

Kural kodları kural dosyalarındadır. Örneğin `GN-1` kuralı `mobile.md` dosyasındadır.

Bu dosyanın iki kopyası var. Biri `rules ai` klasöründe, öteki frappesetup deposundadır. İki kopya aynı kalmalıdır.

Öteki iki karar dosyası şunlardır:

- `SURECLER-VE-SONUCLAR.md` dosyaların nasıl yazıldığını ve denetlendiğini anlatır.
- `ACIK-ISLER.md` bekleyen kararları ve bitmemiş işleri toplar.

## Bu dosyada geçen sözler

- **Ajan.** Kod yazan yapay zekâ aracıdır. Örneğin Claude ve Codex birer ajandır.
- **Kural dosyası.** Ajanın kod yazarken uyduğu kuralları toplar.
- **Bayt.** Dosya boyutunun birimidir. Bir Türkçe kelime yaklaşık 8 bayt tutar.
- **Frappe.** Sunucuda çalışan hazır bir yazılım iskeletidir. Veriyi ve iş kurallarını tutar.
- **DocType.** Frappe'de bir kayıt türünün tanımıdır. Örneğin “Müşteri” bir kayıt türüdür.
- **Ayrı arayüz.** Frappe'nin dışında çalışan ekran uygulamasıdır. İngilizcesi “headless frontend”dir.
- **PWA.** Tarayıcıda açılan ve ana ekrana eklenen web uygulamasıdır.
- **Capacitor.** Web uygulamasını mağaza uygulaması olarak paketleyen araçtır.
- **Canlı güncelleme.** Mağaza uygulamasının ekran kodunu mağazayı beklemeden yeniler.
- **Keycloak.** Kullanıcı girişini yöneten açık kaynak kimlik sunucusudur.
- **Sihirli bağlantı.** E-postayla gelen tek kullanımlık giriş bağlantısıdır.
- **Passkey.** Parola yerine parmak izi ya da yüz tanımayla yapılan giriştir.
- **Olgunluk seviyeleri.** Yazılımın dört seviyesi PoC, MVP, Scale ve Enterprise'dır. PoC deneme sürümüdür. Enterprise en üst seviyedir.
- **Geçici çözüm.** “Şimdilik böyle kalsın, sonra düzeltiriz” denen koddur.
- **DDD planı.** Kod yazmadan önce iş alanını ve sınırlarını çıkaran plandır.
- **Modüler monolit.** Tek uygulamanın içinde sınırları belli modüllerdir.
- **Düşük bağımlılık.** Modüllerin birbirine olabildiğince az bağlanmasıdır.
- **SaaS.** İnternetten abonelikle kullanılan yazılımdır.
- **Kiracı.** Platformu kendi işi için kullanan şirket ya da kişidir.
- **KVKK ve GDPR.** Türkiye'nin ve Avrupa Birliği'nin kişisel veri yasalarıdır.
- **Kurul.** Kişisel Verileri Koruma Kurulu'dur.
- **Cron.** Bir işi belli aralıklarla kendiliğinden çalıştıran zamanlanmış görevdir.
- **Proje kaydı.** Her projenin seviyesini, sürümlerini ve kararlarını tutan dosyadır. Her kural dosyasının Ek A bölümü bu kaydın şablonudur.

## En önemli kararlar

1. Dört kural dosyası yazıldı. Dosyalar Python, Python dışı, ayrı arayüz ve mobil içindir.
2. Kural dosyaları görsel kural taşımaz. Görsel kurallar proje sahibinin kalıcı talimatlarındadır.
3. Önce DDD planı yazılır. Sonra modüler monolit kurulur. Sonra bağımlılık azaltılır.
4. Modül sınırı denetimi MVP ve üstünde zorunludur.
5. Son kullanıcı yalnız ayrı arayüzü görür.
6. Enterprise seviyesinde hiçbir geçici çözüm kalmaz.
7. Telefon uygulaması Capacitor paketi ve PWA olarak çalışır. Uygulama internet yokken de çalışır.
8. Bütün giriş yolları Keycloak'ta kurulur. Parmak izi ve yüzle giriş passkey ile olur.
9. Canlı güncelleme kendi sunucumuzdan kurulur.
10. SaaS'ta açılan yeni sayfa telefona mağaza güncellemesi olmadan gelir.
11. Yeni Huawei telefonlarda şimdilik tarayıcı yolu kullanılır.
12. Bütün veriler Hetzner'de durur. Bu karar KVKK için ek bir sözleşme ister.
13. Platform genel bir SaaS çerçevesidir. Bir pazaryeri planı değildir.
14. Düzenli silme için şimdilik cron kurulmaz.
15. KVKK ve GDPR uyum çalışması şimdilik durdu.
16. Backend geliştirmesi MVP seviyesinde başladı. Kod frappesetup deposundadır.
17. Giriş Keycloak ile olur. Keycloak'ın markası Atonota'dır. Atonota ayrı alan adında durur.
18. İlk turda Press de geliştirilir.
19. Bütün uygulamalar Frappe 16 ile yazılır. Press de Frappe 16 üzerinde çalışır.
20. Her şey yapay zekâyla yönetilebilir olur. Katman model sağlayıcısından bağımsızdır.
21. Proje sahibi kararları Claude'a bıraktı. Claude açık kararları kapatır ve kayda yazar.
22. Sisteme n tane yapay zekâ sağlayıcısı, hesabı ve API'si eklenebilir.

## 20 Kasım 2026 Cuma günü

### Karar 1. Frappe Python kodu için kural dosyası yazılacak

Bu istek önce eski bir oturumda verildi. O oturum haftalık kullanım sınırına takıldı. Bu çalışma işi oradan sürdürdü.

Proje sahibinin asıl isteği şudur:

> frappe python ; için:
>
> kod dosyası yaratırken, standartlarımızın ne olması gerektiğini belirleyen md dosyası ihtiyacım var.

İsteğin kabul ölçütleri şunlardır:

> - ...yaklaşık 4,4 KB pay kaldı... sorunu,
> - genel performans sorunları,
> - genel güvenlik sorunları,
> - sürdürülebilirlik ihtiyacı,
> - vibecoding kronik sorunları,
> - oracle problem,
> - oop mvc precedural, gibi mimari sorunlar,
> - yukarda bahsettiklerin,
> - benim bahsettiklerim,
> - öneriler, önerilerim,
> - modular monolith yaklaşım ihtiyacına karşın modular monolith ihtiyacı ile çelişen problemler,
> - sürdürülebilir kod için yazılımın bütünsel ilişki kurma ihtiyacı ve problemleri,
> - modüllerin, sınıfların veya servislerin birbirine olan bağımlılığının en aza indirilmesi için Low coupling yaklaşımının ihtiyaçları,
> - tdd first yaklaşım gereksinimleri,
> - mobile first adaptive delivery gereksinimleri,
> - yüksek performanslı yazılım çalışması ihtiyacı gereksinimleri,
> - gap analiz ihtiyaçları,
> - SOLID (SRP, OCP, LSP, ISP, DIP) prensipleri yönergeleri uygunluğunun kontrolünün ihtiyacı,
> - Çözümün olgunluk seviyesini (PoC, MVP, scale, Enterprise maturity) seviyesini belirlemek ve kapsamı buna göre uygulamak için PoC'de enterprise karmaşıklığı kurmamak ve Enterprise'da PoC seviyesinde geçici çözüm bırakmamak, böylelikle Sonraki seviyeye geçişi engelleyecek teknik borcu işaretlemek ihtiyacı,
> - technology-boundary; Yeni teknoloji, framework, package veya pattern eklemeden önce codebase ile uyumunu kontrol etmek, Çözülmüş bir problem için ikinci teknoloji eklememek, Yeni dependency ancak mevcut çözüm yetersizse ve gerekçesi belgelenmişse eklenebilirlik gereksinimini tespit etme ihtiyaçları

İstek şu cümleyle bitiyordu:

> önce ki prompt'larıma ve verdiğin yanıtlara ve yukarıdakilere, önerilere, sorularıma, sorunlarıma, tekrar bakarak, vibecoding odaklı, az kod ile çok iş yapmak hedefi ile, bir md dosyası yönergesi hazırla, aynı talimatları codex'e de ver, o da hazırlasın, sonra tartışıp uzlaşın, ortak bir md dosyasını birlikte hazırlayın.

Listedeki ilk madde başka bir projedeki bir uyarıdır. Proje sahibi o uyarıyı anlamamıştı. Uyarının kaynağı `SURECLER-VE-SONUCLAR.md` dosyasındadır.

Sonuç şudur. `frappe-python-standartlari.md` yazıldı. Claude ve Codex ayrı taslak yazdı. Claude iki taslağı birleştirdi. İki model üç tur tartıştı. Codex ortak dosyayı 20 Kasım 2026 Cuma akşamı onayladı.

### Karar 2. Python dosyası beş yere konacak

Claude dosyanın hangi yerlere konacağını sordu. Proje sahibi `rules ai` klasörünü gösterdi. Sonra şunu yazdı:

> ... ve hepsi

Sonuç şudur. Dosya beş yere kondu:

- ajanların ortak kural klasörü,
- `rules ai` klasörü,
- çalışma klasörü,
- iki Frappe uygulama deposu.

İki depoda dosya Git'e eklenmedi. Git, dosyaların geçmişini tutan araçtır.

### Karar 3. JSON ve YAML kuralları Python dışı dosyada olacak

Proje sahibi önce şunu istedi:

> Şimdi de aynı analizi, yaml ve json dosyalarının standardını oluşturmak için yap, python değil. JSON dosyaları bazen frontend de content için kullanıyorum, ve ayrıca Frappe backend de JSON dosyalarını kullanıyor.

Sonra kapsamı düzeltti:

> şimdi de frappe backend tarafında, python hariç, json ve yaml gibi diğer kodlama dilleri ve dosya uzantıları odaklı, standartları dökümante edeceğiz. olayın somut detayı bu.

Sonuç şudur. `frappe-python-disi-standartlari.md` yazıldı. Dosya Frappe arka ucundaki Python dışı her dosyayı kapsar. Örneğin JSON, YAML, JavaScript, şablon, CSS ve çeviri dosyaları bu kapsamdadır.

İlk deneme yanlış kapsamla yazılmıştı. O deneme arşivde durur. Ajanlar o denemeyi kullanmaz.

### Karar 4. Ayrı arayüz için kural dosyası yazılacak

Proje sahibi şunu istedi:

> sonra da headless frontend [ant design, ant-x, typescript, scss, sass, vb etc] için, standartları belirle.

Proje sahibi bu dosya için de aynı kabul ölçütlerini verdi.

Sonuç şudur. `headless-frontend-standartlari.md` yazıldı. Ayrı arayüzde içerik için kullanılan JSON dosyaları da bu dosyadadır.

## 21 Kasım 2026 Cumartesi günü

### Karar 5. Python dosyası ikinci kez düzeltilecek

Proje sahibi ilk teslim raporunu yapıştırdı. Sonra şunu sordu:

> bu çıktılar, doğru mu? kabul kritelerime ve prompt'uma […] uygun mu?

Proje sahibi arşiv isteğinde bu soruyu başlangıç noktası olarak gösterdi.

Claude raporu ve dosyayı yeniden denetledi. Bağımsız bir denetçi de dosyanın isteğe uygunluğunu denetledi. Kısaca durum şuydu:

- Raporun çoğu doğruydu. Altı nokta yanlış ya da eksikti.
- İstek 26 ihtiyaca ayrıldı. 21 ihtiyaç karşılanıyordu. 5 ihtiyaç kısmen karşılanıyordu.
- Üç önemli eksik vardı. Ayrıntı `SURECLER-VE-SONUCLAR.md` dosyasındadır.

Claude bir düzeltme turu önerdi. Python dosyasının sınırını 36.000 bayta çıkarmayı da önerdi. Proje sahibi şöyle dedi:

> Evet, düzelt

Sonuç şudur. Python dosyası düzeltildi ve 35.998 bayt oldu. Codex son hâli onayladı.

### Karar 6. Öteki iki dosya o gün ayrıca denetlenmeyecek

Claude aynı bağımsız denetimi öteki iki dosya için önerdi. Proje sahibi şöyle dedi:

> Şimdilik gerek yok

Dördüncü bağımsız denetçi sonradan dört dosyanın son metnini inceledi. Bu denetim mobil çalışmanın parçasıydı.

### Karar 7. Kural dosyaları görsel kural taşımayacak

Proje sahibi üç dosyayı 19 soruyla değerlendirdi. Claude'un cevapları `SURECLER-VE-SONUCLAR.md` dosyasındadır.

Claude dosyaların kalıcı arayüz kurallarını taşıdığını söyledi. Örneğin yazı tipi ve yazı boyutu kuralları böyleydi. Proje sahibi şöyle dedi:

> taşımasın. sadece backend kuralları bunlar.

Claude hangi kuralların çıkacağını sordu. Bu soru S1 sorusudur. Proje sahibi şöyle cevap verdi:

> burada, backend'i etkileyecek kurarllar kalsın, diğerleri çıksın

Sonuç şudur:

- Yazı tipi, yazı boyutu, odak göstergesi ve hareket kuralları çıktı.
- Vurgu kenarı, seçim kutusu ve tablo sütunu kuralları çıktı.
- Önce telefon yerleşimi ve görsel karşılaştırma kuralları da çıktı.
- Klavye erişimi, odak dönüşü ve alternatif metin kaldı. Bunlar görsel dil değildir.
- Sass ve CSS yazım kuralları kaldı. Ayrıntı Karar 18'dedir.
- Çıkan kodlar her dosyanın “Kullanımdan kalkan kodlar” satırındadır.

### Karar 8. Önce DDD planı, sonra modüler monolit, sonra düşük bağımlılık

Proje sahibi şöyle dedi:

> önce ddd plan + sonra modular monolith, + sonra low coupled,

Claude planın ne kadar ağır olacağını sordu. Bu soru S2 sorusudur. Proje sahibi şöyle cevap verdi:

> hibrit, duruma göre, görevin zorluğuna göre

Sonuç şudur. Python dosyasına B-7, B-8 ve B-9 kuralları eklendi. Kolay işte hafif plan yazılır. Zor işte tam plan yazılır. Altı durum tam plan ister. Emin olunmayan durumda da tam plan yazılır.

### Karar 9. Modül sınırı denetimi MVP ve üstünde zorunlu olacak

Proje sahibi SOLID ilkeleri için şunu sordu:

> denetleyecek bir araç var mı? ne kurmlıyız? nasıl çözeriz? çözmeli miyiz?

Claude şöyle cevap verdi:

- SOLID'i tam denetleyen bir araç yok. SOLID bir tasarım yargısıdır.
- Modül sınırını ve bağımlılık yönünü araç denetleyebilir. Örneğin Python'da `import-linter` bu işi yapar. TypeScript'te `dependency-cruiser` aynı işi yapar.
- Karmaşıklığı Ruff ve ESLint denetleyebilir. Bunlar kodu denetleyen araçlardır.
- Kalan ilkeleri bağımsız inceleme karşılar.

Claude sonra bu denetimin zorunlu olup olmayacağını sordu. Bu soru S3 sorusudur. Proje sahibi şöyle cevap verdi:

> A. Evet. MVP ve üstünde zorunlu olsun.

Sonuç şudur. Python dosyasına B-10 kuralı eklendi. Ayrı arayüz dosyasında MD-2 aynı güvenceyi verir. Denetim şu üç şeyi yakalar:

1. izinsiz modül bağını,
2. bağımlılık döngüsünü,
3. başka modülün kaydına doğrudan yazmayı.

Projede var olan denetim yolu kullanılır. Yeni araç için T-2 kuralı gerekçe ister. PoC'de eksik denetim `BORC(mvp)` diye işaretlenir. Bu araç henüz hiçbir projede kurulu değildir.

### Karar 10. Son kullanıcı yalnız ayrı arayüzü görecek

Claude şu varsayımı yazdı:

- Son kullanıcı yalnız ayrı arayüzü görür.
- Frappe'nin yönetim ekranını yalnız yöneticiler kullanır.
- E-posta ve yazdırma şablonları Frappe'de kalır.

Proje sahibi şöyle dedi:

> doğru

Sonuç şudur. Bu karar üç dosyanın girişinde yazar. Python dosyasına A-7 ve G-16 kuralları eklendi. A-7 son kullanıcıya Frappe'nin hazır portal sayfalarını kapatır. G-16 son kullanıcıya yönetim ekranı rolü verilmesini yasaklar.

### Karar 11. Enterprise seviyesinde hiçbir geçici çözüm kalmayacak

Proje sahibi bunu ilk istekte koşulsuz istemişti. Python dışı dosya bunu yalnız en önemli iş adımları için yazıyordu. Claude bu farkı anlattı. Proje sahibi açıklamanın anlaşılmadığını söyledi. Claude açıklamayı bir örnekle yeniden yazdı.

Sonuç şudur. Üç dosyada da aynı cümle yazar: “Geçici çözümlerin hepsini kapatın.”

### Karar 12. Bulunan üç eksik dosyalara işlenecek

Claude değerlendirmede üç eksik buldu:

1. Ekran kararı dosyalarda yazmıyordu.
2. Telefona kurulan uygulama için arka uç kuralı yoktu.
3. Enterprise cümlesi bir dosyada dardı.

Claude bu eksikleri dosyalara işlemeyi önerdi. Proje sahibi mesajını şöyle bitirdi:

> evet?

Claude bu cevabı onay saydı. Üç eksik dosyalara işlendi. Claude üç dosyanın sınırını 37.000 bayta çıkarmayı da önermişti. Bu öneri uygulanmadı. Sınırlar Karar 15'teki gibi belirlendi.

### Karar 13. Mobil uygulama için yeni bir kural dosyası yazılacak

Proje sahibi şöyle dedi:

> capacitor ile mobile app geliştirmek için tüm önlemler alınmalı. pwa ile mobile app geliştirmek için tüm önlemler alınmalı. yarı native (hybrit) olması belki ihtiyaç olabilir, ama mobile app geliştirmek için backend frappe olacaksa ve ffrappe app mobile olarak paketlenecekse, sadece basic pwa olmasını apple onaylamıyor, bu nedenle capacitor ile paketlenirken önlem almak gerekiyor. bundan önce frappe de alınacak önlemler gap analizi konusu un unks. ve çevrimdışı (internetin olmadığı zamanlar) mobile app yine de mobile device üzerinde açılmalı/çalışmalı. mobile için bir md dosyası hazırlamak üzere, soru setleri hazırla, yanıtlıyım, mobile.md dosyası kurallarına yazılsın

Proje sahibi dosyanın nasıl yazılacağını da söyledi:

> gemini+codex katkılarıyla, bağımsız incelemelerle, yeni dosya yaratacağız

Cevapları verdikten sonra genel bir talimat ekledi:

> ama claude codex antygraviti gemini, uzlaşmaya çalışın, tartışın, birlikte araştırıp zengin veri üretin birlikte karar verin

“antygraviti”, Gemini modellerini çalıştıran Antigravity aracıdır.

Sonuç şudur. `mobile.md` yazıldı. Claude, Codex ve Gemini on üç turda birlikte karar verdi. Dört bağımsız denetçi metni inceledi.

### Karar 14. Mobil soru setinin cevapları

Proje sahibi 20 soruyu cevapladı. Cevaplar aynen şöyledir:

| No | Soru | Cevap |
|---|---|---|
| 1 | Uygulama hangi telefonlarda çalışacak? | “A. iPhone ve Android ve huawei.” |
| 2 | Uygulamayı kim kullanacak? | “şirket çalışanları ve Müşteriler.” |
| 3 | Apple ve Google mağaza hesaplarınız var mı? | “A. İkisi de yok. […]” |
| 4 | Telefon uygulaması hangi ekran kodunu kullansın? | “A. Ayrı arayüzün aynı kodu telefona paketlensin.” |
| 5 | Uygulama telefonun hangi özelliklerini kullanacak? | “Bildirim, Kamera ve fotoğraf, Barkod ya da karekod okuma, Konum, Parmak izi ya da yüz ile giriş.” |
| 6 | Bazı ekranlar telefonun kendi diliyle yazılabilsin mi? | “A. Hayır. Yalnız hazır Capacitor eklentileri kullanılsın.” |
| 7 | İnternet yokken uygulama ne yapabilmeli? | “Her işi internet yokken de yapabilsin.” |
| 8 | İnternet yokken hangi işler yapılabilmeli? | “bununla ilgili "https://karacaismail.github.io/frappesetup/" raposunu incele. bugünkü kurallar md dosyaları bu repo'yu da etkileyecek.” |
| 9 | İki kişi aynı kaydı internet yokken değiştirirse ne olsun? | “A. Uygulama farkı göstersin ve kullanıcıya sorsun.” |
| 10 | Telefonda saklanan veri nasıl korunsun? | “telefonda sql” |
| 11 | Kullanıcı nasıl giriş yapacak? | “keyclock first, E-posta ve parola, magic linki, Google ile giriş, Apple ile giriş.” |
| 12 | Oturum ne kadar açık kalsın? | “bununla ilgili "https://karacaismail.github.io/frappesetup/" raposunu incele” |
| 13 | Kullanıcı uygulamadan kendi hesabını açabilecek mi? | 12. sorunun cevabıyla aynıdır. |
| 14 | Bildirim hangi servisle gönderilsin? | 12. sorunun cevabıyla aynıdır. |
| 15 | Güncellemeler telefona nasıl ulaşsın? | “B. Küçük ekran düzeltmeleri mağazayı beklemeden gitsin. ve bununla ilgili "https://karacaismail.github.io/frappesetup/" raposunu incele” |
| 16 | Çok eski sürümü kullanan kişi ne görsün? | “B. Eski sürüm çalışmaya devam etsin.” |
| 17 | Uygulama içinde ödeme alınacak mı? | “B. Evet, fiziksel ürün ya da hizmet için.” |
| 18 | Mobil uygulama hangi seviyede başlasın? | “A. PoC, deneme sürümü.” |
| 19 | Gerçek telefonda testi kim yapacak? | “A. Elimizde gerçek iPhone ve Android var.” |
| 20 | Uygulama hangi bilgiyi toplasın? | “B. Çökme kaydı ve kullanım ölçümü.” |

Cevaplarla ilgili notlar şunlardır:

- Proje sahibi 3. sorunun kural yazımını etkilemediğini belirtti. Benzer sorular yeniden sorulmaz.
- 15. sorunun seçeneği sonradan düzeltilmişti. Küçük ekran düzeltmesi için genel bir mağaza izni doğrulanamamıştı. Proje sahibi eski metni cevapladı.
- 21 ile 25 arasındaki sorulara cevap gelmedi. Bu soruları modeller karara bağladı.
- Site cevapları için frappesetup sitesi incelendi. Etkilenen site sayfaları `ACIK-ISLER.md` dosyasındadır.

Cevapların sonucu şudur:

- Huawei hedefi kaldı. Ayrıntı Karar 22'dedir.
- Ekran kodu tektir. Ayrı arayüzün kodu telefona paketlenir. Pakette dijital ürün satışının bütün yolları kapanır.
- Telefon özellikleri tek bir ara katmandan çağrılır. İzin, özellik kullanılırken istenir.
- Yalnız hazır eklentiler kullanılır. Eklentinin resmî kurulum satırları izinlidir. Cordova eklentisi kurulmaz.
- İşler üç sınıfa ayrıldı. Çoğu iş internet yokken biter ya da sıraya girer.
- Birkaç adım internet ister. Örneğin ilk giriş ve kart doğrulaması böyledir. Bu sınıfa iş eklemek proje sahibinin kararını ister.
- Çakışmada uygulama farkı gösterir. Kullanıcı birini seçer. Seçim yeni bir yazma sayılır.
- Pakette veri şifreli SQLite veritabanında durur. SQLite, telefonda çalışan küçük bir veritabanıdır. PWA'da SQLite, PoC aşamasında sınanır.
- Eski sürüm çalışır. Genel bir zorunlu güncelleme yoktur. Yalnız güvenlik açığında tek bir işlem durabilir.
- Fiziksel ürün ve hizmet için ödeme uygulamanın dışında alınır. Ödeme sistem tarayıcısında açılır. Sonucu sunucu doğrular.
- PoC en riskli işleri örnek veriyle kanıtlar.
- Gerçek telefon denemesini proje kaydındaki kişi yapar. Ajan gerçek telefonu kullanamaz.
- Çökme kaydı ve ölçüm projenin kendi toplayıcısına gider. Kullanım ölçümü kullanıcının onayına bağlıdır.
- Hesap açılabiliyorsa MVP ve üstünde hesap silme yolu da bulunur.
- PoC'de uygulama içi bildirim listesi kullanılır. Telefon bildirimi için Karar 16'ya bakın.

### Karar 15. Dosya sınırları belirlendi

Proje sahibi önce şunu sordu:

> 36000 bayt kaç kelimedir? kaç satırdır? insan okuyabilir mi? dünya standartlarında uygun mu?

Claude'un cevabı `SURECLER-VE-SONUCLAR.md` dosyasındadır. Kısaca 36.000 bayt yaklaşık 4.400 kelimedir.

Claude sonra iki soru sordu. Proje sahibi ikisine de olumlu cevap verdi:

| Soru | Cevap |
|---|---|
| Python dosyasının sınırı 38.000 bayt olsun mu? | “evet.” |
| Mobil dosya 36.000 bayt sınırıyla kalsın mı? | “evet” |

Sonuç şudur:

- Python dosyasının sınırı 38.000 bayttır. Bu sınır önce 36.000 bayttı.
- Mobil dosyanın sınırı 36.000 bayttır.
- Python dışı ve ayrı arayüz dosyalarının sınırı 32.768 bayttır. Bu sınırı proje sahibi koymadı. Sınırı ilk turda Claude önerdi.

### Karar 16. Telefon bildirimi dış servislerle gönderilecek

Claude telefon bildirimi için dış servislerin kullanılıp kullanılmayacağını sordu. Proje sahibi “evet” dedi.

Sonuç şudur. Apple, Google ve Huawei'nin bildirim servisleri kullanılabilir. Huawei bildirimi şimdilik eksik bir yetenektir. Huawei'nin hazır eklentisi yalnız Cordova için var. Bu servisler yurt dışındadır. Bu yüzden KVKK'nın yurt dışı aktarım kuralı onlar için de geçerlidir.

### Karar 17. Bütün giriş yolları Keycloak'ta kurulacak

Proje sahibi 11. soruya şöyle cevap vermişti:

> keyclock first, E-posta ve parola, magic linki, Google ile giriş, Apple ile giriş.

Claude sihirli bağlantı ve Apple ile girişin yolunu sordu. Proje sahibi “keycloack” dedi. Claude parmak izi ve yüzle girişi sordu. Proje sahibi “keycloack firts” dedi.

Sonuç şudur:

- Bütün giriş yolları Keycloak'ta kurulur.
- Pakette giriş sistem tarayıcısının sekmesinde açılır. PKCE yöntemi kullanılır. PKCE, giriş kodunun çalınmasını önler.
- Frappe gelen belirteci doğrular. Belirteç, girişin yapıldığını gösteren dijital anahtardır.
- Frappe'nin kendi parola ve e-posta bağlantısı girişi kapanır.
- Sihirli bağlantı ve Apple ile giriş Keycloak'ta kurulur. Eklenti gerekirse açık kaynak lisanslı olmalıdır.
- Parmak izi ve yüzle giriş Keycloak'ın passkey yöntemiyle kurulur. GR-7 kuralı buna göre değişti.
- Yerel kilit internetsiz açılış için kalır.

### Karar 18. CSS ve Sass yazım kuralları sonraya kaldı

Claude CSS ve Sass yazım kurallarının da çıkıp çıkmayacağını sordu. Proje sahibi “frontend sonra” dedi.

Modeller bu konuda uzlaşamamıştı. Codex bu kuralların çıkmasını istedi. Claude ve Gemini kalmasını savundu. Gerekçe şuydu: S1 cevabındaki kaldırma listesi bu kuralları saymıyordu.

Sonuç şudur. Kurallar şimdilik dosyalarda duruyor. Python dışı dosyada bu kurallar C-3 ve C-4'tür. Ayrı arayüz dosyasında ST-2 ile ST-7 arası ve ST-12'dir.

### Karar 19. Oturum süreleri makul olacak

Claude telefonda oturumun ne kadar açık kalacağını sordu. Proje sahibi “makul olsun” dedi.

Süreleri modeller seçti. Codex kısa süreler önerdi. Gemini uzun süreler önerdi. Claude iki öneriyi birleştirdi. Dayanak NIST SP 800-63B-4 belgesidir. NIST, ABD'nin standart kurumudur. Çalışana daha sıkı sınır uygulandı. Proje sahibinin “her iş internet yokken” kararı da dayanak oldu. Codex ve Gemini tabloyu onayladı.

| Ayar | Çalışan | Müşteri |
|---|---|---|
| Erişim belirtecinin ömrü | 5 dakika | 5 dakika |
| Yenileme belirteci | Her kullanımda değişir | Her kullanımda değişir |
| Keycloak'ta boşta kalma | 1 saat | 7 gün |
| Keycloak'ta toplam süre | 24 saat | 30 gün |
| PWA'da Frappe çerezinin boşta kalma süresi | 1 saat | 1 saat |
| Paket arka plandayken yerel kilit | 2 dakika | 5 dakika |
| Pakette bağlantısız erişim | 24 saat | 72 saat |
| PWA'da bağlantısız erişim | 8 saat | 24 saat |
| Çıkıştan sonra taslak saklama | 7 gün | 7 gün |

Tablonun uygulama notları şunlardır:

- Keycloak'ta `Revoke Refresh Token` ayarı açılır. Eski belirtecin reddedildiği sınanır.
- Boşta kalma son kullanıcı işleminden sayılır. Toplam süre son kimlik doğrulamasından sayılır.
- Arka plan yenilemesi ve eşitleme süreleri uzatmaz. Sunucu gerçek kullanıcı işlemini ayrıca sayar.
- Frappe çerez süresi sitede tek değerdir. Frappe oturumu erken biterse geçerli Keycloak oturumuyla yeniden açılır.
- Bağlantısız süre son başarılı çevrimiçi oturumdan sayılır. Yerel kilidi açmak bu süreyi yenilemez.
- Taslak yalnız kişisel telefondaki pakette saklanır. PWA'da ve ortak telefonda taslak saklanmaz.
- Uygulamanın kendi açtığı kamera ve dosya seçimi yerel kilidi başlatmaz.

Süreler kural metnine girmedi. Mobil uygulamanın proje kaydı açılınca süreler o kayda yazılmalıdır.

### Karar 20. Canlı güncelleme kendi sunucumuzdan kurulacak

Claude canlı güncelleme için hangi aracın kullanılacağını sordu. Proje sahibi şöyle cevap verdi:

> saas tabanlı olacağı için zaten saas web güncellenince otomatik güncellenir

İki model bu cevaba itiraz etti. Mağazadan kurulan uygulama web gibi kendiliğinden güncellenmez. Claude bunu proje sahibine anlattı. Sonra kendi sunucumuzdan canlı güncellemeyi sordu. Proje sahibi şöyle cevap verdi:

> kurarız

Sonuç şudur:

- Canlı güncelleme MVP ve üstünde kurulur. Bu kural GN-3'tür.
- Canlı güncelleme iPhone ve Google Play paketinde çalışır.
- Huawei paketinde canlı güncelleme kapalıdır. Huawei mağazası buna izin vermez.
- Canlı güncelleme yalnız var olan ekranın hatasını düzeltir. Yeni özellik mağaza sürümü ister. Bu kural GN-4'tür.
- Araç henüz seçilmedi. Araç GN-3 ve HZ-4 kurallarına göre seçilir.

### Karar 21. İçerik bütün platformlara yansıyacak

Proje sahibi şunu istedi:

> ben saas'dan içerik güncellediğimde tüm mobile app platformlardaki platformlara yansımalı.

Sonuç şudur:

- İçerik sunucudan gelir ve her platformda görünür. Bu kural GN-1'dir.
- Web ve PWA kendiliğinden güncellenir.
- iPhone ve Google Play paketine ekran düzeltmesi canlı güncellemeyle gider.
- Huawei paketi ekran düzeltmesi için mağaza güncellemesi ister.
- Yeni bir özellik her mağazada yeni sürüm ister. Bu, mağazaların kuralıdır.

### Karar 22. Yeni Huawei telefonlarda şimdilik tarayıcı yolu kullanılacak

Claude yeni Huawei telefonlarda tarayıcı yolunun yetip yetmeyeceğini sordu. Proje sahibi önce şöyle dedi:

> neden bahsettiğini anlamıyorum.

Claude kısa bir açıklama yazdı. Proje sahibi şunu sordu:

> bu ne demek?

Claude yeniden anlattı. Proje sahibi şunu sordu:

> huawei app store da yayınlanamıyor mu? yoksa yayınlanıyor ama iframe gibi pwa gibi mi?

Proje sahibi ayrı uygulama seçeneğine şöyle cevap verdi:

> capacitor ile paketlensin.

Proje sahibi sonra anlatımın eksik olduğunu söyledi. Her telefonun bir uygulama mağazası olduğunu hatırlattı. Claude bütün nedenleri sırayla anlattı:

1. Huawei'nin mağazasının adı AppGallery'dir.
2. Eski sistemli Huawei telefonlar Android uygulamalarını çalıştırır. Türkiye'deki güncel Huawei telefonlar bu gruptadır. Bu bilgi Huawei'nin yayınlarına dayanır.
3. Bu telefonlara Capacitor paketi Huawei mağazasından kurulur. Bu paket gerçek bir uygulamadır. Paket iframe değildir. iframe, bir sayfanın içinde açılan başka bir web sayfasıdır.
4. Yeni Huawei telefonlarda HarmonyOS NEXT sistemi çalışır. Bu telefonlar şimdilik çoğunlukla Çin'de satılıyor.
5. Bu sistemin mağazası Android uygulamasını kabul etmez. Mağaza yalnız Huawei'nin kendi araçlarıyla yazılan uygulamayı kabul eder.
6. Capacitor bu tür uygulama üretemez. Capacitor'ı geliştiren Ionic şirketi bu desteği araştırıyor.
7. Bu telefonlar için üç yol kalır. Bunlar tarayıcı yolu, resmî olmayan bir araç ve ayrı bir uygulamadır.

Proje sahibi şöyle karar verdi:

> buradan ilerleyelim şimdilik, basit olsun, ileride huawei için daha güçlü bir yol seçeriz

Sonuç şudur:

- HarmonyOS NEXT telefonlarda şimdilik tarayıcı yolu kullanılır. Kullanıcı uygulamayı tarayıcıda açar ve ana ekrana ekler.
- Tarayıcı yolu mağazada görünmez. Bu yolun bu telefonlarda çalıştığı ayrıca sınanmalıdır.
- Eski sistemli Huawei telefonlar Huawei mağazasındaki Capacitor paketini kullanır.
- Huawei için daha güçlü yol sonra seçilecek.

### Karar 23. Hedef kitle önce Türkiye olacak

Proje sahibi şöyle dedi:

> hedef kitle öncelikle türkiye, sonra global (avrupa, mena bölgesi, USA, kanada, avusturalya, en son asya)

Sonuç şudur. İlk hedef Türkiye'dir. Sonra Avrupa, Orta Doğu ve Kuzey Afrika gelir. Sonra ABD, Kanada ve Avustralya gelir. Asya en sondadır. Bu bilgi proje kaydının “Hedef ülkeler” satırına yazılmalıdır.

### Karar 24. Renk gibi tema değerleri sunucudan gelebilecek

Proje sahibi şunu sordu:

> ben uygulamayı antdesign ile UI geliştiriyorsam, web uygulaması da saas ise, ve sonunda web uygulaması güncellendiğinde, mecbur güncellenir, yani butonun rengi de değişir, yanış mı biliyorum?

Claude şöyle cevap verdi:

- Web ve PWA kendiliğinden güncellenir.
- Mağaza uygulaması yalnız canlı güncellemeyle güncellenir.
- Huawei mağazasındaki uygulama mağaza güncellemesi ister.
- Renkler sunucudan gelen tema verisiyle yönetilebilir.

Claude iki değişiklik önerdi. Birincisi, canlı güncelleme görünüş değişikliğini de taşısın. İkincisi, renkler sunucudan tema verisi olarak gelsin.

Sonuç şudur. İkinci öneri kurala girdi. AD-1 kuralı tema değerinin sunucudan veri olarak gelmesine izin verir. Gelen değer SZ-4 kuralıyla denetlenir.

Birinci öneri kurala girmedi. GN-4 hâlâ yalnız hata düzeltmesine izin veriyor. Proje sahibi bu öneriye ayrıca cevap vermedi. Konu `ACIK-ISLER.md` dosyasında açık karar olarak duruyor.

### Karar 25. SaaS'ta açılan yeni sayfa için uygulama güncellemesi gerekmeyecek

Proje sahibi şunu sordu:

> frappe arkaplanda, bir saas uygulaması, önplanda antdesign, saas uygulamasında oturum açtı (uygulamayı indiren kullanıcı), form table olarak web de yeni sayfa da yarattım, mesela hrms ile özlük ve bordro var ise, raporlar form table ile saas panelde solda menu de bir item olarak form table eklendiyse, eğer eklendiyse, o zaman: ios ve android, web'den güncellenmes mi? pwa base zaten (ama kamera erişimi vb capacitor tamamlıyor).

Claude şöyle cevap verdi. Platformun K5 kararına göre ekranlar DocType tanımından üretilir. Bu yüzden yeni sayfa telefona veri olarak gelebilir. Ama üç koşul var:

1. Sayfayı çizen kod mağazaya giden ilk sürümde bulunmalı.
2. Alan türü uygulamaya tanıdık olmalı. İmza ya da harita gibi yeni alan türü yeni kod ister.
3. Sunucu sayfayı telefona açmalı. İnternetsiz çalışma için sayfanın kayıtları indirme listesine girmeli.

Claude bir kuralın düzeltilmesini de önerdi. Mobil dosyadaki bir cümle yeni sayfayı da yasaklıyordu. Cümle şuydu: “İçerikle ya da bayrakla yeni özellik açmayın.”

Claude ayrıca bir yanlışı düzeltti. Mağaza uygulaması PWA'yı açan bir kabuk değildir. Ekran kodunun bir kopyası uygulamanın içinde durur.

Proje sahibi şöyle karar verdi:

> koşulları karşılayan güncellemeyi kurallara işle

Proje sahibi şunu da istedi:

> tüm frontend component gereksinimlerini, önceden karşılamalı, sonradan harita da eklenebilir, başka şeylerde eklenebilir, yine de eklenen sayfa componentlerinin farklılığından ötürü ios android uygulama güncellemek gerekmez. böyle olmalı.

Sonuç şudur. Codex ve Gemini üç turda metni onayladı. Son kurallar şunlardır:

- **RE-11.** Sunucu sayfa tanımını DocType tanımından üretir. Tanım kod ve yetki taşımaz. Yüksek gizlilik işareti tanımda gelir. Sayfa onaylı bileşen kataloğundan çizilir. Çizim kodu ve eklentiler ilk mağaza paketine girer. Sunucu telefona yalnız izin listesindeki sayfaları açar. İnternetsiz açılacak sayfanın tanımı ve kayıtları önceden eşitlenir. Katalogda olmayan bileşen ya da alan türü mağaza sürümü ister.
- **AD-1.** Tema değeri sunucudan veri olarak gelebilir.
- **GN-1.** Tanım ve kayıt sabit yerel şemada saklanır. Sunucu indirilecek kayıtların listesini sözleşmeyle gönderir. Gizli özellik konmaz. Eski sözleşmeye zorunlu alan eklenmez.
- **PK-3 ve MG-1.** Katalogdaki eklentiler baştan pakete girer. Mağaza inceleme notu her yeni işlevi ayrı yazar.

Bileşen kataloğu, uygulamanın çizebildiği ekran parçalarının listesidir. Örneğin form, tablo, rapor, grafik, harita, imza ve dosya bu listededir. Katalogdaki parça yeni bir sayfada kullanılınca mağaza güncellemesi gerekmez. Katalogda hiç olmayan yeni bir parça türü yine mağaza sürümü ister. Bu, mağazaların kuralıdır.

### Karar 26. Üyelik, sözleşme ve KVKK uyumu belgelenecek

Claude bordro gibi gizli verilerin nasıl korunduğunu anlattı. Proje sahibi şunu istedi:

> üyeli kadımları sürecinde kabul edilmesi gereken sözleşmelerle, kyb, kyc süreçleri, ve başka unk unks ne varsa, gap analizi yaparak ne bulabiliyorsan, önceden kullanıcı iznini zorunlu tutarak, izinleri alarak, bu engeli ortadan kaldırmanın yolunu bulup, geliştirme yönergelerine, dökğümante etmelisin. yasal çerçevede. kvkk ve gpdr koşullarına ugyun olmalı

KYB şirketin kimliğini doğrulama sürecidir. KYC kişinin kimliğini doğrulama sürecidir.

Sonuç şudur. İki Claude araştırmacısı ve Codex ayrı ayrı araştırma yaptı. Üçü ana noktalarda aynı sonuca vardı:

1. Herkesten baştan izin almak engeli kaldırmaz. Zorla alınan izin geçersizdir.
2. Kurul 18 Şubat 2026 Çarşamba günü bir ilke kararı aldı. Karar 24 Mart 2026 Salı günü Resmî Gazete'de yayımlandı. Başka bir dayanak varsa açık rıza metni sunulmaz. Kullanıcıdan yalnız “okudum” bilgisi alınır.
3. Bordro bir izin konusu değil, bir güvenlik konusudur. Bordronun dayanağı iş sözleşmesi ve İş Kanunu'dur.
4. Engeli kaldırmanın yolu üç adımdır. Kiracı şirket özelliği açar. Çalışan kendi telefonunda seçeneği açar. Veri şifreli tutulur.
5. KYB ve KYC çoğu durumda zorunlu değildir. Kiracı kendi iyzico hesabını kullanırsa doğrulamayı iyzico yapar.
6. En büyük risk sunucunun yeridir. Ayrıntı Karar 27'dedir.

Yeni dosyanın adı `veri-koruma-ve-uyum-standartlari.md` olacak. Dosyanın durumu `ACIK-ISLER.md` dosyasındadır. Bu bir hukuki görüş değildir. Son metni bir avukat onaylamalıdır.

Proje sahibi bu işi sonra durdurdu. Ayrıntı Karar 31'dedir.

### Karar 27. Bütün veriler Hetzner'de duracak

Claude Türk kiracıların verisinin nerede duracağını sordu. Proje sahibi şöyle cevap verdi:

> tüm veriler hetzner de. olacak.

Hetzner, Almanya merkezli bir sunucu şirketidir. Bu kararın yasal sonucu şudur:

1. Türkiye'deki kişinin verisi Hetzner'e gidince yurt dışına aktarılmış sayılır. Bu aktarım düzenlidir.
2. KVKK'nın 9. maddesi bu aktarım için uygun bir güvence ister. Açık rıza yalnız ara sıra yapılan aktarımda geçerlidir.
3. Olağan güvence Kurulun standart sözleşmesidir. Sözleşmeyi iki taraf imzalar. Metin değiştirilmez.
4. İmzadan sonraki 5 iş günü içinde Kuruma bildirim yapılır.
5. Bildirim yapılmazsa 50.000 TL ile 1.000.000 TL arası para cezası vardır.
6. Hetzner'in belgesine göre Hetzner kişiye özel sözleşme imzalamaz. KVKK sözleşmesini imzalayıp imzalamayacağı doğrulanmadı.

Claude şu adımları önerdi:

1. Şirket Hetzner'e resmî olarak sorar. Soru şudur: “KVKK standart sözleşmesini imzalar mısınız?” Teknik ayrıntıyı DevOps sorumlusu konuşabilir.
2. Bir avukat öteki güvenceleri değerlendirir. Örneğin Kurul izinli taahhütnameyi değerlendirir.
3. Güvence kurulana kadar Türkiye'deki gerçek kişilerin verisi Hetzner'e konmaz. Geliştirme ve PoC örnek veriyle yürür.
4. AB kullanıcılarının verisi Hetzner'in AB'deki veri merkezlerinde durur.

Bildirim servisleri de ayrı yurt dışı alıcılarıdır. Google ve Apple ile giriş ve e-posta sağlayıcısı da öyledir. Bunlar için de aktarım güvencesi gerekir.

frappesetup sitesindeki K3 kararı da bu konuya değinir. K3 notuna göre Hetzner'in AB'de olması KVKK aktarım şartını tek başına karşılamaz.

### Karar 28. Platform genel bir SaaS çerçevesidir

Claude kiracıların mağazasının nasıl çalışacağını sordu. Seçenekler kiracının kendi mağazası ve ortak bir pazaryeriydi. Proje sahibi şöyle cevap verdi:

> ne demek istediğini anlamıyorum. multi-tenancy altyapılı yazılım olacak. ama n11 gibi bir pazaryeri planı değil bu. genel saas çerçevesi. hrms vb sadece örnek. bu aslında drupal gibi bir cms. bu cms ile hrms de yapılabilir, trendyol gibi birşey de yapılabilir. yada kişisel bir single-tenancy kişisel yazılım da yapılabilir.

Çok kiracılı yazılımı birçok şirket aynı anda kullanır. Her şirketin verisi ayrı durur.

Sonuç şudur:

1. Uyum dosyası belirli bir ürünü değil, genel çerçeveyi anlatır.
2. Ürün türüne bağlı kurallar koşullu etiket taşır. Örneğin pazaryeri, tüketiciye satış, çalışan verisi ve AB kullanıcısı birer koşuldur.
3. Her ürünün proje kaydı ürün türünü, kiracı yapısını, rolleri ve satış modelini yazar.
4. Önceki üç soru her ürün için ayrı sorulur. Bunlar mağaza modeli, kiracı türü ve internetsiz bordro denemesidir.

### Karar 29. Düzenli silme için şimdilik cron kurulmayacak

Claude süresi dolan veriyi silmek için cron kurulup kurulmayacağını sordu. Proje sahibi “Şimdilik hayır” dedi.

Sonuç şudur:

- Yasa süresi dolan verinin düzenli silinmesini ister. Bu yüzden silme kuralı belgede kalır.
- Silmeyi elle başlatılan bir iş yapar.
- İşi kimin ve hangi sıklıkla başlatacağı proje kaydına yazılır.
- Her silmenin tarihi ve kapsamı kaydedilir.
- Hiçbir ajan zamanlanmış iş kurmaz.

Claude PWA'da gizli veri konusunda karar beklemedi. Kurallar bu veriyi PWA'da telefona yazdırmaz. Bu seçenek daha güvenlidir.

### Karar 30. Kararlar arşivlenecek

Proje sahibi şunu istedi:

> çok şey konuştuk, "[…]rules ai" dizinine kararları, sonuçları, süreçleri, eklememiz gereken yeni md dosyaları, yönergeleri, herşeyi kaydet, bu thread'ı arşivliycem. atıl data kalmasın

Claude önce bütün çalışma dosyalarını kopyalamaya başladı. Proje sahibi bunu durdurdu:

> 1200+ dosyayı o klasöre kaydetme. sadece birkaç md karar dosyası belki. eksik karar kalmasın. eksik karar kalmasın o kadar.

Proje sahibi sonra frappesetup deposunu da ekledi:

> şimdi frappesetup ve […] dizinine kararları, sonuçları, süreçleri, eklememiz gereken yeni md dosyaları, yönergeleri, herşeyi kaydet, bu thread'ı arşivliycem. atıl data kalmasın istiyorum.

Sonuç şudur:

- Toplu kopya çöp kutusuna taşındı.
- Bu üç karar dosyası yazıldı.
- Dört kural dosyası ve üç karar dosyası frappesetup deposuna da kondu. Depodaki yer `docs/standartlar/` klasörüdür.
- Çalışma dosyaları kendi klasöründe kaldı. Bu klasör herkese açık değildir.

### Karar 31. Uyum çalışması şimdilik durdu

Claude uyum belgesini bitirmek için ayrı bir oturum önerdi. Proje sahibi işin bu konuşmada yapılmasını seçti. Claude Codex, Gemini ve bir denetçiyle incelemeyi başlattı. Proje sahibi sonra şunu yazdı:

> gpdr kvkk şuan değil. benim şuan ki ihtiyacım bu değil. bunu ben hiç istemedim. sen önerdin.

Sonuç şudur:

- Üç inceleme hemen durduruldu. Yarım kalan çıktılar çöp kutusuna taşındı.
- Uyum taslağı ve araştırmalar çalışma klasöründe kaldı. Taslak yerine konmadı.
- Kural dosyaları değişmedi.
- İş yalnız proje sahibi isterse yeniden başlar. Ajan bu işi kendiliğinden önermez.

Karar 26'daki istek kayıtta aynen kalıyor. Proje sahibinin son sözü işi şimdilik durdurur.

## 22 Kasım 2026 Pazar günü

### Karar 32. Backend geliştirmesi Pane ile başlayacak

Proje sahibi şunu istedi:

> "frappe setup" projesini, geliştirmeye başla. tamamen pane ile, paralel agents ile, geliştir. sadece backend'i geliştir.

Sonuç şudur:

- Backend kodu yazılmaya başlandı. Ön yüz bu turda yoktur.
- İşler Pane'de paralel yürür. Her iş kendi Pane'inde ve kendi dalında durur.
- Pane oturumunun adı “frappesetup backend MVP” oldu.
- İşçiler Claude ve Codex hesaplarıdır. Claude'un bu oturumu işleri yönetir.

### Karar 33. Giriş Keycloak ile ve ayrı bir markayla olacak

Proje sahibi şunu istedi:

> giriş yöntemi keycloack olacak. keycloack ayrı bir domain'de barındırılacak. "facebook ile oturum aç" özelliği gibi "xxx ile oturum aç" gibi bir (ayrı) markası olacak (keycloack yeniden markalanacak).

Claude markanın adını sordu. Proje sahibi şöyle cevap verdi:

> atonota.net

Sonuç şudur:

- Kimlik markası Atonota'dır. Düğme metni “Atonota ile oturum aç” olur.
- Claude adı alan adından türetti. Proje sahibi adın yazımını ayrıca onaylamadı.
- Keycloak atonota.net alan adında, platformdan ayrı durur.
- Tam sunucu adı açık karardır. Örneğin ad `atonota.net` ya da `id.atonota.net` olabilir.
- Marka adı ve alan adı koda sabit yazılmaz. İkisi de ayardan gelir.

### Karar 34. Backend'in seviyesi, yeri ve kapsamı belirlendi

Claude dört soruyu tek kartta sordu. Proje sahibinin seçtiği seçenekler şunlardır:

| Soru | Seçilen seçenek |
|---|---|
| Platform hangi olgunluk seviyesinde başlasın? | “MVP, ilk kullanılabilir sürüm” |
| Backend kodu nerede ve hangi lisansla dursun? | “frappesetup deposunun içinde” |
| İlk turda hangi parçalar yapılsın? | “Bunlar ve Press (press_tr)” |
| “xxx ile oturum aç” markasının adı ne olsun? | “Adı şimdi yazacağım” |

Claude MVP'yi önermemişti. Claude PoC'yi önermişti. Proje sahibi MVP'yi seçti.

Sonuç şudur:

- Seviye MVP'dir. Modül sınırı denetimi ve sözleşmeler baştan zorunludur.
- Kod frappesetup deposunun `backend/` klasöründe durur. Kodun lisansı deponun kod lisansıdır, yani MIT'dir.
- Çalışma dalının adı `backend` oldu. Dal `standartlar-ve-kararlar` dalından açıldı.
- İlk tur şu işleri kapsar: geliştirme ortamı, Keycloak realm'i ve Atonota markası, `platform_core` içinde giriş ve ekran verisi uçları, kullanıcı eşitleme servisi ve `press_tr` içinde Press girişi.
- Ayrıntılı kayıt `backend/PROJE-KAYDI.md` dosyasındadır. Açık kararlar ve çelişkiler de oradadır.

### Karar 35. Bütün uygulamalar Frappe 16 ile yazılacak

İşçiler çalışırken proje sahibi şunu yazdı:

> zaten frappe press kurulmuştu  (sanırım collima altında bilgisayarda)
> ve app frappe v16.x ile koldlansın

Claude var olan kurulumu yalnız okudu. Kurulum Colima'nın varsayılan profilinde çalışıyor. Sürümler şunlardır:

| Uygulama | Sürüm |
|---|---|
| Frappe | v16.50.0 |
| ERPNext | v16.50.0 |
| Press | v0.154.1 |
| Python | 3.14.8 |
| MariaDB | 11.8 |

Sonuç şudur:

- `platform_core` ve `press_tr` Frappe 16 ile yazılır.
- Var olan Press kurulumu değiştirilmez. Onun imajı ve kurulum betikleri yeniden kullanılır.
- Bu karar sitedeki K1 kararını değiştirir. K1, Press'i Frappe 15 üzerinde kurar.
- Kurulumun kendi notuna göre Press bu sürümde yalnız yamalarla açılır. Sunucu kurma ve Ansible çalışmaz.
- Üretimde Press'in hangi sürümle çalışacağı ayrı karardır. Konu `backend/PROJE-KAYDI.md` dosyasında A-11 maddesidir.

### Karar 36. Her şey yapay zekâyla yönetilebilir olacak

Proje sahibi şunu istedi:

> bütün doctypes, bütün fields, db, backend, her bir zerresi, tamamen, ai il eetkileşime girebilir altyapıda geliştirilmesi. ai heryerde olmalı, ai provider'dan bağımsız, herşey ai ile yönetilebilmeli.

Proje sahibi sonra sitedeki AI bölümünü gösterdi:

> https://karacaismail.github.io/frappesetup/ai-bakis/
>
> şurada da ayrıca yönergeler var

Sonuç şudur:

- `platform_core` içinde bir yapay zekâ erişim katmanı kurulur. Modülün adı `yapay_zeka` olur.
- Araçlar DocType tanımından çalışma anında üretilir. Böylece yeni DocType için ayrı kod gerekmez.
- Yapay zekâ kullanıcının kimliğiyle ve aynı yetkiyle çalışır.
- Dış arayüz MCP ve OpenAPI olur. Frappe uygulamalarında model sağlayıcısı kitaplığı ve model adı yoktur.
- Sitenin AI bölümündeki kurallar geçerlidir. Örneğin her yazma insan onaylıdır. Gizli alan hiç okunmaz.
- Veritabanına ham SQL aracı açılmaz. Veritabanı DocType katmanından açılır. Bu kural standartların G-5 ve G-10 kurallarından gelir.
- Sitenin K9 kararı Claude Agent SDK'yı ve Claude modellerini adıyla seçer. Bu karar sağlayıcıdan bağımsızlıkla çelişir. Konu `backend/PROJE-KAYDI.md` dosyasında A-12 maddesidir.

### Karar 37. Kararlar Claude'a bırakıldı

Claude açık kalan kararları listeledi. Proje sahibi şöyle cevap verdi:

> Herşeyi onaylıyorum ve izin veriyorum, karar ver soru sorma

Sonuç şudur. Claude açık kararları kapattı. Kararların tam listesi `backend/PROJE-KAYDI.md` dosyasının “Orkestratörün kararları” bölümündedir. Özeti şudur:

| Konu | Karar |
|---|---|
| Keycloak'ın sunucu adı | `id.atonota.net` |
| Giriş teması | Keycloak'ın kendi tema yapısı. Keycloakify sonra yeniden değerlendirilir. |
| Sihirli bağlantı ve Apple ile giriş | MVP'ye girer. Eklentinin lisansı Apache-2.0 ya da MIT olur. |
| `press_tr` lisansı | AGPL-3.0. Press AGPL-3.0'dır. Hukuk görüşü alınmadı. |
| Press'in üretim sürümü | Frappe 16. Sunucu kurma akışı çalışmadan üretime çıkılmaz. |
| Model sağlayıcısı | Ajan servisi sağlayıcıdan bağımsızdır. Claude sağlayıcılardan biridir. |
| Press dağıtımı | Her uygulama dağıtımda ayrı depoya bölünür. |

İşçiler de artık proje sahibine soru sormaz. İşçi en güvenli ve en yalın seçeneği seçer ve kararı yazar. Claude kararları birleştirmede inceler.

Şu sınırlar değişmedi:

- Gerçek kişi verisi güvence kurulmadan Hetzner'e konmaz (Karar 27).
- Sunucu, DNS, yasal kutu ve ödeme hesabı işleri insanda kalır.
- Bu turda push, pull request ve canlıya yükleme yapılmaz.

### Karar 38. Altyapı yapay zekâ tabanlı ve çok sağlayıcılı olacak

Proje sahibi şunu istedi:

> bütün doctypes, bütün fields, db, backend, her bir zerresi, tamamen, ai ile etkileşime girmelidir, ai tabanlı altyapı geliştirilmesi şarttır. ai heryerde olmalı, ai provider'dan bağımsız, herşey ai ile yönetilebilmeli.  birden fazla (n tane) ai provider eklenebilmeli, birden fazla (n tane)  her hangi bir provider'dan, ai account eklenebilmeli, n tane api eklenebilmeli. birden fazla (n tane)  her hangi bir provider'dan, ai api eklenebilmeli, n tane api eklenebilmeli.

Sonuç şudur:

- `platform_core` içinde ikinci bir yapay zekâ modülü kurulur. Modülün adı `model_gecidi` olur.
- Modül sağlayıcıları, hesapları, API'leri ve modelleri kayıtta tutar. Her birinden n tane eklenebilir.
- Model çağrısı tek bir geçitten geçer. Geçit sağlayıcıya düz HTTP ile bağlanır. Sağlayıcı kitaplığı kullanılmaz.
- Geçit sırayla dener. Bir API sınıra takılırsa sıradaki API ya da hesap kullanılır.
- Gizli anahtar şifreli durur. Hiçbir uç ve hiçbir yapay zekâ aracı anahtarı dönmez.
- Her kiracı kendi sağlayıcılarını ekleyebilir. Platformun ortak hesapları sonraki turdadır.
- Sağlık denetimi zamanlanmaz. Sağlık gerçek çağrıların sonucundan çıkar.
- Ayrıntı `backend/docs/sozlesmeler.md` dosyasının 11. bölümündedir.

## Modellerin kararları

Proje sahibi bu konuları cevapsız bıraktı ya da modellere bıraktı. Proje sahibi bu kararları değiştirebilir.

### Cevapsız kalan beş mobil soru

| Soru | Karar | Kurallar |
|---|---|---|
| 21. PWA ile paket arasındaki fark | İki kanal aynı işleri sunar. Güvence düzeyi farklıdır. Kullanıcı bu farkı görür. | VR-8, VR-9, ES-14 |
| 22. Gönderilmemiş kayıt varken çıkış | Erteleme ve silme sunulur. Ağ varsa gönderme de sunulur. Saklama yalnız kişisel telefondaki pakettedir. Kayıt sormadan silinmez. | CK-1 ile CK-3 |
| 23. Telefonun sahibi | Telefon türü proje kaydından gelir. Kayıtta yoksa ajan sorar. Paylaşılan telefonda çıkıştan sonra taslak kalmaz. | CK-3, VR-5, Ek A |
| 24. Eski verinin kabul süresi | Süre iş türüne göre proje kaydından gelir. | ES-11 |
| 25. Birden çok şirket ya da site | Kural tek siteyle de çok siteyle de çalışır. | CK-9, VR-5 |

### Öteki kararlar

- **Kullanım ölçümü.** Kullanım ölçümü kullanıcının onayına bağlandı. Bu karar kişisel veriyi korur.
- **PWA'da saklama.** PWA belirteci, ödeme verisini ve yüksek gizlilikli alanı saklamaz. Bu kurallar VR-8 ve VR-9'dur.
- **Sosyal giriş.** Frappe'nin hazır sosyal girişi kullanıcıyı e-postayla bulur. Bu yüzden ilk bağ yalnız doğrulanmış e-postayla kurulur. Bağ Frappe'nin `social_logins` tablosunun dışında tutulur. Farklı bir bağ reddedilir. Gerekirse kendi dönüş ucu yazılır. Bu kural AU-4'tür.
- **Parola girişinin kapanması.** Frappe'nin parola girişi, yöneticilerin girişi de çalışınca kapanır. Bu kural AU-19'dur.
- **Zamanlanmış iş.** Mobil dosya Python dosyasındaki V-9 kuralını uygular. V-9 proje sahibinin açık “cron” isteğini ister.
- **Kodların numarası.** Kural kodları yeniden numaralanmaz. Çıkan kod “Kullanımdan kalkan kodlar” satırına yazılır.
- **Proje kaydı şablonu.** Mobil dosyanın proje kaydı şablonu 23 satırdır. Şablon Ek A bölümündedir.
- **Uyum taslağının seçimleri.** Taslak altı konuda daha güvenli yolu seçti. Bu seçimler onaylanmadı. İş durduğu için seçimler beklemededir. Liste `ACIK-ISLER.md` dosyasındadır.

### Ayrı arayüz dosyasındaki üç varsayılan

Claude ve Codex bu üç kuralı birlikte seçti. Proje sahibi isterse değiştirebilir.

| Konu | Seçilen kural |
|---|---|
| Ajan bir kuralı uygulayamazsa ne yapar? | Konu güvenlik, veri doğruluğu, erişilebilirlik ya da testse ajan o işi durdurur ve sorar. Ajan kalan güvenli işi sürdürür. |
| Gelen veriyi denetlemek için yeni paket şart mı? | Şart değil. Elle yazılmış denetim de yeterlidir. |
| Sunucu sözleşmesi hangi aşamada zorunlu? | MVP'den başlayarak zorunludur. PoC'de zorunlu değildir. |

## Denetim notu

- Tırnak içindeki alıntılar proje sahibinin kendi sözleridir. Alıntılar değiştirilmedi.
- Ortak yazım politikası aynen korunacak alıntının değiştirilmesini yasaklar.
- Bu yüzden alıntılardaki uzun cümle uyarıları düzeltilmedi. Denetimdeki iki noktalı virgül hatası da alıntıların içindedir.
- Alıntı dışındaki cümleler denetimden uyarısız geçti.
- Dosya gerçek okurla denenmedi.
