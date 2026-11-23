---
title: "AI sağlayıcı bağlantısı ve büyük dosya"
nav: "Sağlayıcı bağlantısı"
order: 27
---

Bu sayfa yapay zekâ sağlayıcısının panele nasıl bağlandığını anlatır. Sağlayıcı, model hizmetini veren şirkettir. Örneğin OpenAI, Google Gemini ve Anthropic birer sağlayıcıdır. Sayfa büyük dosyanın nasıl işleneceğini de anlatır. Kararın tarihi 23 Kasım 2026 Pazartesi günüdür.

Kararın nedeni şudur: Bir PDF 300 MB ya da 1 GB olabilir. Örneğin bir ürün kataloğu bu kadar büyük olabilir. Tek bir API hesabı bu işte darboğaz olur. Bu yüzden panel birden çok sağlayıcıyı ve birden çok hesabı bağlar. Bu istek proje kaydındaki D-11 kararıdır.

Gereksinimler G-155 ve G-156 kalemleridir. İki kalem [Rail 5](/frappesetup/rail-5-ai/) içindeki model geçidine bağlıdır. Model geçidi, platformun sağlayıcılarla konuşan sunucu katmanıdır.

## Durum

Backend bu akışın üç ucunu yazdı. Uçlar testle sınandı. Testlerde sahte sağlayıcı sunucusu kullanıldı. Gerçek sağlayıcıya istek gönderilmedi.

Panel ekranı henüz yazılmadı. Ekran ayrı bir iş olacak. Ekran işi bu sayfadaki sözleşmeyi kullanacak.

Büyük dosya işi henüz yazılmadı. Bu sayfadaki büyük dosya bölümü bir gereksinimdir.

## Sağlayıcı ekleme akışı (G-155)

Yöneticinin panelde izleyeceği sıra şöyledir:

1. Yönetici "API ekle" düğmesine basar.
2. Yönetici bir kategori seçer. Örneğin "AI LLM" kategorisini seçer.
3. Yönetici bir sağlayıcı seçer. Örneğin "OpenAI" sağlayıcısını seçer.
4. Yönetici sağlayıcının istediği alanları doldurur. Örneğin API anahtarını yazar.
5. Yönetici "Kaydet" düğmesine basar.
6. Panel canlı bağlantı denemesini başlatır.
7. Panel sonucu gösterir. Deneme geçerse "Bağlandı" yazar.

Her adımın kuralı aşağıdadır.

### 1. "API ekle" düğmesi

Düğmeyi yalnız yetkili rol görür. Yetkili roller "AI Manager" ve "System Manager" rolleridir. Başka bir kullanıcı uca istek gönderirse sunucu isteği reddeder. Sunucu bu durumda 403 kodu döner.

### 2. Kategori seçimi

Panel kategorileri sunucudan alır. Kategori listesi kodda yazılı değildir. Bugün tek kategori vardır: "AI LLM". Yeni kategori veri dosyasına eklenir.

### 3. Sağlayıcı seçimi

Panel seçilen kategorideki sağlayıcıları listeler. Bugün beş sağlayıcı tanımı vardır:

- OpenAI
- Anthropic
- Google Gemini
- OpenAI uyumlu hizmet
- Ollama

Ollama, platformun kendi ağında çalışan model sunucusudur. Ollama anahtar istemez.

### 4. Alanlar

Panel formu sağlayıcı tanımından çizer. Her alanın tanımında şu bilgiler vardır:

- alanın adı ve ekrandaki etiketi,
- alanın türü,
- alanın zorunlu olup olmadığı,
- alanın açıklaması.

Alan türü üç tanedir. `secret` türü gizli anahtardır. `text` türü düz metindir. `url` türü bir bağlantı adresidir.

Her bağlantıda iki ortak alan da vardır. Birincisi hesap adıdır. İkincisi bağlantı adıdır. Yönetici var olan bir hesabı seçerse hesap adını yazmaz.

### 5. Kaydet

Sunucu alanları tanıma göre denetler. Bir alan hatalıysa sunucu kaydetmez. Sunucu hatalı alanların adlarını döner. Panel bu alanları formda işaretler.

Kayıt geçerse sunucu şu kayıtları yazar:

1. Sağlayıcı kaydı ilk kullanımda açılır. Sonraki bağlantılar aynı kaydı kullanır.
2. Yönetici yeni hesap adı yazdıysa sunucu yeni hesap açar.
3. Sunucu her kayıtta yeni bir API bağlantısı açar.

Böylece bir sağlayıcıda birden çok hesap olur. Bir hesapta da birden çok API bağlantısı olur. Bu kural D-11 kararıdır.

### 6. Canlı bağlantı denemesi

Panel kayıttan sonra deneme ucunu çağırır. Deneme ayrıntısı aşağıdaki bölümdedir.

### 7. Geri bildirim

Panel denemenin sonucunu gösterir. Sonuç API bağlantısının kaydına da yazılır. Yönetici sonucu daha sonra kayıtta görebilir.

## Alan şeması

Sağlayıcı tanımları bir veri dosyasındadır. Dosya `provider_catalog.json` dosyasıdır. Kodda sağlayıcı listesi yoktur. Yeni sağlayıcı bu dosyaya eklenir.

Kod yalnız bir şeyi bilir. Bir alan hangi kayıt alanına yazılabilir? Bu liste kısadır ve kapalıdır. Gizli anahtar yalnız şifreli alana yazılır.

Sunucu veri dosyasını her okumada denetler. Dosya kuralı bozarsa uç 503 kodu döner. Örneğin gizli alanı düz alana yazan tanım reddedilir.

Bugünkü alanlar şöyledir:

| Sağlayıcı | Zorunlu alan | İsteğe bağlı alan |
| --- | --- | --- |
| OpenAI | API anahtarı | kurum kimliği, proje kimliği |
| Anthropic | API anahtarı | yok |
| Google Gemini | API anahtarı | yok |
| OpenAI uyumlu hizmet | hizmet adresi, API anahtarı | yok |
| Ollama | hizmet adresi | yok |

Kurum kimliği ve proje kimliği hesap kaydına yazılır. Geçit bu kimlikleri OpenAI isteğinin başlığına koyar.

Tanım dosyasında model adı yoktur. Model adı yalnız model kaydında durur. Bu kural proje kaydındaki O-13 kararıdır.

## Canlı bağlantı denemesi

Deneme sağlayıcıya tek bir istek gönderir. İstek model listesini okur. Bu, sağlayıcının en ucuz denetim isteğidir.

| Sağlayıcı | Gönderilen istek |
| --- | --- |
| OpenAI ve OpenAI uyumlu hizmet | `GET /v1/models` |
| Anthropic | `GET /v1/models` |
| Google Gemini | `GET /v1beta/models` |
| Ollama | `GET /api/tags` |

### Maliyet

Model listesi isteği token harcamaz. Bu yüzden deneme ücret doğurmaz. Deneme kullanım kaydına satır yazmaz. Sağlayıcı yine de isteği hız sınırından sayar.

Aynı bağlantı için iki deneme aynı anda çalışmaz. İkinci deneme 429 kodu alır.

Her kullanıcı deneme ucunu 60 saniyede en çok 10 kez çağırabilir. Kaydetme ucunda da aynı sınır vardır. Sayaç her kullanıcı ve her uç için ayrıdır. Kullanıcı sınırı aşarsa sunucu 429 kodu ve `gateway_busy` hatasını döner. Bu durumda sağlayıcıya istek gitmez. Kaydetme ucu da kayıt açmaz. Bu sınır sağlayıcının anahtarı kısıtlamasını önler. Çalınmış bir yönetici oturumu da sınırsız istek gönderemez.

### Süre sınırı

Geçit bağlantı kurmak için en çok 5 saniye bekler. Geçit yanıt için en çok 10 saniye bekler. Süre dolarsa sonuç "ağ hatası" olur.

### Sonuç ve ekrandaki ileti

Deneme her durumda HTTP 200 döner. Sonuç `status` alanındadır. Panel her sonuç için şu iletiyi gösterir:

| Sonuç | Ekrandaki ileti | Yöneticinin yapacağı iş |
| --- | --- | --- |
| `connected` | Bağlandı. | İş yok. |
| `invalid_credentials` | Anahtar geçersiz. | Anahtarı yeniden girin. |
| `permission_denied` | Anahtarın bu işe izni yok. | Sağlayıcıda anahtarın iznini açın. |
| `quota_exceeded` | Kota doldu ya da hız sınırı aşıldı. | Kotayı denetleyin. Sonra yeniden deneyin. |
| `network_error` | Sağlayıcıya ulaşılamadı. | Adresi denetleyin. Sonra yeniden deneyin. |
| `provider_error` | Sağlayıcı beklenmeyen bir yanıt verdi. | Adresi ve hesabın kredisini denetleyin. Sorun sürerse destek isteyin. |
| `endpoint_not_approved` | Bu adres onaylı değil. | Platform operatöründen adres onayı isteyin. |
| `configuration_error` | Kayıt eksik. | Bağlantının alanlarını tamamlayın. |

Yanıtta sağlayıcının kendi iletisi yoktur. Yanıtta model adı da yoktur. Yanıt yalnız görülen model sayısını taşır. Bu sayı yalnız ilk sayfadaki modelleri sayar. Bazı sağlayıcılar listeyi sayfa sayfa verir. Örneğin Anthropic ilk sayfada 20 model verir. Gerçek model sayısı daha büyük olabilir.

### "Bağlandı" sonucunun sınırı

"Bağlandı" sonucu anahtarın geçerli olduğunu gösterir. Bu sonuç kalan kotayı göstermez. Kalan krediyi de göstermez. Model listesi isteği kota dolunca da çoğu zaman başarılı olur. Bu yüzden kota sorunu ilk gerçek istekte görünür.

Örneğin bir OpenAI hesabının kredisi bitmiş olabilir. Deneme yine "Bağlandı" der. İlk gerçek istek ise kota hatası alır.

Anthropic kredi bitince 400 kodu dönebilir. Deneme bu yanıtı `provider_error` sonucuna çevirir. `quota_exceeded` sonucu yalnız 429 yanıtında çıkar.

Panel bu sınırı yöneticiye kısa bir notla göstermelidir. Not "Bağlandı" sonucunun yanında durur. Örnek not şudur: "Anahtar geçerli. Kalan kota bu denemede görünmez."

Kotayı gerçekten sınamak için tek tokenlık bir deneme gerekir. Bu deneme ücret doğurur. Bu seçenek bu işte yoktur. Seçenek sonraki bir işte tartışılacak.

Bağlandı sonucu bağlantının sağlık durumunu "sağlıklı" yapar. "Anahtar geçersiz" sonucu bağlantıyı yol seçiminden çıkarır. Yönetici anahtarı ya da adresi değiştirirse sonuç "denenmedi" olur.

### Adres onayı

Geçit yalnız onaylı adrese bağlanır. Onaylı adresler sitenin `model_gateway_endpoints` ayarındadır. Bu ayarı platform operatörü yazar. Panel bu ayarı değiştiremez. Bu kural sunucunun iç ağa istek göndermesini önler.

## Büyük dosya stratejisi (G-156)

### Karar

Platform büyük dosyayı sağlayıcıya bütün olarak göndermez. Platform dosyayı kendi sunucusunda metne çevirir. Sonra metni parçalara böler. Parçaları birden çok hesaba dağıtır.

Sağlayıcının dosya API'si bu aşamada kullanılmaz. Dosya API'si, dosyayı sağlayıcının deposuna yükleyen hizmettir.

### Gerekçe

1. Geçit dış sağlayıcıya giden metni örter. Örneğin telefon numarasını gizler. PDF dosyasının içi örtülemez. Bütün dosya gönderilirse kişisel veri örtülmeden çıkar. Bu durum KVKK kuralına aykırıdır (G-90).
2. Dosya API'si dosyayı tek bir hesaba bağlar. Dosya o hesabın deposunda kalır. O zaman iş başka hesaba dağıtılamaz. Darboğaz tam da budur.
3. Her sağlayıcının dosya API'si farklı çalışır. Sınırları da zamanla değişir. Parçalı metin bütün sağlayıcılarda aynı çalışır.
4. Bir parça başarısız olursa yalnız o parça yeniden denenir. Bütün dosya yeniden gönderilmez.

### Akış

