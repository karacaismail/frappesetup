# Karar 0002: Yapay zekâ erişim katmanı

Bu not 22 Kasım 2026 Pazar günü yazıldı. Notu platform-core-yz işi yazdı. Karar verildi. Orkestratör kararı birleştirmede inceler. Karar, proje kaydının D-9, D-10 ve O-12 maddelerine dayanır. Sözleşmenin 10. bölümüne de dayanır.

## 1. Kısa karar

Katmanı `platform_core` içinde, `yapay_zeka` modülünde kendimiz yazıyoruz. Yeni paket eklemiyoruz.

Katman MCP ile konuşur. MCP, modellerin araç kullandığı açık protokoldür. Protokol kodunu yeniden yazmıyoruz. Frappe 16'nın içindeki `frappe.mcp` modülünün protokol parçalarını kullanıyoruz.

Frappe'nin hazır MCP ucunu ise kullanmıyoruz. Bu uç sözleşmenin dört kuralını karşılamıyor. Platform bu ucu kiracı sitesinde kapatır.

## 2. Hazır yol incelemesi (T-1)

### Frappe 16'nın içinde MCP var

İnceleme `frappe/erpnext:v16.55.0` imajında yapıldı. İmajdaki Frappe sürümü 16.56.0'dır. Python sürümü 3.14.10'dur.

| Bulgu | Kaynak |
| --- | --- |
| Uç adresi `/api/v2/mcp` olur. | `frappe/api/v2.py:289` |
| Ucu “System Settings” içindeki `enable_mcp` ayarı açar. Ayarın varsayılanı açıktır. | `frappe/mcp/__init__.py:11`, `system_settings.json` |
| Uç yalnız yönetim ekranı kullanıcısına açıktır. Öteki kullanıcı 403 alır. | `frappe/mcp/transport.py:37` |
| Uç yalnız POST kabul eder. Oturum kaydı tutmaz. Yanıt tek JSON'dur. | `frappe/mcp/transport.py:3` ve `:33` |
| Desteklenen protokol sürümleri `2026-07-28` ve `2025-11-25` olur. | `frappe/mcp/protocol.py:11` ve `:12` |
| Araç listesi sabit 13 araçtır. Uygulamanın araç ekleyeceği kanca yoktur. | `frappe/mcp/tools/__init__.py:84` |
| Yazma araçları kaydı doğrudan yazar. Önizleme ve onay yoktur. | `frappe/mcp/tools/documents.py` |
| `call_method` aracı her açık işlevi ve “Server Script” ucunu çağırır. | `frappe/mcp/tools/methods.py:31` ve `:67` |
| İşlem günlüğü yoktur. Yalnız izleme verisine araç adı eklenir. | `frappe/mcp/tools/__init__.py` içindeki `call` |
| Alan tanımı `description` değerini dönmez. | `frappe/mcp/tools/discover.py` içindeki `field_schema` |

Bu modül MIT lisanslıdır. Dosya başlıkları bunu yazar.

### Hazır uç neden yetmiyor

| Sözleşme kuralı | Hazır ucun durumu |
| --- | --- |
| Yazma önce önizleme üretir. İnsan onaylar (kural 3). | Yok. Model kaydı doğrudan yazar. |
| Her çağrı “AI Action Log” kaydına düşer (kural 4). | Yok. |
| “Server Script” ve ham çağrı aracı yoktur (kural 5). | `call_method` bu yolu açar. |
| Uygulamalar `ai_tools` kancasıyla araç bildirir (G-105). | Kanca yok. |
| Son kullanıcı “Website User” türündedir (D-5). | Bu kullanıcı 403 alır. |
| Yapay zekâ alanı açıklamasından anlar. | Açıklama dönmüyor. |

### `frappe/mcp` deposu

Karar sitesi bu depoyu `frappe_mcp` adıyla anar (G-84). Depo 22 Kasım 2026 Pazar günü GitHub'dan okundu.

- Depo arşivlenmiştir. README şöyle yazar: “This app is deprecated. Frappe Framework now has a built-in MCP server.”
- Lisansı MIT'dir.
- PyPI'da tek sürüm vardır: 0.1.0, 7 Temmuz 2025. Son commit 27 Ekim 2026 tarihlidir ve kullanımdan kaldırma notudur.
- Kodu `2025-03-26` protokol sürümünü sabit döner. Bu sürüm üç sürüm eskidir.
- Paket `Werkzeug==3.1.3` ister. Frappe 16 `Werkzeug==3.1.9` ister. İki sabitleme çakışır.
- Paket yalnız protokol katmanıdır. Yetki, alan süzme, onay ve günlük taşımaz.
- Frappe 16 üzerinde çalıştığı doğrulanmadı. Paket kurulmadı.

Bu depoyu kullanmıyoruz. Karar sitesindeki G-84 maddesi bu yüzden eskidi. Karar sitesi uyum sağlanamayan durumu da yazar. O durumda aynı araç şeması `platform_core` içinde sunulur. Bu karar o yolu izler.

### MCP'nin güncel sürümü

Kaynak resmî belirtim sitesidir: `modelcontextprotocol.io/specification/2026-07-28`.

- Güncel sürüm `2026-07-28` olur. Önceki sürüm `2025-11-25` olur.
- HTTP taşıma biçiminin adı “Streamable HTTP” olur. Tek uç vardır ve uç POST kabul eder.
- Güncel sürümde oturum başlığı, `initialize` adımı ve GET akışı kaldırıldı. Her mesaj ayrı bir POST isteğidir.
- Sunucu yanıtı tek JSON ya da o isteğe bağlı bir akış olarak döner. Biz tek JSON döneriz.
- `MCP-Protocol-Version` başlığı her istekte zorunludur. `Mcp-Method` başlığı da zorunludur. Araç çağrısında `Mcp-Name` başlığı gerekir.
- Sunucu `Origin` başlığını doğrulamak zorundadır. Geçersiz kökene 403 döner.
- Yetkilendirme isteğe bağlıdır. Kullanılırsa sunucu başka hedef için üretilmiş belirteci kabul edemez.
- Belirtime göre araç çağrısını reddedebilen bir insan her zaman bulunmalıdır.
- Araç hatası protokol hatası değildir. Araç hatası `isError: true` taşıyan sonuçtur.

Frappe'nin `frappe.mcp.transport` ve `frappe.mcp.protocol` modülleri bu kuralları uygular. Bu yüzden o modülleri yeniden kullanıyoruz.

## 3. Seçenekler ve seçim (T-2)

İhtiyaç şudur: Sözleşmenin 10. bölümündeki dokuz kuralı karşılayan bir MCP ucu.

