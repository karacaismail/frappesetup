# 0011. Elle başlatılan güvenlik denetimleri

Proje O-29 kararıyla güvenlik taramalarını elle başlatır.
Araçlar uygulama sunucusundan ayrı çalışır.

## Araç seçimi

Frappe 16’nın testleri uygulama davranışını sınar.
Git geçmişi ve bağımlılık kilitleri ayrı araç ister.

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
Başlık denetimi yalnız bir başlığı inceler.
ZAP aynı yanıtta başka güvenlik uyarıları da arar.
ZAP 2.17.0, yanıtı ağ erişimi kapalı bir ortamda inceler.
ZAP, Apache 2.0 lisansı kullanır. DevOps sorumlusu yeni sürümde imaj özetini günceller.
[ZAP sürüm kaydı](https://github.com/zaproxy/zaproxy/releases/tag/v2.17.0)
[ZAP lisansı](https://github.com/zaproxy/zaproxy/blob/v2.17.0/LICENSE)

22 Kasım 2026 Pazar günü ZAP deposunda yayımlanmış güvenlik bildirimi görünmüyordu.
Bu denetim imajdaki paketleri kapsamadı.
[ZAP güvenlik bildirimleri](https://github.com/zaproxy/zaproxy/security/advisories)

Nuclei yerine ZAP seçildi. ZAP kaydedilen yanıtı yeni istek göndermeden inceler.
Tarayıcıya paket eklenmez. ZAP, yerel denetimde ayrı imaj olarak çalışır.
Yerel hedef yoksa sözleşme adımı `not_run` döner.
Sözleşme denetimi varsayılan olarak GET işlemlerini kapsar.
Özet, sınanan işlem sayısını gösterir. Erişim izni ayrı rol testiyle doğrulanır.
Ayrı test, aynı uçta iki sahte hesabı kullanır.
Yetkili hesap 200, yetkisiz hesap 403 almalıdır.

## Bakım ve geri dönüş

DevOps sorumlusu araç sürümlerini ve açık veritabanını günceller.
Her yanlış alarm için sorumlu rolü ve gerekçeyi yazın.
OSV istisnalarını `backend/dev/security/osv-exceptions.toml` dosyasına girin.
Bandit istisnaları `backend/dev/security/bandit-exceptions.json` dosyasındadır.
Semgrep istisnaları `backend/dev/security/semgrep-exceptions.json` dosyasındadır.
Gitleaks istisnaları `backend/dev/security/.gitleaksignore` dosyasındadır.
Yalnız incelemesi tamamlanan bulguları istisna sayın.

Geri dönüş için bu araçların eklendiği değişikliği geri alın.
Mevcut `security-audit` komutu tek başına çalışır.

## Tarama ve istisna kapsamı

Bandit, Git'in izlediği `backend` altındaki Python dosyalarını tarar.
Bilinen hatalı deneme dosyaları kaynak taramasına girmez.
`packages/press-ai` Python taramasının kapsamı dışındadır.
Bandit istisnası kural, dosya, kod, kod özeti, sahip, gerekçe ve bitiş tarihi taşır.
Kod özeti, komutun tamamını ve bulunduğu işlevi tanımlar.
Satır numarası değişse de aynı kod eşleşir.
Komut değişirse ya da birden çok bulgu aynı kayda uyarsa kapı hata verir.
Süresi geçen veya eşleşmeyen istisna denetimi durdurur.
Gitleaks yalnız kural, dosya, satır, commit ve parmak izi gösterir.

OSV-Scanner kökteki npm kilidini ve diğer izlenen kilitleri tarar.
Paket bulguları sürüm raporuna yazılır. Paket sürümü bu komutla değişmez.

Python kilidi, Git'in izlediği backend projelerinin `dependencies` listelerini kapsar.
Kilit isteğe bağlı paketleri kapsamaz.
