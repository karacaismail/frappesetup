# Frappe arka ucunda Python dışı dosya standartları

Bu kuralları Frappe uygulamasında Python dışı dosya yazan ajan uygular. Frappe yönetim ekranı, e-posta ve yazdırma dosyaları kapsama girer. Son kullanıcı yalnız ayrı arayüzü görür. Frappe'nin yönetim ekranını yalnız yöneticiler kullanır. E-posta ve yazdırma şablonları Frappe'de kalır. Görsel dil kuralları bu belgede yoktur. Görsel dilde ve erişilebilirlikte kalıcı arayüz talimatlarını uygulayın. Python kodunda [Python belgesini](frappe-python-standartlari.md) izleyin. Amaç az kodla güvenli, hızlı ve bakımı kolay uygulamadır.

## 1. İşe başlamadan önce

Python dışı dosya açmadan veya değiştirmeden önce kuralları okuyun. **ZORUNLU** kuralda engel varsa kural koduyla bildirin. **ÖNERİLİR** maddelerini riske göre uygulayın.

CI, değişikliği otomatik denetleyen sistemdir. Okuyucu, dosyayı okuyan programdır. Proje sahibinin kalıcı talimatları geçerlidir.

### Proje sahibinin kararları

Proje sahibi beklenen sonucu, seviyeyi ve boyut sınırını belirler. Silme, toplu değişiklik ve canlıya yükleme proje kararı ister. Zamanlanmış iş, yeni teknoloji, lisans ve misafir erişimi de böyledir. Eksik karar işi etkiliyorsa U-3'e göre sorun.

### Değişiklikte izlenecek sıra

1. Dosyanın üreticisini, sahibini ve okuyucusunu bulun. Bildirilen, kilitli ve çalışan sürümü rapora ayrı yazın.
2. Dosya türünü 2. bölümde bulun. Tür yoksa 3. ve 13. bölümü uygulayın.
3. Seviyeyi L-1 kuralıyla öğrenin.
4. Dosyayı Frappe veya bir araç üretiyorsa H-3 kuralını uygulayın.
5. Hazır yolu H-1 ve H-2 ile inceleyin. Ertelenen işi rapora yazın.
6. Değişen adı kullanan dosyaları X-1 kuralıyla bulun.
7. Beklenen sonucu bir örneğe bağlayın.
8. Davranış değişiyorsa önce N-2 kuralını uygulayın.
9. En küçük değişikliği yapın.
10. Dosyayı gerçek okuyucusuyla sınayın ve sonucu raporlayın.

## 2. Dosya türleri ve hazır yol

DocType, “Sipariş” gibi bir kayıt türünü tanımlar.

| Tür | Frappe'deki görevi | Yazan |
|---|---|---|
| `.json` | DocType tanımı, standart ya da hazır kayıt, araç ayarı | Frappe veya ajan |
| `.js` | Form, liste ve sayfa betiği | Ajan veya Frappe |
| `.cjs`, `.mjs`, `.ts` | Var olan araç veya derleme girdisi | Ajan |
| `.html` | E-posta, yazdırma, web ve tarayıcı şablonu | Ajan |
| `.css`, `.scss` | Yönetim ekranı görünümü | Ajan |
| `.yml`, `.yaml` | CI iş akışı, compose, API sözleşmesi | Ajan |
| `pyproject.toml`, `package.json`, `requirements.txt`, `MANIFEST.in` | Paket, sürüm ve araç ayarı | Ajan |
| `patches.txt`, `modules.txt` | Yama ve modül listesi | Ajan veya Frappe |
| `.csv`, `.po` | Çeviri. CSV, test verisi de taşıyabilir. | Ajan veya çeviri aracı |
| `.sql`, `.sh` | Veritabanı ve kurulum betiği | Ajan |
| `.env`, `site_config.json` | Siteye özel ayar | Kurulum aracı veya işletici |
| `.svg`, `.png` | Görsel | Ajan veya görsel aracı |
| `.template`, `.ini`, `.editorconfig`, `.gitignore` | Sunucu, araç ve depo ayarı | Ajan |
| Kilit dosyası | Çözülen paket sürümleri | Paket aracı |
| `.md` | Kullanım belgesi ve karar kaydı | Ajan |

**H-1 (ZORUNLU).** Yeni dosya veya davranıştan önce Frappe'nin hazır yolunu arayın. İhtiyacı, hazır karşılığını ve kalan farkı yazın. Buna boşluk analizi denir. Örneğin form davranışı için önce alan ayarını deneyin.

**H-2 (ZORUNLU).** Yeni dosyadan önce mevcut dosyayı arayın. Benzer dosyayı ve yeniden kullanma kararını raporlayın.

**H-3 (ZORUNLU).** Üretilen dosyayı kaynağından yeniden üretin. DocType için J-1 ve J-2'yi izleyin.

**H-4 (ZORUNLU).** Mevcut çözüm yeterliyse ikinci teknoloji veya tasarım kalıbı eklemeyin. Yeni dil, çatı, paket ve araç için uyumu inceleyin. Eksiği ve kararın gerekçesini yazın. Python belgesindeki T-2 kuralını uygulayın.

