# press-ai paylaşılan arayüzü

Bu dosya `packages/press-ai` paketinin parçaları arasındaki sözleşmedir: operasyon kontratı biçimi,
sabit kimlikler, MCP araç adları, skill/agent adları ve yetki sınırı. Runtime (`press_ai/`) ve testler
bu dosyaya göre doğrular; bir kimlik veya alan değişecekse önce burası değişir.

## Dizinler

| Dizin | İçerik |
| --- | --- |
| `contracts/` | Makinece okunur operasyon kontratı, kılavuz eşlemesi, kaynak listesi, Frappe genişletme noktaları |
| `skills/` | `SKILL.md` + gerekli `references/` (görev seçimi, sıra, hata/geri alma) |
| `agents/` | Rol tanımları (Claude Code biçimi) |
| `references/` | Birden çok skill'in paylaştığı kaynaklı başvuru metinleri |
| `press_ai/`, `server.py` | MCP stdio runtime ve insan onay CLI'si (Python 3.9+, yalnız stdlib) |
| `tests/`, `config/` | Birim/güvenlik/senaryo testleri, sahte Press sunucusu, örnek yapılandırma |

Kod MIT (`LICENSE`); `LICENSE-CONTENT` (CC BY 4.0) yalnız sitenin `src/content/` ve `src/data/` içeriğini kapsar.
Lisanssız kaynaktan (pressguide: LICENSE yok, aynı yazar;
frappe/skills: LICENSE yok) metin kopyalanmaz; yol + commit ile atıf yapılır. Gizli değer, müşteri ya da kişisel veri yazılmaz.

## Kaynaklar ve doğrulama düzeyi

- `frappe/press` `ebf3e2272dc386e9ceb5e064d6c911d7e2adb7c9` (develop, 2026-10-08): API ve DocType doğrulaması (statik).
- `karacaismail/pressguide` `2b83441b01db520f62480e21ba6d5fc51745a47f`: `src/data/guide.json` 67 adım (54 live, 13 historical);
  `src/data/press-sitemap.json` 11 729 UI metadata düğümü (hepsi `executed: false`, `functionalTest: not_run`, `auditPhase: in_progress`).
  UI düğümü/alan sayısı çalışabilir operasyon sayısı değildir; etiket veya metadata bütünlüğü işlev PASS değildir.
- Kurulu canlı Press'in commit'i bilinmiyor (kılavuz: Press 0.7.0 develop, panel Frappe version-15). Kontrat develop@ebf3e22'ye göre
  statik doğrulanır; canlı uyum `unknown`, canlı Press testi `not_run`.

## Yetki rolleri (principal) ve iki MCP'nin ayrımı

- `team`: Press Dashboard API. `POST {base}/api/method/press.api.<modül>.<fn>`; başlıklar `Authorization: token <key>:<secret>`,
  `X-Press-Team: <takım>`. `@protected("<DocType>")` takım sahipliğini denetler (System User hariç). Dashboard'un genel istemcisi
  `press.api.client.run_doc_method` yalnız `@dashboard_whitelist` metotlarını çalıştırır.
- `operator`: Press sitesinde System User (kılavuzdaki Desk yolu). Frappe Desk API: `frappe.client.get`, `frappe.client.get_list`,
  `POST /api/method/run_doc_method {dt, dn, method, args}` (yalnız `@frappe.whitelist()` doc metotları, doc izniyle).
- `infrastructure_owner` (Hüseyin Cengiz), `dns_owner` (GoDaddy: Hüseyin Cengiz kaydı hazırlar ve doğrular, Asistan Hüseyin uygular),
  `account_holder` (yasal kutu, ödeme), `app_developer` (yerel bench komutları): MCP bunları yürütmez; kontrat devri yazar.
- Bu paketin MCP'si (`press-ai`) kullanıcının kendi Press yetkisiyle HTTPS konuşur; shell, SSH, Server Script, ham SQL, ham Python yoktur.
  Eski özel SSH MCP'si (stdio, 5 araç, SSH ControlMaster üzerinden root; `--full-admin` keyfi komut) ayrıdır; bu paket onu çağırmaz,
  değiştirmez ve onun yerine geçmez.

## Statü sözlüğü (her operasyon tam birini taşır)

