# 0010. Yapay zekâ uygunluk kapısı

Proje kaydındaki D-9, arka uç işlemlerinin yapay zekâyla yönetilebilmesini ister.
O-13, model adlarını kayıtta tutar ve sağlayıcı kitaplıklarını yasaklar.

Depo kökünde `backend/dev/bin/ai-readiness` komutunu çalıştırın.
Kapı Python 3.14 veya üstünü ister.
Komut önce `python3.14` adını arar. Bu ad yoksa `python3` kullanır.
Komut her bulguda dosyayı ve satırı gösterir.
Bir bulgu varsa komut 1 döndürür. Bulgu yoksa 0 döndürür.
Python sürümü yetersizse komut 2 döndürür.

Başka bir arka uç klasörünü taramak için `--root` kullanın.
Programın okuyacağı çıktı için `--json` ekleyin.
JSON çıktısında `findings` bulguları, `checks.naming` ad denetiminin durumunu içerir.
Testleri çalıştırmak için `backend/dev/bin/ai-readiness --self-test` kullanın.
Güvenlik komutu da bu testleri çalıştırır.
Güvenlik komutu da Python 3.14 veya üstünü ister.
Kapı sürüm hatası verirse güvenlik komutu 1 döndürür.

## Kapsam

- Kapı karar notlarının dosya adındaki dört haneli sayıyı denetler.
  Aynı sayı iki notta varsa kapı ikinci dosyayı gösterir.
  Numaraları `backend/docs/gap-backlog.md` içindeki “Orkestratör” bölümü verir.
- Kapı `website_user_allowed_methods` kancasında doğrudan yazılan yöntem adlarını denetler.
  Uygulama yalnız kendi dışa açık yöntemlerini listeye yazar.
  Hazır Frappe yöntemleri için sözleşmenin 5. bölümündeki liste geçerlidir.
  Kapı bilinen yönetici ve servis uçlarını reddeder.
  Kapı doğrudan yazılan yönetici rolü denetimini de tanır.
  Bir yöntem başka bir hedefe yönleniyorsa kapı o hedefi de denetler.
  Kapı çalışma anında belirlenen yetkiyi çözmez. Yetkiyi uygulamanın uç testleri doğrular.

- Kapı DocType tanımlarını okur. DocType, bir kayıt türünün tanımıdır.
- Kapı kayıt türünün ve alanlarının açıklamalarını arar.
  `Section Break`, `Column Break` ve `Tab Break` alanları açıklama istemez.
- Kapı dışarıya açılan Python işlevlerini OpenAPI sözleşmesiyle iki yönde karşılaştırır.
  OpenAPI, bir ağ işleminin adresini ve nasıl çağrıldığını tarif eder.
  Kapı işlev üreten kodu inceler ve dışarıya açılan adları arar.
  İçteki açık işlevin dış adını bulamazsa bulgu yazar.
  Kapı `override_whitelisted_methods` kaydındaki açık adresi yeni işlevle eşleştirir.
  Hedef işlemin `x-frappe-original` alanı eski adresi gösterir.
  Bir hedef birden çok eski adres taşıyorsa alan bir liste olabilir.
  Kapı eski adres için ayrı işlem istemez.
  Hedefte eski adres yazmıyorsa kapı bulgu verir.
  Kapı bu kayıtla değiştirilmemiş hazır Frappe adreslerini atlar.
  Kapı üretim kodunda sonradan açılan işlevi çözemiyorsa bulgu verir.
- Kapı sağlayıcı kitaplıklarını sınır dosyasındaki listeyle birlikte denetler.
  Kapı paket ailesini ve metinle yazılan içe aktarma çağrılarını da arar.
  Kapı `frappe.get_attr` ve `frappe.get_module` çağrılarına da bakar.
  Örneğin `langchain_openai`, `langchain` ailesine girer.
- Kapı Python kodunda, yorumlarda ve uygulamanın metin dosyalarında model adı arar.
  Örneğin JavaScript ve JSON dosyalarını da okur.
  Arama kalıbı tüm model adlarını yakalayamaz.
  Örneğin kapı `gemini-pro` ve `text-embedding-3-small` adlarını yakalayamaz.
  Kapı, model ailesi adlarını yalnız arama kalıplarında kullanır.
  Kapı sağlayıcı kitaplıklarını yüklemez. Kapının kodu `apps/` tarama alanı dışındadır.