| Seçenek | Lisans | Bakım | Değerlendirme |
| --- | --- | --- | --- |
| A. Frappe'nin hazır `/api/v2/mcp` ucu | MIT | Frappe ile gelir | Altı kuralı karşılamıyor. Genişletme kancası yok. |
| B. `frappe/mcp` paketi | MIT | Arşivli | Eski protokol. Sürüm çakışması var. |
| C. `Frappe_Assistant_Core` uygulaması | AGPL-3.0 | Etkin | O-12 yasaklar. Ham Python ve ham sorgu aracı taşır. |
| D. Resmî `mcp` Python paketi | MIT | Etkin | ASGI sunucusu ve yeni bağımlılıklar ister. Frappe WSGI ile çalışır. |
| E. Kendi ince katmanımız ve Frappe'nin protokol modülleri | MIT | Bizde | Yeni paket yok. Bütün kurallar karşılanır. |

Seçim E seçeneğidir.

- Yeni paket eklemiyoruz. `pydantic` paketi Frappe 16 ile gelir (`pyproject.toml:68`). Girdi doğrulamada bu paketi kullanırız.
- `pydantic` doğrudan kullanılır. Bu yüzden T-3 gereği `platform_core/pyproject.toml` dosyasında bildirilmelidir. Dosyanın sahibi dev-ortam işidir. Bu satırı raporda isteyeceğiz.
- Bir risk var. `frappe.mcp.transport` ve `frappe.mcp.protocol` Frappe'nin iç modülleridir. Frappe bu modülleri bir yükseltmede değiştirebilir.
- Bu riske karşı testler gerçek HTTP isteğiyle MCP el sıkışmasını sınar. Yükseltme bu modülleri bozarsa test başarısız olur.
- Geri dönüş yolu da var. İki modül yaklaşık 250 satırdır ve MIT lisanslıdır. Gerekirse lisans notuyla kendi modülümüze kopyalarız. Araçlar ve onay akışı bundan etkilenmez.
- Tarayıcıya etkisi yoktur. Bu iş yalnız sunucu katmanıdır.

### Hazır uç kapatılır

Frappe'nin `/api/v2/mcp` ucu varsayılan olarak açıktır. Açık kalırsa yönetici onaysız yazma yolunu kullanabilir. Bu, sözleşmenin 3. kuralını deler.

- `platform_core` kurulumda ve her `migrate` sonunda `enable_mcp` ayarını kapatır.
- Bu bir ayar değişikliğidir. Frappe'nin kodu değişmez (M-4).
- Test, `/api/v2/mcp` adresinin 404 döndüğünü doğrular.

## 4. Araçlar DocType tanımından nasıl üretilir

Her DocType için ayrı araç üretmiyoruz. Bir sitede yüzlerce DocType vardır. Her biri için dokuz araç, modelin bağlamını doldurur.

Bunun yerine az sayıda genel araç vardır. Her araç `doctype` değerini girdi olarak alır. Tanım çalışma anında `frappe.get_meta` işlevinden okunur. Bu işlev “Custom Field” ve “Property Setter” değişikliklerini de içerir. Yeni DocType için kod gerekmez.

| Tür | Araç | İşi |
| --- | --- | --- |
| Tanım | `search_doctypes` | Kullanıcının okuyabildiği DocType adlarını arar. |
| Tanım | `get_doctype_schema` | Alanları, açıklamaları ve kullanıcının izinlerini döner. |
| Okuma | `list_documents` | Kayıtları süzer ve listeler. |
| Okuma | `get_document` | Tek kaydı alt tablolarıyla döner. |
| Okuma | `run_report` | Kullanıcının çalıştırabildiği raporu çalıştırır. |
| Yazma | `create_document` | Yeni kayıt önerisi açar. |
| Yazma | `update_document` | Güncelleme önerisi açar. |
| Yazma | `submit_document` | Onaya gönderme önerisi açar. |
| Yazma | `cancel_document` | İptal önerisi açar. |
| Yazma | `delete_document` | Silme önerisi açar. |
| Akış | `get_proposal` | Önerinin durumunu ve sonucunu döner. |

- Tanım, okuma ve yazma araçlarının adları Frappe'nin hazır araçlarıyla aynıdır. Modeller bu adları tanır.
- `get_doctype_schema` her alan için ad, tür, etiket, seçenek, zorunluluk ve açıklama döner. Kullanıcının o alanı okuyup yazamadığını da döner.
- Yazma aracı girdiyi çağrı anında tanıma göre doğrular. Bilinmeyen alan reddedilir.
- Araç listesi kullanıcıya göre daralır. Örneğin yönetim araçları yalnız yönetici rolüne görünür (G-84).
- Her araç MCP işaretini taşır. Okuma araçları `readOnlyHint` taşır. Silme ve iptal `destructiveHint` taşır.
- Ham SQL, ham Python, kabuk ve `call_method` aracı yoktur.

### Yazmaya kapalı DocType'lar

Bazı DocType'lar kod ya da kimlik bilgisi taşır. Genel yazma araçları bunlara yazamaz.

- Bazı DocType'lar kod taşır. Örneğin “Server Script”, “Client Script” ve sorgu taşıyan “Report” böyledir. Bunlara yazmak kod çalıştırma yolu açar (kural 5).
- Bazı DocType'lar kimlik bilgisi taşır. Örneğin “OAuth Bearer Token” böyledir. Bunlar okunmaz ve yazılmaz.
- Bazı DocType'lar yönetim kaydıdır. Örneğin “Custom Field”, “Role” ve izin kayıtları böyledir. Bunlar yalnız yönetim araçlarıyla değişir.
- “AI Action Log” ve “AI Action Proposal” katmanın kendi kayıtlarıdır. Bunlar yapay zekâ yoluyla değişmez.

Frappe çatısının kendi DocType'ları da genel yazma araçlarına kapalıdır. Bunlar ayar, kod ya da sistem kaydıdır. Çatıdan yalnız beş DocType açıktır: “ToDo”, “Note”, “Event”, “Contact” ve “Address”. Uygulamaların ve kullanıcıların kendi DocType'ları açıktır. Bu kural listeden güvenlidir. Çatıya yeni bir sistem DocType'ı gelirse kendiliğinden kapalı kalır.

Tam liste kodda tek yerde durur. Dosya `yapay_zeka/policy.py` dosyasıdır. Testler listeyi sınar.

### Uygulama araçları (`ai_tools`, G-105)

Uygulama `hooks.py` dosyasına `ai_tools` satırı ekler. Satır bir işlevin yolunu verir. İşlev araç bildirimlerini döner.

Her bildirim şunları taşır:

- ad ve İngilizce açıklama,
- girdi modeli, yani bir `pydantic` sınıfının yolu,
- tür: okuma ya da yazma,
- gereken roller,
- yıkıcı mı ve ücretli mi işaretleri,
- işi yapan işlevin yolu,
- yazma aracında önizleme üreten işlevin yolu.

