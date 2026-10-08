---
title: "AI · Genel bakış ve karar özeti"
nav: "Genel bakış"
order: 20
---

Bu bölüm, 40'tan fazla Frappe AI deposunun (MCP sunucuları, skill paketleri, ajan uygulamaları, belge işleme araçları) ve Press kılavuzunun karşılaştırmasıdır. Tarih 8 Ekim 2026. Hiçbir depo çalıştırılmadı; bulgular yüzeysel klonların okunmasına dayanır.

## Üç katmanlı AI yığını

| Katman | Görev | Hazır durum | Boşluk |
| --- | --- | --- | --- |
| Skill | Ajana Frappe ve Press bilgisi öğretir | Uygulama geliştirmede güçlü (`frappe/skills`, OpenAEC) | Press kurulum ve dağıtım **yok** |
| MCP | Ajana araç verir | Site verisi için olgun (Assistant Core, vyogotech), Press teşhisi için resmi MCP | Press **komut** araçları yok |
| Ajan | Karar verir ve araçları kullanır | Desk asistanları (Flow, Ask ALYF, Jarvis) | Çok kiracılı, Keycloak delegeli, Press ölçümlü ajan yok |

## Hangi depoyu nasıl kullanırsınız?

| İhtiyaç | Kullanın | Not |
| --- | --- | --- |
| Özel Frappe uygulaması yazdırmak | `frappe/skills` + seçilmiş OpenAEC skill'leri | `deep-app-audit` ayrı bir inceleme ajanıyla |
| Resmi uygulamayı genişletmek | `frappe/skills` denetim kuralları (A-serisi) | Monkey patch yok; hooks ve `super()` |
| Press'te hata aramak | Press MCP (`enable_mcp`) | Okuma ağırlıklı; yazma eylemleri `confirm` ister |
| Site verisiyle sohbet | Frappe Assistant Core, vyogotech, Flow | Yazmada onay ve audit kontrol edilir |
| Mesajlaşma/WhatsApp | Raven, `frappe_whatsapp` | AI'yı ayrı katmandan bağlayın |
| Press'te kurulum ve deploy | **hazır yok** | [Geliştirme planı](../ai-gelistirme/) |

## Ana bulgular

1. **Press teşhisi hazır, Press kurulumu yok.** Resmi Press MCP'si yaklaşık 66 araç taşır, çoğu okuma; Release Group, App Source, Deploy Candidate, build/deploy ve site oluşturma aracı yoktur. Bu işlemler yalnız Press Dashboard API'sindedir.
2. **Hazır skill'ler Press'i bilmez.** Resmi `frappe/skills` Press'ten hiç söz etmez; OpenAEC'in `frappe-ops-cloud` skill'i özet düzeyindedir ve release group ile app source terimlerini içermez.
3. **En yakın Press istemcisi `huf`'tur**; fakat yıkıcı araçlarda onay bayrağı bulunamadı, tek global API anahtarı kullanır ve kararsız `press.api.*` uçlarına bağlıdır; README üretim için önermez.
4. **Güvenlik tutarsızdır.** Kod düzeyinde onay yalnız birkaç depoda var; birkaçında paylaşılan servis anahtarı Frappe izinlerini aşıyor, kimliksiz uç nokta ve keyfi komut çalıştıran sunucular bulundu.
5. **Doğrulama eksiktir.** Skill'ler için gerçek eval yalnız `frappe-ui`'dedir.
6. **Lisanslar karışıktır**: AGPL, MIT, LGPL/MIT çelişkisi, lisanssız resmi skill deposu, ticari kullanımı yasaklayanlar. Karar kullanıcıya aittir.

## Bu bölümdeki sayfalar

- [MCP sunucuları](../ai-mcp/): on bir uygulamanın araç, kimlik, onay ve audit karşılaştırması.
- [Skills](../ai-skills/): kapsam, v16 durumu, doğrulama, lisans.
- [Agents](../ai-agents/): on altı asistan/ajan uygulaması ve Press ilişkisi.
- [Press yetkinliği](../ai-press-yetkinlik/): kılavuzdaki işlemler hangi araçla yapılabilir.
- [Geliştirme planı](../ai-gelistirme/): kendi skill, MCP ve ajanlarımız; aşamalar, sahipler, kabul ölçütleri.

## İncelenemeyenler

`frappe/lms` klonu tamamlanamadı (içerik alınamadı; yalnız bir uygulama olduğu için AI değerlendirmesi dışında kaldı). `Sena-Services/frappe-mcp-server`, `myrmline/erpnext_bot_ai` ve `Tariquaf/invoice-ocr-enhanced` GitHub'da bulunamadı (404). `m-fadil/mcp`, `frappe/mcp` çatalı olduğu için ayrıca incelenmedi. Belge işleme (OCR/çeviri) depoları kısa değerlendirildi: `erpnext_ocr` ve `language_translator` terk edilmiş (2021), `Invoice-OCR` GPL ve basit ayrıştırma, `invoice2erpnext` ücretli harici API'ye bağlı; bunlar bu platform için hazır kullanılacak seviyede değil.
