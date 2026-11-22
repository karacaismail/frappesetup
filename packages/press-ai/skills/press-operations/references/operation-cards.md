# İşlem kartları

Uygulanan mutasyonlar için karar kartları. Ön koşul listeleri kontrattaki makine ön koşullarıdır (`machine: true`);
yürütmeden önce `contract_get` ile güncel hali okunur. Her kartta canlı Press doğrulaması `not_run`dır. Tüm kartlarda
`proposal.no_unknown_outcome` geçerlidir: aynı işlem ve hedef için sonucu `unknown` olan öneri (zaman aşımı, kesilen yürütme
ya da sonucu yazılmamış tüketilmiş öneri) insan onay CLI'sindeki `resolve` komutuyla kapatılana kadar yeni öneri açılmaz.

## `release_group.create`

- Çağrı: `press.api.bench.new` (team). Yeni Bench Group açar.
- Ön koşul: `principal.team`, `release_group.title_available`, `app_source.matches_app`, `proposal.no_unknown_outcome`.
  Press'in çözdüğü takım yapılandırılan takımla aynı olmalıdır (Press üye olunmayan takım başlığında sessizce varsayılan
  takıma geçer; araç çözülen takımı doğrular).
- Başarı: grup kaydı oluştu, Team ve Version doğru. Bu bench ya da site değildir.
- Hata: doğrulama mesajı (sürüm, sunucu, uygulama) olduğu gibi raporlanır.
- Zaman aşımı: `unknown`; `release_group.list` ile oku, yeni öneri açma.
- Geri alma: bu pakette silme veya arşivleme yok. Boş grup zararsızdır; arşivleme insan kararıdır.

## `release_group.add_app`

- Çağrı: `press.api.bench.add_app {name, source, app}`. `team` rolüyle yalnız public (marketplace) kaynaklar
  doğrulanabilir; private kaynak için `operator` gerekir.
