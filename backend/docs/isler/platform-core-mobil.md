# İş: platform-core-mobil

Bu iş telefon uygulamasının sunucu tarafını kurar. Telefon uygulaması internet yokken de çalışır. Bağlantı gelince sunucuyla eşitlenir. Bu işin kuralları hazırdır. Kurallar `docs/standartlar/mobile.md` dosyasının 13. bölümündedir (AU-1 ile AU-19).

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJE-KAYDI.md`
3. `backend/docs/sozlesmeler.md`
4. `docs/standartlar/mobile.md`. Özellikle 7. bölüm (eşitleme) ve 13. bölüm (sunucu önlemleri) önemlidir. Ek B'deki Frappe davranışlarını da okuyun.

## Sahip olduğunuz yerler

- `backend/apps/platform_core/platform_core/mobil/`
- `backend/apps/platform_core/platform_core/api/mobile.py`
- `backend/contracts/platform_core-mobil.openapi.yaml`
- `backend/docs/kararlar/0007-mobil-esitleme.md`
- `modules.txt` dosyasında yalnız `Mobil` satırı
- `hooks.py` içinde yalnız bu işin satırları

## Bağlı işler

- Belirteç doğrulamasını platform-core-kimlik işi kurar. Bu iş onun `auth_hooks` bağdaştırıcısını kullanır. Kendi doğrulamanızı yazmayın.
- Kayıt yetkisi Frappe izinleri ve erişim kuralı motoruyla gelir. Kendi yetki kuralınızı yazmayın.

## Kontrol noktası 1: tasarım ve sözleşme

Bu bölüm Frappe kurulumu istemez. Frappe davranışını `frappe/erpnext:v16.55.0` imajının kaynağında okuyun.

1. Tasarım notunu yazın. Notta şu sorular cevaplansın:
   - Sürümlü mobil uçlar nasıl adlanır (AU-1)?
   - İzinli eşitleme komutları nasıl tanımlanır (AU-2)?
   - İşlem kimliği nasıl tekil tutulur? Aynı kimlik yeniden gelince ilk sonuç nasıl döner (AU-7)?
   - Güncelleme ve silmede sürüm nasıl karşılaştırılır (AU-8)?
   - Telefonun verdiği UUID nasıl doğrulanır (AU-9)?
   - İmleç geç kesinleşen değişikliği nasıl atlamaz (AU-10)?
   - Silme ve yetki kaybı nasıl bildirilir (AU-11)?
   - Sayfa, grup ve dosya sınırları nedir (AU-14)?
   - Sözleşme sürümü nasıl korunur (AU-15, AU-16)?
2. Önce OpenAPI sözleşmesini yazın. Her uca açıklama verin (D-9).
3. Önce testleri ve Frappe'ye bağlı olmayan mantığı yazın.
4. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: uçlar

Bu bölüm `platform_core` iskeletini ister. Orkestratör iskeleti `backend` dalına birleştirince haber verir.

1. DocType'ları yazın. Örneğin işlem kaydı, değişiklik kaydı, kaldırma işareti ve cihaz kaydı gerekir. Her alana açıklama verin.
2. Uçları yazın. Uçlar yalnız mobil adreslerde belirteç kabul etsin (AU-5).
3. Testler gerçek HTTP isteğiyle şunları göstersin:
   - aynı işlem kimliği iki kez gelince sonuç değişmez,
   - aynı kimlikle farklı içerik reddedilir,
   - eski sürümle güncelleme çakışma döner,
   - eşzamanlı yazma imleçte değişiklik kaybettirmez,
   - silinen ve yetkisi kalkan kayıt kaldırma işaretiyle gelir,
   - sınır aşılınca 429 ya da 413 döner,
   - eski sözleşme sürümü çalışmaya devam eder.
4. Kaldırma işaretlerinin temizliği elle başlatılan komut olur. Zamanlanmış iş kurmayın (D-6). Komutun HTTP ucu da olsun.
5. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Telefon uygulaması, PWA ve Capacitor paketi bu turda yazılmaz.
- Telefon bildirimi (AU-17) sonraki turdadır.
- Giriş ve belirteç doğrulaması platform-core-kimlik işinindir.