**H-5 (ZORUNLU).** Kanca, Frappe'nin çağırdığı ek uygulama yoludur. Kancayı okuyan kodu hedef sürümde bulun. Ayar anahtarını hangi aracın okuduğunu doğrulayın.

**H-6 (ZORUNLU).** İş kuralını ve yetki denetimini sunucuda uygulayın. Hazır rol ve izin ayarlarını hedef sürümde sınayın. Veri dosyasında yeni bir komut dili kurmayın.

**H-7 (ZORUNLU).** Bir ayarı tek dosyada tutun. Örneğin bağımlılığı iki ayrı dosyada bildirmeyin. Kopya gerekiyorsa kopyayı araçla üretin.

**H-8 (ZORUNLU).** Aynı hesabı iki dilde yazmayın. Zorunluysa iki kodu aynı bağımsız örneklerle sınayın.

MVC yaklaşımı veri, ekran ve işlem görevlerini ayırır. Tanım dosyası veriyi tarif eder. Betik ve şablon ekranı yönetir. Sunucu kodu kuralı uygular.

**H-9 (ZORUNLU).** Sıralı adımlar yeterliyse düz işlev kullanın. Küçük işlevleri birlikte kullanmayı deneyin. Sınıf veya katman için somut gerekçe yazın.

**H-10 (ZORUNLU).** Kod adlarını İngilizce ve ASCII yazın. Değişken, sabit, `class` ve `id` adı da dahildir. DocType, modül, alan, Select seçeneği ve dosya adı da dahildir. Frappe klasör adını DocType ve modül adından üretir. Görünen adların Türkçesini çeviri dosyasında verin.

### Olgunluk seviyesi

Seviye koşulu olmayan kural her seviyede geçerlidir.

- **PoC, deneme sürümü.** Hazır form ve alan ayarıyla yetinin. Tek soruyu uydurma veriyle sınayın.
- **MVP, ilk kullanılabilir sürüm.** Tanımı, şablonu ve betiği gerçek okuyucuda sınayın. Kaçışı, çeviriyi ve hata yolunu denetleyin.
- **Scale, büyüme sürümü.** Tarayıcıya inen betik ve stil boyutunu ölçün. Yükseltme süresini ve eşzamanlı kullanımı gerçekçi veriyle ölçün.
- **Enterprise, kurumsal sürüm.** Yükseltmeyi ve geri dönüşü eski veriyle sınayın. Geçici çözümlerin hepsini kapatın.

**L-1 (ZORUNLU).** Seviyeyi Ek A'daki proje kaydından okuyun. Modül farklı seviyedeyse bunu kaydedin.

**L-2 (ZORUNLU).** Teknik borç, bilerek bırakılan eksiktir. Borcu örneğin `BORC(scale)` yorumuyla işaretleyin. JSON ve CSV borcunu proje kaydına yazın. Eksiği, etkisini, sorumlusunu ve kapanma koşulunu belirtin.

**L-3 (ZORUNLU).** Güvenliği, veri tutarlılığını ve önce testi her seviyede koruyun. Gerçek veri veya dış erişim varsa MVP denetimlerini uygulayın. Seviye geçişini engelleyen borcu kanıtla kapatın.

## 3. Bütün dosyalar için ortak yazım

**F-1 (ZORUNLU).** Dosyayı UTF-8 ile yazın. Dosyanın başına BOM koymayın. BOM, dosyanın başındaki görünmez işarettir. El yazımı dosyayı satır sonuyla bitirin.

**F-2 (ZORUNLU).** Projenin biçimlendiricisini ve girintisini izleyin. Değişmeyen satırları yeniden biçimlendirmeyin. Üretilen dosyada üreticinin biçimi önce gelir.

**F-3 (ZORUNLU).** Büyük dosyayı elle baştan yazmayın. Hedefli düzenleme yapın. Sonra satır veya kayıt sayısını öncekiyle karşılaştırın.

**F-4 (ZORUNLU).** Koddaki görünen metni uygun çeviri işleviyle sarın. Kodda ve tanım dosyalarında kaynak metni İngilizce yazın. Türkçe metni yalın Türkçe kurallarına göre yazın. Cümleyi parçalardan birleştirmeyin.

**F-5 (ZORUNLU).** Parolayı, anahtarı ve kişisel veriyi depoya koymayın. Ölçümden ve günlükten de çıkarın. Örnek dosyada sahte değer kullanın. Python belgesindeki G-9 ve G-15 kurallarını uygulayın.

**F-6 (ZORUNLU).** Veri tarihini okuyucunun beklediği biçimde yazın. Yeni sözleşmede ISO 8601 biçimini seçin. Örneğin `"2026-11-20"` yazın. Saat bilgisi varsa saat dilimini sözleşmeye yazın.

**F-7 (ZORUNLU).** Dış girdinin türünü, boyutunu ve kaynağını sınayın. Yeni erişimde yetki reddini deneyin. Paket ve gizli bilgi taramasında Python belgesindeki G-14 kuralını izleyin.

## 4. JSON dosyaları

Frappe'nin DocType çıktısı sıralı anahtar ve tek boşluklu girinti kullanır. Türkçe harfi `\u` ile yazar. Dosya sonu sürüme ve dosya türüne göre değişir.

