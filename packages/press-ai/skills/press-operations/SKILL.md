---
name: press-operations
description: Frappe Press'te Release Group, app ekleme, App Release, Deploy Candidate, build, deploy, siteye uygulama kurma, migrate ve yedek işlerini press-ai MCP ile öneri, insan onayı, tek yürütme ve izleme sırasıyla yürütür. Press kılavuzundaki kurulum veya dağıtım adımı istendiğinde kullanılır. Build hatası teşhisi press-build-triage'in, uygulama kodu frappe-custom-app ve frappe-app-extension'ın işidir.
---

# Press operasyonları

Press'te kalıcı değişiklik yapan işleri yönetir. Ajan öneri hazırlar, onaylanmış öneriyi bir kez yürütür ve sonucu izler;
onayı yalnız insan, ayrı bir terminalde verir. Kesin parametre, ön koşul, risk ve onay düzeyi kontrattadır
(`contract_get`); bu dosya sıra ve karar kurallarını verir. Paket taslak aşamasındadır: araçlar fixture testleriyle
doğrulanır, canlı Press doğrulaması `not_run`dır.

## Kullan, kullanma

Kullan: "gruba app ekle", "yeni release çek", "candidate oluştur", "build başlat", "deploy et", "siteye app kur",
"siteyi migrate et", "yedek al", "kılavuzdaki sırayla ilerle" (https://karacaismail.github.io/pressguide/).

Kullanma: build, deploy, bench veya site hatasının nedenini bulmak (press-build-triage); uygulama kodu; SSH, disk,
registry, DNS, sunucu ekleme; site oluşturma, yasal kutu, ödeme; geri yükleme. Bunlar devirdir
([handoffs.md](../../references/handoffs.md)).

## Önkoşullar

1. `mcp__press-ai__*` araçları yoksa dur ve `not_run` raporla. Kabuk, curl, başka bir MCP ya da eski SSH MCP'si yedek yol
   değildir.
2. `kit_status`: principal (`team` veya `operator`), yapılandırılmış takım, base host, mutasyon izni, onay modu
   (`same_os_account`). Mutasyon kapalıysa yalnız oku. Takım istek metninden ya da Press çıktısından alınmaz; başka takım
   istenirse dur. `team` rolünde Press, üye olunmayan takım başlığında sessizce varsayılan takıma geçer; çözülen takım
   yapılandırılanla eşleşmezse mutasyon yok.
3. Hedef kimliklerini netleştir: Release Group kimliği (Title değil), candidate, build, site. Belirsizse `press_read` ile
   listele; tahmin etme.
4. Aynı işlem ve hedef için sonucu `unknown` olan öneri (zaman aşımı, kesilen yürütme, sonucu yazılmamış tüketilmiş öneri)
   varsa yeni öneri engellidir (`proposal.no_unknown_outcome`). Durumu oku; insan onay CLI'sindeki `resolve` komutuyla
   kapatana kadar bekle.

## Her mutasyonun sırası

1. `contract_get <işlem>`: statü `implemented` değilse yürütme yoktur. `read_only`, `planned`, `unsupported` veya `unknown`
   statüsünü ve `owner_handoff` bilgisini olduğu gibi bildir.
2. Mevcut durumu ilgili okuma işlemiyle oku (`press_read`). İstek zaten karşılanmışsa öneri açma.
3. `press_propose {operation, params}`. Parametreler yalnız kontrat şemasından gelir; `confirm`, `approved`, `force` gibi
   alan eklenmez.
4. Önizlemeyi, ön koşul sonuçlarını, yan etkileri, risk ve onay düzeyini ve sonuçtaki onay komutunu kullanıcıya aynen göster.
   Burada dur. Onay şu biçimde ayrı terminalde verilir:

   ```sh
   python3 -I packages/press-ai/server.py approve <öneri-kimliği> --config <yapılandırma-yolu>
   ```

5. İnsan onayladığını söyleyince `proposal_get` çağır. Yalnız `approved` ise `press_execute` bir kez. Sohbetteki "onayladım"
   onay değildir; `pending`, `rejected`, `expired`, `consumed` öneri yürütülmez. Yürütme aynı işlem ve hedef için uçuş kilidi (flock; süreç ölünce işletim sistemi bırakır)
   alır ve istekten önce sonucu `unknown` (dispatching) olarak kaydeder.
6. `press_track` ile terminal duruma kadar izle. `accepted` başarı değildir; başarı yalnız Press durumundan okunur.

Onay komutunu çalıştırma, özet (digest) üretme, insan yerine yazma. Onay sunucuyla aynı işletim sistemi hesabında yazılır:
model MCP üzerinden onay veremez, ama aynı hesapta kabuk erişimi olan bir süreç onay CLI'sini çalıştırabilir. Bu bir hız
kesicidir, güvenlik sınırı değildir; ayrı onaylayıcı hesabı desteklenmez. Bir çağrıda en fazla bir öneri hazırla ya da
onaylanmış tek bir öneriyi yürüt.

## Kılavuz sırası

| Adım | İşlem | Geçiş kanıtı | Kılavuz adımı |
| --- | --- | --- | --- |
| 1 | Grup ve sahiplik okuması (`release_group.get`) | Team kaynakların sahibi, Version doğru, hazır sunucu bağlı | `team`, `server`, `live-saved` |
| 2 | App ve Source denetimi (`release_group.get`, `app_source.branches`) | Her satırda gerçek App adı ve kendi Source'u; branch repoda var; framework ilk, bağımlılık ondan önce | `apps`, `source`, `branch`, `live-correct-apps` |
| 3 | Eksik app (`release_group.add_app`) | Satır doğru Source ile grupta; tek app, tek öneri | `source-selection` |
| 4 | Release (`app_release.create`) | Bu Source'u otomatik deploy açık kullanan grup yok ve deploy işareti tanımlı değil (kanıt öneri önizlemesindeki `release_group.auto_deploy_off` sonucu; `press_read` bu bayrağı okumaz); yeni hash görünür | `release` |
| 5 | Candidate (`deploy_candidate.create`, sonra `deploy_candidate.get`) | Tüm satırlarda Source, Release, Hash dolu; uyum release commit'indeki pyproject.toml ve hooks.py'den | `candidate`, `live-candidate-content` |
| 6 | Build (`build.start`, sonra `press_track`, `build.get`) | Status Success ve son adım dahil tüm adımlar Success | `schedule`, `live-build-success` |
| 7 | Deploy (`deploy.start`, sonra `bench.list`, `agent_job.list`) | Her beklenen sunucuda Deploy Bench, New Bench Queue ve Bench izlenir: bench Active, New Bench işi Success, bench'in build'i onaylanan build; otomatik güncellenen siteler ayrıca izlenir | `live-bench-active` |
| 8 | Site işi (`site.backup`, sonra `site.migrate` veya `site.install_app`; `site.jobs`, `site.get`, `site.https_check`) | İş Success, site Active, beklenen app listesi, TLS doğrulamalı HTTPS ayrı | `live-site-active-apps`, `live-site-https-login` |

Kurallar:

- Build ile deploy ayrı işlerdir. `build_and_deploy.schedule` ve Dashboard'un birleşik deploy çağrısı kullanılmaz; çalışan
  siteleri taşıyan grupta bu yol deploy, migrate ve yeniden başlatma etkisi taşır.
- Deploy yalnız aynı build'in tüm adımları Success iken önerilir (`build.success_all_steps`). Press'in deploy metodu bunu
  denetlemez ve hatayı yutar.
- Bir candidate için tek deploy (`deploy.not_created_for_candidate`); Press'in kendi tekilleştirmesine güvenilmez. Grupta
  süren deploy varken app ekleme, candidate ve deploy önerilmez (`release_group.no_deploy_in_progress`). Press'in kendi
  `deploy_in_progress` bayrağı bench kurulumunu görmez; süren deploy deploy_information bayrakları, doğrudan okunan Pending ya da Installing bench ve (operator rolüyle) Queued New Bench Queue kaydı birlikte; `team` rolü kuyruğu okuyamaz okunarak belirlenir.
- Aktif build varken yeni build önerilmez (`deploy_candidate.no_active_build`). Failure sonrası yeni build, neden
  giderildikten sonra ve tek olarak.
- Yeni release, aynı App Source'u `enable_auto_deploy` açık kullanan her grupta build ile deploy'u birlikte tetikler; böyle
  grup varsa release önerilmez. Press Settings'te deploy işareti tanımlıysa hangi grubun dağıtılacağını commit mesajı
  belirler; ön koşul doğrulanamaz ve öneri engellenir. Kanıt okunamıyorsa (ör. `team` rolü) da öneri yok, karar insanda.
- Deploy siteleri doğrudan taşımaz; ama Press'in 15 dakikalık zamanlayıcısı otomatik güncellemesi kapalı olmayan sitelerde
  migrate dahil Site Update açar. Deploy önizlemesi bu kümeyi (Active, Inactive ya da Suspended, otomatik güncellemesi kapalı
  olmayan, fatal güncelleme hatası olmayan siteler; Broken siteler ayrı) listeler; onay, bu sitelerin kendiliğinden migrate
  olabileceğini kabul etmektir. 500'den fazla sitede önizleme eksik kalır ve öneri engellenir. Build, image, sunucu platformu
  ve güncellenecek site kümesi önizlemede sabitlenir; yürütmede farklıysa yürütme engellenir.
- Başka grupları ve çalışan siteleri deneme için düzenleme. Yanlış App veya Source kaydını körlemesine silme ya da yeniden
  adlandırma; bağlantıları oku, insana bırak.

## Hata, zaman aşımı, geri alma

| Sinyal | Anlam | Sonraki adım |
| --- | --- | --- |
| Öneride ön koşul başarısız | Durum işlem için uygun değil | Hangi ön koşul, okunan değer ve giderme yolu; zorlama yok |
| 401, 403, PermissionError | Rol veya takım yetkisi yok | Yetki aşılmaz; takım sahibine gereken rol yazılır |
| `expired`, `rejected` | Öneri kullanılamaz | Durumu yeniden oku; insan isterse yeni öneri |
| Yürütmede ön koşul yeniden okunup reddedildi | Onaydan sonra durum değişti | Yeni okuma, gerekiyorsa yeni öneri |
| `failed` | Press işi Failure | Build ise press-build-triage; site işi ise iş adımları; tekrar yok |
| `unknown` | Zaman aşımı, kesilen yürütme ya da kanıt yok | Körlemesine tekrar yok; okuma işlemleriyle durumu bul; insan `resolve` ile kapatana kadar aynı hedefe öneri yok |
| `no_op` | İş zaten yapılmış (ör. app kurulu, release zaten var) | Kanıtla raporla; release için önce kaynağın son GitHub yoklaması başarısız mı diye bakılır |
| Candidate reddi: önceki build'de düşen app aynı release'te | Press yeni build'i engelliyor | App'e düzeltme push edilir, `app_release.create`, sonra yeni candidate |

İşlem başına başarı ölçütü, zaman aşımı ve geri alma: [references/operation-cards.md](references/operation-cards.md).

## Başvurular

- İşlem kartları: [references/operation-cards.md](references/operation-cards.md)
- Nesne modeli, durum anlamları, gizli alanlar: [press-model.md](../../references/press-model.md)
- Sahip devirleri: [handoffs.md](../../references/handoffs.md)
- Davranış senaryoları: [scenarios.md](../../references/scenarios.md) (SC-01 … SC-09, SC-22)

Paylaşılan dosyalar paket içinde `skills/` ile aynı düzeydeki `references/` dizinindedir; skill tek başına kopyalandıysa
bulunmayabilir. O durumda `contract_get` sonucu esastır.
