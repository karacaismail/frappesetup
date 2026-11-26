# Güvenlik denetimini CI sistemine devretme

DevOps sorumlusu denetimleri CI sistemine kurar.
CI sistemi değişiklikleri birleştirmeden önce denetimleri çalıştırır.

| İş | Çalışma klasörü | Komut |
| --- | --- | --- |
| Güvenlik araçlarının birim testleri | Depo kökü | `uv run --no-project --offline --python 3.12 python -B -m unittest discover -s backend/dev/security -v` |
| Kaynak, Git geçmişi, bağımlılık ve sözleşme taraması | Depo kökü | `FS_COLIMA_PROFILE=ci backend/dev/bin/security-full --ci --api-target "http://kiraci1.localhost:$((PANE_PORT + 1))"` |
| Yerel yanıtın güvenlik başlığı ve pasif ZAP taraması | Depo kökü | `FS_COLIMA_PROFILE=ci backend/dev/bin/dast-scan --ci "http://kiraci1.localhost:$((PANE_PORT + 1))"` |
| Son taramaların raporu | Depo kökü | `backend/dev/bin/release-report` |

DevOps sorumlusu `backend/dev/tests` testlerini CI sistemine ekler.
Test komutu depo kökünde çalışır.

```sh
python3 -I -m unittest discover -s backend/dev/tests
```

## Hazırlık

GitHub checkout adımında `fetch-depth: 0` kullanın.
`refs/heads/backend` yerel dal kaydını hazırlayın.
Uygunluk kapısı, bu dalla ortak commit'ten sonraki mesajları tarar.
Docker ve uv 0.13.9 kurun. uv ile Python 3.12 ve 3.14 hazırlayın.
Araç sürümleri ve imaj özetleri `backend/dev/security/tool-versions.env` dosyasındadır.
Gitleaks ve ZAP imajlarını kayıtlı özetleriyle önceden indirin.
CI kipi yerel Docker bağlamını kullanır. Colima'da `factory` ya da `default` seçin.
Factory profilinde yeni imaj derlemeyin ve yeni site açmayın.

