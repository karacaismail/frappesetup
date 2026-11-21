# Frappe ve Python kod standartları

Bu kuralları Frappe'de Python yazan ajan uygular. Az kodla güvenli, hızlı ve bakımı kolay uygulama geliştirin. Python dışı dosyalarda [Python dışı belgeye](frappe-python-disi-standartlari.md) bakın. Tanım, `fixtures` ve `patches.txt` bu kapsamdadır.

## 1. İşe başlamadan önce

Kod veya kayıt tanımı yazmaya karar vermeden önce kuralları okuyun. Zorunlu kuralda engel varsa kodunu bildirin. Öneride riske, serbest seçimde ihtiyaca bakın. ÖNERİLİR ve SERBEST etiketleri paragrafı kapsar. Diğer talimatlar kendi koşullarında zorunludur.

Doğruluğu, sürüm uyumunu ve güvenliği koruyun. Frappe'nin koşullarını ve proje kararlarını uygulayın. Kural yoksa yakın kodu izleyin. Çelişkinin etkisini raporlayın. Proje sahibinin kalıcı talimatlarını uygulayın.

### Proje sahibinin kararları

Proje sahibi sonucu, seviyeyi, hız ve boyut sınırlarını belirler. Teknoloji, lisans ve misafir erişimi kararını kayıttan okuyun. Silme, toplu yazma ve canlıya yüklemede işin onayını doğrulayın. Eksik onay işi etkiliyorsa sorun. Soru ve raporda R-8'i uygulayın.

Son kullanıcı yalnız ayrı arayüzü görür. Frappe'nin yönetim ekranını yalnız yöneticiler kullanır. E-posta ve yazdırma şablonları Frappe'de kalır. Görsel dil kuralları bu belgede yoktur. Telefon uçlarında `mobile.md` belgesinin 13. bölümüne uyun.

### Davranış değişikliğinde izlenecek sıra

1. Proje talimatlarını ve yakın kodu okuyun.
2. Ek A'daki proje kaydından olgunluk seviyesini öğrenin.
3. Sürüm aralığını proje ayarından okuyun. `pyproject.toml` yorumunu aralık saymayın. Çalışan Frappe ve Python sürümlerini doğrulayın. Sözdizimini desteklenen en eski Python sürümüne göre seçin.
4. Hazır özelliği ve benzer kodu bulun. A-1 kapsamındaki farkı yazın.
5. Planı B-7'ye göre yazın.
6. Beklenen sonucu bir örneğe bağlayın. Hata veya yetki reddini de yazın.
7. Testi önce yazıp çalıştırın. Beklenen nedenle başarısız olduğunu doğrulayın.
8. Testi geçiren en küçük değişikliği yapın.
9. İlgili kontrolleri çalıştırın ve sonucu raporlayın.

## 2. Hazır özellikler ve teknoloji seçimi

Boşluk analizi, istenen işle hazır çözüm arasındaki farkı bulur. İngilizcesi “gap analysis” sözüdür. DocType, “Sipariş” gibi bir kayıt türünün tanımıdır.

| İhtiyaç | Hazır yol |
|---|---|
| Alan zorunlu, tekil veya seçimli olsun. | DocType alan ayarları |
| Kayıt sırayla onaylansın. | “Workflow” |
| Olayda e-posta gitsin. | “Notification” |
| Kayıt bir kişiye atansın. | “Assignment Rule” |
| Kayıtlar süzülüp listelensin. | “Report Builder” |
| Kayıt yazdırılsın. | “Print Format” |
| Son kullanıcı ekranı gerekir. | Ayrı arayüz ve uç (A-7). Girişsiz uç G-7'ye girer. |
| Erişim kişiye veya role göre değişsin. | Kullanıcı ve rol izinleri |

**A-1 (ZORUNLU).** Yeni özellikte veya mevcut çözüm yetmiyorsa boşluk analizi yapın. Kurulu uygulamalara da bakın. İhtiyacı, hazır karşılığı ve kalan farkı raporlayın. Farkı giderecek en küçük işi seçin. Ertelenen farkı kaydedin. Hazır akış iş kuralını değiştiriyorsa proje kararına bakın.

**A-2 (ZORUNLU).** Yeni koddan önce benzer çözümü arayın. Çözümü ve yeniden kullanma kararını raporlayın.

**A-3 (ZORUNLU).** Kurulum ayarlarını Git'te saklayın. Git, dosya geçmişini tutar. Gerekirse “Custom Field” ve “Property Setter” ayarlarını `fixtures` ile taşıyın. Eşitleme, depodaki ayarı siteye yazar. Dosyalardan gizli bilgiyi ve kişisel veriyi çıkarın.

**A-4 (ZORUNLU).** Kalıcı iş kuralını uygulama koduna yazın. “Server Script” ve “Client Script” ekranları kodu veritabanında saklar. Yönetim ekranının kodunu form betiğinde tutun.

**A-5 (ZORUNLU).** Yalnız istenen işi yapın. İleride gerekebilir diye seçenek veya katman eklemeyin.

**A-6 (ZORUNLU).** Yerini aldığınız kodun çağıranlarını bulun. Kullanılmadığı doğrulanan eski kodu kaldırın. Dışarıya açık işlev değişirse geçişi planlayın.

**A-7 (ZORUNLU).** Son kullanıcı ekranını ayrı arayüzde kurun. Son kullanıcı için Frappe sayfası yalnız arayüz kabuğu olabilir. Son kullanıcıya “Web Form” açmayın. Hazır portal sayfalarını kapatın.

**ÖNERİLİR.** İş kuralı dışındaki üçüncü tekrarda ortak işleve bakın. Kopyalar ayrı nedenlerle değişiyorsa ayrı kalabilir. İş kuralında M-2 geçerlidir.

### Yeni araç eklemeden önce (technology boundary)

Araç, teknoloji, framework, paket ve mimari kalıbı kapsar. Paket, projeye eklenen hazır koddur.

