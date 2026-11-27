# GILT kapsamı: gerçek kapsam, MVP altyapısı ve üst yapı

Bu belge bir araştırma ve plan belgesidir. Belge kural değildir. Kural değişikliği için proje sahibinin kararı gerekir.

- Belgeyi sistem mimarı 27 Kasım 2026 Cuma günü yazdı.
- Belgenin kaynağı AJA-1408 işidir.
- Proje sahibinin yeni kararları AJA-1407 işindedir.
- MVP, ilk kullanılabilir sürüm demektir.

## 1. Kısa özet

Bugünkü GILT planı yalnız dile bakıyor. Gerçek GILT kapsamı daha geniştir. Bir ürün ülkeye ve kültüre göre de uyarlanır. Örneğin tarih, para, ölçü birimi, adres, vergi ve yasal metin bu kapsamdadır.

Bu belge dört şey önerir:

1. Dil ile ülke birbirinden ayrı tutulur. Kullanıcı İngilizce okuyup Türkiye'de yaşayabilir.
2. Varsayılan yerel ayar İngiliz İngilizcesidir (`en-GB`). Kaynak metin de İngiliz İngilizcesiyle yazılır.
3. MVP'de yerel ayar modeli, biçimler, birimler ve çeviri yolu biter. Yeni dil ya da ülke sonra yalnız veri ekleyerek gelir.
4. Çevirmen akışı, yerel pazar ayarları ve ülkeye özel yasal içerik MVP'den sonra gelir.

## 2. Tanımlar

GILT dört işin baş harfinden oluşur. Bu dört iş birbirine bağlıdır ama aynı iş değildir.

### Küreselleştirme (globalization, G11N)

Küreselleştirme en geniş iştir. Şirket ürünü birçok pazarda satmaya hazırlanır. Bu iş yalnız yazılım işi değildir. Hukuk, ödeme, destek ve satış da bu işe girer. IBM ve Oracle bu adı i18n ile yerelleştirmenin toplamı için kullanır [K2].

### Uluslararasılaştırma (internationalization, i18n)

Uluslararasılaştırma, ürünü kolay yerelleştirilecek biçimde tasarlamaktır. Örneğin metin koddan ayrılır. Ürün Unicode kullanır. Ürün sağdan sola yazıyı destekler. Kullanıcının yerel tercihleri ürüne açılır [K1].

### Yerelleştirme (localization, l10n)

Yerelleştirme, ürünü tek bir pazarın diline ve kültürüne uyarlamaktır. W3C bunun çeviriden çok daha büyük bir iş olduğunu söyler. Sayı, tarih, para, klavye ve sıralama bu işe girer. Simge, renk, yasal kural ve adres biçimi de bu işe girer [K1].

### Çeviri (translation)

Çeviri, metni bir dilden ötekine aktarmaktır. Çeviri yerelleştirmenin yalnız bir parçasıdır.

### Kaynak notu

Görev GALA tanımlarını da istedi. GALA sitesindeki dört tanım sayfası 27 Kasım 2026 Cuma günü açılmadı. Sayfalar 404 hatası verdi. LISA için de birincil bir kaynak bulunamadı. Bu yüzden tanımlar W3C kaynağına dayanır. GALA tanımı doğrulanmadı.

## 3. Yerel ayar nedir?

Yerel ayar (locale), kullanıcının dil ve bölge tercihlerinin toplamıdır. Yerel ayarı bir dil etiketi anlatır. Dil etiketinin standardı BCP 47 standardıdır [K9].

Örnek etiketler şunlardır:

- `en-GB` İngiltere'de kullanılan İngilizcedir.
- `tr-TR` Türkiye'de kullanılan Türkçedir.
- `en-GB-u-ms-metric` İngiliz İngilizcesidir ama birimler metriktir.

Etiketin sonundaki `-u-` bölümü tercih taşır. Unicode bu tercihleri tanımlar [K3]:

| Anahtar | Ne seçer? | Örnek |
| --- | --- | --- |
| `ms` | Ölçü sistemi | `metric`, `uksystem`, `ussystem` |
| `mu` | Tek bir birimi | `celsius`, `fahrenhe` |
| `rg` | Bölge varsayılanlarını | `rg=trzzzz` |
| `fw` | Haftanın ilk gününü | `fw=mon` |
| `hc` | Saat düzenini | `h23`, `h12` |

Bu belgenin ana kararı şudur: dil ile bölge ayrı alanlarda tutulur. Dil metnin dilini seçer. Bölge birimi, tatili, vergiyi ve yasal metni seçer. Biçimler ikisinden birlikte çıkar.

## 4. Kapsam tablosu

Tabloda beş sütun var. "Parça" sütunu işin hangi GILT parçasına girdiğini söyler. "MVP" sütunu altyapının MVP'de bitip bitmeyeceğini söyler.

