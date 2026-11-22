# İş: naming-history-fix

Bu iş var olan adları adlandırma kurallarına göre düzeltir. Kurallar ayrı bir oturumun raporundadır. Rapor `naming_rules_report.md` dosyasıdır. Rapor depoda değildir. Asıl kopya proje sahibinin `rules ai` klasöründedir. Raporu orkestratörden isteyin. Proje sahibi bu işi şöyle istedi: “oluşturunca, onu da paralel ayrı bir pane görevi ile başlatıp, geçmişi düzelttirirsin.”

Önce şu dosyaları okuyun:

1. `naming_rules_report.md` raporu. Raporun son hâlini orkestratörden isteyin ve okuyun. Rapor sonradan güncellenebilir.
2. `backend/AGENTS.md`, özellikle “Ad dili” bölümü
3. `backend/PROJECT-RECORD.md`, özellikle D-12
4. `backend/docs/contracts.md`

## Raporda önce okunacak yerler

- 1. bölüm: proje sahibinin kararı ve AV-1, AV-2, AV-3.
- 10. bölüm: Frappe kuralları, özellikle AV-57..AV-69.
- 12. bölüm: önerilen adlar ve geçiş sırası.
- AV-12: Önce her uygulamanın terim sözlüğünü yazın: `docs/glossary.yaml`. Tablodaki adlar yalnız öneridir. Kesin adı sözlük belirler.
- AV-19: Adın bütün biçimlerini arayın: snake, Pascal, kebab, “Title Case” ve `tabXxx`. Veritabanında saklanan değerleri de arayın: Client Script, Server Script, rapor sorgusu, Custom Field `dt` ve `options`, Property Setter ve Dynamic Link.
- AV-26: Dışarıya açık adlarda önce iki adı birlikte okuyun, sonra eskisini kaldırın. Bu projede henüz yayımlanmış bir uç yoktur. Bu yüzden bileşenler arası adlar tek seferde değişebilir. Kararı karar notuna yazın.
- AV-61 ve AV-63: Select seçenekleri ve iş akışı durumları da İngilizce olur. Custom Field `fieldname` değeri `custom_<ön ek küçük harf>_` ile başlar ve elle yazılır.
- AV-67: Yama dosyası adı kuralına uyun. Frappe çalışmış yamayı `patches.txt` satır metniyle tanır. Satır değişirse yama yeniden çalışır.

## Orkestratörün kararları (D-14)

- Ön ekler: `platform_core` için `PLT`, `press_tr` için `PTR`, `hrms_tr` için `HRT`. Örnek: “AI Provider” adı “PLT AI Provider” olur.
- Modül önerileri: `kimlik` → `identity`, `kabuk` → `shell`, `yapay_zeka` → `ai`, `model_gecidi` → `model_gateway`, `erisim` → `access`, `mobil` → `mobile`. Kesin adı sözlük belirler.
- Keycloak rol adları küçük harf ve tireyle yazılır.
- Yasaklı ürün adı (D-13) hiçbir yerde geçmez. Eşleşme tablosunda da geçmez.

## Frappe 16.56.0 kaynağında doğrulanmış uyarılar

1. DocType adı için `frappe.rename_doc("DocType", old, new)` kullanın. `rename_doc.py` içindeki `rename_doctype` yardımcısını doğrudan çağırmayın. O yardımcı yalnız bağlantıları günceller.
2. `rename_field` sütunun adını değiştirmez. Veriyi yeni sütuna kopyalar. Önce yeni alanı ekleyin ve `frappe.reload_doc` ile yükleyin. Yeni alan yoksa işlev sessizce döner. Taşınan satırları sayarak doğrulayın.
3. MariaDB `utf8mb4_unicode_ci` harf ve aksan ayırmaz. “Sube” ile “Şube” aynı sayılır. “ı” ile “i” farklı sayılır.
4. Frappe 16 DocType adında Türkçe harfi reddeder (`doctype.py:44`, `re.ASCII`).

## Betik eş güçlü olmalı

Betik iki kez çalışınca zarar vermemeli. Ön ek eklemek buna dikkat ister. Örneğin “AI Provider” → “PLT AI Provider” değişikliği ikinci çalışmada “PLT PLT AI Provider” üretmemeli. Bunu testle gösterin.

## Neden betikle yapılıyor?