**T-1 (ZORUNLU).** Mevcut araç işi çözüyorsa ikinci araç eklemeyin. Örneğin arka plan işi için önce `frappe.enqueue` işlevine bakın. Yetki ve istek yönlendirme için Frappe'nin hazır yollarını inceleyin.

**T-2 (ZORUNLU).** Yeni aracı mevcut çözüm yetmiyorsa değerlendirin. İhtiyacı, seçenekleri ve seçim nedenini karar kaydına yazın. Paketin varlığını resmî kaynaktan doğrulayın. Sürüm uyumunu, bakımı, lisansı ve bilinen açıkları inceleyin. Kod ve araçlarla uyumu kontrol edin. Ek paketleri, tarayıcı etkisini ve geri dönüşü yazın. Proje kararının eklemeyi kapsadığını doğrulayın.

**T-3 (ZORUNLU).** Doğrudan kullandığınız üçüncü taraf paketlerini proje ayarında bildirin. Frappe'nin zaten yüklediği paketler de buna dahildir. Varsa paket sürümlerini sabitleyen kilit dosyasını güncelleyin.

**T-4 (ZORUNLU).** Yeni veya değişen Frappe çağrısının tanımını okuyun. Sürüm geçişinde etkilenen çağrıları da inceleyin. Parametreleri, dönüşü ve izin davranışını doğrulayın. Ek B'ye bakın.

**ÖNERİLİR.** Önce Frappe'nin bildirim, çeviri, tarih ve günlük işlevlerine bakın.

**SERBEST.** Mevcut kalıbı ihtiyaca göre seçin.

## 3. Olgunluk seviyesi ve teknik borç

Proje sahibi uygulamanın seviyesini seçer. Seviye, hangi kontrollerin gerekeceğini belirler.

- **PoC, deneme sürümü.** Bir soruyu örnek veriyle sınayın. Deneme için gereksiz kurumsal katman kurmayın.
- **MVP, ilk kullanılabilir sürüm.** Ana işi az sayıda gerçek kullanıcıyla sınayın. Hata durumlarını ve yedekten dönüşü doğrulayın.
- **Scale, büyüme sürümü.** Gerçekçi veri ve eşzamanlı kullanıcı yüküyle hız ve dayanıklılığı ölçün. Sınır aşıldığında sistemin davranışını sınayın.
- **Enterprise, kurumsal sürüm.** Denetim kaydını, olay sorumlusunu ve kurtarma hedefini doğrulayın. Geçici çözümlerin hepsini kapatın.

**O-1 (ZORUNLU).** Seviyeyi ve varsa modül farkını proje kaydından okuyun. Karar gerekiyorsa proje sahibine bir kez sorun. Kararı kaydedin.

**O-2 (ZORUNLU).** Kapsamı seviye ve riske göre belirleyin. Seviye etiketi yoksa kural her seviyede geçerlidir. Seviye kuralları ve denetimleri üst seviyelerde de sürer. Veri, erişim, yük ve kesinti riskini ayrı inceleyin.

**O-3 (ZORUNLU).** Bilerek bırakılan eksik, teknik borçtur. Geçiş engelini kodun yanında `BORC(mvp)`, `BORC(scale)` veya `BORC(enterprise)` ile işaretleyin. Parantez, engellenen geçişi gösterir. Eksiği, etkisini, sorumlusunu ve kapanma koşulunu yazın. Yeni borcu raporlayın. Kod dışı borcu proje kaydına yazın.

**O-4 (ZORUNLU).** Geçişte `BORC` etiketlerini, etiketsiz geçici kodu ve proje kaydını inceleyin. Yeni seviyeye kadar biriken kuralları mevcut koda uygulayın. Geçiş engellerini kanıtla kapatın. Örneğin sipariş listesini onaylı veri miktarında ölçün.

**O-5 (ZORUNLU).** Yetkiyi, veri tutarlılığını ve önce testi her seviyede koruyun. PoC internete açıksa veya gerçek veri kullanıyorsa MVP kurallarını uygulayın. Kapsamı raporlayın.

## 4. Kodun yeri, modül sınırları ve SOLID

Controller, bir kayıt türünün kurallarını taşıyan Python sınıfıdır. Kanca, olayda uygulama kodunu çağırır. Uç, ağdan çağrılan işlevdir.

| İş | Kodun yeri |
|---|---|
| Bir kaydın kendi kuralı | Controller |
| Veritabanına dokunmayan hesap | Saf işlev |
| Birden fazla kaydı ilgilendiren iş | Sorumlu modüldeki ortak işlev |
| Ağdan çağrılan işlem | `@frappe.whitelist()` ile açılan uç |
| Başka türdeki kayıt olayına tepki | `doc_events` kancası ve işleyici |
| Kullanıcıyı bekletecek iş | Arka plan işi |
| Eski veriyi taşıma | Yama, yani bir kez uygulanan kod |
| Erişim denetimi | Önce DocType ve kullanıcı izinleri, gerekirse izin kancası |
| Yönetim ekranı davranışı | JavaScript form betiği |

Sıralı (procedural) kod, işi adım adım yürütür. Nesne yönelimli programlama (OOP), veri ve davranışı sınıfta birleştirir. Sınıfı Frappe gerektiriyorsa veya veriyle davranış birlikte değişiyorsa kullanın.

MVC, model, görünüm ve denetleyici görevlerini ayıran bir yaklaşımdır. DocType veriyi tanımlar. Form betiği yönetim ekranını yönetir. Controller ve sunucu işlevleri iş kuralını uygular.

**M-1 (ZORUNLU).** İş kuralını sunucuda uygulayın. Bir kayda özgü kuralı controller içinde tutun. Diğer yazma yollarını da sınayın. Gizli ve salt okunur ekran alanları erişimi korumaz. Koşullu zorunluluğu sunucuda da doğrulayın.

**M-2 (ZORUNLU).** Aynı iş kuralını paylaşan girişler aynı işlevi kullansın.

