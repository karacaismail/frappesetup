---
title: "AI · Kendi skill, MCP ve ajanlarımız"
nav: "Geliştirme planı"
order: 25
---

Bu plan, [Press yetkinlik matrisindeki](../ai-press-yetkinlik/) boşlukları ve Frappe'de özel uygulama geliştirme ile resmi uygulamaları genişletme ihtiyacını kapatır. Kural: hazır olanı kullan, eksik olanı küçük ve denetlenebilir parçalarla yaz. Mimari kararlar [Rail 5](../rail-5-ai/) ile uyumludur: Claude Agent SDK, `frappe_mcp`, Keycloak/Press kimliği, önizle + onayla, AI Action Log.

## Ne hazır alınır, ne yazılır

| Alan | Hazır kullan | Yaz | Gerekçe |
| --- | --- | --- | --- |
| Frappe uygulama geliştirme bilgisi | `frappe/skills` (`frappe-app-dev`, `deep-app-audit`, `code-style`) | Türkiye ve platform_core ince katmanı | Resmi, derin, bakımlı; lisans dosyası netleşene kadar sürüm sabitle |
| Sözdizimi/hata ansiklopedisi | OpenAEC (seçilmiş skill'ler) | — | Geniş; ama lisans çelişkisi ve doğrulanmamış Press içeriği var |
| Press teşhisi | Press MCP (`enable_mcp`) | Teşhis sırası skill'i | Araçlar hazır, sıra bilgisi yok |
| Press kurulum ve dağıtım | — | **Press komut MCP'si + skill'ler** | Hiçbir depo karşılamıyor |
| Site içi veri araçları | Frappe Assistant Core veya `frappe_mcp` + kendi araçlarımız | `platform_core.ai_tools` | Kullanıcı kimliğiyle, AI Action Log'a yazan araç gerekir |
| Kullanıcıya dönük asistan | Flow (v16) veya Ask ALYF değerlendirilir | Agent servisi (Rail 5) | Keycloak delege token, kiracı kotası, Press kredi ölçümü hiçbirinde yok |

AGPL bileşenleri (Flow, huf, Jarvis, Ask ALYF, Raven) kendi kodumuzla aynı süreçte birleştirilmeden önce lisans uyumu kullanıcıyla netleştirilir; yeni depolara lisans onaysız seçilmez.

## 1. Skill'ler (önce bunlar, en ucuz ve en çok kazanç)

Her skill: `SKILL.md` (tetikleyici açıklama, 150 satırı aşmaz) + `references/` + en az üç değerlendirme vakası. İlk kaynak, `pressguide` içindeki canlı kanıtlı adımlardır.

| Skill | İçerik | Kabul ölçütü |
| --- | --- | --- |
| `press-release-group` | Team seçimi, sunucu bağlama, uygulama sırası, App Source alanları, "Frappe kutusu yalnız framework" | Beş vakada doğru sıra; yanlış sahiplikte durur |
| `press-build-deploy` | Create Deploy Candidate → yalnız Build → Success → ayrı Deploy; `Schedule Build and Deploy` uyarısı; formu tekrar göndermeme | "Build Success olmadan deploy" ihlali sıfır |
| `press-build-triage` | İlk Failure satırı, Pending'i hata saymama, Required app not found, Upload HTTP 500 ve disk %100, boş filtre yorumu | Kılavuzdaki 6 gerçek olayı doğru sınıflar |
| `press-site-create` | Plan, bölge, yasal kutu (yalnız kullanıcı kabul ederse), Active ≠ başarı, HTTPS ve giriş ayrı doğrulama | Yasal kutuyu kendi işaretlemez |
| `frappe-custom-app-v16` | `frappe/skills` kurallarına bağlı yeni app iskeleti, `required_apps`, sürüm dalları, fixtures kuralları | `deep-app-audit` temiz |
| `frappe-extend-official-app` | ERPNext/HRMS gibi resmi uygulamaları genişletme: önce `doc_events` ve Custom Field (kodda), sonra `override_doctype_class` + `super()`, monkey patch yok | Denetim A-serisi kuralları geçer |
| `platform-core-tr` | Access Rule motoru, Türkiye temel çizgisi, KVKK kuralları | Rail 2 gereksinimlerine izlenir |

Not: eval sistemi `frappe-ui/skills/frappe-ui/evals/` yapısından alınır (vaka seti + puanlayıcı betik). Başarısız vaka, skill'i geçerli saymak için gevşetilmez.

## 2. Press komut MCP'si (`press_tr.mcp.handler` genişletmesi)

Mevcut Press MCP salt-teşhis ağırlıklıdır. Komut katmanı **ayrı bir sunucu** olur; kullanıcının kendi Press bearer'ı ile çalışır (G-28), paylaşılan API anahtarı kullanmaz.

| Araç | Sınıf | Güvence |
| --- | --- | --- |
| `list_release_groups`, `get_release_group`, `get_build`, `get_deploy_status` | okuma | Press izinleri |
| `preview_add_app_source`, `preview_add_app_to_group` | önizleme | Değişiklik yazmaz; fark ve tek kullanımlık onay jetonu döner |
| `apply_add_app_source`, `apply_add_app_to_group` | uygulama | Jeton + kullanıcı onayı; idempotent |
| `create_deploy_candidate` | uygulama | Aynı gruptaki açık candidate'ı yeniden kullanır |
| `start_build` | uygulama | **Deploy başlatmaz**; yalnız build |
| `start_deploy` | yüksek risk | Yalnız build Success ve ayrı onay; canlı sitelerin bulunduğu gruplarda ikinci onay |
| `preview_create_site`, `apply_create_site` | yüksek risk | Yasal kutu ve ödeme yalnız insanda; çift gönderimi engeller |

Tasarım ilkeleri:

- **Önizle → onayla → uygula** iki ayrı çağrıdır; onay jetonu kullanıcı, işlem ve parametreye bağlıdır, tek kullanımlıktır.
- **Yan etki sınırları kodla zorlanır**, istemle değil: `start_build` içinde deploy yoktur; `archive`, `drop`, `reboot` araçları bu sunucuda hiç yoktur.
- **Kararsız API** (`press.api.*`) bir ince adaptör katmanında tutulur; sürüm uyumu testle korunur. Press'e eklenebilecek resmi uç noktalar için yukarı akış katkısı değerlendirilir.
- Çıktılar Press MCP'nin maskeleme (`redaction`) kuralıyla geçer; araç sonucu "veri" zarfında sunulur (prompt-injection önlemi).
- Her çağrı AI Action Log'a (kullanıcı, araç, parametre özeti, Agent Job kimliği) yazılır.
- `frappe_mcp` Frappe v16 uyumu P3 başında kurulumla doğrulanır; olmazsa aynı şema `platform_core` içinde Streamable HTTP uç noktasıdır.

## 3. Ajanlar (Claude Agent SDK alt ajanları)

| Ajan | Yetki | Çıktı | Bağımsız kontrol |
| --- | --- | --- | --- |
| `press-diagnoser` | yalnız okuma (Press MCP) | Hata sınıfı + kanıt + önerilen sonraki adım | Çıktı insan onayına sunulur |
| `press-operator` | önizleme ve uygulama (komut MCP) | Önizleme fark kartı | Uygulama yalnız kullanıcı onayıyla |
| `app-builder` | izole bench/worktree içinde kod yazar | Pull request | `app-reviewer` ve CI |
| `app-reviewer` | yalnız okuma; `deep-app-audit` | Bulgu listesi | Yazan ajanla aynı olamaz |

İlkeler: yazan ajan kendi işinin tek onaylayıcısı olmaz; ajan oturumu kullanıcı kimliğiyle çalışır ve yetkisini aşamaz; sistem/sunucu sahibi işleri ajana verilmez.

## 4. Özel uygulama ve resmi uygulama genişletme akışı

1. `frappe-custom-app-v16` ile iskelet; `required_apps` ve sürüm dalı bildirilir.
2. Resmi uygulama (ERPNext vb.) davranışı değişecekse sırayla: Custom Field/Property Setter (kodda), `doc_events`, `override_doctype_class` + `super()`; çekirdek dosya değişmez.
3. `app-reviewer` `deep-app-audit` çalıştırır; bulgu kapanmadan birleştirme yok.
4. Temiz bench kurulumu testi (`A13`) ve v16 dalıyla derleme CI'da koşar.
5. Press'te yeni App Source + Release Group ekleme `press-operator` ile **önizleme** olarak hazırlanır; build ve deploy ayrı onaylanır.

## 5. Aşamalar, sahipler, kabul

| Aşama | Görev | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| A0 | Press'te `enable_mcp` açmanın etkisini incelemek, System User hesabı ve IP allowlist | Hüseyin Cengiz | — | Okuma araçları yalnız izinli ağdan çalışır; mevcut servisler yeniden başlatılmaz |
| A1 | İlk üç skill (`press-release-group`, `press-build-deploy`, `press-build-triage`) + eval | Geliştirme ekibi | pressguide | 3 vaka × 3 skill geçer |
| A2 | `press-diagnoser` (yalnız okuma) | Geliştirme ekibi | A0, A1 | Kılavuzdaki Upload HTTP 500 olayını doğru sınıflar |
| A3 | Komut MCP'si: okuma + önizleme araçları | Geliştirme ekibi | A2 | Önizleme hiçbir şey yazmaz (test) |
| A4 | Uygulama araçları, onay jetonu, AI Action Log | Geliştirme ekibi; güvenlik incelemesi Hüseyin Cengiz | A3 | Jeton olmadan uygulama reddedilir; çift gönderim engellenir |
| A5 | DNS ve alan adı gereksinimi çıktısı | Hüseyin Cengiz hazırlar, Asistan Hüseyin GoDaddy'de uygular, Hüseyin Cengiz doğrular | A3 | Ajan DNS'e dokunmaz; yalnız kayıt gereksinimi üretir |
| A6 | Uygulama geliştirme ajanları (`app-builder`, `app-reviewer`) | Geliştirme ekibi | A1 | Bir örnek özel uygulama denetimden geçer |

Güvenlik testleri (X-14) her aşamanın kapısıdır: prompt-injection içeren bir destek talebi metninin araç çağrısını yönlendirememesi, çift gönderim, yetkisiz kullanıcı, jeton yeniden kullanımı.

## 6. Riskler

- `press.api.*` kararlı sözleşme değildir; adaptör testleri her Press sürümünde koşar.
- Yazma yetkili bir MCP, tek hatada canlı sitelere dokunabilir; bu yüzden `start_deploy` ayrı ve ikinci onaylıdır.
- Lisans: yeni depolar için lisansı kullanıcı onaylamadan seçmeyiz; AGPL bileşenleri aynı süreçte karıştırmayız.
- Bu sayfa depo incelemesine dayanır; hiçbir hazır araç canlı Press'te denenmedi. Her araç, bizim test ortamımızda doğrulanmadan "çalışıyor" sayılmaz.
