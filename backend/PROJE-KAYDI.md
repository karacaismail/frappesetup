# Backend proje kaydı

Bu dosya backend'in seviyesini, sürümlerini ve kararlarını tutar. Kod standartlarının Ek A bölümü bu kaydı ister. Kayıt 22 Kasım 2026 Pazar günü açıldı.

## Olgunluk seviyesi

- Seviye MVP'dir. MVP, ilk kullanılabilir sürümdür.
- Bütün modüller aynı seviyededir.
- Gerçek kişi verisi yine kullanılmaz. Bunun nedeni aşağıdaki A-9 maddesidir.

## Sürümler

| Bileşen | Hedef | Durum |
| --- | --- | --- |
| Kiracı sitesi | Frappe 16 ve ERPNext 16 | Yerelde `frappe/erpnext:v16.55.0` imajı var. Çalışan sürümü dev-ortam işi doğrular. |
| Press sitesi | Frappe 16, Press v0.154.1 ve Python 3.14 | Bu Mac'teki deneme kurulumunda bu sürümler çalışıyor. Press bu sürümde yalnız yamalarla açılır (A-11). |
| Keycloak | 26.8 serisi | Son sürümü kimlik-realm işi resmî kaynaktan doğrular. |
| Container | Colima, `colima-factory` profili | Docker Desktop kullanılmaz. |

Sürüm aralığını `pyproject.toml` dosyasından okuyun. Yorum satırını aralık saymayın.

## Uygulamalar ve modüller

| Uygulama | Modül | Görevi |
| --- | --- | --- |
| `platform_core` | `kimlik` | Keycloak ile giriş, çıkış, kimlik bağı ve servis belirteci |
| `platform_core` | `kabuk` | Açılış verisi, kenar çubuğu verisi ve DocType tanımı uçları |
| `platform_core` | `yapay_zeka` | Yapay zekâ erişim katmanı: araç kaydı, MCP ucu, önizleme ve onay, işlem günlüğü |
| `platform_core` | `mobil` | Telefon eşitlemesi: sürümlü mobil uçlar, işlem kimliği, imleç ve kaldırma işareti |
| `platform_core` | `erisim` | Erişim kuralı motoru: kayıt kuralı, hiyerarşi ve alan düzeyi (K8) |
| `platform_core` | `model_gecidi` | Sağlayıcı, hesap, API ve model kaydı. Yönlendirme, model çağrısı ve kullanım kaydı. |
| `press_tr` | `kimlik` | Press'te Keycloak ile giriş, takım açma ve servis uçları |
| `identity_sync` | Yok | Keycloak ile Press ve kiracı siteleri arasında kullanıcı eşitleme |
| `oidc_verify` | Yok | Belirteç doğrulama. Frappe'ye bağlı değildir. |

## Bağımlılık yönü

- `platform_core.kimlik` ve `press_tr.kimlik` yalnız `oidc_verify` kitaplığını kullanır.
- `platform_core.kabuk` ile `platform_core.kimlik` birbirini çağırmaz.
- `platform_core.mobil` yalnız `kimlik` modülünün açık doğrulama işlevini çağırabilir. Öteki modüller `mobil` modülünü çağırmaz.
- `platform_core.erisim` öteki modülleri çağırmaz. Öteki modüller onu içe aktarmaz. Motor Frappe'nin izin kancalarıyla çalışır.
- `platform_core.model_gecidi` öteki modülleri çağırmaz. `yapay_zeka` modülü `model_gecidi` modülünün açık işlevlerini çağırabilir.
- `platform_core.yapay_zeka` öteki modüllerin açık işlevlerini çağırabilir. Öteki modüller `yapay_zeka` modülünü çağırmaz. Uygulamalar araçlarını `ai_tools` kancasıyla bildirir.
- `identity_sync` sitelerin açık uçlarını HTTP ile çağırır. Siteler `identity_sync` kodunu çağırmaz.
- Döngü yasaktır. MVP'de bu yönler otomatik denetlenir (B-10).

## Denetim komutları

Ortam komutları Pane'in verdiği `PANE_PORT` değerini kullanır.

