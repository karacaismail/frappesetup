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
| `platform_core` | `identity` | Keycloak ile giriş, çıkış, kimlik bağı ve servis belirteci |
| `platform_core` | `shell` | Açılış verisi, kenar çubuğu verisi ve DocType tanımı uçları |
| `platform_core` | `ai` | Yapay zekâ erişim katmanı: araç kaydı, MCP ucu, önizleme ve onay, işlem günlüğü |
| `platform_core` | `mobile` | Telefon eşitlemesi: sürümlü mobil uçlar, işlem kimliği, imleç ve kaldırma işareti |
| `platform_core` | `access` | Erişim kuralı motoru: kayıt kuralı, hiyerarşi ve alan düzeyi (K8) |
| `platform_core` | `model_gateway` | Sağlayıcı, hesap, API ve model kaydı. Yönlendirme, model çağrısı ve kullanım kaydı. |
| `press_tr` | `identity` | Press'te Keycloak ile giriş, takım açma ve servis uçları |
| `identity_sync` | Yok | Keycloak ile Press ve kiracı siteleri arasında kullanıcı eşitleme |
| `oidc_verify` | Yok | Belirteç doğrulama. Frappe'ye bağlı değildir. |

## Bağımlılık yönü

- `platform_core.identity` ve `press_tr.press_identity` yalnız `oidc_verify` kitaplığını kullanır.
- `platform_core.shell` ile `platform_core.identity` birbirini çağırmaz.
- `platform_core.mobile` yalnız `identity` modülünün açık doğrulama işlevini çağırabilir. Öteki modüller `mobile` modülünü çağırmaz.
- `platform_core.access` öteki modülleri çağırmaz. Öteki modüller onu içe aktarmaz. Motor Frappe'nin izin kancalarıyla çalışır.
- `platform_core.model_gateway` öteki modülleri çağırmaz. `ai` modülü `model_gateway` modülünün açık işlevlerini çağırabilir.
- `platform_core.ai` öteki modüllerin açık işlevlerini çağırabilir. Öteki modüller `ai` modülünü çağırmaz. Uygulamalar araçlarını `ai_tools` kancasıyla bildirir.
- `identity_sync` sitelerin açık uçlarını HTTP ile çağırır. Siteler `identity_sync` kodunu çağırmaz.
- Döngü yasaktır. MVP'de bu yönler otomatik denetlenir (B-10).

## Denetim komutları

Bu bölümü dev-ortam işi doldurur. Her komutun çalıştığı klasör de yazılır.

| Denetim | Komut | Klasör |
| --- | --- | --- |
| Henüz yok | Yok | Yok |

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
- **D-12. Kod tabanı İngilizcedir.** Proje sahibi şöyle yazdı: “yeni dosya oluşturursen, türkçe değil, codebase ingilizce olsun, dosya adları ingilizce olsun”. Bu kararın uygulanışı şudur:
  - Dosya, klasör, modül, DocType, işlev ve değişken adları İngilizcedir.
  - Koddaki yorumlar, açıklama satırları, hata iletileri ve günlük metinleri İngilizcedir.
  - Kullanıcıya görünen metnin kaynağı İngilizcedir. Türkçesi çeviri dosyasında durur (V-2).
  - Belgelerin içeriği Türkçe kalabilir. Belge dosyalarının adı İngilizcedir.
  - Yerel ad ve adres değerleri de İngilizcedir. Örneğin kiracı sitesi `tenant1.localhost`, Keycloak sunucusu `id.localhost` olur.
  - `docs/standartlar/` klasöründeki standart belgeleri proje sahibinindir. Adları değişmez.
  - Ad eşleşme tablosu aşağıdadır.

## Orkestratörün seçtiği varsayılanlar

Proje sahibi bu konularda karar vermedi. Orkestratör şu varsayılanları seçti. Proje sahibi bunları değiştirebilir.

- **V-1. Ad dili.** Koddaki adlar İngilizcedir. Frappe ekosistemi bu dili kullanır.
- **V-2. Mesaj dili.** Kaynak metin İngilizce yazılır. Türkçesi çeviri dosyasında durur (G-73).
- **V-3. Modül adları.** Bu varsayılan D-12 ile değişti. Modül adları artık İngilizcedir.
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

- **O-13. Model geçidi `platform_core` içinde durur.** Modül `model_gateway` olur. Geçit sağlayıcılara düz HTTP ile bağlanır. Sağlayıcı kitaplığı kullanılmaz. Model adları yalnız kayıtta durur.
- **O-14. Kayıt önce kiracı sitesindedir.** Her kiracı kendi sağlayıcılarını, hesaplarını ve API'lerini ekleyebilir. Platformun ortak hesapları sonraki turda Press'ten site ayarına gelir.
- **O-15. Sağlık denetimi zamanlanmaz.** API'nin sağlığı gerçek çağrıların sonucundan çıkar. Elle başlatılan bağlantı denetimi de vardır (D-6).

## Karar sitesine işlenecek farklar

Backend kararları karar sitesinin bazı maddelerini değiştirdi. Site ayrı bir işte, kendi denetimleriyle güncellenir. Farklar şunlardır:

| Sitedeki madde | Yeni durum | Kaynak |
| --- | --- | --- |
| K1: Press Frappe 15 üzerinde çalışır. | Press de Frappe 16 üzerinde çalışır. | D-7, O-9 |
| K9: Claude Agent SDK ve adı yazılı Claude modelleri | Sağlayıcıdan bağımsız ajan servisi ve model geçidi | D-9, D-11, O-10 |
| G-84: Kiracı MCP'si `frappe_mcp` ile kurulur. | `frappe/mcp` deposu arşivlendi. Katmanı `platform_core.ai` kurar. | Karar notu 0002 |
| Rail 5: Onay `confirm=true` alanıyla verilir. | Modelde onay alanı yoktur. Onay insan oturumundaki ayrı uçtan gelir. | Sözleşme 10. bölüm |
| G-64: Günlük model, token ve maliyet tutar. | Bu alanlar “AI Usage Log” kaydındadır. | Karar notu 0002 |
| G-57: Kiracıda kullanıcı “System User” olur. | Son kullanıcı “Website User” olur. | D-5, O-3 |
| G-80: Tema Keycloakify ile yapılır. | Tema Keycloak'ın kendi tema yapısıyla yapılır. | O-4 |
| Rail 4: Saatlik yoklama ve gece mutabakatı | Zamanlanmış iş yok. Mutabakat elle başlar. | D-6, O-11 |

- **O-16. `cronhr` lisansı GPL-3.0 olur.** `cronhr`, GPL-3.0 lisanslı `hrms` uygulamasını aynı süreçte kullanır. En güvenli seçim budur. Hukuk görüşü alınmadı.
- **O-17. Yapay zekâ katmanı her sitede çalışacak.** Press ve operasyon sitesi de aynı katmanı kullanmalı. Katmanın ayrı bir uygulamaya bölünmesi sonraki turda karara bağlanır.

## Değişmeyen sınırlar

- Türkiye'deki kişilerin verisi güvence kurulmadan Hetzner'e konmaz (Karar 27). Bu tur yalnız yerel ortamda ve örnek veriyle yürür.
- Sunucu, DNS, yasal kutu ve ödeme hesabı işleri insanda kalır.
- Push, pull request ve canlıya yükleme bu turda yapılmaz.


## Ad eşleşme tablosu

Türkçe adlar 22 Kasım 2026 Pazar günü İngilizceye çevrildi (D-12). Pane ve dal adları değişmedi.

| Eski ad | Yeni ad |
| --- | --- |
| `PROJE-KAYDI.md` | `PROJECT-RECORD.md` |
| `docs/sozlesmeler.md` | `docs/contracts.md` |
| `docs/isler/` | `docs/tasks/` |
| `docs/kararlar/` | `docs/decisions/` |
| modül `kimlik` (Kimlik) | `identity` (Identity) |
| modül `kabuk` (Kabuk) | `shell` (Shell) |
| modül `yapay_zeka` (Yapay Zeka) | `ai` (AI) |
| modül `model_gecidi` (Model Gecidi) | `model_gateway` (Model Gateway) |
| modül `erisim` (Erisim) | `access` (Access) |
| modül `mobil` (Mobil) | `mobile` (Mobile) |
| `press_tr` modülü `kimlik` | `press_identity` (Press Identity) |
| `dev/compose.kiraci.yaml` | `dev/compose.tenant.yaml` |
| `dev/Dockerfile.kiraci` | `dev/Dockerfile.tenant` |
| `dev/bin/tunel ac/kapat/durum` | `dev/bin/tunnel open/close/status` |
| `dev/bin/guvenlik-denetimi` | `dev/bin/security-check` |
| `dev/guvenlik/` | `dev/security/` |
| `modul-sinirlari.json` | `module-boundaries.json` |
| `kiraci1.localhost` | `tenant1.localhost` |
| `site-kiraci1`, `aud-site-kiraci1` | `site-tenant1`, `aud-site-tenant1` |
| `kimlik.localhost` | `id.localhost` |
| `kiraci-*` compose servisleri | `tenant-*` |
| `kimlik_marka_adi` ayarı | `identity_brand_name` |
| `platform_core-kimlik.openapi.yaml` | `platform_core-identity.openapi.yaml` |
| `platform_core-kabuk.openapi.yaml` | `platform_core-shell.openapi.yaml` |
| `platform_core-yapay-zeka.openapi.yaml` | `platform_core-ai.openapi.yaml` |
| `platform_core-model-gecidi.openapi.yaml` | `platform_core-model-gateway.openapi.yaml` |
| `platform_core-erisim.openapi.yaml` | `platform_core-access.openapi.yaml` |
| `platform_core-mobil.openapi.yaml` | `platform_core-mobile.openapi.yaml` |
| karar notları `0002-yapay-zeka-katmani` ve benzerleri | `0002-ai-layer`, `0003-keycloak-extensions`, `0004-model-gateway`, `0005-security-gate`, `0006-access-rule`, `0007-mobile-sync`, `0008-first-vertical-slice` |

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