**M-3 (ZORUNLU).** Katman, taban sınıf veya arayüz için somut gerekçe gösterin. Örneğin ikinci sağlayıcıyı aynı kuralla çalıştırmak gerekebilir. Önce küçük işlevleri birlikte kullanın.

**M-4 (ZORUNLU).** Uygulama özelliğini kendi uygulamanızda geliştirin. Frappe'nin ve başka uygulamanın kodunu değiştirmeyin. Davranışı değiştirmek için Frappe'nin desteklediği kancalara bakın.

**M-5 (ZORUNLU).** Standart DocType tanımını geliştirici kipinde Frappe ekranından değiştirin. Üretilen tanımı ve controller dosyasını inceleyin. Alt tablo dışında test dosyası da üretilir. Yeni kayıt türünün ilk izinlerini proje sahibine onaylatın. Başka uygulamanın alanları için A-3 yolunu kullanın.

**M-6 (ZORUNLU).** `hooks.py` dosyasında yalnız bağlantıları tutun. İş kuralını ilgili modülde yazın.

**ÖNERİLİR.** Yeni uygulamayı `bench new-app` ile başlatın. Bench, Frappe uygulamalarını yöneten komut aracıdır. Lisansı proje sahibinden alın. Otomatik Git kaydını `--no-git` ile atlayın. `.gitignore` dosyasını ayrıca hazırlayın.

### Yeni Python dosyası

**M-7 (ZORUNLU).** Olağan uç adresi işlevin tam Python adını kullanır. Adres değişirse A-6'yı uygulayın. Python yamasında `execute` tanımlayın. Olağan yükseltme için yamayı `patches.txt` dosyasına ekleyin. Yama bölümünü Python dışı belgeden seçin.

**M-8 (ZORUNLU).** Projenin ad, girinti ve biçim kurallarına uyun. Tanımlı biçimlendiriciyi yalnız değişen dosyada çalıştırın. Biçim denetiminde R-10'u uygulayın.

**ÖNERİLİR.** Modülün dosya düzenini ve mevcut yama klasörünü izleyin. Yazım kuralı yoksa yakın kodu veya PEP 8'i izleyin. İşlevi küçük tutun. Açık adlar kullanın. Girdi ve dönüş türünü yazın. İşlev başındaki açıklamaya docstring denir. Gerekirse amacı, yan etkiyi ve nedeni yazın. Çeviri için `frappe._` kullanın. Günlük kuralı yoksa `frappe.logger` işlevine bakın.

### Alan planı, modül sınırı ve düşük bağımlılık

DDD, işi iş alanlarına bölen tasarım yöntemidir. Modüler monolit tek uygulama olarak çalışır. Modül, bir işten sorumlu kod bölümüdür. Düşük bağımlılık (low coupling), değişikliğin başka parçalara yayılmasını azaltır.

**B-1 (ZORUNLU).** Sorumluluk ve değişme nedeni ayrışınca yeni modül açın. Ayrı uygulama için karar kaydı yazın.

**B-2 (ZORUNLU).** Her kayıt türüne tek sahip modül verin. Ortak iş ve yazmada sahibin açık işlevini kullanın. Yalnız okuma için ayrı işlev zorunlu değildir.

**B-3 (ZORUNLU, MVP ve üstü).** Ortak işlevi, alanı ve olayı proje kaydında gösterin.

**B-4 (ZORUNLU).** Bağımlılık döngüsü kurmayın. MVP ve üstünde modüller arası bağımlılık yönünü kaydedin. “Sipariş”, “Katalog” modülünü çağırıyorsa ters çağrıyı kurmayın.

**B-5 (ZORUNLU).** Kaydı durdurması gereken kuralı kayıt sırasında uygulayın. Bildirim gibi yan işleri kayıt kesinleştikten sonra başlatın.

**B-6 (ZORUNLU).** Ortak alan, izin veya işlev değişirse kullanan yerleri bulun. Python, JavaScript, tanım, kanca ve raporlarda arayın. “Print Format”, yama ve testleri de inceleyin.

**B-7 (ZORUNLU).** Davranış değişikliğinden önce plan yazın. Önce alan planını yazın. Sonra alanı modüle eşleyin. Sonra bağımlılık yönünü belirleyin.

**B-8 (ZORUNLU).** Planın ağırlığını işin zorluğuna göre seçin. Hafif planda terimi, sahip modülü, kök kaydı ve bağımlılık yönünü belirtin. Değişmez kuralı, çağıranları ve olayı da yazın. Şu durumlarda tam plan yazın:

- yeni modül, yeni uygulama ya da başka modülün kaydına yazma,
- iki modülün ortak kuralı ya da başka modülün kullandığı sözleşme,
- aynı sonucu üreten ikinci yazma yolu,
- para, vergi, stok, onay ya da yetkiyi değiştiren durum geçişi,
- dış sistem, site sınırını geçen iş ya da çevrimdışı yazma,
- verinin sahibini ya da anlamını değiştiren taşıma.

Emin değilseniz tam plan yazın. Tam plana alt tabloyu, durum geçişini ve açık işlevleri ekleyin. Hafif planı rapora, tam planı karar kaydına yazın.

**B-9 (ZORUNLU).** Plan yeni katman gerekçesi değildir. Alanı modülle, kök kaydı DocType ile kurun. Yeni katmanda M-3'ü uygulayın.

**B-10 (ZORUNLU, MVP ve üstü).** İzinsiz modül `import` bağını ve döngüyü otomatik denetleyin. Başka modülün kaydına doğrudan yazmayı otomatik testle yakalayın. İhlalde denetim başarısız olsun. Mevcut denetim yolunu kullanın. Yeni araçta T-2'yi uygulayın. Git kancası için açık onay alın.

PoC'de sahipliği ve bağımlılık yönünü plana yazın. Eksik denetimi O-3'e göre `BORC(mvp)` ile işaretleyin.

