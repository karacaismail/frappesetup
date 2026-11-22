# Backend proje kaydı

Bu dosya backend'in seviyesini, sürümlerini ve kararlarını tutar. Kod standartlarının Ek A bölümü bu kaydı ister. Kayıt 22 Kasım 2026 Pazar günü açıldı.

## Olgunluk seviyesi

- Seviye MVP'dir. MVP, ilk kullanılabilir sürümdür.
- Bütün modüller aynı seviyededir.
- Gerçek kişi verisi yine kullanılmaz. Bunun nedeni “Değişmeyen sınırlar” bölümündeki Karar 27'dir.

## Sürümler

| Bileşen | Hedef | Durum |
| --- | --- | --- |
| Kiracı sitesi | Frappe 16 ve ERPNext 16 | Yerelde `frappe/erpnext:v16.55.0` imajı var. Çalışan sürümü dev-ortam işi doğrular. |
| Press sitesi | Frappe 16, Press v0.154.1 ve Python 3.14 | Bu Mac'teki deneme kurulumunda bu sürümler çalışıyor. Press bu sürümde yalnız yamalarla açılır (O-9). |
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
| `press_tr` | `press_identity` | Press'te Keycloak ile giriş, takım açma ve servis uçları |
| `press_tr` | `ansible_bridge` | Press ile Ansible arasında görev sonuçlarını iletir. |
| `identity_sync` | Yok | Keycloak ile Press ve kiracı siteleri arasında kullanıcı eşitleme |
| `oidc_verify` | Yok | Belirteç doğrulama. Frappe'ye bağlı değildir. |

## Bağımlılık yönü

- `platform_core.identity` ve `press_tr.press_identity` yalnız `oidc_verify` kitaplığını kullanır.
- `press_tr.ansible_bridge` depo içindeki öteki modülleri çağırmaz. Bu modül başka modülün DocType kayıtlarına yazmaz.
- `platform_core.shell` ile `platform_core.identity` birbirini çağırmaz.
- `platform_core.mobile` yalnız `identity` modülünün açık doğrulama işlevini çağırabilir. Öteki modüller `mobile` modülünü çağırmaz.
- `platform_core.access` öteki modülleri çağırmaz. Motor Frappe'nin izin kancalarıyla çalışır.
  - Öteki modüller yalnız `platform_core.access.api` yolunu çağırabilir. Örneğin `ai` modülü `platform_core.access.api.report_guard` işlevini çağırır.
  - `shell` modülü “Access Rule” kayıt olaylarını `doc_events` kancasıyla dinler. Bu yüzden kuralı değiştiren kod kaydı `save` ile yazar. `frappe.db.set_value` kayıt olaylarını çalıştırmaz.
- `platform_core.model_gateway` öteki modülleri çağırmaz. `ai` modülü `model_gateway` modülünün açık işlevlerini çağırabilir.
- `platform_core.ai` öteki modüllerin açık işlevlerini çağırabilir. Öteki modüller `ai` modülünü çağırmaz. Uygulamalar araçlarını `ai_tools` kancasıyla bildirir.
- `identity_sync` sitelerin açık uçlarını HTTP ile çağırır. Siteler `identity_sync` kodunu çağırmaz.
- Döngü yasaktır. MVP'de bu yönler otomatik denetlenir (B-10).

## HRMS TR ortak kayıtları

HRMS TR, erişim kurallarını `platform_core.access` ile uygular.
Uygulama, `ai_tools` kancasıyla izin onay aracını bildirir.
İnsan onay ucu, önizleme alanları ve yanıtlar [OpenAPI sözleşmesinde](contracts/hrms_tr.openapi.yaml) yer alır.

`Leave Application` türünün `validate` ve `before_cancel` olayları izin akışını denetler.
`DocShare.validate` izin taleplerinin paylaşımını engeller.
`User.before_save` portal rollerine sahip kullanıcıların hesap türünü korur.
`modified` alanı kaydın sürümünü belirler.
`leave_balance` alanı izin bakiyesini tutar ve alan iznine bağlıdır.
[0008 numaralı karar](docs/decisions/0008-hrms-tr-first-vertical-slice.md) ayrıntıları açıklar.

## Denetim komutları

Ortam komutları Pane'in verdiği `PANE_PORT` değerini kullanır.

| Denetim | Komut | Klasör |
| --- | --- | --- |
| Frappe kurulum testleri | `backend/dev/bin/test platform_core` | Depo kökü |
| Python kod ve biçim denetimi | `backend/dev/bin/ruff` | Depo kökü |
| Modül sınırları | `backend/dev/bin/module-boundaries` | Depo kökü |
| Ortam betiklerinin Python testleri | `python3 -m unittest discover -s backend/dev/tests` | Depo kökü |
| Atonota giriş teması | Komut ve dosya listesi `backend/identity/keycloak/themes/atonota/README.md` dosyasındadır. Her sayfaya yüklenen stil ve betik ile ileti dosyalarının yolu da oradadır. | Depo kökü |

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

