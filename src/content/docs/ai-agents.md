---
title: "AI · Ajan ve asistan uygulamaları"
nav: "Agents"
order: 23
---

Bu sayfa paketteki dört ajanın rol ayrımını ve hazır Frappe ajan uygulamalarının kanıtını verir. Hazır depolar 8 Ekim 2026'da yüzeysel klonlardan okundu; testleri çalıştırılmadı. "Bulunamadı", ilgili dosyalarda kanıt çıkmadığı anlamına gelir.

## Kararlar

- **Rol ayrımı araç listesiyle yapılır.** Teşhis ve inceleme ajanlarında yazma aracı yoktur; yürüten ajan dosya yazamaz; geliştirme ajanı Press'te yürütme yapamaz. Hiçbir ajanda kabuk yoktur.
- **Ajan kendi işini onaylamaz.** Onay insanın ayrı terminaldeki komutudur; sohbetteki "onayladım" onay sayılmaz, yalnız öneri durumunun `approved` olması geçerlidir. Onay sunucuyla aynı işletim sistemi hesabında yazılır: ajanlarda kabuk olmadığı için model onay veremez, ama aynı hesapta kabuk erişimi olan bir süreç verebilir. Bu hız kesicidir, güvenlik sınırı değildir; ayrı onaylayıcı hesabı desteklenmez.
- **İnceleme bağımsızdır.** İnceleyen ajan değişikliği yazan oturumla aynı olamaz; eserlere bakar, yazarın gerekçesine değil. Bulgu insan onayına girdi olur, onayın yerine geçmez; puan verilmez.
- **Takım yapılandırmadan gelir** ve Press çıktısı güvenilmeyen veridir: kayıt alanındaki ya da logdaki talimat uygulanmaz (G-89).

## Paketteki ajanlar

Yol: `packages/press-ai/agents/<ad>.md` (Claude Code biçimi; ilgili skill önceden yüklenir). Durum: taslak; bağımsız statik inceleme yapıldı, düzeltmeler testlerle son koşuda doğrulanır.

| Ajan | Rol | Araç sınırı | Yapamadığı |
| --- | --- | --- | --- |
| `press-diagnoser` | Press build, deploy, bench, site ve metrik sorunlarını teşhis eder | Okuma araçları, `press_triage_build`, `press_track` | Öneri, yürütme, onay |
| `press-operator` | Öneri hazırlar, onaylanmış öneriyi bir kez yürütür, izler | Okuma, `press_propose`, `press_execute`, `press_track` | Onay vermek, dosya yazmak, kabuk, SSH |
| `frappe-app-developer` | Yapıyı okur, statik denetler; iskeleti ve gerçek kodu (`write_file`) önerir, onay sonrası yazar | `app_inspect`, `app_check`, `app_propose_change`, `app_apply`; Press'te yalnız `press_read` | Doğrudan dosya yazmak, core akışı dışında resmi uygulamaya (Press dahil) yazmak, Press'te öneri ve yürütme, bench, test çıktısı olmadan "geçti" demek |
| `frappe-change-reviewer` | Uygulama ve Press önerilerini bağımsız inceler | Okuma, `app_check`, `press_read` | Onay, yazma, puan |

Onay akışı: ajan öneriyi hazırlar ve durur; insan ayrı terminalde onay komutunu çalıştırır; ajan sonraki çağrıda öneri durumunu okur, `approved` ise bir kez yürütür ve sonucu izler. Komut ve kurulum [geliştirme planındadır](/frappesetup/ai-gelistirme/).

## İndir

Ajan dosyası tek başına `.claude/agents/` altına konur; ajanlar ilgili skill'leri önceden yükler. Skill'ler ve başvurularla birlikte kurmak için tüm paket kullanılır.

<div data-embed="dl-agents"></div>

## Hazır ajan uygulamaları: kanıt

