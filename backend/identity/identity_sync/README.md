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

`replay-dead-letters` komutu varsayılan olarak yalnız önizler. Yürütme için şu sırayı izleyin:

1. `replay-dead-letters` komutunu çalıştırın. Komut çalışacak işleri ve `preview_digest` değerini gösterir. Hiçbir kaydı değiştirmez.
2. İşleri inceleyin ve onay verin.
3. `replay-dead-letters --execute --preview-digest <özet> --approval-id <onay kimliği>` komutunu çalıştırın.

- Onay kimliği bir kez kullanılır.
- Plan önizlemeden sonra değiştiyse komut hiçbir şey yazmaz. Yeni önizleme alın.
- Liste uçları sayfalıdır. `GET /v1/dead-letters` ve `GET /v1/operations` en çok `limit` kadar kayıt döner. Varsayılan değer 100'dür. Başka kayıt varsa yanıt `next_offset` taşır.
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

Servis dört istemci listesi tutar:

- `IDENTITY_SYNC_PREVIEW_AZP` listesindeki istemci yalnız okur ve önizler.
- `IDENTITY_SYNC_EXECUTE_AZP` listesindeki istemci yürütebilir. Bu liste kiracı sitelerinin servis istemcilerini taşır. Örnek: `site-tenant1-service`.
- `IDENTITY_SYNC_SESSION_AZP` listesindeki istemci oturum kapatabilir. Bu liste aynı kiracı istemcilerini taşır.
- `IDENTITY_SYNC_DELETION_AZP` listesindeki istemci yalnız hesap silme isteyebilir. Bu istemci Press istemcisidir.

İnsan onayı kiracı sitesindeki yapay zekâ katmanında verir. Bu yüzden yürütmeyi kiracı sitesi çağırır.

- Yürütme listesi ile oturum listesi aynı istemcileri taşımalıdır. Listeler farklıysa servis açılmaz.
- Bu iki listedeki her istemci, `IDENTITY_SYNC_TENANTS` ayarındaki bir kiracının servis istemcisi olmalıdır. Örneğin `kiraci1` kiracısının istemcisi `site-tenant1-service` adını taşır. Kayıtsız bir kiracının istemcisi listeye yazılırsa servis açılmaz.
- Servis çalışırken de aynı kuralı uygular. Kiracıya bağlı olmayan istemci yürütme isterse 403 alır.
- Önizleme ya da silme listesindeki istemci başka bir listede olamaz.
- Bu servis Keycloak'ta istemci açmaz. Yeni kiracının istemcisini kimlik-realm işi açar. O komutu insan başlatır.

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

Mutabakat hedeflerin kullanıcı listesini `list_identities` ucundan okur:

- Liste sayfalıdır. Servis her istekte en çok 500 kayıt ister.
- Servis bütün sayfaları okur. Farkları ancak son sayfadan sonra hesaplar.
- Yanıt beklenen biçimde değilse ya da sayfalama bitmiyorsa servis hata verir. Yarım listeden sonuç çıkarmaz.
- Keycloak'ta silinen hesabın farkı `job_id` taşır. Hesabın ham kimliği yanıtta yer almaz.

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

## Hesap silme yolları

Bu tablo silme akışının bütün yollarını gösterir. Her satırı `tests/test_deletion_paths.py` dosyasındaki bir test sınar. Testin adı `test_row_` ile ve satır numarasıyla başlar. Her test gerçek HTTP girişini kullanır.

Hiçbir satırda yanıt hesabın ham Keycloak kimliğini göstermez. Yanıt yalnız iş kimliğini gösterir. Her test bunu da denetler.

