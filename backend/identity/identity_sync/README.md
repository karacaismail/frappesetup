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
| Kullanıcı Organization üyesi. | Servis Press'te takımı hazırlar. Servis kullanıcıyı ilgili kiracıda açar ya da günceller. |
| E-posta değişmiş olabilir. | Servis ayrıca kiracıda `change_email` ucunu çağırır. |
| Kullanıcı bir Organization'dan çıktı. | Servis o Organization'ın takım üyeliğini kaldırır. Servis kullanıcıyı o kiracıda kapatır. |

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
- `reconcile` fark bulursa 1 koduyla biter. Fark yoksa 0 koduyla biter.
- Ayar ya da bağlantı hatasında komut 2 koduyla biter.

## Önizleme

Yazan her iş önce önizleme üretebilir. Önizleme şunları söyler:

- işin adı, örneğin `tenant.set_enabled`,
- işin hedefi, örneğin `kiraci1`,
- işi anlatan bir cümle,
- işin yıkıcı olup olmadığı.

Kullanıcıyı kapatmak ve takım üyeliğini kaldırmak yıkıcı işlerdir. Önizleme e-posta ve sır taşımaz. İnsan onayı ileride bu önizlemeye bakacak.

## Ayarlar

Servis ayarları ve sırları ortam değişkeninden okur. Örnek değerler `.env.example` dosyasındadır. O dosyadaki bütün değerler sahtedir. Gerçek sırrı depoya yazmayın.

## Kimlik denetimi

- Olay ucu imza ister. İmza, istek gövdesinin HMAC-SHA256 özetidir.
- Öteki uçlar Keycloak servis belirteci ister. Servis belirteci ortak `oidc_verify` kitaplığıyla doğrular.
- `oidc_verify` kurulu değilse servis bu uçlardaki her isteği reddeder.
- `IDENTITY_SYNC_ALLOWED_AZP` listesi boşsa servis yine her isteği reddeder.

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

## Bilinen eksikler

- Canlı Keycloak ile bütünleşme testi yapılmadı. Bu test realm birleşince yapılır.
- Container dosyası henüz yok.
- Mutabakat, Press'te ve kiracıda `list_identities` ucunu ister. Bu uçlar ortak sözleşmede henüz yok.
- Servis belirteci için `aud-identity-sync` kapsamı ortak sözleşmede henüz yok.
- Admin API belirtecinin kapsam adı ortak sözleşmede henüz yok.
