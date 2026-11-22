---
title: "AI · MCP sunucuları"
nav: "MCP sunucuları"
order: 21
---

Bu sayfa iki kararı verir: hangi hazır MCP sunucusu neye kullanılır ve paketin `press-ai` sunucusu nasıl çalıştırılır. Hazır depolar 8 Ekim 2026'da yüzeysel klonlardan okundu; hiçbiri kurulmadı. Seçimde ilk ölçüt kimliktir: tek paylaşılan servis anahtarıyla çalışan sunucu Frappe izin modelini aşar ve yetki eşitliği ilkesine (G-85) uymaz.

## Kararlar

- **Press teşhisi:** Press içi MCP (frappe/press `press/mcp`) okuma ve teşhis için kullanılabilir. Yalnız System Manager ve System User erişir, `Press Settings → Enable MCP` ile açılır; açmadan önce etkisini Hüseyin Cengiz inceler.
- **Press kurulum ve dağıtımı:** hazır sunucu yok; paketin `press-ai` sunucusu yazılır (taslak).
- **Site içi veri araçları:** kullanıcı kimliğiyle çalışan ve yazmayı kodda onaylayan model (vyogotech) ya da `frappe/mcp` çatısıyla yazılan araçlar (G-84). Paylaşılan anahtarlı proxy'ler kullanılmaz.
- **Ağa açılmaz:** kimliksiz uç açan ya da keyfi komut çalıştıran sunucular.

## Hazır sunucular: kanıt

| Depo | Biçim | Lisans | Kimlik | Yazma onayı (kodda) | Denetim izi | Test kanıtı | Press ve altyapı |
| --- | --- | --- | --- | --- | --- | --- | --- |
| frappe/press `press/mcp` | Press içi | bu incelemede okunmadı | System Manager, System User | yazan araçlarda `confirm=True` | gizli değer maskeleme | incelenmedi | telemetri, log, disk teşhisi; kurulum ve dağıtım aracı yok |
| frappe/mcp | Frappe app kütüphanesi (`pip install frappe-mcp`) | MIT | Frappe oturumu, OAuth2 | yok (yalnız çatı) | yok | 4 test dosyası | yok |
| buildswithpaul/Frappe_Assistant_Core | Frappe app | AGPL-3.0 | OAuth 2.0, API anahtarı | genel önizleme yok | `Assistant Audit Log` | yaklaşık 50 test dosyası | yok |
| vyogotech/frappe-mcp-server | Go proxy | MIT | OAuth2 bearer, `sid`, API anahtarı | tek kullanımlık onay token'ı | log satırı | yaklaşık 60 test dosyası | yok |
| skaslam1407/Frappe-MCP-Server | Python, yerel bench ya da SSH | MIT | tam ve salt okunur token | onay kapısı | JSONL | 19 test dosyası | bench, site, app, yedek; `fc_request` |
| TrueDevs-Inc/frappe-mcp | Frappe app | MIT | OAuth 2.1, zorunlu PKCE S256 | yok; yazma varsayılan kapalı | yok | yaklaşık 32 test | yok |
| mascor/frappe-mcp-server | Frappe app (REST, MCP değil) | MIT | `X-MCP-Token`, tek servis kullanıcısı | yok | `MCP Audit Log` | 6 test | yok |
| appliedrelevance/frappe-mcp-server | Python proxy | LICENSE dosyası yok | paylaşılan API anahtarı | yok | yok | 5 test | yok |
| SajmustafaKe/frappe-dev-mcp-server | TypeScript, yerel bench | MIT | yok | yok | yok | yalnız ad-hoc betikler | keyfi bench komutu |
| danielsebastianc/frappe-api-mcp | Node proxy | bulunamadı | ortam değişkeni token | yok | yok | 2 test | genel REST proxy |

Notlar: Assistant Core'un riskli yüzeyi `run_python_code` ve `run_database_query` araçlarıdır. mascor `delete_doc` içinde `ignore_permissions=True` kullanır (`mcp_server/api.py:347`). SajmustafaKe kimliksiz SSE ucu ve `execSync` ile komut çalıştırır. `Sena-Services/frappe-mcp-server` erişilemedi (404).