| Denetim | Komut | Klasör |
| --- | --- | --- |
| Frappe kurulum testleri | `backend/dev/bin/test platform_core` | Depo kökü |
| Python kod ve biçim denetimi | `backend/dev/bin/ruff` | Depo kökü |
| Modül sınırları | `backend/dev/bin/modul-sinirlari` | Depo kökü |
| Ortam betiklerinin Python testleri | `python3 -m unittest discover -s backend/dev/tests` | Depo kökü |

## Proje sahibinin kararları

Kararlar 22 Kasım 2026 Pazar günü alındı.

- **D-1. Seviye MVP'dir.** Proje sahibi “MVP, ilk kullanılabilir sürüm” seçeneğini seçti.
- **D-2. Kod frappesetup deposundadır.** Kod `backend/` klasöründe durur. Kodun lisansı deponun kod lisansıdır, yani MIT'dir.
- **D-3. İlk turda Press de vardır.** İlk tur şu işleri kapsar:
  - geliştirme ortamı,
  - Keycloak realm'i ve Atonota markası,
  - `platform_core` içinde giriş, çıkış ve ekran verisi uçları,
  - kullanıcı eşitleme servisi,
  - `press_tr` içinde Keycloak ile giriş.
- **D-4. Kimlik markası Atonota'dır.** Proje sahibi alan adı olarak atonota.net yazdı.
  - Keycloak bu alan adında, platformdan ayrı durur.
  - Düğme metni “Atonota ile oturum aç” olur.
  - Marka adı ve alan adı ayardan gelir. Kodda sabit yazılmaz.
- **D-5. Son kullanıcı yalnız ayrı arayüzü görür.** Son kullanıcının türü “Website User” olur (Karar 10, G-16).
- **D-6. Zamanlanmış iş kurulmaz.** Proje sahibi `cron` kurulumunu istemedi (V-9).
- **D-7. Bütün uygulamalar Frappe 16 ile yazılır.** `press_tr` de Frappe 16 üzerinde çalışır. Proje sahibi bunu şöyle yazdı: “app frappe v16.x ile koldlansın”.
- **D-8. Var olan Press kurulumu kullanılır.** Bu Mac'te Colima'da bir Press deneme kurulumu var. Kurulum değiştirilmez. İmajı ve kurulum betikleri yeniden kullanılır.
- **D-9. Her şey yapay zekâyla yönetilebilir olur.** Bütün DocType'lar, alanlar ve backend işlemleri yapay zekâya açık bir katmandan geçer. Katman model sağlayıcısından bağımsızdır. Proje sahibi şöyle yazdı: “ai heryerde olmalı, ai provider'dan bağımsız, herşey ai ile yönetilebilmeli.” Ayrıntı sözleşmenin 10. bölümündedir.
- **D-10. Kararlar ajana bırakıldı.** Proje sahibi şöyle yazdı: “Herşeyi onaylıyorum ve izin veriyorum, karar ver soru sorma”. Ayrıntı aşağıdaki “Orkestratörün kararları” bölümündedir.
- **D-11. Altyapı yapay zekâ tabanlıdır ve çok sağlayıcılıdır.** Sisteme n tane sağlayıcı eklenebilir. Her sağlayıcıdan n tane hesap eklenebilir. Her hesaptan n tane API eklenebilir. Proje sahibi şöyle yazdı: “birden fazla (n tane) ai provider eklenebilmeli, birden fazla (n tane) her hangi bir provider'dan, ai account eklenebilmeli, n tane api eklenebilmeli.” Ayrıntı sözleşmenin 11. bölümündedir.
- **D-12. Yeni kod İngilizce adlarla yazılır.** Proje sahibi şöyle yazdı: “yeni dosya oluşturursen, türkçe değil, codebase ingilizce olsun, dosya adları ingilizce olsun”. Sonra şunu ekledi: “bundan sonrası için öylemiştim, geçmiş için değil.” Bu kararın uygulanışı şudur:
  - Bundan sonra oluşturulan dosya, klasör, modül, DocType, işlev ve değişken adları İngilizce olur.
  - Yeni yazılan koddaki yorumlar, hata iletileri ve günlük metinleri İngilizce olur.
  - Bu madde Karar 40 ile değişti (proje sahibinin karar dosyası). Eski adlar da kurallara göre düzeltilir. Düzeltmeyi yalnız naming-history-fix işinin ortak betiği yapar (D-14). Öteki işçiler adları elle değiştirmez.
  - Bütün kod adları İngilizce ve yalnız ASCII olur. Değişken, sabit, `class`, `id`, DocType, modül, alan, Select seçeneği, iş akışı durumu, çeviri anahtarı, API alanı ve dosya adı bu kapsamdadır.
  - Görünen metnin kaynağı İngilizcedir. Python'da `frappe._`, JavaScript'te `__()` zorunludur. DocType JSON etiketleri de İngilizce yazılır. Türkçesi çeviri dosyasındadır.
  - Var olan bir klasörün içine yeni dosya eklenince yalnız yeni dosyanın adı İngilizce olur.
  - Kullanıcıya görünen yeni metnin kaynağı İngilizcedir. Türkçesi çeviri dosyasında durur (V-2).