| Konu | Neyi kapsar? | Parça | MVP | Kaynak |
| --- | --- | --- | --- | --- |
| Dil | Metnin dili, yedek dil zinciri | i18n, çeviri | Altyapı evet | [K1] |
| Yazı yönü | Sağdan sola diller, `dir` özniteliği, mantıksal CSS | i18n | Altyapı evet | [K7] |
| Çoğul | Dile göre çoğul kuralı | i18n | Evet | [K4] |
| Tarih ve saat | Tarih sırası, saat düzeni, ay adları | i18n, l10n | Evet | [K3] |
| Takvim ve hafta | Haftanın ilk günü, hafta sonu | i18n, l10n | Evet | [K3] |
| Saat dilimi | Kullanıcının ve sitenin saat dilimi | i18n | Evet | [K10] |
| Sayı | Ondalık ayırıcı, binlik ayırıcı | i18n | Evet | [K3] |
| Para | Para birimi, kuruş basamağı, yuvarlama | i18n, l10n | Evet | [K3] |
| Ölçü birimi | Ölçü sistemi, kullanım türüne göre birim | i18n, l10n | Altyapı evet | [K3] |
| Ad | Ad sırası, tek ad, uzun ad | i18n | Kural evet | [K8] |
| Adres | Ülkeye göre adres düzeni, posta kodu | l10n | Frappe hazır | [K11] |
| Telefon | Uluslararası numara biçimi | i18n | Frappe hazır | [K11] |
| Sıralama ve arama | Dile göre sıralama, Türkçe i ve İ | i18n | Evet | [K5] |
| Vergi ve fatura | KDV, VAT, e-fatura, kimlik numarası | l10n | Sonra | [K1] |
| Yasal metin | KVKK, UK GDPR, AB GDPR, çerez metni | l10n | Yapı evet | [K13] |
| Ödeme | Ülkeye göre ödeme yöntemi | g11n | Sonra | Yok |
| Tatil ve iş günü | Resmî tatil, çalışma günü | l10n | Frappe hazır | Frappe |
| Görsel ve renk | Simge, renk, görselin kültüre uygunluğu | l10n | Kural evet | [K1] |
| Yazı tipi | Harf desteği, Türkçe harfler | i18n | Evet | Proje |
| Erişilebilirlik | `lang` özniteliği, ekran okuyucu dili | i18n | Evet | [K7] |
| Bildirim | E-posta, SMS, ekran bildirimi | l10n, çeviri | Altyapı evet | Frappe |
| Destek | Destek dili, saat dilimi | g11n | Sonra | Yok |
| Kiracı ayarı | Kiracının ülkesi, dili, para birimi | i18n | Evet | Frappe |
| Kullanıcı ayarı | Kullanıcının dili, bölgesi, birimi | i18n | Evet | Frappe |
| İçerik yazımı | İngiliz İngilizcesi yazım kılavuzu | çeviri | Evet | [K12] |

"Kaynak" sütununda "Yok" yazan satırlar için birincil kaynak aranmadı. Bu satırlar ürün deneyimine dayanan önerilerdir.

### Ölçü birimi örneği

Birim seçimi yalnız ülkeye bağlı değildir. Ölçülen şeye de bağlıdır. CLDR verisi buna "kullanım türü" der [K3].

- İngiltere'de yol uzaklığı mil ile gösterilir. Öteki ülkelerin çoğunda kilometre kullanılır.
- İngiltere'de insan boyu 3 fitten uzunsa fit ve inç ile gösterilir. Dünya varsayılanı santimetredir.
- CLDR üç ölçü sistemi tanır: metrik, ABD ve Birleşik Krallık sistemi.

Bu yüzden ürün "bu ülke metrik mi?" diye sormaz. Ürün "bu ülkede bu tür ölçü nasıl gösterilir?" diye sorar.

### Türkçe harf örneği

Türkçede `i` büyük harfe `İ` olarak döner. `I` küçük harfe `ı` olarak döner. Unicode bu kuralı yalnız Türkçe ve Azerice için tanımlar [K5]. Arama metni yanlış dille küçültülürse "İstanbul" araması sonuç bulmaz.

## 5. "British first" ne demektir?

Proje sahibi "tüm content british first olmalı" dedi.

Bunun anlamı şudur:

1. Bütün kaynak metin İngiliz İngilizcesiyle yazılır.
2. Kaynak katalog `en-GB` kataloğudur. Türkçe ve öteki diller bu katalogdan çevrilir.
3. Kullanıcı dil seçmezse ürün `en-GB` gösterir.
4. Tarih ve sayı da `en-GB` biçimini kullanır. Örneğin tarih "27 November 2026" biçimindedir.

### Önerilen yazım kılavuzu

Öneri GOV.UK yazım kılavuzudur. Kılavuz açık ve ücretsizdir. Kılavuz sade İngilizceyi zorunlu tutar [K12].

Kılavuzun bu ürüne en çok yarayan kuralları şunlardır:

- İngiliz yazımı kullanılır. Örneğin "organise" yazılır, "organize" yazılmaz.
- Tarihte sıra sayısı kullanılmaz. "2 June" yazılır, "2nd June" yazılmaz.
- Tarihte virgül kullanılmaz. Örnek: "4 June 2017".
- Saat "5:30pm" biçiminde yazılır.
- 25 kelimeden uzun cümle denetlenir. Gerekirse cümle bölünür.
- Paragraf en çok 5 cümle olur.

Kılavuzda "-ise" ile "-ize" için ayrı bir madde bulunamadı. "Organise" örneği "American and UK English" maddesindedir. Oxford University Press "-ize" yazımını kullanır. Bu yüzden ürün "-ise" yazımını açıkça seçmelidir.

The Guardian kılavuzu da önerilen bir seçenekti. Site araştırma sırasında açılmadı. Bu kaynak doğrulanmadı.

### İçerik kılavuzuna eklenecekler

GOV.UK kılavuzu genel bir kılavuzdur. Ürün için ayrıca şunlar yazılmalıdır:

1. Terimler sözlüğü. Örneğin "tenant" yerine hangi kelimenin görüneceği yazılır.
2. Düğme ve hata metni kuralları.
3. Çevirmene not yazma kuralı. Her katalog anahtarına kısa bir açıklama eklenir.

## 6. Bugünkü durum

Bu bölüm 27 Kasım 2026 Cuma günkü kodu anlatır.

### Ayrı arayüz (atonota-web)

- Dil bağlamı var. GILT 1 işi bitti.
- Desteklenen diller yalnız `tr` ve `en` kodlarıdır. Bölge bilgisi yoktur. `en-GB` ile `en-US` ayrılamaz.
- Yedek dil `tr` olarak yazılı. Bu değer `src/app/locale/language.ts` dosyasındadır.
- Bazı yerlerde dil sabit yazılı. Örneğin `src/shell/messages.ts` dosyasında `Intl.NumberFormat('tr-TR')` var.
- Arama, bazı yerlerde metni her zaman Türkçe kurala göre küçültüyor. Örneğin `src/components/controls/dropdown-items.ts` dosyasında `toLocaleLowerCase('tr')` var.
- Ölçü birimi tercihi yoktur.

### Backend açılış verisi

Açılış verisini `platform_core/shell/bootstrap.py` dosyası hazırlar.

- Dil gelir. Tarih ve saat biçimi, haftanın ilk günü ve sayı biçimi de gelir.
- Saat dilimi sitenin saat dilimidir. Kullanıcının saat dilimi gelmez.
- Ülke ve ölçü sistemi gelmez.

### Keycloak giriş teması

- Çok dil açık. Diller `tr` ve `en` dilleridir.
- Varsayılan dil `tr` dilidir. Bu değer `platform-realm.json` dosyasındadır.
- Giriş teması iki dilde de 251 satırdır.
- Hesap temasında Türkçe dosya 258 satırdır. İngilizce dosya yalnız 15 satırdır. İngilizce hesap ekranında metin eksiktir.
- Kullanıcının dili `locale` bilgisiyle belirtece yazılıyor.

### Kural dosyaları

- M-9 kuralı çeviriyi `translations/<dil>.csv` dosyasına yazdırıyor. Frappe 16 ise `.po` dosyalarını kullanır. Eski CSV yolu hâlâ çalışır ama yeni yol `.po` yoludur [F2].
- IC-9 kuralı "İngilizce metin uydurmayın" diyor. AJA-1407 kararından sonra bu kural değişmelidir.

## 7. Frappe'nin hazır sundukları

Kaynak Frappe v16.61.0 sürümüdür. Kaynakta HRMS v16.54.1 sürümü de incelendi. Ürün `frappe/erpnext:v16.55.0` imajını kullanır. ERPNext kaynağı bu makinede yoktu. ERPNext satırları bu yüzden doğrulanmadı.

Hazır olanı yeniden yazmayın. Tablo hazır olanı ve eksik olanı gösterir.

| Konu | Frappe ne sunar? | Eksik ne? |
| --- | --- | --- |
| Dil kaydı | `Language` belge türü, `enabled` alanı, `en-GB` kaydı | `en-GB` kaydı kapalı gelir |
| Dil seçimi | Kullanıcı dili, site dili, çerez, tarayıcı dili | Yok |
| Dile göre biçim | `Language` kaydında tarih, saat, sayı ve hafta başı | Yok |
| Yedek dil | `en-GB` dili `en` diline düşer | `based_on` alanı kullanılmaz |
| Çeviri dosyası | `.po`, `.pot`, `.mo`, Babel | Yok |
| Çeviri komutları | `generate-pot-file`, `compile-po-to-mo`, `migrate-csv-to-po` | Yok |
| Site çevirisi | `Translation` belge türü | Yok |
| Bağlamlı çeviri | `_()` ve `__()` bağlam alır | Çoğul desteği yok |
| Çeviri yönetimi | Crowdin ayarı (`crowdin.yml`) | Bize ait değil |
| Site ayarı | Ülke, dil, saat dilimi, para birimi, biçimler | Ölçü sistemi yok |
| Kullanıcı ayarı | Dil ve saat dilimi | Bölge ve birim yok |
| Ülke kaydı | Tarih biçimi, saat dilimleri, ülke kodu | Ölçü sistemi yok |
| Para kaydı | Simge, kuruş, sayı biçimi, sembol yeri | Yok |
| Tarih biçimleme | Babel ile CLDR verisi | Yok |
| Sayı biçimleme | Frappe'nin kendi kalıpları | CLDR kullanılmaz |
| Adres | Ülkeye göre `Address Template` | Yok |
| Telefon | `phonenumbers` ile doğrulama | Yok |
| Ad | Ad, ikinci ad, soyadı alanları | Ad sırası dile göre değişmez |
| Yazı yönü | Sağdan sola CSS dosyaları | Dil listesi kodda sabit |
| Yazdırma | Yazdırma biçiminde varsayılan dil | Yok |
| E-posta şablonu | `Email Template` | Dil alanı yok |
| Tatil | Tatil listesi, HRMS atamaları | Ülke takvimi elle girilir |
| Bölge modülü | HRMS'de Hindistan ve BAE modülü | Türkiye ve İngiltere modülü yok |
| Veritabanı sıralaması | `utf8mb4_unicode_ci` | Dile göre seçilemez |

Kaynak satırları şunlardır:

- Dil seçimi `frappe/translate.py` dosyasında 33. ile 81. satırlar arasındadır.
- Dile göre biçim `frappe/locale.py` dosyasında 43. ile 53. satırlar arasındadır.
- Sağdan sola dil listesi `frappe/utils/jinja_globals.py` dosyasının 160. ile 165. satırlarındadır.
- Site saat dilimi boşsa Frappe Hindistan saat dilimini kullanır. Bu `frappe/utils/data.py` dosyasının 391. satırındadır. Kiracı kurulumu saat dilimini mutlaka yazmalıdır.
- Veritabanı sıralama ayarı `frappe/database/mariadb/database.py` dosyasının 132. satırındadır.

### Frappe'den çıkan dersler

1. Backend çevirisi `.po` yoluna geçmelidir. Frappe 16 bu yolu hazır sunar.
2. Frappe çoğul desteklemez. Backend metninde sayıya bağlı cümle kurmayın. Sayılı mesajı arayüz kataloğu üretir.
3. Ölçü birimi tercihi Frappe'de yoktur. Bu alan ürünün kendi işidir.
4. ERPNext'teki ölçü birimi (UOM) ticari birimdir. Örneğin "kutu" ve "adet" bu birimlerdir. Gösterim birimi tercihi başka bir şeydir. İkisi karıştırılmaz.

## 8. MVP altyapısı

MVP sonunda şu sonuç alınmalı: yeni bir dil ya da ülke kod değişmeden eklenir. Yalnız veri ve çeviri dosyası eklenir.

### 8.1. Yerel ayar modeli

Her kullanıcının yerel ayarı üç katmandan çıkar:

1. Kullanıcının kendi seçimi.
2. Kiracının ayarı. Kiracı, ürünü kullanan şirkettir. Her kiracının bir Frappe sitesi vardır.
3. Platform varsayılanı. Bu değer `en-GB` değeridir.

Üstteki katman boş değilse alttaki katman kullanılmaz.

Model şu alanları taşır:

| Alan | Örnek | Nerede durur? |
| --- | --- | --- |
| Dil etiketi | `en-GB`, `tr-TR` | Frappe `User.language`, `System Settings.language` |
| Bölge | `GB`, `TR` | Kullanıcıda yeni alan, sitede `System Settings.country` |
| Saat dilimi | `Europe/London` | Frappe `User.time_zone`, `System Settings.time_zone` |
| Para birimi | `GBP`, `TRY` | `System Settings.currency`, belgede kendi alanı |
| Ölçü sistemi | `metric`, `uksystem` | Yeni alan, boşsa bölgeden çıkar |
| Saat düzeni | `h23`, `h12` | Yeni alan, boşsa dil ve bölgeden çıkar |
| Haftanın ilk günü | `mon` | Frappe `Language` kaydı |

Yeni alanları `platform_core` uygulaması ekler. Frappe çekirdek dosyasına dokunulmaz.

### 8.2. Açılış verisi

Açılış verisi tam yerel ayarı gönderir. Arayüz yerel ayarı kendisi tahmin etmez.

- Dil etiketi tam gelir. Örneğin `en` değil `en-GB` gelir.
- Kullanıcının saat dilimi gelir. Kullanıcıda boşsa sitenin saat dilimi gelir.
- Bölge, ölçü sistemi ve saat düzeni gelir.
- Arayüz bu değerlerden bir BCP 47 etiketi kurar. Örnek: `en-GB-u-ms-metric`.

### 8.3. Dil kaydı ve yedek zinciri

- Arayüzde desteklenen diller bir veri dosyasında durur. Kodda dil listesi yazılmaz.
- Veri dosyası her dil için yazı yönünü de taşır.
- Ant Design ve Day.js dil dosyaları etikete göre isteğe bağlı yüklenir. Yalnız seçilen dilin dosyası iner.
- Yedek zinciri şöyledir: tam etiket, sonra dil kökü, sonra `en-GB`. Örnek: `tr-TR`, `tr`, `en-GB`.
- Eksik çeviri kullanıcıya anahtar olarak görünmez. Eksik metin `en-GB` kataloğundan gelir.

### 8.4. Kaynak katalog

- Kaynak katalog `en-GB` kataloğudur.
- `en-GB` metni yazım kılavuzuna göre yazılır ve gözden geçirilir.
- Var olan Türkçe metin `tr` kataloğuna girer.
- Katalog anahtarı İngilizce ve ASCII olur. Her anahtarın çevirmen notu olur.
- Mesaj ICU MessageFormat alt kümesiyle yazılır. Çoğul `Intl.PluralRules` ile seçilir [K4].

### 8.5. Biçimler

- Tarih, saat, sayı, para, liste ve göreli zaman `Intl` ile biçimlenir [K6].
- Kodda `tr-TR` gibi sabit dil yazılmaz.
- Tarih-saat değeri kullanıcının saat diliminde gösterilir.
- Para tutarı belgenin para birimiyle gösterilir. Para birimi dile bağlı değildir.

### 8.6. Ölçü birimleri

- Veri her zaman tek bir temel birimle saklanır. Örneğin uzunluk metre, kütle kilogram ve sıcaklık santigrat olur.
- Gösterim birimi bölgeden ve kullanım türünden çıkar. Örneğin yol uzaklığı İngiltere'de mil olur.
- Kullanıcı ölçü sistemini değiştirebilir.
- Birim tablosu CLDR `units.xml` verisinden derleme anında üretilir [K3]. Çalışma zamanına yeni kütüphane eklenmez.
- Biçimleme `Intl.NumberFormat` ile `style: "unit"` seçeneğini kullanır [K6]. `Intl` birimi çevirmez. Çeviriyi ürünün birim tablosu yapar.
- Bir alanın birim türü belge türü tanımında yazılır. Örneğin "ağırlık" alanının türü `mass` olur.