**ÖNERİLİR.** Modüller arası veriyi parametreyle taşıyın. `frappe.flags` ile gizli bağlantı kurmayın. Ortak kavrama tek ad verin. Dış sistemle konuşan kodu bir yerde tutun.

| Frappe'deki durum | Alınacak önlem |
|---|---|
| Bağlantı alanı silme ve ad değişikliğini etkiler. | Bağımlılık yönünü ve kullanan kayıtları inceleyin. |
| `doc_events` başka modülün olayına bağlanabilir. `"*"` tüm türleri kapsar. | Olayı B-3'e göre kaydedin. Kancayı gereken türe bağlayın. |
| Sınıf değişiklikleri çakışabilir. | Sınıf kancaları için Ek B'ye bakın. |

Örneğin “Sipariş”, “Katalog” modülünün açık fiyat işlevini çağırır. Ödeme, sipariş kesinleşince başlar. Test, reddedilen siparişin ödeme başlatmadığını doğrular.

### Beş SOLID ilkesi

SOLID, tasarımı incelemek için beş ilkedir. İlke tek başına yeni katman gerekçesi değildir.

**S-1 (ZORUNLU).** Yeni sınıfta veya görev değişince ilgili ilkeleri inceleyin. Modül sınırı değişince de inceleyin. İlkeyi ve ihlalin etkisini yazın. İhlali düzeltin veya `BORC` ile işaretleyin. Veri ve yetki ihlalini borca bırakmayın.

- **SRP, tek sorumluluk.** Hesap ve e-posta ayrı nedenlerle değişirse görevleri ayırın.
- **OCP, genişletmeye açıklık.** Gerçek bir ikinci tür gelirse ortak ekleme noktasını değerlendirin.
- **LSP, yerine geçebilme.** Alt sınıf, üst sınıfın çağrı ve hata sözleşmesini korusun.
- **ISP, arayüz ayrımı.** Çağıran kodun yalnız kullandığı işlevlere bağlanmasını sağlayın.
- **DIP, bağımlılığı tersine çevirme.** Hesap, dış sistemin ayrıntısını bilmesin. Örneğin kuru parametre olarak alsın.

## 5. Kayıt olayları ve veri bütünlüğü

Frappe, kaydın durumuna göre controller yöntemlerini çağırır.

| Kuralın zamanı | Yöntem |
|---|---|
| Olağan kayıt ve onay öncesi | `validate` |
| Olağan kayıt öncesi | `before_save` |
| Onay öncesi | `before_submit` |
| Kayıt veya onay yazıldıktan sonra | `on_update` |
| Onay yazıldıktan sonra | `on_submit` |
| İptal öncesi ve sonrası | `before_cancel` ve `on_cancel` |
| Onaydan sonra düzenleme, yazımdan önce ve sonra | `before_update_after_submit` ve `on_update_after_submit` |
| Olağan silme öncesi | `on_trash` |

**V-1 (ZORUNLU).** Olağan yazmada `insert` ve `save` kullanın. Silmede `frappe.delete_doc` kullanın. `frappe.db.set_value` ve `doc.db_set`, izin ve doğrulamayı atlar. `frappe.db.set_value` kayıt olayı çağırmaz. `doc.db_set` yazımdan önce `before_change` çağırır. Yazımdan sonra `on_change` çağırır.

**V-2 (ZORUNLU).** İstek veya kayıt olayında işlemi kesinleştirmeyin. Kesinleştirme, yazıları kalıcı yapar. `frappe.db.commit()` ve `doc.db_set(..., commit=True)` işlemi erken kesinleştirebilir. Hata dışarı çıkmazsa Frappe yazma isteğini kesinleştirir. Parçalı toplu işte yeniden başlatmayı sınayın.

**V-3 (ZORUNLU).** Hata yakalanırsa yazıları geri alın ya da hatayı yeniden yükseltin. Geri alma noktasına dönmek bekleyen `after_commit` çağrısını silmez. Sipariş hatasında stok geri alımını sınayın.

**V-4 (ZORUNLU).** Geri alınamayan dış işi kayıt kesinleşince başlatın. Ödeme gibi kritik işi aynı işlemde kimliğiyle kaydedin. Sıraya girmeyen işi aynı kimlikle yeniden başlatmayı sınayın.

**V-5 (ZORUNLU).** İşe kayıt adını verin. İşte kaydı yeniden okuyun. Koşulları ve isteği yapanın iznini denetleyin. İş, sıraya koyan kullanıcıyla başlar. İç yeniden deneme `Administrator` ile başlar. Yeniden deneme işi iki kez uygulamasın. İş yeni yazıya bağlıysa `enqueue_after_commit=True` kullanın. Ertelenen çağrı `None` döndürür. `now=True` ertelemeyi atlar.

**V-6 (ZORUNLU).** Tablo ve alan yapısını DocType tanımında değiştirin. Gerekirse yama ekleyin. Canlı veritabanında yapıyı elle değiştirmeyin. Tür veya anlam değişirse eski veriyi okuyan geçiş planlayın. Yamada yazma yolunu gerekçelendirin. `save` kayıt olaylarını çağırır. Doğrudan yazma için V-1'e bakın.

**V-7 (ZORUNLU).** Veri geçişi yeniden çalışınca zarar vermesin. Boş kurulumu ve eski verili yükseltmeyi geçişte sınayın.

**V-8 (ZORUNLU).** Tekilliği veritabanında sağlayın. Dizin aramayı hızlandırır. Desteklenen alanda `unique` kullanın. Birleşik dizin için `frappe.db.add_unique` kullanın. Standart DocType için `on_doctype_update` işlevini kullanın. Özel türde tablo oluşunca dizini kurun. Boş kurulum yamaları atlar. Yükseltmede tekrarı önce temizleyin. Dizini yamayla da kurun. Dizini ve eşzamanlı girişi yükseltmede sınayın.

