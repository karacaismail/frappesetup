---
title: "AI · MCP sunucuları"
nav: "MCP sunucuları"
order: 21
---

Bu sayfa on bir MCP uygulamasını karşılaştırır: resmi `frappe/mcp`, `frappe/press` içindeki Press MCP'si ve dokuz topluluk deposu (listedeki on ikinci aday erişilemedi). Kanıt, 8 Ekim 2026'da alınan yüzeysel (shallow) klonların okunmasına dayanır; hiçbir depo çalıştırılmadı ve kurulmadı. Commit tarihleri son commit'tir, bakım hızı değildir. Olgunluk puanı (1–5) öznel bir okumadır.

## Üç farklı şey: kütüphane, uygulama içi sunucu, harici proxy

| Tür | Ne yapar | Örnekler | Frappe izni |
| --- | --- | --- | --- |
| Kütüphane | Kendi app'inize araç yazmanız için çatı sağlar | `frappe/mcp` | Frappe oturumu/OAuth2 ile gelir |
| Uygulama içi sunucu | Frappe app olarak kurulur, WSGI içinde çalışır | Frappe Assistant Core, TrueDevs, mascor, **Press MCP** | Genelde kullanıcı kimliğiyle her çağrıda uygulanır |
| Harici proxy | Ayrı süreç, Frappe REST'ine API anahtarıyla gider | vyogotech (Go), appliedrelevance, danielsebastianc, skaslam1407, SajmustafaKe | Çoğunlukla tek servis hesabı; Frappe izni zayıflar |

Seçim ölçütü önce kimliktir: kullanıcı adına çalışmayan (tek paylaşılan API anahtarı) sunucu, Frappe'nin izin modelini devre dışı bırakır. Bu, platformun G-59/G-82 kararıyla (araç çağrısı kullanıcı token'ıyla yapılır) çelişir.

## Resmi: `frappe/mcp`