- **D-13. Başka bir projenin ürün adı bu depoda yasaktır.** Proje sahibi bu kararı 22 Kasım 2026 Pazar günü verdi. Ad bu projeyle ilgili değildir. Ad bir ajan tarafından yanlışlıkla belgelere eklenmişti.
  - Ad ve bütün yazım biçimleri hiçbir dosyada geçmez. Klasör adı, commit mesajı, imaj adı ve container adı da buna dahildir.
  - Adın kendisi bu kayda da yazılmaz.
  - İK uygulamasının teknik adı `hrms_tr` olur. Görünen adı “HRMS TR” olur. Ad, `press_tr` adıyla aynı kalıbı izler.
  - Yapay zekâ uygunluk kapısı yasaklı adı SHA-256 özetiyle tanır. Böylece kapının kendisi de adı taşımaz.
  - Eski commit mesajlarında ad geçer. Geçmiş yeniden yazılmadı, çünkü bu on dört dalı bozar. `backend` dalı `main` dalına birleşirken geçmiş tek commit'e indirilebilir.

- **D-14. Geçmiş adlar ad verme kuralları raporuna göre düzeltilir.** Proje sahibi şöyle yazdı: “oluşturunca, onu da paralel ayrı bir pane görevi ile başlatıp, geçmişi düzelttirirsin.” Rapor `/Users/w6x/Documents/rules ai/naming_rules_report.md` dosyasıdır (AV-1..AV-73). İşi `naming-history-fix` yapar. Bu iş bitene kadar öteki işçiler var olan adları kendileri değiştirmez. Değişikliği ortak betik yapar.
  - Uygulama ön ekleri (AV-69) şunlardır: `platform_core` için `PLT`, `press_tr` için `PTR`, `hrms_tr` için `HRT`. Ön ek DocType, rapor, rol, çalışma alanı ve yazdırma biçimi adlarına girer.
  - `press_tr` ve `hrms_tr` adlarındaki `tr`, Türkiye'nin ülke kodudur. Bu anlam terim sözlüğüne yazılır.
  - Keycloak rol adları küçük harfle ve tireyle yazılır. Örnek: `leave-approver`.
  - Commit mesajının türü ve kapsamı İngilizce olabilir. Açıklama yalın Türkçe kalır.

- **D-15. Yalnız Frappe 16.x kullanılır. Kural dosyaları son karardır.** Proje sahibi 22 Kasım 2026 Pazar günü şöyle yazdı: “namin dosyasından frappe 15 ile ilgili talimat gelse bile, tamamen frappe 16.x ile geliştirme yap. frappe 16.x nimetlerinden faydalan.” Ayrıca kural dosyaları için “bunlar son kararım” dedi.
  - Kural dosyalarındaki Frappe 15 uyum notları uygulanmaz. Frappe 16 davranışı esas alınır.
  - Frappe 16'nın hazır özellikleri tercih edilir. Örneğin API v2, `UnitTestCase` ve `IntegrationTestCase`, `extend_doctype_class`, `autoname: UUID` ve `frappe.qb`. Her kullanım Frappe 16.56.0 kaynağında doğrulanır.
  - Kural dosyaları `docs/standartlar/` klasöründedir. Asıl kopya proje sahibinin `rules ai` klasöründedir. İki kopya aynı tutulur.
  - Sihirli bağlantı ve Apple ile giriş MVP'ye girer (karar dosyası, 786. satır). Eklenti lisansı Apache-2.0 ya da MIT olur.

## Orkestratörün seçtiği varsayılanlar

Proje sahibi bu konularda karar vermedi. Orkestratör şu varsayılanları seçti. Proje sahibi bunları değiştirebilir.

