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

## Kapsam

- Kapı DocType tanımlarını okur. DocType, bir kayıt türünün tanımıdır.
- Kapı kayıt türünün ve alanlarının açıklamalarını arar.
  `Section Break`, `Column Break` ve `Tab Break` alanları açıklama istemez.
- Kapı dışarıya açılan Python işlevlerini OpenAPI sözleşmesiyle iki yönde karşılaştırır.
  OpenAPI, bir ağ işleminin adresini ve nasıl çağrıldığını tarif eder.
  Kapı işlev üreten kodu inceler ve dışarıya açılan adları arar.
  İçteki açık işlevin dış adını bulamazsa bulgu yazar.
  Kapı `override_whitelisted_methods` kaydındaki açık adresi yeni işlevle eşleştirir.
  Kapı bu kayıtla değiştirilmemiş hazır Frappe adreslerini atlar.
- Kapı sağlayıcı kitaplıklarını sınır dosyasındaki listeyle birlikte denetler.
  Kapı paket ailesini ve metinle yazılan içe aktarma çağrılarını da arar.
  Örneğin `langchain_openai`, `langchain` ailesine girer.
- Kapı Python kodunda, yorumlarda ve uygulamanın metin dosyalarında model adı arar.
  Örneğin JavaScript ve JSON dosyalarını da okur.
- Kapı `hooks.py` dosyasında zamanlanmış iş kaydını arar.
  Kapı içe aktarılan iş kaydını ve zamanlanmış Server Script kayıtlarını da arar.
- Kapı ham SQL çağrılarını yapay zekâ modülünde ve kayıtlı araç işlevlerinde arar.
  Ham SQL, veritabanına doğrudan gönderilen sorgudur.
  Kapı sınır dosyasında yapay zekâ ve MCP yollarını bulur.
  Kapı bu yolları ve sorumlu modülleri denetler.
  Sorumlu modülde Python dosyası yoksa kapı bulgu yazar.
- Kapı araç bildiriminde `handler`, `preview` ve `prepare` değerlerini çözer.
  Kapı düz metni, birleştirilen metni ve f-string biçimini tanır.
  Kapı sabit bir sözlükten kopyalanan değerleri de inceler.
  Kapı bir değeri çözemezse veya bildirim işlev vermiyorsa bulgu yazar.
- Kapı test sınıflarındaki örnek model adlarını ve SQL çağrılarını atlayabilir.
  Bu istisna yalnız test modülündeki test sınıflarına uygulanır.
  Kapı dışarıya açılan veya bir kancaya bağlanan test modülünü bütünüyle denetler.
  Uygulama kodu test modülünü içe aktarırsa kapı yine modülün tamamını denetler.

Kapı uygulama kodunu çalıştırmaz ve dosyaları değiştirmez.
Kapı düz YAML eşlemelerini ve JSON biçimindeki OpenAPI dosyalarını okur.
Kapı girintisiz YAML listelerini de kabul eder.
Kapı işlem tanımında desteklenmeyen bir biçim görürse bulgu yazar.
Kapı çalışma anında hesaplanan adreslerin tümünü çözemez.
Kapı araç işlevinden çağrılan başka işlevleri SQL için izlemez.

## Yasaklı ad

D-13 için kapı Git'in izlediği dosyaları ve yolları tarar.
Kapı hazır alt depoların izlenen dosyalarını da tarar.
Bir alt depo hazır değilse kapı bulgu yazar.
Kapı son Git kaydının mesajını denetler.
`--commit-base` ile bir kayıt verin. Kapı o kayıttan sonraki mesajları tarar.

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

## İnceleme sonrası dal taraması

Ölçümde `12b9d0f` kaydındaki kapı ve Python 3.14.7 kullanıldı.
Tablo, taranan her dalın Git kaydını gösterir.
Kapı 12 dalda bulgu vermedi.
Kapı 10 dalda toplam 287 bulgu verdi.
4 dalda arka uç klasörü yoktu.

| Dal | Git kaydı | Sonuç | Bulgu | Ad denetimi |
| --- | --- | --- | ---: | --- |
| `_reserve/43d361e2` | `308c37a` | `pass` | 0 | `not_run` |
| `_reserve/7c7c61a6` | `8a814f4` | `not_applicable` | 0 | `not_applicable` |
| `ai-readiness-gate` | `12b9d0f` | `pass` | 0 | `not_run` |
| `backend` | `481cd35` | `pass` | 0 | `not_run` |
| `dev-ortam` | `5261c77` | `fail` | 56 | `not_run` |
| `e2e-merge-preview-cvf3hstx` | `6f61dde` | `fail` | 29 | `not_run` |
| `e2e-preview` | `f099504` | `fail` | 58 | `not_run` |
| `e2e-preview-ordered-frozen` | `6796fd3` | `fail` | 64 | `not_run` |
| `erisim-kurali` | `102002d` | `fail` | 2 | `not_run` |
| `guvenlik-kapisi` | `bb41ac3` | `fail` | 47 | `not_run` |
| `identity-sync` | `7338595` | `pass` | 0 | `not_run` |
| `ilk-dikey-dilim` | `a9f9b82` | `fail` | 8 | `not_run` |
| `integration-e2e` | `0586ff1` | `pass` | 0 | `not_run` |
| `kimlik-realm` | `02327df` | `pass` | 0 | `not_run` |
| `kimlik-tema` | `178041e` | `pass` | 0 | `not_run` |
| `main` | `f82a31c` | `not_applicable` | 0 | `not_applicable` |
| `naming-history-fix` | `3ef8a85` | `fail` | 4 | `fail` |
| `platform-core-gecit` | `d8469ab` | `pass` | 0 | `not_run` |
| `platform-core-kabuk` | `69dddb1` | `pass` | 0 | `not_run` |
| `platform-core-kimlik` | `4811e27` | `fail` | 15 | `not_run` |
| `platform-core-mobil` | `30baf3c` | `pass` | 0 | `not_run` |
| `platform-core-yz` | `f03b017` | `fail` | 4 | `not_run` |
| `press-tr` | `d26aa5d` | `pass` | 0 | `not_run` |
| `security-tooling` | `a7b24ed` | `pass` | 0 | `not_run` |
| `site-hrms-tr-rename` | `f82a31c` | `not_applicable` | 0 | `not_applicable` |
| `standartlar-ve-kararlar` | `d09c398` | `not_applicable` | 0 | `not_applicable` |
