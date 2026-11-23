# Canlı ortamlar ve dağıtım hattı

Bu belge ürünün Hetzner sunucularına nasıl çıkacağını anlatır. Belge 23 Kasım 2026 Pazartesi günü yazıldı.

Kod `backend/deploy/` klasöründedir. Bu belge o kodun tasarımıdır.

Belge yalnız tasarımdır. Henüz hiçbir sunucu kurulmadı. Hiçbir dağıtım yapılmadı.

## Proje sahibinin kararları

Proje sahibi şu kararları 23 Kasım 2026 Pazartesi günü verdi:

1. Önce MVP biter. Sonra ürün Hetzner sunucusunda canlıya çıkar.
2. Dağıtım hattı Jenkins ile kurulur.
3. GitHub Actions yalnız pull request test kapısı olarak kalır.
4. Ana dal güncellenince alpha ortamı kendiliğinden güncellenir.
5. Sonraki ortamlara geçiş Jenkins'te elle basılan düğmeyle olur. Sıra alpha, beta, rc ve prod şeklindedir.
6. alpha, beta ve rc birer alt alan adıdır. Prod ana alan adındadır: `atonota.net`.
7. Keycloak'ın prod adresi `id.atonota.net` olarak kalır. Bu adres proje kaydındaki O-1 kararıdır.

## Sözlük

Bu belgede şu kelimeler geçer:

- **Ortam**, ürünün ayrı çalışan bir kopyasıdır. Her ortamın kendi verisi ve kendi sırları vardır.
- **Sürüm paketi**, bir kez derlenen kod paketidir. Paket konteyner imajlarından ve arayüz dosyalarından oluşur.
- **İmaj özeti**, imajın içeriğinden hesaplanan değişmez koddur. Örneğin `sha256:4c6e...` bir özettir.
- **Taşıma**, aynı sürüm paketini bir sonraki ortama koymaktır. Taşımada kod yeniden derlenmez.
- **Geri dönüş**, bir ortamı önceki sürüm paketine döndürmektir.
- **Sağlık denetimi**, ortamın çalıştığını dışarıdan sınayan denetimdir.
- **Ön vekil**, sunucunun internete açık tek kapısıdır. Bu projede ön vekil Caddy'dir.

## Dört ortam

| Ortam | Amacı | Kim kullanır | Nasıl güncellenir |
| --- | --- | --- | --- |
| alpha | Ana daldaki son kodu denemek | Geliştirme ekibi | Ana dal güncellenince kendiliğinden |
| beta | Ürün ekibinin iç denemesi | Ürün sahibi ve test ekibi | Jenkins'te "Move to beta" düğmesiyle |
| rc | Prod'un aynısında son kabul denemesi | Test ekibi ve DevOps sorumlusu | Jenkins'te "Move to rc" düğmesiyle |
| prod | Gerçek müşteri | Müşteriler | Jenkins'te "Move to prod" düğmesiyle |

Her ortamın kuralları `backend/deploy/environments/` klasöründedir. Bu dosyalarda sır yoktur.

rc ve prod ortamları daha sıkıdır:

- Sürüm paketinde her parça bulunmalıdır. Örneğin Press imajı eksikse rc dağıtımı reddeder.
- Yedeğin sunucu dışına kopyası başarılı olmalıdır. Kopya başarısızsa dağıtım başlamaz.
- Hata olursa veritabanı kendiliğinden geri yüklenmez. Bu kararı DevOps sorumlusu verir.

alpha ortamında hata olursa hat yedeği kendiliğinden geri yükler. alpha verisi deneme verisidir.

## Alan adı haritası

Kararım şudur: her ortamın bir temel adı vardır. Öteki adlar bu temel adın önüne eklenir.

| Ad | alpha | beta | rc | prod |
| --- | --- | --- | --- | --- |
| Temel ad | `alpha.atonota.net` | `beta.atonota.net` | `rc.atonota.net` | `atonota.net` |
| Keycloak | `id.alpha.atonota.net` | `id.beta.atonota.net` | `id.rc.atonota.net` | `id.atonota.net` |
| Press | `press.alpha.atonota.net` | `press.beta.atonota.net` | `press.rc.atonota.net` | `press.atonota.net` |
| Kiracı bölgesi | `*.app.alpha.atonota.net` | `*.app.beta.atonota.net` | `*.app.rc.atonota.net` | `*.app.atonota.net` |
| İlk kiracı | `demo.app.alpha.atonota.net` | `demo.app.beta.atonota.net` | `demo.app.rc.atonota.net` | `demo.app.atonota.net` |
| Panel | `https://<kiracı>/panel` | aynı | aynı | aynı |

Jenkins için ayrıca `ci.atonota.net` adı açılır. Bu ad yalnız GitHub bildirimini alır.

### Gerekçe

1. Her ortamda adların biçimi aynıdır. Ortam dosyası yalnız temel adı değiştirir.
2. Keycloak'ın prod adı `id.atonota.net` olarak kalır. O-1 kararı bozulmaz.
3. Kiracı adları karar sitesindeki K-2 biçimini korur. K-2'de kiracılar `<kiracı>.app.<marka>` biçimindedir.
4. Panel her kiracının kendi adresinde `/panel` yolundadır. Ayrı bir `panel.` adı açılmaz. Nedeni şudur: panel Frappe çerezini ve CSRF belirtecini aynı kökten okur (SZ-7). CSRF belirteci, sahte istekleri engelleyen tek kullanımlık koddur.
5. Prod temel adı `atonota.net` markanın tanıtım sayfasıdır. Tanıtım sayfası henüz yok. Bu yüzden temel ad şimdilik ilk kiracının paneline yönlendirir.