## Paketin sunucusu: `press-ai`

- **Ne:** stdio MCP, Python 3.9+ yalnız stdlib, 14 araç. Bağlam: `kit_status`. Kontrat: `contract_search`, `contract_get`, `ui_reference_search`. Press okuma: `press_read`, `press_triage_build`. Press yazma akışı: `press_propose`, `proposal_get`, `press_execute`, `press_track`. Uygulama: `app_inspect`, `app_check`, `app_propose_change`, `app_apply`.
- **Kimlik:** kullanıcının kendi Press API anahtarı (keychain ya da yalnız sahibinin okuyabildiği dosya); `team` ve `operator` rolleri. Mutasyonlar yapılandırmada açılmadıkça kapalıdır. `team` rolünde Press, üye olunmayan takım başlığında sessizce varsayılan takıma geçer; araç Press'in çözdüğü takımı yapılandırılanla karşılaştırır.
- **Onay:** ayrı terminalde, sunucuyla aynı işletim sistemi hesabıyla verilir (`same_os_account`). Model MCP üzerinden onay veremez, ama aynı hesapta kabuk erişimi olan bir süreç onay CLI'sini çalıştırabilir: hız kesicidir, güvenlik sınırı değildir. Ayrı onaylayıcı hesabı desteklenmez.
- **Yok:** onay aracı; `confirm`, `approved`, `force` alanı; kabuk, SSH, Server Script, ham SQL, ham Python. Eski özel SSH MCP'si ayrı kalır, değiştirilmez ve bu kararların yerine geçmez.
- **Uygulama araçları** yapı okur, statik kural denetler, iskelet üretir ve tek dosyalık kod önerisini (`write_file`) insan onayından sonra yazar. Kod çalıştırılmaz ve içe aktarılmaz. Resmi uygulama (core) dosyaları varsayılan olarak reddedilir; yalnız uyarı, kullanıcının açık tekrarı ve `CORE <uygulama>` onayıyla yazılır. Biçimlenmiş SQL (SEC002) ve misafir uçta `ignore_permissions` (SEC003) reddedilir; özel izin değişikliği önizlemede not olarak görünür. `bench migrate` ve test koşusu insan komutudur; davranış ancak test çıktısıyla doğrulanır.
- **Durum:** taslak. Bağımsız statik inceleme yapıldı; bulguların düzeltmeleri fixture testleriyle doğrulanır. Gerçek MCP istemci oturumu ve canlı Press `not_run`.

### İndir

MCP ZIP'i yalnız çalışma zamanını taşır: `server.py`, `press_ai`, kontratlar, örnek yapılandırma ve lisanslar. Açılan dizinde `python3 -I packages/press-ai/server.py check-contract` ile denetlenir.

<div data-embed="dl-mcp"></div>

Kurulum ve onay komutları [geliştirme planındadır](/frappesetup/ai-gelistirme/); hangi işlemin uygulandığı [Press yetkinliği](/frappesetup/ai-press-yetkinlik/) sayfasındaki kapsam tablosundadır.

## Press işlemleri: kim ne yapıyor

| İşlem | Press içi MCP | skaslam1407 | huf | press-ai (taslak) |
| --- | --- | --- | --- | --- |
| Grup, app ekleme, release, candidate | yok | dolaylı (`fc_request`) | kısmi (`press.api.bench.new`, `press.api.bench.add_app`) | öneri ve insan onayı |
| Build ve ayrı deploy | yok | yok | yok | öneri ve insan onayı; deploy için build Success ön koşulu |
| Site oluşturma | yok | `site_create` (yerel bench) | var, onaysız | insanda (plan, bölge, yasal kutu) |
| Siteye app, migrate, yedek | işletim araçları (`restart_bench` gibi) | `app_install`, `migrate`, `backup_create` | var, onaysız | öneri ve insan onayı |
| Teşhis (log, telemetri, disk) | güçlü | sınırlı | yok | build adımları, Error Log, Agent Job; sunucu logu yok |
| SSH, disk temizliği, DNS | bazı komutlar `confirm` ile | SSH | yok | devir (Hüseyin Cengiz, Asistan Hüseyin) |
