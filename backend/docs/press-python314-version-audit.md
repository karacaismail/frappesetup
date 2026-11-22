# Press sürüm taramasının sonucu

Tarama 22 Kasım 2026 Pazar günü tamamlandı.
İncelenen yeni sürümlerde yamasız yol bulunamadı. Bu araştırma kolu kapatıldı.
O-18 borcu açık kaldı. Çalışan Press sürümü yükseltilmedi.
Mevcut geliştirme yaması korunuyor.

## Kapsam

Resmî depoda 714 sürüm etiketi bulundu. Hepsi sürüm numarası taşıyordu.
`v0.154.1` sonrasındaki 162 etiket ayrı ayrı incelendi.
Bu aralık `v0.155.0` ile başlar. Son etiket `v0.204.1` olur.

Varsayılan dal `develop` olarak doğrulandı. `master` dalı da incelendi.
İki dosyanın dal geçmişleri ayrıca tarandı.

| Kaynak | Kapsam |
| --- | --- |
| Sonraki sürüm etiketleri | 162 etiket |
| `v0.154.1..develop` dosya geçmişi | 87 commit |
| `v0.154.1..master` dosya geçmişi | 31 commit |
| Güncel dal uçları | `develop` ve `master` |
| Farklı kaynak durumları | 269 commit |
| Farklı dosya içerikleri | 22 Git blobu |

Git blobu, Git'in sakladığı tek dosya içeriğidir.
Aynı blob kimliği, dosya içeriğinin aynı olduğunu gösterir.

`v0.154.1`, `develop` dalının atası değildir.
Bu nedenle develop geçmişi tarih bakımından daha eski kayıtlar da içerir.
Tablodaki 87 kayıt yalnız sonraki tarihli değişiklikler anlamına gelmez.
Git'in iki kaynak arasındaki erişilebilirlik farkının tamamı incelendi.
Aynı kayıt iki geçmişte bulunabilir. Sayılar doğrudan toplanarak farklı commit sayısı çıkarılmaz.

## Sabit kaynaklar

| Kaynak | Doğrulanan commit kodu |
| --- | --- |
| Başlangıç `v0.154.1` | `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` |
| Son etiket `v0.204.1` | `8ff1813f465cb18354a762479477ebad14ab3d7c` |
| Varsayılan `develop` dalı | `d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410` |
| `master` dalı | `a9a7acd487902e54253d38bd9ef79ce52be9bc86` |

Son etiket ve iki dal ucu 20 Kasım 2026 Cuma günü oluşturuldu.
İmaj denemesi dal adına bağlanmadı. Tam develop commit koduna sabitlendi.

## Kaynak kanıtı

İlk dosya `press/press/doctype/deploy_candidate/cache_utils.py` yolundadır.
Bu dosya 269 kaynak durumunun tamamında aynı içeriği taşıyor.
Blob kimliği `a599d6d5a083a2985eef6e5d016644d06fc8212d` olarak doğrulandı.
Dosyanın 11. satırı doğrudan `typing.TypedDict` alır.
Dosyanın 13. satırındaki tanım `cwd=str` gibi anahtar argümanlar kullanır.
Python 3.14 bu çağrıyı reddeder.

İkinci dosya `press/saas/doctype/product_trial_request/product_trial_request.py` yolundadır.
Bu dosyada 21 farklı içerik bulundu.
Bütün içeriklerde üst düzey `init_telemetry` import'u korunuyor.
Dosya eksikliği veya bu import'u kaldıran ara durum bulunmadı.
Son etiket ve iki dal ucunda ikinci dosyanın içeriği de aynıdır.
Bu içeriğin blob kimliği `7dd7680cf84fc2f41d192e42740026e4a436ff6f` olur.

Tam eşlemeler [makineyle okunabilen kanıt dosyasındadır](evidence/press-python314-versions.json).
`refs` alanı sürüm ve dal adlarını commit kodlarına bağlar.
`histories` alanı iki dal için taranan geçmiş kayıtlarını taşır.
`snapshots` alanı her commit kodunu telemetri dosyasının blobuna bağlar.
`cache_blob` alanı bütün bu kayıtlardaki ortak ilk dosyayı gösterir.
`telemetry_blobs` alanı her farklı içerikteki import satırını kaydeder.

Sürüm araştırmasını ayrı ajan yaptı. Ana ajan bütün eşlemeleri yeniden doğruladı.
Ana ajan resmî ref listesini yeniden aldı.
Ardından her kaydın iki blob kimliğini Git üzerinden karşılaştırdı.
Geçmiş listelerinin tamlığı ve 22 farklı dosyanın içeriği de doğrulandı.