**J-1 (ZORUNLU).** Projenin üreteci varsa onu kullanın. Proje elle yazımı seçmişse yöntemi Ek A'ya yazın. Bu yollar yoksa Python belgesindeki M-5'i uygulayın. JSON ve yan dosya farkını inceleyin.

**J-2 (ZORUNLU).** Elle düzeltmede dosyanın mevcut biçimini koruyun. `field_order` varsa `fields` ile aynı adları taşısın. Alan adını aynı listede yinelemeyin. Alan türü, varsayılan ve izin farkını inceleyin. Bağlı kayıt türünü ve alt tabloyu doğrulayın.

**J-3 (ZORUNLU).** Standart kaydı kendi üretim yolundan değiştirin. Çalışma alanı, rapor ve yazdırma biçimi buna örnektir. Eşitleme koşullarını Ek B'den doğrulayın.

**J-4 (ZORUNLU).** Yüklemeden sonra sitedeki gerçek kaydı denetleyin. Dosya değişti diye kaydı yüklenmiş saymayın.

**J-5 (ZORUNLU).** `fixtures`, uygulamayla taşınan hazır kayıtlardır. Dar dışa aktarım süzgeci yazın. Yeni kaydın süzgece uyduğunu sınayın. İçe alım kancaya bakmaz. Klasördeki her JSON dosyasını yüklemeyi dener. Aynı adlı kaydı değiştirebilir. Yükleyici dosyadan çıkan kaydı siteden silmez. Silme için yama yazın. Yükseltme temizliği için Ek B'ye bakın. Yükleme uyarısı varsa siteyi denetleyin.

**J-6 (ZORUNLU).** Bir site kaydını tek yoldan taşıyın. Örneğin “Custom Field” için `fixtures` veya `custom` seçin. `custom` yolunda `sync_on_migrate` ayarını denetleyin. Dolu `custom_perms` listesi eşitlenen türlerin özel izinlerini değiştirir.

**J-7 (ZORUNLU).** Gerçek site ayarlarını depoya koymayın. `site_config.json` veritabanı parolası taşıyabilir. Site dosyasındaki değer ortak ayar dosyasındaki aynı anahtarın yerini alır. Ortam değişkenlerinin etkisini hedef sürümde doğrulayın.

**J-8 (ZORUNLU).** Sık süzülen veri için önce DocType alanını değerlendirin. Satır kümesi için alt tabloyu inceleyin. JSON seçerseniz sorguyu ve erişim kurallarını sınayın.

**J-9 (ZORUNLU).** Düz JSON'a yorum veya sondaki virgülü eklemeyin. Okurken iç içe nesnelerdeki yinelenen anahtarları da yakalayın. Şema, kabul edilen alanları ve türleri tanımlar. Şema varsa anahtar denetiminden sonra şemayı sınayın. `NaN` ve sonsuz değer yazmayın. Yorumlu biçimi kendi aracıyla sınayın.

**J-10 (ZORUNLU).** Sayı gibi görünen kimliği metin olarak yazın. Telefon, başı sıfırlı kod ve büyük kimlik böyledir. Eksik anahtar, `null` ve boş metin ayrı anlam taşır. `0` ve `false` değerlerini de ayrı sınayın.

**J-11 (ZORUNLU).** Tarih ve tutar biçimini gerçek Frappe yanıtından doğrulayın. `Decimal` değeri kayan noktalı sayıya dönüşebilir. Tutarın birimini ve yuvarlama kuralını sözleşmeye yazın.

## 5. YAML dosyaları

YAML, boşlukla gruplanan veri biçimidir. Sürüm 1.1 ve 1.2 bazı değerleri farklı okur. Hedef okuyucuyu ve seçtiği tür kurallarını doğrulayın.

**Y-1 (ZORUNLU).** Başka türe dönebilen metni çift tırnakla yazın. `"no"`, `"yes"`, `"on"` ve `"off"` böyledir. Okuyucu anahtarı başka türe çeviriyorsa anahtarı tırnaklayın. Sürüm numarasını örneğin `"3.10"` yazın.

**Y-2 (ZORUNLU).** Baştaki sıfırı taşıyan değeri tırnakla yazın. Metin olan saati ve tarihi de tırnaklayın. `#` içeren metni tırnaklayın. Çok satırlı değerde `|` ve `>` çıktısını sınayın.

**Y-3 (ZORUNLU).** Girintide yalnız boşluk kullanın. Aynı anahtarı iki kez yazmayın. İç içe anahtarı da denetleyin.

**Y-4 (ZORUNLU).** Güvenilmeyen YAML'ı güvenli yükleyiciyle okuyun. PyYAML kullanıyorsanız `yaml.safe_load` seçin. Girdi boyutunu ve iç içe yapıyı sınırlayın. `<<` ile birleştirmeyi hedef araçta sınayın.

**Y-5 (ZORUNLU).** Yeni zamanlanmış çalışma için proje sahibinin açık `cron` kurulum isteği gerekir. İş akışındaki `schedule` anahtarı buna dahildir. Hazır kayıt ve kabuk betiği de dahildir. Kopyalama ve yeniden açmada Python belgesindeki V-9 geçerlidir.

