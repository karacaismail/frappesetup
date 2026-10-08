---
title: "AI · Skill paketleri"
nav: "Skills"
order: 22
---

Skill, ajana belirli bir işi nasıl yapacağını öğreten `SKILL.md` + `references/` paketidir. Aşağıdaki değerlendirme 8 Ekim 2026'da alınan yüzeysel klonların okunmasına dayanır; hiçbir skill çalıştırılmadı. Olgunluk puanı (1–5) öznel bir okumadır.

## Karşılaştırma

| Depo | Skill | Frappe sürümü | Lisans | Son commit | Puan |
| --- | --- | --- | --- | --- | --- |
| frappe/skills (resmi) | 9 | v15, v16 kısmi (denetim kurallarında) | LICENSE dosyası yok | 30 Eylül 2026 | 4 |
| OpenAEC-Foundation = Impertio-Studio | 61 | v14–v16 | README MIT, `LICENSE.md` metni LGPL v3 | 1 Nisan 2026 | 4 |
| lubusIN/frappe-skills | 14 | v15+/v16+ notları | MIT | 4 Ağustos 2026 | 3 |
| vyogotech/frappe-apps-manager | 90 (üç kopya) | v14–v16 | MIT | 19 Eylül 2026 | 3 |
| sbknext/forge-frappe-skill | 11 çekirdek + külliyat | v13–v16 karışık | MIT | 7 Haziran 2026 | 3 |
| Dkm0315/frappe-agent | 18 | sürüm bilgisi yok | MIT | 17 Temmuz 2026 | 3 |
| 6missedcalls/erpnext-skill | 1 | yalnız v15 | MIT | 27 Şubat 2026 | 2 |
| frappe/frappe-ui | 1 (+ eval) | UI kütüphanesi | MIT | 8 Ekim 2026 | 4 |

- **OpenAEC ve Impertio aynı projedir**: `diff -rq` çıktısı boştur, aynı commit ("bump to v3.2.0"). Birini kullanın. vyogotech ve sbknext bu içeriğin kopyalarını taşır; kopyalar zamanla ayrışır (drift) ve atıf zayıftır.
- **Lisans uyarısı**: OpenAEC/Impertio kendini MIT ilan eder ama lisans metni LGPL v3'tür; resmi `frappe/skills` deposunda ise lisans dosyası yoktur. Bir paketi ürününüze gömmeden önce lisansı sahibine doğrulatın; lisansı siz seçmeyin.
- **Doğrulama**: gerçek eval yalnız `frappe-ui` içindedir (12 ve 24 vakalık setler, puanlayıcı betik). Impertio/OpenAEC yalnız biçim doğrulayıcı (`quick_validate.py`) taşır. Diğerlerinde skill'in davranışını ölçen test bulunamadı.

## Resmi `frappe/skills`: küçük ama derin

- Dokuz skill: `frappe-app-dev` (18 referans: DocType, controller, hooks, API, izinler, arka plan işleri, testler, desk/vue/portal), `frappe-code-review`, `deep-app-audit`, `code-style`, `technical-writing`, `ui-design`, `fix-issue`, `resolve-backport-conflicts`, `draft-security-advisory`.
- `deep-app-audit` 214 dosyadır: 12 güvenlik alanı, kalite kuralları (özelleştirme 37, doğruluk 36, mekanizma 58), tarama/doğrulama/rapor istemleri ve `run_audit.py`. Bulguları ayrı bağlamda doğrulayan (`prompts/verify.md`) bağımsız bir doğrulama adımı içerir; bizim "ajan kendi işini onaylamaz" ilkesiyle uyumludur.
- Beş skill `disable-model-invocation: true` taşır: kullanıcı çağırmadıkça devreye girmez.
- Zayıf: Press, Frappe Cloud, release group ve deploy hiç yoktur; bench/site yönetimi yalnız iki kısa referanstır (`bench-operations.md`, `site-management.md`).

## OpenAEC/Impertio: en geniş kapsam

- 61 skill, yedi katman: sözdizimi 13, çekirdek 11, uygulama 14, hata 7, **ops 9**, ajan 5, test 2. Ops katmanı: `app-lifecycle`, `backup`, `bench`, `cloud`, `deployment`, `frontend-build`, `performance`, `upgrades`, `website-deploy`.
- Frontmatter şablonu iyidir ("Use when… Prevents… Covers… Keywords…") ve her skill `references/examples.md` ile `anti-patterns.md` taşır. SKILL.md dosyaları 320–500 satırdır; biraz şişkindir.
- `frappe-ops-cloud` (325 satır) Frappe Cloud, Press, paylaşımlı/özel bench ve site oluşturmayı **özet düzeyinde** anlatır. "Release group" ve "app source" terimleri geçmez; Press API içeriğinin canlı doğrulama kanıtı yoktur. Bu nedenle Press işlemleri için güvenilir kaynak değil, yalnız bağlam sağlayıcıdır.
- 2026-04'ten beri güncellenmedi; README'deki "~%95 kapsam" iddiası ölçülmemiştir.

## Diğerleri

- **lubusIN**: temiz router + triage yapısı ve `version-compat.md`; ancak ops/deploy yok, taslak yapay zekâ ile yazılmış ve skill düzeyinde doğrulama kanıtı yok.
- **Dkm0315**: 18 ince skill (ör. bench skill'i 30 satır); sürüm ve Press bilgisi yok.
- **6missedcalls**: tek, büyük (`frappe-framework-complete.md`) ve yalnız v15; bağlamı şişirir.
- **frappe-ui**: yalnız arayüz kütüphanesi için; ancak eval altyapısı örnek alınmalıdır.

## Press ve ops konularında kapsam

| Konu | En iyi kaynak | Durum |
| --- | --- | --- |
| Release Group, App Source, Deploy Candidate | — | **yok** |
| Build hatası teşhisi (Build Steps, Agent Job) | — | **yok** |
| Frappe Cloud / Press genel bilgi | `frappe-ops-cloud` (OpenAEC) | kısmi, doğrulanmamış |
| bench, backup, migrate, upgrade | OpenAEC `frappe-ops-*` | var (genel) |
| v16 geçişi | OpenAEC `frappe-ops-upgrades` | var |
| Uygulama kodu denetimi | `frappe/skills` `deep-app-audit` | var, güçlü |

## Nasıl faydalanılır

1. Uygulama geliştirme için **resmi `frappe/skills`** ana kaynak olsun; üzerine OpenAEC'in sözdizimi ve hata katmanlarını **seçerek** ekleyin (61 skill'in hepsi değil; bağlam şişer).
2. Kopya depoları (vyogotech, sbknext) kullanmayın; kaynağa doğrudan bağlanın ve sürüm sabitleyin.
3. Hiçbir ops/Press skill'ine canlı doğrulama olmadan güvenmeyin. Bizim Press kılavuzumuz (`pressguide`) kanıtlı tek kaynaktır; eksik skill bundan türetilmelidir ([geliştirme planı](../ai-gelistirme/)).