**V-9 (ZORUNLU).** Yeni zamanlanmış iş, proje sahibinin açık `cron` isteğini gerektirir. Buna `scheduler_events` ve zamanlanmış “Server Script” dahildir. Etkin “Auto Repeat” ve “Auto Email Report” da dahildir. Kopyalama ve yeniden etkinleştirmede de izin gerekir. Canlı takip izin vermez. Yasakta veya alıntıda geçen `cron` izin sayılmaz.

**V-10 (ZORUNLU).** Toplu değişikliği veya geri alınamayan silmeyi yazmadan deneyin. Etkilenen kayıtları ve geri dönüş yolunu gösterin. Proje sahibinin onayının bu işi kapsadığını doğrulayın. Karar eksikse sorun.

**V-11 (ZORUNLU).** Yalnız ele alabildiğiniz hata türünü yakalayın. Hata yerine uydurma değer döndürmeyin. Toplu işte hangi adımların başarısız olduğunu kaydedin.

## 6. Yetki ve veri güvenliği

**G-1 (ZORUNLU).** Uçta işlemin gerektirdiği izni denetleyin. Kullanıcıyı `frappe.session.user` üzerinden alın. `frappe.get_doc` varsayılan olarak izin denetlemez. Okurken `doc.check_permission("read")` çağırın. Yanıta yalnız izinli alanları koyun. Yazma, silme ve onay için ayrı izin kullanın.

**G-2 (ZORUNLU).** Rol koşulunu ve kayıt iznini ayrı denetleyin. Örneğin satıcı rolü, başka satıcının siparişine erişim vermesin.

**G-3 (ZORUNLU).** Kullanıcıya dönen listeyi `frappe.get_list` ile okuyun. Sanal DocType kendi satır izinlerini denetlesin. `frappe.get_all` Frappe'nin izin süzmesini atlar. Bu işlevi gerekçesi yazılı sistem işleriyle sınırlayın.

**G-4 (ZORUNLU).** `ignore_permissions=True` kullanımını gerekçesiyle yazın. Hedef kaydı kullanıcı seçiyorsa bu seçeneği kullanmayın. Bayrak nesnede kalır ve sonraki izin denetimlerini atlatır. Önceki değeri `finally` içinde geri yükleyin.

**G-5 (ZORUNLU).** Sorgu değerlerini parametreyle verin. Sorgu metnine kullanıcı değeri eklemeyin. Alan ve sıralama adlarını izinli listeden seçin. Ham SQL ve `frappe.db.get_value` kayıt iznini denetlemez. `frappe.qb` varsayılan olarak denetlemez. İzni ayrıca doğrulayın.

**G-6 (ZORUNLU).** Yeni veya değişen özel uçta `methods` seçeneğini yazın. Salt okumada `GET` kullanın. İşlem başlatırken `POST` kullanın.

**G-7 (ZORUNLU).** Misafir erişimini ancak proje kararıyla açın. İstek sayısını, gövde boyutunu ve girdiyi sınırlayın. İstek sayısı için `frappe.rate_limiter` içindeki `rate_limit` işlevine bakın. Misafirle her çağrı yolunu ve istek sınırını sınayın.

**G-8 (ZORUNLU).** Uç girdisinin ve dönüşünün türünü yazın. Tür, değerin sayı veya metin gibi biçimini belirtir. Frappe girdiyi çevirebilir. İzinli değerleri, uzunluğu ve aralığı sunucuda sınayın. Boş ve yanlış biçimli girdiyi istekle deneyin.

**G-9 (ZORUNLU).** Parolayı ve erişim anahtarını sunucuda saklayın. Site ayarını veya “Password” alanını kullanın. Koda, yanıta ve günlüğe gizli bilgi koymayın. `.env`, `site_config.json` ve yedekleri depoya koymayın. Depoyu herkese açık sayın.

**G-10 (ZORUNLU).** Kullanıcı metnini kod veya şablon olarak çalıştırmayın. Kullanıcı girdisinden çağrılacak Python işlevi seçmeyin.

**G-11 (ZORUNLU).** Kullanıcı metnini gösterildiği yere uygun biçimde işleyin. HTML metninde örneğin `{{ deger | e }}` kullanın. Adres ve JavaScript verisini kendi kurallarıyla doğrulayın.

**G-12 (ZORUNLU).** Önce hazır kayıt izinlerini kullanın. Listeyi `permission_query_conditions` ile süzün. Tek kayıtta `has_permission` kancasını sınayın. Paylaşım bu iki denetimi aşabilir. Sahiplik zorunluysa listede ve uçta ayrıca doğrulayın. Paylaşılmış kayıtla sınayın.

**G-13 (ZORUNLU).** Dış isteğe süre sınırı koyun. Sunucudan yalnız onaylı hedefe istek gönderin. Dosya türünü içeriğinden doğrulayın. Boyutu ve indirme iznini sınayın. Dosyayı uygun erişim ayarıyla “File” türünde saklayın.

**G-14 (ZORUNLU).** Paket ve gizli bilgi taramasında R-10'u uygulayın. Dış erişim büyürse güvenliği OWASP ASVS gibi bir listeyle inceleyin.

**G-15 (ZORUNLU, kişisel veri varsa).** Kişisel veri, bir insanı tanıtan bilgidir. Alanları, saklama süresini ve silme yolunu proje kaydına yazın. Hazır günlükleri de inceleyin. Uygulama günlüğüne ve açık depoya kişisel veri koymayın. Yasal yükümlülüğü proje sahibi doğrular.

**G-16 (ZORUNLU).** Son kullanıcıya `desk_access` açık rol vermeyin. Son kullanıcının türü `Website User` olsun. Yönetim ekranına girişin reddedildiğini sınayın.

## 7. Önce test ve doğru sonucun kaynağı

Testi önce yazıp kodu testle geliştirme yöntemine TDD denir. Kod ve test aynı yanlışı içerebilir. Testin doğru sonucu nereden alacağına “oracle sorunu” denir.

Beklenen sonucu şu kaynaklardan birine bağlayın.