**Y-6 (ZORUNLU).** Canlıya yükleyen iş akışını proje kararı olmadan eklemeyin ve değiştirmeyin. Bu akışı proje kararı olmadan tetiklemeyin.

**Y-7 (ZORUNLU).** GitHub Actions akışında en dar `permissions` ayarını yazın. İşe `timeout-minutes` ile süre sınırı koyun. Güvenilmeyen girdiyi `run` komutunun metnine eklemeyin.

**Y-8 (ZORUNLU, MVP ve üstü).** Yeni veya değişen GitHub Actions dış eylemini sabitleyin. Asıl depodan doğrulanan tam Git kayıt kimliğini kullanın. `@v4` gibi etiket sonradan değişebilir.

**Y-9 (ZORUNLU).** Compose dosyasında imaj sürümünü sabitleyin. Yalnız gereken portu açın. Kısa port eşlemesinde adresi açıkça yazın. Yerel örnek olarak `"127.0.0.1:8000:8000"` kullanın.

**Y-10 (ZORUNLU).** Ayarı hedef aracın denetimiyle sınayın. Compose için `docker compose --env-file sahte.env config --quiet` çalıştırın. Komutu yalnız sahte ayarlarla yalıtılmış ortamda çalıştırın. Dosya birleşimini ve profili sınayın.

**Y-11 (ZORUNLU).** OpenAPI, istek ve yanıtları tarif eden belge biçimidir. Sözleşmeyi ana dosyadan denetleyin ve `$ref` bağlantılarını çözün. OpenAPI sürümüne uygun şema kullanın. Yanıtı, hata yolunu ve yetkiyi gerçek istekle sınayın.

## 6. Kurulum ve liste dosyaları

Yama, var olan veriyi yeni sürüme taşıyan koddur. Frappe `patches.txt` listesini aşama ve satır sırasıyla işler. “Patch Log” tamamlanan yamanın kimliğini tutar.

**K-1 (ZORUNLU).** Yeni yamayı doğru bölümün sonuna ekleyin. `[pre_model_sync]` bölümü tanım eşitlemesinden önce çalışır. `[post_model_sync]` bölümü sonra çalışır. Eski bölümsüz liste ilk aşamada çalışır.

**K-2 (ZORUNLU).** Çalışmış yama satırını değiştirmeyin. Kimlik değişirse Frappe yamayı yeniden çalıştırabilir. Düzeltme için yeni yama ekleyin.

**K-3 (ZORUNLU).** Yama satırını yinelemeyin ve girintilemeyin. Yorumları ayrı satıra yazın. Bölümlü listede iki bölüm adını da koruyun. Başka bölüm adı eklemeyin. Frappe 15 ve 16 o bölümü sessizce atlar. Listeye `execute:` ile kod gömmeyin.

**K-4 (ZORUNLU).** Yeni kurulumu yalnız yamaya bağlamayın. Olağan kurulumda Frappe yamaları çalışmış sayar. Olağan yükseltmede hazır kayıtlar yamalardan sonra yüklenir. Kurulumda `after_install` hazır kayıtlardan önce çalışır. Hazır kayda bağlı adımın sırasını sınayın. Atlanan yamayla geçişi tamamlanmış saymayın. Kurulum ve tekrar denemesinde Python belgesindeki V-7'ye uyun.

**K-5 (ZORUNLU).** `modules.txt` dosyasında her satıra bir modül adı yazın. Adı klasörle eşleştirin. Kurulum ve yükseltmede “Module Def” kaydını doğrulayın. Yeni modülde Python belgesindeki B-1'i izleyin.

**K-6 (ZORUNLU).** Paket bağımlılığını mevcut kurulum aracının okuduğu bölümde bildirin. Python paketi için `pyproject.toml` içindeki `[project].dependencies` alanına bakın. Bench destekliyorsa Frappe aralığını `[tool.bench.frappe-dependencies]` bölümüne yazın. Eski paket listesini kaldırmadan kurulumu sınayın. Uygulama lisansını proje kararı olmadan seçmeyin veya değiştirmeyin.

**K-7 (ZORUNLU).** Projenin paket yöneticisini kullanın. Kilit dosyasını kendi aracıyla güncelleyin. İkinci kilit dosyası üretmeyin.

**K-8 (ZORUNLU).** Gerçek `.env` dosyası için yok sayma kuralı yazın. `.env.example` aynı anahtarları sahte değerle taşısın. Örnek ayarın ve tanım dosyasının depoya girebildiğini sınayın. Açığa çıkan erişim anahtarının iptalini bildirin. Geçici ajan dosyasını depoya ve `public` klasörüne koymayın.

**K-9 (ZORUNLU).** Araç ayarının üst klasörden gelen kurallarını kontrol edin. `.gitignore` eşleşmesini `git check-ignore -v` ile görün. `Dockerfile` ve `Makefile` varsa kendi araçlarıyla sınayın. Git yazar korumasını ve `core.hooksPath` ayarını değiştirmeyin.

## 7. JavaScript ekran betikleri

Frappe form betiğini ilgili kayıt türünün formunda çalıştırır. `app_include_js` betiği yönetim ekranının ortak yüküne ekler. `web_include_js` web şablonunun ortak yüküne eklenebilir.

