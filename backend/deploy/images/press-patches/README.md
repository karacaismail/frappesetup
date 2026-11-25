# Press yama dizisi

Bu klasör Press'in üretim imajına giren yamaları tutar. İmajı `../press.Dockerfile` derler.

Press sürümü v0.154.1 olarak sabittir. Kaynak `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` commit koduyla doğrulanır.

## Yamalar nasıl uygulanır

Derleme yamaları ad sırasıyla uygular. Her yamadan önce `git apply --check` çalışır. Bir yama tutmazsa derleme durur. Çalışan kapta kod değiştirilmez.

| Yama | Amacı | Press'e öneri |
| --- | --- | --- |
| `0001-typeddict-dict-form.patch` | `TypedDict` tanımını Python 3.14'te açılır yapar | Öneri 1 |
| `0002-press-telemetry-helper.patch` | Telemetri işlevini Frappe yerine Press'ten alır | Öneri 2 |
| `0003-request-cookies.patch` | Çerezi Frappe 16'nın istek nesnesinden okur | Öneri 3 |
| `0004-optional-telegram.patch` | Telegram paketi yoksa da Press'in açılmasını sağlar | Öneri 5 |
| `0005-dependency-pins.patch` | Bağımlılık sürümlerini Python 3.14 ve Frappe 16'ya uyarlar | Öneri 4 |
| `0006-queue-setup-wizard.patch` | Site “Active” olunca kurulum sihirbazını kuyruğa atar (G-42) | Öneri 6 |

Öneriler `backend/docs/press-python314-upstream.md` dosyasındadır. Her yamanın başında amacı ve kaldırma koşulu yazılıdır.

## Ne zaman kaldırılır

Press bir yamanın düzeltmesini yayımlarsa o yama silinir. Sonra Press sürümü yeni sürüme taşınır. Bu kural proje kaydındaki O-52 kararıdır.

## Lisans

Press, AGPL-3.0 lisanslıdır. Bu yamalar Press kodundan türer. Bu yüzden yamalar da AGPL-3.0 lisanslıdır. Deponun öteki kodu MIT lisansıyla kalır. `press_tr` de AGPL-3.0 lisanslıdır (O-8).