- Proje sahibinin yazılı isteği veya onayladığı örnek.
- Geçerli sözleşme veya resmî kural.
- Sonucu doğrulanmış eski sistem veya hesap tablosu.
- Her durumda geçerli kural. Örneğin toplam, satır tutarlarının toplamına eşittir.

> Sepette 1.000 TL tutarında ürün var. İndirim sınırı yüzde 20.
>
> Satıcı 200 TL indirim girerse sistem kabul eder.
>
> Satıcı 200,01 TL indirim girerse sistem reddeder.

**D-1 (ZORUNLU).** Beklenen sonucu bağımsız kaynağa bağlayın. Sonuç belirsizse proje sahibine sayılı örnek gösterin. Örneğin onayını alın. Örnekleri ve kaynaklarını raporlayın.

**D-2 (ZORUNLU).** Anlamlı davranış değişikliğinde veya hata düzeltmesinde önce test yazın. Testi çalıştırın ve beklenen nedenle başarısız olduğunu kaydedin. Kurulum hatası bu kanıtın yerini tutmaz. Kodu düzelttikten sonra aynı testi yeniden çalıştırın.

**D-3 (ZORUNLU).** Beklenen değeri değişen kodun çıktısından kopyalamayın.

**D-4 (ZORUNLU).** Testi geçirmek için kontrolü silmeyin veya atlamayın. Beklenen değeri koda uydurmayın. Üretim koduna yalnız testte çalışan dal eklemeyin. Testin yanlışlığını bağımsız kaynak gösterirse testi düzeltin. Proje sahibinin onayladığı örneği değiştirmeden önce sorun. Test düzeltmesini raporda ayrı belirtin.

**D-5 (ZORUNLU).** Testte beklenen değeri, durum değişikliğini veya hatayı denetleyin.

**D-6 (ZORUNLU).** Yetkiyi gerçek giriş yolunda sınayın. Ağ ucu için HTTP isteği kullanın. Ağdaki misafir ve HTTP yöntemi denetimi doğrudan çağrıda çalışmaz. Kısıtlı kullanıcıyla izin ve ret durumunu sınayın. Gerekirse başkasına ait ya da paylaşılmış kayıtları ekleyin.

**D-7 (ZORUNLU).** Para, stok ve yetkiyi açık doğrulamayla koruyun. Bu kurallarda `assert` kullanmayın. Hatayı `frappe.throw` ile bildirin. Yetki reddinde `frappe.PermissionError` verin. Paranın birimini ve yuvarlamasını sınayın. Alanın basamak sayısını ve site ayarını koruyun. `frappe.utils.flt` kullanırsanız basamak sayısını verin.

**D-8 (ZORUNLU).** İzin ve kayıt davranışını gerçek Frappe yolundan sınayın. Dış sistem yerine test taklidi kullanabilirsiniz. Saf hesapları ayrı ve hızlı test edin.

**D-9 (ZORUNLU).** Veri kullanan testleri ayrı test sitesinde çalıştırın. Canlı sitede `allow_tests` ayarını açmayın.

**ÖNERİLİR.** Kritik kuralı geçici olarak bozun. Testin başarısız olduğunu görün. Test sınıfı ve komut için Ek B'ye bakın.

## 8. Hız, mobil teslim ve boyut sınırı

Hız ölçerken değişiklik öncesi ve sonrası aynı koşulu kullanın. Ölçümde gerçekçi veri ve kullanıcı sayısını yazın. Örneğin sorgu sayısını, yanıt süresini veya aktarım boyutunu ölçün.

**P-1 (ZORUNLU).** Kayıt sayısıyla artan sorgulardan kaçının. Döngüde her kayıt için `get_doc` çağırmayın. Gereken alanları toplu veya sınırlı gruplarla alın.

**P-2 (ZORUNLU).** Sorguda gereken alanları açıkça isteyin.

**P-3 (ZORUNLU).** Büyüyebilen listede sorguya açık sınır koyun. Kararlı sıralama için eşitliği bozan bir alan ekleyin. Örneğin tarih eşitse kayıt adına bakın.

**P-4 (ZORUNLU).** Kullanıcıyı bekletecek işi arka plana verin. `short` ve `default` için varsayılan sınır 300 saniyedir. `long` için 1.500 saniyedir. Uzun işte `queue` ve `timeout` değerini açık verin. Sırada beklemeyi ve yeniden denemeyi ölçün.

**P-5 (ZORUNLU).** Önbelleği ölçümle gerekçelendirin. Önbellek, sık istenen sonucu geçici olarak saklar. Anahtar, sonucu değiştiren girdileri ve gerekiyorsa kullanıcıyı içersin. Sonucun ne zaman silineceğini veya yenileneceğini belirleyin.

**P-6 (ZORUNLU).** Redis'i önbellek ve iş sırası için kullanın. Kalıcı iş verisini veritabanında tutun. Redis'e erişimi sunucu sorumlusu gerekli servislerle sınırlar. Açık erişim görürseniz bildirin.

**P-7 (ZORUNLU).** Ekrana özel kodu yalnız gerektiğinde yükleyin. `app_include_js` yönetim ekranının, `web_include_js` web sayfalarının ortak yükünü artırır. Form eki için `doctype_js` seçeneğini inceleyin.

**ÖNERİLİR.** Sorgu sayısı için `assertQueryCount` kullanın. Yavaş sorgunun planına bakın. Ölçüm gerektirirse dizin ekleyin. Uygun alanda `search_index` kullanın. Elle eklenen tek alanlı dizin eşitlemede silinebilir.

### Ayrı arayüz ve telefon için arka uç (adaptive delivery)

**P-8 (ZORUNLU).** İş kuralını ve yetkiyi bütün ekranlar için ortak tutun. Sunucu davranışını cihaz adına göre ayırmayın.

**P-9 (ZORUNLU).** Ekrana yalnız gereken alanları gönderin. Sonuç sonra alınacaksa takip için iş kimliği döndürün. Durum sorgusunda da erişim iznini denetleyin.