- **V-1. Ad dili.** Koddaki adlar İngilizcedir. Frappe ekosistemi bu dili kullanır.
- **V-2. Mesaj dili.** Kaynak metin İngilizce yazılır. Türkçesi çeviri dosyasında durur (G-73).
- **V-3. Modül adları.** Modül adları İngilizcedir (Karar 40). Var olan Türkçe modül adlarını naming-history-fix işi değiştirir.
- **V-4. Ortak kitaplık.** Belirteç doğrulama tek kitaplıkta durur. `platform_core` ve `press_tr` aynı kodu kullanır (H-8).
- **V-5. Container profili.** Geliştirme `colima-factory` profilinde yürür. Bu profilde daha çok bellek var.

## Orkestratörün kararları

Proje sahibi 22 Kasım 2026 Pazar günü şöyle yazdı: “Herşeyi onaylıyorum ve izin veriyorum, karar ver soru sorma”. Bu söz D-10 kararıdır. Orkestratör açık kararları bu yetkiyle kapattı. Proje sahibi her kararı değiştirebilir.

- **O-1. Keycloak'ın sunucu adı `id.atonota.net` olur.** Kök alan adı markanın tanıtım sayfasına kalır. DNS değerini DevOps sorumlusu hazırlar. Kaydı alan adı sorumlusu uygular. Ajan DNS'e dokunmaz. Alan adının kayıt yeri doğrulanmadı.
- **O-2. Platformun alan adı ayardan gelir.** Karar sitesi `<marka>.com.tr` yazar. Marka belli olunca yalnız ayar değişir.
- **O-3. Kiracıda son kullanıcı “Website User” olur.** Bu, Karar 10'dur. Frappe 16 bu yolu engellerse işçi engeli kaynakla raporlar.
- **O-4. Giriş teması Keycloak'ın kendi tema yapısıyla kurulur.** Tema `keycloak.v2` temasından türer. Renkler ve yazılar CSS değişkeniyle verilir. Bu yol yeni teknoloji eklemez (T-1). Keycloakify (G-80), panelin tasarım tokenları hazır olunca yeniden değerlendirilir.
- **O-5. Web realm'i G-78 süreleriyle kurulur.** Mobil iş başlayınca Karar 19 süreleri mobil istemcilere uygulanır.
- **O-6. Sihirli bağlantı ve Apple ile giriş MVP'ye girer.** Bu, Karar 17'dir. Eklentiyi kimlik-realm işi T-2 notuyla seçer. Eklentinin lisansı Apache-2.0 ya da MIT olmalıdır.
- **O-7. Press dağıtımında her uygulama ayrı depoya bölünür.** Bölme `git subtree split` ile dağıtım zamanında yapılır. Geliştirmede `backend/apps/` yapısı kalır.
- **O-8. `press_tr` lisansı AGPL-3.0 olur.** Press AGPL-3.0'dır. `press_tr` Press'i aynı süreçte kullanır. En güvenli seçim budur. Öteki backend kodu MIT kalır. Hukuk görüşü alınmadı.
- **O-9. Press de Frappe 16 üzerinde geliştirilir.** Press bu sürümde yalnız yamalarla açılır. Press'in sunucu kurma akışı Frappe 16'da çalışmadan üretime çıkılmaz. Bu madde teknik borç tablosundadır.
- **O-10. Ajan servisi sağlayıcıdan bağımsızdır.** Model ve sağlayıcı ayardan gelir. Claude desteklenen sağlayıcılardan biridir. K9'daki Claude Agent SDK seçimi bu yüzden zorunlu değildir.
- **O-11. Eşitleme olaylarının kaynağını identity-sync işi seçer.** İşçi T-2 notunda en yalın açık kaynak yolu seçer. Zamanlanmış yoklama yine yasaktır (D-6).
- **O-12. `platform_core` MIT lisanslı kalır.** AGPL lisanslı bir bileşen `platform_core` içine alınmaz. Böyle bir bileşen gerekirse ayrı uygulama ya da ayrı servis olur.

