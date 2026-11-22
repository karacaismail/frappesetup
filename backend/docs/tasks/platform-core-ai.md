# İş: platform-core-yz

Bu iş `platform_core` içinde yapay zekâ erişim katmanını kurar. Proje sahibinin kararı şudur: Her DocType, her alan ve her backend işlemi yapay zekâyla yönetilebilir olacak. Katman model sağlayıcısından bağımsız olacak (Proje kaydı D-9).

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJECT-RECORD.md`
3. `backend/docs/contracts.md`, özellikle 10. bölüm
4. Karar sitesinde `src/content/docs/rail-5-ai.md` ve `ai-*.md` sayfaları
5. Depodaki `packages/press-ai/INTERFACE.md` dosyası. Onay ve “unknown” kuralları orada uygulanmıştır.

## Sahip olduğunuz yerler

- `backend/apps/platform_core/platform_core/ai/`
- `backend/apps/platform_core/platform_core/api/ai.py`
- `backend/contracts/platform_core-ai.openapi.yaml`
- `backend/docs/decisions/0002-ai-layer.md`
- `hooks.py` içinde yalnız bu işin satırları

## Kontrol noktası 1: karar notu

1. Önce hazır yolu arayın (T-1). Karar sitesi `frappe_mcp` adını anar (G-84). Şunları inceleyin:
   - Frappe 16'nın içinde MCP desteği var mı?
   - `frappe/mcp` deposu ne sunuyor? Lisansı ne? Son sürümü ve bakımı nasıl?
   - Bu depo Frappe 16 ile çalışıyor mu?
2. MCP'nin güncel sürümünü ve HTTP taşıma biçimini resmî kaynaktan doğrulayın.
3. Karar notunu `backend/docs/decisions/0002-ai-layer.md` dosyasına yazın. Notta şu tasarımlar olsun:
   - Araçlar DocType tanımından nasıl üretilir?
   - Kimlik nasıl taşınır? İnsan oturumu ve aracı belirteci ayrı ele alınır (G-148).
   - Yetki eşitliği nasıl sağlanır (G-85)?
   - Önizleme ve onay nasıl çalışır (G-86)?
   - “AI Action Log” kaydı hangi alanları tutar (G-64)?
   - Gizli alanlar nasıl dışarıda kalır?
4. Yeni paket gerekiyorsa T-2 bölümünü yazın. Açık kaynak lisanslı paketi gerekçesiyle seçin (D-10). AGPL lisanslı bileşeni `platform_core` içine almayın (O-12). Soru sormayın.

## Kontrol noktası 2: çekirdek katman

Bu bölüm `platform_core` iskeletini ister. Orkestratör iskeleti `backend` dalına birleştirince haber verir. Sonra `backend` dalını kendi dalınıza alın.

1. Önce OpenAPI sözleşmesini ve araç şemasını yazın.
2. Önce testleri yazın. Testler şunları göstersin:
   - Kısıtlı kullanıcı başkasının kaydını yapay zekâ yoluyla da okuyamaz.
   - İzin seviyesi yüksek alan dönmez.
   - “Password” türündeki alan hiç dönmez.
   - Onaysız yazma reddedilir.
   - Onay tek kullanımlıktır. İkinci kullanım reddedilir.
   - Süresi dolan onay reddedilir.
   - Kayıt önizlemeden sonra değiştiyse onay reddedilir.
   - Model belirteciyle gelen onay reddedilir. Onay yalnız insan oturumundan gelir.
   - İzin verilen ve reddedilen her çağrı “AI Action Log” kaydına düşer.
3. Genel araçları yazın: tanım, liste, kayıt, oluşturma, güncelleme, onaya gönderme, iptal, silme ve rapor.
4. Uygulamaların araç bildirdiği `ai_tools` kancasını yazın (G-105).
5. Kodda model sağlayıcısı kitaplığı olmadığını denetleyen bir test yazın.
6. Commit atın ve `ready` raporlayın.

## Kontrol noktası 3: yönetim araçları

1. Özel alan, alan ayarı, rol ve izin değişikliği için araç yazın.
2. Bu araçlar yalnız yönetici rolüne açılır. Her biri önizleme ve insan onayı ister.
3. Elle başlatılan komutların HTTP uçlarını araç olarak kaydedin.
4. Commit atın ve `done` raporlayın.

## Model geçidiyle ilişki

- Sağlayıcı, hesap ve API kaydını platform-core-gecit işi kurar. Kayıt `model_gateway` modülündedir.
- Bu kayıt da DocType olduğu için genel araçlardan görünür. Gizli anahtar hiçbir araçtan dönmez.
- Yapay zekâ kaydı yönetim araçlarıyla değiştirebilir. Her değişiklik önizleme ve insan onayı ister.
- Bu katman model çağırmaz. Model çağrısı gerekirse `model_gateway` modülünün açık işlevini kullanın.

## Kapsam dışı

- Ajan servisi, model seçimi ve sohbet ekranı Rail 5 işidir. Bu iş yalnız sunucu katmanını kurar.
- Press araçları press-tr işinindir. Press için `packages/press-ai` temel alınır.
- Gerçek bir model sağlayıcısına istek atmayın. Testler MCP istemcisini taklit eder.