Katman bildirimi yüklerken doğrular. Önizleme işlevi olmayan yazma aracı reddedilir. Adı çakışan araç reddedilir. Girdisinde `confirm` gibi onay alanı olan araç reddedilir.

Uygulama aracının adı `<uygulama>_<araç>` biçimindedir. Uygulama aracı da aynı onay ve günlük yolundan geçer.

Tek tık akışları (Prompts) bu işte yoktur. O iş Rail 5'e kalır.

## 5. Kimlik nasıl taşınır (G-148)

İki ayrı kimlik türü vardır. Katman her istekte türü belirler ve günlüğe yazar.

### İnsan oturumu

- İnsan panelde Keycloak ile giriş yapar. Tarayıcı Frappe oturum çerezini ve CSRF belirtecini taşır.
- Onay verme, reddetme ve aracı belirteci alma yalnız bu kimlikle yapılır.
- İstek `Authorization` başlığı taşıyorsa insan oturumu sayılmaz.
- Yazan insan isteği CSRF belirteci ister. CSRF belirteci, isteğin kendi sayfamızdan geldiğini kanıtlayan değerdir. Frappe bu denetimi oturumda belirteç yoksa atlar (`frappe/auth.py:92`). Katman belirteci olmayan oturumu reddeder.

### Aracı belirteci

Aracı belirteci, ajan servisinin kullanıcı adına kullandığı kısa ömürlü anahtardır.

1. Panel, insan oturumuyla `platform_core.api.ai.issue_agent_token` ucunu çağırır.
2. Site rastgele bir belirteç üretir. Belirtecin yalnız SHA-256 özeti saklanır.
3. Kayıt Frappe'nin önbelleğinde süreli durur. Süre dolunca kayıt kendiliğinden silinir. Zamanlanmış temizlik gerekmez (D-6).
4. Ajan servisi belirteci `Authorization: Bearer` başlığıyla gönderir.
5. `auth_hooks` kancasındaki bağdaştırıcı belirteci doğrular. Kanca Frappe'de hazırdır (`frappe/auth.py:756`).
6. Doğrulama geçerse istek o kullanıcının kimliğiyle sürer.

Belirtecin sınırları şunlardır:

| Sınır | Değer |
| --- | --- |
| Ömür | 300 saniye. Sözleşmedeki erişim belirteci süresiyle aynıdır. |
| Çağrı sayısı | En çok 20 araç çağrısı. Sonraki çağrı reddedilir. |
| Geçerli adres | Yalnız MCP ucu. Öteki adreslerde belirteç yok sayılır. |
| Bağlı oturum | Belirteci alan Frappe oturumu. Oturum kapanınca belirteç de geçersiz olur. |
| Hedef | Tek site ve tek servis adı. Servis adı ayardan gelir. |
| Yetki | Okuma ve öneri açma. Onay veremez. |

- Belirteç yalnız bu sitede geçer. Kayıt bu sitenin önbelleğindedir.
- İstek `cmd` alanı taşıyorsa belirteç kimliğe çevrilmez. Frappe bu alanla yolu yok sayar ve başka işlevi çalıştırır (`frappe/app.py:121`). Bağımsız inceleme bu açığı buldu. Test bu yolu sınar.
- Önbellek temizlenirse belirteçler geçersiz olur. Bu güvenli yöndür.
- İstek hem oturum çerezi hem belirteç taşıyorsa reddedilir. Sözleşmenin 3. bölümü aynı kuralı koyar.

### Bu turda kabul edilmeyen kimlikler

MCP ucu bu turda API anahtarını ve OAuth belirtecini kabul etmez. Bu kimlikler uzun ömürlüdür ve G-148 sınırlarını taşımaz.

Bu bir yorumdur. G-148 “yeniden kullanım reddedilir” der. Biz bunu şöyle yorumladık: belirteç süresi ve çağrı sınırı içinde kullanılır, sonra reddedilir. Her çağrıya yeni belirteç istemek ajan turunu çalışmaz kılar.

Sağlayıcıdan bağımsızlık protokol düzeyinde sağlanır. Bearer başlığı gönderebilen her MCP istemcisi bağlanabilir.

Bu konu `BORC(scale)` etiketli bir teknik borçtur. Dış MCP istemcileri için OAuth 2.1 girişi yoktur. Frappe 16 gereken uçları taşır (`frappe/integrations/oauth2.py:294`). Sorumlu platform-core-yz işidir. Dış istemci ihtiyacı doğunca bu borç kapanır.

## 6. Yetki eşitliği nasıl sağlanır (G-85)

Araçlar kullanıcının kimliğiyle çalışır. Ajan servisinin kendi hesabı yoktur.

- Tek kayıt okuma `doc.check_permission("read")` çağırır. Sonra `doc.apply_fieldlevel_read_permissions()` çağırır. REST ucu da aynı iki çağrıyı yapar (`frappe/api/v2.py:68` ve `:69`).
- Liste `frappe.get_list` ile okunur. Bu işlev kullanıcı izinlerini ve paylaşımı uygular.
- Yazma `doc.insert`, `doc.save`, `doc.submit`, `doc.cancel` ve `frappe.delete_doc` ile yapılır. Bu yollar izin ve doğrulama çalıştırır.
- Rapor Frappe'nin rapor çalıştırma işleviyle çalışır. İşlev rapor iznini denetler.
- Araç kodunda `ignore_permissions`, `frappe.get_all` ve `frappe.db.sql` yoktur. Bir test bu sözcükleri araç kodunda arar.
- Liste aracı istenen alanları ve süzgeç alanlarını denetler. Kullanıcının okuyamadığı alan reddedilir. Böylece süzgeçle değer tahmini yapılamaz.
- İzin önizlemede denetlenir. Onaydan sonra, yazmadan hemen önce yeniden denetlenir.

Tek istisna katmanın kendi kayıtlarıdır. “AI Action Log” ve “AI Action Proposal” kayıtlarını sistem yazar. Son kullanıcının bu türlere yazma izni yoktur. Bu yüzden yalnız bu iki kayıt `ignore_permissions` ile yazılır (G-4). Hedefi kullanıcı seçmez. İstisna tek dosyada durur ve test bunu sınar.

Testler gerçek HTTP isteğiyle şunları doğrular (D-6):

- Kısıtlı kullanıcı başkasının kaydını okuyamaz.
- İzin seviyesi yüksek alan dönmez.
- İzinsiz DocType reddedilir.
- Her ret “AI Action Log” kaydına `denied` olarak düşer.

## 7. Önizleme ve onay nasıl çalışır (G-86)

Model hiçbir zaman doğrudan yazamaz. Yazma araçları yalnız öneri açar.

### Akış