- **O-16. `hrms_tr` lisansı GPL-3.0 olur.** `hrms_tr`, GPL-3.0 lisanslı `hrms` uygulamasını aynı süreçte kullanır. En güvenli seçim budur. Hukuk görüşü alınmadı.
- **O-17. Yapay zekâ katmanı her sitede çalışacak.** Press ve operasyon sitesi de aynı katmanı kullanmalı. Katmanın ayrı bir uygulamaya bölünmesi sonraki turda karara bağlanır.
- **O-18. Press'in geliştirme yaması geçici bir istisnadır.** `dev/press/patch-py314.sh` betiği Press'in kurulu kodunu değiştirir. Bu, M-4 kuralına aykırıdır. Yama yalnız geliştirme imajında çalışır. Üretim imajına girmez. 22 Kasım 2026 Pazar günü temiz Press v0.154.1 kaynağı denendi. Python 3.14.10 ve Frappe 16.56.0 kullanıldı. Ansible, Telegram ve Stripe paket adayları içe aktarıldı. Press kaynak farkı boştu. Eski `TypedDict` tanımı ve kaldırılan `init_telemetry` işlevi modül açılışını engelledi. İnceleme, `press/api/cookies.py:7` satırında üçüncü kaynak engelini doğruladı. Frappe 16, `get_cookie_dict_from_headers` işlevini sunmuyor. `pyproject.toml` bağımlılık şartları da aday paketlerle karşılanmadı. `--no-deps` tanı kurulumu tam çözüm veya bağımlılık kilidi değildir. İnceleme sonrası başlangıç kaynağında 13 test çalıştı. Yedi test geçti ve altı test başarısız oldu. Kaynak bütünlüğü ve yama izi denetimleri geçti. `uv pip check`, 177 pakette 32 uyumsuzluk buldu. Site ve masa denemeleri çalıştırılmadı. Yama kaldırılmadı ve borç açık kaldı. [Press değişiklik önerisi](docs/press-python314-upstream.md) hazırlandı. Öneri henüz gönderilmedi. Ardından 162 yeni etikette iki kaynak dosyası tarandı. İki dalın aynı dosyalara ait geçmişi de tarandı. `TypedDict` ve telemetri engelleri hepsinde korundu. Bu tarama çerez dosyasını veya bağımlılık çözümünü kapsamadı. Son develop commit koduyla ilk dar kapsamlı kabul testleri de başarısız oldu. [Sürüm taramasının kanıtı](docs/press-python314-version-audit.md) kaydedildi. Bu araştırma kolu kapatıldı. Kapanma koşulu borç tablosundadır.
- **O-19. Dallar sırayla birleşir.** Sıra şudur: kimlik-realm, platform-core-kimlik, identity-sync, press-tr, platform-core-kabuk, platform-core-yz, platform-core-gecit, erisim-kurali, platform-core-mobil, ilk-dikey-dilim, kimlik-tema, integration-e2e.
  - Her birleştirmeden önce bağımsız inceleme `pass` olur.
  - `hooks.py` dosyasını orkestratör birleştirir. Liste değerleri birleşir, hiçbiri silinmez. Örneğin iki dalın `override_whitelisted_methods` satırları yan yana kalır.
  - Birleştirmede kurulum testinin modül listesi güncellenir. `oidc_verify` kiracı imajına eklenir.
- **O-20. Ad düzeltmesi geliştirme sitelerini yeniden kurar.** Sitelerde gerçek veri yok. Bu yüzden veri taşıma yaması yazılmaz. `frappe.rename_doc` da kullanılmaz.
  - Kiracı sitesi, Press sitesi ve Keycloak realm'i silinir ve yeniden kurulur.
  - Betikten önce eski compose projesi eski adıyla kapatılır.
  - Salt okunur bir denetim `.env` ve site ayarında eski anahtar arar. Eski anahtar kalırsa uyarı verir.
  - İlk yayından sonra bu yol kapanır. O zaman her ad değişikliği veri taşıma yamasıyla yapılır (AV-26).
- **O-21. Ad ile serbest metin ayrı işlerdir.** Ad eşleşmesini yalnız naming-history-fix betiği uygular. Betik cümleye, yoruma ve Türkçe belge içeriğine dokunmaz.
  - Türkçe etiket, ileti, açıklama ve sözleşme açıklamasını her işin sahibi İngilizceye çevirir. Örneğin `mobile_change.json` etiketlerini platform-core-mobil işi çevirir.
  - Eski Türkçe metin çeviri dosyasına girer. Böylece ekran Türkçe kalır.
  - Çeviri betik çalıştıktan sonra yapılır. Bir ad kapısı kalan Türkçe adı ve etiketi bulur.
