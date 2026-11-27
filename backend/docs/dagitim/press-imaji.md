# Press üretim imajı

Ürün adı `PRODUCT_NAME` ayarından gelir. Alan adı `BRAND_DOMAIN` ayarından gelir.
İki değer [ortak marka dosyasında](../../brand.env) tutulur.
Bu belgedeki `<PRODUCT_NAME>` ve `<BRAND_DOMAIN>` alanlarını bu değerlerle doldurun.

Bu belge Press'in üretim imajını anlatır. Belge 23 Kasım 2026 Pazartesi günü yazıldı. İş, [dağıtım belgesindeki](ortamlar.md) E-2 engelidir.

İmaj, konteynerin çalıştığı değişmez paketidir. Press imajının adı `atonota-press` olur. Sürüm paketi bu imajı dördüncü parça olarak taşır.

## İmajın içi

İmajı `backend/deploy/images/press.Dockerfile` dosyası derler. İmaj şunları taşır:

| Parça | Sürüm | Nasıl doğrulanır |
| --- | --- | --- |
| Taban imaj | `frappe/erpnext:v16.55.0` | Sabit özetle çağrılır. Kiracı imajıyla aynı tabandır. |
| Frappe | 16.56.0 | Taban imajdan gelir. |
| Python | 3.14.10 | Taban imajdan gelir. |
| Press | v0.154.1 | Derleme commit kodunu denetler: `7a4384d5eec9f0f0dce4124e9dd48b106e51222f`. |
| frappe-mcp | `b5c9730d18401c85d4b3ea68d20e2ba6f2bb7e7c` | Derleme commit kodunu denetler. |
| `press_tr` | Depodaki kod | `backend/apps/press_tr` klasöründen kopyalanır. |
| `oidc_verify` | Depodaki kod | `backend/libs/oidc_verify` klasöründen kurulur. |

İmajda site verisi yoktur. `site_config.json` dosyası ve sırlar da yoktur. Bu dosyalar sunucudaki birimde ve sır dosyasında durur.

İmajda test aracı ve derleme aracı kalmaz. Node paketleri derlemeden sonra silinir. Go ve C derleyicisi yalnız ayrı derleme aşamasında durur.

## Yama dizisi

Press v0.154.1, Python 3.14 ve Frappe 16 ile yamasız açılmaz. Bu yüzden imaj beş yama uygular. Yamalar `backend/deploy/images/press-patches/` klasöründedir.

Derleme her yamadan önce `git apply --check` çalıştırır. Bir yama tutmazsa derleme durur. Çalışan kapta kod değiştirilmez. Bu kural proje kaydındaki O-52 kararıdır.

Yamaların listesi ve lisansı [yama klasörünün notundadır](../../deploy/images/press-patches/README.md). Press'e gönderilecek öneriler [öneri belgesindedir](../press-python314-upstream.md).

Geliştirme imajının `patch-py314.sh` betiği bu imaja girmez. O betik kurulu paketleri de değiştirir. Üretim imajı paket dosyalarını değiştirmez. Uyum için paket sürümü seçer.

## Bağımlılıklar

Python paketleri `press-requirements.lock.txt` kilidinden kurulur. Kilit her paketi sürümüyle ve SHA-256 özetiyle sabitler. Kurulum `--require-hashes` seçeneğiyle yapılır. Özeti tutmayan paket kurulmaz.

Kilidin girdisi `press-requirements.in` dosyasıdır. Kilit çözülürken taban imajın bütün paketleri kısıt olarak verildi. Bu yüzden kilit Frappe'nin ve ERPNext'in hiçbir paketini değiştirmez.

Bazı sürümler Press'in istediğinden farklıdır. Her farkın nedeni `0005-dependency-pins.patch` yamasının başında yazılıdır. Önemli üç seçim şunlardır:

1. Telegram paketi kurulmaz. Paket Python 3.12 ve sonrasında açılmaz. Telegram uyarıları bu imajda çalışmaz.
2. Semgrep 1.79.0 kurulur. Press 1.159.0 ister. O sürüm Frappe 16'nın OpenTelemetry sürümüyle çakışır. Semgrep yalnız Marketplace uygulama denetiminde kullanılır. Bu denetim sınanmadı.
3. Stripe 3.1.0 kurulur. Press 2.56 ister. 2.56 sürümü Python 3.12 ve sonrasında açılmaz. Ödeme akışı sınanmadı.
4. Üç paket açık taraması yüzünden yükseldi. `dnspython` 2.9.2, `paramiko` 5.1.0 ve `setuptools` 84.2.1 kurulur. Ayrıntı "Açık taraması" bölümündedir.