1. Model bir yazma aracını çağırır. Örneğin `update_document` çağırır.
2. Sunucu girdiyi ve kullanıcının iznini denetler.
3. Sunucu önizleme üretir. Önizleme her alanın eski ve yeni değerini gösterir.
4. Sunucu bir “AI Action Proposal” kaydı açar. Kayda hiçbir şey yazılmaz.
5. Model `approval_required` durumunu, öneri kimliğini ve önizlemeyi alır.
6. Panel öneriyi insana gösterir. İnsan önizlemeyi okur.
7. İnsan `platform_core.api.ai.approve_proposal` ucunu çağırır. İstek öneri kimliğini ve önizleme özetini taşır.
8. Sunucu denetimleri yapar ve işi o istekte yürütür.
9. Model sonucu `get_proposal` aracıyla okur.

Onay ayrı bir belirteç üretmez. Onay isteğinin kendisi tek kullanımlık yürütmedir. Böylece model onayı ele geçirip kullanamaz.

### Onay anındaki denetimler

Sunucu şu denetimleri sırayla yapar. Biri başarısız olursa iş yürümez.

| Denetim | Ret nedeni |
| --- | --- |
| İstek insan oturumundan mı geliyor? | Aracı belirteciyle gelen onay reddedilir. |
| Onaylayan, öneriyi açan kullanıcı mı? | Başka kullanıcının onayı reddedilir. |
| Öneri `pending` durumunda mı? | İkinci kullanım reddedilir. |
| Süre doldu mu? | Öneri 10 dakika geçerlidir. Sonrası reddedilir. |
| Gönderilen özet kayıttaki özetle aynı mı? | Farklı önizlemeye verilen onay reddedilir. |
| Kaydın `modified` değeri önizlemedekiyle aynı mı? | Kayıt değiştiyse yeni önizleme istenir. |
| Kullanıcının izni hâlâ var mı? | İzin kalktıysa iş reddedilir. |
| Aynı hedefte sonucu bilinmeyen iş var mı? | Kör tekrar yapılmaz. |

Özet bir SHA-256 değeridir. Özete şunlar girer: kullanıcı, site, araç, hedef kayıt, kaydın `modified` değeri, girdi ve önizleme. Özete rastgele bir değer de girer. Rastgele değer yüzünden model özeti hesaplayamaz. Özet yalnız insan ucundan döner. Model öneri kaydını genel araçlarla okuyamaz.

Başka kullanıcının onayı 403 alır. Yanıt öneriyi taşımaz. Önizleme o kullanıcının verisidir.

### Yürütme ve “unknown” kuralı

1. Sunucu aynı hedefin bütün öneri satırlarını veritabanında kilitler. Yarışan ikinci onay bekler. Kilit birden çok sunucuda da çalışır.
   - Kilit sırası her istekte aynıdır. Sunucu önce hedefin önerilerini, sonra bu öneriyi kilitler.
   - MariaDB, yarışan bir onayın değiştirdiği satırda kilitli okumayı reddedebilir (`frappe/database/mariadb/database.py:27`). O zaman sunucu işlemi geri alır ve denetimleri güncel veriyle yeniden yapar. En çok dört kez dener.
   - Yarış testleri bu durumu sınar. İki onay aynı anda gelir ve yalnız biri yürür.
2. Sunucu öneriyi `consumed` yapar ve sonucu `unknown` yazar. Bu yazıyı hemen kesinleştirir.
3. Sunucu işi yürütür.
4. İş başarılıysa sonuç `succeeded` olur. İş hata verirse yazılar geri alınır.
   - Hata katmanın kendi denetiminde oluştuysa sonuç `failed` olur. Bu denetim yalnız katmanın kodudur ve kayıt yöntemi çağırmaz.
   - Katmanın denetimi bittikten sonraki her hata `unknown` olur. Bu bölümde Frappe'nin kayıt yöntemleri ve kancaları çalışır. Uygulama aracının bütün işlevleri de bu bölümdedir.
   - Sınır kodda tek yerdedir: `proposals.py` içindeki `_execute` işlevi.
5. Süreç arada ölürse sonuç `unknown` kalır.

İkinci adımdaki erken kesinleştirme bilinçli bir istisnadır (V-2). Bu yazı olmadan ölen iş iz bırakmaz. Tek kullanım kuralı da bu yazıya dayanır.

Sonucu `unknown` olan hedefe yeni öneri açılmaz. İnsan `resolve_proposal` ucuyla durumu kapatır. Sonra yeni öneri açılabilir.

### Öteki kurallar

- Hiçbir araç şemasında `confirm`, `approved` ya da `force` alanı yoktur. Bu alanlar gelirse çağrı reddedilir.
- Modelde onay aracı yoktur.
- Her öneri tek iştir. Zincirli yazma yoktur.
- Süre zamanlanmış işle değil, okuma anında denetlenir (D-6).
- İnsan öneriyi `reject_proposal` ucuyla reddedebilir.
- Risk sınıfını model belirlemez. Sınıf aracın tanımından gelir.
- Yerleşik yazma araçları kaydı yürütmede satır kilidiyle okur. Sürüm önizlemedekinden farklıysa yazmaz.
- Okuma aracı kalıcı yazı bırakamaz. Katman okuma aracından sonra işlemi geri alır.

## 8. “AI Action Log” hangi alanları tutar (G-64)

Her araç çağrısı bir kayıt açar. Ret de kayıt açar. Onay, ret ve yürütme adımları da ayrı kayıt açar.

| Alan | İçerik |
| --- | --- |
| `user` | İşlemi yapan kullanıcı |
| `principal` | Kimlik türü: insan oturumu ya da aracı belirteci |
| `session_id` | İstemcinin verdiği konuşma kimliği |
| `client_info` | MCP istemcisinin adı ve sürümü. Güvenilmeyen metindir. |
| `stage` | Adım: çağrı, önizleme, onay, ret, yürütme ya da kapatma |
| `tool` | Araç adı |
| `tool_class` | Araç türü: tanım, okuma, yazma, yönetim ya da uygulama |
| `target_doctype` | Hedef DocType |
| `target_name` | Hedef kaydın adı |
| `args_hash` | Girdinin SHA-256 özeti |
| `decision` | Karar: `allowed`, `denied` ya da `error` |
| `deny_reason` | Ret nedeninin kodu. Örneğin `permission` ya da `expired`. |
| `proposal` | Bağlı öneri kaydı |
| `approval_state` | Önerinin o andaki durumu |
| `result` | Sonuç: `succeeded`, `failed`, `unknown` ya da boş |
| `version` | Yazmanın ürettiği “Version” kaydı |
| `ip` | İsteğin geldiği adres |
| `duration_ms` | Çağrının süresi |