| Satır | Giriş | Keycloak okuması | Yazma isteği | Kayıt durumu |
| --- | --- | --- | --- | --- |
| 1 | Press isteği | Okuma yok | Beş adım | İş bitti |
| 2 | Press isteği, 4. adım hata verir | Okuma yok | 1., 2. ve 3. adım | İş kuyrukta |
| 3 | İkinci Press isteği | Okuma yok | Yok | İş bitti |
| 4 | Silme olayı, iş bitmiş | Kullanıcı yok | Yok | İş bitti |
| 5 | Silme olayı, iş yok | Kullanıcı yok | 2., 3. ve 4. adım | İş bitti |
| 6 | Silme olayı, iş yarım | Kullanıcı yok | Yalnız kalan adım | İş bitti |
| 7 | Silme olayı | Okuma hatası | Yok | Olay kuyrukta |
| 8 | Silme olayı | Kullanıcı var | Yalnız kapatma | Olay bitti, iş açılmadı |
| 9 | Kuyruktaki olayın önizlemesi | Kullanıcı yok | Yok | Olay kuyrukta |
| 10 | Kuyruktaki olayın önizlemesi | Kullanıcı kapalı | Yok | Olay kuyrukta |
| 11 | Kuyruktaki olayın önizlemesi | Okuma hatası | Yok | Olay kuyrukta |
| 12 | Kuyruk listesi | Okuma yok | Yok | Olay kuyrukta |
| 13 | Onaylı yeniden deneme | Önce kapalı, yürütmeden sonra yok | Yalnız kapatma | Olay bitti, iş açık |
| 14 | Onaylı yeniden deneme | Önce yok, yürütmeden sonra var | 2., 3. ve 4. adım | İş bitti |
| 15 | Onaylı yeniden deneme | Onaydan sonra değişti | Yok, yanıt 409 | Olay kuyrukta |
| 16 | Silme olayı, iş bitmiş | Okuma hatası | Yok | İş bitti, olay kuyruğa girmez |
| 17 | Mutabakat, olay hiç gelmedi | Kullanıcı listede yok | 2., 3. ve 4. adım | İş bitti |
| 18 | İş biter, eski kayıtlar var | Okuma yok | Beş adım | Hiçbir kayıt kimliği tutmaz |
| 19 | İş biter, kayıt yazması hata verir | Okuma yok | Yeniden denemede yok | İş bitti, hiçbir kayıt kimliği tutmaz |
| 20 | Onaylı yeniden deneme, kuyrukta iş ve aynı kullanıcının eski olayı var | Okuma yok | Yalnız işin kalan adımları | İş bitti, eski olay yeniden kaydedilmez |
| 21 | İş bittikten sonra aynı hesabın başka olayı gelir | Okuma yok | Yok | Olay kaydedilmez, hiçbir kayıt kimliği tutmaz |

Adımlar şunlardır:

1. Keycloak kullanıcısını kapatma.
2. Press kullanıcısını kapatma.
3. Kiracıda kapatma ve telefon kurulumlarını iptal.
4. Press'te ve kiracıda anonim yapma.
5. Keycloak kullanıcısını silme.

- 8. satırda servis hiçbir şeyi anonim yapmaz. Çünkü Keycloak kullanıcının durduğunu söyler.
- 13. ve 14. satırda plan, onaylandığı kaydın altında kalır. Yürütme Keycloak'ı yeniden okumaz.
- 17. satırda fark listesi kullanıcıyı Keycloak kimliğiyle anar. Sözleşme bu alanı mutabakat okuru için tanımlar. Önizleme ve sonuç iş kimliğini gösterir.
- 19. satırda bitiş kaydı ve kimlik temizliği tek kayıt işlemidir. Yazma başarısız olursa iş bitmiş sayılmaz.
- 20. satırda servis her olaydan önce kaydın hâlâ kuyrukta olduğunu veritabanından doğrular. Bellekteki kopyayı çalıştırmaz.
- 16. ve 21. satırda servis hesabın silindiğini yalnız işin anahtarlı özetinden bilir. Geç gelen olayı çalıştırmaz ve kaydetmez.
- Silme işi kuyrukta ya da bitmişse o hesabın öteki olayları da yanıtta hesap kimliğini göstermez.

## Olay dinleyici eklentisi

Keycloak olayları kimlik-realm işinin kurduğu eklentiden gelir. Eklenti olayı imzalar ve `POST /v1/events` ucuna gönderir.

- Eklentinin imza kodu bu servisin alıcısıyla denendi. `tests/test_server.py` içindeki `ForkedListenerTest` sınıfı eklentinin ürettiği bir imzayı sabit veri olarak taşır.
- İmza anahtarı en az 16 karakter olmalıdır. Eklenti de daha kısa anahtarı reddeder.

## Oturum kapatma

Kullanıcı bir telefon kurulumunu iptal edince kiracı sitesi `POST /v1/sessions/revoke` ucunu çağırır. Gövde `sid` ve `subject` alanlarını taşır.

