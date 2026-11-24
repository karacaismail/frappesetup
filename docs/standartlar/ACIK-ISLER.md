# Açık işler

Bu dosya bekleyen kararları ve bitmemiş işleri toplar. Tarih 21 Kasım 2026 Cumartesi günüdür.

Kararlar `KARARLAR.md` dosyasındadır. Yapılan denetimler `SURECLER-VE-SONUCLAR.md` dosyasındadır.

## Proje sahibini bekleyen kararlar

1. **Hetzner sözleşmesi.** Şirket Hetzner'e resmî olarak sormalı. Soru şudur: “KVKK standart sözleşmesini imzalar mısınız?” Teknik ayrıntıyı DevOps sorumlusu konuşabilir. Cevap gelene kadar Türkiye'deki gerçek kişilerin verisi Hetzner'e konmaz.
2. **Avukat.** Aydınlatma metni ve sözleşmeler canlıya çıkmadan önce avukat onayı ister. Avukatı proje sahibi seçer.
3. **Canlı güncellemede görünüş değişikliği.** GN-4 bugün yalnız hata düzeltmesine izin veriyor. Claude görünüş değişikliğinin de taşınmasını önerdi. Proje sahibi bu öneriye cevap vermedi. Renk ve tema değerleri ise sunucudan veri olarak gelebilir.
4. **Frappe yönetim ekranı.** Frappe'nin hazır görünümü kalıcı arayüz kurallarıyla çatışıyor. Örneğin hazır yazı boyutları 11, 12 ve 13 pikseldir. Soru şudur: Bu kurallar yönetim ekranında da uygulansın mı?
5. **DocType tanım dosyaları.** İki uygulamadaki tanım dosyalarının çoğu Frappe'nin kendi biçiminde değil. Soru şudur: Tanımları ajan elle mi yazsın, Frappe mi üretsin?
6. **Arayüz projeleri.** Üç kural dosyası yedi arayüz projesine konsun mu? Claude bunu önerdi. Cevap gelmedi.
7. **İki Frappe deposu.** Python ve Python dışı dosya iki depoda izlenmeyen dosya olarak duruyor. Soru şudur: Dosyalar Git'e eklensin mi?
8. **Canlı güncelleme aracı.** Araç henüz seçilmedi. Araştırmadaki aday `@capgo/capacitor-updater` eklentisidir. Eklentinin lisansı MPL-2.0'dır. Eklenti kendi sunucumuzda çalışabilir. Sunucu tarafının bir bölümünü ekip yazar.
9. **frappesetup sayfaları.** Sitenin karar sayfaları yeni kararlarla güncellensin mi? Ayrıntı aşağıdaki bölümdedir.

Karar gelene kadar ajan 4. ve 5. maddedeki çatışmayı raporlar. Ajan bu çatışmaları kendiliğinden düzeltmez.

KVKK ve GDPR uyum çalışması şimdilik durdu. Yine de 1. ve 2. madde listede kalıyor. Bu iki madde yasal bir risktir. Örneğin gerçek kişisel veri güvence kurulmadan Hetzner'e konmaz.

## Ürün başına sorulacak sorular

Platform genel bir çerçevedir. Bu yüzden şu sorular her ürün için ayrı sorulur:

1. **Mağaza modeli.** Kiracıların mağazası nasıl çalışsın? Öneri, her kiracının kendi mağazası ve kendi iyzico hesabıdır. Böylece platform para akışına girmez. Ortak pazaryeri satıcı doğrulaması ve ek bildirimler getirir.
2. **Kiracı türü.** Kiracılar yalnız şirketler mi olsun? Öneri evettir. Kişiler de kiracı olursa tüketici kuralları da uygulanır.
3. **İnternetsiz bordro.** İnternetsiz bordro denemesi yapılsın mı? Öneri küçük bir denemedir.

İnternetsiz bordro denemesinin önerilen koşulları şunlardır:

