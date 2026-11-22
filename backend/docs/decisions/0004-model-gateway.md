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

## Frappe uygulaması

Geçit, her sağlayıcı denemesinden önce kullanım kaydı açar.
Kayıt, çağrının sonucunu ve ölçülen kullanımı tutar.
Geçit mesaj metnini, anahtarı ve araç girdisini kayda yazmaz.
Maliyeti bilinmeyen ücretli deneme, sınırlı hesabı tekrar kullanıma kapatır.
Sınır takvim ayı değişince yeni ay için hesaplanır.
Geçit, aynı sitede aynı anda bir ücretli çağrı başlatır.

Yönetici, `model_gateway_endpoints` ayarına tam bağlantı adresini ekler.
Adresin değeri yerel ağ için `local`, dış hizmet için `external` olur.
Geçit, OAuth adresini de aynı listeye göre denetler.
Dış hizmet bağlantısı HTTPS ister.
`local_only` yolu yalnız yerel ağa çağrı yapar.

`masked` yolu, yaygın kimlik ve ödeme bilgilerini kalıpla örter.
Geçit, dış çağrıdan önce örtülmüş isteğin parmak izini hesaplar.
Parmak izi, içeriği temsil eden sabit uzunlukta bir özettir.
Yönetici onaylı özetleri `model_gateway_external_payloads` ayarına ekler.
Ayar, yol kimliğini onaylı özet listesine bağlar.
Özet mesajı, araç listesini, çıktı şemasını ve çıktı sınırını kapsar.
Geçit onaysız içeriği dış hizmete göndermez.
Bağlantı denemesi yalnız sunucudaki sabit ve açık metni gönderir.

İki HTTP ucu izin denetimini ortak geçit işlevlerine bırakır.
Statik tarama bu işlevleri izleyemediği için iki uçta dar istisna vardır.
HTTP testleri hem misafir hem yetkisiz kullanıcı erişimini sınar.
Kullanım günlüğüne yazan iç işlev yalnız sunucunun seçtiği alanları alır.
İşlev, sağlayıcı çağrısından önce deneme kaydını veritabanına yazar.
Bu kayıt, istek yarıda kalırsa bütçe denetiminde korunur.

Model çağrısı, yapay zekâ erişim katmanının süreli belirtecini de kabul eder.
Geçit belirteci yalnız model çağrısı yolunda tanır.
Geçit oturum sahibini ve kalan çağrı sayısını denetler.
Yapay zekâ katmanı ile birleştirmede ortak kanca listesi iki girişi korumalıdır.
