# identity_sync

Bu servis Keycloak'taki kullanıcı değişikliklerini Press'e ve kiracı sitelerine taşır (G-81). Keycloak, kullanıcıların giriş yaptığı kimlik sunucusudur.

Servis yalnız Python'un kendi kitaplığını kullanır. Servis Python 3.11 ve sonrasında çalışır. Teknoloji kararı [karar notundadır](../../docs/kararlar/0001-identity-sync.md). Uçların sözleşmesi [OpenAPI dosyasındadır](../../contracts/identity_sync.openapi.yaml).

## Servis nasıl çalışır?

1. Servis bir olay alır. Örneğin kullanıcı e-postasını doğruladı.
2. Servis kullanıcının güncel durumunu Keycloak'tan okur.
3. Servis bu duruma göre eylemleri seçer. Örneğin Press'te takımı hazırlar.
4. Servis eylemleri sırayla çalıştırır.
5. Bir eylem başarısız olursa servis olayı bekleme kuyruğuna yazar.

Servis eylemi olayın içeriğinden seçmez. Kullanıcının güncel durumundan seçer. Bu yüzden aynı olay iki kez gelirse sonuç değişmez. Geç gelen olay da yanlış sonuç üretmez.

## Olaylar ve eylemler

| Kullanıcının durumu | Servisin yaptığı iş |
| --- | --- |
| Kullanıcı silindi ya da kapatıldı. | Servis kullanıcıyı bütün kiracılarda kapatır. Servis Press'e tek bir `all_organizations` isteği gönderir. Press kullanıcıyı bütün takımlardan çıkarır, kapatır ve API anahtarlarını geçersiz yapar. |
| Kullanıcının e-postası doğrulanmadı. | Servis iş yapmaz. İlk bağ yalnız doğrulanmış e-postayla kurulur. |
| Kullanıcı kendi kaydoldu ve Organization üyesi değil. | Servis bir Organization açar ve kullanıcıyı ekler. Sonra Press'te takımı hazırlar. |
| Kullanıcı Organization üyesi. | Servis Press'te takımı hazırlar. Servis kiracıda önce `change_email` ucunu çağırır. Sonra kullanıcıyı açar ya da günceller. |
| Kullanıcı bir Organization'dan çıktı. | Servis o Organization'ın takım üyeliğini kaldırır. Servis kullanıcıyı o kiracıda kapatır. |
| Keycloak belirsiz yanıt verdi. | Servis hiçbir kaydı değiştirmez. Olay bekleme kuyruğuna girer. |

Servis `change_email` ucunu her eşitlemede çağırır. Çünkü olayın adı e-postanın değiştiğini söylemez. E-posta aynıysa kiracı iş yapmaz. Kiracıda bağ yoksa kiracı 404 ve `IdentityNotFound` döner. Servis bu yanıtı hata saymaz.

Servis önce `change_email`, sonra `provision` çağırır. Çünkü kiracı, bağ eski e-postayı gösterirken `provision` isteğini reddeder.

Kapalı ya da silinen hesabın planı üyelik listesine bağlı değildir. Üyelik okunamasa da servis kapatma isteklerini gönderir.

Servis silinmeyi iki adımda doğrular. Keycloak önce kullanıcı için 404 dönmelidir. Sonra realm kullanıcı sayısını vermelidir. Yanlış adres de 404 döner. Bu yüzden tek 404 yanıtı kullanıcıyı kapatmaz.

Bir adım başarısız olursa servis öteki adımları yine dener. Örneğin Press yanıt vermese de kullanıcı kiracılarda kapanır.

Organization, Keycloak'ta bir müşteri kuruluşunu temsil eden kayıttır. Kurallar `identity_sync/mapping.py` dosyasındadır. Bu dosya ağa ve diske dokunmaz.

## Komutlar

Komutları `backend/identity/identity_sync` klasöründe çalıştırın. Her komut elle başlar. Zamanlanmış iş yoktur (Proje kaydı D-6).

| Komut | İşi | HTTP karşılığı |
| --- | --- | --- |
| `python3 -m identity_sync serve` | HTTP sunucusunu başlatır. | Yok |
| `python3 -m identity_sync reconcile` | Keycloak, Press ve kiracı kullanıcılarını karşılaştırır. Farkı ve düzeltme planını gösterir. | `POST /v1/reconcile` |
| `python3 -m identity_sync operations` | Yarıda kalan çok adımlı işleri listeler. | `GET /v1/operations` |
| `python3 -m identity_sync resolve-operation` | Yarıda kalan bir işi kapatır. | `POST /v1/operations/<kimlik>/resolve` |
| `python3 -m identity_sync dead-letters` | Bekleme kuyruğunu listeler. | `GET /v1/dead-letters` |
| `python3 -m identity_sync replay-dead-letters` | Bekleyen olayları bir kez yeniden işler. | `POST /v1/dead-letters/replay` |