- Kiracı şirket özelliği risk değerlendirmesiyle açar. Özellik baştan kapalıdır.
- Çalışan seçeneği telefonda kendisi açar. Bu bir izin değil, kullanıcı seçimidir.
- Uyum taslağına göre ilk aşamada yalnız şirketin verdiği telefon kullanılır.
- Yalnız çalışanın kendi bordrosu telefona iner.
- Bordro yalnız okunur.
- Sendika ve engellilik gibi satırlar telefona inmez.
- Veri şifreli tutulur. Anahtar ayrı saklanır.
- Özellik yalnız mağaza uygulamasında olur. PWA'da bordro saklanmaz.

## Sonraya bırakılan kararlar

- **CSS ve Sass yazım kuralları.** Proje sahibi “frontend sonra” dedi. Kurallar şimdilik dosyalarda duruyor.
- **Huawei için güçlü yol.** Proje sahibi bu yolu sonra seçecek.
- **AB temsilcisi.** Avrupa'ya açılınca AB içinde bir temsilci gerekir.
- **Yaş sınırı.** Müşteri hesabı için bir yaş sınırı gerekir. Öneri 18 yaştır.
- **Elektronik imza.** İK'daki bazı onaylar elektronik imza isteyebilir. Örneğin fazla çalışma onayı böyledir.
- **Düzenli silme için cron.** Proje sahibi “Şimdilik hayır” dedi. Silme şimdilik elle başlatılır.

## Yazılması gereken yeni dosyalar

### 1. Veri koruma ve uyum dosyası

**Bu iş şimdilik durdu.** Proje sahibi 21 Kasım 2026 Cumartesi gecesi işi durdurdu. Ayrıntı `KARARLAR.md` dosyasındaki Karar 31'dedir. İş yalnız proje sahibi isterse yeniden başlar. Aşağıdaki bilgiler o gün için saklanıyor.

Dosyanın adı `veri-koruma-ve-uyum-standartlari.md` olacak. Kodları `UY` harfleriyle başlıyor. Hedef sınır 32.768 bayttır. Codex 32.000 bayt önerdi. Sınırı proje sahibi seçer.

İlk taslak 21 Kasım 2026 Cumartesi akşamı yazıldı. Taslağı Claude'un bir yardımcısı yazdı. Taslağın durumu şudur:

- Taslak 32.708 bayttır. Taslakta 58 kural var. Kuralların 23'ü bir koşula bağlıdır.
- Yapı denetimi hata bulmadı. Türkçe denetimi de hata bulmadı.
- Üç araştırmanın karşılaştırma notu da yazıldı. Notta 49 konu karşılaştırıldı.
- Taslak Codex'e ve Gemini'ye henüz gitmedi. Taslak henüz yerine konmadı.

İş yeniden başlarsa adımlar şunlardır:

1. Taslağı Codex'e ve Gemini'ye inceletin.
2. Son metni bağımsız bir denetçiye denetletin.
3. Açık soruları proje sahibine sorun.
4. Son metni bir avukata onaylatın.
5. Dosyayı öteki dört dosyanın yanına koyun.
6. Ortak kural rehberine bir işaret ekleyin.
7. Üç dosyaya kısa bir gönderme ekleyin.

Göndermenin yerleri mobil dosyada VR-8, ayrı arayüz dosyasında GV-4 ve Python dosyasında G-15'tir. Python dosyasında boş yer yok. Mobil dosyada 11 bayt boş yer var. Bu yüzden ya yer açılmalı ya da sınır artırılmalı. Sınır artışı proje sahibinin kararını ister.

Araştırmanın öteki bulguları şunlardır. Taslak bunları da kapsamalıdır:

- Çalışanın verdiği izin zayıftır. Çalışan işverene karşı tam özgür sayılmaz.
- Platform, kiracının verisinde veri işleyendir. Bunun için kiracıyla veri işleme sözleşmesi gerekir.
- Platform kendi amaçları için kullandığı veride veri sorumlusudur.
- Ticari ileti onayı İYS'ye kaydedilmelidir. İYS, ileti onaylarının ulusal kayıt sistemidir. Kayıtsız onay geçersizdir.
- VERBİS kaydı Kurulun eşiklerine bağlıdır. VERBİS, veri sorumlularının ulusal kayıt sistemidir.
- 7545 sayılı Siber Güvenlik Kanunu bildirim yükü getirebilir.
- 5651 sayılı kanun yer sağlayıcıya yük getirir.
- Mesafeli satışta ön bilgilendirme formu gerekir. Cayma süresi 14 gündür. Kayıtlar 3 yıl saklanır.
- Pazaryeri ürünü satıcı doğrulaması, ETBİS, MASAK ve DSA yükleri getirir.
- Avrupa'ya açılınca GDPR'nin 27. maddesine göre AB temsilcisi gerekir.
- Kimlik taşıyan çökme kaydı izin gerektirebilir.
- Yurt dışındaki her alıcı için aktarım güvencesi gerekir. Örneğin bildirim, giriş ve e-posta servisleri böyledir.

Bu bulgular hukuki görüş değildir. Son metni bir avukat onaylamalıdır.

#### Taslağın seçtiği güvenli yollar

Araştırmalar altı konuda ayrıştı. Taslak her konuda daha güvenli yolu seçti. Bu seçimler henüz onaylanmadı:

1. PWA ilk aşamada yüksek gizlilikli verinin kalıcı kopyasını tutmaz. PRF yolu proje kararı ve gerçek telefonda sınama ister. PRF, passkey'den şifre anahtarı üreten tarayıcı özelliğidir. Kurallar UY-31 ve UY-32'dir.
2. Yüksek gizlilikli veri için bağlantısız süre en çok 8 saattir. Proje kararı bu süreyi değiştirebilir. Süre çalışanın 24 saatlik genel süresini aşamaz. Kural UY-29'dur.
3. Çalışan verisi ilk aşamada yalnız şirketin kişiye verdiği telefonda açılır. Kişisel telefon proje kararı ister. Ortak telefonda bu özellik hiç açılmaz. Kurallar UY-24 ve UY-25'tir.
4. Kullanım ölçümü açık rızaya bağlıdır. Bu kural Türkiye'de de geçerlidir. Kural UY-36'dır.
5. Ayrıntılı çökme raporu ayrı bir onaya bağlıdır. Onaysız sinyal yalnız proje kararı ve hukukçu onayıyla açılır. Kural UY-36'dır.
6. Proje kararı yoksa müşterinin en düşük yaşı 18'dir. Kural UY-19'dur.

#### Uyum için açık sorular

Taslak 42 açık soru çıkardı. Bu sorular iş yeniden başlarsa sorulur. Sorular proje sahibinin ya da avukatın kararını ister. Bazı sorular bu dosyanın başındaki listede de geçer. Numaralar karşılaştırma notundaki numaralardır.

Veri yeri ve aktarım ile ilgili sorular şunlardır:

1. Hetzner ile standart sözleşmeyi kim imzalayacak? Kuruma bildirimi kim yapacak?
2. Hetzner sözleşmeyi imzalamazsa ne yapılacak?
3. Bildirim, e-posta, giriş ve destek servisleri için aktarım aracı ne olacak?
4. Hangi alt işleyenlere izin verilecek? Veriye kim erişecek?
5. Platform hangi işlerde veri sorumlusu olacak?

Alt işleyen, platform adına veriyi işleyen başka bir şirkettir.

Şirket yapısı ile ilgili sorular şunlardır:

6. Platformun AB'de şirketi var mı? Yoksa AB temsilcisi kim olacak?
7. Platform işletmecisi mikro ya da küçük işletme mi?

Ürün ve satış ile ilgili sorular şunlardır:

8. Her ürünün iş modeli ne olacak? Satıcı kim olacak?
9. Platform satışta altyapı sağlayıcı mı, aracı mı olacak?
10. Kiracıya mağaza kuran ürün ETBİS yükü doğurur mu?
11. Ödeme modeli ne olacak?
12. Tüketici kiracı kabul edilecek mi?