Bir kural daha geçerlidir. Hiçbir servis `Domain=atonota.net` çerezi yazmaz. Yazarsa prod çerezi alpha'ya da gider. Frappe ve Keycloak çerezleri yalnız kendi adlarında geçerlidir.

## Hetzner yerleşimi

Kararım dört sunucudur:

| Sunucu adı | İçinde ne var | Neden |
| --- | --- | --- |
| `atonota-ci` | Jenkins ve derleme ajanı | Derleme ürün sunucusunun kaynağını tüketmez |
| `atonota-nonprod` | alpha ve beta | İki deneme ortamı tek sunucuyu paylaşır |
| `atonota-rc` | rc | rc, prod'un aynı tip sunucusunda sınanır |
| `atonota-prod` | prod | Prod hiçbir ortamla sunucu paylaşmaz |

Sunucu tipini DevOps sorumlusu seçer. rc ve prod aynı tip olur. Sunucu tipini ölçümle seçin. Proje kaydında üretim işçi sayısı henüz ölçülmedi.

### Bir sunucunun içi

Her ortam ayrı bir Docker Compose projesidir. Compose, birden çok konteyneri birlikte yöneten araçtır. Proje adı `atonota-<ortam>` olur. Örneğin `atonota-alpha`.

Her ortamın kendi veritabanı, kendi birimleri ve kendi iç ağı vardır. Ortamlar birbirinin veritabanını göremez.

Her sunucuda tek bir ön vekil vardır. Ön vekil 80 ve 443 portlarını açar. Öteki hiçbir servis port açmaz.

Ön vekil her ortamın servislerine o ortamın kendi ağından ulaşır. Ağın adı `atonota-edge-<ortam>` olur. Örneğin `atonota-edge-alpha` bir ağdır. Bu ağda yalnız üç servis vardır: kiracı ön yüzü, Keycloak ve Press ön yüzü. Veritabanları bu ağda değildir.

Ortamlar aynı ağı paylaşmaz. Bu yüzden alpha'daki bir konteyner beta'nın Keycloak'ına doğrudan ulaşamaz. `remote/apply` betiği ağı açar. Betik ön vekilin ağ listesini de `networks.yaml` dosyasına yazar.

Dosyalar şunlardır:

- `backend/deploy/compose/stack.yaml` dosyası bir ortamın servislerini tanımlar.
- `backend/deploy/compose/edge.yaml` dosyası ön vekili tanımlar.
- `backend/deploy/compose/Caddyfile` dosyası ön vekilin genel ayarını tutar.
- `backend/deploy/compose/site.caddy.template` dosyası bir ortamın adlarını tutar. Dağıtım betiği bu şablonu doldurur.

### Ağ ve erişim

1. Hetzner güvenlik duvarı yalnız 80 ve 443 portlarını internete açar.
2. SSH portu internete kapalıdır. Jenkins sunuculara Tailscale ağı üzerinden bağlanır. Tailscale, sunucuları özel bir ağda birleştiren araçtır.
3. Jenkins arayüzü yalnız Tailscale ağında açılır.
4. `ci.atonota.net` adresi yalnız `/github-webhook/` yolunu Jenkins'e iletir. GitHub bildirimi gizli bir paylaşılan anahtarla imzalanır.
5. Keycloak yönetim konsolu herkese açık adreste kapalıdır. Ön vekil `/admin` ve `master` realm yollarına 404 yanıtı verir.

## Bir kez derle, aynı paketi taşı

Kural şudur: kod bir kez derlenir. Her ortam aynı paketi çalıştırır.

### Arka uç paketi

Arka uç paketinde dört imaj vardır:

- `atonota-tenant` imajı kiracı sitesini taşır. İçinde ERPNext, HRMS, `platform_core` ve `hrms_tr` vardır. İmajı `backend/deploy/images/tenant.Dockerfile` dosyası derler.
- `atonota-keycloak` imajı Keycloak'ı taşır. İmajı `backend/identity/keycloak/Dockerfile` dosyasının `prod` hedefi derler.
- `atonota-identity-sync` imajı kullanıcı eşitleme servisini taşır. İmajı `backend/identity/identity_sync/Dockerfile` dosyası derler.
- `atonota-press` imajı Press'i taşır. İçinde Press v0.154.1, `press_tr` ve `oidc_verify` vardır. İmajı `backend/deploy/images/press.Dockerfile` dosyası derler. Ayrıntı [Press imajı belgesindedir](press-imaji.md).

Press'in sunucu tarafı işleri henüz tam değildir. Kalan iş E-2 satırındadır.

İmajlar GitHub Container Registry'ye yüklenir. Adres `ghcr.io/karacaismail/atonota-<parça>` olur. Depo açık kaynaktır. İmajlarda sır yoktur.

Paketin kimliği `release.json` dosyasıdır. Dosya her imajı özetiyle yazar. Örnek:

```json
{
  "schema": 1,
  "kind": "backend",
  "release_id": "backend-36afb874abcd-b42",
  "commit": "<40 haneli Git kaydı>",
  "build": 42,
  "components": {
    "tenant": {"image": "ghcr.io/karacaismail/atonota-tenant@sha256:<64 hane>"}
  }
}
```

