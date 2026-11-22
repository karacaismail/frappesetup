---
title: "AI · Genel bakış ve karar özeti"
nav: "Genel bakış"
order: 20
---

Bu bölüm Frappe ve Press için AI araçlarında üç kararı kayda geçirir: hazır depolardan ne alınır, depodaki `packages/press-ai` paketinde ne yazılır, hangi iş insanda kalır. Kanıt 8 Ekim 2026 tarihli statik okumadır: hazır depolar yüzeysel klonlardan, Press davranışı frappe/press develop `ebf3e22` kaynağından, kurulum sırası [Press kılavuzundan](https://karacaismail.github.io/pressguide/) okundu. Paket taslak aşamasındadır: bağımsız statik inceleme yapıldı, bulguların düzeltmeleri test sonuçlarıyla son koşuda doğrulanır; canlı Press doğrulaması `not_run`.

## Kararlar

1. **Teşhis için hazır olan kullanılır, kurulum ve dağıtım için yazılır.** Press içindeki MCP okuma ve teşhis araçları taşır; Release Group, App Source, Deploy Candidate, build ve deploy için onaylı araç hiçbir hazır depoda yoktur.
2. **İki yetki rolü.** `team` Dashboard API'sini takım başlığıyla çağırır; `operator` Press sitesinde System User'dır (Desk yolu). Kılavuzdaki grup, App, Source, candidate, build ve deploy adımları Desk yoludur. Takım yapılandırmadan gelir; System User takım denetimini atladığı için operatör kullanımında da takım kapsamı zorunludur.
3. **Her yazma insan onaylıdır** (G-86): öneri, ayrı terminalde insan onayı (özete bağlı, tek kullanımlık, süreli), tek yürütme, durum izleme. Modelde onay aracı ya da `confirm` bayrağı yoktur. Onay sunucuyla aynı işletim sistemi hesabında yazılır; model MCP üzerinden onay veremez, ama aynı hesapta kabuk erişimi olan bir süreç onay CLI'sini çalıştırabilir. Bu hız kesicidir, güvenlik sınırı değildir; ayrı onaylayıcı hesabı desteklenmez.
4. **Build ile deploy ayrıdır.** Deploy yalnız aynı build'in tüm adımları Success iken önerilir. Press'in deploy metodu bunu denetlemez; kural paketin ön koşuludur. Deploy siteleri doğrudan taşımaz, ama Press'in 15 dakikalık zamanlayıcısı otomatik güncellemesi açık sitelerde migrate dahil güncelleme açar; deploy onayı bunu kabul etmektir ve önizleme bu siteleri listeler. Yeni release de aynı kaynağı otomatik deploy açık kullanan her grupta build ve deploy tetikler; böyle grup varken, Press'te deploy işareti tanımlıyken ya da bu okunamıyorken release önerilmez.
5. **Kuyruğa alınma başarı değildir.** HTTP 200 ya da "kabul edildi" sonucu işin başarısı sayılmaz; başarı Press durumundan okunur. Yürütme aynı işlem ve hedef için uçuş kilidi alır ve istekten önce sonucu `unknown` olarak kaydeder. Zaman aşımı, kesilen yürütme ya da sonucu yazılmamış tüketilmiş öneri "sonuç bilinmiyor"dur: kör tekrar yok, insan `resolve` ile kapatana kadar o hedefe yeni öneri açılmaz.
6. **Gizli alan istenmez.** Build token'ı, özel anahtar, Agent Job istek verisi, GitHub token'ı ve imzalı yedek adresleri hiç okunmaz; okuma açık alan listesiyle yapılır.
7. **Uygulama geliştirmede iskelet davranış değildir.** MCP yapıyı okur, statik kuralları denetler ve iskelet üretir; iş mantığı ve genişletme kodu tek dosyalık kod önerisiyle (`write_file`) yazılır ve her öneri insan onayından geçer. MCP kodu çalıştırmaz; davranış yalnız geliştiricinin koştuğu test çıktısıyla doğrulanır. Resmi uygulamalar önce genişletme noktalarıyla genişletilir; çekirdek dosya değişikliği varsayılan olarak reddedilir ve yalnız uyarı, kullanıcının açık tekrarı ve `CORE <uygulama>` onayıyla yazılır; fork varsayılan değildir.
8. **Sınır işleri insanda kalır.** Altyapı (disk, cache temizliği, servis yeniden başlatma, registry, sunucu hazırlığı) Hüseyin Cengiz'dedir. GoDaddy DNS kaydını Hüseyin Cengiz hazırlar ve doğrular, Asistan Hüseyin uygular. Yasal kutu ve ödeme hesap sahibindedir.
9. **Puan yerine kanıt.** Hazır depolar dosya yolu, test dosyası, kodda onay ve lisans dosyasıyla değerlendirilir. "Bulunamadı" ilgili dosyalarda kanıt çıkmadığı anlamına gelir, yokluğu kanıtlamaz.

## Göreve göre başlangıç

| Görev | Hazır alınabilecek | Paketteki karşılığı | Durum |
| --- | --- | --- | --- |
| Press build hatası, takılan iş | Press içi MCP (System Manager, `enable_mcp`) | `press-build-triage` skill, `press-diagnoser` ajanı | Salt okuma; taslak |
| Kılavuz sırasıyla kurulum ve dağıtım | yok | `press-operations`, `press-operator` | Öneri ve insan onayı; taslak |
| Siteye uygulama kurma, migrate, yedek | `huf` ham çağrıları (onaysız) | aynı | Öneri ve insan onayı; taslak |
| Özel Frappe uygulaması | `frappe/skills` (`frappe-app-dev`) | `frappe-custom-app`, `frappe-app-developer` | İskelet ve onaylı kod önerisi; davranış test çıktısıyla |
| Resmi uygulamayı genişletme | `frappe/skills` denetim kuralları | `frappe-app-extension` | Sürüme göre mekanizma sırası |
| Bağımsız inceleme | `deep-app-audit` doğrulama adımı | `frappe-change-reviewer` | Salt okunur; onay ve puan yok |
| Sunucu, disk, registry, DNS, yasal kutu, ödeme | — | devir metni | İnsan |

## Kanıt nasıl okunur

- İşlem statüleri kontrattan gelir: `implemented` (runtime yürütür ve fixture testi vardır), `read_only`, `planned`, `unsupported`, `not_applicable`, `unknown`. Canlı Press doğrulaması her işlemde `not_run`dır.
- Kılavuzun arayüz haritasındaki 11 729 düğüm metadata'dır (hepsi `executed: false`, `functionalTest: not_run`); düğüm ya da alan sayısı çalışan işlem sayısı değildir.
- Test sonuç sayıları son koşudan alınır; bu bölümde sayı uydurulmaz.

## Bu bölümdeki sayfalar

- [MCP sunucuları](/frappesetup/ai-mcp/): hazır sunucuların kanıt tablosu ve paketin `press-ai` sunucusu.
- [Skills](/frappesetup/ai-skills/): paketteki dört skill, kurulum, hazır skill depoları.
- [Agents](/frappesetup/ai-agents/): paketteki dört ajan, rol ayrımı, hazır ajan uygulamaları.
- [Press yetkinliği](/frappesetup/ai-press-yetkinlik/): kontrattan üretilen kapsam ve kılavuz kurallarının yeri.
- [Geliştirme planı](/frappesetup/ai-gelistirme/): paket durumu, kurulum, kabul ölçütleri, kalan sınırlar, sahipler.

## İncelenemeyenler

`frappe/lms` klonu tamamlanamadı. `Sena-Services/frappe-mcp-server`, `myrmline/erpnext_bot_ai` ve `Tariquaf/invoice-ocr-enhanced` GitHub'da bulunamadı (404). `m-fadil/mcp`, `frappe/mcp` çatalı olduğu için ayrıca incelenmedi. Belge işleme (OCR, çeviri) depoları kısa değerlendirildi: `erpnext_ocr` ve `language_translator` 2021'den beri güncellenmiyor, `Invoice-OCR` GPL ve basit ayrıştırma kullanıyor, `invoice2erpnext` ücretli harici API'ye bağlı; hiçbiri bu platformda hazır kullanılacak düzeyde değil.
