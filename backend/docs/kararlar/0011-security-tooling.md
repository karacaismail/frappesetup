# 0011. Elle başlatılan güvenlik denetimleri

Proje O-29 kararıyla güvenlik taramalarını elle başlatır.
Araçlar uygulama sunucusundan ayrı çalışır.

## Araç seçimi

- Bandit 1.9.4, Python kaynak kodunu inceler. Lisansı Apache 2.0'dır.
- Gitleaks 8.30.1, yerelde erişilebilen Git geçmişini inceler. Lisansı MIT'dir.
- OSV-Scanner 2.7.1, sabit sürümlü bağımlılık listesini inceler. Lisansı Apache 2.0'dır.

Gitleaks, var olan imajı özetiyle kullanır. Git geçmişini ağ erişimi kapalı bir ortamda tarar.
OSV-Scanner yerel açık veritabanını kullanır. Bağımlılık listesini dışarı göndermez.
Bu nedenle ağ üzerinden sorgu yapan pip-audit seçeneğini kullanmadık.
[OSV çevrim dışı tarama rehberi](https://google.github.io/osv-scanner/usage/offline-mode/)

Bandit, var olan Semgrep kurallarına ek Python denetimleri sağlar. Python denetimini bunun için ayrı tuttuk.
Çalışan site kontrolü, yerel bir adresten tek HTTP yanıtı alır.
Komut `X-Content-Type-Options: nosniff` başlığını denetler. Yönlendirmeyi izlemez.
ZAP Baseline ve canlı Schemathesis taraması uygulama kapsamı dışında kaldı.

## Bakım ve geri dönüş

DevOps sorumlusu araç sürümlerini ve açık veritabanını günceller.
Her yanlış alarm için sorumlu rolü ve gerekçeyi yazın.
OSV istisnalarını `backend/dev/security/osv-exceptions.toml` dosyasına girin.
Diğer araçlardaki istisna önerisini aynı işin karar kaydında incelemeye sunun.
İlk sürüm hiçbir bulguyu istisna saymaz.

Yeni komutlar geri alınırsa mevcut `guvenlik-denetimi` komutu çalışmaya devam eder.