- `replay-dead-letters --dry-run` hiçbir kaydı değiştirmez. Komut yalnız çalışacak işleri gösterir.
- `replay-dead-letters` sonucu bilinmeyen olayı atlar. `--include-unknown` bu olayları da işletir. Önce hedefi denetleyin.
- `reconcile` fark bulursa 1 koduyla biter. Fark yoksa 0 koduyla biter.
- `reconcile` varsayılan olarak yalnız rapor üretir. Hiçbir kaydı değiştirmez.
- `reconcile --execute --preview-digest <özet> --approval-id <onay>` raporda gösterilen düzeltmeyi yürütür. Plan değiştiyse komut hiçbir şey yazmaz.
- Ayar ya da bağlantı hatasında komut 2 koduyla biter.

## Önizleme

Yazan her iş önce önizleme üretebilir. Önizleme şunları söyler:

- işin adı, örneğin `tenant.set_enabled`,
- işin hedefi, örneğin `kiraci1`,
- işi anlatan bir cümle,
- işin yıkıcı olup olmadığı.

Kullanıcıyı kapatmak ve takım üyeliğini kaldırmak yıkıcı işlerdir. Önizleme e-posta ve sır taşımaz.

## Yapay zekâ ve insan onayı

Yapay zekâ bu servisin yazma uçlarını doğrudan yürütemez. Kural ortak sözleşmenin 10. bölümündedir.

1. Yapay zekâ aracısı ucu `dry_run: true` ile çağırır. Servis yalnız okur.
2. Servis çalışacak işleri ve bir `preview_digest` değeri döner. Bu değer önizlemenin özetidir.
3. Onay katmanı işleri insana gösterir. Onay katmanı `platform_core` içindedir.
4. İnsan onaylar. Onay katmanı ucu `dry_run: false` ile çağırır.
5. İstek `preview_digest` ve `approval_id` alanlarını taşır.
6. Servis onay kimliğini tek kullanımlık olarak kaydeder. Aynı onay ikinci kez gelirse servis 409 ve `approval_used` döner.
7. Servis planı yeniden hesaplar. Plan değiştiyse servis 409 ve `preview_changed` döner ve iş yapmaz.
8. Servis yalnız onaylanan planı yürütür. Servis her olaydan hemen önce planı bir kez daha denetler.
9. Servis çağıranı, onay kimliğini, özeti ve sonucu günlüğe yazar.

Özet yazılacak her şeyi kapsar: her işin adını, hedefini ve bütün alan değerlerini. Örneğin e-posta önizlemeden sonra değişirse özet tutmaz.

Özet anahtarlıdır. Servis özeti HMAC-SHA256 ile üretir. Anahtar `IDENTITY_SYNC_DIGEST_KEY` ortam sırrındadır. Anahtarı bilmeyen biri bir e-posta tahminini özetle karşılaştıramaz.

Özet kuruluşun gerçek Keycloak kimliğini de kapsar. Servis kuruluşu plan sırasında arar. Yürütmede yeniden aramaz. Kuruluş önizlemeden sonra oluştuysa özet tutmaz.

Bir istek birden çok olay kapsayabilir. Herhangi bir olayın planı değiştiyse servis bütün isteği reddeder ve hiçbir olayı yazmaz.

## Yarıda kalan davet

Davet Keycloak'a üç adımda yazar: kullanıcıyı açar, üye yapar ve e-posta gönderir.

1. Servis her adımı yazmadan önce kaydeder.
2. Adım bitince servis kaydı günceller.
3. Süreç yarıda durursa kayıt hangi adımın belirsiz kaldığını gösterir.

`python3 -m identity_sync operations` komutu yarıda kalan işleri listeler. HTTP karşılığı `GET /v1/operations` ucudur.

İnsan önce Keycloak'ı denetler. Sonra işi kapatır:

```bash
python3 -m identity_sync resolve-operation <kimlik> --resolution completed
```

`completed` değeri işin hedefte tamamlandığını söyler. `abandoned` değeri işten vazgeçildiğini söyler. HTTP karşılığı `POST /v1/operations/<kimlik>/resolve` ucudur. Bu ucu yalnız onay katmanı çağırabilir.

`serve` komutu günlüğü standart hata akışına yazar. İşlem günlüğü satırı `execute operation=` ile başlar.

Servis iki istemci listesi tutar:

- `IDENTITY_SYNC_PREVIEW_AZP` listesindeki istemci yalnız okur ve önizler.
- `IDENTITY_SYNC_EXECUTE_AZP` listesindeki istemci yürütebilir.

Aracı belirteci yürütme listesine girmez. Önizleme listesindeki istemci yürütme isterse 403 alır.

Olay ucu bu akışın dışındadır. Olay Keycloak'ta zaten olmuş bir değişikliği taşır.

## Sonucu bilinmeyen iş

Servis hedefin yalnız kesin başarı yanıtını başarı sayar. Yanıtların biçimi OpenAPI dosyasındaki `Target` şemalarındadır. Bu şemalar Press'in ve kiracının kendi sözleşmelerinden gelir.

Servis yanıttaki son durumu istediği durumla da karşılaştırır. Örneğin kullanıcıyı kapattıysa yanıtta `enabled` yanlış olmalıdır.

- Hedef 202 dönerse iş bitmemiş olabilir. Boş yanıt da aynı durumdadır.
- Servis böyle bir olayı `unknown` durumuyla bekleme kuyruğuna yazar.
- İstek gitti ama yanıt okunamadıysa sonuç yine bilinmez. 502 ve 504 yanıtları da böyledir.
- Servis bu olayı işlenmiş saymaz. Servis olayı kendiliğinden yeniden denemez.
- Aynı olay yeniden gelirse servis yazmayı tekrarlamaz.
- İnsan hedefi denetler. Sonra olayı `--include-unknown` seçeneğiyle yeniden işletir.

## Mutabakat

Olay kaybolabilir. Örneğin Keycloak eklentisi olayı gönderemeyebilir. Mutabakat yedek yoldur. Komut zamanlanmaz. İnsan komutu elle başlatır.

Komut Keycloak'taki bütün kullanıcıları Press ve kiracı kayıtlarıyla karşılaştırır. Örnek farklar şunlardır:

- Kullanıcı Keycloak'ta kapalı ama kiracıda açık.
- Kullanıcının kiracıda bağı yok.
- Kullanıcı Press'te yanlış takımın üyesi.

Rapor e-posta taşımaz. Rapor her fark için düzeltme işini de gösterir. Düzeltme önizleme ve onay akışından geçer. Servis yalnız onaylanan planı yürütür.

Bazı farkların güvenli bir düzeltmesi yoktur. Servis bunları yalnız raporlar. Örneğin Press'te kapalı bir kullanıcıyı açan uç yoktur.

## Yarıda kalan iş

Süreç her an durabilir. Servis olayı kaybetmez ve yazmayı körlemesine tekrarlamaz.

1. Servis kabul ettiği olayı işe başlamadan önce bekleme kuyruğuna yazar.
2. Servis ilk dış yazmadan hemen önce kaydı `unknown` yapar.
3. Olay başarıyla bitince kayıt kuyruktan çıkar.

Süreç yazmadan önce durduysa olay elle yeniden işlenir. Süreç bir yazmadan sonra durduysa sonuç bilinmez. İnsan hedefi denetler ve olayı `--include-unknown` ile yeniden işletir.

## Süreçler arası sıra

Sunucu ve `replay-dead-letters` komutu ayrı süreçlerdir. İkisi aynı kayıt dosyasını açar.

- Servis her olayın işini bir iş kilidi altında yürütür. Kilit bir kilit dosyasındadır.
- İkinci süreç ilk süreç o olayı bitirene kadar bekler. Bekleme en çok 10 saniyedir.
- Süre dolarsa komut 2 koduyla biter. HTTP ucu 503 ve `busy` döner.
- Böylece aynı olay iki kez çalışmaz. Aynı kullanıcının iki olayı da sıraya girer.
- Servis her kaydı hemen kalıcı yazar. Yeniden işleme yarıda kesilirse biten olaylar kaybolmaz.
- Süreç ölürse kilit kendiliğinden açılır.

## Sözleşme metninin dili

OpenAPI dosyasındaki özet ve açıklama metinleri İngilizcedir. Araçlar ve yapay zekâ bu metinleri okur.

- Türkçe metin `translations/tr.csv` dosyasındadır.
- Dosyanın üç sütunu vardır: İngilizce kaynak, Türkçe çeviri ve bağlam.
- Bağlam, metnin sözleşmedeki yerini söyler. Örneğin `identity_sync.openapi.yaml: paths./healthz.get.summary` yazar.
- Sözleşmedeki bir metni değiştirirseniz çeviri dosyasındaki satırı da değiştirin. Bir test iki dosyanın uyuştuğunu denetler.