- **O-22. İki belge eski adıyla bir yönlendirme dosyası bırakır.** `PROJE-KAYDI.md` ve `docs/sozlesmeler.md` dosyalarının adı değişir. Proje sahibinin karar dosyası bu iki yolu anar. Bu yüzden eski yolda tek satırlık bir dosya kalır. Dosya yeni adı gösterir.
- **O-23. Çeviri dosyası bağlam sütunu taşır.** Biçim Frappe 16'nın CSV biçimidir: kaynak, çeviri, bağlam. Aynı İngilizce sözcük iki anlam taşıyorsa bağlam sütunu doldurulur. `tr.csv` ortak dosyadır ve orkestratör birleştirir.
- **O-24. DocType JSON dosyaları Frappe'nin dışa aktarma biçimindedir.** Dosyayı Frappe'nin kendi yazdığı biçimde tutun. Anahtarlar sıralı, girinti bir boşluktur. Elle yazılan dosya bu biçime çevrilir.
- **O-25. Karar 19 süreleri bu turda uygulanır.** Bu karar O-5'in ikinci cümlesinin yerine geçer. Mobil iş başladı. Süreler şunlardır:

  | Ayar | Çalışan | Müşteri |
  | --- | --- | --- |
  | Erişim belirtecinin ömrü | 5 dakika | 5 dakika |
  | Yenileme belirteci | Her kullanımda değişir | Her kullanımda değişir |
  | Keycloak'ta boşta kalma | 1 saat | 7 gün |
  | Keycloak'ta toplam süre | 24 saat | 30 gün |
  | PWA'da Frappe çerezinin boşta kalma süresi | 1 saat | 1 saat |
  | Paket arka plandayken yerel kilit | 2 dakika | 5 dakika |
  | Pakette bağlantısız erişim | 24 saat | 72 saat |
  | PWA'da bağlantısız erişim | 8 saat | 24 saat |
  | Çıkıştan sonra taslak saklama | 7 gün | 7 gün |

  - Keycloak ayarlarını kimlik-realm işi kurar. Frappe çerez süresini platform-core-kimlik işi kurar. Paket ve PWA sürelerini sunucu tarafında platform-core-mobil işi denetler.
  - Çalışan 1 saat boşta kalırsa yeniden kimlik doğrular. Keycloak'ın açık çerezi bu adımı atlatmaz. Bunu canlı test gösterir.
  - Arka plan eşitlemesi süreleri uzatmaz. Sunucu gerçek kullanıcı işlemini ayrıca sayar.
  - MVP'de kiracı sitesinin ve telefon paketinin bütün kullanıcıları çalışan süresini alır. Müşteri süreleri Press'e uygulanır. Ayrıntı sözleşmenin 3. bölümündedir.
- **O-26. Telefon paketi bu turda yazılmaz.** Sunucu tarafı MVP düzeyinde kurulur. Paket işi açılınca `mobile.md` MVP koşulları o işe yazılır. Mağaza hesapları proje sahibindedir.
- **O-27. Müşteri kendi hesabını açabilir. Bu yüzden hesap silme yolu MVP'dedir.** Deneme akışı Keycloak kayıt sayfasıyla başlar (G-79). Kuralın dayanağı karar dosyasındaki hesap silme kuralı ve CK-6'dır.
  - Çalışan kendi hesabını açamaz. Çalışan yalnız davetle gelir.
  - Müşteri silme isteğini Press'te verir. Press kullanıcıyı önce Keycloak'ta yeniden doğrular. Keycloak'ın kendi hesap silme eylemi kapalıdır, çünkü bu eylem kullanıcıyı ilk adımda siler. Hesap ekranındaki bağlantı Press'teki silme sayfasına gider.
  - identity-sync isteği kaydeder. Sonra Keycloak kullanıcısını kapatır ve siler. Press kullanıcısını kapatır ve API anahtarlarını geçersiz kılar. Kiracı sitelerindeki kullanıcıyı kapatır. Telefon kurulumlarını ve bildirim bağlarını siler (CK-7).
  - İş kayıtları silinmez. Çalışan kartındaki kişisel alanlar O-41 kapsamına göre anonim yapılır. İzin, devam ve bordro kayıtlarındaki ad kopyaları şimdilik kalır. Ad kopyalarının silinmesi hedeftir. Bu iş O-41 borcudur. Proje sahibi bu varsayılanı değiştirebilir.
  - Fatura kayıtları değişmez. Fatura yasal kayıttır ve kesildiği hâliyle saklanır.
  - Silinen kimliğin ham değeri saklanmaz. Yeniden açmayı engellemek için yalnız kimliğin HMAC özeti tutulur.
  - Kullanıcı bir takımın tek üyesiyse takım kapatılır ve siteleri askıya alınır. Siteler silinmez.
  - Ayrıntılı kurallar sözleşmenin 7. bölümündedir.
  - Kiracı sitesi, `clear_fields` listesindeki zorunlu olmayan alanları boşaltır. Listede zorunlu bir alan varsa sistem hata verir.
  - Sistem, boşalttığı dosya ve fotoğraf alanlarına bağlı dosya kayıtlarını siler. Başka bir kayıt dosyayı kullanmıyorsa sistem dosyayı diskten de siler.
  - Sistem, anonim yaptığı alanların eski ve yeni değerlerini kart geçmişinden temizler. Sistem bu işlemi geçmişi kimin yazdığına bakmadan yapar. Diğer alanların geçmişi kalır.