Playwright paketi kuruludur, ama tarayıcıları kurulu değildir. Press olay kaydında ekran görüntüsü almak için tarayıcı ister. Bu özellik bu imajda çalışmaz.

`dockerfile` paketinin arm64 için hazır kurulum dosyası yoktur. Bu yüzden derleme arm64'te paketi kaynaktan derler. Kaynak dosyası özetle doğrulanır. Ancak paketin derleme betiği Go bağımlılıklarını da indirir. Bu bağımlılıkların sürümü sabit değildir. amd64 derlemesi hazır dosyayı kullanır ve bu adımı atlar.

Bu yüzden iki kural vardır:

1. `build-release` bütün sürüm imajlarını `--platform linux/amd64` ile derler. arm64 derleme ajanı da amd64 imajı üretir. Bunun için ajanda QEMU öykünmesi gerekir.
2. Dockerfile arm64 derlemesini reddeder. Yerel deneme için `--build-arg PRESS_LOCAL_ARM64_TRIAL=1` verin. `build-release` bu değeri hiç vermez. Böylece sabitlenmemiş Go kodu sürüm imajına giremez.

Karar gerekçesi şudur: sunucular için tek mimari yeterlidir. Yalnız arm64'ü reddetmek yetmezdi. O zaman arm64 ajanı hiç sürüm üretemezdi. Go bağımlılıklarını kaynağa almak ise daha büyük bir iştir. Bu iş yalnız arm64 sunucu seçilirse gerekir (E-15).

### Açık taraması

Güvenlik kapısı kilidi OSV-Scanner 2.7.1 ile tarar. OSV-Scanner, paket sürümlerini açık veritabanıyla karşılaştıran bir araçtır. Komut `backend/dev/security/scans.py press-lock` olur. `backend/dev/bin/security-audit` bu komutu çalıştırır. Açık bulunursa kapı düşer. Araç ya da veritabanı yoksa kapı yine düşer.

Tarama ağsız çalışır. Yalnız yerel dosyaları okur. Aracı ve veritabanını `backend/dev/security/osv-setup` betiği indirir. Bu betik ağ ister. Veritabanı en çok yedi gün eski olabilir. Bu yüzden betiği en az haftada bir çalıştırın.

23 Kasım 2026 Pazartesi günü ilk tarama eski kilitte 4 pakette 8 açık buldu. Yapılanlar şunlardır:

| Paket | Açık | Karar |
| --- | --- | --- |
| `dnspython` 1.16.0 | CVE-2023-29483 ve iki yeni hizmet engelleme açığı | 2.9.2 sürümüne yükseldi. Press `Resolver.query` işlevini kullanır. Bu işlev 2.9.2'de de vardır. |
| `paramiko` 3.3.1 | Terrapin (CVE-2023-48795) ve SHA-1 RSA imzası (CVE-2026-44405) | 5.1.0 sürümüne yükseldi. Press kodu `paramiko` kullanmaz. Ansible eklentileri ve `docker` paketi kullanır. Yeni sürüm `invoke` paketini de getirdi. |
| `setuptools` 80.9.0 | CVE-2026-59890 ve GHSA-xmj3-9gf7-h52w | 84.2.1 sürümüne yükseldi. Bu sürümde `pkg_resources` yoktur. İmajda bu modülü açan her satır `try` bloğu içindedir. |
| `wcmatch` 8.5.2 | GHSA-53pm-wgxf-c6qf | İstisna kaydına yazıldı. Semgrep 1.79.0, `wcmatch~=8.3` ister. Semgrep yalnız kapalı Marketplace denetiminde çalışır. Kayıt `backend/dev/security/osv-exceptions-press.toml` dosyasındadır. Bu dosya yalnız Press kilidinde kullanılır. Bitiş tarihi 23 Şubat 2027 Salı günüdür. |

Yükseltmeler `0005` yamasıyla Press'in `pyproject.toml` dosyasına da yazıldı. Böylece `uv pip check` yine yalnız izinli iki satırı bildirir.

### Bağımlılık denetimi

Derleme `uv pip check` komutunu çalıştırır. Komut yalnız iki satır bildirebilir. Satırlar `press-pip-check.allowed` dosyasındadır. Başka her satır derlemeyi durdurur. Eksik bir satır da derlemeyi durdurur.