- `implemented`: `press-ai` aracı işlemi yürütür (öneri → insan onayı → yürütme → izleme) ya da okuma/analizi tam yapar; fixture testi zorunlu.
- `read_only`: MCP ilgili durumu okur/doğrular; eylemin kendisini insan arayüzde yapar.
- `planned`: kaynak doğrulandı, kasıtlı olarak henüz uygulanmadı (gerekçe zorunlu).
- `unsupported`: bu MCP'nin yetkisiyle yapılmaz (SSH, GoDaddy, yasal/ödeme, yıkıcı); devir zorunlu.
- `not_applicable`: operasyon değil (anlatı/gözlem).
- `unknown`: API veya kaynak doğrulanamadı.

Canlı Press doğrulaması her operasyonda `not_run`dır; `implemented` statik kaynak + fixture kanıtıdır.

## Operasyon kontratı

Dosyalar: `contracts/press/{release,build-deploy,bench-site,jobs-diagnostics,backups,infrastructure,access}.json` ve
`contracts/frappe-app-operations.json`. Her dosya `{"family": "<aile>", "operations": [OPERATION, ...]}` biçimindedir.
Aile adları: `release`, `build_deploy`, `bench_site`, `jobs_diagnostics`, `backups`, `infrastructure`, `access`, `app_dev`.

OPERATION alanlarının hepsi bulunur; uygulanamayan alan `null` veya `[]` olur:

```json
{
  "id": "build.start",
  "family": "build_deploy",
  "title": "Türkçe kısa ad",
  "kind": "read | mutation | analysis | human | external",
  "status": "implemented | read_only | planned | unsupported | not_applicable | unknown",
  "status_reason": "Statünün gerekçesi",
  "authority": ["team | operator | infrastructure_owner | dns_owner | account_holder | app_developer"],
  "owner_handoff": null,
  "guide_steps": ["schedule"],
  "ui": [{"surface": "desk | dashboard", "path": "Deploy Candidate → Build → Complete", "sitemap_node_ids": []}],
  "doctypes": [{"doctype": "Deploy Candidate", "fields": ["status"],
                "child_tables": [{"field": "apps", "doctype": "Deploy Candidate App", "fields": ["app", "source", "release", "hash"]}]}],
  "api": [
    {"principal": "operator", "transport": "doc_method", "doctype": "Deploy Candidate", "method": "build",
     "args": {"no_push": "bool=false", "no_build": "bool=false", "no_cache": "bool=false"},
     "returns": "{error, message: <Deploy Candidate Build adı>}",
     "permission": "@frappe.whitelist(); Desk doc izni",
     "source": {"source_id": "frappe_press", "path": "press/press/doctype/deploy_candidate/deploy_candidate.py", "lines": [225, 241]}},
    {"principal": "team", "transport": "unavailable", "reason": "Gerekçe", "source": null}
  ],
  "params": null,
  "preconditions": [{"id": "deploy_candidate.apps_released", "description": "Açıklama", "machine": true}],
  "side_effects": ["Açıklama"],
  "async": {"returns": "Deploy Candidate Build adı", "track": "track.build",
            "terminal_success": ["Success"], "terminal_failure": ["Failure"],
            "intermediate": ["Draft", "Scheduled", "Pending", "Preparing", "Running"]},
  "success": "Gerçek başarı koşulu (HTTP 200 veya kuyruğa alınma başarı değildir)",
  "failure": {"modes": [{"signal": "...", "meaning": "...", "next": "..."}],
              "timeout": "Sonuç unknown; körlemesine tekrar yok", "retry": "...", "rollback": "..."},
  "risk": "read | write | destructive",
  "approval": "none | single | double | human_only",
  "mcp": {"tools": ["press_propose", "press_execute", "press_track"]},
  "skill": "press-operations",
  "agent": "press-operator",
  "verification": {"source": "verified | partial | unverified", "fixture": "required | not_applicable", "live": "not_run"},
  "notes": []
}
```