1. Kullanıcı dosyayı yükler. Yükleme parça parça yapılır. En büyük dosya boyutu bir site ayarıdır.
2. Dosya Frappe'nin özel dosya alanına girer. Dosya dışarıya açık değildir.
3. Kullanıcı işi başlatır. İş, Frappe kuyruğunda çalışan bir arka plan işidir. Zamanlanmış iş değildir.
4. Sunucu dosyadan sayfa sayfa metin çıkarır.
5. Taranmış sayfada metin yoksa yazı tanıma çalışır. Yazı tanıma yalnız platformun kendi sunucusunda çalışır.
6. Sunucu metni parçalara böler. Parça sayfa sınırından bölünür.
7. Parça boyu model kaydındaki bağlam boyundan hesaplanır. Bağlam boyu, modelin bir istekte okuyabildiği en çok token sayısıdır. Parça boyu kodda sabit yazılmaz.
8. Ekran iş başlamadan önce parça sayısını ve tahmini maliyeti gösterir. Tahmin model kaydındaki fiyattan hesaplanır.
9. Her parça geçidin `complete` ucundan gider. Örtme kuralı her parçaya uygulanır.
10. Bütün parçalar bitince sunucu sonuçları sırayla birleştirir. Özet gerekiyorsa sunucu parça özetlerini ikinci bir istekle birleştirir.

### Birden çok hesaba dağıtma

Bir yol birden çok API bağlantısını hedef alabilir. Bu bağlantılar farklı hesaplarda ve farklı sağlayıcılarda olabilir. Geçit her parça için bir bağlantı seçer. Seçim önceliğe, ağırlığa ve bekleme süresine göre yapılır.

Bir bağlantı 429 kodu alırsa geçit o bağlantıyı 60 saniye dinlendirir. Parça sıradaki bağlantıya gider. Böylece tek bir hesabın sınırı bütün işi durdurmaz.

### Kota ve hız sınırı

Her API bağlantısında iki sınır vardır. Birincisi dakikadaki istek sayısıdır. İkincisi dakikadaki token sayısıdır. Geçit parçayı göndermeden önce iki sınırı denetler. Sınır doluysa parça başka bağlantıya gider.

Hesabın aylık bütçesi de vardır. Geçit her parçadan önce tahmini tutarı bütçeden ayırır. Bütçe yetmezse parça o hesaba gitmez.

### Kullanım kaydı

Her parça kullanım kaydına bir satır yazar. Satırda bağlantı, hesap, model, token sayısı ve tutar durur. Satırda dosya işinin kimliği ve parçanın sırası da durmalıdır. Bu iki alan henüz yoktur. Alanlar büyük dosya işiyle eklenecek.

Yönetici bir dosya işinin toplam maliyetini bu satırlardan görür.

## Güvenlik

- Anahtar yalnız sunucuda durur. Anahtar Frappe'nin şifreli parola alanına yazılır.
- Anahtar arayüze dönmez. Kaydetme yanıtında da deneme yanıtında da anahtar yoktur.
- Kayıt okunduğunda anahtar alanı yanıttan çıkarılır. Frappe'nin parola okuma yolu da kapalıdır.
- Anahtar günlüğe yazılmaz. Günlükte yalnız sabit hata kodları durur.
- Yalnız "AI Manager" ve "System Manager" rolleri bağlantı ekleyebilir. Bu roller deneme de yapabilir.
- Uçlar yalnız tarayıcı oturumunu kabul eder. Kullanıcı API anahtarıyla bu uçlar çağrılamaz.
- Genel yapay zekâ yazma katmanı API ve hesap kayıtlarına yazamaz.

## Backend sözleşmesi

Uçların sözleşmesi `backend/contracts/platform_core-model-gateway.openapi.yaml` dosyasındadır. Panel işi bu sözleşmeye göre yazılır.

| Uç | İşi |
| --- | --- |
| `platform_core.api.model.provider_catalog` | Kategorileri, sağlayıcıları ve alanları döner. |
| `platform_core.api.model.save_connection` | Alanları denetler. Bağlantıyı kaydeder. |
| `platform_core.api.model.check_connection` | Canlı denemeyi yapar. Sonucu kayda yazar. |

Üç uç da `POST` yöntemiyle çağrılır.
