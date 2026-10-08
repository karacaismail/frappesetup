# Genişletme noktaları

Her mekanizma için: ne zaman, iskelette ne üretilir, asıl kodda ne yazılır (`write_file` önerisi, insan onayı), doğrulama,
geri alma. Sürüm durumu
frappe/frappe `version-15` `b0b5b99` ve `version-16` `6b450a1` statik okumasıdır; makinece kayıt
`contracts/frappe-extension-points.json`. Ek okuma (lisans dosyası yok, yalnız atıf): frappe/skills `0bef982`,
skills/deep-app-audit/quality/A-customization (A01 monkey patch yok, A02 override `super()` çağırır, A03 eklemek için
extend, A05 override edilen metodun sözleşmesi, A08 özel alan kodda, A09 fixture siteyi ezer, A10 kaldırırken temizlik,
A11 `required_apps`, A16 özel alan öneki, A27 son kazanan kancalar, A28 izin kancaları yalnız daraltır).

## 1. Fixture: Custom Field ve Property Setter

- Ne zaman: resmi DocType'a alan eklemek; etiket, zorunluluk, görünürlük, varsayılan değer gibi özellikleri değiştirmek.
- İskelet: hooks.py fixtures girdisi, filtreyle (`add_fixture_filter`). Filtre modüle ya da uygulamaya özgü ad önekine
  göre seçer.
- Kod: alanları geliştirici yerel sitede oluşturur ve insan komutuyla dışa aktarır
  (`bench --site <site> export-fixtures --app <app>`), dosyayı gözden geçirir; yalnız bu uygulamanın kayıtları kalır.
- Doğrulama: fixture dosyasındaki kayıt adları başka uygulamaların fixture'larıyla çakışmıyor; alan adı önekli.
- Risk: fixture her migrate'te zorla uygulanır; sitede yapılan elle değişiklik geri döner. Customize Form'da yapılıp dışa
  aktarılmayan değişiklik kodda yoktur.
- Geri alma: fixture girdisini kaldırmak sitedeki kaydı silmez; kaldırma etkisi (alan, veri) hedef sürümde ayrıca
  doğrulanır ve yedekle yapılır.

## 2. `doc_events`

- Ne zaman: belgenin yaşam döngüsünde yan etki (validate, before_save, on_update, after_insert, on_submit, on_cancel,
  on_trash). `"*"` tüm DocType'lara uygulanır; gerekmedikçe kullanılmaz.
- İskelet: hooks.py girdisi ve boş işleyici (`add_doc_event`), imza `doc, method`.
- Kod (`write_file`): işleyici gövdesi; hata durumunda `frappe.throw` ile anlaşılır mesaj; commit yok.
- Doğrulama: işleyici yolu çözülüyor; resmi uygulamanın kendi işleyicisiyle sıra ve etkileşim test edildi.
- Geri alma: girdiyi kaldır, yeni release ve deploy.

## 3. `extend_doctype_class` (yalnız v16)

- Ne zaman: resmi sınıfa yeni metot veya özellik eklemek, mevcut metodu `super()` ile sarmak.
- İskelet: hooks.py girdisi ve yalnız `super().validate()` çağıran mixin sınıfı (`extend_doctype_class`, `mode: extend`).
- Kod (`write_file`): metot gövdeleri; sarılan her metotta `super()` çağrısı korunur.
- Doğrulama: v16 hedefinde uzantı sınıfı temel sınıfın önünde yer alır (frappe/model/base_document.py v16 180–207);
  diğer uygulamaların uzantılarıyla zincir bozulmuyor.
- v15: yoktur; önerilmez.

## 4. `override_doctype_class`

- Ne zaman: 1–3 yetmiyor ve sınıf davranışı değişmek zorunda.
- İskelet: hooks.py girdisi ve asıl sınıftan türeyen, yalnız `super().validate()` çağıran sınıf (`mode: override`).
- Kod (`write_file`): değişen metotlar; her birinde gerekçe ve `super()` çağrısı.
- Doğrulama: v16'da override sınıfı asıl sınıfın alt sınıfı olmak zorundadır (base_document.py v16 109–123; v15 88–96).
  Kurulu başka bir uygulama aynı DocType'ı override ediyorsa son kurulan kazanır ve diğeri sessizce düşer: çakışma raporlanır,
  çözüm kararı insandadır.
- Yükseltme: resmi uygulama sürümü değiştiğinde override edilen her metodun imzası yeniden okunur.

## 5. `override_whitelisted_methods`

- Ne zaman: istemcinin çağırdığı bir API metodunun davranışı değişmek zorunda ve olay ya da sınıf yolu yok.
- İskelet: ayrı bir değişiklik türü yoktur; hooks girdisi ve metot `write_file` ile önerilir, `app_check` denetler.
- Kod: aynı imza, aynı dönüş biçimi, aynı izin denetimi.
- Doğrulama: her resmi uygulama yükseltmesinde yeniden test; son kurulan uygulama kazanır.

## 6. Çekirdek yama ve fork

Resmi uygulamanın dosyasını değiştirmek varsayılan değildir. press-ai'de core akışı: ilk istek `core_warning` döner ve öneri
oluşmaz; ajan uyarıyı gösterip durur; kullanıcı aynı değişikliği açıkça yeniden isterse öneri oluşur ve ayrı terminalde
`APPROVE <digest12>` ile `CORE <uygulama>` (doğrulanmamış dosyada `CORE UNCHECKED <uygulama>`) onayı ister; onaysız core yolu
`core_not_approved` ile reddedilir. Fork ajan tarafından açılmaz. Her iki durumda karar kaydı: neden genişletme noktalarının
yetmediği, sorumlu kişi, yukarı akışa katkı veya dönüş planı, her yükseltmedeki birleştirme maliyeti.

## Diğer noktalar

`doctype_js` (form istemci genişletmesi), `doctype_list_js`, `permission_query_conditions` ve `has_permission` (yalnız
daraltır), `scheduler_events` (noktalı yol bir API'dir, yeniden adlandırılmaz). Sürüm durumu kontrat kaydında yoksa `unknown`.

## Yükseltme denetimi (resmi uygulama veya Frappe sürümü değişince)

1. Hedef sürüm ve resmi uygulamanın yeni commit'i belirlenir.
2. `app_check {app_path, target_frappe}` yeni hedefle koşar.
3. Override ve extend edilen her metodun imzası yeni commit'te okunur; değişen imza bulgu olarak yazılır.
4. `override_whitelisted_methods` girdileri yeniden test edilir.
5. Fixture kayıtlarının hedef DocType'ta hâlâ geçerli alanlara bağlı olduğu denetlenir.
6. Testleri insan koşar; çıktı yoksa `not_run`.