**P-10 (ZORUNLU).** Uç sözleşmesini proje belgesine yazın. Girdiyi, çıktıyı ve hataları belirtin. Mevcut sözleşmeyi koruyun. Değişiklikte A-6'yı uygulayın.

Frappe'nin sunduğu JavaScript, CSS ve görseli yalnız gerektiğinde yükleyin. Gizlenen dosya yine inebilir. Gerçek aktarımı ağ kaydından doğrulayın.

### Hız ve boyut sınırları

**P-11 (ZORUNLU, MVP ve üstü).** İlgili sınırı ve ölçüm koşulunu kayıttan alın. Sınır yoksa ölçümle önerin ve proje kararını alın. Onaylı sınırı otomatik denetime bağlayın. Mevcut denetim yolunu kullanın. Aşılırsa denetim başarısız olsun. Sınırı sessizce büyütmeyin.

PoC'de onaylı sınır varsa P-11'i uygulayın.

**P-12 (ZORUNLU).** Ölçüm raporunda eski ve yeni değeri yazın. Sayfayı, ölçüm aşamasını ve sıkıştırma koşulunu belirtin. Eklenen işi açıklayın. Sınır varsa sınırı ve kalan payı yazın. Payın yeterli olup olmadığını söyleyin. Gereken işi ve karar sahibini yazın.

> Örnek. Sipariş sayfasına yeni bir düğme ekledim. Sayfa açılırken telefon, ekranı çalıştıran kodu indirir. Bu kodun adı JavaScript'tir.
>
> Sayfayı gönderen bilgisayar önce bu dosyayı küçültür. Buna sıkıştırma denir. Sayılar telefonun indirdiği küçültülmüş dosyaya aittir.
>
> Sınır 50 KB. KB, dosyanın büyüklüğünü gösteren birimdir. Büyük dosya sayfanın açılışını yavaşlatabilir.
>
> Telefon önce 44,8 KB indiriyordu. Şimdi 45,6 KB indiriyor. Dosya 4,4 KB daha büyürse sınıra ulaşır.
>
> Bu kadar boş yer azdır. Yeni bir özellik sınırı aşabilir. Şu anda bir şey yapmanız gerekmiyor.
>
> Sınır aşılırsa önce kodu küçültürüm. Sınır değişikliğine siz karar verirsiniz.

## 9. Kontroller ve teslim kanıtı

**R-1 (ZORUNLU).** Her kontrolün komutunu, sonucunu ve ilgili çıktısını yazın. Geçtiyse `pass`, kaldıysa `fail` yazın. Çalışmadıysa `not_run`, kapsam dışıysa `not_applicable` yazın. Son iki durumda nedeni belirtin.

**R-2 (ZORUNLU).** Başarısızlık nedenini düzeltin veya raporlayın. Denetimi susturmak için kuralı gevşetmeyin. `# noqa` gibi susturma yorumunda aracın kural kodunu kullanın. Gerekçeyi ayrı yorumda yazın.

**R-3 (ZORUNLU).** Komutları kendiniz çalıştırın. Parola, `sudo` veya kişisel onay gerekirse nedeni ve adımı bildirin.

**R-4 (ZORUNLU).** Değişikliği istenen işle sınırlayın. İlgili güvenlik ve veri sorunlarını bildirin.

**R-5 (ZORUNLU).** Doğrulayamadığınız sonucu açıkça bildirin. Otomatik çalışan kuralı komut ve çıktıyla gösterin.

**R-6 (ZORUNLU).** Kuralları değişen işe ve etkilenen davranışa uygulayın. Eski kodu sırf belgeye uydurmayın. Seviye geçişinde O-4'ü uygulayın.

**R-7 (ZORUNLU).** Proje belgesi ve kod çelişirse farkı kaynakla gösterin. Kod bugünkü durumu gösterir. Beklenen davranışı onaylı kural belirler.

**R-8 (ZORUNLU).** Raporu, soruyu ve uyarıyı yalın Türkçe yazın. Türkçe kullanıcı ve Git mesajlarında da yalın yazın. Kısa ve tam cümle kurun. Önce olanı, etkisini ve gereken işi söyleyin. Komut ve çıktıyı sona koyun. Terimi ilk kullanımda açıklayın.

**R-9 (ZORUNLU).** Ağır riskli değişikliği bağımsız inceletin. Yetki, veri geçişi ve eşzamanlılık değişiklikleri buna girer. Önemli mimari ve ortak sözleşme değişiklikleri de buna girer. İnceleyen yalnız okur. Kontrolleri siz çalıştırın. İnceleme yapılamazsa raporlayın.

**R-10 (ZORUNLU).** İlgili mevcut biçim, tür, test ve güvenlik denetimlerini çalıştırın. Onaylı denetimleri her kod değişikliğinde çalıştırın. Eksik denetimi bildirin. İhlal yinelenirse otomatik denetim önerin. Yeni araçta T-2'yi uygulayın.

Git yazar korumasını ve canlıya yükleme yetkilerini koruyun.

### Ajanla çalışırken sık görülen sorunlar

Vibecoding, kodu yapay zekâ ajanına yazdırarak çalışma biçimidir.

| Sorun | Kural |
|---|---|
| Ajan çalışan kodu bir daha yazar. | A-2 |
| Ajan gereksiz katman ekler. | M-3, O-2 |
| Ajan olmayan Frappe işlevini kullanır. | T-4 |
| Ajan testi zayıflatıp geçirir. | D-4 |
| Ajan aynı hatayı koda ve teste yazar. | D-1, D-3 |
| Ajan çalıştırmadığı kontrolü geçti sayar. | R-1, R-10 |
| Ajan gerekçesiz paket ekler. | T-2 |
| Ajan kayıt erişimini denetlemez. | G-1, D-6 |
| Ajan ilgisiz dosyaları değiştirir. | R-4 |
| Ajan geçici kodu kalıcı bırakır. | O-3, O-4 |
| Ajan hatayı yakalayıp gizler. | V-11 |
| Ajan anlaşılmayan uyarı yazar. | R-8, P-12 |

