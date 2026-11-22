# İş: naming-history-fix

Bu iş var olan adları adlandırma kurallarına göre düzeltir. Kurallar ayrı bir oturumun raporundadır. Rapor `/Users/w6x/Documents/rules ai/naming_rules_report.md` dosyasıdır. Proje sahibi bu işi şöyle istedi: “oluşturunca, onu da paralel ayrı bir pane görevi ile başlatıp, geçmişi düzelttirirsin.”

Önce şu dosyaları okuyun:

1. `/Users/w6x/Documents/rules ai/naming_rules_report.md`. Dosyanın son hâlini okuyun. Rapor sonradan güncellenebilir.
2. `backend/AGENTS.md`, özellikle “Ad dili” bölümü
3. `backend/PROJE-KAYDI.md`, özellikle D-12
4. `backend/docs/sozlesmeler.md`

## Neden betikle yapılıyor?

Aynı anda on bir işçi kendi dalında çalışıyor. Adlar yalnız `backend` dalında değişirse öteki dallar çakışır. Bu yüzden ad değişikliğini bir betik yapar. Her işçi aynı betiği kendi dalında çalıştırır. Böylece her dalda aynı sonuç çıkar.

## Sahip olduğunuz yerler

- `backend/dev/naming/` (yeni klasör)
- `backend/docs/kararlar/` altında yeni karar notu: `0009-naming-history-fix.md`
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

## Kontrol noktası 2: backend dalında uygulama

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
