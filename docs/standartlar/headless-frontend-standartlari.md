# Frappe'ye bağlı ayrı arayüz uygulaması standartları

Ayrı arayüz, Frappe dışında çalışan ekran uygulamasıdır. Buna “headless frontend” denir. Frappe veri ve işlem sunar. Sunucuda [Python belgesini](frappe-python-standartlari.md) ve [Python dışı belgeyi](frappe-python-disi-standartlari.md) izleyin. YAML için de Python dışı belgeyi izleyin. Telefon uygulamasında [mobil belgeyi](mobile.md) izleyin. Az kodla güvenli ekran kurun.

Son kullanıcı yalnız bu arayüzü görür. Frappe'nin yönetim ekranını yalnız yöneticiler kullanır. E-posta ve yazdırma şablonları Frappe'de kalır.

## 1. İşe başlamadan önce

Kuralları okuyun ve işe uyanları uygulayın. **ZORUNLU** kuralda engeli koduyla bildirin. OL-3 engelinde etkilenen işi durdurun ve sorun. Kalan güvenli işi sürdürün ve OL-2 borcunu yazın. **ÖNERİLİR** maddelerini riske göre uygulayın. Seviye etiketi yoksa kural her seviyede geçerlidir.

Önce proje sahibinin kalıcı kurallarını uygulayın. Proje kararlarını okuyun. Daha sıkı karara uyun ve çelişkiyi bildirin. Görsel dil kuralları bu belgede yoktur. Görsel dilde ve erişilebilirlikte proje sahibinin kalıcı arayüz talimatlarını uygulayın.

### Proje sahibinin kararları

Proje sahibi seviyeyi ve boyut sınırını belirler. Yeni paket, teknoloji, mimari ve lisans için karar alın. Dış servis, marka ve misafir erişimi için de karar alın. Eksik karar işi etkilerse KR-3 ile sorun.

### Değişiklikte izlenecek sıra

1. Bildirilen, kilitli ve kurulu sürümü ayırın.
2. Seviyeyi OL-1 kuralıyla öğrenin.
3. Hazır bileşeni ve benzer kodu HZ-1 ile arayın.
4. Sunucu sözleşmesini okuyun. Eksik alan için sözleşme değişikliği önerin.
5. Beklenen sonucu bir örneğe bağlayın.
6. Kod yazmadan önce TE-1 kuralını uygulayın.
7. En küçük değişikliği yapın.
8. Kontrolleri KR-1 ile çalıştırın ve sonucu raporlayın.

## 2. Adlar ve görevleri

| Ad | Nedir? | Uygulamadaki işi |
|---|---|---|
| HTML | Sayfanın yapı dili | Başlık ve formu tanımlar. |
| CSS | Görünüm kuralları | Renk, boşluk ve yerleşimi belirler. |
| Sass ve SCSS | CSS üreten araç ve yazım biçimi | Sass, SCSS dosyasını CSS yapar. |
| JavaScript (JS) | Tarayıcıda çalışan dil | Ekranı çalıştırır. |
| TypeScript | Türleri denetleyen JavaScript yazımı | Tarayıcıya JavaScript olarak gider. |
| React | Ekranı bileşenlerle kuran kitaplık | Ekran parçalarını yeniden kullanır. |
| Ant Design | Hazır arayüz bileşenleri | Form, tablo, menü ve pencere verir. |
| Ant Design X | Yapay zekâ sohbeti bileşenleri | Asistan ekranını kurar. |
| Node.js | JavaScript'i tarayıcı dışında çalıştıran program | Derleme ve test araçlarını çalıştırır. |
| npm | Node.js paket yöneticisi | Paketleri kurar, kilit dosyasını yönetir. |
| Vite | Derleme aracı | Tarayıcı için JS ve CSS üretir. |
| API | Arayüzün sunucuyla konuştuğu uçlar | Frappe verisini taşır. |
| Python | Frappe sunucusunun kod dili | İş kurallarını uygular. |
| JSON | Veri biçimi | İçerik, çeviri ve ayar taşır. |
| Derleme çıktısı | Tarayıcıya sunulan dosyalar | Boyutu bu dosyalarla ölçün. |
| KB | Dosya boyutu birimi | 1 KB 1.000 bayttır. |

Test, çeviri, içerik ve derleme ayarları da kapsamdadır.

## 3. Hazır yol ve teknoloji sınırı

**HZ-1 (ZORUNLU).** Önce ortak kodu, sonra kurulu hazır bileşenleri arayın. İhtiyacı, hazır karşılığı ve kalan farkı yazın. Buna boşluk analizi denir.

**HZ-2 (ZORUNLU).** Kurulu paketin açık arayüzünü tür dosyasından doğrulayın. Değişen kodda eskiyen özelliği düzeltin.

**HZ-3 (ZORUNLU).** Çözülmüş iş için ikinci araç, paket veya kalıp eklemeyin.

