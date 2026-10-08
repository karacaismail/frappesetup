---
title: "AI · Skill paketleri"
nav: "Skills"
order: 22
---

Skill, ajana bir işi nasıl yapacağını öğreten `SKILL.md` ve gerektiğinde okunan başvuru dosyalarıdır. Bu sayfa paketteki dört skill'i ve kurulumunu, ardından hazır skill depolarının kanıtını verir. Hazır depolar 8 Ekim 2026'da yüzeysel klonlardan okundu; hiçbir skill çalıştırılmadı.

## Kararlar

- **Press skill'i yazılır.** Hazır depolarda Release Group, App Source, Deploy Candidate ve build/deploy ayrımını işleyen skill yoktur ("release group" ve "app source" aramasında eşleşme çıkmadı).
- **Kaynak kopyalanmaz.** Skill'ler kılavuzdan ve Press kaynağından türetilir; [kılavuz](https://karacaismail.github.io/pressguide/) metni kopyalanmaz, adım kimliğiyle (`schedule`, `hata-tanisi` gibi) atıf yapılır. Lisans dosyası olmayan `frappe/skills` ve lisansı çelişkili OpenAEC pakete gömülmez; yalnız yol ve commit ile atıf yapılır.
- **Her skill somut sıra taşır:** tetikleyici, ön koşul, adım sırası, izin sınırı, hata, zaman aşımı, geri alma ve devir. Kesin parametre ve ön koşul kontrattadır (`contract_get`).

## Paketteki skill'ler

Yol: `packages/press-ai/skills/<ad>/SKILL.md`; paylaşılan başvurular `packages/press-ai/references/` (Press nesne modeli ve gizli alanlar, sahip devirleri, Frappe uygulama modeli, davranış senaryoları).

| Skill | Tetikleyici | Ön koşul | Yapmadığı |
| --- | --- | --- | --- |
| `press-operations` | Gruba app ekleme, release, candidate, build, deploy, siteye app, migrate, yedek | `kit_status` takımı ve rolü; hedef kimlik; sonucu bilinmeyen öneri yok | Onay vermez; site oluşturma, yasal kutu, ödeme, geri yükleme, SSH |
| `press-build-triage` | Build Failure, takılan build, belirsiz deploy, bench ya da site işi, "No data" | Build ya da candidate kimliği; Error Log için `operator` | Build, deploy, temizlik başlatmaz |
| `frappe-custom-app` | Yeni app, DocType, child table, patch, fixture, iş mantığı, test | Hedef Frappe sürümü; lisansı kullanıcı seçer | Dosyayı doğrudan yazmaz (yalnız onaylı öneri); bench çalıştırmaz; test çıktısı olmadan "geçti" demez |
| `frappe-app-extension` | ERPNext, HRMS gibi resmi uygulamanın davranışını değiştirme | Resmi uygulamanın sabit commit'i; hedef sürüm | Çekirdek dosyaya yalnız core akışıyla (uyarı, açık tekrar, CORE onayı) yazar; fork yok; v15'te `extend_doctype_class` yok |

## İndir

Tekil `SKILL.md` tek dosya içindir; başvurularıyla kurmak için skill ZIP'i ya da tüm paket. ZIP'ler `packages/press-ai/` yerleşimindedir; aşağıdaki komutlar açılan dizinde çalışır.

<div data-embed="dl-skills"></div>

## Kurulum

MCP sunucusu eklentiye gömülü değildir, ayrıca kaydedilir (komut [geliştirme planında](/frappesetup/ai-gelistirme/)); ajanların araç listeleri `mcp__press-ai__` önekini bekler.

Eklenti denetimi ve oturumluk deneme (paketin `.claude-plugin/plugin.json` manifestiyle; `plugin details` 4 skill, 4 ajan ve 0 MCP sunucusu listeler; skill `/press-ai:press-operations`, ajan `press-ai:press-operator` olarak çağrılır):

```sh
claude plugin validate packages/press-ai --strict
claude --plugin-dir packages/press-ai plugin details press-ai
claude --plugin-dir packages/press-ai
```

Kalıcı proje kurulumu; `skills` ve `references` aynı üst dizinde kalır (`references` kopyalanmazsa `contract_get` esastır):

```sh
mkdir -p .claude/skills .claude/agents
cp -R packages/press-ai/skills/. .claude/skills/
cp -R packages/press-ai/references .claude/references
cp packages/press-ai/agents/*.md .claude/agents/
```

Doğrulama durumu: frontmatter, bağlantı ve kimlik denetimleri paket testlerindedir (sonuç son koşudan). Davranış senaryoları `packages/press-ai/references/scenarios.md` içindedir; koşu `not_run`.

## Hazır skill depoları: kanıt

| Depo | Skill | Frappe sürümü | Lisans | Son commit | Davranış değerlendirmesi | Press içeriği |
| --- | --- | --- | --- | --- | --- | --- |
| frappe/skills (resmi) | 9 | v15; v16 denetim kurallarında | LICENSE dosyası yok | 30 Eylül 2026 | yok; denetimde ayrı doğrulama istemi | yok |
| OpenAEC-Foundation = Impertio-Studio | 61 | v14–v16 beyanı | README MIT, `LICENSE.md` metni LGPL v3 | 1 Nisan 2026 | biçim doğrulayıcı | `frappe-ops-cloud` özet; release group ve app source yok |
| lubusIN/frappe-skills | 14 | v15+ ve v16+ notları | MIT | 4 Ağustos 2026 | yok | yok |
| vyogotech/frappe-apps-manager | 90 (üç kopya) | v14–v16 | MIT | 19 Eylül 2026 | elle kontrol listesi | OpenAEC kopyası |
| sbknext/forge-frappe-skill | 11 + külliyat | v13–v16 karışık | MIT | 7 Haziran 2026 | yok | OpenAEC kopyası |
| Dkm0315/frappe-agent | 18 | sürüm bilgisi yok | MIT | 17 Temmuz 2026 | yok | yok |
| 6missedcalls/erpnext-skill | 1 | yalnız v15 | MIT | 27 Şubat 2026 | yok | yok |
| frappe/frappe-ui | 1 | UI kütüphanesi | MIT | 8 Ekim 2026 | var: 12 ve 24 vakalık set, puanlayıcı betik | yok |

## Hazır depo nasıl alınır

- **Kişisel kullanım:** depoyu klonla, commit'i sabitle, skill dizinini `~/.claude/skills/` altına kopyala. Bu depoya gömülmez.
- **`frappe/skills`:** uygulama geliştirme ve `deep-app-audit` kuralları için en derin kaynak; lisans dosyası olmadığı için yeniden dağıtım hakkı belirsizdir.
- **OpenAEC / Impertio:** iki depo içerik olarak aynıdır; lisans çelişkisi sahibine doğrulatılmadan kullanılmaz. Kopyaları (vyogotech, sbknext) yerine kaynağa bağlanılır.
- **frappe-ui:** yalnız arayüz kütüphanesi için; eval yapısı paket senaryolarına örnektir.

## Kalan sınırlar

- Paket skill'leri taslaktır; davranış senaryoları koşulmadı (`not_run`).
- MCP araç adları paketin arayüz dosyasındaki 14 araçtır; gerçek MCP istemci oturumunda eşleşme `not_run`.
- Ajan tanımları Claude Code biçimindedir; başka istemcilerde kullanım doğrulanmadı (`unknown`).