- Zaman, Frappe'nin hazır `creation` alanındadır.
- Günlük girdinin kendisini tutmaz. Yalnız özetini tutar. Böylece günlüğe kişisel veri ve gizli değer girmez.
- Günlük yalnız eklenir. Kayıt değişmez ve silinmez. Controller bunu engeller.
- Günlüğü yalnız “System Manager” rolü okur.
- Ret durumunda istek hata vermez. Araç `isError` taşıyan sonuç döner. Böylece günlük yazısı geri alınmaz.
- Beklenmeyen hatada sunucu yazıları geri alır. Sonra günlüğü yazar ve kesinleştirir.

### G-64 ile fark

G-64 `model`, token ve maliyet alanlarını da sayar. Bu alanlar bu kayıtta yoktur.

- Bu katman model çağırmaz. Hangi modelin konuştuğunu bilemez.
- Token ve maliyet “AI Usage Log” kaydındadır. O kaydın sahibi `model_gecidi` modülüdür.
- İki kayıt `session_id` değeriyle eşleşir.

Günlüğün saklama süresi 365 gündür (Rail 5). Eski kaydı elle başlatılan bir komut siler. Komut `retention.purge` işlevidir. Komutun HTTP ucu `purge_logs`, aracı `purge_action_log` olur. Zamanlanmış iş yoktur (D-6). Sonucu bilinmeyen öneriler silinmez.

Günlük kullanıcı adını ve adresini tutar. Bunlar kişisel veridir. Proje kaydının “Kişisel veri” bölümüne eklenmelidir (G-15). Bunu raporda isteyeceğiz.

## 9. Gizli alanlar nasıl dışarıda kalır

Gizli alan tek bir işlevde belirlenir. Bütün araçlar bu işlevi kullanır.

Bir alan şu durumlarda gizlidir:

1. Alanın türü “Password” olur.
2. Alanın adı gizli bilgi kalıbına uyar. Örneğin `api_key`, `api_secret`, `client_secret`, `token` ve `private_key` böyledir.
3. Alan, kimlik bilgisi taşıyan bir DocType içindedir.

Gizli alan için kurallar şunlardır:

| Yer | Davranış |
| --- | --- |
| Tanım | Alanın adı ve açıklaması görünür. Alan `secret: true` işaretini taşır. |
| Okuma ve liste | Değer hiç dönmez. Yıldızlı maske de dönmez. |
| Süzgeç ve sıralama | Gizli alanla süzme ve sıralama reddedilir. |
| Yazma | Gizli alana yazma reddedilir. İnsan bu değeri ekrandan girer. |
| Önizleme ve günlük | Gizli değer hiç yer almaz. |
| Rapor | Gizli alan adını taşıyan sütun sonuçtan çıkarılır. |

Yazmanın reddi bilinçlidir. Model gizli değeri yazarsa değer model sağlayıcısından geçer. Bu yüzden anahtarı insan girer.

Model geçidinin “AI API” kaydı bu kurala örnektir. Yapay zekâ kaydın adresini ve önceliğini değiştirebilir. Gizli anahtarı okuyamaz ve yazamaz.

İzin seviyesi yüksek alanlar ayrı bir konudur. Onları Frappe'nin kendi alan izni çıkarır (6. bölüm).

## 10. Uçlar

Bütün uçlar `platform_core/api/ai.py` dosyasındadır. Dosya ince kalır. İş kuralı `yapay_zeka` modülündedir.

| Yol | Yöntem | Kimlik | İşi |
| --- | --- | --- | --- |
| `platform_core.api.ai.mcp` | POST | İnsan oturumu ya da aracı belirteci | MCP ucu. Araç listesi ve araç çağrısı. |
| `platform_core.api.ai.issue_agent_token` | POST | İnsan oturumu | Aracı belirteci üretir. |
| `platform_core.api.ai.list_proposals` | GET | İnsan oturumu | Kullanıcının önerilerini listeler. |
| `platform_core.api.ai.get_proposal` | GET | İnsan oturumu | Bir önerinin önizlemesini ve özetini döner. |
| `platform_core.api.ai.approve_proposal` | POST | İnsan oturumu | Öneriyi onaylar ve yürütür. Yıkıcı olabilir. |
| `platform_core.api.ai.reject_proposal` | POST | İnsan oturumu | Öneriyi reddeder. |
| `platform_core.api.ai.resolve_proposal` | POST | İnsan oturumu | Sonucu bilinmeyen öneriyi kapatır. |
| `platform_core.api.ai.purge_logs` | POST | İnsan oturumu ve yönetici rolü | Saklama süresi dolan kayıtları siler. Yıkıcıdır. Varsayılan yalnız sayar. |

Ayrıntılı biçim `contracts/platform_core-yapay-zeka.openapi.yaml` dosyasına yazılır. Bu dosya ikinci kontrol noktasında, koddan önce yazılır.

## 11. Yönetim araçları

Yönetim araçları yalnız “System Manager” rolüne görünür. Her biri önizleme ve insan onayı ister. İşlevler rolü kendileri de denetler.

| Araç | İşi | Kullandığı Frappe yolu |
| --- | --- | --- |
| `add_custom_field` | DocType'a özel alan ekler. Açıklama zorunludur (D-9). | “Custom Field” kaydı |
| `set_field_property` | Alanın bir ayarını değiştirir. Örneğin zorunluluğu değiştirir. | “Property Setter” kaydı |
| `set_role_permission` | Rolün bir DocType'taki iznini değiştirir. | Frappe'nin izin yöneticisi işlevleri |
| `assign_role` | Kullanıcıya rol verir. | Kullanıcı kaydının `add_roles` işlevi |
| `remove_role` | Kullanıcıdan rol alır. | Kullanıcı kaydının `remove_roles` işlevi |
| `purge_action_log` | Saklama süresi dolan günlükleri siler. | `retention.purge` komutu |

- Alan ayarı aracı yalnız 13 ayarı kabul eder. İfade çalıştıran ayarlar listede yoktur. Örneğin `depends_on` ve `fetch_from` reddedilir.
- Korunan roller yapay zekâ yoluyla verilmez ve alınmaz. Bunlar “Administrator”, “System Manager”, “Guest”, “All” ve “Desk User” rolleridir.
- “Guest” ve “All” rollerinin izinleri yapay zekâ yoluyla değişmez. Bu roller herkesi kapsar.
- Model geçidinin kayıtları olağan DocType'lardır. Onları genel yazma araçları değiştirir. Yetkiyi o DocType'ların izinleri belirler.

### Elle başlatılan komutlar

Bu katmanın tek komutu günlük temizliğidir. Komut üç yoldan başlar: `bench execute`, HTTP ucu ve araç.

