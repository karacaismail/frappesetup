# Güvenlik denetimini CI sistemine devretme

DevOps sorumlusu denetimleri CI sistemine kurar. CI sistemi, değişiklikleri birleştirmeden önce denetimleri çalıştırır.

| İş | Çalışma klasörü | Komut |
| --- | --- | --- |
| Kaynak, Git geçmişi ve bağımlılık taraması | Depo kökü | `backend/dev/bin/security-full --requirements requirements.txt` |
| Yerel sitenin güvenlik başlığı | Depo kökü | `backend/dev/bin/dast-scan http://127.0.0.1:8000` |
| Son taramaların raporu | Depo kökü | `backend/dev/bin/release-report` |
| Python kodunda güvenlik kuralları | Depo kökü | `codeql database analyze DATABASE CODEQL_QUERY_SUITE` |

`requirements.txt` yoluna, çalışan ortamın sabit sürümlü bağımlılık listesini verin.
Git geçmişini tam alın. Gitleaks imajını komuttaki özetiyle önceden indirin.
OSV-Scanner 2.7.1 ve yerel PyPI açık veritabanını hazırlayın.
[OSV çevrim dışı kurulum rehberi](https://google.github.io/osv-scanner/usage/offline-mode/)

Yerel siteyi başlatın. Komuttaki portu siteye göre değiştirin.
Raporu alın ve taramalardan sonra saklayın. Rapor komutu birleştirme kararını vermez.

CodeQL veritabanını Python dili için kurun. Sorgu paketini ve araç sürümünü CI ayarında sabitleyin.
Canlı sözleşme testi ve ZAP Baseline, raporda `not_run` olarak görünür.

Başarısız tarama birleştirmeyi durdurur.
Zorunlu taramalardan biri çalışmazsa birleştirme durur.

Bu komutlar ek sır gerektirmez. Zamanlanmış iş kurmayın.

## Güvenlik karnesi

Depo kökünde `backend/dev/bin/security-scorecard` çalıştırın.
Komut son denetim sonuçlarını sayar.
Açık bulgu sayısını inceleme kaydından alın. Sayıyı `--open-findings` ile girin.
Paket açığı sayısını tarama çıktısından alın. Sayıyı `--package-vulnerabilities` ile girin.
Reddedilen istek sayısını test kaydından alın. Sayıyı `--rejected-requests` ile girin.
Bir sayıyı girmediğinizde karne “Ölçülmedi” yazar.