**HZ-4 (ZORUNLU).** Yeni paketi mevcut çözüm yetersizse önerin ve onayı bekleyin. İhtiyacı, seçimi ve geri dönüşü yazın. Uyumu, lisansı, bakımı ve açıkları inceleyin. Boyut etkisini BY-5 ile ölçün.

**HZ-5 (ZORUNLU).** Paket sürümünü tam numarayla sabitleyin. Kilidi paket yöneticisiyle güncelleyin. npm ile temiz kurulumda `npm ci` kullanın. Sürümü sabit olmayan aracı ağdan çalıştırmayın.

**HZ-6 (ZORUNLU).** Sürüm yükseltmeyi ayrı iş yapın. Paketlerin birbirinden istediği sürümleri doğrulayın. Doğrudan kullandığınız paketi `package.json` dosyasında bildirin.

**HZ-7 (ZORUNLU).** Mimari kalıbı proje kararından alın. Karar yoksa en yalın yapıyı kurun. Yeni katman, sınıf veya soyutlama için somut gerekçe yazın. Planlamada Python belgesindeki B-7 ile B-9'u uygulayın. Arka uç planındaki terimleri ve sınırları kullanın.

MVC, veri, görünüm ve eylem görevlerini ayırır. MVVM, ekrana hazır durumu ayrı modelde tutar. Kanca, bileşene durum ve davranış ekleyen işlevdir. Sıralı işlemde küçük işlev kullanın. Nesne yönelimli tasarımda derin kalıtım yerine parçaları birleştirin.

## 4. Olgunluk seviyesi

- **PoC, deneme sürümü.** Tek soruyu örnek veriyle sınayın. Hazır bileşen kullanın. Kurumsal katman eklemeyin.
- **MVP, ilk kullanılabilir sürüm.** Gerçek sözleşmeye bağlanın. Kritik akışı sınayın. Paket ve sır taramasını denetime bağlayın.
- **Scale, büyüme sürümü.** BY-2 ve BY-7 kurallarını uygulayın.
- **Enterprise, kurumsal sürüm.** Geri dönüşü sınayın. Eski oturum ve veriyle geçişi deneyin. Gerçek cihaz kanıtı toplayın. Geçici çözümlerin hepsini kapatın.

**OL-1 (ZORUNLU).** Seviyeyi proje kaydından alın. Ekranın seviyesi farklıysa yazın. Eksik seviye kapsamı etkilerse proje sahibine sorun. Kararı kaydedin.

**OL-2 (ZORUNLU).** Teknik borç, bilerek bırakılan eksiktir. Borcu örneğin `BORC(scale)` yorumuyla işaretleyin. Eksiği, etkisini, sorumlusunu ve kapanma koşulunu yazın. JSON borcunu proje kaydına yazın.

**OL-3 (ZORUNLU).** Güvenliği, veri bütünlüğünü, erişilebilirliği ve önce testi koruyun. Gerçek veri veya dış erişimde MVP kurallarını uygulayın. Geçişi engelleyen borcu kanıtla kapatın.

## 5. Sunucu sözleşmesi ve veri

Sözleşme, arayüz ile sunucunun anlaştığı istek ve yanıt biçimidir.

**SZ-1 (ZORUNLU).** İş kuralını ve hesabı sunucuda tutun. Sunucu sonucunu gösterin. Tutarı ve vergiyi yeniden hesaplamayın.

**SZ-2 (ZORUNLU).** Rol, kayıt ve alan iznini sunucu doğrulasın. Başka hesaba ait kaydı, yazmayı ve indirmeyi sınayın. Rota koruması yalnız gezinmeyi yönetir.

**SZ-3 (ZORUNLU, MVP ve üstü).** Önce istek, yanıt, hata ve yetki sözleşmesini yazın. OpenAPI bir sözleşme biçimidir. Türleri sözleşmeden üretin. Üretilen tür eskiyse denetim başarısız olsun.

**SZ-4 (ZORUNLU).** Yanıtı ekrandan önce şemayla denetleyin. Şema, izinli alanları ve türleri tanımlar. Denetimi elle de yazabilirsiniz. Geçersiz yanıtı reddedin.

**SZ-5 (ZORUNLU).** Bileşen dışındaki ortak API istemcisini kullanın. İptali, zaman aşımını ve oturumu burada yönetin. Durum kodunu ve içerik türünü denetleyin.

**SZ-6 (ZORUNLU).** Uygulamaya açılmış veri uçlarını kullanın. Genel kayıt ucunu kullanacaksanız bağımlılığı kaydedin. İzinleri, alanları ve sürümü sınayın. Uç ayrıntısını istemcide tutun.

**SZ-7 (ZORUNLU).** Çerezli oturumda HTTPS ve çerez bayraklarını doğrulayın. Çerezli yazmada `X-Frappe-CSRF-Token` başlığını ekleyin. CSRF, başka sitenin oturumla işlem başlatma riskidir. Sunucu belirteci üretsin ve aynı oturuma güvenle versin. Belirteci bellekte tutun. Eksik veya yanlış belirtecin reddini sınayın.