[OSV-Scanner 2.7.1 Linux amd64](https://github.com/google/osv-scanner/releases/download/v2.7.1/osv-scanner_linux_amd64) dosyasını indirin.
Dosyanın SHA-256 özeti `fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8` olmalı.
Dosyayı çalıştırılabilir yapın ve PATH üzerine `osv-scanner` adıyla koyun.
Yerelde `backend/dev/security/osv-setup` aynı dosyayı özetiyle indirir. Betik veritabanlarını da indirir.
Araç özetleri `tool-versions.env` dosyasındadır. `osv-setup` ve `scans.py` aynı özetleri kullanır.
`scans.py` PATH'teki aracı da bu özetle karşılaştırır. Özet tutmazsa araç kullanılmaz.

### Jenkins'te OSV hazırlığı

`backend.Jenkinsfile` dosyasında `Security tools` aşaması vardır. Bu aşama ilk kapı aşamasından hemen önce çalışır.

1. Aşama `backend/dev/security/osv-setup --if-stale` komutunu çalıştırır.
2. Araç yoksa ya da özeti tutmazsa komut aracı indirir. Komut aracın özetini denetler.
3. Veritabanı dosyası yoksa komut onu indirir.
4. Veritabanı dosyası altı gün ya da daha eskiyse komut onu yeniden indirir.
5. Daha yeni dosyaya komut dokunmaz.
6. Sonra `Gate: security audit` aşaması `security-audit` kapısını çalıştırır.

Tarama yedi günden eski veritabanını reddeder. Bir günlük pay, yedinci güne yakın dosyanın kapıyı düşürmesini önler.
Zamanlanmış iş kurmayın. Yenilemeyi her derleme kendisi yapar.
Jenkins ajanında `curl` olmalıdır. Ajan `github.com` ve `osv-vulnerabilities.storage.googleapis.com` adreslerine HTTPS ile ulaşmalıdır.
İndirme düşerse aşama düşer. Kapı eski veritabanıyla geçmez.
Bu davranışı `backend/dev/tests/test_osv_setup.py` ve `backend/deploy/tests/test_jenkins_side.py` sınar.

Veritabanı dosyalarının yayımlanmış özeti yoktur. Komut bu dosyaları özetsiz indirir. Bağlantı HTTPS'tir ve kaynak OSV'nin kendi deposudur. Bu yol kabul edildi.

### OSV istisnaları

Genel istisnalar `backend/dev/security/osv-exceptions.toml` dosyasındadır.
Press imajının kilidi için ayrı bir dosya vardır. Adı `osv-exceptions-press.toml` olur.
Press dosyasındaki istisna yalnız Press kilidinin taramasında kullanılır. Örneğin `wcmatch` istisnası öteki kilitlerde geçerli değildir.
Başka bir kilit `wcmatch` alırsa açık raporlanır. Bunu `test_scans.py` sınar.
`security-audit` kapısı Press kilidini tarar. Kapı aracı ve veritabanını bulamazsa düşer.
Komut aracı bulamazsa OSV adımını `not_run` olarak kaydeder.
Bu durumda `security-full`, yerelde ve CI kipinde 1 ile çıkar.
`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY` değişkenine yerel önbellek klasörünü verin.
Aşağıdaki komutlar yalnız açık veritabanlarını indirir.

```sh
for ecosystem in PyPI npm; do
  db_dir="$OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY/osv-scalibr/$ecosystem"
  mkdir -p "$db_dir"
  curl -fsSL "https://osv-vulnerabilities.storage.googleapis.com/$ecosystem/all.zip" -o "$db_dir/all.zip.new"
  mv "$db_dir/all.zip.new" "$db_dir/all.zip"
done
```

Tarama veritabanı yaşını dosyanın değişiklik zamanı üzerinden hesaplar.
Dosyayı kopyalamak bu zamanı değiştirebilir.
Bu ölçüm veritabanının yayımlanma tarihini doğrulamaz.
Tarama yedi günden eski veritabanını reddeder.
Python kaynak listeleri değişince `backend/dev/security/compile-lock` çalıştırın.
Oluşan `backend/dev/security/requirements.txt` dosyasını commit edin.
Kilit, Git kayıtlı backend projelerinin zorunlu Python paketlerini kapsar.
CI kipi kilidi bellekte yeniden üretir. Dosyadaki içerik farklıysa tarama durur.
OSV, Git üzerinden alınan Python paketlerini denetlemez. Rapor bu paketleri `not_run` olarak gösterir.
Bir Frappe imajının kurulu paketlerini ayrı listelemek için `--runtime-image IMAGE_ID` kullanın.
`docker image inspect` çıktısındaki yerel imaj kimliğini verin.

## Jenkins kapıları

Jenkins hattında her kapı ayrı bir aşamadır.
Bir kapı düşerse Jenkins düşen aşamanın adını gösterir.
Aşama adı `Gate: ` ile başlar.
Aşağıdaki tablo kapıların tam listesidir.
`backend/deploy/tests/test_jenkins_gates.py` bu tabloyu Jenkinsfile aşamalarıyla karşılaştırır.
İki liste eşit değilse test düşer.
Yeni kapı eklerseniz bu tabloya da bir satır ekleyin.

| Jenkinsfile | Aşama | Çalışma klasörü | Komut |
| --- | --- | --- | --- |
| `backend.Jenkinsfile` | `Gate: deploy tests` | `.` | `uv run --no-project --offline --python 3.14 python -I -m unittest discover -s backend/deploy/tests` |
| `backend.Jenkinsfile` | `Gate: dev tests` | `.` | `uv run --no-project --offline --python 3.14 python -I -m unittest discover -s backend/dev/tests` |
| `backend.Jenkinsfile` | `Gate: security tool tests` | `.` | `uv run --no-project --offline --python 3.12 python -B -m unittest discover -s backend/dev/security` |
| `backend.Jenkinsfile` | `Gate: module boundaries` | `.` | `backend/dev/bin/module-boundaries` |
| `backend.Jenkinsfile` | `Gate: security audit` | `.` | `backend/dev/bin/security-audit` |
| `backend.Jenkinsfile` | `Gate: platform_core tests` | `.` | `backend/dev/bin/test platform_core` |
| `backend.Jenkinsfile` | `Gate: hrms_tr tests` | `.` | `backend/dev/bin/test hrms_tr` |
| `web.Jenkinsfile` | `Gate: lint` | `web` | `npm run lint` |
| `web.Jenkinsfile` | `Gate: typecheck` | `web` | `npm run typecheck` |
| `web.Jenkinsfile` | `Gate: unit tests` | `web` | `npm test` |

`.` depo kökü demektir. `web` klasörü `atonota-web` deposunun kopyasıdır.
`backend/deploy/tests` ve `backend/dev/tests` testleri Python 3.14 ister. Python 3.9 bazı test dosyalarını açamaz.
`promote.Jenkinsfile` kapı çalıştırmaz. Bu iş yalnız denetlenmiş sürümü taşır.

Şu iki iş henüz Jenkins kapısı değildir:

- `security-full` kaynak taramasıdır.
- `dast-scan` pasif ZAP taramasıdır.

İki iş de CI işinin içinde açılan geçici bir site ister.
Jenkins ajanında bu site henüz kurulmadı.
Site hazır olunca iki işi de tabloya ve Jenkinsfile dosyasına ekleyin.

Aynı test üç kuralı daha denetler:

1. Jenkinsfile içinde `cron`, `pollSCM` ya da başka zamanlı tetikleyici yoktur. Yalnız `githubPush()` işi başlatır.
2. Jenkinsfile içinde açık parola, token ya da anahtar yoktur.
3. Jenkinsfile içinde sunucu adresi yoktur. Sunucu adresleri `backend/deploy/environments/` dosyalarındadır.

Gizli değerler yalnız Jenkins kimlik kaydından adla okunur.
Kayıt adları `backend/docs/handoff/jenkins-credentials.md` dosyasındadır.

## Yerel site ve kabul

Kendi sitenizi hazırlayın. Sitenin web portu `PANE_PORT + 1` olur.
Gerekirse `FS_COLIMA_PROFILE=default backend/dev/bin/tunnel open` komutuyla tüneli açın.
Site kurulumu için gereken sırlar `MARIADB_ROOT_PASSWORD` ve `ADMIN_PASSWORD` değerleridir.
Sözleşme denetimi için gereken sır `FS_API_TEST_PASSWORD` değeridir.

### Sözleşme denetiminin ayarları

Sözleşme denetimi Schemathesis aracıyla yapılır. Araç, `backend/contracts/` dosyalarını çalışan siteye karşı dener.

1. Hedefi `--api-target` seçeneğiyle verin.
2. Hedef yalnız CI işinin içinde açılan yerel geçici site olur.
3. Adres `http://kiraci1.localhost:<port>` biçiminde olur. Port, sitenin web portudur.
4. Komut `127.0.0.1` ve `*.localhost` dışındaki adresleri reddeder.
5. Seçenek verilmezse komut önce `FS_API_TARGET` değişkenini okur. Bu değişken yoksa `PANE_PORT + 1` portunu kullanır.

Oturum gereken uçlar için bir test hesabı verin:

1. Geçici sitede uydurma bir test hesabı açın. Örneğin `contract.tester@example.com` adını kullanın.
2. Hesabın adını `FS_API_TEST_USER` değişkenine yazın.
3. Hesabın parolasını `FS_API_TEST_PASSWORD` değişkenine verin. Bu değer CI gizli değişkeninden gelir.
4. Parolayı CI dosyasına ve komut satırına yazmayın.

Komut "Administrator" ve "Guest" hesaplarını reddeder. Gerçek kişi hesabı kullanmayın. İki değişken de boşsa denetim oturumsuz çalışır.

Komut, oturum kimliğini araca ortam değişkeniyle verir. Test hesabının adı ve parolası araca aktarılmaz.

Yazan istekler varsayılan olarak gönderilmez. `--allow-writes` seçeneği bu istekleri açar. CI işinde bu seçeneği kullanmayın.

Başarısız tarama birleştirmeyi durdurur.
CI kipinde zorunlu adım çalışmazsa komut 1 ile çıkar.
ZAP, yerel siteden alınan ilk yanıtı pasif olarak inceler. Yanıt yeniden gönderilmez.
Komut her uyarı için kimliği, risk düzeyini ve yerel adresi gösterir.
Yerel hedef yoksa sözleşme adımı `not_run` döner.
Sözleşme denetimi varsayılan olarak GET işlemlerini kapsar.
Özet, sınanan işlem sayısını gösterir. Erişim izni ayrı rol testiyle doğrulanır.
Ayrı test, aynı uçta iki sahte hesabı kullanır.
Yetkili hesap 200, yetkisiz hesap 403 almalıdır.
Rapor kendi başına birleştirme kararı vermez.

CodeQL Python işi için aşağıdaki ayarları kullanın.
İş 15 dakikada bitmezse GitHub işi durdurur.

```yaml
timeout-minutes: 15
permissions:
  contents: read
  security-events: write
steps:
  # Check out the full repository before initializing CodeQL.
  - uses: github/codeql-action/init@33d7b85da1a04171e211befe2c739303b9a4c066 # v4.39.3
    with:
      languages: python
      build-mode: none
  - uses: github/codeql-action/analyze@33d7b85da1a04171e211befe2c739303b9a4c066 # v4.39.3
```

GitHub dal kuralında CodeQL sonucunu zorunlu tutun.
Açık uyarıları durdurmak için kod tarama kuralında eşik seçin.
CI adımını ve kod tarama kuralını DevOps sorumlusu doğrular.
Zamanlanmış iş kurmayın.

## Güvenlik karnesi

Depo kökünde `backend/dev/bin/security-scorecard` çalıştırın.
Komut son denetim sonuçlarını sayar.
Açık bulgu sayısını inceleme kaydından alın. Sayıyı `--open-findings` ile girin.
Paket açığı sayısını tarama çıktısından alın. Sayıyı `--package-vulnerabilities` ile girin.
Reddedilen istek sayısını test kaydından alın. Sayıyı `--rejected-requests` ile girin.
Bir sayıyı girmediğinizde karne “Not measured” yazar.