Telefondaki gizli veri ile ilgili sorular şunlardır:

13. Çevrimdışı yüksek gizlilikli veri açılacak mı?
14. Telefona hangi alanlar inecek? Özel nitelikli satırlar inecek mi?
15. PWA'da PRF ile saklama olacak mı?
16. Yüksek gizlilikli veride süre ne olacak? Taslak 8 saat diyor.
17. Kişisel telefona izin verilecek mi? Riske kim karar verecek?
18. İlk aşamada yalnız okuma koşulu kabul ediliyor mu?

Ölçüm, konum ve fotoğraf ile ilgili sorular şunlardır:

19. Kullanım ölçümünün dayanağı ne olacak?
20. Çökme sinyali kimliksiz mi olacak? Ayrıntılı rapor ayrı onaya mı bağlanacak?
21. Müşterinin en düşük yaşı ne olacak?
22. Çocuklar hesap açabilecek mi?
23. Konum hangi amaçla alınacak? Sürekli izleme kapalı mı kalacak?
24. Konum iş performansını etkileyecek mi?
25. Fotoğrafta başka kişilerin verisi bekleniyor mu?

İmza, ihlal ve görevler ile ilgili sorular şunlardır:

26. Güvenli elektronik imza kullanılacak mı?
27. İhlal planında kim, ne zaman bildirim yapacak?
28. VERBİS, başvuru, saklama ve imha işini hangi rol yapacak?
29. Elle imhayı hangi rol, hangi aralıkla başlatacak?
30. Yer sağlayıcı bildirimi yapılacak mı? Trafik kaydı ne kadar tutulacak?
31. Veri koruma görevlisi atanacak mı?
32. Risk değerlendirmesi şablonunu kim hazırlayacak?
33. Saklama süreleri listesini kim hazırlayacak?
34. Uygulama içi başvuruda T.C. kimlik numarası istenecek mi?

Mağaza ve vergi ile ilgili sorular şunlardır:

35. Mağazada tek uygulama mı olacak, kiracı başına uygulama mı?
36. Mağaza paketi kimlere açılacak?
37. Geliştirici hesapları şirket adına mı açılacak?
38. DAC7 için vergi uzmanına sorulacak mı?

DAC7, AB'nin dijital platformlar için vergi bildirimi kuralıdır.

Ülkeler ile ilgili sorular şunlardır:

39. Önce hangi AB ülkesi açılacak?
40. Öteki bölgeler için ayrı inceleme yapılacak mı?

Metin ve belge ile ilgili sorular şunlardır:

41. Metinleri hangi avukat onaylayacak?
42. Belgenin sınırı 32.768 bayt mı olacak, 32.000 bayt mı?

Karşılaştırma notunda 61 maddelik bir “emin değilim” listesi de var. Örneğin 7499 sayılı Kanun değişikliğinin tarihi iki notta farklı yazılmış. Bu liste avukata gösterilmelidir.

### 2. CSS ve Sass kuralları

Proje sahibi bu işi sonraya bıraktı. Kurallar şimdilik Python dışı dosyada ve ayrı arayüz dosyasında duruyor.

### 3. Proje kayıtları

Her kural dosyasının Ek A bölümü bir proje kaydı şablonu verir. Hiçbir projede proje kaydı henüz yok. Proje kaydı seviyeyi, sürümleri ve denetim komutlarını tutar.

Mobil projenin kaydı şunları yazmalıdır:

- oturum süreleri tablosu,
- bileşen kataloğunun listesi,
- hedef ülkeler,
- mağaza hesapları ve sahipleri,
- canlı güncelleme aracı ve sunucusu,
- bildirim servisleri,
- Huawei kararı,
- telefonun kişisel mi ortak mı olduğu,
- internetsiz yapılacak işlerin listesi,
- düzenli silmeyi kimin ve ne sıklıkla başlatacağı,
- gerçek telefon denemesini yapan kişi.