## Ayarlar

Servis ayarları ve sırları ortam değişkeninden okur. Örnek değerler `.env.example` dosyasındadır. O dosyadaki bütün değerler sahtedir. Gerçek sırrı depoya yazmayın.

## Hesap silme

Müşteri hesabının silinmesini Press'te ister (Proje kaydı O-27). Press o zaman `POST /v1/account-deletions` ucunu çağırır.

- Ucu yalnız Press çağırabilir. İzinli istemci `IDENTITY_SYNC_DELETION_AZP` ayarındadır. Varsayılan değer `press-service` olur.
- Gövde `issuer`, `subject` ve `reauthenticated_at` alanlarını taşır.
- Press müşteriyi Keycloak'ta yeniden doğrular. `reauthenticated_at` bu girişin zamanıdır.
- Servis 300 saniyeden eski girişi reddeder. Yanıt 403 ve `reauthentication_required` olur.
- Bu uçta önizleme ve onay kimliği yoktur. Onay, hesap sahibinin yeni girişidir.

Akış beş adımdır ve sırası sabittir:

1. Servis Keycloak kullanıcısını kapatır. Bu adımda kullanıcıyı silmez.
2. Servis Press'e `all_organizations: true` isteği gönderir. Press kullanıcıyı kapatır ve API anahtarlarını geçersiz yapar.
3. Servis kullanıcıyı her kiracıda kapatır ve telefon kurulumlarını iptal ettirir.
4. Servis kişiyi gösteren alanları Press'te ve her kiracıda anonim yaptırır. İş kayıtları silinmez.
5. Servis Keycloak kullanıcısını siler.

- Her adım tekrar edilebilir.
- Adımlar birbirine bağlıdır. Bir adım başarısız olursa servis sonraki adımları yürütmez.
- Başarısız istek bekleme kuyruğuna girer. Servis kaç adımın bittiğini saklar.
- İnsan isteği `replay-dead-letters` komutuyla yeniden işletir. İş bitmemiş ilk adımdan sürer.
- Press aynı isteği yeniden gönderirse iş yine bitmemiş ilk adımdan sürer.
- İsteğin kimliği hesabın anahtarlı özetidir. Bu yüzden bir hesap her zaman tek istektir.
- Servis e-postayı hiç saklamaz. İş bitince kayıtta yalnız isteğin kimliği kalır.
- Hedef `anonymize_user` ucu 409 dönerse servis isteği yeniden dener.
- Keycloak'ın kendi `delete_account` eylemi kapalıdır. O eylem kullanıcıyı ilk adımda siler.

Yönetici bir kullanıcıyı Keycloak yönetim ekranından silebilir. Olay dinleyici o zaman olayı gönderir. Servis 2., 3. ve 4. adımı yürütür.

Press isteği ve Keycloak silme olayı bir hesap için tek iştir:

- İşin kimliği hesabın anahtarlı özetidir. Kimlik `del-` ile başlar.
- 5. adım Keycloak kullanıcısını siler. Olay dinleyici bu silmeyi de bildirir. O olay bitmiş işi bulur ve hiçbir iş başlatmaz.
- Press isteği bir adımda durduysa silme olayı aynı işi sürdürür. Servis bitmiş adımı yeniden çağırmaz.
- Önizleme ve bekleme kuyruğu listesi işin kimliğini gösterir. Hesabın kimliğini göstermez.

Silme olayı kaybolabilir. O zaman `reconcile` komutu silinen kullanıcıyı bulur:

1. Komut farkı `deleted_in_keycloak` türüyle raporlar.
2. Önizleme işin kalan adımlarını gösterir.
3. İnsan onay verir.
4. Komut kalan adımları sırayla yürütür. Yerel hesap önceden kapalı olsa da adımlar çalışır.

Keycloak'ta kapatılan kullanıcının telefon kurulumları da iptal edilir. Bu iş kapatma planının parçasıdır.

## Olay dinleyici eklentisi

Keycloak olayları kimlik-realm işinin kurduğu eklentiden gelir. Eklenti olayı imzalar ve `POST /v1/events` ucuna gönderir.

- Eklentinin imza kodu bu servisin alıcısıyla denendi. `tests/test_server.py` içindeki `ForkedListenerTest` sınıfı eklentinin ürettiği bir imzayı sabit veri olarak taşır.
- İmza anahtarı en az 16 karakter olmalıdır. Eklenti de daha kısa anahtarı reddeder.

## Oturum kapatma

Kullanıcı bir telefon kurulumunu iptal edince kiracı sitesi `POST /v1/sessions/revoke` ucunu çağırır. Gövde `sid` ve `subject` alanlarını taşır.