İmaj etiketle değil, özetle çağrılır. Etiket değişebilir. Özet değişmez.

### Paketin dağıtım dosyaları

Paket, imajlardan başka dağıtım dosyalarını da taşır. Bu dosyalar paketin `deploy/` klasöründedir:

- `compose/` klasöründeki `stack.yaml`, `edge.yaml`, `Caddyfile` ve site şablonu,
- `environments/` klasöründeki dört ortam dosyası,
- `remote/` klasöründeki sunucu betikleri.

Derleme işi bu dosyaları paketin commit'inden kopyalar. Bunu `release.py pack-deploy` komutu yapar. Komut her dosyanın SHA-256 özetini `deploy/files.json` dosyasına yazar. Jenkins paketi bu klasörle birlikte arşivler.

`bin/deploy` sunucuya yalnız paketteki dosyaları gönderir. Göndermeden önce `release.py check-deploy` komutu özetleri denetler. Eksik, değişmiş ya da fazla dosya varsa iş bağlanmadan durur. Arka uç paketinde dosyaların commit'i paketin commit'ine eşit olmalıdır.

Böylece rc ve prod, paketin alpha'da denendiği dosyaları alır. Ana dala sonradan giren bir `stack.yaml` eski paketle birlikte gitmez.

Taşıma işinin kendi kopyası yalnız iki şey verir: Jenkins tarafındaki betikler ve sunucuya bağlanma ayarı. Bağlanma ayarı ortam dosyasındaki `ATONOTA_SSH_HOST` ve `ATONOTA_SSH_USER` değerleridir.

Sunucudaki betik kopyaları da paketten gelir:

- Arka uç paketi kurulunca betikleri `/srv/atonota/<ortam>/bin/` klasörüne yazılır.
- Arayüz paketi kurulunca betikleri `/srv/atonota/web/<ortam>/bin/` klasörüne yazılır.
- Geri dönüş, o türün son kurulan paketinin betiğiyle çalışır.

Arayüz paketi arka uç betiklerine dokunmaz. Böylece eski bir arayüz paketi arka ucun geri dönüş betiğini eskitemez.

### Arayüz paketi

Arayüz `atonota-web` deposundadır. Paket, derlenmiş `dist` klasörünün `tar.gz` arşividir. Arşivin SHA-256 özeti `release.json` dosyasına yazılır.

Arşiv her derlemede aynı baytlarla üretilir. Dosya sırası, sahibi ve zamanı sabittir.

### Arayüz nasıl sunulur

Kararım şudur:

1. Panelin HTML sayfası Frappe'nin `/panel` sayfasıdır. Bu sayfa oturumu denetler. Sayfaya CSRF belirtecini ve güvenlik başlıklarını koyar.
2. Arayüzün betik ve stil dosyaları `/panel/assets/` yolundan sunulur. Bu dosyaları ön vekil sunucudaki arayüz paketinden verir.
3. Arayüz `--base=/panel/` ile derlenir.

Bugün `/panel` sayfası arayüz dosyalarını yüklemiyor. Bu bir engeldir (E-3).

## Jenkins hattı

Üç Jenkins işi vardır. Dosyalar `backend/deploy/jenkins/` klasöründedir.

| Dosya | Ne yapar | Nasıl başlar |
| --- | --- | --- |
| `backend.Jenkinsfile` | Arka uç paketini derler. Paketi alpha'ya ve beta'ya koyar | Ana dala push |
| `web.Jenkinsfile` | Arayüz paketini derler. Paketi alpha'ya ve beta'ya koyar | `atonota-web` ana dalına push |
| `promote.Jenkinsfile` | Paketi rc'ye ya da prod'a taşır. Bir ortamı geri döndürür. Yarıda kalan taşımayı sürdürür | Elle |

### Jenkins klasörleri ve anahtarlar

Her ortamın kendi SSH anahtarı vardır. Her ortamın sunucuda kendi kullanıcısı da vardır. Kullanıcının adı `deploy-<ortam>` olur. Örneğin alpha'nın kullanıcısı `deploy-alpha` olur.

Jenkins'te iki klasör vardır. Bir klasördeki iş yalnız o klasörün anahtarlarını görür.

| Klasör | İşler | Anahtarlar |
| --- | --- | --- |
| `atonota-delivery` | `atonota-backend`, `atonota-web`, `atonota-promote` | alpha ve beta |
| `atonota-release` | `atonota-promote` | beta, rc ve prod |

Ana dala gelen bir değişiklik `atonota-delivery` klasöründe çalışır. Bu klasörde rc ve prod anahtarı yoktur. Bu yüzden değişiklik prod'a kendiliğinden bağlanamaz.

`atonota-release` klasöründeki iş kendiliğinden başlamaz. İşi bir kişi başlatır. Sonra onay düğmesine yetkili biri basar.

Sunucuda her anahtarın önünde `restrict` ve `from=` kısıtı vardır. Kısıt yönlendirmeyi kapatır. Kısıt bağlantıyı yalnız Jenkins ajanının adresinden kabul eder. Ayrıntı devir notundadır.

### Ana hat

Ana hatta adımlar şu sıradadır:

1. Jenkins ana daldaki kodu alır.
2. Jenkins kapıları koşar. Kapılar dağıtım testleri, modül sınırı denetimi, güvenlik denetimi ve uygulama testleridir.
3. Jenkins imajları derler ve yükler. Sonra `release.json` dosyasını yazar.
4. Jenkins paketi alpha'ya dağıtır.
5. Jenkins alpha'nın sağlık denetimini koşar. Denetim geçerse sunucuya sağlık kaydı yazar.
6. Hat "Move to beta" düğmesinde bekler. Beklerken bir Jenkins ajanını tutmaz.
7. Biri düğmeye basarsa Jenkins taşıma denetimini koşar. Sonra paketi beta'ya dağıtır ve denetler.
8. rc ve prod için `atonota-release/atonota-promote` işi kullanılır. İş önceki ortamda çalışan paketi taşır.

Onaydan sonraki aşama ilk aşamanın dosyalarını kullanır. Jenkins ilk aşamada dağıtım betiklerini ve paketi saklar. Sonraki aşama bu saklanan kopyaları alır. Aşama ana daldan yeni kod almaz. Böylece beta'ya da aynı commit ve aynı imaj özeti dağıtılır. Bu kural rc ve prod için de geçerlidir. Orada dosyalar paketin arşivinden gelir.

### Elle taşıma

`promote.Jenkinsfile` şu sırayla çalışır:

1. İş önceki ortamın sunucusundan iki dosya alır: o an çalışan paketin `release.json` dosyası ve sağlık kaydı.
2. İş paketin derleme numarasını okur. Sonra o derlemenin Jenkins arşivindeki `release.json` dosyasını alır.
3. Sunucudaki kopya arşivdeki kopyayla aynı olmalıdır. Değilse iş durur.
4. İş taşıma denetimini koşar.
5. İş onay düğmesinde bekler. Beklerken bir Jenkins ajanını tutmaz.
6. Onaydan sonra iş 1. adımdan 4. adıma kadar denetimi yeniden koşar. Önceki ortam bu arada değiştiyse iş durur.
7. İş arşivdeki kopyayı hedef ortama dağıtır. Kopyada dağıtım dosyaları da vardır.

Böylece sunucu yalnız hangi paketin çalıştığını söyler. Dağıtılan dosyalar Jenkins'in kendi arşivinden gelir. Ele geçen bir alt ortam sunucusu prod'a başka bir imaj taşıtamaz.

Jenkins arşivi son 100 derlemeyi tutar. Daha eski bir paket taşınamaz.

Dağıtım dosyası olmadan arşivlenmiş eski bir paket de taşınamaz. Bu paketi yeniden derleyin.

Taşıma denetimi `backend/deploy/release.py` dosyasındadır. Denetim şu durumlarda taşımayı reddeder:

- Paket dosyasının biçimi bozuksa. Örneğin derleme numarası tam sayı değilse.

- Paket önceki ortamda çalışan paket değilse.
- Önceki ortamın sağlık kaydı bu paket için yoksa.
- Bir ortam atlanıyorsa. Örneğin beta'dan doğrudan prod'a geçilemez.
- Paket hedef ortamın kuralına uymuyorsa. Örneğin rc eksik parça kabul etmez.

Düğmeye herkes basamaz. beta ve rc düğmesine `atonota-deployers` grubu basar. prod düğmesine `atonota-release-managers` grubu basar.

### Yeni derleme eskisini geçer

Ana dala yeni bir push gelebilir. O sırada eski derleme bir düğmede bekleyebilir. Yeni derleme alpha'ya geçince eski derleme durur. Bunu Jenkins'in `milestone` adımı yapar.

Eski bir paketi taşımak gerekirse `promote.Jenkinsfile` işini kullanın. Bu iş önceki ortamda o an çalışan paketi taşır.

### Aynı ortama iki dağıtım olmaz

Her ortamın bir kilidi vardır. Örneğin `atonota-beta`. İki iş aynı ortama aynı anda dağıtım yapamaz.

## Veritabanı taşıma, yedek ve geri dönüş

### Dağıtım sırası

Sunucudaki `backend/deploy/remote/apply` betiği arka uç paketini şu sırayla kurar:

1. Betik paketi "bekleyen sürüm" bağına yazar. Bağın adı `backend-pending` olur. Sonra paketin dosyalarını kopyalar.
2. Betik yeni imajları indirir. Eski sürüm bu sırada çalışmaya devam eder.
3. Betik siteleri bakım kipine alır. Sonra veri yazan bütün süreçleri durdurur. Bu süreçler Frappe ön yüzü, işçiler, soket sunucusu, Keycloak ve eşitleme servisidir.
4. Betik yedek alır. Yedekte kiracı siteleri, Keycloak veritabanı ve eşitleme servisinin veritabanı vardır. Bu sırada hiçbir süreç veri yazmaz. Bu yüzden yedekten sonra veri kaybolmaz.
5. Betik yeni Keycloak'ı başlatır. Keycloak kendi veritabanını açılışta günceller.
6. Betik her site için `bench migrate` komutunu koşar.
7. Betik bütün servisleri başlatır. Servisler sağlıklı olunca bakım kipini kapatır.
8. Betik ön vekilin ayarını yazar ve yeniden yükler.
9. Betik "şu anki sürüm" bağını yeni pakete çevirir. Sonra "bekleyen sürüm" bağını siler.

Bir adım başarısız olursa betik durur. Yeni paket "şu anki sürüm" olmaz.