### 4. Önerilen ama istenmeyen işler

- **Proje sahibi için kısa özet.** Claude iki kez önerdi. Proje sahibi cevap vermedi. Bu karar dosyaları o işin bir bölümünü görür.
- **Kural denetim betiği.** Claude önerdi. Betik kuralların bir kısmını kodda arayabilir. Betik yazılmadı.
- **Modül sınırı aracı.** Araç önce tek bir projede denenmeli. Bu öneri Claude'undur. Araç henüz kurulmadı.

## frappesetup sitesine işlenecekler

Site, platformun karar çerçevesidir. Sitenin karar sayfaları yeni kararlarla henüz güncellenmedi. Bu iş sitenin kendi denetiminden geçmelidir. Örneğin derleme, Playwright testleri ve görsel onay gerekir. Playwright, tarayıcıda test çalıştıran araçtır.

Yollar sitenin `src/content/docs/` klasörüne göredir. Satır numaraları inceleme günündeki yerel kopyalara göredir. Satırlar sonradan kaymış olabilir.

| Yeni karar | Sitedeki yer | Durum |
|---|---|---|
| Paketin kökeni farklıdır. | `rail-2-yapilandirma.md:33`, `kalite-kurallari.md:28` | Çerezli web yolu aynı kökende kalır. Paket çapraz köken kullanırsa yalnız doğrulanan kökenler açılır. |
| Paket belirteç taşır. | `acik-kararlar.md:37` (K-25) | K-25 yalnız tarayıcıyı kapsıyor. Paket için ayrı karar gerekir. |
| Paket girişi sistem tarayıcısıyla olur. | `rail-4-keycloak.md:45-73` | Akış yalnız tarayıcı yönlendirmesi olarak çizili. |
| Sihirli bağlantı ve Apple ile giriş istenir. | `karar-katalogu.md:25`, `karar-katalogu.md:33` | K-38 açık. Eklenti lisansı KM-09 ve K-52 ile karşılaştırılmalı. Özel kimlik eklentisi SUS-03 ile karşılaştırılmalı. |
| Telefonda oturum süresi. | `rail-4-keycloak.md:168`, `acik-kararlar.md:65` | K-41 açık. Frappe'nin 12 saatlik değeri boşta kalma süresidir. Bu değer toplam süre değildir. |
| İnternet yokken her iş yapılır. | `rail-3-frontend.md:33`, `kalite-kurallari.md:44` (PERF-05) | PERF-05 izin verisini yalnız bellekte tutar. Çevrimdışı yetki kuralı yeni kararla uyumlu olmalı. |
| Eski sürüm çalışmaya devam eder. | `rail-2-gelistirme.md:96` | İki küçük sürüm telefon için en az süredir. Bu süre kaldırma tarihi değildir. |
| Telefon bildirimi. | `admin-shell.md:91-92` | Servis kararı yok. |
| Çökme kaydı ve ölçüm. | `olcum-gozlem.md:38-43` | Telefon paketi için yüzey sınıfı yok. |
| Hedef telefonlar ve ülkeler. | `rail-3-frontend.md:98` | Huawei yok. Hedef ülke sırası da yazılmalı. |
| Ödeme telefonda alınır. | `app-cercevesi.md:43` | Mobil ödeme akışı yok. Abonelik ve kredi satın alma ekranları pakette mağaza kurallarına takılır. |
| Planlama sırası ve olgunluk seviyeleri. | `raylar.md:22-29` | DDD, modüler monolit ve seviye kavramı yok. |
| Modül sınırı denetimi. | `app-cercevesi.md:60`, `rail-2-gelistirme.md:96-98` | Modül haritası ve API uyum denetimi var. Karar 9'daki üç denetimin MVP kanıtı yok. |
| Firefox testi. | `rail-3-frontend.md:94`, `admin-shell.md:126` ve dört dosya daha | Proje sahibinin kalıcı kuralı Firefox testini açık istek olmadan yasaklar. |
| Yönetim ekranının kullanıcıları. | `rail-2-yapilandirma.md:28` | Site yönetim ekranını yalnız operatöre açar. Yeni karar “yöneticiler” der. Bu fark netleşmeli. |
| Bütün veriler Hetzner'de durur. | `kararlar.md` içindeki K3 notu | Site aktarım yolunu hukuka bırakıyor. Yeni bulgu standart sözleşme ve 5 iş günü bildirimdir. |
| Sunucu tanımlı sayfa ve bileşen kataloğu. | K5 kararı | Karar K5 ile uyumludur. Katalog kararı sitede yazılmalı. |
| Kendi sunucudan canlı güncelleme. | Yer yok | Bu karar sitede yazılmalı. |

