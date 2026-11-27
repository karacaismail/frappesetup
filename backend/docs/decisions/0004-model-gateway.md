# Model geçidi

Geçit, uygulamanın model sağlayıcılarıyla konuştuğu ortak giriş noktasıdır.
Model adı ve bağlantı adresi site kaydından gelir.
Yolun hedefleri bir alt tabloda sıralanır.
`priority` kipinde geçit küçük öncelik değerini önce seçer.
Değerler eşitse geçit alt tablodaki sırayı kullanır.
Veri taşıma işlemi eski JSON sütununu bilinçli olarak bırakır.
Bütün sütunları isteyen Frappe çağrısı bu eski değeri de döndürebilir.
Geçit hedefleri artık alt tablodan okur.

## Hazır çözüm karşılaştırması

Geçit birden çok sağlayıcıyı tek biçimde çağırmalı.
Her kiracı kendi erişim, kota, bütçe ve bağlantı kurallarını uygulamalı.
D-10 kapsamında hazır seçenekler ve kalan işler karşılaştırıldı.

| Seçenek | Lisans | Hazır karşılık ve kalan iş |
| --- | --- | --- |
| Kurulu Frappe 16 ve ERPNext 16 | Frappe MIT. ERPNext GPL-3.0. | Frappe kayıt, rol, parola alanı ve HTTP ucu sağlar. ERPNext bu kurulumda iş uygulamasıdır. Sağlayıcı biçimleri ve çağrı yönlendirmesi geçit kodunda kalır. [Frappe kayıt türleri](https://docs.frappe.io/framework/user/en/basics/doctypes), [Frappe lisansı](https://github.com/frappe/frappe/blob/version-16/LICENSE), [ERPNext lisansı](https://github.com/frappe/erpnext/blob/version-16/license.txt) |
| LiteLLM | Açık çekirdek MIT. Enterprise klasöründe ayrı lisans vardır. | Ortak model çağrısı, yönlendirme ve maliyet takibi sunar. Frappe rolü ve çağrıdan önce kalıcı bütçe ayırma yine kiracıya bağlanır. Geçit sunucusu seçilirse ayrı servis işletilir. [LiteLLM geçit kılavuzu](https://docs.litellm.ai/docs/proxy/quick_start), [LiteLLM lisansı](https://github.com/BerriAI/litellm/blob/main/LICENSE) |
| Ollama | Sunucu MIT. Model lisansları ayrı değerlendirilir. | Yerel model çalıştırır ve OpenAI arayüzünün bir bölümünü sunar. Kiracı bütçesini ve diğer sağlayıcılara geçişi Frappe geçidi yönetir. [Ollama API](https://docs.ollama.com/api/openai-compatibility), [Ollama lisansı](https://github.com/ollama/ollama/blob/main/LICENSE) |

**Seçim nedeni.** Geçit, kurulu Frappe kayıtlarını ve rol denetimini yeniden kullanır.
Sağlayıcı farklarını küçük bağlantı işlevlerinde toplar.
Bu seçim ayrı bir geçit servisi kurma ihtiyacını kaldırır.
Ollama, yerel model sağlayıcısı olarak kalır.

## İlk kayıt izinleri

Tabloda `create` oluşturma, `delete` silme, `read` okuma, `write` yazma iznidir.
İzin seviyesi 0 kayda, seviye 1 ise `api_key` parola alanına uygulanır.
Alt tablo erişimini bağlı olduğu üst kayıttan alır.

| Kayıt türü | İzin seviyesi | Rol | İşlemler |
| --- | --- | --- | --- |
| `PLT AI Account` | 0 | PLT AI Manager, System Manager | create, delete, read, write |
| `PLT AI API` | 0 | PLT AI Manager, System Manager | create, delete, read, write |
| `PLT AI API` | 1 | PLT AI Manager, System Manager | write |
| `PLT AI Model` | 0 | PLT AI Manager, System Manager | create, delete, read, write |
| `PLT AI Provider` | 0 | PLT AI Manager, System Manager | create, delete, read, write |
| `PLT AI Route` | 0 | PLT AI Manager, System Manager | create, delete, read, write |
| `PLT AI Usage Log` | 0 | PLT AI Manager, System Manager | read |
| `PLT AI File Job` | 0 | PLT AI Manager, System Manager | read |
| `PLT AI Route Target` | 0 | Yok | Yok |
| `PLT AI File Chunk` | 0 | Yok | Yok |

Orkestratör, D-10, 22 Kasım 2026 Pazar

## Modül arayüzü

| Tür | Açık işlev veya olay | Görevi |
| --- | --- | --- |
| Python | `platform_core.model_gateway.api.complete` | Yetkili yol üzerinden model çağrısı yapar. |
| Python ve Bench | `platform_core.model_gateway.api.purge_usage_logs(*, dry_run=False, names=None)` | Yalnız “System Manager” çağırabilir. İşlev `eligible`, `deleted` ve `names` alanlarını döndürür. |
| HTTP | `platform_core.api.model.complete` | Oturum veya kullanıcı anahtarıyla model çağrısı yapar. |
| HTTP | `platform_core.api.model.test_api` | Yöneticiye bağlantı denemesi sunar. |
| HTTP | `platform_core.api.model.resolve_usage` | Yöneticinin doğruladığı tutarı kullanım kaydına işler. |
| HTTP | `platform_core.api.model.reconcile_stale_pending` | Yönetici oturumuyla takılı kayıt grubunu kapatır. |
| HTTP | `platform_core.api.model.purge_usage` | Silinecek kayıtları gösterir veya onaylı önizlemeye göre siler. |
| HTTP | `platform_core.api.model.clear_api_credential` | Kapalı bağlantının anahtarını siler. |
| HTTP | `platform_core.api.model.provider_catalog` | Bağlantı formunun sağlayıcı tanımlarını ve alanlarını verir. |
| HTTP | `platform_core.api.model.save_connection` | Alanları tanıma göre denetler. Yeni bağlantıyı kaydeder. Anahtarı şifreli alana yazar. Kullanıcı başına 60 saniyede 10 isteği kabul eder. |
| HTTP | `platform_core.api.model.check_connection` | Model listesini okuyarak canlı deneme yapar. Sonucu kayda yazar. Kullanıcı başına 60 saniyede 10 isteği kabul eder. |
| HTTP | `platform_core.api.model.create_file_job` | Büyük PDF işini açar. Yol ve dosya yetkisini denetler. Sağlayıcıyı çağırmaz. |
| HTTP | `platform_core.api.model.file_job_status` | Parça planını, tahmini maliyeti ve parça durumlarını gösterir. Parça metnini vermez. |
| HTTP | `platform_core.api.model.start_file_job` | Planlanmış işin parçalarını kuyruğa koyar. |
| HTTP | `platform_core.api.model.retry_file_chunk` | Başarısız tek parçayı yeniden kuyruğa koyar. |
| Bench | `platform_core.model_gateway.maintenance.reconcile_stale_pending` | Takılı kullanım kayıtlarını elle başlatılan işlemle kapatır. |
| Kanca | `ai_tools` | `create_ai_api`, `update_ai_api`, `create_ai_account`, `update_ai_account` ve `reconcile_stale_pending` araçlarını bildirir. |
| Yapay zekâ aracı | `reconcile_stale_pending` | İnsan onayından sonra seçilen takılı kaydı kapatır. |
| Kanca | `ai_write_closed_doctypes` | Genel yapay zekâ yazmasını `PLT AI API` ve `PLT AI Account` için kapatır. |
| Kayıt olayı | `validate` | `PLT AI API`, `PLT AI Model`, `PLT AI Provider` ve `PLT AI Route` kayıtlarını yazmadan önce denetler. |
| Şema olayı | `on_doctype_update` | `PLT AI Route Target` için aynı hedefin ikinci kez yazılmasını engeller. |

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
Geçit bütçe ayırırken hesap başına kilit alır.
Geçit çağrıdan önce kilidi bırakır.
Bütçe yeterse aynı hesapta iki çağrı birlikte çalışabilir.
Geçit çağrıdan önce tahmini üst tutarı bütçeden ayırır.
Çağrı hiç çıkmadıysa geçit ayrılan tutarı geri bırakır.
Sonuç bilinmiyorsa tahmini tutar, yönetici gerçek tutarı girene kadar ayrılır.
Eski kayıtta tahmin yoksa geçit yönetici çözümünü bekler.
Geçit bütçeyi her takvim ayı için ayrı hesaplar.
Geçit, bütçeli hesapta sonucu bilinmeyen süre aşımından sonra yedeğe geçmez.
Geçit bağlantı için 5 saniye ayırır.
Geçit okuma süresini model hızına ve çıktı sınırına göre hesaplar.
Hız belirtilmezse geçit saniyede 30 token kullanır.
Süreye sığmayan çağrı bütçeden pay ayırmadan reddedilir.
Geçit bir yol için en çok 60 saniye ayırır.
Deneme ortamı `bench serve` kullanır. Temel imaj Gunicorn için 120 saniye ayırır.

Yönetici, `model_gateway_endpoints` ayarına tam bağlantı adresini ekler.
Yönetici kendi hizmeti için `local`, dış hizmet için `external` seçer.
Yönetici yerel adresleri `addresses` listesine tek tek yazar.
Geçit, OAuth adresini de aynı listeye göre denetler.
Dış hizmet bağlantısı HTTPS ister.
`local_only` yolu yalnız yöneticinin `local` olarak işaretlediği hizmeti çağırır.
Geçit bağlantı anında sunucu adını çözer.
Geçit özel ağ adresi dönen bağlantıyı reddeder.
Geçit yalnız denetlediği açık ağ adresine bağlanır.

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
İşlev, sağlayıcı çağrısından önce `pending` kaydını kalıcı olarak yazar.
Bu kayıt, istek yarıda kalırsa bütçe denetiminde korunur.
Geçit çağrı bitince son durumu kalıcı olarak kaydeder.
Elle başlatılan mutabakat, takılı kayıtları `unknown` durumuna alır.
Gerçek ücret belirlenene kadar ayrılan tutar korunur.
Yönetici mutabakatı HTTP üzerinden de başlatabilir.
Yapay zekâ aracı yalnız önizlemede seçilen tek kaydı kapatır.
Araç yazımdan önce insan onayı ister.
İşletim komutu aşağıdadır.

```sh
bench --site SITE execute platform_core.model_gateway.maintenance.reconcile_stale_pending
```

Model çağrısı insan oturumunu ve Frappe kullanıcı anahtarını kabul eder.
Aracı, çağrıyı yapay zekâ katmanından başlatır.
Arka plan işi `platform_core.model_gateway.api.complete` işlevini kullanır.
Geçit bu işlevde kullanıcının yetkisini denetler.
Arka plan işi, model çağrısından önce kendi veritabanı yazısını bitirir.

Yönetici sonucu bilinmeyen denemenin gerçek ücretini yazabilir.
Geçit ücret tutarını ondalık metin olarak döner.
Yanıtta para birimi de bulunur.
Geçit önceki sonucu saklar. Yönetici kısa bir not ekleyebilir.
Yönetici kapalı bağlantının anahtarını ayrı bir uçla silebilir.
Geçit yönetim araçları adres değişince bağlantıyı kapatır ve anahtarı siler.
Yönetici yeni anahtarı Desk ekranında girer.
Kayıtlı anahtarlar varsa geçit, onları etkileyen sağlayıcı adresi değişikliğini reddeder.
Geçit bağlantı kaydına silme notu ekler.
Boş anahtar alanıyla form kaydetmek mevcut anahtarı korur.
Kapanmış kullanım günlükleri 365 gün tutulur.
Bu süre sabittir.
Temizliği yalnız “System Manager” rolü başlatabilir.
HTTP isteğinde yönetici önce silinecek kayıtları önizler.
Geçit önizleme kodunu `preview_token` alanında döner.
Yönetici silmeyi aynı kodla elle başlatır.
Temizlik yalnız kapanmış kayıtları siler. Her çağrı en çok 500 kayıt siler.
O-32 kararı gereği saklama temizliği kayıtları kalıcı siler.
Frappe “Deleted Document” tablosuna kopya yazmaz.
Geri dönüş için silme öncesi alınan veritabanı yedeği kullanılır.
Geçit temizliği “Activity Log” kaydına yazar.

Python işlevi 365 günden eski kapanmış kayıtları sayar.
`dry_run=True` ise işlev kayıt silmez. En çok 500 kayıt adı döndürür.
Silme yalnız onaylanan adları kapsar. Bir kayıt silinemezse bütün silmeler geri alınır.
İşlev önizleme belirteci istemez. Onayı çağıran taraf yönetir.

Aşağıdaki terminal komutları önce önizler, sonra en çok 500 kaydı kalıcı siler.
Önce önizlemedeki kayıt adlarını kontrol edin. Silme komutuna onayladığınız adları verin.

```sh
bench --site SITE execute platform_core.model_gateway.api.purge_usage_logs --kwargs '{"dry_run":True}'
```

```sh
bench --site SITE execute platform_core.model_gateway.api.purge_usage_logs --kwargs '{"names":["ONAYLANAN-KAYIT-ADI"]}'
```

## Bağlantı formu ve canlı deneme

Bu bölüm 23 Kasım 2026 Pazartesi günü eklendi. Ayrıntı karar sitesinin `ai-saglayici.md` sayfasındadır.

Sağlayıcı tanımları `model_gateway/provider_catalog.json` dosyasındadır. Kodda sağlayıcı listesi yoktur. Kod yalnız alanın yazılabileceği kayıt alanlarını bilir. Gizli anahtar yalnız şifreli `api_key` alanına yazılır.

Canlı deneme model listesini okur. Bu istek token harcamaz. Bu yüzden deneme kullanım kaydına satır yazmaz. Sonuç `PLT AI API` kaydının `connection_status` alanına yazılır.

Büyük dosya sağlayıcıya bütün olarak gönderilmez. Sunucu dosyayı metne çevirir ve parçalara böler. Sağlayıcının dosya API'si bu aşamada kullanılmaz. Neden şudur: İkili dosya örtülemez ve dosya tek hesaba bağlanır.
