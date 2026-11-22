# İş: platform-core-gecit

Bu iş model geçidini ve sağlayıcı kaydını kurar. Proje sahibinin kararı şudur: Sisteme n tane sağlayıcı, her sağlayıcıdan n tane hesap ve her hesaptan n tane API eklenebilir. Altyapı sağlayıcıdan bağımsızdır (D-9, D-11).

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJE-KAYDI.md`, özellikle D-9, D-11, O-13, O-14 ve O-15
3. `backend/docs/sozlesmeler.md`, özellikle 10 ve 11. bölümler
4. Karar sitesinde `src/content/docs/rail-5-ai.md`. G-90 ve G-92 kurallarını bulun.

## Sahip olduğunuz yerler

- `backend/apps/platform_core/platform_core/model_gecidi/`
- `backend/apps/platform_core/platform_core/api/model.py`
- `backend/contracts/platform_core-model-gecidi.openapi.yaml`
- `backend/docs/kararlar/0004-model-gecidi.md`
- `hooks.py` içinde yalnız bu işin satırları

## Kontrol noktası 1: bağdaştırıcılar ve yönlendirme

Bu bölüm Frappe istemez. Kodu saf Python olarak yazın.

1. Karar notunu yazın. Notta şunlar olsun:
   - ortak çağrının ve ortak yanıtın biçimi,
   - her bağdaştırıcının çevirdiği alanlar,
   - araç çağrısının sağlayıcılar arasında nasıl eşlendiği,
   - akışlı yanıtın sonraki tura kaldığı.
2. Her sağlayıcının güncel API biçimini resmî belgesinden doğrulayın. Belleğe güvenmeyin.
3. Bağdaştırıcıları sözleşmenin 11. bölümüne göre yazın. HTTP için Frappe'nin içindeki `requests` paketini kullanın. Sağlayıcı kitaplığı eklemeyin.
4. Yönlendirmeyi saf işlev olarak yazın. İşlev adayları sıralar ve sıradakine geçme kararını verir.
5. Testleri önce yazın. Testler sahte bir HTTP sunucusu kullansın. Testler şunları göstersin:
   - her bağdaştırıcı aynı ortak yanıtı üretir,
   - 429 ve 5xx sonrası sıradaki adaya geçilir,
   - kimlik hatası API'yi kapalı sayar,
   - dinlenme süresi dolan aday geri döner,
   - bütçesi dolan hesap seçilmez,
   - anahtar hiçbir hata metninde ve kayıtta görünmez.
6. Kodda model adı yazmayın. Testlerde sahte model adı kullanın.
7. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: DocType'lar ve uçlar

Bu bölüm `platform_core` iskeletini ister. Orkestratör iskeleti `backend` dalına birleştirince haber verir. Sonra `backend` dalını kendi dalınıza alın.

1. Önce OpenAPI sözleşmesini yazın.
2. Sözleşmedeki altı DocType'ı yazın. Her alana açıklama verin.
3. “AI Manager” rolünü ekleyin. İzinleri sözleşmeye göre verin.
4. Gizli anahtarı “Password” alanında tutun. Anahtarı yalnız geçit okusun.
5. `model.complete` ve `model.test_api` uçlarını yazın.
6. Her çağrıyı “AI Usage Log” kaydına yazın. Mesaj içeriğini yazmayın.
7. Testler HTTP isteğiyle şunları göstersin:
   - yetkisiz kullanıcı kaydı göremez,
   - anahtar REST yanıtında ve DocType okumasında dönmez,
   - iki hesap ve iki API arasında yedeğe geçiş çalışır,
   - bir kiracı birden çok sağlayıcı ekleyebilir.
8. Commit atın ve `done` raporlayın.

## Kapsam dışı

- MCP araçları platform-core-yz işinindir. Bu işin DocType'ları o katmandan kendiliğinden görünür olacak.
- Ajan servisi ve sohbet ekranı Rail 5 işidir.
- Gerçek sağlayıcıya istek atmayın. Gerçek anahtar kullanmayın.
- Platformun ortak hesapları sonraki turdadır (O-14).