- `transport`: `method` (`/api/method/<method>`), `doc_method` (`run_doc_method`), `get_doc` (`frappe.client.get` veya
  team için `press.api.client.get`), `get_list` (`frappe.client.get_list`, açık alan listesiyle), `https` (Press dışı,
  TLS doğrulamalı GET; yalnız Press'in bu principal için doğruladığı siteye), `local` (ağsız analiz veya yerel dosya),
  `human` (insan arayüzü/komutu), `unavailable`.
- Operator okumaları tam belge (`frappe.client.get`) kullanmaz: Deploy Candidate `user_private_key`/`build_token`,
  Agent Job `request_data`/`request_files`/`data`, Press Settings token alanları düz metin döner. Runtime yalnız açık
  alan listeli `frappe.client.get_list` (alt tablolar `parent` ile) kullanır; kontrattaki `api[].transport` buna göre
  `get_list` yazılır.
- `source.source_id` yalnız `contracts/sources.json` kimliklerinden; `lines` gerçek satır aralığı `[ilk, son]`.
- `owner_handoff`: `{"role": "...", "person": "Hüseyin Cengiz | Asistan Hüseyin | null", "steps": ["..."], "acceptance": "..."}`.
- `params`: MCP'ye açılan girdinin JSON Schema'sı; `implemented` işlemlerde zorunlu ve `additionalProperties: false`, diğerlerinde `null`.
- `implemented` statüsünü yalnız aşağıdaki uygulanan küme taşır; runtime'daki kod izin listesiyle test edilir. Kontrat düzenlemesi
  tek başına yeni bir çağrıyı yürütülebilir yapmaz.

### Sabit operasyon kimlikleri

Kimlikler yeniden adlandırılmaz; ek işlem yalnız kılavuz ve kaynak kanıtıyla eklenir.

- `press/release.json`: `release_group.list`, `release_group.get`, `release_group.create`, `release_group.add_server`,
  `release_group.add_app`, `release_group.dependencies`, `app.get`, `app.create`, `app_source.get`, `app_source.create`,
  `app_source.branches`, `app_release.create`, `app_release.get`
- `press/build-deploy.json`: `deploy_candidate.create`, `deploy_candidate.list`, `deploy_candidate.get`, `deploy_candidate.duplicate`,
  `build.start`, `build.get`, `build.triage`, `build_and_deploy.schedule`, `deploy.start`, `deploy.status`
- `press/bench-site.json`: `bench.list`, `bench.get`, `site.create_options`, `site.create`, `site.get`, `site.https_check`,
  `site.setup_wizard`, `site.install_app`, `site.migrate`, `site.update`, `site.jobs`
- `press/jobs-diagnostics.json`: `agent_job.list`, `agent_job.get`, `error_log.list`, `server.ping_agent`, `server.agent_version`,
  `press.version`, `site.usage`, `logs.read`
- `press/backups.json`: `site.backups`, `site.backup`, `site.restore_preflight`, `site.restore`
- `press/infrastructure.json`: `server.list`, `server.get`, `server.disk_check`, `server.build_cache_cleanup`,
  `server.restart_services`, `registry.repository_check`, `dns.record`, `cluster.catalog_label`, `press.code_fix`
- `press/access.json`: `team.context`, `team.roles`, `press_settings.flags`, `payment.method`, `site.legal_acceptance`
- `frappe-app-operations.json` (`app_dev`): `app.scaffold`, `doctype.create`, `child_table.create`, `doctype.permissions`,
  `hooks.doc_event`, `hooks.extend_class`, `patch.create`, `fixtures.filter`, `assets.include`, `localization.translations`,
  `tests.scaffold`, `app.inspect`, `app.check`, `app.install_local`, `app.migrate_local`, `app.run_tests_local`,
  `app_file.write`

### Uygulanan küme

Press mutasyonları (öneri → insan onayı → yürütme → izleme):

| İşlem | Principal | Çağrı |
| --- | --- | --- |
| `release_group.create` | team | `press.api.bench.new {bench}`; `press.api.bench.options` yalnız çerçeve kaynaklarını listeler (`only_frappe=True`), bu yüzden ön koşul yalnız çerçeve app/source çiftini doğrular; diğer uygulamalar oluşturmadan sonra `release_group.add_app` ile eklenir |
| `release_group.add_app` | team, operator | `press.api.bench.add_app {name, source, app}` |
| `app_release.create` | team, operator | `press.api.bench.fetch_latest_app_update {name, app}` |
| `deploy_candidate.create` | operator | `run_doc_method` `Release Group.create_deploy_candidate` (argümansız: tüm uygulamalar en güncel release ile; kılavuz yolu). Dashboard'daki `press.api.bench.create_deploy_candidate` `apps_to_ignore`'u `apps_to_update` olarak geçirir (boş liste güncelleme seçmez); team yolu bu nedenle uygulanmaz |
| `build.start` | operator | `run_doc_method` `Deploy Candidate.build` (yalnız build) |
| `deploy.start` | operator | `run_doc_method` `Deploy Candidate Build.deploy`; Press bu metotta Success denetlemez, ön koşul bizde zorlanır |
| `site.backup` | team, operator | `press.api.site.backup {name, with_files}` |
| `site.migrate` | team, operator | `press.api.site.migrate {name, skip_failing_patches}` |
| `site.install_app` | team, operator | `press.api.site.install_app {name, app, plan: None}`; plan seçilmez (ücretli Marketplace aboneliği hesap sahibinin kararıdır). Uygulama zaten kuruluysa Press iş açmadan döner; izleme bunu `no_op` olarak raporlar |

`press.api.site.backup`, `migrate` ve `install_app` iş adını döndürmez; izleme, öneri yürütme zamanından sonra açılan
`Backup Site` / `Migrate Site` / `Install App on Site` işini site iş listesinden bulur. `press.api.site.jobs` `Undelivered`
durumunu `Pending` olarak gösterir.

Uygulanan işlemlerin `params` şeması runtime kodundadır (`python3 packages/press-ai/server.py schemas` basar); kontrattaki
`params` alanı bununla birebir aynı olmalıdır (test denetler).

Press okuma/analiz (`press_read`, `press_triage_build`, `press_track`): `team.context`, `release_group.list`, `release_group.get`,
`release_group.dependencies`, `app_source.branches`, `deploy_candidate.list`, `deploy_candidate.get`, `build.get`, `build.triage`,
`deploy.status`, `bench.list`, `site.create_options`, `site.get`, `site.jobs`, `site.https_check`, `agent_job.list`, `agent_job.get`,
`error_log.list` (operator), `press.version` (operator), `site.backups`, `server.list`, `server.get`, `press_settings.flags` (operator).

Bilinçli olarak uygulanmayan: `build_and_deploy.schedule` (build ile deploy'u birleştirir; kılavuz ayrımını bozar),
`site.create`, `site.legal_acceptance`, `payment.method` (hesap sahibi), `site.restore` (yıkıcı), SSH/registry/DNS işleri (devir),
`release_group.add_server` (sunucu hazırlığı altyapı sahibinde).

App geliştirme (yerel workspace): `app.inspect`, `app.check`, `app.scaffold`, `doctype.create`, `child_table.create`,
`hooks.doc_event`, `hooks.extend_class`, `patch.create`, `fixtures.filter`, `tests.scaffold`, `app_file.write` uygulanır.
Yerel bench komutları (`app.install_local`, `app.migrate_local`, `app.run_tests_local`) MCP tarafından çalıştırılmaz; komut
metni insana verilir.

- İskelet türleri boş gövde üretir (`pass`, boş `execute()`, yalnız `super()`); iş mantığı değildir.
- `app_file.write` (`change.kind = write_file`): geliştiricinin yazdığı gerçek kod/metin için tek dosya oluşturma veya
  güncelleme. Uygulamaya göre göreli `path`, tam `content`, `purpose`, `expected_sha256`: var olan dosyada ZORUNLU ve
  `app_inspect {files}` ile içerikle aynı okumadan alınır; `null` yeni dosya bekler. Yalnız kaynak/metin uzantıları, içerik
  en fazla 200 KiB (öneri kaydında içerik bir kez saklanır, kayıt sınırı 1 MiB). Kod çalıştırılmaz ve import edilmez:
  Python `ast.parse`, JSON `json.loads` ile ayrıştırılır. Sunucu Python'u uygulamanın `requires-python` alt sınırına
  yetişiyorsa ayrıştırma o sürümün dilbilgisiyle yapılır (`feature_version`) ve sözdizimi hatası kesindir. Yetişmiyorsa
  (ör. 3.9 sunucu, 3.10+ hedef) dosya `UNCHECKED` olur: yalnız en iyi çaba metin taraması koşar ve öneri `UNCHECKED <yol>`
  onay ifadeli çift onay ister. Biçimlenmiş SQL (SEC002) ve guest uç noktasında `ignore_permissions` (SEC003 error)
  içeren Python önerisi (ağaçtan ya da metin taramasından) reddedilir; metin taraması SEC003'ü temkinli uygular (dosyada
  `allow_guest=True` ile `ignore_permissions=True` birlikte). Özel koddaki resmi modül monkey patch'i (EXT001) engellenmez
  ve core akışına girmez; `app_check` ve önizleme onu uyarı (`warning`) olarak gösterir. İçerik, mevcut dosyada bulunmayan `[REDACTED]` içeriyorsa reddedilir (maskelenmiş bir okumanın
  geri yazılmasını önler). Özel geliştirme yetkilidir: DocType JSON'unda `permissions` değişikliği, izinli yeni DocType
  JSON'u ve izin/rol fixture'ı engellenmez; önizleme notu rolleri önce/sonra listeler ve Guest/All rollerini açıklar.
  Davranış, geliştirici testleri koşup gerçek çıktıyı gösterene kadar doğrulanmamış sayılır.
- Bütün app mutasyonlarında kod düzeyinde mutlak sınır: gizli bileşenli yol (`.git`, `.env`, `.github`), `sites`/`env`/
  `logs`/`node_modules`, secret/config/veritabanı/ikili dosya adı yazılmaz ve `app_inspect {files}` ile de okunmaz;
  workspace dışına ve sembolik bağdan geçen yol reddedilir. Ad karşılaştırmaları harften bağımsızdır ve var olan her yol
  bileşeni diskteki adla birebir yazılmalıdır (harf duyarsız APFS'de `Erpnext/` ya da `DocType/` ile atlatma yok).
- Orijinal core dosyaları varsayılan olarak reddedilir ama mutlak yasak değildir. Core dosyası: resmi uygulama
  deposu/paketi (adı resmi modül listesinde — `press` dahil — ve `hooks.py` taşıyan dizin) içindeki her dosya. Özel uygulama
  dosyaları bu kurala girmez. İlk istek öneri oluşturmaz: `app_propose_change` `{state: core_warning, proposal_id: null,
  core: {apps, files}, warning, warning_expires_at, preview}` döner ve istek özetine bağlı tek kullanımlık uyarı kaydı yazar.
  Ajan uyarıyı kullanıcıya gösterir; kullanıcı aynı değişikliği açıkça yeniden isterse aynı argümanlarla ikinci çağrı
  (uyarı süresi içinde, dosya tabanları değişmeden) öneriyi oluşturur. Bu öneri çift onaylıdır: `APPROVE <digest12>` ve
  `CORE <uygulama>` (ayrıştırılamıyorsa `CORE UNCHECKED <uygulama>`); onay ekranı diff'ten önce core uygulamalarını,
  dosyaları ve riski gösterir. Uyarı onay değildir; model bayrağı yoktur. `app_apply` core
  yolunu yalnız CORE onaylı öneride ve öneride listelenmişse yazar, değilse `core_not_approved`. Resmi uygulama kodu
  okunabilir (genişletilecek kodun görülmesi için).
- Çok dosyalı yazım hep ya da hiç: geri alma da başarısız olursa sonuç `failed_partial` olur ve geri alınamayan yollar
  raporlanır.

### Makine ön koşulları ve izleme probları

`preconditions[].id` (`machine: true`): `principal.team`, `principal.operator`, `release_group.owned_by_team`,
`release_group.no_deploy_in_progress`, `release_group.app_absent`, `release_group.app_present`, `release_group.title_available`,
`release_group.auto_deploy_off` (app_release.create: bu App Source'u kullanan hiçbir Release Group App satırında
`enable_auto_deploy` açık olmamalı ve deploy işareti yapılandırılmışsa takımın `auto-deploy` etiketli grubu bulunmamalı;
aksi halde yeni release build+deploy'u birlikte tetikler; team principal bunu okuyamaz → doğrulanamaz → öneri engellenir),
`team.resolved_matches_config` (team mutasyonları: `press.api.account.current_team`'in çözdüğü takım yapılandırılan
`X-Press-Team` ile aynı olmalı; Press üyelik yoksa sessizce varsayılan takıma düşer, `press/utils/__init__.py:143-146`;
operator'da System User başlığı korur), `deploy.artifact_matches_build` (deploy.start: Press imajı çağrılan build'den değil
candidate'in sunucu platformuna göre `intel_build`/`arm_build` alanından alır, `deploy.py:45-49`; her sunucu için bu alan
onaylanan build olmalı ve imaj dolu olmalı; artifact önizlemede sabitlenir, yürütmede farklıysa öneri engellenir),
`app_source.matches_app`, `deploy_candidate.belongs_to_group`,
`deploy_candidate.apps_released`, `deploy_candidate.no_active_build`, `build.success_all_steps`, `deploy.not_created_for_candidate`,
`site.owned_by_team`, `site.active`, `site.no_running_jobs`, `site.recent_backup`, `site.app_available`, `proposal.no_unknown_outcome`.
Diğer ön koşullar `machine: false` ile açıklama olarak yazılır.

`async.track`: `track.release_group`, `track.app_release`, `track.candidate`, `track.build`, `track.deploy`, `track.site_job`,
`track.site_backup`, `track.agent_job`.

## Diğer kontrat dosyaları

- `contracts/sources.json`: `{"sources": [{"id", "repo" | "path", "commit" | null, "ref", "date", "license", "use"}]}`; en az
  `frappe_press`, `pressguide`, `press_sitemap`, `frappe_skills`, `frappe_mcp`, `huf`, `press_mcp_local` (dosya sha256), varsa
  `frappe_v15`, `frappe_v16`.
- `contracts/guide-map.json`: `{"guide": {"source_id": "pressguide", "path": "src/data/guide.json", "steps_total": 67},
  "steps": [{"id", "guide_status": "live | historical", "role": "operation | verification | diagnosis | handoff | narrative",
  "operations": ["..."], "note": "..."}]}`; 67 adımın hepsi kılavuz sırasıyla. Adım kapsam statüsü saklanmaz, runtime işlemlerden türetir.
- `contracts/frappe-extension-points.json`: `{"versions": {"v15": {"source_id", "ref": "version-15", "commit"}, "v16": {...}},
  "decision_order": ["fixtures_custom_field_property_setter", "doc_events", "extend_doctype_class", "override_doctype_class",
  "override_whitelisted_methods", "core_patch_forbidden"], "extension_points": [{"id": "hooks.doc_events",
  "kind": "hook | fixture | patch | config", "v15": "supported | absent | unknown", "v16": "supported | absent | unknown",
  "use_for": "...", "risks": "...", "source": {"source_id", "path", "lines"}}], "rules": [{"id", "severity": "error | warning",
  "description", "source"}]}`. Doğrulanamayan sürüm iddiası `unknown` olur.

## MCP araçları

Sunucu adı `press-ai`; Claude Code araç öneki `mcp__press-ai__`.

| Araç | Girdi | Sonuç |
| --- | --- | --- |
| `kit_status` | `{}` | principal, takım, base host, mutasyon/yazma izinleri, onay yalıtım modu ve sınırı; secret yok |
| `contract_search` | `{query, family?, status?, limit?}` | kontrat ve kılavuz adımı araması |
| `contract_get` | `{id}` | tek operasyonun tam kontratı |
| `ui_reference_search` | `{query, limit?}` | yapılandırılmışsa pressguide sitemap düğümleri; işlev kanıtı değildir |
| `press_read` | `{operation, params}` | yalnız read/analiz kontratları; Press çıktısı `{untrusted_data, data_notice}` zarfında (desenli maskeleme) |
| `press_triage_build` | `{build}` veya `{candidate}` | ilk Failure adımı, kılavuz sınıfı, sonraki adım, sahip |
| `press_propose` | `{operation, params}` | mutasyon önizlemesi; canlı ön koşul; yazmaz; insan onay komutunu döner; `preview` güvenilmeyen veri zarfında |
| `proposal_get` | `{proposal_id, detail?}` | `pending / approved / rejected / expired / consumed`; `detail: true` ile params, tam istek, önizleme, tam özet ve app önerilerinde yazılacak içeriğin güncel dosyaya karşı diff'i (onay ekranıyla aynı yol; güvenilmeyen veri zarfında) |
| `press_execute` | `{proposal_id}` | insan onaylı, süresi dolmamış, tek kullanımlık öneri; aynı (işlem, hedef) kilidi altında ön koşulu yeniden okur; sonuç `accepted`, başarı değil; Press `response` zarfta |
| `press_track` | `{proposal_id}` | `in_progress / succeeded / failed / no_op / unknown` ve kanıt (`evidence` zarfta); zaman aşımı ve gönderilmemiş tüketim `unknown` |
| `app_inspect` | `{app_path, files?}` | workspace içi uygulama yapısı; `files` (en fazla 20, uygulamaya göre göreli) her dosyanın içeriğini ve sha256'sını aynı okumada döndürür (güvenilmeyen veri zarfında) |
| `app_check` | `{app_path, target_frappe?}` | statik kurallar; hedef sürüm yoksa sürüme bağlı kurallar `unknown` |
| `app_propose_change` | `{app_path, change}` | dosya planı, diff, sha256; yazmaz |
| `app_apply` | `{proposal_id}` | insan onaylı öneriyi workspace'e atomik yazar; taban hash değiştiyse reddeder |

Onay aracı yoktur. `confirm`, `approved`, `force` gibi alanlar hiçbir şemada yoktur ve reddedilir. İnsan onayı ayrı terminalde
`python3 -I packages/press-ai/server.py approve <proposal_id> --config <yol>` ile verilir (TTY zorunlu; `APPROVE <digest12>`,
çift onayda ayrıca `<FİİL> <hedef>`). Onay ekranı yazılacak içeriği önerideki istekten üretir ve denetim/bidi karakterlerini
kaçışlar. Onay sunucuyla aynı OS hesabıyla yazılır: bu bir hız kesicidir, OS veya kriptografik sınır değildir. Ayrı onaylayıcı
hesabı desteklenmez (`approval.approver_uid` reddedilir). Onay süresi önerinin süresini aşamaz. Yürütme aynı (işlem, hedef)
için `flock` ile kilitlidir (süreç ölünce işletim sistemi bırakır; dosya silinerek ya da PID'e bakılarak kilit bozulmaz) ve
istekten önce `unknown/dispatching` sonucu yazılır; tüketilmiş ama sonucu olmayan öneri `unknown` sayılır. Workspace
içeriği (`app_inspect {files}`, `proposal_get` ayrıntısı) desen maskelemesi olmadan birebir döner; yalnız yapılandırılmış
kimlik değerleri maskelenir ve gizli değer gibi görünen metin `contains_secret_like_text` ile işaretlenir.

`app_propose_change.change.kind`: `new_app {app_name, app_title, publisher, email, description, license, target_frappe}`
(lisans zorunlu, varsayılan yok), `new_doctype {module, doctype, fields[], istable?, naming_rule?, permissions[]}`,
`add_child_table {module, parent_doctype, child_doctype, table_fieldname, label, fields[]}`,
`add_patch {patch_name, description, section: pre_model_sync | post_model_sync, folder?}`, `add_fixture_filter {doctype, filters}`,
`add_doc_event {doctype, event, handler}`, `extend_doctype_class {doctype, base_class, mode: extend | override, target_frappe}`,
`add_test {doctype, target_frappe}`, `write_file {path, content, purpose, expected_sha256}` (`expected_sha256` var olan
dosyada zorunlu, yeni dosyada `null`).

CLI: `python3 packages/press-ai/server.py serve | approve | reject | proposals | check-contract | call --config <yol>`.
`check-contract` kontratı doğrular ve kapsam özetini JSON olarak basar.

## Skills ve agents

- Skills (ad sabit): `press-operations`, `press-build-triage`, `frappe-custom-app`, `frappe-app-extension`;
  `skills/<ad>/SKILL.md` (frontmatter `name`, `description`) ve yalnız gerekli `references/*.md`.
- Agents (ad sabit), `agents/<ad>.md`, Claude Code biçimi (`name`, `description`, `tools`):
  `press-diagnoser` (yalnız okuma ve teşhis), `press-operator` (öneri, yürütme, izleme; asla onay vermez),
  `frappe-app-developer` (workspace'te geliştirme; değişiklik yalnız öneri → onay → apply), `frappe-change-reviewer`
  (bağımsız, salt okunur; yazarla aynı olamaz).
- Metin Türkçe, teknik kimlikler İngilizce. Kontrat kimliklerine backtick ile atıf yapılır; var olmayan kimlik veya araç yazılmaz
  (testler denetler).