- **O-28. Yapay zekâ katmanı genel Frappe erişimi değildir.** D-9 her şeyin yapay zekâyla yönetilmesini ister. AX-2 modele genel Frappe erişimi vermeyi yasaklar. İki kural şöyle birleşir:
  - Model yalnız kayıtlı araçları çağırır. Her araç kullanıcının yetkisiyle çalışır.
  - Yazma önce öneri olur. İnsan ayrı uçtan onay verir.
  - Hassas DocType'lar genel yazma araçlarına kapalıdır. Bunlar kimlik bağı, erişim kuralı, AI API, AI Account ve telefon kurulumudur. Her sahip kendi DocType'ını `ai_write_closed_doctypes` kancasına ekler. Bu kayıtlar yalnız kendi özel araçlarıyla değişir.
- **O-29. Güvenlik taramaları elle başlatılan komutlardır.** Zamanlanmış tarama kurulmaz (D-6). Komutları security-tooling işi yazar. Bandit, gizli bilgi taraması, sözleşme tabanlı API testi ve yerel DAST taraması bu kapsamdadır. CI kurulumunun teknik sahibi DevOps sorumlusudur. Ajanlar CI dosyasını değiştirmez, devir notu yazar.
- **O-30. Ad denetimi geçiş süresinde uyarı verir.** Ad denetim betiği birleşince kapı bütün dallarda 389 ad bulgusu verdi. Eski adlar ancak ad değiştirme betiği bütün dallarda çalışınca kalkar. Bu yüzden kapı ad bulgularını şimdilik yalnız yazar ve başarısız olmaz. Kip `backend/dev/naming/enforcement.json` dosyasındaki `mode` alanında durur. Değer `advisory` ya da `enforce` olur. Başlangıç değeri `advisory` olur. Ad değiştirme bütün dallarda bitince orkestratör değeri `enforce` yapar. `enforce` kipinde `legacy-name`, `turkish-name`, `module-name` ve `translation-binding` bulguları kapıyı durdurur. Öteki ad bulguları yine yalnız uyarıdır. Kip dosyası yoksa kapı `advisory` kabul eder ve bunu çıktısına yazar.
- **O-31. MVP performans sınırı.** Sunucu süresi okuma uçlarında p95 500 milisaniyeyi, yazma uçlarında p95 1 saniyeyi geçmez. Ölçüm geliştirme sitesinde örnek veriyle yapılır. Örnek veri 200 çalışan ve 2.000 izin kaydıdır. Her uç en az 50 kez çağrılır. Ölçümü elle başlatılan bir komut yapar ve sonucu durum dosyasına yazar. Frappe dışındaki servisler, örneğin identity-sync, kendi geliştirme kurulumunda sahte hedeflerle ölçülür. Bu ölçüm O-31 için geçerlidir, çünkü servis süresi hedef servisten ayrı ölçülür. Grafana ve gerçek kullanıcı ölçümü P1 işidir (G-149). Bu yüzden teknik borç tablosuna yazıldı.
- **O-32. Saklama temizliği kopya bırakmaz.** Saklama süresi dolan kayıt kalıcı silinir. Kod `frappe.delete_doc` çağrısına `delete_permanently=True` verir. Böylece “Deleted Document” tablosunda kopya kalmaz. Geri dönüş yolu veritabanı yedeğidir. V-10 kuralının geri yükleme kopyası yalnız yöneticinin iş kaydını elle silmesi için geçerlidir. Bu kural bütün modüllerin saklama temizliğine uygulanır. Örneğin model geçidi ve yapay zekâ katmanının günlük temizliği böyledir.
- **O-33. Bağımsız dal sırayı beklemez.** O-19 sırası bağımlılık içindir. Bağımsız inceleme `pass` veren ve başka dala bağlı olmayan dal hemen birleşir. Bağımlı dal bağlı olduğu daldan sonra birleşir. Örneğin press-tr ve identity-sync dalları kimlik-realm dalından sonra birleşir, çünkü ikisi de `oidc_verify` kitaplığını kullanır. ilk-dikey-dilim dalı platform-core-yz ve erisim-kurali dallarından sonra birleşir. Her birleşmeden sonra orkestratör kapıları, modül sınırını ve ortak dosya denetimlerini çalıştırır.
- **O-34. Yasaklı adı taşıyan commit mesajı yayımlanmaz.** Yasaklı ürün adı (D-13) yerel geçmişte sekiz commit mesajında kaldı. Biri `backend` dalındaki `58e8dbc` kaydıdır. Yedisi `ilk-dikey-dilim` dalının ilk kayıtlarıdır. Bu kayıtlar hiçbir uzak depoya gönderilmedi. Geçmişi yeniden yazmak öteki dalların ortak atasını bozar. Bu yüzden şu kurallar uygulanır:
  - `ilk-dikey-dilim` dalı `backend` dalına `git merge --squash` ile girer. Birleşme commit'i yeni ve temiz bir mesaj taşır.
  - `backend` dalı `main` dalına tek commit olarak girer. Yasaklı adı taşıyan hiçbir commit uzak depoya gönderilmez. Gönderim için proje sahibinin onayı gerekir.
  - Uygunluk kapısı commit mesajlarındaki yasaklı adı yakalamaya devam eder.
  - integration-e2e işinin geçici önizleme dalları uzak depoya gönderilmez. İş bitince silinir.