Betik her adımda paketin `phase` dosyasına aşamanın adını yazar. Geri dönüş bu adı okur. Aşamalar sırasıyla şunlardır: `preparing`, `pulling`, `stopping`, `backing-up`, `migrating`, `migrated`, `starting` ve `done`.

prod ve rc sunucu dışı yedek ister. Yedeğin ayar dosyası yoksa betik bakım kipine girmeden durur.

Bir paket bekleyen sürümken yeni paket kurulmaz. Önce bekleyen paket geri alınır.

Aynı paket yeniden taşınabilir. Bu yalnız paket `preparing` ya da `pulling` aşamasında kaldıysa olur. O aşamalarda eski sürüm hâlâ çalışır.

Paket `stopping` aşamasına geçtiyse yeniden taşıma reddedilir. Eski sürüm o noktada durmuştur. Yedek de alınmış olabilir. Bu durumda iş durur ve kararı bir kişi verir. Kişinin üç seçeneği vardır: `rollback`, `rollback-restore` ya da `resume`.

Aşama hiçbir zaman geriye yazılmaz. Örneğin `migrating` aşaması `preparing` olamaz. Bu kuralı `remote/common.sh` dosyası uygular. Geri dönüş bir paketi bitirince aşamayı `abandoned` ya da `rolled-back` yapar. Bundan sonra aynı paket baştan taşınabilir.

İlk kurulumda çalışan sürüm yoktur. Bu durumda betik yalnız `ATONOTA_FIRST_INSTALL=1` ile çalışır. İlk kurulum adımları devir notundadır.

### Taşıma kuralı

Veritabanı değişikliği iki sürüme yayılır. Bu kurala "genişlet, sonra daralt" denir.

1. Yeni sürüm yalnız ekler. Örneğin yeni alan ekler. Eski alanı silmez.
2. Eski kod yeni tabloda da çalışır.
3. Eski alan bir sonraki sürümde silinir.

Bir örnek verelim. Bir alanın adı değişecekse önce yeni alan eklenir. Eski alan bir sonraki sürümde kalkar.

Bu kural tutarsa geri dönüşte veritabanını geri yüklemek gerekmez.

### Yedek

- Yedek her arka uç dağıtımından önce alınır.
- Yedek sunucuda `/srv/atonota/<ortam>/backups/<zaman>/` klasörüne yazılır.
- Yedek klasöründe bir `SHA256SUMS` dosyası vardır. Geri yükleme önce bu özetleri denetler.
- Sunucu dışı kopya Hetzner Object Storage'a gider. Kopyayı `rclone` aracı yapar.
- rc ve prod'da sunucu dışı kopya zorunludur.
- Yedeği yalnız bir kişi ya da bir dağıtım başlatır. Zamanlanmış yedek yoktur.

Elle yedek almak için DevOps sorumlusu sunucuda şu komutu çalıştırır:

```sh
/srv/atonota/prod/bin/backup prod /srv/atonota/prod/backend-current
```

### Geri dönüş

Geri dönüşün komutu şudur:

```sh
rollback <ortam> <backend|web> [--failed <paket kimliği>] [--restore-backup]
```

Komutun seçenekleri şunlardır:

| Seçenek | Ne yapar |
| --- | --- |
| `--failed <paket kimliği>` | Yalnız bu paketi geri alır. Jenkins bir dağıtım başarısız olunca bu seçeneği kullanır. |
| Seçenek yok | Bir kişi geri dönüş istedi. Bekleyen paket varsa o geri alınır. Yoksa şu anki paket önceki pakete döner. |
| `--restore-backup` | Geri alınan paketten önceki yedeği de geri yükler. Yalnız arka uçta çalışır. |

Jenkins yalnız başarısız olan paketi geri alır. Sağlıklı çalışan paket hiç geri alınmaz. Kurallar şunlardır:

1. Başarısız paket bekleyen sürüm değilse ve şu anki sürüm de değilse hiçbir şey yapılmaz. Örneğin dosya kopyası yarıda kaldıysa çalışan paket olduğu gibi kalır.
2. Başarısız paket şu anki sürümse ve sağlık kaydı varsa hiçbir şey yapılmaz.
3. Başarısız paket şu anki sürümse ve sağlık kaydı yoksa paket geri alınır. Bu durum sağlık denetimi başarısız olunca oluşur.

Bekleyen bir paket ulaştığı aşamaya göre geri alınır:

| Aşama | Veritabanı | Geri dönüş ne yapar |
| --- | --- | --- |
| `preparing`, `pulling` | Değişmedi | Hiçbir şey yapmaz. Eski paket zaten çalışıyor. |
| `stopping`, `backing-up` | Değişmedi | Eski paketi yeniden başlatır. Bakım kipini kapatır. Yedeği geri yüklemez. |
| `migrating` | Yarıda kalmış olabilir | `--restore-backup` varsa yedeği geri yükler. Yoksa ortam bakım kipinde kalır ve komut hata verir. Kararı bir kişi verir. Kişi taşımayı elle bitirebilir. Sonra `resume` ile devam eder. |
| `migrated`, `starting` | Yeni şemada | Eski paketi başlatır. Taşıma kuralı sayesinde eski kod yeni şemada çalışır. |

Yedek yoksa veritabanı geri yüklenmez. Bu durumda komut hiçbir servisi durdurmaz. Ortam olduğu gibi açık kalır. Komut hatayı açıkça yazar.