## Ek A. Proje kaydı

Proje kaydını `AGENTS.md` veya `CLAUDE.md` içinde tutun. Kayıt yoksa bu başlıklarla açın. İşi etkileyen eksik kararı sorun.

- Olgunluk seviyesi ve farklı seviyedeki modüller.
- Frappe ve Python sürüm aralıkları ve çalışan sürümler.
- Modül sahipleri. MVP ve üstünde bağımlılık yönleri, ortak çağrılar, alanlar ve olaylar.
- Denetim komutları, kapsanan kurallar, test sitesi, sınırlar ve ölçüm koşulları.
- Proje sahibinin kararları ve karar kayıtlarının yeri.
- Yönetici rolleri.
- Onaylı araçlar, ad dili ve mesaj dili.
- Kişisel veri alanları, saklama süresi ve silme yolu.
- Kod dışı teknik borç, sorumlu ve kapanma koşulu.

## Ek B. Frappe sürüm farkları ve sık hatalar

Bulgular Frappe 15.126.1 ve 16.56.0 kaynak kodunun okunmasına dayanır. Sürüm yükselirse kullandığınız yolu yeniden inceleyin.

| Konu | Kaynakta görülen davranış ve uygulama |
|---|---|
| `frappe.get_doc` | Adla yükleme varsayılan olarak izin denetlemez. `check_permission` bu yolda 16'da çalışır, 15'te etkisizdir. İki sürüm için `doc.check_permission` çağırın. |
| Liste sınırı | `frappe.get_list` ve `frappe.get_all` sınırsız sonuç döndürebilir. Çağrıya `limit` ile açık sınır verin. |
| Liste sırası | Olağan listede varsa DocType sırası kullanılır. Ayar yoksa 15'te `modified`, 16'da `creation` kullanılır. Sırayı açık yazın. |
| `frappe.only_for` | 15, `frappe.flags.in_test` açıkken rolü denetlemez. 16 bu istisnayı kaldırır. Rol reddini yönetici olmayan kullanıcıyla sınayın. 15'te bayrağı yalnız rol çağrısı boyunca kapatın. Önceki değeri `finally` içinde geri yükleyin. |
| `has_permission` kancası | `None`, 15'te sıradaki denetime geçer. 16'da kanca reddeder. Kanca tek başına izin veremez. `True` veya `False` döndürün. |
| Tür denetimi | Frappe girdi denetiminde metin biçimindeki türleri atlar. `from __future__ import annotations` türleri metne çevirir. İstek tür denetimi için çalışma anında çözülen tür yazın. |
| `methods` seçeneği | Boş değer `GET`, `POST`, `PUT` ve `DELETE` açar. Çağrı yolu ayrıca sınır koyabilir. İzinli yöntemleri açık yazın ve ilgili yolu sınayın. |
| `GET` isteği | Frappe işlemde kalan yazıları geri alır. Erken kesinleştirme veya kesinleştirme bayrağı sonucu değiştirir. |
| Ağdan çağrılan controller yöntemi | `frappe.handler.run_doc_method` okuma izniyle çağırabilir. Nesne istek verisinden kurulabilir. 15'in hazır kayıt yolları `methods` kısıtını denetlemez. İşlem iznini ve HTTP yöntemini ayrıca denetleyin. İzne esas alanı veritabanından okuyun. |
| `frappe.db.delete` | Etkin süzgeç yoksa tüm tablo satırları silinir. Kayıt olayları çalışmaz. Süzgeci ve etkilenecek kayıtları doğrulayın. |
| `frappe.db.add_index` ve `add_unique` | Dizin eklenirken değişiklikler kesinleşebilir. Bu çağrıyı veri yazma işleminin ortasına koymayın. |
| `override_doctype_class` | Son kanca kaydı seçilir. 16, `extend_doctype_class` eklerini de birleştirir. Olaylara bağlanmak için önce `doc_events` kullanın. |
| `Document.validate` | Temel sınıfta bu yöntem yoktur. `super().validate()` öncesi üst sınıfın yöntemi sağladığını doğrulayın. |
| `frappe.publish_realtime` | Hedef çıkmazsa bildirim sitenin yönetim ekranına yayılır. Olay türü veya iş kimliği hedefi değiştirebilir. Alıcıyı açıkça seçin. |
| Test taban sınıfı | 15'te `FrappeTestCase`, 16'da `IntegrationTestCase` kesinleşmemiş yazıları sınıf sonunda geri alır. 16'daki `UnitTestCase` geri almaz. Testleri birbirinin verisine bağlamayın. |
| `bench run-tests` | `CI` boşsa 15 başarısız teste rağmen sıfır koduyla dönebilir. 16 çalışan test başarısızsa 1 döndürür. İki sürümde de test sayısını ve sonucu okuyun. |
| Alt tablo satırı | Ana kayıt yazılırken Frappe satırın `validate` yöntemini çağırmaz. Satır kuralını ana kaydın `validate` yönteminde uygulayın. |
| `doc_events` işleyicisi | 15, kaydı ve olay adını verir. Ek girdi yoksa 16 tek parametreyi destekler. Uyum için `(doc, method)` yazın. |
| Web sayfası önbelleği | Sonuç yol ve dile göre saklanır. Anahtarda kullanıcı yoktur. Kişiye özel sayfanın Python dosyasına `no_cache = 1` yazın. Eski önbelleği silin. Geliştirici kipi kapalıyken sınayın. |
| Ruff denetimi | Ruff, Python kodunu denetler. `bench new-app` şablonu `RUF003` kuralını açar. Kural yorumdaki `ı` harfini işaretleyebilir. Gerekirse `[tool.ruff.lint]` altında `allowed-confusables` listesine `ı` ekleyin. |
