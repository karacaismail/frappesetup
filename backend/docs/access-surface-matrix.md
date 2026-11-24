# Veri yüzeyi yetki matrisi (G-121)

Bu belge 24 Kasım 2026 Salı günü yazıldı. Belgeyi AJA-530 işi yazdı.

## Amaç

Her veri yüzeyi aynı yetki kararını vermelidir. Örneğin çalışan listede kendi kaydını görür. Aynı çalışan raporda, aramada ve dosyada da yalnız kendi kaydını görür.

Kararı üç katman verir:

1. Rol izni (“DocPerm”) işlemi açar. Bu katman Frappe'nindir.
2. Erişim kuralı (“Access Rule”) kayıtları daraltır. Bu katman erişim motorunundur.
3. İzin seviyesi (`permlevel`) alanı kapatır. Örneğin maaş alanı yalnız İK rolüne açılır.

Ayrıntılı karar notu `docs/decisions/0006-access-rule.md` dosyasındadır.

## Testler nasıl çalışır?

Testler gerçek HTTP isteği yollar. İstek Frappe'nin uygulamasından geçer. Arayüz kullanılmaz.

Testlerde altı kayıt vardır. Her kullanıcının görmesi gereken kayıtlar `access/tests/base.py` içindeki `EXPECTED_VISIBLE` tablosundadır. Her yüzey bu tabloyla karşılaştırılır.

Testleri şu komut çalıştırır:

```
PANE_PORT=<port> backend/dev/bin/test platform_core --module <modül>
```

## Matris

Aşağıdaki tabloda her satır bir yüzeydir. “Kural” sütunu kayıt kararının nereden geldiğini söyler. “Alan” sütunu izin seviyesinin nasıl uygulandığını söyler.

| Yüzey | Frappe yolu | Kural | Alan | Test |
| --- | --- | --- | --- | --- |
| Liste | `/api/v2/document/<tür>` ve `frappe.get_list` | Liste kancası (`permission_query_conditions`) | Frappe alanı yanıttan çıkarır. Süzgeçte kullanılamaz. | `test_surfaces.py`, `test_field_level.py` |
| Tek kayıt | `/api/v2/document/<tür>/<ad>` | Kayıt kancası (`has_permission`) | Frappe alanı yanıttan çıkarır. Yazılamaz. | `test_record_rule.py`, `test_field_level.py` |
| Masaüstü form | `frappe.desk.form.load.getdoc` | Kayıt kancası | Alan dönmez. | `test_surface_matrix.py` |
| Tek değer | `frappe.client.get_value` | Liste kancası | Alan dönmez. | `test_surface_matrix.py` |
| Liste raporu ve sayım | `frappe.desk.reportview.get` ve `get_count` | Liste kancası | Alan dönmez. İK rolü alanı görür. | `test_surfaces.py`, `test_surface_matrix.py` |
| Liste dışa aktarma | `frappe.desk.reportview.export_query` | Liste kancası | Alan dosyaya girmez. | `test_surfaces.py`, `test_surface_matrix.py` |
| Veri içe aktarma ekranından dışa aktarma | `frappe.core.doctype.data_import.data_import.download_template` | Liste kancası (`frappe.get_list`) | Alan dosyaya girmez. | `test_surface_matrix.py` |
| Sorgu raporu ve betik raporu | `frappe.desk.query_report.run` ve `export_query` | Rapor kapısı. Kural varken yalnız “System Manager” çalıştırır. | Kapı raporu baştan kapatır. | `test_reports.py`, `test_report_rules.py` |
| Hazır rapor (“Prepared Report”) | Kayıt, uç ve arka plan işi | Kural varken kapalıdır. İş başlamadan reddedilir. | Kapı raporu baştan kapatır. | `test_report_rules.py`, `test_review.py` |
| Otomatik e-posta raporu | “Auto Email Report” ve zamanlayıcı | Kural varken kapalıdır. | Kapı raporu baştan kapatır. | `test_auto_email_report.py` |
| Bağlantı araması | `frappe.desk.search.search_link` ve `search_widget` | Motorun sarmalayıcısı ve liste kancası. Özel arama işlevi reddedilir. | Frappe alanı aramadan çıkarır. | `test_link_search.py`, `test_surfaces.py` |
| Bağlantı doğrulama | `frappe.client.validate_link_and_fetch` | Motorun sarmalayıcısı | Frappe alanı okuma izniyle getirir. | `test_link_search.py` |
| Genel arama | `frappe.utils.global_search.search` | Frappe her sonuç için kayıt kancasını çağırır. | Bkz. “Açık kalanlar”. | `test_surface_matrix.py` |
| Yazdırma | `frappe.www.printview.get_html_and_style`, `/printview` ve `download_pdf` | Kayıt kancası (`validate_print_permission`) | Frappe alanı çıktıdan çıkarır. İK rolü alanı görür. | `test_surfaces.py`, `test_surface_matrix.py` |
| Dosya kaydı ve indirme | `/api/v2/document/File/<ad>` ve `/private/files/<dosya>` | Frappe dosyanın bağlı olduğu kaydın kararını sorar. | Dosya içeriği alan düzeyine bölünmez. | `test_surface_matrix.py` |
| Dosya listesi | `/api/v2/document/File` | Motor, bağlı kaydın liste koşulunu ekler (`access/files.py`). | Yok | `test_surface_matrix.py` |
| Anlık olay: kayıt odası | `frappe.realtime.has_permission`, kayıt adıyla | Kayıt kancası | Olay yalnız kaydın adını ve zamanını taşır. | `test_realtime.py`, `test_surface_matrix.py` |
| Anlık olay: liste odası | `frappe.realtime.has_permission`, kayıt adı olmadan | Motorun sarmalayıcısı (`access/realtime.py`). Kural kullanıcıyı daraltıyorsa oda kapanır. | Olay alan değeri taşımaz. | `test_realtime.py`, `test_surface_matrix.py` |
| Motorun kendi uçları | `platform_core.api.access.*` | Her uç kendi iznini denetler. | Alan uçları yalnız yöneticiye açıktır. | `test_entry_matrix.py`, `test_endpoints.py` |
| Yapay zekâ araçları (MCP) | `platform_core.api.ai.mcp`, `plt_list_documents` ve `plt_get_document` | Araç kullanıcının kimliğiyle `frappe.get_list` ve `check_permission` çağırır. | Liste aracı alanı reddeder. Kayıt aracı alanı çıkarır. | `test_surface_matrix.py`, `ai/tests/test_read.py` |
| Motorun yapay zekâ araçları | `ai_tools` kancası | Her araç kendi iznini denetler. | Yok | `test_ai_tools.py` |
| Arka plan işleri | Hazır rapor ve dışa aktarma işleri | İş çalışırken karar yeniden verilir. | Kapı raporu baştan kapatır. | `test_report_rules.py` |
| Paylaşılmış kayıt | “DocShare” | Paylaşım kuralı bilerek aşar. Liste ve kayıt aynı sonucu verir. | Paylaşım alan seviyesini açmaz. | `test_sharing.py` |