**SZ-8 (ZORUNLU).** Hatayı istemcide çevirin. API v1 için `exc_type` alanını kontrol edin. API v2 için `errors` listesini kontrol edin. Alan eksikse durum kodunu ve içerik türünü kullanın. Yetki reddini oturum bitiminden ayırın. Belirsiz 403 için oturumu ayrı, önbelleksiz istekle doğrulayın. Ham gövdeyi ve hata izini göstermeyin.

**SZ-9 (ZORUNLU).** Saat dilimini, para birimini ve yuvarlamayı sözleşmeye yazın. Eksik alanı, `null` ve boş değeri ayırın.

**SZ-10 (ZORUNLU).** Sayfalamayı, süzmeyi ve sıralamayı sunucuda yapın. İstekte gereken alanları ve sayfa sınırını verin.

**SZ-11 (ZORUNLU).** Sunucu yazmada kayıt sürümünü denetlesin. Okunan kaydın `modified` değerini güncellemede aynen gönderin. Mobil eşitlemede sürüm için ES-6 önceliklidir. Çakışmada taslağı koruyun ve yeni sürümü gösterin.

**SZ-12 (ZORUNLU).** Örnek sunucuyu sözleşmeden kurun. Ekranda “Örnek veri” yazın. Örnek veride gerçek kişi bilgisi kullanmayın. Örnek sunucuda yetki reddini de sınayın. İşlenmeyen isteği hata sayın ve dış ağa bırakmayın.

**SZ-13 (ZORUNLU).** Sözleşme değişince iki tarafı birlikte değiştirin. Ayrı yayımlanıyorsa geçişte eski ve yeni alanı destekleyin.

**SZ-14 (ZORUNLU).** GET isteğiyle veri değiştirmeyin. Çerezli bağlantıda aynı kökeni seçin. Kökeni protokol, sunucu adı ve kapı numarası belirler. Başka köken gerekiyorsa `allow_cors` ayarında tam adresleri belirtin. Frappe `sid` çerezini `SameSite=Lax` ile yazar. CORS, başka siteden gelen API isteğine çerez ekletmez. Aynı sitede başka kökende `credentials: "include"` kullanın.

**SZ-15 (ZORUNLU).** Çift gönderimi ve belirsiz sonucu sınayın. Sunucu güvencesi yoksa yazmayı kendiliğinden yinelemeyin. Sonuç belirsizse kayıt durumunu okuyun. Geçici başarıyı hata sonrası geri alın.

## 6. TypeScript

**TS-1 (ZORUNLU).** TypeScript sürümünü ve geçerli ayarı doğrulayın. Tarayıcı, Node.js ve test kapsamlarını denetleyin.

**TS-2 (ZORUNLU).** Tür denetimini ayrı çalıştırın. Vite derlemesi TypeScript tür denetimi yapmaz.

**TS-3 (ZORUNLU).** Yeni projede `strict` açın. Mevcut sıkı ayarı koruyun. Mevcut projede yeni bayrak açmayı ayrı iş yapın.

**TS-4 (ZORUNLU).** Tür hatasını `any`, `as`, `!` veya `@ts-ignore` ile gizlemeyin. Bu yazımlar çalışma anında denetim eklemez. Dar istisnanın nedenini ve kaldırma koşulunu yazın.

**TS-5 (ZORUNLU).** Dış veriyi `unknown` sayın ve şemayla daraltın. API yanıtı, çalışırken yüklenen JSON ve tarayıcı deposu dış veridir. Adres parametresi de dış veridir.

**TS-6 (ZORUNLU).** Türü sözleşmeden veya şemadan türetin. Üretilen türü elle değiştirmeyin.

**TS-7 (ZORUNLU).** Ekran durumunu birleşim türüyle yazın. Birkaç mantıksal bayrağı birlikte kullanmayın.

**TS-8 (ZORUNLU).** Dizi ve nesne erişiminde eksik değeri ele alın. `strict` bu hatayı tek başına yakalamaz.

**ÖNERİLİR.** Yeni projede `noUncheckedIndexedAccess` ve `verbatimModuleSyntax` bayraklarını açın. `target`, `module`, `moduleResolution` ve `types` ayarını açıkça yazın.

## 7. React bileşenleri ve durum

**RE-1 (ZORUNLU).** İşlev bileşeni ve kanca kullanın. Hata sınırı, alt bileşenin çizim hatasını yakalar. Hazır sınıra güvenli başlık ve açıklama verin. Ham hatayı ve izini göstermeyin.

**RE-2 (ZORUNLU).** Bileşeni saf tutun. Çizim sırasında doğrudan veri çekmeyin ve depoya yazmayın.

**RE-3 (ZORUNLU).** Hesaplanabilen değeri durumda tutmayın. Kullanıcı eylemini olay işleyicisinde ele alın. Etkiyle dış sistemi eşitleyin. Aboneliği, dinleyiciyi ve zamanlayıcıyı temizleyin.