- Servis kiracıyı belirtecin `azp` değerinden bulur. Örneğin `site-kiraci1` istemcisi `kiraci1` kiracısıdır.
- Kullanıcı o kiracının kuruluşuna üye değilse servis 403 döner.
- Servis yalnız o kullanıcının oturum listesindeki oturumu siler. Yenileme belirteci de geçersiz olur.
- Uç tekrar edilebilir. Oturum zaten kapalıysa servis yine 200 döner.
- Ucu yalnız `IDENTITY_SYNC_SESSION_AZP` listesindeki istemci çağırabilir. Bu liste kiracı sitelerinin servis istemcilerini taşır.
- Yeni kiracı eklerken istemcisini bu listeye de yazın. Yazmazsanız o kiracı oturum kapatamaz.
- Bu istemciler öteki uçları çağıramaz.

## Kimlik denetimi

- Olay ucu imza ister. İmza HMAC-SHA256 ile üretilir.
- İmza üç parçayı kapsar: zaman damgasını, kipi ve gövdeyi. Kip `execute` ya da `preview` olur.
- Zaman damgası `X-Identity-Sync-Timestamp` başlığında gelir. Servis en çok 300 saniyelik farkı kabul eder.
- Aynı imza yalnız bir kez geçer. Önizleme imzası yürütmede geçmez.
- Öteki uçlar Keycloak servis belirteci ister. Servis belirteci ortak `oidc_verify` kitaplığıyla doğrular.
- `oidc_verify` kurulu değilse servis bu uçlardaki her isteği reddeder.
- İki istemci listesi de boşsa servis yine her isteği reddeder.
- Servis bir isteğin başlığını ve gövdesini en çok 10 saniye bekler. Yavaş istemci sunucuyu tutamaz.

Keycloak kendi olay biçiminde realm'in iç kimliğini gönderir. Realm adını göndermez. Servis bu kimliği `IDENTITY_SYNC_REALM_ID` ayarıyla karşılaştırır.

## Kişisel veri

- Servis e-postayı saklamaz. Kayıt dosyası yalnız olay kimliğini ve kullanıcı kimliğini tutar.
- Hata kaydı yanıt gövdesini taşımaz. Yalnız adımı ve durum kodunu taşır.
- Mutabakat raporu e-posta taşımaz.

## Testler

Testleri `backend/identity/identity_sync` klasöründe çalıştırın:

```bash
python3 -I -W error -m unittest discover -s tests -t .
```

Testler ağa çıkmaz. Sahte sunucular Keycloak, Press ve kiracı sitesi yerine geçer. Örnek kullanıcılar uydurmadır ve `example.test` alan adını kullanır.

Bu komut 16 testi atlar. Atlanan testler gerçek belirteç doğrulamasını sınar ve `oidc_verify` kitaplığını ister. Kitaplık `backend/libs/oidc_verify` klasörüne gelince şu komutu çalıştırın:

```bash
PYTHONPATH=../../libs/oidc_verify/src uv run --no-project --with 'pyjwt>=2.13,<3' --with 'cryptography>=50,<51' python -m unittest discover -s tests -t .
```

Bu komutta hiçbir test atlanmamalıdır. Testler RSA anahtarını kendisi üretir.

## Bilinen eksikler

- Canlı Keycloak ile bütünleşme testi yapılmadı. Bu test realm birleşince yapılır.
- Container dosyası henüz yok.
- Mutabakat, Press'te ve kiracıda `list_identities` ucunu ister. Bu uçlar ortak sözleşmede henüz yok.
- Servis belirteci için `aud-identity-sync` kapsamı ortak sözleşmede henüz yok.
- Onay katmanının istemci adı ortak sözleşmede henüz yok.
- Bu dalda Press'in ve kiracının sözleşme dosyaları yok. Testler o dosyalara göre yazılmış sahte hedefler kullanır. Gerçek bütünleşme testi `integration-e2e` işindedir.
- Mutabakat Press'te ve kiracıda kullanıcı listesi veren uç ister. Bu uçlar o sözleşmelerde henüz yok.
- Hesap silme ve kapatma üç hedef ucu çağırır: `revoke_user_installations` ve iki `anonymize_user` ucu. Bu uçlar öteki dallarda yazıldı. Bu dalda yalnız sahte hedeflerle denendi.
- Eklenti canlı Keycloak üzerinde bu servisle denenmedi. Yalnız eklentinin imza kodu denendi.
- `ensure_site_client` işlevi Keycloak'ta `manage-clients` rolünü ister. Ortak sözleşme servis hesabına bu rolü vermez.