## `get_all` ve ham SQL

`frappe.get_list` izin uygular. `frappe.get_all` izin uygulamaz. Ham SQL de izin uygulamaz.

Motorun kodunda bu kurala bir test bakar: `test_static_files.py` içindeki `test_every_unchecked_read_or_write_says_why`. İzin uygulamayan her çağrının hemen üstünde gerekçe yorumu olmalıdır. Yorum yoksa test düşer.

Bütün kullanıcı kodu için Semgrep kuralları vardır. Kurallar `dev/security/fixtures/rules.yaml` dosyasındadır. Örneğin `frappe-built-sql` kuralı metinden kurulan SQL'i reddeder. `frappe-ignore-permissions` kuralı izni atlayan seçeneği reddeder.

Bu kurallar `get_all` çağrısını motor dışında aramaz. Bu eksik “Açık kalanlar” bölümündedir.

## Bu işte bulunan iki açık

1. **Liste odası.** Frappe her kayıt değişince “list_update” olayını yollar. Olay kaydın adını ve değiştiren kişiyi taşır. Önce kural daralttığı kullanıcı da bu odaya giriyordu. Artık oda bu kullanıcıya kapalıdır. Kullanıcının listesi kendiliğinden yenilenmez. Kullanıcı listeyi elle yenileyince doğru kayıtları görür.
2. **Dosya listesi.** Çalışan dosya listesinde kural dışı kayıtların eklerini görüyordu. Dosya adı ve kaydın adı sızıyordu. Dosyanın içeriği sızmıyordu. Artık motor dosya listesine kural koşulunu ekler.

## Açık kalanlar

Aşağıdaki maddeler bu işte kapanmadı. Her madde ayrı iş ister.

1. **Genel arama içeriği.** Frappe genel aramada kayıt kararını uygular. Ancak sonuçta aranan metnin özeti de döner. Bir alan hem izin seviyesindeyse hem genel aramaya açıksa değeri özette görünebilir. Bugün test türünde böyle bir alan yoktur. Kiracı yöneticisi izin seviyesindeki alanı genel aramaya açmamalıdır.
2. **Açık dosya.** Frappe açık dosyayı (`is_private` kapalı) herkese açar. Bu Frappe'nin bilinen davranışıdır. Kural, açık dosyayı kapatmaz.
3. **`get_all` tarayıcısı.** Motor dışındaki uygulama kodunda `get_all` çağrısını arayan kural yoktur.
4. **CI kaydı.** Testler yerel yığında koştu. CI koşu kaydı birleştirmeden sonra eklenmelidir.
5. **Gerçek tarayıcıda anlık olay.** Testler odaya giriş kararını sınar. Gerçek soket bağlantısı sınanmadı.
