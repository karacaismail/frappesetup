# Dış MCP istemcileri için OAuth tasarımı

22 Kasım 2026 Pazar günü hazırlandı. Bu belge uygulama planıdır.
OAuth varsayılan olarak kapalıdır. Kabul durumu proje kaydında tutulur.

MCP, yapay zekâ istemcisinin araç çağırdığı protokoldür.
OAuth, kullanıcının parolasını paylaşmadan erişim izni verdiği yöntemdir.
Bu plan, dış istemcinin Keycloak üzerinden kullanıcı adına bağlanmasını sağlar.

## Tasarım öncesindeki durum

Tasarım öncesinde MCP ucu, insan oturumunu ve aracı belirtecini kabul ediyordu.
Uç API anahtarını ve OAuth belirtecini reddediyordu.
Aracı belirteci 300 saniye yaşar. En çok 20 araç çağrısında kullanılır.
Bağlı Frappe oturumu kapanınca belirteç geçersiz olur.
İnsan onayı yalnız oturum çereziyle verilir.

Mevcut parçalar yeniden kullanılabilir:

| Parça | Sağladığı iş | Eksik iş |
| --- | --- | --- |
| `oidc_verify` | İmza, sağlayıcı, hedef, istemci ve süre denetimi | Frappe kullanıcısı ve oturum yaşamı |
| `kimlik.api.verify_mobile_token` | Telefon kimliğini doğrulama | MCP kapsamı ve MCP hedefi |
| `kimlik.sign_out` | Frappe oturumlarını kapatma | Dış MCP oturumunu kapatma sözleşmesi |
| `yapay_zeka.agent_token` | Kısa süre, çağrı sınırı ve insan ayrımı | Keycloak belirtecini kabul etme |

Kimlik modülünün açık arayüzü yalnız telefon belirtecini doğrular.
Bu işlev `mobile` kapsamını ve telefon kurulum başlığını ister.
MCP çağrısı telefon çağrısı gibi gösterilmez.

Realm dosyasında MCP istemcisi ve MCP kapsamı bulunmadı.
Kaynak `identity/keycloak/realm/platform-realm.json` dosyasıdır.
Mevcut istemciler kiracı, servis, Press, eşitleme ve telefon istemcileridir.

## Seçim ve sahipler

Keycloak izin sunucusu olur. Platform yalnız kendisine verilen belirteci doğrular.
Platform yeni bir OAuth sunucusu kurmaz. Yeni paket eklenmez.

1. `kimlik-realm` işi dış istemciyi ve kapsamı tanımlar.
2. `platform-core-kimlik` işi ortak MCP kimlik doğrulamasını sağlar.
3. `platform-core-yz` işi keşfi, araç erişimini ve çağrı sınırını bağlar.
4. `integration-e2e` işi gerçek Keycloak ile bütün akışı sınar.

Kimlik modülünün özel işlevleri yapay zekâ katmanına aktarılmaz.
Hesap silme ve oturum kapatma kuralları ikinci kez yazılmaz.

## Kimlik modülünden gereken açık işlev

Önerilen yol `platform_core.identity.api.verify_mcp_token` olur.
İşlev yalnız belirteci alır. Hedef ve izinli istemciler sunucu ayarından gelir.
İstek bu değerleri belirleyemez.

```python
verify_mcp_token(token: str) -> dict
```

Başarılı yanıt şu alanları taşır:

| Alan | Tür | Anlam |
| --- | --- | --- |
| `account` | Metin | Var olan ve etkin Frappe kullanıcısı |
| `issuer` | Metin | Ayarda sabitlenen Keycloak sağlayıcısı |
| `subject` | Metin | Doğrulanmış kullanıcı kimliği |
| `session_id` | Metin | Doğrulanmış ve açık Keycloak oturumunun kimliği |
| `resource` | Metin | Bu sitenin tam MCP adresi |
| `client_id` | Metin | İzin listesindeki dış istemci |
| `issued_at` | Tamsayı | Belirtecin üretildiği saniye |
| `expires_at` | Tamsayı | Belirtecin bittiği saniye |
| `scopes` | Metin listesi | Doğrulanmış kapsamlar |

İşlev şu koşulları birlikte denetler:

- İmza ve algoritma geçerli olur.
- `iss` değeri yapılandırılmış sağlayıcıyla aynıdır.
- `aud` değeri yalnız bu sitenin tam MCP adresidir.
- `azp` değeri izin verilen istemcilerden biridir.
- Kapsam `mcp` değerini içerir.
- `iat` ve `exp` tamsayıdır. Belirteç süresi en çok 300 saniyedir.
- Süre dolmamıştır. Gelecek zamanlı üretim tarihi reddedilir.
- Kimlik bağı var olan, etkin ve silinmemiş kullanıcıyı gösterir.
- Belirteç bir kullanıcı oturumuna bağlıdır. Servis hesabı kabul edilmez.
- Bağlı oturum açıktır. Çıkış ve hesap kapatma sonraki isteği reddettirir.

Geçersiz belirteç 401 üretir. Kimlik sağlayıcısına ulaşılamazsa 503 üretilir.
Oturum sorgusunun toplam sınırı 3 saniyedir.
Bu süre adres çözümünü, bağlantıyı ve tüm yanıtı kapsar.
Süre dolarsa platform 503 döner ve erişim vermez.
Hata metni sabittir. Belirteç veya kişisel bilgi hata kaydına girmez.
İşlev oturum açmaz. `frappe.set_user` çağırmaz. HTTP başlığı da yazmaz.

Oturum denetiminin yöntemi kimlik işinde belirlenir.
Yalnız imza denetimi açık oturumun kanıtı değildir.
Yalnız beş dakikalık süre de çıkış denetiminin yerini tutmaz.
Kimlik işi çıkışın sonraki isteği reddettiğini gerçek testle kanıtlar.

## Keycloak tarafındaki gereksinimler

İstemci ilk sürümde yönetici tarafından önceden kaydedilir.
Açık, sınırsız istemci kaydı bu planın parçası değildir.
İzin akışı Authorization Code ve PKCE kullanır.
PKCE, ele geçirilen giriş kodunun başka istemcide kullanılmasını önleyen denetimdir.
PKCE yöntemi `S256` olur. Parola ve örtük izin akışları kapalıdır.
Keycloak keşif belgesindeki `code_challenge_methods_supported` alanı `S256` değerini içerir.
Realm kabul testi bu bildirimi de denetler.

Keycloak, istekteki dönüş adresini kayıtlı adresle tam olarak karşılaştırır.
Keycloak joker, parça işareti veya kullanıcı bilgisi içeren adresi reddeder.
Dönüş adresi HTTPS kullanır. Yalnız yerel geliştirmede localhost adresi HTTP kullanabilir.
İzin ve belirteç uçları HTTPS kullanır.
Genel istemcinin yenileme belirteci döndürülür ve eski değer yeniden kullanılamaz.

İstemci izin ve belirteç isteğinde `resource` alanını gönderir.
Bu alan sitenin tam MCP adresidir.
Keycloak aynı adresi `aud` alanına koyar.
İstekte tek ve doğru kaynak varsa Keycloak `mcp_resource` alanını imzalar.
Platform her istekte iki alanı da sitenin tam MCP adresiyle karşılaştırır.
Platform `mcp_resource` alanı yoksa belirteci reddeder.
Başka sitenin adresi ve bilinmeyen kaynak reddedilir.
Aynı belirteçte birden çok site hedefi kabul edilmez.

Bu davranış Keycloak 26.8 kurulumunda ayrıca doğrulanmalıdır.
Mevcut realm dosyası tek başına bu desteğin kanıtı değildir.

## Yapay zekâ katmanındaki akış

OAuth desteği varsayılan olarak kapalı olur.
Kimlik işlevi ve realm kabul testleri tamamlanınca destek açılır.
Keşif belgesi de yalnız destek gerçekten açıkken yayımlanır.

1. İstemci MCP ucunu kimlik olmadan çağırır.
2. Sunucu 401 yanıtında `WWW-Authenticate` başlığı verir.
3. Başlıktaki `resource_metadata` adresi kaynak belgesini gösterir.
4. Kaynak belgesi Keycloak adresini ve istenen `mcp` kapsamını bildirir.
5. İstemci kullanıcıyı Keycloak girişine yönlendirir.
6. İstemci aldığı belirteci MCP ucuna Bearer başlığıyla gönderir.
7. Katman ortak kimlik işlevini çağırır.
8. Katman kullanıcının mevcut izinleriyle okuma yapar veya öneri açar.

Kaynak belgesi şu bilgileri taşır:

```json
{
  "resource": "https://tenant.example.test/api/method/platform_core.api.ai.mcp",
  "authorization_servers": ["https://identity.example.test/realms/platform"],
  "scopes_supported": ["mcp"],
  "bearer_methods_supported": ["header"]
}
```

Adresler sunucunun doğrulanmış ayarından gelir.
İstek başlığından veya istek gövdesinden adres türetilmez.
Kaynak belgesi sır veya kullanıcı bilgisi taşımaz.
Belge, Frappe yanıt zarfı olmadan doğrudan JSON olarak döner.
Keşif ucu ve yanıtları OpenAPI sözleşmesine eklenir.

## Korunacak sınırlar

OAuth kimliği insan oturumu sayılmaz.
İnsan onay uçları OAuth belirtecini reddeder.
Katman dış belirteci başka servise iletmez.
Belirteç yalnız MCP yolunda geçer. `cmd` alanı olan istek reddedilir.
Oturum çerezi ve belirteci birlikte gönderen istek reddedilir.
Başlık dışındaki belirteçler kabul edilmez.

Her belirteç en çok 20 araç çağrısı yapabilir.
Sayaç siteye, istemciye ve belirtecin özetine bağlı olur.
Sayaç atomik güncellenir. Aynı anda gelen çağrılar sınırı aşamaz.
Ham belirteç saklanmaz. Sayaç kaybolursa eski belirteç yeniden hak kazanamaz.
Bu durum için güvenli yeniden başlatma davranışı testle kanıtlanır.
Süre ve sayaç reddi günlüğe sabit neden koduyla yazılır.

Kimlik doğrulanınca veri izni mevcut araç katmanında denetlenir.
Yazma önce öneri açar. İnsan onayı ayrı oturumda verilir.

## Kabul testleri ve sıra

Önce her davranış için başarısız test yazılır.
Kurulum hatası başarısız davranış testinin yerine geçmez.

1. Kimlik işi yanlış imzayı, sağlayıcıyı, hedefi, istemciyi ve kapsamı reddeder.
2. Kimlik işi silinmiş hesabı, kapalı hesabı ve kapanmış oturumu reddeder.
3. Realm işi kod değişimini, PKCE yöntemini ve tam dönüş adresini sınar.
4. Realm işi yanlış kaynak isteğini ve çok hedefli belirteci reddeder.
5. Yapay zekâ işi 401 keşfini ve doğrudan JSON belgesini sınar.
6. Yapay zekâ işi etkin kullanıcıyla gerçek HTTP üzerinden araç çağırır.
7. Yapay zekâ işi başkasının verisini okumayı reddeder.
8. Yapay zekâ işi insan onayını ve başka HTTP yollarını reddeder.
9. Yapay zekâ işi süresi dolmuş belirteci ve 21. çağrıyı reddeder.
10. Yapay zekâ işi eşzamanlı çağrıyı ve sayaç kaybını sınar.
11. Entegrasyon işi gerçek Keycloak ve gerçek MCP istemcisiyle akışı tamamlar.
12. Bağımsız inceleyici yetki ve oturum sınırlarını inceler.

## Teslim sınırı ve geri dönüş

Uygulama yerel ayarla açılır. İnsan oturumu ve aracı belirteci desteklenir.
Tam realm kurulumu ve hazır bir MCP istemcisi birlikte sınanınca borç kapanır.

Uygulama sonrasında geri dönüş, OAuth ayarını kapatmaktır.
Bu işlem mevcut insan onay yolunu kapatmaz.

## Kaynaklar ve sürüm kanıtı

MCP belirtimi `2026-07-28` sürümüdür.
[Keşif kuralları](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/authorization-server-discovery)
kaynak belgesini ve 401 başlığını tanımlar.
[Güvenlik kuralları](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations)
hedef bağını, PKCE yöntemini ve belirteç aktarımı yasağını açıklar.

Uygulama bildirimi Python `>=3.14,<3.15` ve Frappe `>=16.56.0,<17.0.0` ister.
Ortak kitaplık bildirimi `oidc_verify==0.1.0` değerini taşır.
Bu tasarımda yeni paket veya sürüm değişikliği yoktur.
Yerel denemeler Keycloak 26.8.2 ve Frappe 16.56.0 kullandı.
Tam realm ve hazır MCP istemcisi denemesi `not_run` durumundadır.

Gerçek okurla denenmedi.