- **O-13. Model geçidi `platform_core` içinde durur.** Modül `model_gecidi` olur. Geçit sağlayıcılara düz HTTP ile bağlanır. Sağlayıcı kitaplığı kullanılmaz. Model adları yalnız kayıtta durur.
- **O-14. Kayıt önce kiracı sitesindedir.** Her kiracı kendi sağlayıcılarını, hesaplarını ve API'lerini ekleyebilir. Platformun ortak hesapları sonraki turda Press'ten site ayarına gelir.
- **O-15. Sağlık denetimi zamanlanmaz.** API'nin sağlığı gerçek çağrıların sonucundan çıkar. Elle başlatılan bağlantı denetimi de vardır (D-6).

## Karar sitesine işlenecek farklar

Backend kararları karar sitesinin bazı maddelerini değiştirdi. Site ayrı bir işte, kendi denetimleriyle güncellenir. Farklar şunlardır:

| Sitedeki madde | Yeni durum | Kaynak |
| --- | --- | --- |
| K1: Press Frappe 15 üzerinde çalışır. | Press de Frappe 16 üzerinde çalışır. | D-7, O-9 |
| K9: Claude Agent SDK ve adı yazılı Claude modelleri | Sağlayıcıdan bağımsız ajan servisi ve model geçidi | D-9, D-11, O-10 |
| G-84: Kiracı MCP'si `frappe_mcp` ile kurulur. | `frappe/mcp` deposu arşivlendi. Katmanı `platform_core.yapay_zeka` kurar. | Karar notu 0002 |
| Rail 5: Onay `confirm=true` alanıyla verilir. | Modelde onay alanı yoktur. Onay insan oturumundaki ayrı uçtan gelir. | Sözleşme 10. bölüm |
| G-64: Günlük model, token ve maliyet tutar. | Bu alanlar “AI Usage Log” kaydındadır. | Karar notu 0002 |
| G-57: Kiracıda kullanıcı “System User” olur. | Son kullanıcı “Website User” olur. | D-5, O-3 |
| G-80: Tema Keycloakify ile yapılır. | Tema Keycloak'ın kendi tema yapısıyla yapılır. | O-4 |
| Rail 4: Saatlik yoklama ve gece mutabakatı | Zamanlanmış iş yok. Mutabakat elle başlar. | D-6, O-11 |

- **O-16. `hrms_tr` lisansı GPL-3.0 olur.** `hrms_tr`, GPL-3.0 lisanslı `hrms` uygulamasını aynı süreçte kullanır. En güvenli seçim budur. Hukuk görüşü alınmadı.
- **O-17. Yapay zekâ katmanı her sitede çalışacak.** Press ve operasyon sitesi de aynı katmanı kullanmalı. Katmanın ayrı bir uygulamaya bölünmesi sonraki turda karara bağlanır.

## Değişmeyen sınırlar

- Türkiye'deki kişilerin verisi güvence kurulmadan Hetzner'e konmaz (Karar 27). Bu tur yalnız yerel ortamda ve örnek veriyle yürür.
- Sunucu, DNS, yasal kutu ve ödeme hesabı işleri insanda kalır.
- Push, pull request ve canlıya yükleme bu turda yapılmaz.

## Kişisel veri

Bu turda gerçek kişisel veri yoktur. Saklama süresi ve silme yolu MVP yayınından önce yazılır (G-15). Kişisel veri taşıyan kayıtlar şunlardır:

| Kayıt | Kişisel veri | Saklama | Silme yolu |
| --- | --- | --- | --- |
| “User” ve kimlik bağı | E-posta, ad, Keycloak kimliği | Hesap açık kaldıkça | Hesap silme isteği |
| “AI Action Log” | Kullanıcı adı, IP adresi | 365 gün (Rail 5) | Elle başlatılan silme komutu. Komut henüz yok. |
| “AI Usage Log” | Kullanıcı adı | Belirlenmedi | Belirlenmedi |

Mesaj içeriği ve araç girdisi günlüğe yazılmaz. Günlük yalnız girdinin özetini tutar.

## Teknik borç

Kod dışı borç bu bölüme yazılır. Her satırda eksik, etki, sorumlu ve kapanma koşulu bulunur.

| Borç | Etki | Sorumlu | Kapanma koşulu |
| --- | --- | --- | --- |
| `BORC(mvp)`: Press'in sunucu kurma akışı Frappe 16'da çalışmıyor | Press üretime çıkamaz | press-tr işi ve DevOps sorumlusu | Sunucu kurma akışı Frappe 16 ile hazırlık ortamında çalışır |
