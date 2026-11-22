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
| Kullanıcı silindi ya da kapatıldı. | Servis kullanıcıyı bütün kiracılarda kapatır. Servis Press üyeliğini kaldırır. |
| Kullanıcının e-postası doğrulanmadı. | Servis iş yapmaz. İlk bağ yalnız doğrulanmış e-postayla kurulur. |
| Kullanıcı kendi kaydoldu ve Organization üyesi değil. | Servis bir Organization açar ve kullanıcıyı ekler. Sonra Press'te takımı hazırlar. |
| Kullanıcı Organization üyesi. | Servis Press'te takımı hazırlar. Servis kullanıcıyı ilgili kiracıda açar ya da günceller. Sonra kiracıda `change_email` ucunu çağırır. |
| Kullanıcı bir Organization'dan çıktı. | Servis o Organization'ın takım üyeliğini kaldırır. Servis kullanıcıyı o kiracıda kapatır. |
| Keycloak belirsiz yanıt verdi. | Servis hiçbir kaydı değiştirmez. Olay bekleme kuyruğuna girer. |

Servis `change_email` ucunu her eşitlemede çağırır. Çünkü olayın adı e-postanın değiştiğini söylemez. E-posta aynıysa kiracı iş yapmaz.

Servis silinmeyi iki adımda doğrular. Keycloak önce kullanıcı için 404 dönmelidir. Sonra realm kullanıcı sayısını vermelidir. Yanlış adres de 404 döner. Bu yüzden tek 404 yanıtı kullanıcıyı kapatmaz.

Bir adım başarısız olursa servis öteki adımları yine dener. Örneğin Press yanıt vermese de kullanıcı kiracılarda kapanır.

Organization, Keycloak'ta bir müşteri kuruluşunu temsil eden kayıttır. Kurallar `identity_sync/mapping.py` dosyasındadır. Bu dosya ağa ve diske dokunmaz.

## Komutlar

Komutları `backend/identity/identity_sync` klasöründe çalıştırın. Her komut elle başlar. Zamanlanmış iş yoktur (Proje kaydı D-6).

| Komut | İşi | HTTP karşılığı |
| --- | --- | --- |
| `python3 -m identity_sync serve` | HTTP sunucusunu başlatır. | Yok |
| `python3 -m identity_sync reconcile` | Keycloak, Press ve kiracı kullanıcılarını karşılaştırır. Yalnız farkı raporlar. | `POST /v1/reconcile` |
| `python3 -m identity_sync dead-letters` | Bekleme kuyruğunu listeler. | `GET /v1/dead-letters` |
| `python3 -m identity_sync replay-dead-letters` | Bekleyen olayları bir kez yeniden işler. | `POST /v1/dead-letters/replay` |

- `replay-dead-letters --dry-run` hiçbir kaydı değiştirmez. Komut yalnız çalışacak işleri gösterir.
- `replay-dead-letters` sonucu bilinmeyen olayı atlar. `--include-unknown` bu olayları da işletir. Önce hedefi denetleyin.
- `reconcile` fark bulursa 1 koduyla biter. Fark yoksa 0 koduyla biter.
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
6. Servis planı yeniden hesaplar. Plan değiştiyse servis 409 döner ve iş yapmaz.
7. Servis yalnız onaylanan planı yürütür. Servis her olaydan hemen önce planı bir kez daha denetler.
8. Servis çağıranı, onay kimliğini, özeti ve sonucu günlüğe yazar.

`serve` komutu günlüğü standart hata akışına yazar. İşlem günlüğü satırı `execute operation=` ile başlar.

Servis iki istemci listesi tutar:

- `IDENTITY_SYNC_PREVIEW_AZP` listesindeki istemci yalnız okur ve önizler.
- `IDENTITY_SYNC_EXECUTE_AZP` listesindeki istemci yürütebilir.

Aracı belirteci yürütme listesine girmez. Önizleme listesindeki istemci yürütme isterse 403 alır.

Olay ucu bu akışın dışındadır. Olay Keycloak'ta zaten olmuş bir değişikliği taşır.

## Sonucu bilinmeyen iş

Servis hedefin yalnız kesin başarı yanıtını başarı sayar. Yanıtların biçimi OpenAPI dosyasındadır.

- Hedef 202 dönerse iş bitmemiş olabilir. Boş yanıt da aynı durumdadır.
- Servis böyle bir olayı `unknown` durumuyla bekleme kuyruğuna yazar.
- İstek gitti ama yanıt okunamadıysa sonuç yine bilinmez. 502 ve 504 yanıtları da böyledir.
- Servis bu olayı işlenmiş saymaz. Servis olayı kendiliğinden yeniden denemez.
- Aynı olay yeniden gelirse servis yazmayı tekrarlamaz.
- İnsan hedefi denetler. Sonra olayı `--include-unknown` seçeneğiyle yeniden işletir.

## Süreçler arası sıra

Sunucu ve `replay-dead-letters` komutu ayrı süreçlerdir. İkisi aynı kayıt dosyasını açar.

- Servis her olayın işini bir iş kilidi altında yürütür. Kilit bir kilit dosyasındadır.
- İkinci süreç ilk süreç o olayı bitirene kadar bekler. Bekleme en çok 10 saniyedir.
- Süre dolarsa komut 2 koduyla biter. HTTP ucu 503 ve `busy` döner.
- Böylece aynı olay iki kez çalışmaz. Aynı kullanıcının iki olayı da sıraya girer.
- Servis her kaydı hemen kalıcı yazar. Yeniden işleme yarıda kesilirse biten olaylar kaybolmaz.
- Süreç ölürse kilit kendiliğinden açılır.

## Ayarlar

Servis ayarları ve sırları ortam değişkeninden okur. Örnek değerler `.env.example` dosyasındadır. O dosyadaki bütün değerler sahtedir. Gerçek sırrı depoya yazmayın.

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
- `provision` gibi kiracı uçlarının başarı yanıtı ortak sözleşmede henüz yok. Bu servis `{"message": {"status": "done"}}` bekler.
- Silinen kullanıcının kuruluşları okunamaz. Servis bu durumda `remove_team_member` isteğini `organization_id` olmadan gönderir.
