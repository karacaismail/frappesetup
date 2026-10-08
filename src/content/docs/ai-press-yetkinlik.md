---
title: "AI · Press işlemleri yetkinlik matrisi"
nav: "Press yetkinliği"
order: 24
---

Soru: [Press kılavuzundaki](https://karacaismail.github.io/pressguide/) işlemlerden hangisi hangi araçla yapılabilir ve hangi kural nerede zorlanır? Kapsam tablosu paketin operasyon kontratından (`packages/press-ai/contracts/`) üretilir; elle yazılmaz. Kaynaklar: frappe/press develop `ebf3e22` (statik), pressguide `2b83441` (67 adım: 54 canlı, 13 tarihsel). Kurulu Press'in commit'i bilinmiyor; canlı uyum `unknown`, canlı Press doğrulaması `not_run`.

## Statüler

- `implemented` (uygulandı): runtime işlemi yürütür (öneri, insan onayı, yürütme, izleme) ya da okumayı yapar; fixture testi vardır.
- `read_only`: MCP durumu okur; eylemi insan arayüzde yapar.
- `planned`: kaynak doğrulandı, bilerek henüz uygulanmadı.
- `unsupported`: bu MCP'nin yetkisiyle yapılmaz (SSH, GoDaddy, yasal kutu, ödeme, yıkıcı işlem); devir zorunlu.
- `not_applicable`, `unknown`: işlem değil ya da kaynak doğrulanamadı.

Kılavuzun arayüz haritasındaki 11 729 düğüm işlev kanıtı değildir (hepsi `executed: false`, `functionalTest: not_run`, `auditPhase: in_progress`).

## Kapsam

<!-- press-ai:coverage:start -->

| Aile | uygulandı | salt okuma | planlı | desteklenmez | uygulanamaz | bilinmiyor | Toplam |
| --- | --- | --- | --- | --- | --- | --- | --- |
| App, Source, Release Group | 7 | 0 | 6 | 0 | 0 | 0 | 13 |
| Candidate, build, deploy | 8 | 0 | 1 | 1 | 0 | 0 | 10 |
| Bench ve site | 7 | 2 | 2 | 0 | 0 | 0 | 11 |
| İşler ve teşhis | 4 | 0 | 3 | 1 | 0 | 0 | 8 |
| Yedek | 2 | 0 | 1 | 1 | 0 | 0 | 4 |
| Sunucu ve altyapı | 2 | 0 | 0 | 7 | 0 | 0 | 9 |
| Erişim ve ayarlar | 2 | 0 | 1 | 2 | 0 | 0 | 5 |
| Uygulama geliştirme | 11 | 0 | 3 | 3 | 0 | 0 | 17 |
| **Toplam** | 43 | 2 | 17 | 15 | 0 | 0 | **77** |

Kılavuzun 67 adımı, adımdaki en zayıf işlemin statüsüne göre: 36 uygulandı, 2 salt okuma, 19 planlı, 10 desteklenmez. En az bir işlemi uygulanmış adım: 60. Canlı Press doğrulaması: `not_run`.

<!-- press-ai:coverage:end -->

"Uygulandı" sayısı statik kaynak ve fixture kanıtıdır; paket taslak aşamasındadır, bağımsız statik inceleme bulgularının düzeltmeleri son koşuda doğrulanır.

## Kılavuz kuralları nerede zorlanır

| Kural | Kılavuz adımı | Nerede |
| --- | --- | --- |
| Önce build, Success'ten sonra ayrı deploy | `schedule`, `live-build-success` | Deploy önerisi aynı build'in tüm adımları Success iken açılır; Press'in deploy metodu bunu denetlemez |
| Build ile deploy'u birleştiren yol kullanılmaz | `schedule` | Dashboard'un birleşik deploy çağrısı ve Schedule Build and Deploy uygulanmaz |
| Bir candidate için tek deploy | `live-build-success` | Press'in tekilleştirmesi build adına bakıp kaydı candidate adıyla yazar; denetim pakette candidate adıyla yapılır |
| Sonuç görülmeden tekrar gönderilmez | `site`, `preparing` | Öneri tek kullanımlıktır; aynı işlem ve hedef için uçuş kilidi; istekten önce sonuç `unknown`; zaman aşımı ya da kesilen yürütme `unknown` kalır ve insan `resolve` ile kapatana kadar o hedefe yeni öneri açılmaz |
| Yeni release otomatik deploy tetikleyebilir | `release` | Aynı App Source'u `enable_auto_deploy` açık kullanan herhangi bir grup varsa release önerilmez. Press Settings'te deploy işareti tanımlıysa dağıtılacak grubu commit mesajı belirler; ön koşul doğrulanamaz ve öneri engellenir. Kanıt okunamıyorsa (ör. `team` rolü) da önerilmez, insan karar verir |
| Deploy çalışan sitelerde migrate'e yol açabilir | `schedule` | Deploy siteleri doğrudan taşımaz; Press'in 15 dakikalık zamanlayıcısı otomatik güncellemesi kapalı olmayan sitelerde migrate dahil güncelleme açar. Önizleme bu kümeyi listeler (Broken siteler ayrı), onay bunu kabul etmektir; 500'den fazla sitede önizleme eksikse öneri engellenir; build, image, platform ve site kümesi yürütmede farklıysa yürütme engellenir |
| İlk Failure satırı okunur; Pending satırları hata değildir | `hata-tanisi`, `live-upload-row` | `press-build-triage` sırası |
| Boş filtre "iş yok" ya da "hata yok" değildir | `live-no-error-at-preparing`, `live-no-job-at-preparing` | Terminal durumdan sonra ve filtresiz yeniden okuma |
| "Required app not found" önce App ve Source bağımlılığıdır | `live-error`, `identity-error` | Sınıflama; düzeltme grup yapılandırmasında |
| Kuyruğa alınma başarı değildir | `site`, `live-site-active-apps` | Yedek, migrate ve app kurma iş adı döndürmez; sonuç site iş listesinden izlenir; zaten kurulu app `no_op` |
| "No data" sıfır kullanım değildir | `live-analytics-daily-usage` | Log server yoksa kullanım verisi boş döner |
| Yasal kutu ve ödeme yalnız insanda | `site`, `live-site-header` | Uygulanmaz; hesap sahibine devir |

## İnsan kapıları

| İş | Sorumlu | Kabul ölçütü |
| --- | --- | --- |
| Disk ölçümü, onaylı build cache temizliği, servis yeniden başlatma, registry deposu, sunucu hazırlığı | Hüseyin Cengiz | Önce ve sonra ölçüm; ardından tek build ya da iş sonucu |
| GoDaddy DNS kaydı | Hüseyin Cengiz kaydı hazırlar ve doğrular; Asistan Hüseyin uygular | Çözümleme ve TLS doğrulaması açık HTTPS sonucu |
| Bölgesel yasal kutu, ödeme, plan ve ücretli Marketplace planı, site oluşturma formu | Hesap sahibi | İnsanın kendi işlemi; ajan işaretlemez, uygulama kurarken plan seçmez |
| Press kod düzeltmesi | Geliştirici yazar, bağımsız inceleme; kurulum Hüseyin Cengiz | Yedek ve SHA, önce kırmızı sonra yeşil test, yalnız gereken sürecin yeniden başlatılması |
| Geri yükleme | Site sahibi karar verir | Yedek durumu ve dosya erişilebilirliği önceden okunur |

## Hazır araçlarla fark

Press içi MCP telemetri, log ve disk teşhisinde güçlüdür ama kurulum ve dağıtım aracı taşımaz. `huf` Press API'sini çağırır ama onay ve takım ayrımı yoktur. skaslam1407'nin genel `fc_request` aracı onay kapılıdır, fakat grup, candidate ve build/deploy ayrımını modellemez. Ayrıntı: [MCP sunucuları](/frappesetup/ai-mcp/).