Öteki modüller kendi komut uçlarını `ai_tools` kancasıyla araç olarak bildirir. Bildirim `yapay_zeka` modülünü içe aktarmayı gerektirmez. Böylece bağımlılık yönü korunur. Bu turda öteki modüllerin kodu bu dalda yoktur. Onların bildirimi kendi işlerine kalır.

## 12. Bağımsız inceleme

Kod bağımsız bir inceleyiciye okutuldu. İnceleyici yalnız okudu, komut çalıştırmadı. Bulgular ve sonuçları şunlardır:

| Bulgu | Sonuç |
| --- | --- |
| Aracı belirteci `cmd` alanıyla başka işlevi çalıştırabiliyordu. | Kapatıldı. Test eklendi. |
| “unknown” denetimi iki sunucuda yarışabiliyordu. | Dosya kilidi yerine veritabanı satır kilidi geldi. |
| Kapalı DocType listesi eksikti. | Çatı DocType'ları toptan kapandı. Okuma listesi ve gizli ad kalıbı genişledi. |
| Başkasının onay denemesi öneriyi döndürüyordu. | Artık 403 döner. Test eklendi. |
| Bozuk bir `ai_tools` bildirimi ucu durduruyordu. | Bozuk bildirim yalnız kendini düşürür. Test eklendi. |
| Model onay özetini hesaplayabiliyordu. | Özete rastgele değer girdi. Öneri kaydı modele kapandı. CSRF belirteci zorunlu oldu. |
| Yürütme, kayıt arada değişirse üstüne yazabiliyordu. | Yerleşik araçlar sürümü satır kilidiyle yeniden denetler. |
| Hata veren uygulama aracı `failed` yazılıyordu. | Artık `unknown` kalır. Ham hata metni modele dönmez. |
| Bilinmeyen araç çağrısı günlüğe düşmüyordu. | Artık düşer. |
| Okuma diye bildirilen araç yazabiliyordu. | Okuma aracından sonra işlem geri alınır. Test eklendi. |

Açık kalan, bilinçli bırakılan noktalar şunlardır:

- Misafir ve bilinmeyen belirteç retleri günlüğe yazılmaz. Yazılsaydı kimliksiz istekler günlüğü doldururdu.
- Günlük kaydı Frappe ekranından ve kayıt yolundan değişmez. Veritabanına doğrudan erişen yönetici yine değiştirebilir. Bu, uygulama katmanının sınırıdır.
- Kayıt yoksa `not_found`, izin yoksa `permission` döner. Frappe'nin REST ucu da aynı ayrımı yapar.
- Her giriş yapmış kullanıcı alt tablo tanımını okuyabilir. Tanım veri değildir.
- Uygulama araçlarının yürütme işlevi sürüm denetimini kendisi yapar. Katman önizlemeyi kilit altında yeniden çalıştırır.
- Uygulamaların kendi DocType'ları genel yazma araçlarına açıktır. Sahibi hassas DocType'ı kancayla kapatır. Bu, D-9 kararının sonucudur.
- Rapor, kaynağı belli olmayan gizli değeri yanlış adla döndürürse katman bunu tanıyamaz. Rapor yazarı sütunu işaretlemelidir.

### İkinci inceleme: Codex

İkinci bağımsız incelemeyi başka bir model yaptı. Bir engelleyici ve beş önemli bulgu verdi. Her bulgu için önce saldırıyı gösteren test yazıldı. Test başarısız oldu. Sonra kod düzeltildi. Testler `tests/test_codex.py` dosyasındadır.

| Bulgu | Düzeltme |
| --- | --- |
| B1. Alt tablo satırı başka kayda ait olabiliyordu. Satır alanında izin aranmıyordu. | Satır adı yalnız aynı ana kaydın satırı olabilir. Yeni satırın adı istemciden alınmaz. Satır alanında da yazma izni aranır. Denetim önizlemede ve yürütmede çalışır. |
| B2. Rapor, “Password” türündeki sütunu modele verebiliyordu. | Sütunun türü, adı, etiketi ve kaynak DocType'taki alanı denetlenir. |
| B3. Kalıcı etki bırakan hata `failed` yazılıyordu. | Yürütme yazdıysa ya da işlemi kesinleştirdiyse sonuç `unknown` kalır. |
| B4. Yönetim araçları araya giren değişikliğin üstüne yazabiliyordu. | Araç asıl hedefi kilitler. Sürümü yazmadan hemen önce yeniden karşılaştırır. |
| B5. Aracı belirteci süresi dolmuş oturuma bağlı kalabiliyordu. | Oturumun hareketsizlik süresi ve bitiş zamanı Frappe'nin ölçütleriyle denetlenir. |
| B6. Bazı insan çağrıları ve retleri günlüğe düşmüyordu. | Belirteç üretimi, öneri okuma, öneri listeleme ve bütün retler günlüğe düşer. |

Bu incelemede Frappe'nin şu davranışları imajdaki kaynakta doğrulandı:

- Frappe, gönderilen satır adını korur ve satıra yeni ana kaydı yazar (`frappe/model/document.py:2477`).
- Frappe, yeni kayıtta alt tablonun alan iznini denetlemez (`frappe/model/document.py:1303`).
- Frappe'nin izinli alan listesi tablo alanlarını saymaz. Bu yüzden katman alt tabloyu önce hiç döndürmüyor ve yazdırmıyordu. Artık tablo alanı kendi izin seviyesine göre okunur ve yazılır.
- Frappe oturumu hareketsizlik süresi ve `session_end` değeriyle sınar (`frappe/sessions.py:363`).

Aynı turda kendi başlattığım ikinci inceleme de şu ek düzeltmeleri getirdi:

- Rol izni önizlemesi, yeni kuralın getirdiği okuma iznini de gösterir.
- Kod ve yönetim DocType'larının izinleri yapay zekâ yoluyla değişmez. Örneğin “Server Script” ve “User” böyledir.
- “Desk User” rolünün izinleri değişmez. “Script Manager” gibi dört rol daha verilemez.
- Eski değerleri taşıyan DocType'lar okumaya kapandı. Örneğin “Version” ve “Deleted Document” böyledir.
- Uygulama bir DocType'ı `ai_write_closed_doctypes` kancasıyla yazmaya kapatabilir.
- Hedefi olmayan işte de “unknown” engeli çalışır. Anahtar araç ve girdiden üretilir.
- CSRF başlığı her yazan insan isteğinde katmanın kendisi tarafından karşılaştırılır.
- Aracı belirtecinin çağrı hakkı bilinmeyen araç adında da düşer.

### Üçüncü tur: Codex'in ikinci incelemesi ve HRMS TR incelemesi

Codex'in ikinci incelemesi B1, B2, B4 ve B5 bulgularını kapalı buldu. B3 ve B6 kısmen açık kaldı. Orkestratör iki bulgu için karar verdi. Kararlar şöyle uygulandı:

- **B3.** Sonuç yalnız bir durumda `failed` olur. Hata katmanın kendi denetiminde oluşmuştur. Katmanın denetimi bittikten sonraki her hata `unknown` olur. `ToolDenied` türü de buna dahildir.
- Her yerleşik yazma aracı iki işleve ayrıldı. `prepare_*` işlevi ön denetimi yapar ve kayıt yöntemi çağırmaz. `write_*` işlevi kayıt yöntemini çağırır.
- Sınır kodda tek yerdedir. Yer `proposals.py` içindeki `_execute` işlevinde “WRITE BOUNDARY” yorumuyla işaretlidir.
- **B6.** Kimliği bilinen üç ret daha günlüğe düşer. Birincisi API anahtarıyla gelen MCP isteğidir. İkincisi süresi dolmuş oturuma bağlı belirteçtir. Üçüncüsü çerezle birlikte gelen belirteçtir. Kayıt hata yanıtından önce kesinleştirilir. Bilinmeyen belirteç ve misafir istisna kalır.

HRMS TR incelemesi iki konu getirdi:

- Uygulama aracının önizlemesi `frappe.ValidationError` verirse araç `invalid_arguments` döner ve ret günlüğe düşer. Onay anında verirse öneri `rejected` olur. Önceden öneri `pending` kalıyor ve yanıt 417 oluyordu.
- Uygulama aracı `prepare` ve `versioned` bildirebilir. `versioned` bildirirse katman hedef satırı kilitler, önizlemeyi yeniden çalıştırır ve sürümü karşılaştırır.
- Uygulama aracının `prepare` işlevi katmanın denetimi sayılmaz. O işlev başladıktan sonraki her hata `unknown` olur. Bunu Codex'in üçüncü incelemesi buldu.
- Rapor aracı raporu çalıştırmadan önce erişim motorunun rapor kapısını çağırır. Kapı `platform_core.erisim.reports.guard` işlevidir. Kapı kurulu değilse rapor aracı kapalı kalır.

Aynı turda araçların sonuç şeması sözleşmeye yazıldı (D-1). Şema `x-mcp-results` bölümündedir. Araç listesi aynı şemayı `outputSchema` olarak yayımlar. Bir test kodu sözleşmeye bağlar.

### Dördüncü tur: Codex'in üçüncü incelemesi

Üçüncü inceleme engelleyici bulmadı. Dört konu açık kaldı ve kapatıldı:

- **B3.** `failed` sonucu yalnız katmanın kendi denetimi içindir. Uygulama aracının `prepare` işlevi sınırın öte yanına alındı.
- **B6.** Kimliği bilinen kullanıcının erken MCP reddi de günlüğe düşer. Örneğin yasak `Origin` başlığı böyledir. Kayıt hata yanıtından önce kesinleştirilir.
- **Y1.** `versioned` bildiren araç önizlemede üç değeri vermek zorundadır: `target_doctype`, `target_name` ve `target_version`. Biri eksikse araç `invalid_preview` döner. Denetim öneri açılmadan önce, onay anında ve yürütmeden hemen önce yapılır.
- **Y2.** Bu notun 7. bölümündeki eski sonuç kuralı yeni kuralla aynı yapıldı.

Proje sahibi yalnız Frappe 16'yı hedefledi (D-15). Bu katman baştan beri yalnız Frappe 16 ile yazıldı. Katman Frappe 16'nın hazır MCP protokol modüllerini ve izin yöneticisi işlevlerini kullanır.

### Beşinci tur: boşluk analizi ve gerçek MCP istemcisi

Bağımsız boşluk analizi şu konuları getirdi. Hepsi testle kapatıldı:

- `assign_role` aracı, son kullanıcıya masaüstü rolü önermez. Frappe 16 böyle bir kullanıcıyı “System User” yapar (`frappe/core/doctype/user/user.py:445`).
- “Platform Identity Link” yapay zekâ yazmasına tümüyle kapalıdır. Yönetim araçları da ona dokunamaz.
- “Access Rule” yönetim sınıfındadır. Genel yazma araçları ona yazamaz.
- Katmanın istek içindeki tek kesinleştirme satırı `access.commit_own_writes` işlevindedir. Ret kaydından önce bekleyen yazılar geri alınır. Onay, bekleyen yazı taşıyan işlemde çalışmaz.
- İnsanın öneri listesi tek ve sınırlı sorguyla okunur.
- Katmanın kendi kayıtlarını yazarken açtığı izin bayrağı `finally` içinde geri döner.
- Rapor aracı en çok `limit` kadar satır okur. Arka planda hazırlanan raporu istek içinde çalıştırmaz.
- Rapor kapısı erişim modülünün açık yolundan çağrılır: `platform_core.erisim.api.report_guard`.

Masaüstü rolü kuralı kimlik modülündeki kuralla aynı sonucu verir, ama ortak bir işlev kullanmaz. Kimlik modülünün açık yolunda böyle bir işlev henüz yoktur. Ortak işlev açılınca iki yer ona bağlanmalıdır.

Rapor için bir sınır kalır. Frappe'nin rapor işlevi sonucun tamamını kendisi üretir. Katman rapor işlevinin içini sınırlayamaz. Katman yalnız kendi okuduğu ve kopyaladığı satırı sınırlar.

Resmî Python MCP istemcisiyle (sürüm 2.3.0) gerçek oturum açıldı. İstemci `2025-11-25` ve `2026-07-28` sürümleriyle bağlandı. Araç listesi, okuma aracı, öneri ve insan onayı çalıştı. Belirteçsiz istek, süresi dolmuş belirteç ve çerezle birlikte belirteç reddedildi. Oturum bir sözleşme hatası gösterdi: kimliksiz istek 401 değil 403 alıyor. Sözleşme düzeltildi.

### Altıncı tur: eksik işler listesi

`docs/gap-backlog.md` dosyasındaki sekiz madde kapatıldı (O-28):

1. Öneri zamanları saat farkıyla ISO 8601 biçiminde döner. Örneğin `2026-11-22T12:41:57+03:00`.
2. Süresi dolmuş oturum 401, oturumsuz istek 403 alır. Sözleşme bütün uçlarda 401 yanıtını yazar. Kaynak `frappe/__init__.py:483` satırıdır.
3. Önizleme saklanmadan önce şemayla denetlenir. Değişiklik satırının anahtarları `fieldname`, `label`, `old` ve `new` olur. Uymayan önizleme `invalid_preview` döner.
4. `ai_write_closed_doctypes` kancası sınanır. Kancadaki ve güvenlik listelerindeki her DocType'ın sitede var olduğu da sınanır.
5. Okuma sonuçları `as_of`, `site` ve `source` taşır. Öneri `created_at` taşır.
6. Okuma sonucunun satır ve bayt sınırı vardır. Alt tablo en çok 200 satır döner. Sonucun verisi en çok 262.144 bayttır. Sınır aşılınca `truncated` doğru olur.
7. Öneri listesi veritabanında süzülür ve sayfalanır. Uç `start` parametresini alır ve `has_next_page` döner.
8. GET isteği günlüğe yalnız reddi yazar. Başarılı okuma satır yazmaz ve kesinleştirme yapmaz.