- **O-35. Ölçüm komutları yalnız ayrı deneme sitesinde çalışır.** Performans ölçüm komutu var olan veriye ve kuyruğa dokunmaz. Kurallar şunlardır:
  - Komut yalnız adı `perf-` ile başlayan ve `.localhost` ile biten sitede çalışır. Site ayarında `allow_performance_fixture` değeri 1 olmalıdır. Öteki sitede komut veri oluşturmadan durur.
  - Komut başlamadan önce kuyruk boş olmalıdır. Kuyruk boş değilse komut veri oluşturmadan durur. Komut başka işin kuyruğunu çalıştırmaz.
  - Komut yalnız kendi oluşturduğu kayıtları siler. Kayıtları tür ve ad çiftiyle seçer.
  - Ölçüm bitince site silinebilir. Geri yükleme gerekmez.
  - Bu kural bütün işlerin ölçüm komutlarına uygulanır.
  - Veritabanını değiştiren ölçüm testleri yalnız `perf-` sitesinde koşar, öteki sitede açık nedenle atlanır. Ölçüm mantığının testleri sahte veriyle çalışır.
  - Adı `test-` ile başlayan siteler atılabilir deneme siteleridir. Ortak test sınıflarının bu sitelerdeki toplu temizliği kabul edilir.
- **O-36. Servis belirteci kodu kimlik klasöründe durur.** Kiracı sitesi identity-sync için servis belirteci alır. Bu kod `kimlik/service_client.py` dosyasındadır. Kurallar şunlardır:
  - Dosyayı platform-core-mobil dalı yazdı. Orkestratör bu yazımı bir kez onayladı. Mobil dal birleşene kadar dosyayı mobil çalışanı düzeltir. Birleşmeden sonra dosyanın sahibi platform-core-kimlik işidir.
  - Modülün açık yolu `platform_core.kimlik.service_client` olur. Yol `dev/modul-sinirlari.json` dosyasına eklendi.
  - Belirteç adresi Keycloak ayarlarından türetilir. Önce `keycloak_internal_url`, yoksa `keycloak_public_url` kullanılır. `mobile_identity_sync_token_url` ayarı kullanılmaz.
  - Adres HTTPS olmalıdır. Bu yüzden geliştirme sitesinde uzak oturum kapatma `delivery_pending` durumunda kalır. Gerçek deneme için integration-e2e işi Keycloak'a HTTPS iç adres verir.
  - platform-core-kimlik dalı mobil dosyalarındaki değişikliklerini geri alır. Bu dosyalar `mobil/identity_sync_client.py`, onun testi ve `0007-mobil-esitleme.md` notudur.
