# press-ai kontratları

Makinece okunur operasyon kontratı. Biçim ve sabit kimlikler `../INTERFACE.md` dosyasındadır; runtime (`press_ai/`) bu dosyaları yükler ve doğrular.

| Dosya | İçerik |
| --- | --- |
| `press/release.json` | Release Group, App, App Source, App Release |
| `press/build-deploy.json` | Deploy Candidate, build, build teşhisi, deploy |
| `press/bench-site.json` | Bench ve site (oluşturma, okuma, HTTPS, kurulum sihirbazı, uygulama kurma, migrate, güncelleme, işler) |
| `press/jobs-diagnostics.json` | Agent Job, Error Log, agent ping/sürüm, panel sürümü, kullanım analitiği, sunucu logları |
| `press/backups.json` | Yedek listesi, yedek alma, geri yükleme öncesi denetim, geri yükleme |
| `press/infrastructure.json` | Sunucu okuma ve altyapı sahibine devredilen işler (disk, build cache, servis, registry, DNS, katalog etiketi, Press kod düzeltmesi) |
| `press/access.json` | Takım bağlamı, roller, Press Settings bayrakları, ödeme, yasal kabul |
| `frappe-app-operations.json` | Yerel workspace'te Frappe uygulama geliştirme işlemleri |
| `guide-map.json` | pressguide'ın 67 adımı, kılavuz sırasıyla; her adımın rolü ve işlemleri |
| `sources.json` | Kaynak kimlikleri, sabit commit/sha256, lisans ve kullanım |
| `frappe-extension-points.json` | Frappe v15/v16 genişletme noktaları, karar sırası ve kurallar |

## Statüler ve sınırlar

- `implemented` yalnız runtime izin listesindeki 43 işlemde bulunur (Press 32, uygulama geliştirme 11); `params` şeması `python3 -I packages/press-ai/server.py schemas` çıktısıyla birebir aynıdır.
- `read_only`: eylemi insan yapar, MCP sonucu uygulanan okumalarla doğrular. `planned`: kaynak doğrulandı, bilinçli olarak uygulanmadı. `unsupported`: MCP yetkisi dışında (SSH, GoDaddy, ödeme/yasal kabul, yıkıcı işlem, Press kod değişikliği); `owner_handoff` sahibini ve kabul ölçütünü yazar.
- Doğrulama statiktir: `frappe/press` develop `ebf3e22`, `frappe/frappe` version-15 `b0b5b99` ve version-16 `6b450a1` dal uçları. Kurulu canlı Press'in commit'i bilinmiyor; her işlemde `verification.live` değeri `not_run`'dır.
- Sitemap düğüm kimlikleri yalnız UI konumu için atıftır; 11 729 düğümün hiçbiri işlev testi değildir ve düğüm sayısı işlem sayısı değildir.
- Kurulumdan kayıt adı, IP, alan adı, kişisel veri veya secret yazılmaz. Kaynak koddan metin kopyalanmaz; yol + satır aralığı ile atıf yapılır. Depo lisansları (`LICENSE`, `LICENSE-CONTENT`) değiştirilmedi.

## Doğrulama

```sh
python3 -I packages/press-ai/server.py check-contract --guide <pressguide>/src/data/guide.json --sitemap <pressguide>/src/data/press-sitemap.json
```

Komut kılavuz sırasını, sitemap kimliklerini, kaynak kimliklerini, makine ön koşullarını, izleme problarını ve `implemented` ↔ runtime eşitliğini denetler; çıkış kodu 1 hata olduğunu gösterir.