[Son etiketin TypedDict kaynağı](https://github.com/frappe/press/blob/8ff1813f465cb18354a762479477ebad14ab3d7c/press/press/doctype/deploy_candidate/cache_utils.py#L11-L19)
[Develop telemetri kaynağı](https://github.com/frappe/press/blob/d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410/press/saas/doctype/product_trial_request/product_trial_request.py#L16)
[Master telemetri kaynağı](https://github.com/frappe/press/blob/a9a7acd487902e54253d38bd9ef79ce52be9bc86/press/saas/doctype/product_trial_request/product_trial_request.py#L16)

## Çalıştırılan kabul testleri

Yeni Frappe temel imajı üretilmedi.
Deneme `frappe/erpnext:v16.55.0` temel imajında çalıştı.
Gerçek Python sürümü 3.14.10 oldu. Gerçek Frappe sürümü 16.56.0 oldu.
Derleme tek başına çalıştırıldı. Aynı anda başka ağır derleme başlatılmadı.
Başlangıçta kullanılabilir bellek 49 GiB oldu. Boş disk 87 GB oldu.

```sh
PANE_PORT=47320 docker --context colima-factory build \
  --build-arg PRESS_REVISION=d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410 \
  -f backend/dev/press/Dockerfile.unpatched \
  -t fs-pd-press-py314:probe .

PANE_PORT=47320 docker --context colima-factory compose \
  -f backend/dev/press/compose.unpatched.yaml run --rm probe
```

| Denetim | Sonuç |
| --- | --- |
| Develop adayının derlenmesi | `pass` |
| Tam commit kodu ve boş Press `git diff HEAD` | `pass` |
| Beklenmeyen yeni Press dosyası bulunmaması | `pass` |
| Python 3.14 ve Frappe 16 sürüm denetimi | `pass` |
| Press yürütücüsü ve yerel Ansible görevi | `pass` |
| Standart modüller, Telegram ve Stripe import'u | `pass` |
| `cache_utils` ve bağımsız `TypedDict` denemesi | `fail` |
| Ürün denemesi modülü ve bağımsız telemetri import'u | `fail` |
| Son etiket ve master için ayrı imaj derlemesi | `not_run` |
| Site, HTTP ve Press masası | `not_run` |

On testin altısı geçti. Dördü aynı iki kaynak engeliyle kaldı.
Test komutu 1 koduyla çıktı. Hatalar beklenen başarı olarak işaretlenmedi.
Press dosyaları değiştirilmedi. Standart kitaplık gölgelenmedi.
Kaynak kodu bellekte değiştirilmedi.

Bağımsız inceleme, aday testlerinde iki yanlış ret riski buldu.
Telemetri testi, seçili kaynağın gerçek import satırlarını izlemek zorundadır.
Kaynak bu import'u kaldırırsa eski hata ayrıca üretilmez.
TypedDict testi de geçerli sınıf biçimini kabul etmek zorundadır.
Bu iki durum için regresyon testleri eklendi.
Gerçek modül açılışı testleri her adayda zorunlu kaldı.

Son etiket ve master için aynı deneme yeniden derlenmedi.
İki engeli taşıyan dosyalar bu üç kaynakta birebir aynıdır.
Site açılışının ön koşulu başarısız olduğundan site ve masa denenmedi.
Deneme imajı ayrıca tam Press bağımlılık kurulumu değildir.
Bu kapsamın dışında kalan işlevler çalışıyor diye sunulmaz.

## Diğer yolların sonucu

Alternatif yolları ikinci ajan inceledi.
Ana ajan kanca sırasını imajdaki gerçek Frappe dosyalarından doğruladı.

| Yol | Neden çözüm sağlamıyor? |
| --- | --- |
| `typing_extensions` veya farklı paket sürümü | Press doğrudan Python'un `typing` modülünü kullanır. Ek paket bu import'u değiştirmez. |
| `override_doctype_class` | Frappe önce özgün modülü yükler. Özel sınıf ancak bundan sonra uygulanır. |
| `extend_doctype_class` | Frappe genişletmeyi özgün sınıf yüklendikten sonra uygular. |
| Telemetriyi ayarla kapatma | Hata, ayar okunmadan önceki import satırında oluşur. |
| `posthog` paketini kurma | Paket, Frappe'den kaldırılan işlevi geri getirmez. |
| Python `-O` veya `-OO` seçeneği | Bu seçenekler normal modül atamasını ve import'u kaldırmaz. |
| Modülü geç yükleme veya atlama | Modül çalıştırıldığında aynı hata oluşur. Kabul koşulu karşılanmaz. |
| Eski modülü gölgeleme veya başlangıç yaması | Bu yollar kullanıcının açık sınırlarını ihlal eder. |
| Python veya Frappe ana sürümünü düşürme | Python 3.14 ve Frappe 16 hedefleri korunmaz. |

Kurulu Frappe kaynağında `frappe/model/document.py:140` özgün modülü yükler.
Özel sınıf seçimi bu çağrıdan sonra uygulanır.
Genişletme kancası `document.py:218` içinde okunur.
`frappe/modules/utils.py:291` standart DocType modülünü yükleyen işlevdir.
Bu işlev, özel sınıf kancasından bağımsız çalıştığını da belirtir.
Frappe telemetri kaynağında `init_telemetry` işlevi yoktur.

[Frappe denetleyici yükleme sırası](https://github.com/frappe/frappe/blob/v16.56.0/frappe/model/document.py#L126-L168)
[Frappe standart modül yükleyicisi](https://github.com/frappe/frappe/blob/v16.56.0/frappe/modules/utils.py#L291-L308)
[Python TypedDict sözleşmesi](https://docs.python.org/3.14/library/typing.html#typing.TypedDict)

## Kapanış kararı

İncelenen resmî sürümlerde ve belirtilen dal geçmişlerinde uygun kaynak bulunmadı.
Yeni Press sürümü seçilmedi. Geliştirme kaydı `v0.154.1` olarak kaldı.
Mevcut [Press önerisi](press-python314-upstream.md) geçerlidir. Öneri henüz gönderilmedi.
O-18 ve ilgili borç satırı açık kalır.
Bu sonuç yalnız kaydedilen tarama kapsamı ve tarih için geçerlidir.

Deneme container'ları ve geçici birimler kapatılıp silinir.
Bu görevin bütün imaj etiketleri de silinir.
Görev C için çalışan yamasız Press ortamı sağlanamadı.
Yeni commit, `8b91fcd` üzerine eklenir. Geçmiş yeniden yazılmaz.

Gerçek okurla denenmedi.
