# Kayıt paylaşımı

## Paylaş düğmesi

1. “Paylaş” düğmesinde ekranın normal bağlantısını kullanın.
2. Telefon destekliyorsa cihazın paylaş menüsünü açın.
3. Menü açılamazsa bağlantıyı kopyalayın.
4. Özel bağlantı için `create_record_link` yolunu çağırın.
5. Yanıttaki `path` değerini aynı sitenin adresine ekleyin.
6. İptal işlemi için yanıttaki `id` değerini saklayın.

Özel bağlantı 7 gün geçerlidir. Bağlantı, alıcının mevcut yetkisini kullanır.

## Sunucu yolları

Yollar `/api/method/platform_core.api.access.` ile başlar. Arayüz bu yolları `POST` ile çağırır. Arayüz istek gövdesinde JSON ve oturumun CSRF başlığını gönderir. CSRF başlığı, isteğin sitedeki oturumdan geldiğini doğrulamaya yardım eder.

| Yol | İstek alanları | Yanıt |
| --- | --- | --- |
| `create_record_link` | `doctype`, `name` | 200 ve `id`, `path`. Kayıt açılamıyorsa 404. |
| `open_record_link` | `token` | 200 ve `doctype`, `name`. Kayıt açılamıyorsa 404. Bağlantı iptal edildiyse veya süresi dolduysa 410. |
| `revoke_record_link` | `link_id` | 200. Bağlantı açılamıyorsa 404. |
| `request_record_access` | `token` veya `doctype` ve `name` | 202 ve `status: received`. Kullanıcı dakikada 10 isteği aşarsa 429. |

`token`, bağlantının `#` işaretinden sonraki gizli değeridir. Arayüz bu değeri yalnız istek gövdesinde gönderir. Arayüz bu değeri olay kaydına ve ölçüm araçlarına yazmaz.

## Açma ve erişim isteme

1. `/panel/share` ekranı bağlantıdaki gizli değeri alır.
2. Alıcı giriş yapmadıysa arayüz değeri giriş boyunca korur.
3. Girişten sonra arayüz `open_record_link` yolunu çağırır.
4. Yanıt 200 ise arayüz mevcut kayıt ekranını açar.
5. Yanıt 404 ise arayüz tek bir “Kayıt açılamadı” ekranı gösterir.
6. Bu ekrandaki “Erişim iste” düğmesi `request_record_access` yolunu çağırır.
7. Yanıt 410 ise arayüz “Bağlantı artık geçerli değil” mesajını gösterir.

Sunucu 202 yanıtında kayıt hakkında bilgi vermez. Arayüz 202 yanıtında “İsteğiniz alındı” mesajını gösterir.

## Önizleme ve kalan işler

Tarayıcı tıklamayı bildirirse sunucu giriş sayfasını açar. Diğer girişsiz isteklerde sunucu genel kartı gösterir. Karttaki bağlantı giriş sayfasını açar.

Paylaş düğmesi ve `/panel/share` ekranı arayüz işidir. Giriş sırasında gizli değeri koruma işi de bu ekrana aittir. Bildirim gönderme ve DocShare ile erişim onayı ayrı iş ister. Herkese açık bağlantı bu teslimin kapsamı dışındadır.