- Streamable HTTP MCP sunucusunu Frappe içinde kurmak için Python kütüphanesidir: `@mcp.tool()` ile fonksiyon kaydedilir, Google stili docstring ve tip ipuçlarından `inputSchema` çıkarılır.
- WSGI gerçeği nedeniyle resmi Python SDK'sı yerine sıfırdan yazılmıştır. README "yüksek derecede deneysel" uyarısı verir ve yalnız **Tools** destekler; resources ve SSE akışı yoktur (prompts kodda vardır, README'de listelenmez).
- Kimlik: OAuth2 (frappe#33188) olan sürümlerde doğrudan; yoksa istemci için OAuth Client kaydı gerekir. Hazır araç kataloğu, onay, audit ve oran sınırı yoktur; bunları siz yazarsınız.
- Olgunluk 3. Son commit 29 Mayıs 2026.

## Resmi (Press içinde): `press/mcp`

`frappe/press` deposunda ayrı bir ops MCP'si vardır (`Press Settings → Enable MCP`; yalnız System Manager ve System User). Yaklaşık 66 araç kaydedilidir; çoğu okuma ve teşhistir.

| Sınıf | Araçlar (örnek) |
| --- | --- |
| DocType okuma | `list_doctypes`, `get_doctype`, `list_documents`, `get_document`, `get_document_versions`, `get_agent_jobs_for_document`, `get_linked_documents` |
| Telemetri | `query_prometheus`, `query_elasticsearch`, `investigate_site`, `investigate_slow_site`, `get_top_slow_paths`, `get_site_error_trend`, `search_site_logs`, `inspect_trace_id` |
| Sunucu/bench dosya ve log | `tail_file_in_bench`, `grep_file_in_server`, `get_disk_usage_in_bench`, `get_server_storage_breakdown`, `tail_supervisor_log_in_bench` |
| Kod/uygulama bilgisi | `get_bench_apps_info`, `get_site_apps_info`, `get_app_release_clone_url` |
| Yazan eylemler (`confirm=True` ister) | `clear_site_cache`, `activate_site`, `restart_bench`, `cancel_stuck_jobs`, `run_supervisor_command_in_bench/server`, `run_systemctl_command_in_server`, `reboot_in_server` |

Güçlü yanlar: `confirm` bayrağı, yol/komut doğrulama ve gizli değer maskeleme (`guardrails/redaction.py`). Boşluk: **Release Group oluşturma, App Source oluşturma, uygulama ekleme, Deploy Candidate, build/deploy başlatma ve site oluşturma aracı yoktur**; bunlar yalnız Press Dashboard API'sindedir (`press.api.bench`, `press.api.site`).

## Topluluk sunucuları

| Depo | Biçim | Lisans | Araç | Kimlik | Onay | Audit | Puan |
| --- | --- | --- | --- | --- | --- | --- | --- |
| buildswithpaul/Frappe_Assistant_Core | Frappe app | AGPL-3.0 | 24 | OAuth 2.0, API key | yazmada yok | DocType (`Assistant Audit Log`) | 5 |
| vyogotech/frappe-mcp-server | Go proxy | MIT | 17 (14 okuma, 3 yazma) | OAuth2 bearer, `sid`, API key | evet (tek kullanımlık token) | yalnız log | 4 |
| skaslam1407/Frappe-MCP-Server | Python, yerel bench veya SSH | MIT | 49 (17 okuma, 32 yazma) | HTTP'de tam ve salt-okunur token | evet | JSONL | 4 |
| TrueDevs-Inc/frappe-mcp | Frappe app + OAuth | MIT | 14 (5 okuma, 9 yazma) | OAuth + zorunlu PKCE S256 | yok; yazma varsayılan kapalı | yok | 3 |
| mascor/frappe-mcp-server | Frappe app, REST (MCP değil) | MIT | 8 | `X-MCP-Token`, tek servis kullanıcısı | yok | DocType | 2 |
| appliedrelevance/frappe-mcp-server | Python FastMCP | LICENSE dosyası yok | ~18 | paylaşılan API anahtarı | yok | yok | 2 |
| SajmustafaKe/frappe-dev-mcp-server | TypeScript, yerel bench | MIT | 139 | yok | yok | yok | 2 |
| danielsebastianc/frappe-api-mcp | Node proxy | bulunamadı | 1 (`frappe_api`) | ortam değişkeni token | yok | yok | 1 |

Notlar:

- **Frappe Assistant Core** en olgun seçenektir: ~50 test dosyası, prompts ve resources, kullanıcı izni uygulanır. Riskli yüzeyi `run_python_code` ve `run_database_query` araçlarıdır; AGPL-3.0, kapalı kaynak SaaS ürününe bağlanırken hukuki inceleme ister.
- **vyogotech** kullanıcı kimliğiyle çalışan ve yazmayı tek kullanımlık onay token'ıyla kapılayan tek harici proxy'dir; yönetim aracı ve prompts yoktur.
- **skaslam1407** altyapıya en yakın olandır (aşağıda), fakat Frappe kullanıcı izin modelini uygulamaz ve `console_exec` ile geniş yazma yüzeyi açar. Tek commit'lik yeni bir depodur; README'deki prompts/resources kodda bulunamadı.
- **mascor** düz `!=` ile token karşılaştırır ve `delete_doc` içinde `ignore_permissions=True` kullanır (`mcp_server/api.py:347`); README "18/18 test" der, kodda 6 test vardır.
- **SajmustafaKe** kimliksiz SSE ucu ve `execSync` ile keyfi bench komutu çalıştırır; ağa açılmamalıdır.
- Depo listenizdeki `Sena-Services/frappe-mcp-server` erişilemedi (404: kaldırılmış ya da özel olabilir); `m-fadil/mcp` yalnız `frappe/mcp` çatalı olduğu için ayrıca incelenmedi.

## Altyapı işlemleri: kim ne yapıyor?

| İşlem | Press MCP | skaslam1407 | SajmustafaKe | Diğerleri |
| --- | --- | --- | --- | --- |
| Release Group / App Source / Deploy Candidate | yok | yok | yok | yok |
| Site oluşturma | yok | `site_create` (`bench new-site`, yerel/SSH) | `frappe_new_site` (yerel) | yok |
| Uygulama kurma | yok | `app_install` | `frappe_install_app` | yok |
| Frappe Cloud/Press API'sine genel istek | — | `fc_request` (yazma onay kapılı) | yok | danielsebastianc (dolaylı, test edilmedi) |
| Yedek / migrate / restart | `restart_bench` | `backup_create`, `migrate`, `restart` | keyfi bench komutu | yok |
| Log ve teşhis | **güçlü** (telemetri, loglar, disk) | sınırlı | yok | yok |

Sonuç: Press'te **teşhis** için resmi MCP yeterince güçlüdür; Press'te **kurulum ve dağıtım** işlemlerini yapan hazır bir MCP yoktur. Bu boşluk ve kapatma planı [Press yetkinlik matrisi](../ai-press-yetkinlik/) ile [geliştirme planı](../ai-gelistirme/) sayfalarındadır.
