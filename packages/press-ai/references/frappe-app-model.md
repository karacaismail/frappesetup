# Frappe uygulama modeli: karar etkileyen kurallar

Paylaşan: `frappe-custom-app`, `frappe-app-extension`, `frappe-app-developer`, `frappe-change-reviewer`.

Sürüm kanıtı: frappe/frappe `version-15` `b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4` ve `version-16`
`6b450a166e076dd842e4db7ea0843f62881e62ac` (statik okuma). Sürüme bağlı her kural hedef sürüm bilinmeden uygulanmaz;
hedef yoksa sonuç `unknown` yazılır. Ayrıntılı genişletme noktası kaydı `contracts/frappe-extension-points.json`
dosyasındadır; orada `unknown` olan iddia doğrulanmış sayılmaz. Ek okuma (lisans dosyası yok, yalnız atıf):
frappe/skills `0bef982`, skills/frappe-app-dev/references ve skills/deep-app-audit/quality kuralları (A01–A41, M04).

## Kimlik ve dizin

- Uygulama adı Python paket adıdır (küçük harf, alt çizgi). Aynı ad hooks.py içindeki app_name, repodaki paket klasörü,
  Press'teki App kaydı ve App Source'un App alanıdır. İkinci bir teknik kimlik açılmaz.
- Tipik yerleşim: depo kökünde pyproject.toml; paket içinde hooks.py, modules.txt, patches.txt; her modülde
  `<modül>/doctype/<doctype_snake>/` altında DocType JSON'u, Python denetleyicisi, isteğe bağlı JS ve test dosyası;
  `public/` asset'ler, `fixtures/` dışa aktarılan kayıtlar.
- Başka bir uygulamaya bağımlılık `required_apps` ile bildirilir. Press build'i bu listeyi okur; eksik bağımlılık
  Pre-build'de "Required app not found" verir. Bağımlı app grupta kendisine ihtiyaç duyandan önce gelir.
- Sürüm gereksinimleri pyproject.toml içinde yazılır: `requires-python` ve tool.bench.frappe-dependencies tablosu; Node
  için package.json `engines`. Yeni app şablonu `requires-python` için v15'te `>=3.10`, v16'da `>=3.14` yazar
  (frappe/utils/boilerplate.py). Press bu aralıkları grup runtime'ıyla Pre-build'de karşılaştırır.
- Dal adları `version-15`, `version-16`, `develop`. Uyum branch ucundan değil, candidate'taki release commit'inden okunur.

## DocType şeması

- DocType adı kurulu tüm uygulamalarda tektir. Modül modules.txt içinde bulunmalıdır.
- Alan adları küçük harf ve alt çizgiyle yazılır; standart sütun adları (`name`, `owner`, `creation`, `modified`,
  `modified_by`, `docstatus`, `idx`, `parent`, `parenttype`, `parentfield`) alan adı olamaz.
- Standart DocType kod içindedir ve geliştirici modu açık yerel bench'te üretilir; Press sitesinde Desk'ten oluşturulan
  DocType yalnız veritabanında kalır ve uygulama koduna girmez.
- Alan silmek sütunu ve veriyi kendiliğinden taşımaz; yeniden adlandırma ve veri taşıma patch ister.
- Gönderilebilir (submittable) belgede `docstatus` akışı (Draft, Submitted, Cancelled) ve iptal/değiştirme izinleri birlikte
  tasarlanır.

## Child table

- Child DocType `istable` işaretlidir, kendi izni yoktur; erişim üst belgenin izniyle olur. Satırlar `parent`, `parenttype`,
  `parentfield`, `idx` taşır.
- Üst DocType'ta Table alanının `options` değeri child DocType adıdır. Child kaydı üst belge olmadan kaydedilmez ve doğrudan
  listelenmez; liste sorgusu üst DocType üzerinden yapılır.

## İzinler

- DocType izin satırları rol başına okuma, yazma, oluşturma, silme, gönderme, iptal, değiştirme bayraklarını ve `permlevel`
  ile `if_owner` ayarını taşır. En dar rol kümesiyle başlanır; System Manager'a varsayılan tam yetki eklemek gerekçe ister.
- Role Permission Manager'da yapılan değişiklik Custom DocPerm olarak sitede kalır ve kodun izinlerini geçersiz kılar.
- `has_permission` ve `permission_query_conditions` kancaları yalnız daraltır; yetki genişletmek için kullanılmaz.
- `ignore_permissions=True` yalnız sistem içi kayıt için ve gerekçeyle; kullanıcı girdisiyle birleşen yolda kullanılmaz.
- Beyaz listeli (whitelisted) metot çağıranın yetkisini kendisi denetler.

## hooks.py