- **O-37. Birleştirmede ortak dosya ve bağımlılık kuralları.** 22 Kasım 2026 Pazar günü bütün backend dalları birleşti. Kurallar şunlardır:
  - `oidc_verify` kitaplığı iki uygulamada da `oidc_verify==0.1.0` kuralıyla istenir. Kitaplık depodadır ve sürüm paketiyle birlikte kurulur. Kural değişince güvenlik kilidi `backend/dev/security/compile-lock` ile yeniden üretilir.
  - `hooks.py` içinde her kanca bir kez atanır. Örneğin `override_whitelisted_methods` sözlüğü hem kimlik giriş kapılarını hem erişim kuralının bağlantı aramasını taşır. İkinci atama birinciyi sileceği için yazılmaz.
  - `auth_hooks` sırası şudur: kimlik servis belirteci, yapay zekâ ajan belirteci, MCP OAuth, kabuk meta veri kapısı. Belirteç kancaları kapıdan önce çalışır.
  - Press çıkış bildirim ucunda imzası doğrulanan bildirim sayaca girmez. Reddedilen bildirim dakikada 120 ile sınırlıdır. Sözleşme bu kuralı yazar. Uç denetimi bu ucu kodla eşleşen istisnayla kabul eder.
  - Semgrep istisna özeti yalnız Git'in izlediği ve yok saymadığı dosyalardan hesaplanır. Böylece geliştiricinin ön bellek klasörü özeti değiştirmez.
  - Bandit istisna listeleri birleşirken iki taraf korunur. Kod imzası artık eşleşmeyen kayıtları güvenlik işi sonraki taramada temizler.
- **O-38. identity-sync'te kiracı ve platform yetkisi ayrıdır.** Bir kiracının servis istemcisi bütün platformun kuyruğunu yeniden oynatabiliyordu. Bu açık şöyle kapanır:
  - Kiracı servis istemcisi yürütme yetkisini korur. Yetki yalnız kendi kuruluşu içindir. Örneğin kendi kuruluşuna kullanıcı davet eder.
  - Mutabakat, kuyruk yeniden oynatma ve platform listeleri yeni `IDENTITY_SYNC_OPERATOR_AZP` listesindeki istemcinindir.
  - Operatör, önizleme ve silme listelerinde `site-` ile başlayan istemci olmaz. Ayrıntı sözleşmenin 7. bölümündedir.
- **O-39. Saklama komutu yalnız süresi dolan izin kayıtlarını siler.** Komut, çalışan kaydını ve diğer HR kayıtlarını korur.
  - Hesap silme, çalışan kartındaki kişisel alanları O-41 kapsamına göre anonim yapar. Ayrıntı sözleşmenin 5. ve 7. bölümlerindedir.
  - Gönderilmiş izin kayıtları komutun kapsamı dışındadır. HRMS iptali izin hareketlerine ve devam kayıtlarına yazar. Bu izinlerin silme yolu hukuk kararından sonra ayrıca belirlenir.
  - Bağlı HR kayıtlarının saklama süresini hukuk sorumlusu belirler. Bu süre teknik borç tablosunda açık kalır.
- **O-40. Kiracı yanıtları içerik güvenliği politikası taşır.** Desk satır içi betik kullanır. Taban politika bu betiklere izin verir.
  - Taban yanıt `frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'` politikasını taşır.
  - Giriş ve Panel `default-src 'self'; script-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'` politikasını taşır.
  - Giriş ve Panel yanıtları `X-Frame-Options: DENY` taşır. Yönlendirme yanıtları da aynı başlıkları taşır.
  - Başlığı `platform_core` kancası ekler. Kanca, varsa yanıtın kendi başlığını korur. Frappe kodu değişmez.
  - Üretimde ters vekil başlığı ekleyebilir. Uygulamanın taban politikası da yürürlükte kalır.

- **O-41. Hesap silme, çalışan kartındaki kişisel alanları anonim yapar.** Sistem, çalışan kartını kullanıcı bağıyla bulur.
  - Sistem adları, iletişim ve acil durum bilgilerini ve adresleri anonim yapar.
  - Sistem pasaport numarasını, pasaportun düzenlendiği yeri, banka, sağlık, sigorta ve aile bilgilerini anonim yapar.
  - Doğum tarihi, pasaport tarihleri, devam cihazı kimliği, kan grubu ve medeni durum alanları boşalır.
  - Sistem fotoğraf alanını boşaltır ve bu alana bağlı dosya kaydını siler. Başka bir kayıt dosyayı kullanmıyorsa sistem dosyayı diskten de siler. Ortak küçük resim, ilgili son dosya kaydı silinene kadar kalır. Aynı kartta fotoğraf adresini kullanan başka dosya kaydı yoksa yükleme bağlantısı da silinir.
  - Sistem, seçili kart alanlarının eski ve yeni değerlerini değişiklik geçmişinden temizler. İK'nın yazdığı geçmiş de bu kapsamdadır. Diğer alanların geçmişi kalır. Geçmiş verisi bozuksa sistem hata verir ve mevcut geçmişi korur.
  - `clear_fields`, `redact_fields` içindeki zorunlu olmayan tek değerli alanları boşaltır. Listede zorunlu bir alan varsa sistem hata verir.
  - Eğitim ve önceki iş alt tabloları bu kancayla temizlenmez. Bu tablolar açık teknik borçtur.
  - İzin, devam ve bordro kayıtlarındaki çalışan adı kopyaları kalır. Bu kopyalar için `platform_core` tarafında ayrı bir kanca gerekir.