- Servis kiracıyı belirtecin `azp` değerinden bulur. Örneğin `site-tenant1-service` istemcisi `kiraci1` kiracısıdır.
- Her kiracının iki istemcisi vardır. `site-kiraci1` yalnız tarayıcı girişi içindir ve servis hesabı yoktur. `site-tenant1-service` yalnız servis hesabıdır.
- Tarayıcı istemcisi hiçbir listeye yazılamaz. Yazılırsa servis açılmaz ve nedeni söyler.
- Tarayıcı istemcisinin `azp` değeriyle gelen belirteç her uçta 401 alır.
- Kullanıcı o kiracının kuruluşuna üye değilse servis 403 döner.
- Servis yalnız o kullanıcının oturum listesindeki oturumu siler. Yenileme belirteci de geçersiz olur.
- Uç tekrar edilebilir. Oturum zaten kapalıysa servis yine 200 döner.
- Ucu yalnız `IDENTITY_SYNC_SESSION_AZP` listesindeki istemci çağırabilir. Bu liste kiracı sitelerinin servis istemcilerini taşır.
- Yeni kiracı eklerken istemcisini bu listeye de yazın. Yazmazsanız o kiracı oturum kapatamaz.
- Bu istemciler öteki uçları çağıramaz.

## Yetki tablosu

Bu tablo her ucu her çağıran türüyle gösterir. Tabloyu `tests/test_access_matrix.py` dosyası gerçek HTTP girişinden sınar. Reddedilen hiçbir çağıran hedefe yazmaz. Test bunu da denetler.

