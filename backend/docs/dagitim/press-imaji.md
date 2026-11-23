# Press üretim imajı

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

Derleme her yamadan önce `git apply --check` çalıştırır. Bir yama tutmazsa derleme durur. Çalışan kapta kod değiştirilmez. Bu kural proje kaydındaki O-51 kararıdır.

Yamaların listesi ve lisansı [yama klasörünün notundadır](../../deploy/images/press-patches/README.md). Press'e gönderilecek öneriler [öneri belgesindedir](../press-python314-upstream.md).

Geliştirme imajının `patch-py314.sh` betiği bu imaja girmez. O betik kurulu paketleri de değiştirir. Üretim imajı paket dosyalarını değiştirmez. Uyum için paket sürümü seçer.

## Bağımlılıklar

Python paketleri `press-requirements.lock.txt` kilidinden kurulur. Kilit her paketi sürümüyle ve SHA-256 özetiyle sabitler. Kurulum `--require-hashes` seçeneğiyle yapılır. Özeti tutmayan paket kurulmaz.

Kilidin girdisi `press-requirements.in` dosyasıdır. Kilit çözülürken taban imajın bütün paketleri kısıt olarak verildi. Bu yüzden kilit Frappe'nin ve ERPNext'in hiçbir paketini değiştirmez.

Bazı sürümler Press'in istediğinden farklıdır. Her farkın nedeni `0005-dependency-pins.patch` yamasının başında yazılıdır. Önemli üç seçim şunlardır:

1. Telegram paketi kurulmaz. Paket Python 3.12 ve sonrasında açılmaz. Telegram uyarıları bu imajda çalışmaz.
2. Semgrep 1.79.0 kurulur. Press 1.159.0 ister. O sürüm Frappe 16'nın OpenTelemetry sürümüyle çakışır. Semgrep yalnız Marketplace uygulama denetiminde kullanılır. Bu denetim sınanmadı.
3. Stripe 3.1.0 kurulur. Press 2.56 ister. 2.56 sürümü Python 3.12 ve sonrasında açılmaz. Ödeme akışı sınanmadı.

Playwright paketi kuruludur, ama tarayıcıları kurulu değildir. Press olay kaydında ekran görüntüsü almak için tarayıcı ister. Bu özellik bu imajda çalışmaz.

`dockerfile` paketinin arm64 için hazır kurulum dosyası yoktur. Bu yüzden derleme arm64'te paketi kaynaktan derler. Kaynak dosyası özetle doğrulanır. Ancak paketin derleme betiği Go bağımlılıklarını da indirir. Bu bağımlılıkların sürümü sabit değildir. amd64 derlemesi hazır dosyayı kullanır ve bu adımı atlar. Sunucular için derleme amd64'te yapılır (E-15).

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

Anahtar bütün ortamlarda bugün 0'dır. Press sitesi açılmadan profil açılırsa `press-web` sağlıklı olmaz. O zaman dağıtım düşer. rc ve prod'da anahtar 1 olamaz. `release.py` bunu reddeder. Nedeni şudur: dağıtım betikleri Press sitesini henüz yedeklemez (E-2).

Sağlık denetimi aynı kuralı kullanır. Anahtar 0 ise Press denetimi `not_run` yazar.

Press'in veritabanı kiracıların MariaDB sunucusundadır. Press'in veritabanı ve kullanıcısı ayrıdır. Bunları `bench new-site` komutu açar.

Press'in Redis'i ayrıdır. Nedeni şudur: iki bench de aynı klasördedir. Kuyruk ortak olursa kiracı işçisi Press'in işini alabilir.

Ön vekil `press.<taban>` adını `press-frontend` servisine iletir. Örneğin alpha'da ad `press.alpha.atonota.net` olur.

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

Deneme 23 Kasım 2026 Pazartesi günü bu Mac'te yapıldı. Colima'nın `colima-factory` profili kullanıldı. İşlemci arm64'tür. Yerel imaj kimliği `sha256:b84de35339dfd0de55602746d76aee6b4cabe3709b65cbb6f17fed737f82478a` oldu. İmaj hiçbir kayıt deposuna yüklenmedi.

Deneme geçici kaplarla yapıldı. Kapların adı `e2press-` ile başladı. Hiçbir port bilgisayara açılmadı. Parolalar çalışma anında üretildi ve depoya yazılmadı. Deneme bitince kaplar, ağ, birimler ve imaj silindi.

| Denetim | Sonuç |
| --- | --- |
| İmaj derlemesi, beş yamanın `git apply --check` denetimi | `pass` |
| Temiz kapta `uv pip check`: yalnız izinli iki satır | `pass` |
| `press`, `press_tr` ve yamalı modüllerin içe aktarılması | `pass` |
| `bench new-site` ve `--install-app press` | `pass` |
| `bench --site <site> install-app press_tr` | `pass` |
| `bench --site <site> migrate` | `pass` |
| Uygulama sunucusunda `/api/method/ping`: 200 ve `pong` | `pass` |
| Ön yüz kabında `/api/method/ping`, `/dashboard` ve Press dosyaları: 200 | `pass` |
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

Denemede iki şey daha görüldü:

1. Press'in `migrate` adımı kendi denetimini de çalıştırır. Denetim internetten chromedriver indirmeye çalışır. İmajda `unzip` olmadığı için denetim bir uyarıyla durdu. `migrate` yine başarılı bitti.
2. Press'in `hooks.py` dosyası açılırken veritabanını okur. Bu yüzden `bench build` sitesiz derlemede kanca adımında düşer. Dockerfile bu yüzden derlemenin iki adımını doğrudan çalıştırır. Hiçbir uygulamada derleme sonrası kanca yoktur. Kanca eklenirse derleme durur.

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