- **O-43. Kiracı, hesap silme sonucunu eşitleme hizmetine bildirir.**
  - Başarılı yanıtta `anonymized` ve `found` alanları `true` olur. Yanıt `user`, `enabled` ve `status` alanlarını da taşır.
  - Sistem kimlik bağını ve silme kaydını bulamazsa HTTP 404 ve `IdentityNotFound` döner. Eşitleme hizmeti bu sitedeki silme adımını tamamlandı sayar.

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

## Değişmeyen sınırlar

- Türkiye'deki kişilerin verisi güvence kurulmadan Hetzner'e konmaz (Karar 27). Bu tur yalnız yerel ortamda ve örnek veriyle yürür.
- Sunucu, DNS, yasal kutu ve ödeme hesabı işleri insanda kalır.
- Push, pull request ve canlıya yükleme bu turda yapılmaz.

## Kişisel veri

Bu turda gerçek kişisel veri yoktur. Saklama süresi ve silme yolu MVP yayınından önce yazılır (G-15). Kişisel veri taşıyan kayıtlar şunlardır:

| Kayıt | Kişisel veri | Saklama | Silme yolu |
| --- | --- | --- | --- |
| “User” ve kimlik bağı | E-posta, ad, Keycloak kimliği | Hesap açık kaldıkça | Hesap silme isteği |
| “AI Action Log” | Kullanıcı adı, IP adresi, hedef kaydın adı (`target_name`). Hedef adı e-posta olabilir | 365 gün (Rail 5) | `platform_core.api.ai.purge_logs` komutu elle çalışır |
| “AI Usage Log” | Kullanıcı adı | 365 gün. Bütçe ve fatura denetimi bu süreyi ister | Aynı silme komutu elle çalışır |
| “AI Action Proposal” | Kullanıcı adı ve önizlemedeki kişi bilgisi. Örneğin çalışan adı ve izin tarihleri | Karar ya da süre dolumundan sonra 30 gün | Aynı silme komutu elle çalışır. Önizleme yalnız gerekli bilgiyi tutar |
| Hesap silme isteği (O-27) | E-posta ve Keycloak kimliği | İş bitene kadar | İş bitince kayıt anonim yapılır |
| identity-sync kayıt dosyası | Keycloak kullanıcı kimliği. E-posta ve ad tutulmaz | İş bitene kadar | İş bitince kimlik HMAC izine çevrilir (O-27) |
| HRMS TR çalışan ve izin kayıtları | Ad, izin tarihleri, onaylayan kişi | İş ilişkisi sürdükçe. Yasal saklama süresini hukuk sorumlusu belirler. Bu madde teknik borçtur | Hesap silme, çalışan kartındaki alanları O-41 kapsamına göre anonim yapar. İş kayıtları ve ad kopyaları kalır (O-27). |

Mesaj içeriği ve araç girdisi günlüğe yazılmaz. Günlük yalnız girdinin özetini tutar.

## Teknik borç

Kod dışı borç bu bölüme yazılır. Her satırda eksik, etki, sorumlu ve kapanma koşulu bulunur.