- Ön koşul: `release_group.owned_by_team`, `release_group.app_absent`, `app_source.matches_app`,
  `release_group.no_deploy_in_progress`, `proposal.no_unknown_outcome`. Süren deploy; deploy_information bayrakları, doğrudan okunan Pending ya da Installing bench ve (operator rolüyle) Queued New Bench Queue kaydı birlikte; `team` rolü kuyruğu okuyamaz okunarak
  belirlenir (Press'in kendi bayrağı bench kurulumunu görmez).
- Önce: App adı repo paket adı ve hooks.py app_name ile aynı mı; Source'un repo, branch ve Versions alanları grubun sürümüne
  uyuyor mu; bağımlılıkları grupta önce mi.
- Başarı: Apps tablosunda satır ve doğru Source (`release_group.get`). Build başarısı değildir.
- Hata: Source yoksa yeni App Source insan tarafından açılır (`app_source.create` statüsü kontrattan); App yoksa aynı şekilde
  (`app.create`).
- Geri alma: app kaldırma bu pakette yok; insan Dashboard'dan kaldırır. Çalışan bench etkilenmez, sonraki candidate'tan düşer.

## `app_release.create`

- Çağrı: `press.api.bench.fetch_latest_app_update {name, app}` (team, operator). Source'un son commit'ini release yapar.
- Ön koşul: `release_group.owned_by_team`, `release_group.app_present`, `release_group.auto_deploy_off`,
  `proposal.no_unknown_outcome`.
- Otomatik deploy engeli: yeni App Release, aynı App Source'u `enable_auto_deploy` açık kullanan her grupta build ile
  deploy'u birlikte planlar; böyle grup varsa öneri açılmaz. Press Settings'te deploy işareti tanımlıysa dağıtılacak grubu
  commit mesajı belirler; ön koşul doğrulanamaz ve öneri engellenir (etiket sorgusu yapılmaz). Kanıt okunamıyorsa (ör. `team`
  rolü) sonuç doğrulanamaz: öneri yok, karar insanda.
- Başarı: yeni App Release ve hash görünür; candidate'a girdiği `deploy_candidate.get` ile ayrıca okunur.
- `no_op` ayrımı: aynı (app, source, hash) release varsa yenisi oluşmaz. Press release oluşturma hatasını yutar; izleme
  `no_op` demeden önce kaynağın son GitHub yoklamasının başarısız olup olmadığına bakar. Ayrım yapılamıyorsa `unknown`.
- Geri alma: gerekmez; release kurulmaz.

## `deploy_candidate.create`

- Çağrı: Desk yolu `Release Group.create_deploy_candidate`, argümansız (operator): tüm uygulamaları en güncel release ile alır.
  Dashboard'daki karşılığı boş listeyle hiçbir güncellemeyi seçmediği için kullanılmaz.
- Ön koşul: `principal.operator`, `release_group.owned_by_team`, `release_group.no_deploy_in_progress`,
  `proposal.no_unknown_outcome`.
- Başarı: candidate gruba bağlı; Apps & Deps satırlarında Source, Release, Hash dolu (`deploy_candidate.get`). Uyum, release
  commit'lerindeki pyproject.toml ve hooks.py ile grup runtime'ı karşılaştırılarak okunur.
- Hata: "önceki build'de düşen app hâlâ aynı release'te" reddi → app düzeltmesi, `app_release.create`, sonra yeni candidate.
  Çözülmemiş Press bildirimi yeni build'i engelliyorsa insan bildirimi okur ve giderir.
- Geri alma: kullanılmayan candidate zararsızdır; silinmez. Create Duplicate Deploy Candidate (`deploy_candidate.duplicate`)
  ayrı iştir.

## `build.start`

- Çağrı: `run_doc_method` `Deploy Candidate.build` (operator). Yalnız build; deploy başlatmaz.
- Ön koşul: `principal.operator`, `release_group.owned_by_team`, `deploy_candidate.apps_released`,
  `deploy_candidate.no_active_build`, `proposal.no_unknown_outcome`.
- İzleme: Draft, Scheduled, Pending, Preparing, Running ara durumdur; terminal Success veya Failure.
- Başarı: Status Success ve son adım Upload Docker Image dahil tüm Build Steps Success.
- Hata: ilk Failure satırı → press-build-triage. Uzun Preparing → kanıtla Hüseyin Cengiz'e devir; yeni build açılmaz.
- Zaman aşımı: `unknown`; ikinci build yok.
- Geri alma: build çalışan bench'leri değiştirmez; geri alınacak durum yoktur.

## `deploy.start`

- Çağrı: `run_doc_method` `Deploy Candidate Build.deploy` (operator). Onay düzeyi çift onaydır.
- Ön koşul: `principal.operator`, `release_group.owned_by_team`, `build.success_all_steps`,
  `deploy.not_created_for_candidate`, `release_group.no_deploy_in_progress`, `proposal.no_unknown_outcome`. Press metodu
  build Success'ini denetlemez, image bulunamazsa hatayı yutar.
- Site etkisi: deploy siteleri doğrudan taşımaz. Ancak Press'in 15 dakikalık zamanlayıcısı, yeni bench'te güncellemesi olan ve
  otomatik güncellemesi kapalı olmayan sitelerde migrate dahil Site Update açar. Önizleme bu kümeyi listeler: Active, Inactive
  ya da Suspended, otomatik güncellemesi kapalı olmayan ve fatal güncelleme hatası olmayan siteler; Broken siteler ayrı
  listelenir. Deploy onayı bu sitelerin kendiliğinden migrate olabileceğini kabul etmektir. 500'den fazla sitede önizleme
  eksik kalır ve öneri engellenir.
- Sabitleme: build, image, sunucu platformu ve güncellenecek site kümesi önizlemede sabitlenir; yürütmede farklıysa yürütme
  engellenir.
- Başarı: Deploy kaydı; grubun her beklenen sunucusunda Deploy Bench, New Bench Queue ve Bench zinciri izlenir: yeni bench
  Installing'den Active'e geçer ve New Bench işi Success (`bench.list`, `agent_job.list`). Bench'in build'i onaylanan
  build'den farklıysa sonuç `failed`. Yalnız var olan bench'lere bakılarak başarı verilmez. HTTP yanıtı başarı değildir.
- Hata: bench Broken ya da New Bench Failure → iş adımları ve kimliklerle Hüseyin Cengiz'e devir.
- Zaman aşımı: `unknown`; ikinci deploy yok (Press tekilleştirmesi güvenilir değil).
- Geri alma: eski bench çalışmaya devam eder. Kendiliğinden güncellenen siteler için geri dönüş yedekten geri yüklemedir
  (insan kararı). Yeni bench'i arşivlemek, siteleri taşımak ya da geri taşımak insan ve altyapı kararıdır; bu paket yapmaz.

## `site.backup`

- Çağrı: `press.api.site.backup {name, with_files}` (team, operator). İş adı dönmez; izleme Backup Site işini site iş
  listesinde bulur.
- Ön koşul: `site.owned_by_team`, `site.active`, `site.no_running_jobs`, `proposal.no_unknown_outcome`.
- Başarı: Site Backup Success; indirme gerekecekse `files_availability` Available. İmzalı indirme adresleri rapora yazılmaz.
- Hata: iş adımları; disk gibi altyapı nedeni → devir.
- Geri alma: yoktur.

## `site.migrate`

- Çağrı: `press.api.site.migrate {name, skip_failing_patches}` (team, operator). Çift onay. İş adı dönmez; Migrate Site işi
  izlenir.
- Ön koşul: `site.owned_by_team`, `site.active`, `site.no_running_jobs`, `site.recent_backup`, `proposal.no_unknown_outcome`.
  `skip_failing_patches` varsayılan kapalı; açmak yalnız insanın açık kararıyladır, atlanan patch veriyi tutarsız bırakabilir.
- Başarı: Migrate Site işi Success ve site Active. Inactive veya Suspended site migrate sonrası etkinleşmez.
- Hata: site Broken olabilir; iş adımlarını oku. Patch hatası uygulama kodu sorunudur (frappe-custom-app).
- Zaman aşımı: `unknown`; ikinci migrate yok.
- Geri alma: yedekten geri yükleme bu pakette yok (`site.restore`); karar site sahibinde, `site.restore_preflight` kanıtıyla.

## `site.install_app`

- Çağrı: `press.api.site.install_app {name, app}` (team, operator). Plan gönderilmez; ücretli Marketplace planı hesap
  sahibine devredilir. İş adı dönmez; Install App on Site işi izlenir.
- Ön koşul: `site.owned_by_team`, `site.active`, `site.no_running_jobs`, `site.app_available`, `site.recent_backup`,
  `proposal.no_unknown_outcome`.
- Başarı: iş Success ve app site listesinde. Uygulama zaten kuruluysa Press iş açmaz; sonuç `no_op`.
- Hata: bağımlı app eksikse önce o kurulur; iş adımları raporlanır.
- Geri alma: kaldırma bu pakette yok ve uygulama verisini siler; insan yedekle karar verir.

## Uygulanmayan işler

| İşlem | Neden | Ne yapılır |
| --- | --- | --- |
| `app.create`, `app_source.create` | Statü kontrattan; kimlik kararı insanda | Alan kontrol listesi: App adı paket adıyla aynı; repo, branch, Versions, Team; Frappe kutusu yalnız framework |
| `release_group.add_server` | Sunucu hazırlığı | Hüseyin Cengiz |
| `build_and_deploy.schedule` | Build ile deploy'u birleştirir | Kullanılmaz |
| `site.create`, `site.legal_acceptance`, `payment.method`, `site.setup_wizard` | Hesap ve site sahibi | Grubun kendi Sites sayfasından insan; kişisel alanları sahibi girer |
| `site.update` | Statü kontrattan | Otomatik güncellemesi açık sitelerde Press deploy sonrası kendiliğinden açar; elle güncelleme insan Dashboard'dan, öncesinde yedek |
| `site.restore` | Yıkıcı | Site sahibi karar verir; `site.restore_preflight` kanıtı |
| SSH, disk, registry, DNS, Press kodu | Bu MCP'nin yetkisi dışında | Paylaşılan [handoffs.md](../../../references/handoffs.md) |
