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

Ön vekil servislere `atonota-edge` ağından ulaşır. Bu ağda yalnız üç servis vardır: kiracı ön yüzü, Keycloak ve Press. Veritabanları bu ağda değildir.

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

Arka uç paketinde üç imaj vardır:

- `atonota-tenant` imajı kiracı sitesini taşır. İçinde ERPNext, HRMS, `platform_core` ve `hrms_tr` vardır. İmajı `backend/deploy/images/tenant.Dockerfile` dosyası derler.
- `atonota-keycloak` imajı Keycloak'ı taşır. İmajı `backend/identity/keycloak/Dockerfile` dosyasının `prod` hedefi derler.
- `atonota-identity-sync` imajı kullanıcı eşitleme servisini taşır. İmajı `backend/identity/identity_sync/Dockerfile` dosyası derler.

Press imajı henüz yok. Bu bir engeldir (E-2). Press imajı eklenince pakete dördüncü parça olarak girer.

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
| `backend.Jenkinsfile` | Arka uç paketini derler ve taşır | Ana dala push |
| `web.Jenkinsfile` | Arayüz paketini derler ve taşır | `atonota-web` ana dalına push |
| `promote.Jenkinsfile` | Eski bir paketi taşır ya da geri döner | Elle |

### Ana hat

Ana hatta adımlar şu sıradadır:

1. Jenkins ana daldaki kodu alır.
2. Jenkins kapıları koşar. Kapılar dağıtım testleri, modül sınırı denetimi, güvenlik denetimi ve uygulama testleridir.
3. Jenkins imajları derler ve yükler. Sonra `release.json` dosyasını yazar.
4. Jenkins paketi alpha'ya dağıtır.
5. Jenkins alpha'nın sağlık denetimini koşar. Denetim geçerse sunucuya sağlık kaydı yazar.
6. Hat "Move to beta" düğmesinde bekler.
7. Biri düğmeye basarsa Jenkins taşıma denetimini koşar. Sonra paketi beta'ya dağıtır ve denetler.
8. rc ve prod için aynı adımlar tekrarlanır.

Taşıma denetimi `backend/deploy/release.py` dosyasındadır. Denetim şu durumlarda taşımayı reddeder:

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

1. Betik yeni imajları indirir. Eski sürüm bu sırada çalışmaya devam eder.
2. Betik yedek alır. Yedekte kiracı siteleri, Keycloak veritabanı ve eşitleme servisinin veritabanı vardır.
3. Betik siteleri bakım kipine alır. Sonra Frappe süreçlerini durdurur.
4. Betik yeni Keycloak'ı başlatır. Keycloak kendi veritabanını açılışta günceller.
5. Betik her site için `bench migrate` komutunu koşar.
6. Betik bütün servisleri başlatır. Servisler sağlıklı olunca bakım kipini kapatır.
7. Betik ön vekilin ayarını yazar ve yeniden yükler.
8. Betik "şu anki sürüm" bağını yeni pakete çevirir.

Bir adım başarısız olursa betik durur. Yeni paket "şu anki sürüm" olmaz.

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

Geri dönüşün iki biçimi vardır:

| Komut | Ne yapar | Ne zaman |
| --- | --- | --- |
| `rollback <ortam> backend` | Önceki imajları başlatır. Veritabanına dokunmaz. | Taşıma kuralı tuttuysa |
| `rollback <ortam> backend --restore-backup` | Dağıtımdan önceki yedeği geri yükler. Sonra önceki imajları başlatır. | Taşıma yarıda kaldıysa ya da kural tutmadıysa |
| `rollback <ortam> web` | Önceki arayüz paketine döner | Arayüz bozulduysa |

Jenkins bir ortamda hata görürse geri dönüşü kendiliğinden başlatır. Yalnız dağıtım başladıysa başlatır. Örneğin taşıma denetimi reddettiyse hiçbir şey geri dönmez.

alpha'da geri dönüş yedeği de geri yükler. Öteki ortamlarda yalnız imajlar geri döner. Yedeği geri yükleme kararını DevOps sorumlusu verir. Bunun için `promote.Jenkinsfile` işinde `rollback-restore` seçilir.

`--restore-backup` yedekten sonra yazılan veriyi siler. prod'da önce bu kaybı onaylayın. Sonra komutu çalıştırın.

## Sırlar

Depoda sır yoktur. Sırlar iki yerde durur:

| Yer | İçinde ne var | Kim yazar |
| --- | --- | --- |
| Jenkins kimlik bilgileri | `atonota-deploy-ssh` SSH anahtarı ve `atonota-registry` GHCR belirteci | DevOps sorumlusu |
| Sunucuda `/etc/atonota/<ortam>/<servis>.env` | Veritabanı parolaları, Keycloak istemci sırları, SMTP parolası | DevOps sorumlusu |

Sunucudaki sır dosyaları şunlardır:

- `tenant.env` ve `tenant-db.env` dosyaları kiracı sitesinin ve MariaDB'nin sırlarını tutar.
- `keycloak.env` ve `keycloak-db.env` dosyaları Keycloak'ın ve PostgreSQL'in sırlarını tutar. Anahtar adları `backend/identity/keycloak/production.env.example` dosyasındadır.
- `identity-sync.env` dosyası eşitleme servisinin sırlarını tutar.
- `press.env` dosyası Press'in sırlarını tutar. Bu dosya Press imajı gelince gerekir.
- `offsite.env` dosyası sunucu dışı yedeğin `rclone` adresini tutar.
- `/etc/atonota/edge.env` dosyası sertifika uyarısının gideceği e-posta adresini tutar.

Her dosyanın izni `0600` olur. Dosyanın sahibi `root` olur.

Jenkins uygulama sırlarını hiç görmez. Jenkins yalnız sunucuya bağlanır ve imaj yükler. Böylece Jenkins'in ele geçmesi veritabanı parolasını açmaz.

`deploy` kullanıcısı `docker` grubundadır. Bu grup sunucuda root yetkisine denktir. Bu yüzden `deploy` kullanıcısının anahtarı yalnız Jenkins'te durur.

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
| E-1 | Press'in sunucu kurma akışı Frappe 16'da çalışmıyor | MVP'de Press sunucu kurmaz. Kiracı sitesini DevOps sorumlusu ilk kurulumda elle açar. Kurma akışı hazırlık sunucusunda ayrıca sınanır | press-tr işi ve DevOps sorumlusu |
| E-2 | Press'in üretim imajı yok. Press bugün açılışta kurulur. Python 3.14 yaması da açık (O-18) | press-tr işi `backend/deploy/images/press.Dockerfile` dosyasını yazar. Dosya gelince `build-release` Press'i pakete ekler | press-tr işi |
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
- Üretim kiracı imajı yerelde derlendi. İçinde `panel.bundle.css` ve `panel-focus.bundle.js` dosyaları var.
- Jenkins dosyaları Jenkins'in kendi denetleyicisinden geçti.

Şunlar sınanmadı:

- Gerçek sunucuda dağıtım.
- Gerçek veritabanında geri yükleme.
- Keycloak ve identity-sync imajlarının üretim derlemesi.
- Ön vekilin gerçek sertifika alması.
