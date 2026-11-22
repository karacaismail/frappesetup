# İş: erisim-kurali

Bu iş `platform_core` içinde erişim kuralı motorunu kurar. Karar sitesinin K8 kararı şudur: SaaS müşterisi kendi yetki modelini yönetebilmeli. Frappe'nin rol yetkisi tek başına yetmez. Motor kayıt kuralını, hiyerarşiyi ve alan düzeyini kapsar.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJECT-RECORD.md`
3. `backend/docs/contracts.md`
4. Karar sitesinde `kararlar.md` (K8), `rail-2-gelistirme.md`, `rail-2-yapilandirma.md` ve `yol-haritasi.md`. G-60, G-61, G-62, G-104 ve G-121 maddelerini bulun.
5. `docs/standartlar/frappe-python-standartlari.md`, özellikle G-2, G-3 ve G-12

## Sahip olduğunuz yerler

- `backend/apps/platform_core/platform_core/access/`
- `backend/apps/platform_core/platform_core/api/access.py`
- `backend/contracts/platform_core-access.openapi.yaml`
- `backend/docs/decisions/0006-access-rule.md`
- `modules.txt` dosyasında yalnız `Access` satırı
- `hooks.py` içinde yalnız bu işin satırları

## Kontrol noktası 1: tasarım notu

Bu bölüm Frappe kurulumu istemez. Frappe davranışını kaynakta okuyun.

1. Tasarım notunu yazın. Notta şu sorular cevaplansın:
   - “Access Rule” kaydı hangi alanları taşır?
   - Kural listeye `permission_query_conditions` kancasıyla nasıl girer?
   - Kural tek kayda `has_permission` kancasıyla nasıl girer?
   - Hiyerarşi nasıl çalışır? Örneğin yönetici, `reports_to` zincirindeki ekibini görür.
   - Alan düzeyi nasıl çalışır? Örneğin maaş alanı izin seviyesiyle kapanır.
   - Liste, kayıt, rapor ve dışa aktarma aynı sonucu nasıl verir (G-121)?
   - Paylaşılmış kayıt kuralı nasıl etkiler (G-12)?
   - Yapay zekâ katmanı aynı sonucu nasıl alır (G-85)?
2. Frappe 16'nın kanca davranışını kaynakta doğrulayın. Örneğin `has_permission` kancası `None` dönerse ne olur? Dosya ve satır yazın.
3. Önce sözleşmeyi ve testleri yazın. Testler kısıtlı kullanıcıyla ret durumunu da sınasın.
4. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: motor

Bu bölüm `platform_core` iskeletini ister. Orkestratör iskeleti `backend` dalına birleştirince haber verir.

1. “Access Rule” DocType'ını ve motoru yazın. Her alana açıklama verin (D-9).
2. Motoru Frappe'nin kancalarına bağlayın. Frappe'nin kodunu değiştirmeyin (M-4).
3. Testler gerçek HTTP isteğiyle şunları göstersin:
   - çalışan yalnız kendi kayıtlarını görür,
   - yönetici ekibinin kayıtlarını görür,
   - kısıtlı alan dönmez,
   - liste, kayıt ve rapor aynı sonucu verir,
   - kural değişince sonuç hemen değişir.
4. Sorgu sayısını ölçün. Kural yüzünden her kayıt için ayrı sorgu açılmasın (P-1).
5. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Uygulamaya özel kural şablonları, örneğin CronHR, sonraki turdadır.
- Ekran yoktur. Kurallar API ve yapay zekâ araçlarıyla yönetilir.