Geri alınan paket `backend-failed` bağına yazılır. Bu paket hiç "önceki sürüm" olmaz. Bu yüzden ikinci bir geri dönüş başarısız pakete dönemez. İkinci geri dönüşü bir kişi elle seçer.

alpha'da Jenkins yedeği de kendiliğinden geri yükler. Öteki ortamlarda Jenkins yalnız imajları geri döndürür. Yedeği geri yükleme kararını DevOps sorumlusu verir. Bunun için `promote.Jenkinsfile` işinde `rollback-restore` seçilir.

`--restore-backup` yedekten sonra yazılan veriyi siler. prod'da önce bu kaybı onaylayın. Sonra komutu çalıştırın.

### Yarıda kalan taşımayı sürdürmek

Bazen `bench migrate` yarıda kalır. Kişi sorunu elle çözebilir. Örneğin bozuk bir kaydı düzeltir. Sonra taşımayı sürdürmek için `promote.Jenkinsfile` işinde `resume` seçilir.

`resume` şu sırayla çalışır:

1. Sunucu bekleyen paketin kendi `apply` betiğini `--resume` seçeneğiyle çalıştırır.
2. Paket `migrating` aşamasındaysa betik `bench migrate` komutunu yeniden koşar. Komut biten adımları atlar.
3. Paket `migrated` ya da `starting` aşamasındaysa taşıma atlanır.
4. Betik bütün servisleri başlatır ve bakım kipini kapatır.
5. Betik bağları çevirir. Bekleyen paket şu anki sürüm olur. Eski paket önceki sürüm olur.
6. Jenkins sağlık denetimini koşar. Denetim başarısız olursa paket geri alınır.

`resume` hiçbir servisi durdurmaz ve yeni yedek almaz. Paketin `backup-before` dosyası olduğu gibi kalır. Bu yüzden sonra yine `rollback-restore` yapılabilir.

`resume` yalnız `migrating`, `migrated` ve `starting` aşamalarında çalışır. Paket yedekten önce durduysa `resume` reddedilir. Bu durumda `rollback` eski sürümü başlatır.

## Sırlar

Depoda sır yoktur. Sırlar iki yerde durur:

| Yer | İçinde ne var | Kim yazar |
| --- | --- | --- |
| Jenkins kimlik bilgileri | Her ortamın kendi SSH anahtarı (`atonota-deploy-ssh-<ortam>`) ve `atonota-registry` GHCR belirteci | DevOps sorumlusu |
| Sunucuda `/etc/atonota/<ortam>/<servis>.env` | Veritabanı parolaları, Keycloak istemci sırları, SMTP parolası | DevOps sorumlusu |

Sunucudaki sır dosyaları şunlardır:

- `tenant.env` ve `tenant-db.env` dosyaları kiracı sitesinin ve MariaDB'nin sırlarını tutar.
- `keycloak.env` ve `keycloak-db.env` dosyaları Keycloak'ın ve PostgreSQL'in sırlarını tutar. Anahtar adları `backend/identity/keycloak/production.env.example` dosyasındadır.
- `identity-sync.env` dosyası eşitleme servisinin sırlarını tutar.
- `press.env` dosyası Press'in sırlarını tutar. Press servisleri bu dosyayı okur.
- `offsite.env` dosyası sunucu dışı yedeğin `rclone` adresini tutar.
- `/etc/atonota/edge.env` dosyası sertifika uyarısının gideceği e-posta adresini tutar.

Her dosyanın izni `0600` olur. Dosyanın sahibi o ortamın kullanıcısıdır. Örneğin alpha'nın dosyalarının sahibi `deploy-alpha` olur. Docker Compose bu dosyaları dağıtım kullanıcısıyla okur. Bu yüzden sahip `root` olamaz.

Jenkins uygulama sırlarını hiç görmez. Jenkins yalnız sunucuya bağlanır ve imaj yükler. Böylece Jenkins'in ele geçmesi veritabanı parolasını açmaz.

Dağıtım kullanıcıları `docker` grubundadır. Bu grup sunucuda root yetkisine denktir. Bu yüzden asıl sınır sunucudur. prod ve rc kendi sunucusundadır. alpha ve beta aynı sunucuyu paylaşır. Bu iki ortamın kullanıcıları ayrıdır. İki kullanıcı da o sunucuda root yetkisine denktir.

Bu yüzden beta onayı bir süreç adımıdır, güvenlik sınırı değildir. Ana dala yazan biri Jenkins dosyasını değiştirebilir. Değişen dosya alpha aşamasında beta anahtarını kullanabilir. alpha kullanıcısı beta'nın sağlık kaydını da yazabilir. Sonra paket beta'da denenmeden rc'ye taşınabilir. Bu yolu iki kural daraltır. rc onayı yine gerekir. Arşiv karşılaştırması da yine çalışır. beta'yı ayrı sunucuya taşımak bu açığı kapatır.

Alt ortamın sunucusu üst ortamda komut çalıştıramaz. Bunu üç kural sağlar:

1. Sunucuda Jenkins anahtarı durmaz. Jenkins anahtarı ajan yönlendirmesi olmadan kullanır.
2. Jenkins sunucudan aldığı dosyayı komuta koymadan önce denetler. Uzak komutun her sözcüğü tırnaklanır.
3. Taşınan paket Jenkins arşivinden gelir. Sunucudaki kopya yalnız karşılaştırılır.