### 8.7. Yazı yönü

- `<html>` öğesinin `lang` ve `dir` değeri yerel ayardan gelir [K7].
- Yeni CSS mantıksal yön özelliklerini kullanır. Örneğin `margin-inline-start` yazılır.
- Ant Design yönü `ConfigProvider direction` ile verilir [K14].
- MVP'de sağdan sola bir dil açılmaz. Ama sözde dil denemesi sağdan sola düzeni de dener.

### 8.8. Sıralama ve arama

- Arayüz sıralaması `Intl.Collator` ile kullanıcının diline göre yapılır [K6].
- Arama metni kullanıcının diline göre küçültülür. Kodda `toLocaleLowerCase('tr')` gibi sabit dil yazılmaz.
- Veritabanı sıralaması dile göre değişmez. Bu bir Frappe sınırıdır. Sınır kayda yazılır.

### 8.9. Backend çevirisi

- Backend metni İngilizce yazılır ve `_()` ile bağlamla sarılır.
- Çeviri Frappe 16'nın `.po` dosyalarına yazılır.
- Var olan `tr.csv` dosyası `migrate-csv-to-po` komutuyla taşınır.
- Frappe'de `en-GB` dili açılır. Sistem dili `en-GB` olur.

### 8.10. Kimlik sunucusu (Keycloak)

- Varsayılan dil İngilizce olur.
- Hesap temasının İngilizce metni tamamlanır. Türkçe dosya 258 satır, İngilizce dosya 15 satırdır. Eksik metin yazılır.
- Kullanıcı dili Keycloak ile Frappe arasında tek yönde akar. Frappe dili boşsa Keycloak dili kullanılır.
- Keycloak'ın `en-GB` etiketini nasıl işlediği doğrulanmadı. Bu bir deneme işidir.
- E-posta teması da aynı dil kuralına uyar.

### 8.11. Bildirimler

- E-posta, SMS ve ekran bildirimi alıcının dilinde hazırlanır.
- Tarih ve tutar alıcının yerel ayarıyla biçimlenir.
- Frappe `Email Template` belge türünde dil alanı yoktur. MVP'de şablon metni `_()` ile çevrilir. Dile özel şablon MVP'den sonra gelir.

### 8.12. Yasal metin için yapı

- Yasal metin ülke ve dil ile anahtarlanır. Örneğin "TR ve tr" anahtarı KVKK aydınlatma metnini verir.
- MVP'de yalnız yapı kurulur. Metnin hukuki içeriğini hukuk danışmanı yazar.
- MVP'nin kapsadığı yasalar şunlardır: Türkiye için KVKK, İngiltere için UK GDPR [K13].

### 8.13. Denetim ve kapılar

- Gömülü metin denetimi derlemede çalışır.
- Sözde dil denemesi uzayan metni ve gömülü metni yakalar.
- Sağdan sola sözde dil denemesi ters düzeni yakalar.
- Eksik çeviri listesi her derlemede çıkar. Liste kapıyı düşürmez.

## 9. MVP sonrası üst yapı

Üst yapı, altyapının üstüne kurulan iş ve süreçtir. Bu işler MVP'den sonra gelir. Sıra bağımlılığa göredir.

1. **Çeviri yönetim sistemi.** Çeviriler bir sistemde toplanır. Açık kaynak seçenekler Weblate ve Pontoon'dur [K15]. Weblate GPL-3.0, Pontoon BSD-3-Clause lisanslıdır. Frappe kendi çevirisi için Crowdin kullanır.
2. **Çevirmen akışı.** Çevirmen çevirir, ikinci kişi gözden geçirir, sonra çeviri yayımlanır. Terimler sözlüğü ve çeviri belleği bu akışa girer.
3. **Değişen kaynak metin.** Kaynak metin değişince çeviri "eskimiş" olarak işaretlenir.
4. **Yerel pazar ayarları.** Her ülke için para, vergi, tatil, ödeme ve birim varsayılanları bir paket olur.
5. **Ülkeye özel yasal içerik.** Sözleşme, gizlilik metni, çerez metni ve fatura notu ülkeye göre değişir.
6. **Vergi ve e-fatura.** Türkiye e-Fatura ve İngiltere VAT kuralları ayrı modül olur. HRMS ve ERPNext'te Türkiye ve İngiltere modülü bulunamadı.
7. **Çok dilli veri.** Ürün adı gibi kullanıcı verisi birden çok dilde tutulur. Frappe'de `translatable` alan desteği vardır.
8. **Dile özel e-posta şablonu.** Her şablonun dil sürümü olur.
9. **Sağdan sola dil açılışı.** İlk sağdan sola dil gerçek kullanıcıyla denenir.
10. **Ad ve adres biçimi.** Ad sırası ve adres düzeni ülkeye göre gösterilir. Google adres verisi açık lisanslıdır [K11].
11. **Destek ve satış.** Destek dili, destek saatleri ve yerel iletişim kanalları belirlenir.
12. **Görsel uygunluk.** Görsel, renk ve simge her pazar için gözden geçirilir.
13. **Ölçüm.** Hangi dilin ve ülkenin kullanıldığı izlenir. İzleme KVKK ve GDPR kurallarına uyar.

## 10. Ayrı arayüz ve Keycloak teması ne yapmalı?