Sekizinci madde, B6 bulgusuyla gelen bir kuralı daraltır. Önceden başarılı öneri okuması da günlüğe düşüyordu. Artık düşmüyor. Neden şudur: Oturum çerezi başka siteden gelen GET isteğiyle de gider. Böyle bir istek günlüğü doldurabilirdi.

İki DocType'a açıklama yazıldı. Yapay zekâ uygunluk kapısı bunu istedi (D-9).

### Yedinci tur: Codex'in dördüncü incelemesi

Codex dördüncü incelemede bir engel, dört önemli ve iki küçük bulgu yazdı. Katman hepsini düzeltti. Her düzeltmenin testi `tests/test_fourth_review.py` dosyasındadır.

- **Onay önizlemenin tamamına bağlıdır.** Katman öneriyi açarken önizlemenin ve hedefin özetini `preview_digest` alanına yazar. Katman onayda önizlemeyi yeniden üretir ve özeti karşılaştırır. Özet farklıysa katman hiçbir şey yürütmez ve `document_changed` döner. O zaman yeni öneri ve yeni insan onayı gerekir. Bu kural sürümlü ve sürümsüz araçta aynıdır.
- **Aynı karşılaştırma yürütmeden hemen önce yinelenir.** Bu denetim katmanın kendi ön denetimidir ve yazma sınırından öncedir. Bu yüzden sonuç `failed` olur.
- **Sürümlü uygulama aracında katman saklanan hedefi kilitler.** Katman hedef satırın `modified` değerini aynı kilitli okumadan alır. Kilitli okuma en son kaydedilmiş satırı verir. Kilitsiz okuma tekrarlanabilir okuma kipinde eski satırı gösterebilir. Bu yüzden katman karşılaştırmada kilitsiz okumanın sonucunu kullanmaz.
- **Önizleme yayımlanan şemaya uyar.** Katman önizlemeyi `tools/results.py` dosyasındaki şemayla denetler. Örneğin `label` alanı sayı ise öneri açılmaz ve yanıt `invalid_preview` olur.
- **Bayt sınırı sonucun tamamını sayar.** Rapor aracı sütun tanımlarını da sayar. Sütunlar tek başına sınırı aşarsa sütun ve satır listesi boş döner. `get_doctype_schema` alan listesini sınırda keser ve `truncated` değerini döner.
- **Kesilen liste devam yerini söyler.** `list_documents` yanıtı `next_start` alanını taşır. Son sayfada bu alan boştur. İlk kayıt tek başına sınıra sığmazsa katman o kaydı kırparak döner. Böylece istemci aynı boş sayfayı yeniden almaz.
- **Öneri listesinin başlangıç değeri sınırlıdır.** `start` en çok 10.000 olabilir. Daha büyük değer 417 döner.
- **Model adı testi geri geldi.** Test model ailesi adlarını düz yazıyla taşımaz, özetleriyle arar. Uygunluk kapısı `backend` dalına birleşince bu test kaldırılabilir.
- **Günlüğe yazılmayanlar sözleşmededir.** Başarılı GET isteği, kimliği bilinmeyen istek ve Frappe'nin uçtan önce reddettiği istek günlüğe yazılmaz. Sonuncusunun kanıtı web sunucusunun erişim günlüğüdür.

Veritabanı MariaDB 11.8.9 sürümüdür. Yalıtım kipi `REPEATABLE-READ` ve `innodb_snapshot_isolation` ayarı açıktır. Bu ayar açıkken veritabanı, anlık görüntüden sonra değişmiş satırı kilitlemeyi reddeder. Katman bu ayara güvenmez ve kilitli okumanın sonucunu kullanır.

Aynı kalıp `tools/admin.py` dosyasında alan ayarı aracında da vardır. Araç “Property Setter” satırını kilitler, sonra önizlemeyi kilitsiz okur. Bu yer bu turda değişmedi. Açık iş olarak 14. bölüme yazıldı.

### Çeviri (O-21 ve O-23)

Katmanın yorumları, docstring'leri, iletileri ve OpenAPI açıklamaları İngilizcedir. Türkçe metin `translations/tr.csv` dosyasındadır. Her ileti `platform_core.yapay_zeka` bağlamını taşır. DocType etiketleri ve açıklamaları bağlam olarak DocType adını kullanır. Kuralı `tests/test_translations.py` sınar.

### Website User yöntemleri

Son kullanıcı panelde Website User olarak çalışır. Katmanın yedi ucu `website_user_allowed_methods` kancasındadır. `purge_logs` ucu listede yoktur, çünkü bu uç “System Manager” rolü ister. Kuralı `tests/test_website_user_methods.py` sınar.

## 13. Karar sitesiyle çelişkiler

| Konu | Karar sitesi | Bu karar | Neden |
| --- | --- | --- | --- |
| Onay biçimi | Rail 5, `confirm=true` ve `preview_hash` yazar. | `confirm` alanı yok. Onay insan ucundan gelir. | Sözleşmenin 10. bölümü `confirm` alanını yasaklar. |
| Kiracı MCP'si | G-84, `frappe_mcp` uygulamasını yazar. | Kendi ucumuz. | Depo arşivlendi. Hazır uç kuralları karşılamıyor. |
| Günlük alanları | G-64 model, token ve maliyet yazar. | Bu alanlar “AI Usage Log” kaydında. | Bu katman model çağırmaz. |
| Model adları | Rail 5 model adlarını yazar. | Kodda model adı yok. | Proje kaydı O-10 ve sözleşme kural 8. |

## 14. Doğrulanmayanlar

- `frappe/mcp` paketinin Frappe 16'da çalışıp çalışmadığı denenmedi.
- Gerçek bir MCP istemcisiyle oturum açılmadı. Testler istemciyi taklit edecek.
- Sürecin yürütme ortasında ölmesi testle denenmedi. Bu durumda sonuç `unknown` kalır. Kod okunarak incelendi.
- GitHub'daki `version-16` dalı 16.60.2 sürümündedir. İmajdaki sürüm 16.56.0'dır. Aradaki fark incelenmedi.
- Alan ayarı aracı “Property Setter” satırını kilitledikten sonra önizlemeyi kilitsiz okur. Tekrarlanabilir okuma kipindeki eski okuma olasılığı bu araçta testle denenmedi.