**E-1 (ZORUNLU).** Betikten önce alan ayarını deneyin. Görünürlük, zorunluluk ve değer getirme ayarı böyledir. Betiği ayar yetmezse yazın. Sunucu `mandatory_depends_on` koşulunu kendiliğinden denetlemez. Koşulu sunucuda da doğrulayın.

**E-2 (ZORUNLU).** Betiğe iş kuralı, yetki ve gizli bilgi koymayın. Kullanıcı betiği atlayabilir.

**E-3 (ZORUNLU).** Betiği Frappe'nin beklediği dosyaya yazın. Standart form için `ad.js`, liste için `ad_list.js` kullanın. Başka uygulamanın formu için `doctype_js` kancasına bakın. Liste için `doctype_list_js` kancasına bakın. Alt tablonun betiğini üst formun dosyasına yazın.

**E-4 (ZORUNLU).** Kalıcı betiği uygulama dosyasında tutun. “Client Script” kaydı gerekiyorsa sahibini ve taşıma yolunu yazın.

**E-5 (ZORUNLU).** Her sayfaya yüklenen betiği küçük tutun. Seyrek kullanılan kodu `frappe.require` ile gerektiğinde yükleyin. Yüklemeyi ağ kaydında doğrulayın. Boyut sınırını proje kaydından alın.

**E-6 (ZORUNLU).** Düz dosya için `/assets/uygulama/js/dosya.js` gibi kökten başlayan yol kullanın. Derlenen dosyayı `ad.bundle.js` adıyla çağırın. Yüklemeyi tarayıcının ağ kaydından doğrulayın.

**E-7 (ZORUNLU).** Paket girişini `public` altında `ad.bundle.js` biçiminde adlandırın. Paket adı aynı Bench içindeki uygulamalarda benzersiz olsun. Derleme çıktısını elle değiştirmeyin.

**E-8 (ZORUNLU).** Uygulamanın mevcut sunucu çağrı yolunu kullanın. Örneğin `frappe.call` seçin. Hata durumunu ekranda ele alın. `async: false` kullanmayın. Her satır için ayrı çağrı açmayın.

**E-9 (ZORUNLU).** Çift tıklamayı ve geç gelen yanıtı sınayın. Kalıcı yazmada tekrarı sunucuda engelleyin.

**E-10 (ZORUNLU).** Kullanıcı metnini `textContent` ile gösterin. HTML metni gerekiyorsa `frappe.utils.escape_html` kullanın. `frappe.msgprint` HTML işler. Bağlantının adres türünü doğrulayın.

**E-11 (ZORUNLU).** Görünen metni `__("Metin")` ile yazın. Değer eklemek için `{0}` gibi yer tutucu kullanın. Metnin çeviri listesine çıktığını doğrulayın.

**E-12 (ZORUNLU).** `refresh` olayında tekrarlanan ağır işi önleyin. Aynı düğmeyi veya dinleyiciyi iki kez eklemeyin.

**E-13 (ZORUNLU).** JavaScript ve TypeScript dosyasının çalıştığı ortamı doğrulayın. Node.js, JavaScript'i tarayıcı dışında çalıştırır. Modül biçimini ve mevcut derleme yolunu inceleyin. TypeScript tür denetimini çalıştırın. Dış veriyi program çalışırken de doğrulayın.

**E-14 (ZORUNLU, Scale ve üstü).** Önceki ve yeni derleme çıktısını aynı koşulda ölçün. Ham, sıkıştırılmış ve ağdan aktarılan boyutu ayırın. Web sayfasını boş ve dolu önbellekle ayrı ölçün. Önbellek, önce alınan veriyi geçici olarak saklar.

**E-15 (ZORUNLU, Scale ve üstü).** Etkilenen akışta yanıt süresini ve sorgu sayısını ölçün. Gerekirse belleği ölçün. Yük ve veri sayısını rapora yazın. Python belgesindeki P-11 ve P-12'ye uyun.

## 8. HTML ve Jinja şablonları

Jinja, Frappe'nin sunucuda kullandığı şablon dilidir. Şablondaki `{{ }}` yerlerine değer koyar. Kaçış, özel işaretlerin HTML kodu gibi çalışmasını önler. Rapor, sayfa ve DocType şablonunu tarayıcı da işleyebilir. Tarayıcı şablonunda HTML metnini `frappe.utils.escape_html` ile kaçırın.

**W-1 (ZORUNLU).** Değeri kullanıldığı yere uygun biçimde kaçırın. Jinja'da HTML metni için `{{ ad | e }}` yazın. `| safe` süzgecini yalnız bu kullanım için temizlenmiş HTML'de kullanın. Bağlantı adresinin türünü doğrulayın.

**W-2 (ZORUNLU).** Şablonu eksik veriyle de sınayın. Jinja eksik değişkeni `{{ ad }}` olarak gösterebilir. Eksik değişkenin alanına erişmek hata verebilir.

**W-3 (ZORUNLU).** Şablona iş kuralı koymayın. İzinli veriyi çağıran kod hazırlasın. Şablonda kayıt başına sorgu açmayın.

