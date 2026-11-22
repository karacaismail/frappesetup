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
ZAP 2.17.0 bu yanıtı ağ erişimi kapalı bir ortamda inceler.
Canlı Schemathesis adımı açıktır. `security-full --ci` bu adımı geçirmez.

## Bakım ve geri dönüş

DevOps sorumlusu araç sürümlerini ve açık veritabanını günceller.
Her yanlış alarm için sorumlu rolü ve gerekçeyi yazın.
OSV istisnalarını `backend/dev/security/osv-exceptions.toml` dosyasına girin.
Bandit istisnaları `backend/dev/security/bandit-exceptions.json` dosyasındadır.
Gitleaks istisnaları `backend/dev/security/.gitleaksignore` dosyasındadır.
Yalnız incelemesi tamamlanan bulguları istisna sayın.

Yeni komutlar geri alınırsa mevcut `guvenlik-denetimi` komutu çalışmaya devam eder.

## Tarama ve istisna kapsamı

Bandit, Git'in izlediği `backend` altındaki Python dosyalarını tarar.
Bilinen hatalı deneme dosyaları kaynak taramasına girmez.
`packages/press-ai` Python taramasının kapsamı dışındadır.
Bandit istisnası kural, dosya, satır, sahip, gerekçe ve bitiş tarihi taşır.
Süresi geçen veya eşleşmeyen istisna denetimi durdurur.
Gitleaks yalnız kural, dosya, satır, commit ve parmak izi gösterir.

OSV-Scanner kökteki npm kilidini ve diğer izlenen kilitleri tarar.
Paket bulguları sürüm raporuna yazılır. Paket sürümü bu komutla değişmez.

Python kilidi, Git'in izlediği backend projelerinin `dependencies` listelerini kapsar.
Kilit isteğe bağlı paketleri kapsamaz.
