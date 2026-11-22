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
Geçit aynı hesapta süren denemeler için hesap başına kilit alır.
Farklı hesaplar aynı anda çağrı yapabilir.
Geçit çağrıdan önce tahmini üst tutarı bütçeden ayırır.
Çağrı hiç çıkmadıysa geçit ayrılan tutarı geri bırakır.
Sonuç bilinmiyorsa tahmini tutar, yönetici gerçek tutarı girene kadar ayrılır.
Eski kayıtta tahmin yoksa geçit yönetici çözümünü bekler.
Geçit bütçeyi her takvim ayı için ayrı hesaplar.
Geçit, bütçeli hesapta sonucu bilinmeyen süre aşımından sonra yedeğe geçmez.
Geçit bağlantı için 5 saniye ayırır. Okuma süresi çıktı sınırına göre artar.
Geçit bir yol için en çok 105 saniye ayırır.
Deneme ortamı `bench serve` kullanır. Temel imaj Gunicorn için 120 saniye ayırır.

Yönetici, `model_gateway_endpoints` ayarına tam bağlantı adresini ekler.
Adresin değeri yerel ağ için `local`, dış hizmet için `external` olur.
Geçit, OAuth adresini de aynı listeye göre denetler.
Dış hizmet bağlantısı HTTPS ister.
`local_only` yolu yalnız yerel ağa çağrı yapar.

`masked` yolu, yaygın kimlik ve ödeme bilgilerini kalıpla örter.
Geçit dış hizmete her gönderimde mesajı örter.
Geçit araç ve şema metnindeki hassas değerleri de örter.
Geçit hassas bir alan adı bulursa isteği durdurur.
“AI Manager” dış gönderime izin veren yolu seçebilir.
Bağlantı denemesi sunucudaki sabit ve açık metni gönderir.

HTTP uçları izin denetimini ortak işlevlere bırakır.
Statik tarama bu işlevleri izleyemediği için uçlarda dar istisna vardır.
HTTP testleri hem misafir hem yetkisiz kullanıcı erişimini sınar.
Kullanım günlüğüne yazan iç işlev yalnız sunucunun seçtiği alanları alır.
İşlev, sağlayıcı çağrısından önce deneme kaydını veritabanına yazar.
Bu kayıt, istek yarıda kalırsa bütçe denetiminde korunur.

Model çağrısı insan oturumunu ve Frappe kullanıcı anahtarını kabul eder.
Aracı, çağrıyı yapay zekâ katmanından başlatır.
Geçidin ortak işlevi arka plan işinde de kullanıcının yetkisini denetler.
Arka plan işi, model çağrısından önce kendi veritabanı yazısını bitirir.

Yönetici, sonucu bilinmeyen denemenin gerçek ücretini kayda yazabilir.
Yönetici, kapalı bağlantının anahtarını ayrı bir uçla silebilir.
Boş anahtar alanıyla form kaydetmek mevcut anahtarı korur.
Kullanım günlükleri varsayılan olarak 365 gün tutulur.
Site yöneticisi süreyi `model_gateway_usage_retention_days` ayarında belirler.
Yönetici temizliği önizleyebilir veya elle başlatabilir.
Temizlik yalnız kapanmış kayıtları siler. Her çağrı en çok 500 kayıt siler.