**W-4 (ZORUNLU).** Kullanıcının yazdığı metni şablon olarak çalıştırmayın. Python belgesindeki G-10 kuralını uygulayın.

**W-5 (ZORUNLU).** Kişiye özel sayfada ortak önbelleği kapatın. Sayfa kodunda `no_cache = 1` ayarını doğrulayın. Erişimi ve sunucu dışındaki önbelleği de sınayın. `www` sayfası girişsiz açılabilir. Özel sayfada erişimi sunucuda denetleyin.

**W-6 (ZORUNLU).** E-posta şablonunda dış betik ve dış stil kullanmayın. Gönderimde oluşan stili ve bağlantıları denetleyin. E-postayı test kutusunda sınayın.

**W-7 (ZORUNLU).** Yazdırma için önce hazır “Print Format” aracını kullanın. Özel şablonda sayfa kırılınca içeriğin kaybolmadığını sınayın.

**W-8 (ZORUNLU).** Uygunsa betiği ayrı dosyada tutun. Jinja'da JSON veri bloğu için `tojson` kullanın. HTML özelliğinde `tojson` çıktısını tek tırnağa alın. Çift tırnakta `forceescape` ekleyin. `| e` tek başına yetmez.

**W-9 (ZORUNLU).** Frappe'den veri sunan ekranlarda Python belgesindeki P-8 ile P-10'u uygulayın.

**W-10 (ZORUNLU).** E-posta ve yazdırma şablonunda okuyucunun dilini kullanın. Tarih ve tutar için Frappe'nin biçim ayarlarını uygulayın. Örneğin `doc.get_formatted` kullanın.

## 9. CSS, SCSS ve görseller

**C-3 (ZORUNLU).** Seçiciyi dar tutun. Sınıf adının çakışmadığını doğrulayın. `body` ve `.btn` gibi ortak seçicileri ezmeyin.

**C-4 (ZORUNLU).** `!important` ancak mevcut kuralla çözülemiyorsa kullanın. Nedeni yorumda yazın.

**C-6 (ZORUNLU).** Standart forma özel stili `ad.css` dosyasına yazın. Bu stil sayfa geneline uygulanır. `app_include_css` yönetim ekranına, `web_include_css` web sayfasına ortak stil ekler.

**C-7 (ZORUNLU).** `public` ve yayımlanan `docs` altında yalnız açık dosya tutun. SVG içindeki çalıştırılabilir içeriği denetleyin. Görselin lisansını ve boyutunu inceleyin. Anlam taşıyan görsele alternatif metin yazın.

## 10. Çeviri dosyaları

Frappe iki sürümde de `translations/dil.csv` yolunu okur. Derlenmiş `.mo` sözlüğünü de okur.

**I-1 (ZORUNLU).** Projenin kullandığı çeviri yolunu izleyin. Aynı metni iki yolda elle yönetmeyin. `.pot` ve `.mo` dosyasını araç üretir.

**I-2 (ZORUNLU).** CSV satırını 2 veya 3 sütunla yazın. Sütunlar kaynak, çeviri ve bağlamdır. Başlık satırı eklemeyin.

**I-3 (ZORUNLU).** Virgül, tırnak ve satır sonu için CSV yazıcısı kullanın. Hedef okuyucuyla sütunları ve çevrilen metni sınayın.

**I-4 (ZORUNLU).** Kaynak metni koddaki metinle birebir aynı yazın. Koddaki metin değişirse bütün dil dosyalarını güncelleyin.

**I-5 (ZORUNLU).** `{0}` gibi yer tutucuları çeviride koruyun. Aynı kaynak ve bağlam çiftini yinelemeyin.

**I-6 (ZORUNLU).** Test CSV'sinde sütunları ve örneğin kaynağını yazın. Elektronik tabloya aktarılan metnin formül olarak çalışmasını önleyin.

## 11. SQL, kabuk betiği ve ortam dosyası

**Q-1 (ZORUNLU).** Kalıcı DocType yapısında Python belgesindeki V-6 kuralını uygulayın. SQL dosyasının çağrıldığı yeri bulun. Üretilen SQL için kaynak ve komutu kaydedin. Deneme şemasını yalnız ayrı test veritabanında kullanın.

**Q-2 (ZORUNLU).** Sorgu değerini ayrı parametre olarak verin. Alan ve sıralama adını izinli listeden seçin. Sorguyu hedef veritabanında sahte veriyle sınayın. Büyüyen sorguda `EXPLAIN` ile çalışma planını inceleyin. SQL betiğini canlı veritabanında elle çalıştırmayın.

**Q-3 (ZORUNLU).** “Query Report” ham okuma sorgusu çalıştırır. Raporu açma izni ile satır iznini ayrı sınayın. Kısıtlı kullanıcıyla ve başka sahibin kaydıyla çıktıyı denetleyin.

**Q-4 (ZORUNLU).** Kabuk betiğinin ilk satırında çalıştıracak kabuğu belirtin. `pipefail` seçeneğini yalnız destekleyen kabukta kullanın. Değişkenleri tırnak içinde kullanın. Kullanıcı değerini `eval` ile çalıştırmayın. Hata ve kesilme durumunda çıkışı sınayın.