Frappe'nin geri yükleme komutu veritabanı kök parolasını komut satırında ister. Sunucudaki öteki kullanıcılar bu satırı `ps` ile göremez. Bunun için `/proc` dizini `hidepid=invisible` seçeneğiyle bağlanır. Ayrıntı devir notundadır.

`hidepid` yalnız `docker` grubunda olmayan kullanıcıları korur. `docker` grubundaki kullanıcı bir konteyner açıp sunucunun bütün süreçlerini görebilir. Bu yüzden ayar, aynı sunucudaki öteki ortamın kullanıcısına karşı işe yaramaz. Bu iki ortam için sınır yine sunucudur.

Her ortamın sırları ayrıdır. alpha'nın parolası prod'da kullanılmaz.

## Kabul ölçütleri

Jenkins her dağıtımdan sonra `backend/deploy/bin/health` betiğini koşar. Betik ortama dışarıdan, HTTPS ile bakar.

Arka uç için şu denetimler geçmelidir:

1. Sunucu bu paketi "şu anki sürüm" olarak bildirir. Bütün konteynerler sağlıklıdır.
2. `https://<Keycloak>/realms/platform/.well-known/openid-configuration` yanıt verir. Yanıttaki `issuer` değeri ortamın Keycloak adresidir.
3. `https://<Keycloak>/admin/` adresi 404 döner.
4. Her kiracıda `/api/method/ping` adresi `pong` döner.
5. Her kiracıda oturumsuz `/panel` isteği `/login` sayfasına yönlenir.
6. Press imajı paketteyse `https://<Press>/api/method/ping` adresi `pong` döner. İmaj yoksa denetim `not_run` yazar.
7. Sertifika geçerlidir. `curl` geçersiz sertifikada hata verir.

Arayüz için şu denetim geçmelidir:

1. Arayüzün ana betiği her kiracıda `/panel/assets/` yolundan gelir.

Denetim geçince betik sunucuya sağlık kaydı yazar. Sonraki ortama taşıma bu kaydı ister.

Bu denetimler giriş akışını sınamaz. Giriş akışını beta'da test ekibi elle sınar. Gerçek servislerle uçtan uca test bir engeldir (E-9).

## Karar sitesiyle çelişkiler

Proje kaydı karar sitesinden önce gelir. Şu çelişkileri buldum:

| No | Karar sitesi | Bugünkü durum | Öneri |
| --- | --- | --- | --- |
| Ç-1 | P0: Press Frappe v15 ve Python 3.11 üzerinde | Backend Frappe 16 ve Python 3.14 kullanır (D-15) | P0 metni Frappe 16 ve Python 3.14 olarak düzeltilir |
| Ç-2 | P0 ve Rail 1: Route 53 bölgesi, NS devri ve joker sertifika | DNS GoDaddy'dedir. MVP'de Route 53 yoktur | MVP'de GoDaddy kaydı ve ad başına sertifika kullanılır. Route 53 kararı Press sunucu kurma akışı çalışınca yeniden açılır |
| Ç-3 | Adlar `<marka>.com.tr`. `panel.` Press'in adıdır | Marka adı `atonota.net`. Panel kiracının `/panel` yoludur | Rail 1 tablosu bu belgedeki harita ile değiştirilir |
| Ç-4 | P0: "Press staging ve prod" | Dört ortam vardır: alpha, beta, rc ve prod | "staging" yerine beta ve rc yazılır |
| Ç-5 | Yol haritası X-02 üç ortam sayar: Colima geliştirme, staging ve prod | Colima yalnız geliştirme içindir. Canlıda dört ortam vardır | X-02 dört ortamla yazılır |
| Ç-6 | Dağıtım hattı P1 içinde kurulur | Jenkins hattı canlıya çıkıştan önce gerekir | Dağıtım hattı P0'a alınır |
| Ç-7 | O-1: "Alan adının kayıt yeri doğrulanmadı" | Proje sahibi DNS'in GoDaddy'de olduğunu söyledi | O-1 notu "GoDaddy" olarak güncellenir |
| Ç-8 | P0: offsite yedek ve izleme uyarıları | Zamanlanmış iş yasağı vardır | Yedek yalnız dağıtımda ve elle alınır. Düzenli yedek için proje sahibinin kararı gerekir (E-7) |
| Ç-9 | `ci.yml` PR kapısı | Kapı yalnız siteyi ve `press-ai` paketini sınıyordu | Bu iş dağıtım testlerini kapıya ekledi. Backend testleri yine yalnız Jenkins'te koşar |

Bu belge karar sitesini değiştirmedi. Düzeltmeleri orkestratör ayrı bir işle yapar.

## Canlıya çıkışın önündeki engeller