**RE-4 (ZORUNLU).** Her durumun tek sahibi olsun. Sunucu verisini sorgu önbelleğinde tutun. Paylaşılacak süzgeci, sayfayı ve sekmeyi adrese yazın. Form taslağı formda kalsın. Yön ve boyut değişiminde kullanıcının girdisini koruyun.

**RE-5 (ZORUNLU).** Sunucu verisini bileşen durumuna kopyalamayın. Yazma sonrası ilgili sorguyu yenileyin. Önbellek anahtarına hesap ve sorgu kapsamını katın. Bekleyen yerel iş varsa CK-1'i uygulayın. Çıkış kesinleşince yerel erişimi kapatın. Hesaba ait bekleyen ağ isteklerini iptal edin. Sunucu oturumu ya da belirteç varsa CK-5'i uygulayın. Yerel veri ya da belirteç varsa CK-2 ile CK-4'ü uygulayın. Özel sorgu önbelleğini temizleyin.

**RE-6 (ZORUNLU, MVP ve üstü).** Her veri ekranında dört durumu çizin. Durumlar yükleniyor, boş, hata ve yetkisizdir. Hata durumunda yeniden deneme yolu verin.

**RE-7 (ZORUNLU).** Eski isteği iptal edin. Geç yanıt yeni durumu ezmesin. Bunu sınayın.

**RE-8 (ZORUNLU).** Ayrı sorumlulukları görünüm, kanca veya işleve bölün. Liste anahtarına kararlı kimlik verin. `useMemo` için maliyeti veya kimlik gereğini gösterin.

**RE-9 (ZORUNLU).** Rota sözleşmesini tek yerde tutun. Tarayıcının geri tuşunu sınayın.

**RE-10 (ZORUNLU).** Anlamlı HTML etiketi ve etiketli form alanı kullanın. Pencere kapanınca odağı açan düğmeye döndürün. Her eyleme klavyeyle ulaşılsın.

**RE-11 (ZORUNLU).** Sunucu sayfa tanımını DocType tanımından üretsin. Sayfa tanımı yalnız veri taşısın. Tanıma kod ve yetki koymayın. Yüksek gizlilik işaretini tanımda verin. Çizimden önce tanımı şemayla denetleyin. Sayfayı onaylı katalogdaki bileşenlerle çizin. Gereken bütün bileşenleri ve alan türlerini kataloğa alın. Örneğin form, tablo, rapor, grafik, harita, imza ve dosyayı ekleyin. Kataloğu sürümleyin ve proje kaydına yazın. Telefon paketi varsa çizim kodunu ilk mağaza paketine koyun. Gereken eklentileri de bu pakete koyun. Sunucu yalnız izin listesindeki sayfaları telefona açsın. Her istekte KP-5 ile yetkiyi denetleyin. İnternetsiz açılacak sayfanın tanımını önceden eşitleyin. VR-6 kapsamındaki kayıtlarını da eşitleyin. İnternet yoksa kapsamdaki son geçerli tanımı kullanın. Eşitlemede AU-1, AU-2 ve ES-2'yi uygulayın. Katalogda olmayan bileşen ya da alan türü mağaza sürümü ister. Kurulu sürüm bileşeni ya da alan türünü tanımıyorsa GN-7'yi uygulayın.

## 8. Ant Design

**AD-1 (ZORUNLU).** Ant Design değerlerini `ConfigProvider` içinde `theme.token` ve `theme.components` ile verin. Token, adı olan tasarım değeridir. CSS ile `ConfigProvider` aynı kaynağı kullansın. Tema değerini sunucudan veri olarak alabilirsiniz. Gelen değeri SZ-4 ile denetleyin. İnternet yoksa son geçerli temayı kullanın.

**AD-2 (ZORUNLU).** Önce tokenı, sonra `classNames` ve `styles` alanlarını kullanın. Değişebilen `.ant-` iç sınıflarından kaçının. Zorunlu uyarlamayı ortak dosyada gerekçesiyle tutun. Kaldırma koşulunu yazın.

**AD-3 (ZORUNLU).** `antd/es` ve `antd/lib` yollarını kullanmayın. Gerekirse `@ant-design/cssinjs` paketinden `StyleProvider` alın. `layer` ile kitaplık stilini katmana koyun. `!important` yazmayın. Zorunluysa nedenini yazın.

**AD-4 (ZORUNLU).** `ConfigProvider` altında `App` kullanın. Mesajı, bildirimi ve onayı `App.useApp` ile açın.

**AD-9 (ZORUNLU).** Tabloya kararlı `rowKey` verin.

**AD-10 (ZORUNLU).** Form doğrulamasını sunucu sözleşmesine bağlayın. Gönderim sürerken yinelenen isteği önleyin.