**Q-5 (ZORUNLU).** Veri silen komutu proje kararı olmadan betiğe koymayın. Örneğin `drop-site` ve `reinstall` komutlarını inceleyin. Siteyi açıkça seçin. İşlemden önce hedefi ve geri dönüş yolunu doğrulayın.

**Q-6 (ZORUNLU).** Ayar şablonunda yalnız tanımlı yer tutucuyu doldurun. Örneğin nginx'in kendi `$host` değişkenini koruyun. Üretilen ayarı yalıtılmış ortamda sınayın. Denetim için canlı servisi yeniden başlatmayın.

**Q-7 (ZORUNLU).** Kabuk yazımını hedef sistemin kabuğuyla sınayın. Örneğin `bash -n` veya `dash -n` kullanın. Sahte girdilerle çıkış kodunu denetleyin.

## 12. Dosyalar arası bağ ve modül sınırı

Modüler monolit, modüllerin tek uygulama olarak çalışmasıdır. Bir alanın adı birçok dosyada geçer. Düşük bağımlılık, bir değişikliğin başka dosyalara yayılmasını azaltır.

**X-1 (ZORUNLU).** Ad değişince bütün dosya türlerinde arayın. Tanımda, betikte, şablonda ve çeviride arayın. Yamaları, raporları ve `fixtures` dosyalarını da inceleyin.

**X-2 (ZORUNLU).** Modüle ait dosyanın tek bir sahibi olsun. Başka modülün açtığı çağrıyı veya kancayı kullanın. Python belgesindeki M-4, B-2 ve B-3 kurallarını izleyin.

**X-3 (ZORUNLU).** Her sayfaya yüklenen betik ve stil gizli bağ kurar. Bu bağı proje kaydına yazın.

**X-4 (ZORUNLU).** Sıraya dayanan bağı kaydedin. Yama sırası ve `fixtures` yükleme sırası böyledir.

**X-5 (ZORUNLU).** Kullanan yerler ayrı yayımlanıyorsa gerekirse iki adı geçici okuyun. Eski veriyle ve mevcut çağıranlarla geçişi sınayın. Geçiş bitince eski adı kaldırın.

**X-6 (ZORUNLU).** Modüller arasındaki bağımlılık yönünü kaydedin. Döngüye izin vermeyin. Planlamada Python belgesindeki B-7 ile B-9'u uygulayın. MVP ve üstünde B-10'u uygulayın. Ayrı servis veya olay kuyruğu için somut gerekçe yazın. Önemli kararı ve geri dönüşü proje kaydına yazın.

**X-7 (ZORUNLU).** Modül veya dosya sınırı değiştiğinde SOLID ilkelerini inceleyin. Etkisini ve sınadığınız davranışı rapora yazın.

SOLID ilkeleri bu dosyalara şöyle uyar:

- **SRP, tek sorumluluk.** Bir dosya tek iş yapsın. Betik ekranı, şablon görünümü taşısın.
- **OCP, genişletmeye açıklık.** Yeni alanı isteğe bağlı ekleyin. Eski kayıt çalışmaya devam etsin.
- **LSP, yerine geçebilme.** Yeni şablon mevcut çağıranlarla aynı sözleşmeye uysun. İki şablonu aynı örneklerle sınayın.
- **ISP, arayüz ayrımı.** Sayfaya yalnız gereken betiği ve alanı gönderin.
- **DIP, bağımlılığı tersine çevirme.** Betik sunucu ucuna bağlansın. Tablo adına bağlanmasın.

## 13. Önce test ve doğru sonucun kaynağı

Sözdizimi denetimi dosyanın biçimini sınar. Test için beklenen sonucu ayrı belirleyin. Testin doğru sonucu nereden alacağına “oracle sorunu” denir.

| Dosya | Önce yazılacak denetim |
|---|---|
| Tanım dosyası | Alanı, izinleri ve yüklenen kaydı sınayan test |
| Form betiği | Arayüz testi. Araç yoksa yazılı deneme adımı. |
| Şablon | Örnek veriyle şablon testi |
| Çeviri | Eksik ve atlanan satır denetimi |
| YAML ve TOML | Aracın kendi denetimi |
| Yama listesi | Boş kurulum ve yükseltme denemesi |

**N-1 (ZORUNLU).** Beklenen sonucu bağımsız kaynağa bağlayın. Onaylı örnek, resmî sözleşme veya bağımsız hesap kullanın. Kaynak yoksa proje sahibinden somut örnek onayı alın.

**N-2 (ZORUNLU).** Davranış değişikliğinde veya hata düzeltmesinde önce denetimi yazın. Denetimin beklenen nedenle başarısız olduğunu görün. Düzeltmeden sonra aynı denetimi çalıştırın.

**N-3 (ZORUNLU).** Dosyayı gerçek okuyucusuyla sınayın. Tanım için `bench migrate` komutunu test sitesinde çalıştırın. Veri geçişini boş kurulumda ve eski veride sınayın.

**N-4 (ZORUNLU).** Beklenen değeri değiştirdiğiniz dosyadan kopyalamayın. Denetimi geçirmek için kuralı gevşetmeyin.

**N-5 (ZORUNLU).** Denetimin hatalı örneği gerçekten reddettiğini görün. Testte uydurma kayıt kullanın.

