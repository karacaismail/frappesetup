# İş: ai-readiness-gate

Bu iş otomatik bir kapı yazar. Kapı, yapay zekâ kurallarının bütün backend kodunda tuttuğunu denetler. Proje sahibi her şeyin yapay zekâyla yönetilebilir olmasını istedi (D-9). Kural yazılı ama henüz otomatik denetlenmiyor. Bu iş o açığı kapatır.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`, özellikle “Yapay zekâ erişimi” ve “Ad dili” bölümleri
2. `backend/PROJECT-RECORD.md`, özellikle D-9 ve O-13
3. `backend/docs/contracts.md`, 10. ve 11. bölüm
4. `backend/dev/check_boundaries.py` ve `backend/dev/security/`. Yeni kapı bu iki denetimin biçimini izlesin.

## Sahip olduğunuz yerler

- `backend/dev/ai_readiness/` (yeni klasör)
- `backend/dev/bin/ai-readiness` (yeni komut)
- `backend/dev/bin/security-audit` içinde yalnız yeni kapıyı çağıran satır
- `backend/docs/decisions/0010-ai-readiness-gate.md` (yeni karar notu)

Yeni dosya, işlev ve değişken adları İngilizce olur (D-12). Yeni koddaki yorum ve iletiler de İngilizce olur.

## Kapının denetimleri

Kapı yalnız Python standart kitaplığıyla yazılır. Kapı `backend/apps/` altındaki bütün uygulamaları tarar.

1. **DocType açıklaması.** Her DocType JSON dosyasında `description` dolu olmalı. Her alanda da `description` dolu olmalı. Yerleşim alanları istisnadır. Örnekler “Section Break”, “Column Break” ve “Tab Break” alanlarıdır.
2. **Uç sözleşmesi.** `@frappe.whitelist` ile açılan her işlevin `backend/contracts/*.yaml` içinde bir işlemi olmalı. İşlemin `summary` ve `description` alanları dolu olmalı. Ters yön de denetlenir: sözleşmedeki her işlemin kodda bir işlevi olmalı.
3. **Sağlayıcı kitaplığı yok.** Kod sağlayıcı kitaplığı içe aktarmamalı. Örnekler `openai`, `anthropic`, `google.generativeai`, `mistralai`, `cohere`, `ollama` ve `langchain` kitaplıklarıdır.
4. **Kodda model adı yok.** Kodda bilinen model adı kalıbı geçmemeli. Model adları yalnız kayıtta durur (O-13). Test dosyalarındaki uydurma adlar bu kurala girmez.
5. **Zamanlanmış iş yok.** `hooks.py` içinde `scheduler_events` olmamalı. Proje sahibi `cron` istemedi.
6. **Ham SQL yolu yok.** Yapay zekâ araçlarında `frappe.db.sql` çağrısı olmamalı. Kapsam `ai` modülü ve `ai_tools` kancasıyla bildirilen araçlardır.
7. **Yasaklı ad yok (D-13).** Bu denetim `backend/` ile sınırlı değildir. Depodaki bütün izlenen dosyaları tarar (`git ls-files`). Dosya ve klasör adlarını da tarar.
   - Adın kendisi kapıya yazılmaz. Kapı yalnız şu SHA-256 özetini taşır: `17618b2344e07d3418e161912308ad63a118158bf4e3f1307329b5543b5fd743`.
   - Kapı metni küçük harfe çevirir. Sonra harf ve rakam dışındaki işaretleri siler. Böylece boşluk, alt çizgi, tire ve nokta ile yazılan biçimler de yakalanır.
   - Kapı kalan metinde 6 harflik her pencerenin özetini alır. Özet eşleşirse ihlal yazar.
   - Test, adı doğrudan yazmasın. Test adı karakter kodlarından ya da ters çevrilmiş bir metinden üretsin. Parçaları yan yana yazmayın. Kapı işaretleri sildiği için yan yana parçaları da yakalar.
   - Yanlış alarm çıkarsa durum dosyasına yazın. Orkestratör karar verir.

Her denetim ihlali dosya ve satırla yazar. Çıkış kodu ihlal varsa 1, yoksa 0 olur.

## Kontrol noktası 1: kapı ve testleri

1. Önce testleri yazın (D-2). Testler geçici bir klasörde sahte uygulama kurar. Her denetim için hem geçen hem kalan örnek olsun.
2. Testlerin beklenen nedenle başarısız olduğunu görün. Kanıtı durum dosyasına yazın.
3. Kapıyı yazın. `--json` seçeneği makine okunur çıktı versin. Böylece yapay zekâ da sonucu okuyabilir.
4. Kapıyı `backend` dalının son hâlinde çalıştırın. Sonucu durum dosyasına yazın.
5. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: öteki dallarda ölçüm

1. Kapıyı öteki işlerin dallarında salt okunur olarak çalıştırın. Dallar `~/Documents/frappesetup/worktrees/` altındadır.
2. Başka dalda dosya değiştirmeyin ve commit atmayın.
3. Her dal için ihlal sayısını ve ilk beş ihlali durum dosyasına yazın.
4. `security-audit` komutuna yeni kapıyı çağıran satırı ekleyin.
5. Commit atın ve `done` raporlayın. Orkestratör ihlalleri ilgili işçilere iletir.

## Sınırlar

- Proje sahibine soru sormayın (D-10).
- Bir denetim yanlış alarm veriyorsa kuralı daraltın. Kararı karar notuna yazın.
- Kapı yalnız okur. Hiçbir dosyayı kendiliğinden düzeltmez.
- Container gerekmez. Kapı Python ile çalışır.