**AD-11 (ZORUNLU).** Simgeyi açık adıyla içe aktarın. Dili `ConfigProvider` ile verin. Türkçe Day.js tarih seçicisinde `dayjs/locale/tr` dosyasını yükleyin.

## 9. Ant Design X ve yapay zekâ yüzeyi

**AX-1 (ZORUNLU).** Yapay zekâ odaklı ekranda kayıt için Ant Design kullanın. Sohbet için Ant Design X kullanın. `Pro Components`, `X SDK`, `X Markdown` ve `X Cards` isteğe bağlıdır.

**AX-2 (ZORUNLU).** Model anahtarını sunucuda tutun. İsteği kendi sunucunuzdan geçirin. Modele genel Frappe erişimi vermeyin.

**AX-3 (ZORUNLU).** Model çıktısını güvenilmez sayın. `XMarkdown` form, stil ve dış görseli bırakabilir. `dompurifyConfig` ile bunları engelleyin. Gerekirse ham HTML'i düz yazı verin.

**AX-4 (ZORUNLU).** Onaylı katalogdan ekran çizin. Katalog adresini çizimden önce doğrulayın. Çıktının türünü, alanlarını ve boyutunu sınayın. Kritik kayıtta ve onayda sabit ekran kullanın. Serbest HTML, CSS veya bileşen kodu çalıştırmayın.

**AX-5 (ZORUNLU).** Akış parçasını doğrulayın. İptali, geç yanıtı ve kopmayı sınayın. Zaman aşımından sonra yeni `XRequest` örneği kurun. Yeniden denemeyi sınırlayın. Durdurma, hata ve yeniden bağlanmayı gösterin. Sahte ilerleme veya iç düşünce göstermeyin.

**AX-6 (ZORUNLU).** Okuma ve yazma araçlarını ayırın. Yazma öncesi farkı gösterin ve onay alın. Sunucu yetkiyi ve onayı doğrulasın.

**AX-7 (ZORUNLU).** Hesabı, kapsamı, modu, kaynağı ve veri zamanını gösterin. Uzun işin durumu yeniden açılabilsin. Kural tabanlı cevabı canlı yapay zekâ gibi sunmayın.

**AX-8 (ZORUNLU).** Sohbet günlüğünü saran öğeye `role="log"` verin. Yeni mesajı ekran okuyucuyla sınayın. Yüklenme durumunu metinle bildirin.

**AX-9 (ZORUNLU).** X dil alanlarını Ant Design Türkçe dil nesnesiyle birleştirin.

## 10. Stil: CSS, SCSS ve Sass

**ST-2 (ZORUNLU).** Tarayıcıda değişen değeri CSS değişkeniyle yazın.

**ST-3 (ZORUNLU).** Projenin stil dilini izleyin. Düz CSS kullanan projeye SCSS eklemeyin.

**ST-4 (ZORUNLU).** Sass modüllerinde `@use` ve gerekirse `@forward` kullanın. Eski Sass `@import` yolunu çoğaltmayın. Derleme bölmesinde `math.div`, tarayıcı hesabında `calc()` kullanın.

**ST-5 (ZORUNLU).** Sass değerini CSS değişkenine `#{...}` ile yazın. Sayısal `@container` eşiğinde de kullanın. Tırnağı `meta.inspect` ile koruyun.

**ST-6 (ZORUNLU).** Temel bildirimi iç içe kuraldan ve `@include` satırından önce yazın. Sonraki bildirim aynı öncelikteki koşullu stili ezebilir.

**ST-7 (ZORUNLU).** Dar ve düşük öncelikli seçici kullanın. Genel seçiciyi temel katmanda tutun. `@extend` yerine ortak sınıfı veya `@mixin` seçin.

**ST-12 (ZORUNLU).** Yeni Sass uyarısını giderin. Stil denetiminin kullanılan dosya türlerini okuduğunu doğrulayın.

## 11. İçerik ve çeviri dosyaları

**IC-1 (ZORUNLU).** Görünen metni koda gömmeyin. Metni çeviri veya içerik dosyasından alın. Cümleyi parçalardan birleştirmeyin. Değer için yer tutucu kullanın.

**IC-2 (ZORUNLU).** Türkçeyi yalın yazın ve yazım denetimini çalıştırın.

**IC-3 (ZORUNLU).** Anahtar, çoğul ve yer tutucuyu diller arasında denetleyin. Eksik çeviride davranışı sınayın. Gereken çevirileri yükleyin.

**IC-4 (ZORUNLU).** İçerik JSON dosyasını derleme denetiminde şemayla sınayın. Dışarıdan gelen içeriği kullanmadan önce yine sınayın.

**IC-5 (ZORUNLU).** Büyük içeriği ilk dosyaya statik olarak bağlamayın. Dinamik içe aktarmayı veya ayrı JSON isteğini ölçün.

