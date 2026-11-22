# Model geçidi

Geçit, uygulamanın model sağlayıcılarıyla konuştuğu ortak giriş noktasıdır.
Model adı ve bağlantı adresi site kaydından gelir.

## Ortak istek ve yanıt

İstek bir yol adı ve mesaj listesi taşır.
Her mesaj rol ve metin taşır.
İstek ayrıca araç tanımı, çıktı şeması ve çıktı sınırı taşıyabilir.
Araç tanımı ad, açıklama ve JSON Schema biçiminde parametreler taşır.

Yanıt metni, araç çağrılarını, token sayılarını, model adını ve API kaydını taşır.
Sağlayıcı token sayısını vermezse geçit boş değer döner.
Geçit araç çağrısını yalnız çevirir. Uygulama aracı kendi yetki denetiminden geçirir.
Bu turda sağlayıcı yanıtı bütünüyle gelir. Parça parça yanıt sonraki tura kalır.

## Sağlayıcı biçimleri

- OpenAI uyumlu geçit, mesajları `messages` alanına koyar. Araçları `tools` alanına koyar.
  Geçit araç girdisini `function.arguments` alanındaki JSON metninden okur.
  [OpenAI Chat API](https://developers.openai.com/api/reference/resources/chat)
- Anthropic geçidi, sistem mesajlarını `system` alanına taşır.
  Araç şemasını `input_schema` alanına koyar.
  Yanıttaki `tool_use` bölümünden çağrı kimliğini ve girdisini alır.
  [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create)
- Gemini geçidi, mesajları `contents` alanına koyar.
  Sistem mesajlarını `systemInstruction` alanına taşır.
  Araç tanımını `functionDeclarations` alanına koyar.
  Araç çağrısını `functionCall` alanından alır.
  [Gemini Generate Content](https://aistudio.google.com/api-reference/generate-content)
- Ollama geçidi, `/api/chat` ucunu kullanır.
  Araç girdisini `message.tool_calls` listesinden alır.
  Sağlayıcı kimlik vermezse geçit yanıt içindeki sıradan bir kimlik üretir.
  Gemini için de aynı kural geçerlidir.
  [Ollama Chat API](https://docs.ollama.com/api/chat)

## Yönlendirme

Geçit, kapalı veya dinlenen bağlantıları çıkarır.
Bütçesi dolan hesapları ve gereken yeteneği taşımayan modelleri de çıkarır.
Kalan adayları önceliğe, ağırlığa veya maliyete göre sıralar.
Kota veya sunucu hatası gelirse geçit bağlantıyı dinlendirir.
Zaman aşımında aynı kural geçerlidir.
Kimlik hatasında geçit bağlantıyı kapalı sayar.
Geçit bu hatalardan sonra sıradaki uygun adayı dener.

Frappe katmanı süreli sağlık kaydını ve deneme günlüğünü tutar.
Site katmanı dış çağrıdan önce veri kısıtını ve kotayı uygular.
Geçit hata metninde yalnız sabit hata kodu kullanır.

Site yöneticisi çıkışa izin verilen adresleri kurulum ayarında tanımlar.
Geçit çağrıdan önce model ve OAuth adresini bu listeye göre denetler.
Geçit anahtar ve belirteç taşıyan çağrılarda HTTPS kullanır.
Kurulum yalnız onaylı kimliksiz Ollama adresinde HTTP'ye izin verebilir.
OAuth istemci kimliği ve sırrı, önce erişim belirteci almak için kullanılır.
Geçit her sonucu hesaba bağlı API kaydı üzerinden değerlendirir.
Aynı API'deki başka bir model, dinlenme süresinde seçilmez.
Bütçe sınırı varsa geçit çağrının üst maliyetini önceden hesaplar.
Maliyeti hesaplanamayan çağrı bütçeli hesaba gitmez.