| Uç | Belirteçsiz | Listede olmayan istemci | Yanlış `azp` | Yanlış `aud` | Süresi dolmuş | Başka kiracının istemcisi | Doğru istemci |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST /v1/reconcile`, önizleme | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | 200 |
| `POST /v1/reconcile`, yürütme | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | Kabul |
| `GET /v1/dead-letters` | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | 200 |
| `POST /v1/dead-letters/replay`, önizleme | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | 200 |
| `POST /v1/dead-letters/replay`, yürütme | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | Kabul |
| `GET /v1/operations` | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | 200 |
| `POST /v1/operations/{kimlik}/resolve` | 401 | 401 | 403 | 401 | 401 | Kiracıya bağlı değil | Kabul |
| `POST /v1/invitations`, önizleme | 401 | 401 | 403 | 401 | 401 | 403 | 200 |
| `POST /v1/invitations`, yürütme | 401 | 401 | 403 | 401 | 401 | 403 | Kabul |
| `POST /v1/sessions/revoke` | 401 | 401 | 403 | 401 | 401 | 403 | 200 |
| `POST /v1/account-deletions` | 401 | 401 | 403 | 401 | 401 | 403 | 200 |
| `POST /v1/events` | 401 | 401 | 401 | 401 | 401 | 401 | 202, imzayla |
| `GET /healthz` | 200 | 200 | 200 | 200 | 200 | 200 | 200 |

- “Kabul” şu demektir: istek yetki denetimini geçer ve işleyiciye ulaşır. Testte bu satırlar eski bir özet gönderir ve 409 alır. Çözme ucu olmayan bir işlem için 404 alır.
- Tarayıcı istemcisi (`site-kiraci1`) hiçbir listede değildir. Bu yüzden “Listede olmayan istemci” sütunundaki gibi her belirteçli uçta 401 alır. Test bunu ayrı bir sütun olarak sınar.
- “Yanlış `azp`” listede olan ama bu uç için yetkisi olmayan istemcidir. Örneğin önizleme istemcisi yürütme isterse 403 alır.
- Yanlış `aud` ve süresi dolmuş belirteç sütunları gerçek `oidc_verify` kitaplığını ister. Kitaplık yoksa bu iki sütunun testi atlanır.
- Olay ucu belirteç kabul etmez. Yalnız imzayı kabul eder. Bozuk imza, eski zaman damgası ve ikinci kez kullanılan imza 401 alır.
- Sağlık ucu kimlik istemez. Yanıt yalnız servisin ayakta olduğunu söyler.
- Mutabakat, yeniden işletme ve işlem uçları bütün platformda çalışır. Bu yüzden tek kiracıya bağlı değildir. Yürütme listesindeki her kiracı istemcisi bu uçları çağırabilir.

## İstek sınırı

Bir istemci adresi bir dakikada en çok 600 istek gönderebilir. Sınırı `IDENTITY_SYNC_RATE_LIMIT` ayarı değiştirir.

- Sınır aşılınca servis 429 ve `rate_limited` döner. Servis o isteğin gövdesini okumaz.
- Sınır belirteç istemeyen uçları da kapsar. Bunlar `/healthz` ve `/v1/events` uçlarıdır.
- Sayaç bellekte durur ve dakika bitince sıfırlanır.

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

Proje kaydı Keycloak kullanıcı kimliğini kişisel veri sayar. Servisin kayıt dosyası bu kimliği tutar. E-posta ve ad tutmaz.

| Kayıt | Tutulan alan | Saklama süresi | Silme yolu |
| --- | --- | --- | --- |
| Bekleme kuyruğu | Olaydaki kullanıcı kimliği | Olay işlenene kadar | Olay işlenince servis satırı siler |
| İşlem günlüğü | Davet edilen kullanıcının kimliği | İşlem bitene ya da çözülene kadar | Servis alanı boşaltır |
| Bütün kayıtlar | Hesabı silinen kullanıcının kimliği | Silme işi bitene kadar | Silme işi bitince servis kalan alanları boşaltır |
| İşlenen olaylar ve onaylar | Yalnız olay, iş ve onay kimliği | Süresiz | Kullanıcı kimliği taşımaz |

- Silme işinin kimliği hesabın anahtarlı özetidir. Kimlikten kullanıcı bulunamaz.
- Hata kaydı yanıt gövdesini taşımaz. Yalnız adımı ve durum kodunu taşır.
- Günlük e-posta, belirteç ve oturum kimliği yazmaz.
- Mutabakat raporu e-posta taşımaz. Kullanıcıyı Keycloak kimliğiyle anar.

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

## Container

Servisin container dosyası bu klasördeki `Dockerfile` dosyasıdır. İmaj servisi `oidc_verify` kitaplığıyla kurar.

Kitaplık `backend/libs/oidc_verify` klasöründedir. Bu yüzden derlemeyi `backend` klasöründen başlatın:

```bash
docker --context colima-factory build -f identity/identity_sync/Dockerfile -t fs-identity-sync .
```

- Temel imaj özetiyle sabitlidir. Sürüm Python 3.14'tür.
- Derleme `oidc_verify` kitaplığını içe aktaramazsa durur.
- Servis container içinde `identity` kullanıcısıyla çalışır. Bu kullanıcı yönetici değildir.
- Kayıt dosyası `/data` biriminde durur.
- İmaj hiçbir ayar ve sır taşımaz. Ayarları çalıştırırken ortam değişkeniyle verin. Adlar `.env.example` dosyasındadır.
- Container bütün ağ arayüzlerini dinler. Portu ana bilgisayarda yalnız `127.0.0.1` adresine bağlayın.

`oidc_verify` kitaplığı anahtar adresi için düz `http` kabul etmez. Tek istisna `localhost` ve geri döngü adresidir.

- `IDENTITY_SYNC_KEYCLOAK_INTERNAL_URL` ayarı `https` ile başlamalıdır ya da `localhost` adresini göstermelidir.
- Adres bu kurala uymazsa servis açılmaz. Servis nedeni tek satırla yazar ve 2 koduyla çıkar.
- Örneğin `http://keycloak:8080` adresi reddedilir.

Bu imaj 22 Kasım 2026 Pazar günü `colima-factory` profilinde derlendi ve ağsız denendi. Deneme imajı ve container'ı sonra silindi.

## Performans ölçümü

Proje kaydının O-31 kararı iki sınır koyar. Okuma ucunda p95 en çok 500 milisaniyedir. Yazma ucunda p95 en çok 1 saniyedir. p95, çağrıların yüzde 95'inin altında kaldığı süredir.

Ölçümü elle başlatın. Şu sırayı izleyin:

1. Bu klasöre geçin.
2. Komutu çalıştırın. Komut sonucu bir dosyaya yazar:

   ```bash
   python3 -m tests.measure > olcum-sonucu.json
   ```