**IC-6 (ZORUNLU).** Düz JSON dosyasına yorum ve sondaki virgül koymayın. Yinelenen anahtarı veriyi ayrıştırmadan önce yakalayın. Büyük tamsayıyı ve kimliği metinle koruyun. Tarihi ISO 8601 biçiminde saklayın.

**IC-7 (ZORUNLU).** İçerik dosyasına gizli bilgi, kişisel veri ve iç adres koymayın. İçerikteki HTML'i temizlemeden basmayın.

**IC-8 (ZORUNLU).** Üretilen JSON dosyasını elle düzenlemeyin.

## 12. Güvenlik

**GV-1 (ZORUNLU).** Tarayıcı çıktısını açık sayın. Her `VITE_` veya Astro `PUBLIC_` değeri istemci koduna girebilir. API anahtarını ve gizli değeri tarayıcıya koymayın.

**GV-2 (ZORUNLU).** `dangerouslySetInnerHTML` ve `innerHTML` kullanmayın. Zorunluysa temizleyici kullanın ve tek ortak bileşende toplayın.

**GV-3 (ZORUNLU).** Bağlantı türünü ve hedefini izin listesiyle doğrulayın. İç yönlendirmede aynı kökeni doğrulayın.

**GV-4 (ZORUNLU).** Tarayıcı deposuna oturum belirteci ve gizli veri yazmayın. Kalıcı depoya yalnız gereken alanı yazın.

**GV-5 (ZORUNLU).** Kaynak haritasının canlı yayını için proje kararını doğrulayın.

**GV-6 (ZORUNLU).** Dış betik, yazı tipi ve izleme aracı karar ister. `postMessage` kaynağını, kökenini ve verisini doğrulayın. İçerik güvenlik politikasını yayımlanan yanıtta sınayın.

**GV-7 (ZORUNLU).** Hata kaydına ve konsola kişisel veri yazmayın. `console.log` satırını teslimden önce silin.

**GV-8 (ZORUNLU).** Gerçek `.env` dosyasını depoya koymayın. Geçici ajan dosyasını depoya veya `public` alanına koymayın.

## 13. Uyarlanır teslim (adaptive delivery)

**MB-5 (ZORUNLU).** Temel akış tarayıcı ipucu gelmeden de çalışsın. Gerekmeyen JS, CSS ve görseli koşullu yükleyin. Üretim dosya listesini ağ istekleriyle eşleyin. Önyüklemeyi ve önbelleği de ölçün.

## 14. Hız ve boyut sınırı

Gzip dosyayı sıkıştırır. Parça, derlemenin ayrı JavaScript dosyasıdır.

**BY-1 (ZORUNLU).** Onaylı sınırı proje kaydında veya denetim ayarında arayın. Onay belirsizse ölçüp sınır önerin. İlk açılışı, tek parçayı ve toplamı ayrı değerlendirin. Ham, sıkıştırılmış ve gerçek aktarımı ayrı ölçün.

**BY-2 (ZORUNLU, Scale ve üstü).** Sınırı derleme çıktısını ölçen otomatik denetime bağlayın. Mevcut denetim yolunu kullanın. Ortak dosyayı bir kez sayın. Aşımda denetim başarısız olsun. Vite parça uyarısı derlemeyi durdurmaz.

**BY-3 (ZORUNLU).** Sınırı sessizce büyütmeyin. Aşımda önce kendi kodunuzu küçültün. Yetmezse seçenek sunun. Sınırı yalnız proje sahibi yükseltir. Kararı tarihiyle kaydedin.

**BY-4 (ZORUNLU).** Ağır ekranı veya özelliği gerekince yükleyin. Örneğin raporu dinamik `import()` ile açın. Ortak girişin erken yüklemediğini MB-5 ile sınayın.

**BY-5 (ZORUNLU).** Yeni paketin boyut etkisini deneme kurulumunda ölçün. İki derleme çıktısını aynı koşullarda karşılaştırın.

**BY-6 (ZORUNLU).** Önce olanı ve kullanıcıya etkisini yazın. Açılış etkisi bilinmiyorsa belirtin. Neyi ölçtüğünüzü, sınırı ve kalan payı yazın. Önceki ve yeni boyutu gösterin. Gereken adımı ve karar sahibini belirtin.

**BY-7 (ZORUNLU, Scale ve üstü).** Uzun listeyi, yavaş ağı ve zayıf cihazı sınayın. Sunucu bekleme süresini tarayıcı işinden ayırın. Aktarımda görseli, yazı tipini ve veriyi ölçün.

**Örnek uyarı**

> Telefona giden sıkıştırılmış kodun boyutu sınıra yaklaştı. Kod büyürse uygulama daha geç açılabilir. Bu etkiyi henüz ölçmedim. KB, dosya boyutu birimidir. Kod önce 1.117 KB idi. Şimdi 1.120,6 KB. Sınır 1.125 KB. Kod 4,4 KB daha büyürse sınıra ulaşır. Şimdilik bir şey yapmanız gerekmiyor. Sınırı aşarsam önce kodu küçülteceğim. Sınırı yalnız siz yükseltebilirsiniz.