İki satır frappe-mcp paketine aittir:

| Bildirilen satır | Neden zararsız |
| --- | --- |
| frappe-mcp `pydantic~=2.11.7` ister, `2.12.5` kurulu | frappe-mcp'nin kendi 67 testi bu sürümle geçti. |
| frappe-mcp `werkzeug==3.1.3` ister, `3.1.9` kurulu | Aynı test koşusu bu sürümle de geçti. |

Frappe 16, pydantic 2.12.5 ve Werkzeug 3.1.9 sürümlerini sabitler. Frappe'nin sürümünü düşürmek Frappe'yi bozabilir. Bu yüzden frappe-mcp `--no-deps` ile kurulur.

frappe-mcp artık bakımı bırakılmış bir pakettir. Frappe 16'nın kendi MCP sunucusu vardır. Press'in MCP modülü bu pakete bağlıdır. Modül Press ayarındaki `enable_mcp` anahtarıyla kapalıdır.

## Servisler

`backend/deploy/compose/stack.yaml` dosyası Press'i altı servisle çalıştırır:

| Servis | Görevi |
| --- | --- |
| `press-web` | Press'in uygulama sunucusudur. 8000 portunda çalışır. |
| `press-worker` | Arka plan işlerini çalıştırır. |
| `press-socket` | Canlı güncellemeleri taşır. |
| `press-frontend` | Derlenmiş dosyaları sunar ve istekleri `press-web` servisine iletir. 8080 portunda çalışır. |
| `press-redis-cache` | Press'in önbelleğidir. |
| `press-redis-queue` | Press'in iş kuyruğudur. |

Bu servislerin hepsi `press` profilindedir. `remote/apply` betiği profili iki koşul birlikte sağlanınca açar:

1. Sürüm paketinde Press imajı vardır. `build-release` imajı her pakete koyar.
2. Ortam dosyasında `ATONOTA_PRESS_ENABLED=1` yazılıdır.

Anahtar bütün ortamlarda bugün 0'dır. Press sitesi açılmadan profil açılırsa `press-web` sağlıklı olmaz. O zaman dağıtım düşer. rc ve prod'da anahtar 1 olamaz. `release.py` bunu Jenkins tarafında reddeder. Sunucudaki `remote/apply` de reddeder. Biri `apply` betiğini sunucuda elle çalıştırsa da kural geçerlidir. Nedeni şudur: dağıtım betikleri Press sitesini henüz yedeklemez (E-2).

Sağlık denetimi aynı kuralı kullanır. Anahtar 0 ise Press denetimi `not_run` yazar.

Press'in veritabanı kiracıların MariaDB sunucusundadır. Press'in veritabanı ve kullanıcısı ayrıdır. Bunları `bench new-site` komutu açar.

Press'in Redis'i ayrıdır. Nedeni şudur: iki bench de aynı klasördedir. Kuyruk ortak olursa kiracı işçisi Press'in işini alabilir.

Press servisleri ayrı bir ağdadır. Ağın adı `press-internal` olur. Kiracı kapları bu ağda değildir. Bu yüzden kiracı kabı Press'in Redis kuyruğuna iş yazamaz. Kiracı kabı `press-web:8000` adresine de ulaşamaz. Yalnız `tenant-db` iki ağdadır. `press-frontend` ayrıca ortamın kenar ağındadır.

Press, Keycloak'a ve identity-sync servisine genel HTTPS adresiyle ulaşır. Bu iki servis `press-internal` ağında değildir. Bu yüzden `keycloak_internal_url` ayarı üretimde boş kalır.

Ön vekil `press.<taban>` adını `press-frontend` servisine iletir. Örneğin alpha'da ad `press.alpha.<BRAND_DOMAIN>` olur.

Press'in site adı, Press'in alan adıyla aynı olmalıdır. Ön yüz siteyi istekteki alan adından seçer.

## İlk kurulum

Press sitesini DevOps sorumlusu elle açar. Adımlar sunucuda henüz denenmedi. Yalnız alpha ve beta'da yapılabilir.

Komutlar `atonota-<ortam>` Compose projesinde çalışır. Anahtar 0 iken profil kapalıdır. Bu yüzden her komuta `--profile press` ekleyin. Örnek: `docker compose ... --profile press run --rm press-web bench --site <Press alan adı> list-apps`.