3. Komutun çıkış kodunu denetleyin. 0 kodu, bütün uçların sınırın altında kaldığını gösterir. 1 kodu, bir sınırın aşıldığını ya da bir isteğin hata verdiğini gösterir.
4. `olcum-sonucu.json` dosyasını açın. `endpoints` listesindeki her satır bir ucun sonucudur.
5. Her uç için şu değerleri durum dosyasına tablo olarak yazın: `endpoint`, `kind`, `calls`, `p95_ms`, `limit_ms`, `errors`, `concurrent_errors` ve `concurrent_requests`.
6. Tablonun altına ölçüm gününü, Python sürümünü ve `passed` değerini yazın.
7. `olcum-sonucu.json` dosyasını silin. Bu dosya depoya girmez.

Proje kaydının O-31 kararı sonucun durum dosyasına yazılmasını ister. Durum dosyası `.pane/prompts/durum.md` yolundadır.

- Komut zamanlanmaz. Yalnız siz başlatınca çalışır.
- Bu servis bir Frappe sitesi değildir. Geliştirme kurulumu, gerçek HTTP sunucusu ile sahte Keycloak, Press ve kiracıdır. Komut bu kurulumu açar. Ağa çıkmaz.
- Örnek veri 200 uydurma kullanıcıdır. Liste uçları için kuyrukta 50 olay ve günlükte 50 açık işlem vardır.
- Komut sözleşmedeki her ucu ölçer. Her ucu 50 kez sırayla, sonra 20 kez aynı anda çağırır.
- Önizleme ve yürütme biçimi olan uç iki biçimde de ölçülür. Önizleme okuma, yürütme yazma sayılır.
- Komut sonucu JSON olarak yazar. Bir sınır aşılırsa ya da bir istek hata verirse 1 koduyla çıkar.
- Sayıları `--samples`, `--concurrency` ve `--users` seçenekleri değiştirir.
- Tam ölçüm dakikada 600 istekten fazlasını gönderir. Komut bu yüzden istek sınırını ölçüm süresince yükseltir. Rapor bunu `rate_limit_raised` alanında yazar.

Bir test, komutun sözleşmedeki bütün uçları ölçtüğünü denetler. Yeni bir uç eklenip ölçüme eklenmezse test başarısız olur.

Sonucu okurken şunları bilin:

- Süre istemcide ölçülür. Yani sunucu süresine yerel ağ gidiş dönüşü eklenir.
- Sahte hedefler hemen yanıt verir. Sayılar bu servisin maliyetini gösterir. Keycloak, Press ve kiracı sitesinin süresini göstermez.
- Mutabakat ve yeniden işletme uçları aynı anda tek onaylı planı yürütür. Aynı önizleme için verilen 20 onaydan biri çalışır. Ötekiler 409 alır ve hiçbir şey yazmaz. Rapor bunları hata saymaz, `concurrent_conflicts` alanında verir.
- Sunucu istekleri tek tek işler. 20 istek aynı anda gelirse sonuncusu öncekileri bekler. Rapor bu bekleme süresini `concurrent_wait_p95_ms` alanında verir. Bu alan sınırla karşılaştırılmaz.

## Bilinen eksikler

Bu maddeler bilerek bırakılan eksiklerdir. Her biri bir teknik borçtur. `BORC(mvp)` işareti, eksiğin MVP seviyesini tamamlamayı engellediğini gösterir.

- `BORC(mvp)`: Servis canlı Keycloak, Press ve kiracı ile denenmedi. Olay eklentisinin yalnız imza kodu denendi. Etki: Sahte hedeflerin kaçırdığı bir uyumsuzluk üretimde ortaya çıkabilir. Sorumlu: integration-e2e işi. Kapanma koşulu: Uçtan uca test gerçek servislerle geçer.
- `BORC(mvp)`: `list_identities` satırı e-posta ve takım taşımaz. Etki: Mutabakat, var olan kaydın e-posta farkını ve fazla takım üyeliğini göremez. Sorumlu: orkestratör. Kapanma koşulu: Bu iki farkın nasıl bulunacağı sözleşmeye yazılır ya da farklar kapsam dışı sayılır.
- `BORC(mvp)`: Bu servisin testleri ve biçim denetimi CI'da koşmaz. Etki: Bozulma yalnız elle çalıştırılan testte görülür. Sorumlu: DevOps sorumlusu. Kapanma koşulu: CI bu klasörün testlerini her değişiklikte koşar.