## 15. Modül sınırı, bağımlılık ve SOLID

Modüler monolit, modüllerin tek uygulama olarak çalışmasıdır. Düşük bağımlılık, bir değişikliğin başka dosyalara yayılmasını azaltır.

**MD-1 (ZORUNLU).** Dosyaları kullanıcı işine göre gruplayın. Başka modülü açık girişinden kullanın. İç dosyasını doğrudan almayın.

**MD-2 (ZORUNLU).** Bağımlılık kabuktan modüle, modülden ortak koda gitsin. Döngüyü reddedin. Sınırı statik ve dinamik aktarmada denetleyin. MVP ve üstünde bu denetimi proje denetimine bağlayın. İhlalde denetim başarısız olsun. Mevcut denetim yolunu kullanın. Git kancası için açık onay alın. Yeni araçta HZ-4'ü uygulayın. PoC'de eksik denetimi `BORC(mvp)` ile işaretleyin.

**MD-3 (ZORUNLU).** Ortak bileşeni tek bir ekran için değiştirmeyin.

**MD-4 (ZORUNLU).** Genel depo, olay yolu ve bağlam gizli bağ kurar. Bu bağı proje kaydına yazın.

**MD-5 (ZORUNLU).** Ad ve sözleşme değişince kullananları bulun. Ekran, stil, çeviri, tür, test ve sözleşmeyi tarayın. Aynı kavrama aynı adı verin.

**MD-6 (ZORUNLU).** Ayrı uygulama ve mikro arayüz için somut gerekçe yazın. Önemli kararı ve geri dönüşü proje kaydına yazın.

**MD-7 (ZORUNLU).** Modül veya ortak bileşen sınırı değiştiğinde SOLID ilkelerini inceleyin. Etkisini ve sınadığınız davranışı rapora yazın.

SOLID ilkeleri bu uygulamaya şöyle uyar:

- **SRP, tek sorumluluk.** Bir bileşen tek iş yapsın. Görünüm çizsin, kanca durumu taşısın.
- **OCP, genişletmeye açıklık.** Yeni durumu özellik veya yuva ile ekleyin. Ortak bileşeni kopyalamayın.
- **LSP, yerine geçebilme.** Gerçek ve örnek istemci aynı sözleşmeye uysun. İkisini aynı davranış testinden geçirin.
- **ISP, arayüz ayrımı.** Bileşene yalnız kullandığı alanı verin. Bütün kaydı vermeyin.
- **DIP, bağımlılığı tersine çevirme.** Ekran kendi veri sözleşmesine bağlansın. Frappe ayrıntısını bağlantı kodu taşısın.

## 16. Önce test ve doğru sonucun kaynağı

Testin doğru sonucu nereden alacağına “oracle sorunu” denir.

| İş | Önce yazılacak denetim |
|---|---|
| Kanca ve yardımcı işlev | Birim testi |
| Bileşen | Rol ve etiketle davranış testi |
| Ekran akışı | Tarayıcı testi |
| Sunucu bağı | Sözleşmeden kurulan örnek sunucu testi |
| Çeviri ve içerik | Anahtar ve şema denetimi |

**TE-1 (ZORUNLU).** Davranış değişikliğinde veya hata düzeltmesinde önce testi yazın. Testin beklenen nedenle başarısız olduğunu görün. Düzeltmeden sonra aynı testi çalıştırın.

**TE-2 (ZORUNLU).** Beklenen sonucu sözleşmeden veya bağımsız örnekten alın. Kaynak yoksa proje sahibinden örnek onayı alın. Beklenen değeri değişen koddan kopyalamayın.

**TE-4 (ZORUNLU).** Öğeyi rol ve etiketle bulun. Sınıf adına ve iç yapıya bağlı test yazmayın.

**TE-5 (ZORUNLU).** Riske göre Chrome ve Safari ailesinde sınayın. İzole Chromium ve WebKit kullanılabilir. Açık istek olmadan Firefox'u, kişisel tarayıcıyı ve profilini kullanmayın. Yüzeysel testte yalnız açılışı ve temel akışı sınayın. Bu testte tarayıcı başına 5 dakikayı, toplam 20 dakikayı aşmayın.

**TE-6 (ZORUNLU).** Sabit bekleme süresi kullanmayın. Ağı örnek sunucuyla, saati sabit değerle yönetin.

**TE-7 (ZORUNLU).** Denetimin hatalı örneği gerçekten reddettiğini görün. Denetimi geçirmek için kuralı gevşetmeyin.

## 17. Kontroller ve rapor

**KR-1 (ZORUNLU).** Mevcut tür, kod, test ve derleme kontrollerini kendiniz çalıştırın. Geçtiyse `pass`, kaldıysa `fail` yazın. Çalışmadıysa `not_run`, kapsam dışıysa `not_applicable` yazın. İkisinde de neden yazın.