**ÖNERİLİR.** Yalnız yazımı değişen dosyada yeni test kurmayın. Okuyan aracın mevcut denetimini çalıştırın.

## 14. Kontroller ve rapor

**U-1 (ZORUNLU).** Komutları kendiniz çalıştırın. Her denetimin komutunu, sürümünü ve sonucunu yazın. Geçtiyse `pass`, kaldıysa `fail` yazın. Çalışmadıysa `not_run`, kapsam dışıysa `not_applicable` yazın. Nedenini belirtin. Eksik otomatik denetimi raporlayın.

**U-2 (ZORUNLU).** Değişikliği istenen işle sınırlayın. Kuralları yeni ve değişen satıra uygulayın. Eski satırı sırf kurala uydurmak için değiştirmeyin. Gördüğünüz güvenlik ve veri sorununu bildirin.

**U-3 (ZORUNLU).** Raporu, soruyu ve uyarıyı yalın Türkçe yazın. Önce olanı ve proje sahibine etkisini söyleyin. Gereken adımı ve karar sahibini yazın. Komut ve çıktıyı sona koyun. Teknik terimi ilk kullanımda açıklayın.

**U-4 (ZORUNLU).** Boyut uyarısında sınırı ve ölçülen dosya türünü yazın. Önceki değeri, yeni değeri ve kalan payı belirtin. Python belgesindeki P-11 ve P-12'yi uygulayın.

**U-5 (ZORUNLU).** Yetki, veri geçişi ve ortak sözleşme değişikliğini bağımsız incelemeye verin. İnceleme yapılamazsa bunu raporlayın.

**U-6 (ZORUNLU).** Kurulum veya kullanım değiştiyse belgeyi de güncelleyin. Komutun çalışacağı klasörü belirtin.

## Ek A. Proje kaydına yazılacaklar

Python belgesinin Ek A'sındaki kaydı kullanın. Bu dosyalar için şu bilgileri ekleyin.

- Her dosya türünün sahibi, üreticisi ve okuyucu sürümü.
- Biçimlendirici, girinti ve denetim komutları.
- Üretilen dosyalar ve üreten komut.
- Her sayfaya yüklenen betik ve stil listesi.
- Onaylı boyut sınırı ve ölçüm koşulu.
- Çeviri yolu, kaynak dil ve desteklenen diller.
- `fixtures` ile taşınan kayıt türleri ve yükleme sırası.
- Modül bağı, geçiş kararı ve geri dönüş yolu.
- Teknik borcun sorumlusu ve kapanma koşulu.

## Ek B. Doğrulanan davranışlar

Frappe satırları 15.126.1 ve 16.56.0 kaynaklarına dayanır. Sürüm veya araç değişirse ilgili davranışı yeniden sınayın. Kullanımdan kalkan kodlar: C-1, C-2 ve C-5. Bu kodları yeniden kullanmayın.

| Konu | Görülen davranış |
|---|---|
| Tanım eşitlemesi | Frappe eşit dosya özetinde DocType kaydını atlar. Diğer standart kayıtta dosyanın `modified` değeri daha yeniyse yükler. Frappe 16 siteye özel Kanban panosunu korur. |
| Yükseltmede silme | Frappe 15, denetleyicisi yüklenemeyen standart DocType kaydını silebilir. Frappe 16, tanım dosyası olmayan standart DocType kaydını siler. Standart rapor, sayfa ve bildirim de kapsama girebilir. Yalnız `fixtures` ile taşımak bu kayıtları korumaz. |
| `field_order` | Frappe dolu listeyi alan sırası olarak kullanır. Listede olmayan alanları sona ekler. |
| `fixtures` | Frappe uygulamanın JSON dosyalarını ad sırasıyla işler. Frappe 16, DocType ve “Page” dışa aktarımını reddeder. |
| “Workspace” | `content` alanı JSON metnidir. Bu alanı listeye çevirmeyin. Kısayol için `content` alanına da blok ekleyin. |
| Yama satırı | Frappe işlenen adı günlüğe yazar. Satır sonu yorumu kimliğe girebilir. Aynı bölümde tekrar hata verir. Önceki yamadan derin girinti hata verebilir. |
| Paket dosyası | Derleyici paket adına içerik özeti ekler. |
| Jinja kaçışı | Frappe'nin varsayılan Jinja ortamı otomatik HTML kaçışı açmaz. |
| E-posta stili | Frappe biçimlenen e-postada stili satır içine alır. `email_css` kancası bulunan yerel stil dosyalarını ekler. |
| Çeviri satırı | Frappe boş olmayan hatalı satırı hata kaydına yazar. Varsayılan çağrı o satırı atlar. |
| JS çevirisi | İki sürüm de metin taraması yapar. JavaScript için ayrıca ayrıştırıcı kullanır. Çalışırken birleşen söze güvenmeyin. |
| Yinelenen anahtar | Python JSON, Node JSON ve PyYAML son değeri alır. Denenen Node YAML paketleri tekrar için hata verir. |
| Web sayfası başlığı | Frappe sayfa başındaki YAML bölümünü PyYAML ile okur. PyYAML tırnaksız `on` anahtarını `True`, `010` değerini 8 okur. |