- Statik veri dosyasıdır; içinde sorgu, ağ çağrısı veya yan etki yazılmaz. Noktalı yollar gerçekten çözümlenmelidir.
- Olay işleyicilerinin imzası çağrı yerine uyar (`doc_events` için `doc, method`). İşleyici içinde `frappe.db.commit`
  yazılmaz; işlem sınırını çerçeve yönetir.
- Bazı kancalarda son kurulan uygulama kazanır; başka uygulamanın davranışını sessizce silen işleyici yazılmaz.

## Fixtures ve dışa aktarılan özelleştirmeler

- Fixture her migrate'te zorla içe aktarılır; sitede yapılan düzenleme bir sonraki deploy'da geri döner. İki uygulama aynı
  kaydı dışa aktarırsa son uygulama kazanır.
- Filtresiz giriş (ör. tüm Custom Field kayıtları) başka uygulamaların özelleştirmelerini de dışa aktarır. Giriş modüle
  ya da ada göre filtrelenir; özel alan adları uygulamaya özgü önekle başlar.
- Dışa aktarma insan komutudur (`bench --site <site> export-fixtures --app <app>`); fixture DocType ve Page için kullanılmaz.
- Customize Form ile yapılıp dışa aktarılmayan değişiklik koda girmez; diğer sitelerde ve yeniden kurulumda kaybolur.

## Patch ve migrate

- patches.txt iki bölüm taşır: `[pre_model_sync]` (eski şemayı okuyan, ör. kaldırılacak alanın verisini taşıyan patch) ve
  `[post_model_sync]` (yeni şemayı gerektiren, olağan bölüm). Patch, `execute()` fonksiyonu olan bir modüldür.
- Patch site başına bir kez, satırdaki metinle Patch Log'a yazılarak çalışır. Satırı yeniden adlandırmak patch'i tüm
  sitelerde yeniden çalıştırır. Patch ikinci kez çalıştığında hiçbir şeyi değiştirmeyecek biçimde yazılır; büyük tabloda
  parça parça işler.
- Aynı sürümde eklenen alanı okuyan patch başında DocType'ı yeniden yükler.
- Migrate sırası (özet): `before_migrate`, pre patch'ler, şema eşitleme, post patch'ler, fixture'lar, `after_migrate`.
  Press'te site migrate'i `site.migrate` ile, yeni sürüme taşıma deploy sonrası site güncellemesiyle olur; otomatik
  güncellemesi açık sitelerde Press bu güncellemeyi (migrate dahil) kendiliğinden açar. Öncesinde başarılı yedek gerekir.
  `skip_failing_patches` yalnız insanın açık kararıyla açılır.

## Asset

- Uygulama asset'leri `public/` altındadır ve bench build ile derlenir (`bench build --app <app>`); masaüstüne eklenen
  paketler hooks.py içindeki app_include_js ve app_include_css ile bağlanır. Asset derleme ve yükleme sözdizimi hedef
  sürümde doğrulanır (`unknown` kalabilir).
- Press'te asset'ler build sırasında image içinde üretilir; frontend bağımlılık ve derleme hataları build adımında görünür.

## Çeviri

- Python'da `frappe._("...")`, JavaScript'te `__("...")`; çevrilecek metin düz dize olarak yazılır (biçimlendirilmiş dize
  çıkarılamaz).
- Çeviri dosyası biçimi (CSV `translations/<dil>.csv` ya da PO tabanlı `locale/`) hedef dalda doğrulanır; doğrulanmadıysa
  `unknown`. Aynı uygulamada iki kaynak tutulmaz.

## Test

- Test tabanı v15'te FrappeTestCase, v16'da IntegrationTestCase'tir. Test dosyası DocType dizininde `test_<doctype_snake>`
  adını taşır.
- Testler ayrı bir test sitesinde koşar: `bench --site <test-site> set-config allow_tests true` bir kez, sonra
  `bench --site <test-site> run-tests --app <app>`. Komutu insan çalıştırır; çıktı gelmeden sonuç `not_run`dır.

## Genişletme mekanizmaları (sürüm)

| Mekanizma | v15 | v16 | Not |
| --- | --- | --- | --- |
| Fixture: Custom Field, Property Setter (filtreli) | var | var | İlk tercih; model ve form eklemeleri |
| `doc_events` | var | var | Yaşam döngüsü yan etkisi |
| `extend_doctype_class` | yok | var | Mixin; temel sınıfın önüne eklenir (frappe/model/base_document.py v16 180–207) |
| `override_doctype_class` | var | var | `super()` çağrılır; son uygulama kazanır; v16'da alt sınıf olmak zorunlu (base_document.py v15 88–96, v16 109–123) |
| `override_whitelisted_methods` | var | var | İmza ve dönüş sözleşmesi korunur; her yükseltmede yeniden test |
| Çekirdek yama, fork | — | — | Yapılmaz; ayrıntı frappe-app-extension skill'inde |