### Ayrı arayüz (atonota-web)

1. Dil kodu yerine tam yerel ayar etiketi kullanır.
2. Desteklenen dilleri veri dosyasından okur.
3. Yedek dili `en-GB` yapar.
4. Kaynak katalog olarak `en-GB` kataloğunu kullanır.
5. Birim tablosunu ve birim biçimleyicisini kurar.
6. Arama ve sıralamada kullanıcının dilini kullanır.
7. Kullanıcı ayarları ekranında dil, bölge, saat dilimi ve ölçü sistemi seçilir.

### Keycloak giriş teması

1. Varsayılan dili İngilizce yapar.
2. Hesap temasındaki eksik İngilizce metni tamamlar.
3. İngilizce metni İngiliz yazımıyla yazar.
4. Seçilen dili belirteçle Frappe'ye gönderir.
5. Sözde dil ile bir kez denenir.

## 11. GILT 2 ile GILT 5 nasıl değişmeli?

| İş | Bugünkü kapsam | Öneri |
| --- | --- | --- |
| GILT 1 (AJA-1362) | Dil bağlamı. İş bitti. | Yedek dil `en-GB` olur. Dil kodu tam etikete geçer. Bu işi GILT 6 yapar. |
| GILT 2 (AJA-1363) | `Intl` biçimleri | Sürer. Yedek dil `en-GB` olur. Saat dilimi kullanıcıdan gelir. |
| GILT 3 (AJA-1364) | `lang` ve `dir` | GILT 6'dan sonra sürer. Yön veri dosyasından gelir. |
| GILT 4 (AJA-1365) | Katalog | Kapsam değişir. Kaynak katalog `en-GB` olur. `en-GB` metni yazılır ve gözden geçirilir. |
| GILT 5 (AJA-1366) | Sözde dil | Sözde dil `en-GB` kataloğundan üretilir. Sağdan sola sözde dil eklenir. |

Önerilen sıra şudur:

1. GILT 2 sürer. GILT 2 yalnız yedek dili düzeltir.
2. GILT 6 yerel ayar modelini kurar.
3. GILT 3 ve GILT 4 GILT 6'dan sonra başlar.
4. GILT 5 GILT 4'ten sonra başlar.
5. GILT 7 ile GILT 11 GILT 6'dan sonra paralel yürür.

## 12. İş listesi ve gereksinim önerileri

Bu öneriler gereksinim kaydı değildir. Kaydı PO açar. PO kimliği `requirements.json` dosyasının sonuna ekler.

Her işte önce test yazılır. QA ve Committer işi kural listesiyle inceler.

### GILT 6: Yerel ayar modeli ve açılış verisi

- **Öneri.** Kullanıcının yerel ayarı kullanıcı, kiracı ve platform katmanlarından çıkar. Platform varsayılanı `en-GB` olur. Dil ile bölge ayrı alanlardır.
- **Kabul ölçütü 1.** Açılış verisi tam dil etiketi, bölge, kullanıcı saat dilimi, ölçü sistemi ve saat düzenini taşır. Bunu bir backend testi gösterir.
- **Kabul ölçütü 2.** Kullanıcı ve kiracı ayarı boşsa yerel ayar `en-GB` olur. Bunu bir test gösterir.
- **Kabul ölçütü 3.** Arayüzde desteklenen diller veri dosyasından gelir. Yeni dil yalnız veri ve katalog eklenerek açılır. Bunu bir test gösterir.
- **Takım.** Backend ve arayüz takımı birlikte çalışır.

### GILT 7: Ölçü birimleri

- **Öneri.** Veri temel birimle saklanır. Gösterim birimi bölgeden, kullanım türünden ve kullanıcı tercihinden çıkar.
- **Kabul ölçütü 1.** Bölge `GB` iken yol uzaklığı mil ile görünür. Bölge `TR` iken kilometre ile görünür.
- **Kabul ölçütü 2.** Kullanıcı metrik sistemi seçerse bölge ne olursa olsun metrik birim görünür.
- **Kabul ölçütü 3.** Birim tablosu CLDR verisinden üretilir. Elle yazılmaz.

### GILT 8: Backend çevirisi ve `en-GB` dili

- **Öneri.** Backend çevirisi `.po` dosyalarına taşınır. Frappe'de `en-GB` açılır. M-9 kuralı buna göre değişir.
- **Kabul ölçütü 1.** `tr.csv` dosyası `.po` dosyasına taşınmıştır. Türkçe metin değişmez.
- **Kabul ölçütü 2.** Yeni kiracı sitesi `en-GB` diliyle ve dolu saat dilimiyle kurulur.

### GILT 9: Keycloak dili

- **Öneri.** Keycloak varsayılan dili İngilizcedir. Hesap teması iki dilde tamdır.
- **Kabul ölçütü 1.** Hesap temasında `en` ve `tr` dosyalarının anahtarları aynıdır. Bunu bir test gösterir.
- **Kabul ölçütü 2.** Dil seçilmezse giriş ekranı İngilizce açılır.

### GILT 10: Sıralama ve arama

- **Öneri.** Arama ve sıralama kullanıcının dilini kullanır.
- **Kabul ölçütü.** Kodda `toLocaleLowerCase('tr')` gibi sabit dil kalmaz. Türkçe kullanıcı "istanbul" yazınca "İstanbul" bulunur.

### GILT 11: Bildirim dili ve yasal metin yapısı

