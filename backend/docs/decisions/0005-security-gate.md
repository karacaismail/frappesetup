# Backend güvenlik kapısı için araç seçimi

Kapı, Frappe kurallarını ve koda yazılmış gizli bilgileri denetler.
Uç listesini Python'un kod ağacını okuyan `ast` modülü çıkarır.

| Araç | Son kararlı sürüm | Lisans | Karar |
| --- | --- | --- | --- |
| Semgrep Community Edition | [1.186.0](https://github.com/semgrep/semgrep/releases/tag/v1.186.0) | [LGPL-2.1](https://github.com/semgrep/semgrep/blob/develop/LICENSE) | Frappe kurallarını yerel dosyadan çalıştırır. |
| Bandit | [1.9.4](https://github.com/PyCQA/bandit/releases/tag/1.9.4) | [Apache-2.0](https://github.com/PyCQA/bandit/blob/main/LICENSE) | Python denetimleri seçilen kurallarla örtüşür. |
| Gitleaks | [8.30.1](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1) | [MIT](https://github.com/gitleaks/gitleaks/blob/master/LICENSE) | Gizli bilgileri arar ve değerleri raporda gizler. |
| Schemathesis | [4.33.4](https://github.com/schemathesis/schemathesis/releases/tag/v4.33.4) | [MIT](https://github.com/schemathesis/schemathesis/blob/master/LICENSE) | OpenAPI sözleşmesinden istek üretir. Kapıya alınmadı. |

Resmî GitHub kayıtları 22 Kasım 2026 Pazar günü doğrulandı.
Semgrep ve Schemathesis kasımda sürüm çıkardı.
Bandit şubatta, Gitleaks martta sürüm çıkardı.
Yeni sürümlerde lisansı ve kural testlerini yeniden denetleyin.

Semgrep, `uvx` ile sabit sürümden çalışır.
Gitleaks, Colima'da sabit sürümlü imajdan çalışır.
Araçlar uygulamaya paket olarak eklenmez.
Araç değişikliği gerekirse komuttaki ilgili adımı önceki sürüme döndürün.
Kural örneklerini ve kapıyı tekrar çalıştırın.

Bu turda çalıştırılan kapı kaynak dosyalarını okur.
Canlı site taraması ayrı bir iş olarak kayıtta kalır.