1. `/etc/atonota/<ortam>/press.env` dosyasını `0600` izniyle açın. Kapsayıcı bu dosyadan anahtar okumaz. Dosya boş olabilir.
2. Press'in ortak ayarına veritabanı adresini yazın. Örnek: `bench set-config -g db_host tenant-db`.
3. Redis adreslerini yazın. Önbellek `redis://press-redis-cache:6379`, kuyruk `redis://press-redis-queue:6379` olur. `redis_socketio` da kuyruk adresini alır.
4. Siteyi Press alan adıyla açın ve Press'i kurun: `bench new-site <Press alan adı> --install-app press`.
5. `press_tr` uygulamasını kurun: `bench --site <Press alan adı> install-app press_tr`.
6. Zamanlayıcıyı kapalı tutun: `bench --site <Press alan adı> disable-scheduler`. Proje sahibi zamanlanmış iş istemedi.
7. Press sitesinin ayarlarını `press-site.production.env.example` listesine göre yazın.
8. Ortam dosyasında `ATONOTA_PRESS_ENABLED=1` yazın. Bu değişiklik commit ile gelir. Sonraki dağıtım Press servislerini açar.

`bench new-site` veritabanı kök parolasını ister. Parolayı komut satırına yazmayın. Komutu terminalli `exec` ile çalıştırın. Komut parolayı sorar. Parola `tenant-db.env` dosyasındadır. Frappe bu soruyu `frappe/database/mariadb/setup_db.py` dosyasının 140. satırında sorar.

## Deneme sonucu

Deneme 23 Kasım 2026 Pazartesi günü bu Mac'te yapıldı. Colima'nın `colima-factory` profili kullanıldı. İşlemci arm64'tür. Son deneme `abc68402` commit'inden derlenen imajla yapıldı. Yerel imaj kimliği `sha256:22d7d0ed5898e6548eab8c27078b53d14f3dedadc8ea45ff5ffcea483e2e2ab6` oldu. İmaj hiçbir kayıt deposuna yüklenmedi.

Deneme geçici kaplarla yapıldı. Kapların adı `e2press-` ile başladı. Hiçbir port bilgisayara açılmadı. Parolalar çalışma anında üretildi ve depoya yazılmadı. Deneme bitince kaplar, ağ, birimler ve imaj silindi.

| Denetim | Sonuç |
| --- | --- |
| İmaj derlemesi, beş yamanın `git apply --check` denetimi | `pass` |
| Temiz kapta `uv pip check`: yalnız izinli iki satır | `pass` |
| `press` ve `press_tr` içindeki test dışı 1052 modülün içe aktarılması | `pass` |
| `bench new-site` ve `--install-app press` | `pass` |
| `bench --site <site> install-app press_tr` | `pass` |
| `bench --site <site> migrate` | `pass` |
| Uygulama sunucusunda `/api/method/ping`: 200 ve `pong` | `pass` |
| Ön yüz kabında `/api/method/ping`, `/dashboard`, Press, Frappe ve ERPNext dosyaları: 200 | `pass` |
| Telegram yaması: paket yokken mesaj "Error" olur ve hata kaydı yazılır | `pass` |
| Çerez yaması: izin değişince kayıt açılır, değişmeyince açılmaz | `pass` |
| Press'in dar birim test kümesi: 34 test, 1 test kendiliğinden atlandı | `pass` |
| frappe-mcp'nin kendi testleri imajın paket sürümleriyle: 67 test | `pass` |
| Yerel Ansible oyunu, ansible-core 2.21.6 | `pass` |
| Gerçek sunucu kurma akışı (E-1) | `not_run` |
| amd64 derlemesi ve sunucuda çalışma | `not_run` |
| Ödeme, Telegram, Marketplace denetimi ve tarayıcıyla Press masası | `not_run` |

Dar test kümesi şu üç modüldür:

1. `press.press.doctype.deploy_candidate.test_deploy_candidate`. Bu modül 0001 yamasının dosyasını kullanır.
2. `press.utils.test_ssrf`. Bu modül dış adres güvenliğini sınar.
3. `press.utils.test_external_url`. Bu modül de dış adres güvenliğini sınar.

Testler Frappe'nin `run-tests` komutuyla koşmadı. Komut bağlı belge türlerinin test dosyalarını da açar. Bu dosyalardan biri Telegram paketini ister. Bu yüzden testler `unittest` ile doğrudan koştu. Test araçları imajda yoktur. `moto`, `hypothesis`, `faker` ve `pytest` yalnız geçici kaba kuruldu.