- **Öneri.** Bildirim alıcının dilinde hazırlanır. Yasal metin ülke ve dil ile seçilir.
- **Kabul ölçütü 1.** Türkçe kullanıcıya giden e-posta Türkçedir. Tarih Türkçe biçimdedir.
- **Kabul ölçütü 2.** Yasal metin anahtarı ülke ve dilden oluşur. Eksik metin için `en-GB` metni gösterilir.

### İçerik işi: İngiliz İngilizcesi kılavuzu

- **Öneri.** Ürün GOV.UK yazım kılavuzunu temel alır. Ürün kendi terimler sözlüğünü yazar.
- **Kabul ölçütü.** Kılavuz ve sözlük `docs/standartlar/` klasöründedir. IC-9 kuralı yeni kaynak dile göre güncellenmiştir.

### Kural değişikliği önerileri

Bu değişiklikler için proje sahibinin kararı gerekir. Karar `KARARLAR.md` dosyasına yazılır.

1. IC-9: Kaynak metin `en-GB` olur. "İngilizce metin uydurmayın" cümlesi "İngilizce metni kılavuza göre yazın" olur.
2. IC-12: Yedek dil `en-GB` olur. Yedek zinciri kurala yazılır.
3. M-9: Çeviri `.po` dosyasına yazılır.
4. Yeni bir kural dil ile bölgeyi ayırır.
5. Yeni bir kural ölçü verisini temel birimle saklatır.

### Kod yorumları İngilizce olur

Proje sahibi "tüm codebase ingilizce olmalı" dedi. Karar 40 yalnız kod adlarını kapsar. Proje sahibi 27 Kasım 2026 Cuma günü bir soruyu da cevapladı. Cevaba göre kod yorumları da İngiliz İngilizcesiyle yazılır. Cevap AJA-1408 işindedir.

- Yeni kod Türkçe yorum eklemez.
- Var olan Türkçe yorumlar ayrı bir işte çevrilir. Bu iş AJA-1409 işidir.

Öneri şudur: bir denetim yeni Türkçe yorumu reddeder.

Denetim şu yerlerde çalışır:

1. atonota-web deposunda denetim ayrı bir `lint:comments` betiğidir. `npm run lint` komutu bu betiği de çalıştırır. CI aynı komutu çalıştırır.
2. frappesetup deposunda denetim `backend` uygulamaları için yeni bir CI adımıdır. Bugünkü CI bu uygulamaları denetlemiyor. Adımı uygulayan takım ekler.
3. Committer inceleme listesine bir satır eklenir. Satırda "Yeni Türkçe yorum yok" yazar.

Denetim Git hook'u olarak kurulmaz. Böylece yazar koruması ve hook ayarları değişmez.

ESLint ve öteki araçlar bütün dosyayı okur. Bu araçlar Git farkını bilmez. atonota-web deposunda bugün Türkçe harfli yaklaşık 1059 yorum satırı var. Araç tek başına çalışırsa denetim hemen düşer. Bu yüzden denetimi bir sarmalayıcı betik yürütür.

Sarmalayıcı betik şu adımları izler:

1. Betik hedef dalı bulur. atonota-web için hedef dal `main` dalıdır. frappesetup için hedef dal `backend` dalıdır.
2. Betik farkı alır. Komut `git diff --unified=0 <hedef dal>...HEAD` komutudur.
3. Betik farktan her dosyanın yeni satır numaralarını çıkarır.
4. Betik yorumları dilin kendi aracıyla bulur. TypeScript için ESLint yorumları okur. Python için `tokenize` modülü yorumları okur. `ast` modülü docstring metinlerini okur. Keycloak şablonlarında `<#-- -->` ve `<!-- -->` yorumları okunur.
5. Betik yalnız yeni satırlara düşen yorumları tutar. Öteki yorumları atar.
6. Yeni yorumda Türkçeye özgü harf varsa betik hata verir. Küçük harfler ç, ğ, ı, ö, ş ve ü harfleridir. Büyük harfler Ç, Ğ, İ, Ö, Ş ve Ü harfleridir.
7. Bir kelime listesi Türkçe harfi olmayan Türkçe yorumu yakalar. Örneğin "ile" ve "bu" listededir. Bu kontrol yalnız uyarı verir. Yanlış alarm olabilir.

CI hedef dalı indirmelidir. Bugün iki depoda da `actions/checkout` adımı yalnız son commit'i indirir. Bu durumda fark alınamaz. Bu yüzden adıma `fetch-depth: 0` ayarı eklenir. Bir başka yol da hedef dalı ayrıca çekmektir. Hedef dal yoksa betik hata verir. Betik bu durumda sessizce geçmez.

Denetim eski satırlara bakmaz. Bu yüzden izin listesi gerekmez. AJA-1409 işi bitince denetim bütün dosyalara açılabilir.

Şu dosyalar denetimin dışında kalır:

- Çeviri katalogları dışarıda kalır. Örneğin `tr` kataloğu, `tr.po` ve `messages_tr.properties` dosyaları.
- Türkçe deneme verisi taşıyan test dosyaları dışarıda kalır. Bu dosyalar adıyla listelenir.
- Ekran metni bu denetime girmez. Ekran metnini IC-10 denetimi yakalar.
- `docs/standartlar/` klasöründeki Türkçe belgeler dışarıda kalır. Bu belgeler kod değildir.

Denetimi yazan takım önce dört test yazar:

1. Yeni bir Türkçe yorum denetimi düşürür.
2. Yeni bir İngilizce yorum denetimi geçer.
3. Dokunulmamış eski bir Türkçe yorum denetimi geçer.
4. Hedef dal yoksa denetim düşer.