| No | Engel | Önerilen çözüm | Sahibi |
| --- | --- | --- | --- |
| E-1 | Press'in sunucu kurma akışı Frappe 16'da çalışmıyor. 23 Kasım 2026 Pazartesi günü üretim imajında ansible-core 2.21.6 yerel bir oyunu çalıştırdı. Gerçek sunucu kurma denenmedi | MVP'de Press sunucu kurmaz. Kiracı sitesini DevOps sorumlusu ilk kurulumda elle açar. Kurma akışı hazırlık sunucusunda ayrıca sınanır | press-tr işi ve DevOps sorumlusu |
| E-2 | Press üretim imajı yazıldı ve Colima'da denendi ([Press imajı belgesi](press-imaji.md)). Kalan iş şudur: `remote/backup`, `remote/restore` ve `remote/apply` Press sitesini yedeklemez, geri yüklemez ve Press sitesinde `migrate` çalıştırmaz. Press'in migrate adımı Press'in kendi denetimi için internetten chromedriver indirmeye çalışır. İmaj sunucuda ve amd64'te denenmedi | press-tr işi betiklere Press sitesini ekler. Ekleme bitmeden rc ve prod'a Press'li paket taşınmaz. DevOps sorumlusu ilk kurulumda Press sitesini açar | press-tr işi ve DevOps sorumlusu |
| E-3 | `/panel` sayfası arayüz dosyalarını yüklemiyor. Sayfa yer tutucu metin gösteriyor | `panel.html`, arayüz paketinin Vite listesini okur. Sonra `/panel/assets/` dosyalarını yükler. İçerik güvenlik politikası bu yola izin verir | platform-core-kabuk işi |
| E-4 | Üretim ayarlarının listesi yok. Örneğin Keycloak istemci sırları, sitenin kimlik ayarları ve eşitleme servisinin kiracı listesi | Her servis için üretim anahtar listesi yazılır. Liste `production.env.example` biçiminde olur | kimlik-realm işi ve DevOps sorumlusu |
| E-5 | CI'da güvenlik kapısı yok (O-29) | `docs/handoff/ci-security.md` işleri Jenkins kapılarına eklenir | DevOps sorumlusu |
| E-6 | identity-sync testleri CI'da koşmuyor | Testler Jenkins kapılarına eklenir | DevOps sorumlusu |
| E-7 | Zamanlanmış iş yasağı var. Bu yüzden Frappe zamanlayıcısı kapalıdır. Düzenli yedek de yoktur | Proje sahibi karar verir. Zamanlayıcı `COMPOSE_PROFILES=scheduler` ile açılır | Proje sahibi |
| E-8 | Üretim işçi sayısı ölçülmedi | DevOps sorumlusu rc'de yük ölçer. `ATONOTA_GUNICORN_WORKERS` değerini ölçümle seçer | DevOps sorumlusu |
| E-9 | Gerçek servislerle uçtan uca test yok | Uçtan uca test beta'da gerçek Keycloak ve kiracıyla koşar | integration-e2e işi |
| E-10 | Sunucular, Jenkins, Tailscale ve GHCR hesabı yok | Devir notundaki adımlar uygulanır | DevOps sorumlusu |
| E-11 | GoDaddy'nin `*.app.alpha` gibi çok katlı joker kaydı kabul ettiği doğrulanmadı | Kayıt girilirken denenir. Kabul edilmezse her kiracı için ayrı A kaydı girilir | Alan adı sorumlusu |
| E-12 | E-posta aktarma sunucusu seçilmedi (G-47) | SMTP sağlayıcısı seçilir. Sırlar `keycloak.env` dosyasına yazılır | DevOps sorumlusu |
| E-13 | Arayüz ve arka uç ayrı taşınır. Bir ortamda uyumsuz ikili oluşabilir | Bir ortamda önce arka uç taşınır. Arayüz arka ucun sözleşmesini aşmaz | Orkestratör |
| E-14 | Gerçek müşteri verisi için KVKK aktarım bildirimi ve VERBİS kaydı bitmedi | prod'a gerçek veri girmeden önce hukuk onayı alınır | Hukuk ve ürün sahibi |
| E-15 | Üretim imajları Mac'te arm64 ile denendi. Hetzner sunucuları amd64 olabilir | Derleme ajanı sunucularla aynı mimaride olur | DevOps sorumlusu |

## Neler sınandı

- `backend/deploy/tests/test_release.py` dosyası paket kurallarını ve taşıma denetimini sınar.
- `backend/deploy/tests/test_remote.py` dosyası sunucu betiklerini sınar. Test sahte bir `docker` komutu kullanır. Test dağıtım sırasını, bağları ve geri dönüşü denetler. Test Linux'ta koşar.
- Geri dönüş testleri her aşamadaki hatayı ayrı sınar. Örneğin eksik dosya, imaj indirme hatası, yedek hatası, yarım taşıma ve sağlık hatası sınanır.
- Aynı paketin yeniden taşınması sınanır. Yarım taşımada yeniden taşıma reddedilir. Bekleyen bağ kalır ve sonraki paket kurulmaz. `resume` yolu iki aşamadan ayrı sınanır.
- `backend/deploy/tests/test_jenkins_side.py` dosyası Jenkins tarafını sınar. Test sahte `ssh` ve `scp` komutları kullanır. Test uzak komutun tırnaklandığını denetler. Test Jenkins dosyalarının anahtar ve aşama kurallarını da denetler.
- Sunucuya giden her dosyanın paketten geldiği sınanır. Değişmiş, eksik ya da başka commit'ten gelen dağıtım dosyası iş bağlanmadan reddedilir.
- Üretim kiracı imajı yerelde derlendi. İçinde `panel.bundle.css` ve `panel-focus.bundle.js` dosyaları var.
- Jenkins dosyaları Jenkins'in kendi denetleyicisinden geçti.

Şunlar sınanmadı:

- Gerçek sunucuda dağıtım.
- Gerçek veritabanında geri yükleme.
- Keycloak ve identity-sync imajlarının üretim derlemesi.
- Ön vekilin gerçek sertifika alması.
- Gerçek Jenkins'te onay, saklanan kopya ve arşivden kopya alma adımları. Jenkins denetleyicisi yalnız sözdizimini sınar.