**KR-2 (ZORUNLU).** Değişikliği istenen işle sınırlayın. Kuralları yeni ve değişen satıra uygulayın. Eski satırı sırf kurala uydurmak için değiştirmeyin. Gördüğünüz güvenlik ve veri sorununu bildirin.

**KR-3 (ZORUNLU).** Yalın Türkçe yazın. Önce olanı ve proje sahibine etkisini söyleyin. Sonraki adımı ve karar sahibini yazın. Soruda seçenekleri ve önerinizi verin. Komut ve çıktıyı sona koyun. Terimi ilk kullanımda açıklayın.

**KR-4 (ZORUNLU).** Yetki ve ortak bileşen değişikliğini bağımsız incelemeye verin. İnceleme yapılamazsa bunu raporlayın.

**KR-5 (ZORUNLU).** Komutu, tarayıcı adını, sürümünü ve işletim sistemini yazın. Kanıtı ekleyin. Gerçek tarayıcı ve cihaz sonuçlarını benzetimden ayırın.

**KR-7 (ZORUNLU).** Git yazar korumasını ve `core.hooksPath` ayarını değiştirmeyin. Canlıya yüklemek için onay alın. Açık `cron` isteği olmadan iş zamanlamayın. Kurulum veya kullanım değiştiyse proje belgesini güncelleyin.

## Ek A. Proje kaydına yazılacaklar

Proje talimatında şu bilgileri kaydedin.

- Seviye, kurulu sürümler ve paket yöneticisi.
- Mimari kalıp, klasör düzeni ve bağımlılık yönü.
- Stil dosyalarının yazım dili. Örneğin CSS ya da SCSS.
- Sözleşme dosyası, tür üretme komutu ve örnek sunucu.
- Oturum yolu ve kararların yeri.
- Bileşen kataloğu, sürümü ve telefon eklentileri.
- Boyut sınırları, ölçüm koşulları ve karar tarihleri.
- Test tarayıcıları ve desteklenen diller.
- Üretilen dosyalar ve üreten komut.
- Teknik borcun sorumlusu ve kapanma koşulu.

## Ek B. Doğrulanan davranışlar

Frappe satırları 15.126.1 ve 16.56.0 kaynaklarına dayanır. Sürüm değişince yeniden sınayın. Kullanımdan kalkan kodlar: AD-5, AD-6, AD-7, AD-8, ST-1, ST-8, ST-9, ST-10, ST-11, ST-13, MB-1, MB-2, MB-3, MB-4, MB-6, TE-3, TE-8 ve KR-6. Bu kodları yeniden kullanmayın.

| Konu | Görülen davranış |
|---|---|
| TypeScript 6.0.3 | 5.9.3 ile `strict` ve modül varsayılanları farklıdır. |
| MSW 3.0.3 | Eşleşmeyen istek ağa gidebilir. `onUnhandledFrame: "error"` ile durdurun. |
| Frappe CSRF | Oturumda belirteç yoksa çekirdek denetimi atlar. Uygulama belirteç sağlamalıdır. |
| Frappe CORS | `allow_cors: "*"` gelen kökeni yanıta yazar. Yanıt kimlik bilgisine izin verir. |
| Frappe hatası | API v1 `_server_messages` alanı iki kez kodlanır. `TimestampMismatchError` ve `ValidationError` 417 döner. |
| Oturum bitimi | Çerezli akışta giriş isteyen işlev `sid` yoksa 403 döner. Gelen `sid` için kayıt yoksa `session_expired` yazılır. İşaret varsa 15'te 403, 16'da 401 döner. `/api/method/frappe.auth.get_logged_user` geçerli oturumda kullanıcıyı `message` alanına yazar. |
| Frappe listesi | Varsayılan sayfa sınırı 20 kayıttır. Frappe 16 API v2 `has_next_page` verir. Liste yanıtında toplam sayı yoktur. |
| Frappe kaydı | API v1 kayıt okumasında `null` alan atlanabilir. API v1 ve v2 güncellemesinde `modified` yoksa eski taslak yakalanmaz. |
| Frappe verisi | Olağan tarih saat metni saat dilimi taşımaz. Maskesiz para alanı kayan noktalı sayıdır. |
| Tablo | WebKit 27.2 denemesinde sütun `minWidth` etkisiz kaldı. Ant Design 6.7.0 `scroll.x` kutusu Tab ile odaklanmadı. |
| Klavye tuzağı | İleri Tab, boş `Input.OTP` ve 6.7.0 boş `RangePicker` denemelerinde takıldı. |
| X SDK 2.9.0 ve 2.10.0 | Zaman aşımından sonra aynı `XRequest` örneği yanıtı işleyemez. Yeniden deneme açıksa `retryTimes` üst sınır koyar. |
| X Cards 2.9.0 ve 2.10.0 | `Box` kayıt dışı katalog adresini isteyebilir. Katalog doğrulaması tek başına çizimi durdurmaz. |