- Kapı `hooks.py` dosyasında zamanlanmış iş kaydını arar.
  Kapı içe aktarılan iş kaydını ve zamanlanmış Server Script kayıtlarını da arar.
  Kapı Auto Repeat ve Auto Email Report kayıtlarını da arar.
- Kapı `ai_tools` ve `override_whitelisted_methods` için tek düz atama ister.
  Atama dosyanın en üst düzeyinde olmalıdır.
  Örneğin kapı `+=` ve `.extend()` kullanımlarını bulgu sayar.
- Kapı ham SQL çağrılarını yapay zekâ modülünde ve kayıtlı araç işlevlerinde arar.
  Ham SQL, veritabanına doğrudan gönderilen sorgudur.
  Kapı SQL işlevinin çağrısını ve bu işleve verilen başvuruyu arar.
  Kapı veritabanının imlecine ve bağlantısına verilen başvuruları da arar.
  Kapı aynı uygulamadaki yardımcı işlevlerin çağrılarını ve başvurularını izler.
  Kapı aracın iç işlevlerinde de bu izleri arar.
  Kapı sınır dosyasında yapay zekâ ve MCP yollarını bulur.
  Kapı bu yolları ve sorumlu modülleri denetler.
  Sorumlu modülde Python dosyası yoksa kapı bulgu yazar.
- Kapı araç bildiriminde `handler`, `preview` ve `prepare` değerlerini çözer.
  Kapı düz metni, birleştirilen metni ve f-string biçimini tanır.
  Kapı sabit bir sözlükten kopyalanan değerleri de inceler.
  Kapı bir değeri çözemezse veya bildirim işlev vermiyorsa bulgu yazar.
- Kapı test sınıflarındaki örnek model adlarını ve SQL çağrılarını atlayabilir.
  Bu istisna yalnız test modülündeki test sınıflarına uygulanır.
  Kapı başka bir modülden alınan ortak test sınıfını da tanır.
  Kapı dışarıya açılan veya bir kancaya bağlanan test modülünü bütünüyle denetler.
  Uygulama kodu test modülünü içe aktarırsa kapı yine modülün tamamını denetler.

Kapı uygulama kodunu çalıştırmaz ve dosyaları değiştirmez.
Kapı düz YAML eşlemelerini ve JSON biçimindeki OpenAPI dosyalarını okur.
Kapı girintisiz YAML listelerini de kabul eder.
Kapı işlem tanımında desteklenmeyen bir biçim görürse bulgu yazar.
Kapı çalışma anında hesaplanan adreslerin tümünü çözemez.
Kapı aynı uygulamada `__init__.py` üzerinden dışa açılan işlevleri izler.
Kapı, kayıtlı araçtan çıkan `Class().method()` ve `self.method()` çağrılarını izlemez.
Kapı çalışma anında seçilen yardımcı işlevleri de SQL için çözemez.

## Yasaklı ad

D-13 için kapı Git'in izlediği dosyaları ve yolları tarar.
Kapı hazır alt depoların izlenen dosyalarını da tarar.
Bir alt depo hazır değilse kapı bulgu yazar.
Varsayılan ayarda kapı yalnız son Git kaydının mesajını denetler.
`--commit-base` ile bir kayıt verin. Kapı o kayıttan sonraki mesajları tarar.
Güvenlik komutu şimdilik varsayılan ayarı kullanır.
Ortak başlangıç kaydını güvenlik işini yürüten ekip belirleyecek.

Bu denetim depo köküne göre dosya yolu verir.
Diğer denetimler arka uç klasörüne göre dosya yolu verir.
Kapı yalnız SHA-256 özetini saklar. Özet, metinden hesaplanan bir sayı dizisidir.
Kapı harfleri ortak biçime çevirir. Kapı bilinen benzer harfleri de eşler.
Kapı küçük harfleri ve rakamları altı karakterlik parçalar hâlinde karşılaştırır.

Yolda eşleşme varsa kapı, yol yerine kısa bir kod gösterir.
`--path-code` ile bu kodu verin.
Kapı ilgili dosyanın Git listesindeki sırasını ve alt depo bilgisini verir.
Sıra 1'den başlar. Listeyi `git ls-files --cached --deduplicate` ile görebilirsiniz.
Kapı eşleşen adı çıktıya yazmaz.

## Ad denetimi

Kapı, varsa `dev/naming/check_names.py` betiğini ayrı bir Python sürecinde çalıştırır.
Betik yoksa kapı `not_run` durumunu bildirir.
Bu durumda diğer bulgular ve çıkış kodu aynen kalır.
Betik çalışamazsa kapı bulgu yazar.