Aynı anda on bir işçi kendi dalında çalışıyor. Adlar yalnız `backend` dalında değişirse öteki dallar çakışır. Bu yüzden ad değişikliğini bir betik yapar. Her işçi aynı betiği kendi dalında çalıştırır. Böylece her dalda aynı sonuç çıkar.

## Sahip olduğunuz yerler

- `backend/dev/naming/` (yeni klasör)
- `backend/docs/decisions/` altında yeni karar notu: `0009-naming-history-fix.md`
- Ad değişikliğinin `backend` dalındaki uygulaması

## Kontrol noktası 1: eşleşme dosyası ve betik

1. Raporu okuyun. Var olan adları rapordaki kurallarla karşılaştırın.
2. Kapsam şunlardır:
   - `backend/` altındaki dosya ve klasör adları,
   - Frappe modül adları (`modules.txt`) ve modül klasörleri,
   - DocType, işlev, değişken ve ayar adları,
   - koddaki Türkçe yorumlar, hata iletileri ve günlük metinleri,
   - compose servis adları, site adları ve Keycloak istemci adları.
3. Kapsam dışı olanlar şunlardır:
   - `docs/standartlar/` klasörü. Bu belgeler proje sahibinindir.
   - Belgelerin Türkçe içeriği. Yalnız belge dosyalarının adı rapora göre değişir.
   - Kullanıcıya görünen Türkçe çeviri dosyaları.
   - Pane ve dal adları.
4. Eşleşmeyi `backend/dev/naming/rename-map.json` dosyasına yazın. Her satır eski adı, yeni adı ve türünü taşır. Tür örnekleri: yol, modül, tanımlayıcı, ayar.
5. Eşleşmeyi uygulayan betiği yazın: `backend/dev/naming/apply_renames.py`. Betik şunları yapar:
   - dosya ve klasörleri `git mv` ile taşır,
   - metin içindeki atıfları değiştirir,
   - iki kez çalışınca zarar vermez,
   - `--dry-run` seçeneğiyle yalnız ne yapacağını listeler,
   - eşleşmede olmayan bir adı değiştirmez.
6. Betiğin testlerini yazın. Testler geçici bir git deposunda çalışsın.
7. Koddaki Türkçe yorum ve iletilerin İngilizce karşılığını eşleşmeye koymayın. Onları bu iş kendi dalında elle çevirir. Öteki işçiler kendi dosyalarındakini çevirir.
8. Commit atın ve `ready` raporlayın. Raporda eşleşme tablosunun özetini verin.
9. Betiği `--dry-run` ile öteki işlerin dallarında salt okunur çalıştırın. Dalların çalışma ağaçlarını `git worktree list` komutu gösterir. Başka dalda dosya değiştirmeyin. Her dal için değişecek dosya sayısını ve çakışma riskini durum dosyasına yazın.

## Kontrol noktası 2: backend dalında uygulama

Bu kontrol noktası bir istisnadır. Orkestratör “başla” deyince yapılır. Nedeni şudur: birçok dal incelemede. Önce incelemesi geçen dallar birleşir. Beklerken kontrol noktası 1'in 9. adımını yapın.

1. Betiği kendi dalınızda `backend` dalının son hâline uygulayın.
2. Frappe modül adı değişince var olan geliştirme sitesi bozulabilir. Geliştirme sitesinde gerçek veri yoktur. Siteyi yeniden kurmak yeterlidir. Yöntemi README'ye yazın.
3. Bütün testleri yeniden çalıştırın: modül sınırı denetimi, güvenlik kapısı ve `platform_core` testleri.
4. Commit atın ve `ready` raporlayın.
5. Orkestratör dalınızı birleştirir. Sonra öteki işçilere betiği kendi dallarında çalıştırmalarını söyler.

## Kontrol noktası 3: kod içindeki Türkçe metin

1. `backend` dalında, birleşmiş koddaki Türkçe yorumları, hata iletilerini ve günlük metinlerini İngilizceye çevirin.
2. Kullanıcıya görünen metnin kaynağını İngilizce yapın. Türkçesini çeviri dosyasına koyun.
3. Testleri yeniden çalıştırın. Commit atın ve `done` raporlayın.

## Sınırlar

- Proje sahibine soru sormayın (D-10).
- Rapor bir konuda kesin değilse en yalın ve en tutarlı seçeneği seçin. Kararı karar notuna yazın.
- Başka işin dalında değişiklik yapmayın. Onlar betiği kendileri çalıştırır.