| Borç | Etki | Sorumlu | Kapanma koşulu |
| --- | --- | --- | --- |
| `BORC(mvp)`: Dış MCP istemcileri OAuth 2.1 ile giremez | Özellik varsayılan olarak kapalı. Yerel testler dönüş adresini, kaynak alanını ve 3 saniyelik süre sınırını doğruladı. | platform-core-yz | Tam realm, `resource-indicators` özelliğiyle hazırlanır. Hazır bir MCP istemcisiyle uçtan uca OAuth akışı doğrulanır. |
| `BORC(mvp)`: Üretim işçi sayısı ölçülmedi | 50 eşzamanlı telefonda 4 Gunicorn işçisiyle istemci p95 1 saniyeyi aştı. Sunucu süresi sınırın altında kaldı | DevOps sorumlusu | Üretim kapasite ölçümü yapılır ve işçi sayısı ölçümle seçilir |
| `BORC(mvp)`: identity-sync canlı Keycloak, Press ve kiracı ile denenmedi | Sahte hedeflerin kaçırdığı uyumsuzluk üretimde çıkabilir | integration-e2e | Uçtan uca test gerçek servislerle geçer |
| `BORC(mvp)`: identity-sync testleri CI'da koşmaz | Bozulma yalnız elle çalışan testte görülür | DevOps sorumlusu | CI bu klasörün testlerini her değişiklikte koşar |
| `BORC(mvp)`: Tema derleme adımının iki kopyası var | Bir kopya değişince öteki eski kalabilir | kimlik-tema | Derleme adımı tek yerde durur ve test bunu denetler |
| `BORC(mvp)`: Bazı tema ekranları sınanmadı | Görünüm hatası fark edilmeyebilir | kimlik-tema | Sınanmamış ekranların listesi boşalır |
| `BORC(mvp)`: Geçiş anahtarı testleri yük altında zaman aşımına uğruyor | Test sonucu güvenilmez olur | kimlik-tema | Testler yük altında da kararlı geçer |
| `BORC(mvp)`: Performans ölçümü yalnız elle yapılır (O-31) | Canlı darboğaz görülmez | DevOps sorumlusu | P1'de Grafana ve gerçek kullanıcı ölçümü kurulur (G-149) |
| `BORC(mvp)`: İzinlerin ve bağlı HR kayıtlarının yasal saklama süresi yok (O-39) | Silme zamanı belli değil | Hukuk sorumlusu | Hukuk sorumlusu süreleri proje kaydına yazar. İzin komutu yalnız taslak ve iptal edilmiş izinlerde site ayarındaki süreyi uygular. Bağlı HR kayıtları için silme yolu ayrıca belirlenir. |
| `BORC(mvp)`: Çalışan kartının alt tabloları ve iş kayıtlarındaki ad kopyaları kalıyor (O-41) | Hesap silme bu alanları temizlemez | platform-core-kimlik ve ilk-dikey-dilim | `platform_core` hesap silme kancası alt tablolara ve kullanıcıya bağlı iş kayıtlarına güvenli erişim sağlar |
| `BORC(mvp)`: Press'in sunucu kurma akışı Frappe 16'da çalışmıyor | Press üretime çıkamaz | press-tr işi ve DevOps sorumlusu | Sunucu kurma akışı Frappe 16 ile hazırlık ortamında çalışır |
| `BORC(mvp)`: Press geliştirme yaması açık kaldı (O-18) | M-4 ihlali sürüyor. Temiz v0.154.1 kaynağında `TypedDict`, telemetri ve çerez import'u başarısız. Tam bağımlılık çözümü ve kilidi de eksik. [Öneri ve test kanıtı](docs/press-python314-upstream.md) hazırlandı. [162 yeni etiketin iki dosyalık taraması](docs/press-python314-version-audit.md) ilk iki engeli kaldıramadı. | press-tr işi | Press, Python 3.14 ve Frappe 16 üzerinde yamasız açılır ya da düzeltmeler Press'e kabul edilir. Üç kaynak engeli giderilir. Tam bağımlılık denetimi, kaynak bütünlüğü, site ve masa testleri geçer. |
| `BORC(mvp)`: CI'da güvenlik kapısı yok (O-29) | Taramalar yalnız elle çalışır | DevOps sorumlusu | Devir notundaki işler CI'da koşar ve başarısız tarama birleştirmeyi durdurur |
| Bandit istisnaları 22 Şubat 2027 Pazartesi günü sona erer | Süresi dolan istisna taramayı durdurur | dev-ortam ve security-tooling | Sahipler her istisnayı yeniden inceler |
| `BORC(mvp)`: Telefon paketi yok (O-26) | Mağaza koşulları sınanmadı | Proje sahibi ve sonraki tur | Paket işi açılır ve `mobile.md` MVP koşulları geçer |

### Kapanan teknik borç

- **Çalışan fotoğrafı ve kart geçmişi (O-41).** Hesap silme, fotoğraf alanına bağlı dosya kaydını siler. Paylaşılan dosya içeriği son kayıt silinene kadar diskte kalır. Sistem, karttaki seçili alanların eski ve yeni değerlerini geçmişten temizler.

- `list_identities` uçları tamamlandı. Kiracı ve Press uçları aynı sayfalama sözleşmesini kullanır.
- Kiracı HTTP testleri ikinci sayfayı ve yetkisiz istek reddini doğruladı.
- Press ucu ve sayfalama testleri `f4cb09f` birleşme kaydında yer alır.

- **Yeni kiracı için Keycloak istemcisi.** `a51ef9a` kaydı `create-tenant-client.py` komutunu ekledi.
  `test_confirmed_creation_posts_restricted_client_to_admin_api` testi, onay sonrası isteği doğrular.
- **Kimlik eşitleme servisinin container dosyası.** `6aaa981` kaydı `Dockerfile` dosyasını ekledi.
  İmaj `oidc_verify` kitaplığıyla açıldı. `/healthz` isteği HTTP 200 döndü.