### Açık soru

Test adları da bir tür metindir. Örneğin `describe('...')` içindeki ad bir test adıdır. Proje sahibinin kararı test adlarını da kapsıyor olabilir. PM bunu AJA-1409 işinde netleştirebilir. Test adları kapsama girerse denetim onlara da bakar.

## 13. Kaynaklar

Bütün web kaynakları 27 Kasım 2026 Cuma günü açıldı. Açılmayan kaynaklar ayrıca yazıldı.

- **[K1]** W3C, Localization vs. Internationalization: https://www.w3.org/International/questions/qa-i18n
- **[K2]** Wikipedia, Internationalization and localization. Bu ikincil bir kaynaktır: https://en.wikipedia.org/wiki/Internationalization_and_localization
- **[K3]** Unicode CLDR, TR35 belgeleri:
  - Birim tercihleri: https://www.unicode.org/reports/tr35/tr35-info.html#Unit_Preferences
  - Birim verisi: https://github.com/unicode-org/cldr/blob/main/common/supplemental/units.xml
  - Ölçü sistemi: https://www.unicode.org/reports/tr35/tr35-general.html#Measurement_System_Data
  - Yerel ayar anahtarları: https://www.unicode.org/reports/tr35/tr35.html#Key_And_Type_Definitions
  - Hafta verisi: https://www.unicode.org/reports/tr35/tr35-dates.html#Week_Data
  - Para verisi: https://www.unicode.org/reports/tr35/tr35-numbers.html#Supplemental_Currency_Data
- **[K4]** ICU ve CLDR mesaj ve çoğul kuralları:
  - ICU MessageFormat: https://unicode-org.github.io/icu/userguide/format_parse/messages/
  - MessageFormat 2: https://www.unicode.org/reports/tr35/tr35-messageFormat.html
  - Çoğul kuralları: https://cldr.unicode.org/index/cldr-spec/plural-rules
- **[K5]** Unicode sıralama ve harf kuralları:
  - UTS #10: https://www.unicode.org/reports/tr10/
  - SpecialCasing: https://www.unicode.org/Public/UCD/latest/ucd/SpecialCasing.txt
- **[K6]** ECMAScript Intl:
  - ECMA-402: https://tc39.es/ecma402/
  - NumberFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat
  - Collator: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
  - PluralRules: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
  - getWeekInfo: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/getWeekInfo
- **[K7]** W3C dil ve yön:
  - Dil bildirimi: https://www.w3.org/International/questions/qa-html-language-declarations
  - Sağdan sola yazı: https://www.w3.org/International/questions/qa-html-dir
  - Strings on the Web, taslak: https://www.w3.org/TR/string-meta/
- **[K8]** W3C, Personal names around the world: https://www.w3.org/International/questions/qa-personal-names
- **[K9]** BCP 47: https://www.rfc-editor.org/info/bcp47 ve IANA dil kaydı: https://www.iana.org/assignments/language-subtag-registry
- **[K10]** IANA saat dilimi veritabanı: https://www.iana.org/time-zones
- **[K11]** Adres ve telefon:
  - libaddressinput: https://github.com/google/libaddressinput
  - libphonenumber: https://github.com/google/libphonenumber
  - ITU E.164: https://www.itu.int/rec/T-REC-E.164
- **[K12]** GOV.UK yazım kılavuzu:
  - A to Z: https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/style-guides/a-to-z-style-guide/
  - Sade dil: https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/
- **[K13]** Yasal metinler:
  - KVKK 6698: https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5
  - UK GDPR: https://www.legislation.gov.uk/eur/2016/679/contents
- **[K14]** Ant Design ve Day.js:
  - Ant Design i18n: https://ant.design/docs/react/i18n
  - ConfigProvider: https://ant.design/components/config-provider
  - Day.js i18n: https://day.js.org/docs/en/i18n/i18n
- **[K15]** Çeviri yönetimi:
  - Weblate: https://github.com/WeblateOrg/weblate
  - Pontoon: https://github.com/mozilla/pontoon
  - XLIFF 2.1: https://docs.oasis-open.org/xliff/xliff-core/v2.1/xliff-core-v2.1.html
- **[K16]** Keycloak yönetici kılavuzu: https://www.keycloak.org/docs/latest/server_admin/index.html#enabling-internationalization

### Frappe kaynakları

- **[F1]** Frappe v16.61.0 kaynak kodu. Dosya yolları 7. bölümdedir.
- **[F2]** Frappe gettext komutları: `frappe/commands/gettext.py` dosyası.
- **[F3]** HRMS v16.54.1 tatil ve bölge modülleri: `hrms/utils/holiday_list.py` ve `hrms/regional/` klasörü.

### Doğrulanamayan kaynaklar

- GALA tanım sayfaları 404 hatası verdi.
- LISA için birincil kaynak bulunamadı.
- ISO 3166 ve ISO 4217 sayfaları 403 hatası verdi.
- AB GDPR metni EUR-Lex sitesinde açılmadı.
- ICO rehberi 403 hatası verdi.
- The Guardian yazım kılavuzu açılmadı.
- ERPNext kaynağı bu makinede yoktu. UOM ve tatil listesi ERPNext satırları doğrulanmadı.
- Keycloak'ın sağdan sola tema desteği doğrulanmadı.
- Keycloak'ın `en-GB` etiketini işleme biçimi doğrulanmadı.
