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
| `press_tr` | `kimlik` | Press'te Keycloak ile giriş, takım açma ve servis uçları |
| `identity_sync` | Yok | Keycloak ile Press ve kiracı siteleri arasında kullanıcı eşitleme |
| `oidc_verify` | Yok | Belirteç doğrulama. Frappe'ye bağlı değildir. |

## Bağımlılık yönü

- `platform_core.kimlik` ve `press_tr.kimlik` yalnız `oidc_verify` kitaplığını kullanır.
- `platform_core.kabuk` ile `platform_core.kimlik` birbirini çağırmaz.
- `platform_core.yapay_zeka` öteki modüllerin açık işlevlerini çağırabilir. Öteki modüller `yapay_zeka` modülünü çağırmaz. Uygulamalar araçlarını `ai_tools` kancasıyla bildirir.
- `identity_sync` sitelerin açık uçlarını HTTP ile çağırır. Siteler `identity_sync` kodunu çağırmaz.
- Döngü yasaktır. MVP'de bu yönler otomatik denetlenir (B-10).

## Denetim komutları

Bu bölümü dev-ortam işi doldurur. Her komutun çalıştığı klasör de yazılır.

| Denetim | Komut | Klasör |
| --- | --- | --- |
| Henüz yok | Yok | Yok |

## Proje sahibinin kararları

Kararlar 22 Kasım 2026 Pazar günü Pane kartıyla alındı.

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
- **D-9. Her şey yapay zekâyla yönetilebilir olur.** Bütün DocType'lar, alanlar ve backend işlemleri yapay zekâya açık bir katmandan geçer. Katman model sağlayıcısından bağımsızdır. Proje sahibi şöyle yazdı: “ai heryerde olmalı, ai provider'dan bağımsız, herşey ai ile yönetilebilmeli.” Ayrıntı sözleşmenin 10. bölümündedir.
- **D-8. Var olan Press kurulumu kullanılır.** Bu Mac'te Colima'da bir Press deneme kurulumu var. Kurulum değiştirilmez. İmajı ve kurulum betikleri yeniden kullanılır.

## Orkestratörün seçtiği varsayılanlar

Proje sahibi bu konularda karar vermedi. Orkestratör şu varsayılanları seçti. Proje sahibi bunları değiştirebilir.

- **V-1. Ad dili.** Koddaki adlar İngilizcedir. Frappe ekosistemi bu dili kullanır.
- **V-2. Mesaj dili.** Kaynak metin İngilizce yazılır. Türkçesi çeviri dosyasında durur (G-73).
- **V-3. Modül adları.** Modül adları Türkçedir. Örneğin `kimlik` ve `kabuk` modülleri vardır.
- **V-4. Ortak kitaplık.** Belirteç doğrulama tek kitaplıkta durur. `platform_core` ve `press_tr` aynı kodu kullanır (H-8).
- **V-5. Container profili.** Geliştirme `colima-factory` profilinde yürür. Bu profilde daha çok bellek var.

## Açık kararlar ve çelişkiler

Ajan bu maddeleri kendiliğinden kapatmaz. Etkilenen işi raporda yazar.

- **A-1. Keycloak'ın tam sunucu adı.** Ad `atonota.net` mi olacak, yoksa `id.atonota.net` gibi bir alt ad mı? Kararı proje sahibi verir. DNS değerini DevOps sorumlusu hazırlar. Alan adının kayıt yeri doğrulanmadı.
- **A-2. Platformun alan adı.** Karar sitesi `<marka>.com.tr` yazar. Marka henüz belli değil. Kod bu adı ayardan alır.
- **A-3. Kiracıdaki kullanıcı türü.** Karar sitesi G-57'de “System User” der. Karar 10 “Website User” der. Karar 10 uygulanır. Frappe 16'da Website User'ın API ile çalışabildiği kaynak kodda doğrulanmalı.
- **A-4. Giriş temasının yapım yolu.** G-80 Keycloakify ister. Panelin tasarım tokenları henüz yok. Tema işi başlamadan proje sahibine sorulur.
- **A-5. Oturum süreleri.** G-78 30 dakika boşta kalma ve 12 saat toplam süre der. Karar 19 mobil için daha uzun süreler seçti. Web realm'i G-78 ile kurulur. Mobil iş başlayınca süreler istemciye göre ayrılır.
- **A-6. Sihirli bağlantı ve Apple ile giriş.** Keycloak bu iki yolu hazır sunmaz. Eklenti T-2 değerlendirmesi ve proje kararı ister (K-38).
- **A-7. Press'te uygulama kaynağı.** Press uygulamayı deponun kökünde bekleyebilir. Bu bilgi doğrulanmadı. Doğruysa `backend/apps/` yapısı dağıtımda ayrı depo ister.
- **A-8. `press_tr` lisansı.** Press AGPL-3.0 lisanslıdır. `press_tr` Press'i kullanır. Lisans etkisini hukuk değerlendirir (K-1).
- **A-9. Gerçek veri.** Türkiye'deki kişilerin verisi güvence kurulmadan Hetzner'e konmaz (Karar 27). Bu tur yalnız yerel ortamda ve örnek veriyle yürür.
- **A-11. Press'in Frappe 16 desteği.** Karar sitesinin K1 kararı Press'i Frappe 15 üzerinde kurar. D-7 bunu değiştirir. Press v0.154.1 Frappe 16 ve Python 3.14 üzerinde yalnız yamalarla açılır. Ansible ve sunucu kurma bu sürümde çalışmaz. Üretimde Press'in hangi sürümle çalışacağı ayrı karardır.
- **A-12. Model sağlayıcısı.** Karar sitesinin K9 kararı Claude Agent SDK'yı ve Claude modellerini adıyla seçer. D-9 sağlayıcıdan bağımsızlık ister. Backend bu yüzden hiçbir sağlayıcıya bağlanmaz. Ajan servisinin sağlayıcı seçimi Rail 5 işinde ayrıca karara bağlanır.
- **A-10. Eşitleme olaylarının kaynağı.** Zamanlanmış yoklama yasaktır (D-6). Keycloak olay eklentisi T-2 değerlendirmesi ister.

## Kişisel veri

Bu turda gerçek kişisel veri yoktur. Kullanıcı tablosu e-posta, ad ve Keycloak kimliği taşır. Saklama süresi ve silme yolu MVP yayınından önce yazılır (G-15).

## Teknik borç

Kod dışı borç bu bölüme yazılır. Her satırda eksik, etki, sorumlu ve kapanma koşulu bulunur.

| Borç | Etki | Sorumlu | Kapanma koşulu |
| --- | --- | --- | --- |
| Henüz yok | Yok | Yok | Yok |
