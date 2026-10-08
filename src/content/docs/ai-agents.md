---
title: "AI · Ajan ve asistan uygulamaları"
nav: "Agents"
order: 23
---

Bu sayfa, Frappe içinde çalışan on altı AI asistanı, ajan ve ilgili kanal uygulamasını inceler. Kanıt 8 Ekim 2026'da alınan yüzeysel klonların okunmasıdır; testler çalıştırılmadı. Olgunluk puanı (1–5) öznel bir okumadır; "bulunamadı" ifadesi, ilgili dosyalarda kanıt çıkmadığı anlamına gelir ve yokluğu kanıtlamaz.

## Karşılaştırma

| Depo | Rol | LLM sağlayıcıları | Araç çağrısı | MCP | Yazma onayı | Lisans | Puan |
| --- | --- | --- | --- | --- | --- | --- | --- |
| frappe/flow (flow_client) | Resmi Desk ajanı, Frappe v16 | LiteLLM (Anthropic, OpenAI, OpenRouter, Ollama) | evet (`@tool`) | bulunamadı | evet (`requires_confirmation`) | AGPL-3.0 | 3 |
| frappe/builder | Site kurucu ajan "Bob" | LiteLLM, OpenRouter, Codex | evet | yok | evet (Apply/Skip kartı) | MIT | 5 (AI 4) |
| frappe/raven | Mesajlaşma + AI botlar | OpenAI Agents SDK, yerel LLM | evet | `HostedMCPTool` içe aktarılmış | bulunamadı | AGPL-3.0 | 4 (AI 3) |
| tridz-dev/huf | Çok ajanlı platform | LiteLLM (çok sağlayıcı) | evet | **istemci** + OAuth | kısmi (`ask_user`) | AGPL-3.0 | 4 |
| aerele/jarvis | "AI takım arkadaşı" | havuz modeli, 10+ sağlayıcı | evet | **istemci** | **güçlü** (Approval Board) | AGPL-3.0 | 4 |
| alyf-de/ask_alyf | Desk sohbeti (Ask/Agent) | LangChain, LiteLLM | evet | bulunamadı | **her yazma** | AGPL-3.0 | 4 |
| navdeepghai/nextassist | Çok sağlayıcılı asistan | OpenAI, Anthropic, Gemini, Claude Code | evet | bulunamadı | kısmi | MIT | 3 |
| byt3crafter/erpnext-copilot | Desk sohbeti, 40+ araç | OpenAI, Anthropic | evet | yok | yalnız istemle | MIT | 3 |
| ERPGulf/changai | Doğal dilden SQL | Gemini, Qwen3, Claude | hayır (boru hattı) | bulunamadı | bulunamadı | MIT | 3 |
| MirzaAreebBaig/Frappe-FlowAgent | Görsel iş akışı + AI | yalnız Claude | evet | yok | kısmi (onay düğümü) | MIT | 2–3 |
| AlazabDev/ai_chatbot | BI sohbeti + belge çıkarma | OpenAI, Claude, Gemini, Ollama, vLLM | evet | bulunamadı | yalnız IDP akışı | MIT | 2–3 |
| erpnextai/next_ai | Metin üretimi | yalnız Gemini | hayır | yok | yok | **özel, ticari kullanım yasak** | 2 |
| KorucuTech/kai | CrewAI sarmalayıcı | Groq, Ollama | CrewAI | yok | yok | MIT | 1–2 (2024'ten beri durgun) |
| shridarpatil/frappe_whatsapp | WhatsApp kanalı | AI yok | — | — | — | MIT | 4 (AI değil) |
| shridarpatil/whatsapp_chat | Desk WhatsApp arayüzü | AI yok | — | — | — | GPL-2.0 | 3 |
| shridarpatil/frappe_whatsapp_chatbot | WhatsApp botu | OpenAI, Anthropic, Google | hayır | yok | insana devir | Commons Clause | 3 |

## Bizim mimari için en önemli bulgular

1. **Press API'sini gerçekten çağıran tek depo `tridz-dev/huf`'tur.** `huf/ai/tools/frappe_cloud.py`, `https://cloud.frappe.io/api/method/...` adresine `token key:secret` ile gider ve yaklaşık 45 `fc_*` aracı açar: `press.api.bench.{all,get,new,archive,add_app}`, `press.api.site.{new,archive,backup,migrate,clear_cache,install_app,login,...}`, sunucu oluşturma/arşivleme/reboot. Sınırları: tek global API anahtarı, yıkıcı araçlarda (arşivle, sil, reboot) araç düzeyinde onay bayrağı bulunamadı, `press.api.*` kararlı genel API olmadığı için şema değişince kırılır, testler `httpx` mock'ludur (canlı Press testi yok). **Release Group ve App Source oluşturma/değiştirme çağrısı yoktur**; uygulama ekleme `add_app(source=...)` ile yapılır. README ve CLAUDE.md "üretim için önerilmez" der.
2. **`aerele/jarvis` Press'i yönetmez.** Press ile ilişkisi yalnız paketleme uyumu ve CI'da `frappe/press` Semgrep kurallarını çalıştırmaktır. Onay mimarisi (Approval Board, `confirm_card`, değiştirilemez çalışma anlık görüntüleri, `agent_audit`) örnek alınacak en iyi tasarımdır; fakat çekirdek çalışma zamanı Aerele'nin barındırılan "fleet" hizmetine bağlıdır ve tek başına self-host edilebilirliği belirsizdir.
3. **Onay modeli**: kod düzeyinde zorlanan onay yalnız Flow (`requires_confirmation`), Builder (`pending.py`), Jarvis ve Ask ALYF'de vardır. Copilot'ta onay yalnız sistem istemindedir; model atlayabilir. Bizim ilkemiz (önizle + onayla, G-83..G-92) bu dört yaklaşımdan çıkarılır.
4. **Prompt-injection**: ayrı savunma yalnız `erpnext-copilot` içinde bulundu (`prompt_defense.py` + test) ve `huf` bellek zarfında ("veri, talimat değildir") var. Diğerlerinde bulunamadı. Ajanın okuduğu kayıt alanı (örn. destek talebi metni) araç çağrısını yönlendirebilir.
5. **İzin atlama**: `ignore_permissions=True` sayıları yüksektir (Flow 58, Builder 24, FlowAgent 21, Copilot 43, WhatsApp chatbot 18). Çoğu sistem içi kayıt içindir, ama anonim girdiyle birleştiği yerde (WhatsApp chatbot) risk büyür.
6. **Güvenlik hataları**: `next_ai` içinde `allow_guest=True` bir LLM uç noktası ve API anahtarını `os.environ` içine yazma (çok kiracılı süreçte sızıntı riski) bulundu; `kai` araçları izin denetimi yapmadan kullanıcı kaydı döndürür. Bu ikisi üretimde kullanılmamalıdır.

## Lisans uyarısı: AGPL

`huf`, `jarvis`, `ask_alyf`, `raven`, `flow` AGPL-3.0'dır. Kodu değiştirip ağ üzerinden hizmet olarak sunmak, değiştirilmiş kaynağı sunmayı gerektirir. Depo ilkemiz zaten açık kaynaktır, ama AGPL bileşenleri MIT lisanslı kendi `platform_core` kodumuzla aynı süreçte birleştirmeden önce lisans uyumu kullanıcıyla netleştirilmelidir. `next_ai` (ticari yasak) ve `frappe_whatsapp_chatbot` (Commons Clause) OSI açık kaynak değildir ve ücretli SaaS içinde kullanılamaz.

## Nasıl faydalanılır

| Hedef | Önerilen | Neden |
| --- | --- | --- |
| Kiracı sitesinde kullanıcıya dönük asistan | Flow (v16) veya Ask ALYF; mimari referans için Jarvis | yazmada kod düzeyinde onay, Frappe izinleri |
| Sayfa/site kurma | Builder + `frappe-builder` skill | zaten resmi ve testli |
| Mesajlaşmada bot | Raven AI | yalnız okuma ağırlıklı kullanılmalı; yazmaya onay ekleyin |
| WhatsApp | `frappe_whatsapp` kanalı | AI'yı ayrı katmandan bağlayın (lisans) |
| Press yönetimi | **hiçbiri üretime hazır değil** | huf `fc_*` araçları esin kaynağı; onay ve ayrıştırma eksik |
| Doğal dilden rapor | ChangAI yerine Frappe izinli rapor/aggregate araçları | ham SQL izin güvencesi zayıf |

Hiçbir depo bizim tasarımımızın tüm gereksinimlerini (Keycloak JWT ile kullanıcıya delege edilmiş token, kiracı kotası, AI Action Log, Press defterine kredi ölçümü) karşılamaz; bu yüzden kendi ajan servisimiz gerekir ([geliştirme planı](../ai-gelistirme/)).