Dört karar siteyle uyumludur. Bunlar ayrı arayüz (K4), Keycloak (K7), kendi sunucuda barındırma (K3) ve DocType'tan ekran üretimidir (K5).

## Projelerde görülen sorunlar

Denetçiler proje sahibinin projelerinde 22 sorun gördü. Sorunlar düzeltilmedi. Her biri ayrı bir iştir.

- Python dışı dosyanın denetiminde 9 sorun görüldü. Örneğin yedi e-posta şablonunda 41 değer kaçırılmadan basılıyor.
- Ayrı arayüz dosyasının denetiminde 13 sorun görüldü. Örneğin yedi projenin hiçbirinde olgunluk seviyesi kaydı yok.

Listeler çalışma klasöründeki teslim notlarındadır. Her sorunun dosyası ve satırı orada yazılıdır.

## Ad verme raporunun açık işleri

Ad verme raporu `naming_rules_report.md` dosyasındadır. Rapor 22 Kasım 2026 Pazar günü yazıldı. Raporun açık işleri şunlardır:

1. frappesetup dışındaki iki Frappe uygulamasında eski adlar Türkçedir. Bu adları düzeltme işi henüz kimseye verilmedi. Liste raporun 12. bölümündedir.
2. Ad denetim araçları hiçbir projede kurulu değil. Bu araçlar raporun AV-71 ve AV-72 kurallarındadır.
3. Rapor gerçek okurla denenmedi.

Raporun dört açık kararı vardı. frappesetup projesinde Claude üçünü kapattı. Kararlar `backend/PROJE-KAYDI.md` dosyasında D-14 maddesindedir:

- Uygulama ön ekleri `PLT`, `PTR` ve `HRT` oldu.
- Keycloak rol adları küçük harf ve tireyle yazılır.
- Commit mesajında tür ve kapsam İngilizce olur. Açıklama Türkçe kalır.

Öteki uygulamalar için bu kararlar henüz verilmedi.

## Python dosyasının cevapsız soruları

Python dosyası şu sorulara cevap vermiyor:

1. Ekran yokken kayıt türü nasıl oluşturulur?
2. Hata yanıtının ortak biçimi nedir?
3. Aynı yazma isteği iki kez gelirse ne olur?
4. Yama büyük tabloda işi nasıl böler?
5. Yama için önce test nasıl yazılır?

Yama, veritabanını yeni sürüme taşıyan küçük betiktir. Bu soruların önemi orta ya da düşüktür. Python dosyasında boş yer kalmadı. Yeni cümle için başka bir cümle çıkmalı ya da sınır artmalı.

## Bilinen sınırlar

- Kurallar yazılı belgedir. Araçla denetim henüz hiçbir projede kurulu değil.
- Bir ekip deposunun talimatı bu dosyaları anmıyor. Başka bilgisayardaki ajan dosyaları görmeyebilir.
- Frappe 16 yükseltmesi bazı standart kayıtları silebilir. Koşul, kaydın uygulamada dosyasının kalmamasıdır. Bu risk tam bir sitede denenmedi.
- Gerçek telefon, gerçek Safari ve gerçek okur denemesi yapılmadı.
