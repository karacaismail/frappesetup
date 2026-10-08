---
name: frappe-app-extension
description: ERPNext, HRMS, CRM, LMS gibi resmi Frappe uygulamalarının davranışını çekirdek dosyalara dokunmadan ayrı bir özel uygulamadan genişletir; hedef sürüme göre en dar mekanizmayı seçer (filtreli Custom Field ve Property Setter fixture'ı, doc_events, extend_doctype_class, override_doctype_class, override_whitelisted_methods) ve mekanizmanın iskeletini ve asıl genişletme kodunu press-ai MCP ile öneri, insan onayı ve apply sırasıyla yazar; davranış geliştiricinin koştuğu test çıktısıyla doğrulanır. Çekirdek yama ve fork varsayılan değildir.
---

# Resmi uygulamayı genişletme

Resmi bir uygulamanın davranışı, yalnız genişletme uygulamasının (özel app) dosyalarıyla değiştirilir. Mekanizma en dar
olandan başlayarak seçilir; her üst basamak, alttakinin neden yetmediği yazılarak kullanılır. Sürüm kanıtı frappe/frappe
`version-15` `b0b5b99` ve `version-16` `6b450a1` statik okumasıdır; ayrıntı `contracts/frappe-extension-points.json`.

MCP mekanizmanın iskeletini üretir (fixture filtresi, hooks girdisi ile boş `doc_events` işleyicisi, yalnız
`super().validate()` çağıran extend veya override sınıfı); genişletmenin asıl kodu genişletme uygulamasındaki dosyaya
`write_file` (`app_file.write`) önerisiyle yazılır. Her öneri insan onayından geçer; resmi uygulama dosyasına değişiklik
varsayılan olarak reddedilir ve yalnız core akışıyla (uyarı, kullanıcının açık tekrarı, `CORE <uygulama>` onayı) yazılır.
İskelet ya da onaylanmış kod, geliştiricinin koştuğu test çıktısı olmadan çalışan davranış sayılmaz.

## Kullan, kullanma

Kullan: "Sales Invoice'a alan ekle", "Sales Order gönderilince kayıt oluştur", "ERPNext sınıfına metot ekle", "HRMS'in bu
metodunu değiştir", "fork etmeden özelleştir".

Kullanma: yeni ve bağımsız bir uygulama (frappe-custom-app); Press'te dağıtım (press-operations).

## Önkoşullar

1. press-ai app araçları (`app_inspect`, `app_check`, `app_propose_change`, `app_apply`) yoksa dur, `not_run` raporla.
2. Hedef resmi uygulama, dalı ve tam commit'i: Press'teki candidate release hash'i (`press_read` ile `deploy_candidate.get`)
   ya da yerel bench'teki commit. Branch ucu
   kanıt değildir.
3. Hedef Frappe sürümü. Bilinmiyorsa sürüme bağlı karar `unknown`dır ve öneri açılmaz.
4. Genişletme uygulaması mevcut (yoksa önce frappe-custom-app ile `new_app`); `required_apps` resmi uygulamayı içerir.
5. İstek somut: hangi DocType, hangi olay ya da metot, hangi davranış.

## Karar sırası

| Sıra | Mekanizma | Ne için | v15 | v16 | Başlıca risk |
| --- | --- | --- | --- | --- | --- |
| 1 | Custom Field, Property Setter (filtreli fixture) | Alan, etiket, zorunluluk, görünürlük | var | var | Her migrate'te siteyi ezer; filtresiz dışa aktarma başka app'lerin kayıtlarını alır |
| 2 | `doc_events` | Olaya yan etki (validate, on_submit, on_cancel, on_update, after_insert, on_trash) | var | var | İşleyici imzası `doc, method`; commit yok; app'ler arası sıra |
| 3 | `extend_doctype_class` | Sınıfa metot veya özellik eklemek, `super()` ile sarmak | yok | var | Mixin zinciri; `super()` kırılırsa diğer uzantılar düşer |
| 4 | `override_doctype_class` | Sınıfın davranışını değiştirmek | var | var | Son kurulan app kazanır; v16'da sınıf asıl sınıfın alt sınıfı olmak zorunda; `super()` çağrılır |
| 5 | `override_whitelisted_methods` | Bir API metodunu değiştirmek | var | var | İmza ve dönüş sözleşmesi korunur; son app kazanır; her yükseltmede yeniden test |
| 6 | Çekirdek yama, fork | İstisna | core akışı | core akışı | Yükseltmede çakışma ve bakım yükü; yalnız kullanıcının açık tekrarı ve CORE onayıyla; fork ajan işi değil |

v15 hedefinde `extend_doctype_class` önerilmez. Kural: önce 1 ve 2 yeterli mi diye bak; sınıf mekanizması yalnız davranış
olayla ifade edilemiyorsa.

## Sıra

1. Resmi uygulamanın ilgili kodunu sabit commit'te oku: DocType denetleyicisi, değiştirilecek metot ve imzası, resmi
   uygulamanın kendi hooks girdileri. `app_inspect` resmi app kodunu okur; yazma genişletme uygulamasına yapılır,
   resmi dosyaya yazma core akışına girer.
2. Çakışma taraması: kurulu diğer uygulamaların aynı DocType veya metot için `override_doctype_class`,
   `override_whitelisted_methods`, `doc_events` ve fixture girdileri. Aynı sınıfı iki app override ediyorsa biri sessizce
   kaybolur; bunu raporla ve dur.
3. En dar mekanizmayı seç; neden üsttekine gerek olmadığını yaz.
4. `app_check {app_path, target_frappe}` genişletme uygulamasında.
5. `app_propose_change`: önce iskelet (`add_fixture_filter`, `add_doc_event` ya da `extend_doctype_class`, `mode: extend`
   veya `override`), sonra asıl kod (`write_file`, tek dosya). Tek öneride tek değişiklik. Diff ve sha256'yı göster; dur.
   İnsan onayı ayrı terminalde:

   ```sh
   python3 -I packages/press-ai/server.py approve <öneri-kimliği> --config <yapılandırma-yolu>
   ```

6. `proposal_get` `approved` ise `app_apply` bir kez; sonra `app_check` yeniden.
7. Test: genişletmenin kendi test içeriği `write_file` ile; resmi uygulamanın ilgili DocType testleri de koşulur. Komutları
   insan çalıştırır; çıktı yoksa `not_run`, "geçti" denmez.
8. Press: genişletme uygulaması grupta resmi uygulamadan sonra gelir; dağıtım press-operations sırasıyla.

## Yapılmaz

- Core akışı dışında resmi uygulama dosyasına yazmak. İlk istek `core_warning` döner; uyarıyı göster ve dur. Yalnız kullanıcı
  aynı değişikliği açıkça yeniden isterse aynı argümanlarla bir kez daha çağır; onay `CORE <uygulama>` ister.
- Varsayılan olarak fork. Fork yalnız kullanıcının açık kararıyla, sorumlusu, yukarı akışa dönüş planı ve bakım maliyeti
  yazılarak yapılır; ajan fork açmaz.
- İçe aktarma anında monkey patch (EXT001 uyarısı: engellenmez ama önerilmez; hooks, override ya da extend tercih edilir); Server Script ya da Client Script ile uygulama mantığı; Customize Form'da yapılıp dışa
  aktarılmayan değişikliği kod saymak.
- İzin kancalarıyla yetki genişletmek; `ignore_permissions` ile denetimi aşmak; işleyicide commit.

## Başvurular

- Mekanizma ayrıntıları, çakışma ve yükseltme denetimi: [references/extension-points.md](references/extension-points.md)
- Frappe modeli: [frappe-app-model.md](../../references/frappe-app-model.md)
- Senaryolar: [scenarios.md](../../references/scenarios.md) (SC-16 … SC-18)