Denemede dört şey daha görüldü:

1. Press'in `migrate` adımı kendi denetimini de çalıştırır. Denetim internetten chromedriver indirmeye çalışır. İmajda `unzip` olmadığı için denetim bir uyarıyla durdu. `migrate` yine başarılı bitti.
2. Press'in `hooks.py` dosyası açılırken veritabanını okur. Bu yüzden `bench build` sitesiz derlemede kanca adımında düşer. Dockerfile bu yüzden derlemenin iki adımını doğrudan çalıştırır. Hiçbir uygulamada derleme sonrası kanca yoktur. Kanca eklenirse derleme durur.
3. Press'in Telegram kuyruğu Frappe 16'da çalışmaz. `TelegramMessage.get_one` sıralamada `FIELD(priority, ...)` ifadesini kullanır. Frappe 16 bu ifadeyi reddeder. Bu engel Telegram paketinden ayrıdır. Bu imajda Telegram zaten kapalıdır.
4. Press sitesinde `/login` adresi 403 döner. Bu beklenen davranıştır. `press_tr` yerel girişi kapatır. Kural `press_tr/press_identity/request_policy.py` dosyasındaki `block_native_login` işlevidir. Giriş Keycloak ile yapılır.

### İnceleme sonrası deneme

Bağımsız inceleme beş önemli bulgu verdi. Bulgular 23 Kasım 2026 Pazartesi günü kapatıldı. Paketler yükseldiği için imaj yeniden derlendi ve denendi. Deneme `colima-factory` profilinde arm64 ile yapıldı. Derleme `PRESS_LOCAL_ARM64_TRIAL=1` ile yapıldı. Yerel imaj kimliği `sha256:3b3d97db25f0c8c2e9a0c0730f497262b65fa4536b34921dcae6b80c21040149` oldu. İmaj kimliği her derlemede değişebilir. Kimlik üst veriye de bağlıdır. İmaj hiçbir kayıt deposuna yüklenmedi.

| Denetim | Sonuç |
| --- | --- |
| İmaj derlemesi ve `uv pip check`: yalnız izinli iki satır | `pass` |
| İmajdaki sürümler: `dnspython` 2.9.2, `paramiko` 5.1.0, `setuptools` 84.2.1 | `pass` |
| `press` ve `press_tr` içindeki test dışı 1052 modülün içe aktarılması | `pass`. `press.hooks` yalnız siteye bağlıyken açılır. Siteyle ayrıca açıldı. |
| `bench new-site --install-app press`, `install-app press_tr`, `migrate` | `pass` |
| Uygulama sunucusunda `/api/method/ping`: 200 ve `pong` | `pass` |
| Press'in `check_dns_a` ve `check_dns_cname` işlevleri, sahte DNS sunucusuyla | `pass`. A ve CNAME eşleşti. Olmayan ad hata metni döndü. |
| `paramiko` 5.1.0 anahtar okuma ve `docker` SSH taşıyıcısının açılması | `pass` |
| Bayraksız arm64 derlemesi | `pass`. Derleme ilk adımda durdu. |
| Gerçek SSH bağlantısı ve Press'in dar birim test kümesi | `not_run` |
| amd64 derlemesi ve sunucuda çalışma | `not_run` |

Geçici kapların adı `e2r2-` ile başladı. Kaplar, ağ ve imaj deneme sonunda silindi.

## Kalan iş

Kalan iş dağıtım belgesindeki E-2 satırındadır. Özeti şudur:

1. `remote/backup` ve `remote/restore` Press sitesini kapsamaz.
2. `remote/apply` Press sitesinde `migrate` çalıştırmaz.
3. Bu iki iş bitmeden rc ve prod'da Press açılmaz. `release.py` bu kuralı uygular.
4. `remote/site-probe.py` Press sitesinin ayarlarını henüz denetlemez. Liste hazırdır: `press-site.production.env.example`.
5. Eski bir sürüme geri dönüşte Press servislerinin ne olacağı denenmedi.
6. Press'in chromedriver denetimi kapatılmadı.
7. İmaj amd64'te ve sunucuda denenmedi (E-15).
8. Press'in sunucu kurma akışı ayrı bir engeldir (E-1).
9. Telegram yaması Press'in uyarılarını kapatır. Press açılmadan önce başka bir uyarı kanalı belirlenmelidir (E-2).
