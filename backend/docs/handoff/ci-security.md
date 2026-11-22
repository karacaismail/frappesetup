# Güvenlik denetimini CI sistemine devretme

DevOps sorumlusu denetimleri CI sistemine kurar.
CI sistemi değişiklikleri birleştirmeden önce denetimleri çalıştırır.

| İş | Çalışma klasörü | Komut |
| --- | --- | --- |
| Güvenlik araçlarının birim testleri | Depo kökü | `python3 -B -m unittest discover -s backend/dev/security -v` |
| Kaynak, Git geçmişi ve bağımlılık taraması | Depo kökü | `FS_COLIMA_PROFILE=ci backend/dev/bin/security-full --ci` |
| Yerel sitenin güvenlik başlığı | Depo kökü | `backend/dev/bin/dast-scan --ci "http://kiraci1.localhost:$((PANE_PORT + 1))"` |
| Son taramaların raporu | Depo kökü | `backend/dev/bin/release-report` |

## Hazırlık

GitHub checkout adımında `fetch-depth: 0` kullanın.
Docker ve uv 0.13.9 kurun. uv ile Python 3.12 ve 3.14 hazırlayın.
Araç sürümleri ve Gitleaks imaj özeti `backend/dev/security/tool-versions.env` dosyasındadır.
Gitleaks imajını o özetle önceden indirin.
CI kipi yerel Docker bağlamını kullanır. Colima'da `factory` ya da `default` seçin.
Factory profilinde yeni imaj derlemeyin ve yeni site açmayın.

[OSV-Scanner 2.7.1 Linux amd64](https://github.com/google/osv-scanner/releases/download/v2.7.1/osv-scanner_linux_amd64) dosyasını indirin.
Dosyanın SHA-256 özeti `fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8` olmalı.
Dosyayı çalıştırılabilir yapın ve PATH üzerine `osv-scanner` adıyla koyun.
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

Tarama yedi günden eski veritabanını reddeder.
Python kaynak listeleri değişince `backend/dev/security/compile-lock` çalıştırın.
Oluşan `backend/dev/security/requirements.txt` dosyasını commit edin.
Kilit, uygulamaların bildirdiği Python paketlerini kapsar.
Bir Frappe imajının kurulu paketlerini ayrı listelemek için `--runtime-image IMAGE_ID` kullanın.
`docker image inspect` çıktısındaki yerel imaj kimliğini verin.

## Yerel site ve kabul

Kendi sitenizi hazırlayın. Sitenin web portu `PANE_PORT + 1` olur.
Gerekirse `FS_COLIMA_PROFILE=default backend/dev/bin/tunel ac` komutuyla tüneli açın.
Site kurulumu için gereken sırlar `MARIADB_ROOT_PASSWORD` ve `ADMIN_PASSWORD` değerleridir.

Başarısız tarama birleştirmeyi durdurur.
CI kipinde zorunlu adım çalışmazsa komut 1 ile çıkar.
ZAP Baseline ve canlı Schemathesis `not_run` döner. Bu yüzden iki tam CI kapısı geçmez.
Rapor kendi başına birleştirme kararı vermez.

CodeQL Python işi için şu adımları kullanın.

```yaml
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
Bir sayıyı girmediğinizde karne “Ölçülmedi” yazar.