| Depo | Rol | Yazma onayı (kodda) | MCP | Lisans | Press ilişkisi |
| --- | --- | --- | --- | --- | --- |
| frappe/flow (flow_client) | Resmi Desk ajanı, Frappe v16 | var (`requires_confirmation`) | bulunamadı | AGPL-3.0 | yok |
| frappe/builder | Site kurucu ajan "Bob" | var (Apply/Skip kartı) | yok | MIT | yok |
| frappe/raven | Mesajlaşma ve AI botları | bulunamadı | `HostedMCPTool` içe aktarılmış | AGPL-3.0 | bildirimler; Press API çağrısı doğrulanmadı |
| tridz-dev/huf | Çok ajanlı platform | kısmi (`ask_user`); Press araçlarında yok | istemci | AGPL-3.0 | Press API'sini çağıran tek depo (yaklaşık 45 araç, tek global anahtar) |
| aerele/jarvis | "AI takım arkadaşı" | var (Approval Board, onay kartı) | istemci | AGPL-3.0 | yalnız paketleme ve marketplace denetimi |
| alyf-de/ask_alyf | Desk sohbeti (Ask/Agent) | her yazmada | bulunamadı | AGPL-3.0 | yok |
| navdeepghai/nextassist | Çok sağlayıcılı asistan | kısmi | bulunamadı | MIT | yok |
| byt3crafter/erpnext-copilot | Desk sohbeti, 40+ araç | yalnız istemde (kodda zorlanmıyor) | yok | MIT | yok |
| ERPGulf/changai | Doğal dilden SQL | bulunamadı | bulunamadı | MIT | yok |
| MirzaAreebBaig/Frappe-FlowAgent | Görsel iş akışı ve AI | kısmi (onay düğümü) | yok | MIT | yok |
| AlazabDev/ai_chatbot | BI sohbeti ve belge çıkarma | yalnız belge çıkarma akışında | bulunamadı | MIT | yok |
| erpnextai/next_ai | Metin üretimi | yok | yok | özel lisans, ticari kullanım yasak | yok |
| KorucuTech/kai | CrewAI sarmalayıcı | yok | yok | MIT (2024'ten beri güncellenmiyor) | yok |
| shridarpatil/frappe_whatsapp_chatbot | WhatsApp botu | insana devir | yok | Commons Clause | yok |

Güvenlik bulguları: `next_ai` oturumsuz çağrılabilen bir LLM ucu açar ve API anahtarını süreç ortamına yazar; `kai` araçları izin denetimi yapmadan kullanıcı kaydı döndürür. İkisi üretimde kullanılmaz. `ignore_permissions=True` kullanımı yüksektir (Flow 58, Copilot 43, Builder 24, FlowAgent 21, WhatsApp botu 18).

## Nasıl faydalanılır

| Hedef | Önerilen | Neden |
| --- | --- | --- |
| Kiracı sitesinde kullanıcıya dönük asistan | Flow izlenir (not: sınıf C); staging'de Jarvis ve Huf; mimari referans Jarvis (KD-39, AI-08, AI-09) | yazmada kod düzeyinde onay, Frappe izinleri |
| Sayfa/site kurma | Builder + `frappe-builder` skill, yalnız pazarlama sayfası ve onay kapısı açık (not: sınıf B/C, çok yeni) | resmi; karar AI-08 |
| Mesajlaşmada bot | Raven AI | okuma ağırlıklı kullanılır; yazmaya onay eklenir |
| WhatsApp | `frappe_whatsapp` kanalı | AI ayrı katmandan bağlanır (lisans) |
| Press yönetimi | Hazır depo yok; paketin `press-operator` ve `press-diagnoser` ajanları (taslak) | huf araçlarında onay ve takım ayrımı yok |
| Doğal dilden rapor | ChangAI yerine Frappe izinli rapor araçları | ham SQL izin güvencesi zayıf |

## Lisans

`huf`, `jarvis`, `ask_alyf`, `raven` ve `flow` AGPL-3.0'dır: değiştirilip ağ üzerinden sunulan kodun kaynağı sunulmalıdır. AGPL bileşenleri MIT lisanslı kendi kodumuzla aynı süreçte birleştirilmeden önce lisans uyumu kullanıcıyla netleştirilir. `next_ai` ve `frappe_whatsapp_chatbot` OSI açık kaynak değildir; ücretli SaaS içinde kullanılamaz.

Hiçbir hazır depo platformun tüm gereksinimlerini (Keycloak ile delege token, kiracı kotası, AI denetim izi, Press defterine kredi ölçümü; G-87, G-92) karşılamaz; bu yüzden kendi ajan servisi gerekir ([Rail 5](/frappesetup/rail-5-ai/)).
