---
title: "AtonotA Login ile güvenle giriş yapın"
nav: "AtonotA Login tanıtımı"
order: 29
---

Bu sayfa AtonotA Login ürününü tanıtır. Sayfa bir taslaktır. Ürün sahibi metni henüz onaylamadı. Ürün canlıda değildir. Ürünün ayrıntıları [AtonotA Login](/frappesetup/atonota-login/) sayfasındadır.

Sayfada fiyat yazmaz. Fiyat kararı açıktır. Bu kararın gereksinimi G-166'dır.

## Kısa tanıtım

AtonotA Login bir giriş ürünüdür. Ürün Keycloak üzerine kurulur. Keycloak, açık kaynaklı bir giriş sistemidir. Ürünün kendi kodu da açık kaynaktır. Bu kuralın gereksinimi G-157'dir.

## Değer önerileri

Ürün size şu yedi şeyi sunacak. Her önerinin yanında gereksinim kimliği vardır. Ürün canlıda olmadığı için bugün hiçbiri kullanıma açık değildir. Önerilerin bugünkü durumu sonraki bölümdedir.

1. **Bildiğiniz hesapla girersiniz.** Google, Apple ve LinkedIn ile giriş yapabilirsiniz (G-159).
2. **Başkası sizin adınıza hesap açamaz.** E-posta adresi tek başına hesap bağlamaz (G-160).
3. **Şirketiniz kendi girişini zorunlu kılabilir.** O zaman çalışan sosyal hesapla giremez (G-160).
4. **Parola yazmadan girebilirsiniz.** E-postanıza tek kullanımlık bir bağlantı gelir (G-162).
5. **Girişe ikinci bir adım ekleyebilirsiniz.** Örneğin geçiş anahtarı ya da telefondaki kod kullanılır (G-163).
6. **Her işlem ayrıca denetlenir.** Giriş yapmak her işleme izin vermez (G-161).
7. **Eksik kural işlemi açmaz.** Bir kuralın değeri boşsa sistem işlemi durdurur (G-167).

## Bugün ne durumda?

Bu bölüm 24 Kasım 2026 Salı günkü durumu yazar. Durumlar [görev panosundaki](/frappesetup/gereksinimler/) durumlarla aynıdır. Hiçbir özellik canlı sunucuda denenmedi.

### Bitti

Bu satırların kodu ve testi vardır. Testler yalnız yerel yığında geçti.

| Özellik | Kimlik | Commit | Kanıt dosyası |
| --- | --- | --- | --- |
| Ürün sınırı ve iki ayrı lisans | G-157 | `18a9fff8` | `backend/identity/atonota_login/tests/test_product_boundary.py` |
| Giriş ekranı ve e-postalar ürünün adını gösterir | G-157 | `18a9fff8` | `backend/identity/keycloak/themes/atonota/test/tests/brand.spec.ts` |

### Kodu yazıldı, iş sürüyor

Bu satırların kodu yazıldı ve yerel testten geçti. Ama her kalemde kalan bir iş vardır. Kalan iş [AtonotA Login](/frappesetup/atonota-login/) sayfasının sonundadır.

| Özellik | Kimlik | Commit | Kanıt dosyası |
| --- | --- | --- | --- |
| Platform listesi veri dosyasından gelir | G-159 | `cbf87c05` | `backend/identity/atonota_login/tests/test_platforms.py` |
| Platform kayıtları Keycloak'a aynı biçimde yazılır | G-159 | `b2819fdd` | `backend/identity/atonota_login/tests/test_keycloak_apply.py` |
| E-posta eşleşmesi tek başına bağ kurmaz | G-160 | `cbf87c05` | `backend/identity/atonota_login/tests/test_linking_rule.py` |
| Şirket giriş sağlayıcısı ve istisna kaydı | G-160 | `7ada5369` | `backend/identity/atonota_login/tests/test_enterprise_apply.py` |
| Her işlem ayrı karar alır | G-161 | `cbf87c05` | `backend/identity/atonota_login/tests/test_decision.py` |
| İşlem kararı Frappe ucunda verilir | G-161 | `b0442397` | `backend/apps/platform_core/platform_core/api/test_atonota_login.py` |
| E-posta bağlantısı tek kullanımlıktır | G-162 | `837963eb` | `backend/identity/keycloak/tests/test_magic_link.py` |
| Giriş akışında ikinci adım vardır | G-163 | `1e15299e` | `backend/identity/keycloak/themes/atonota/test/tests/flow.spec.ts` |
| İmzası geçersiz doğrulama bildirimi reddedilir | G-164 | `cbf87c05` | `backend/identity/atonota_login/tests/test_verification_inbox.py` |
| Fiyat kuralı boşsa ücretli plan açılmaz | G-166 | `fb39c6e2` | `backend/identity/atonota_login/tests/test_paid_plan_gate.py` |
| Kural boşsa sonuç "yapılandırma gerekiyor" olur | G-167 | `fb39c6e2` | `backend/identity/atonota_login/tests/test_paid_plan_gate.py` |

Commit, test dosyasını depoya ekleyen commit'tir. Sonraki commit'ler testi değiştirmiş olabilir.

### Yakında

Bu özellikler yapılmadı. Ürün bunları bugün sunmaz.

| Özellik | Kimlik | Neden henüz yok? |
| --- | --- | --- |
| `api.login.atonota.net` adresinden giriş | G-158 | DNS kaydı ve canlı adres denemesi yapılmadı. |
| Facebook ve X ile giriş | G-159 | Bu iki platform e-postanın doğrulandığını bildirmez. Ek denetim yazılmadı. |
| Gerçek platform hesapları | G-159 | DevOps sorumlusu platform panellerinde istemci açmadı. |
| Şirket alan adının DNS ile denetlenmesi | G-160 | Bu kod yazılmadı. |
| Herkese aynı yanıt ve ekranda ayrı onay | G-162 | Bu iki davranış denenmedi. |
| Hesap kurtarma, cihazı unutma ve çıkış kapsamı | G-163 | Bu akışlar yapılmadı. |
| Belge ve yüz ile kimlik doğrulama | G-164 | Sağlayıcı seçilmedi. Doğrulamayı başlatan kod yoktur. |
| Ücretli plan | G-166 | Fiyat kararı açıktır. |
| Bu sayfanın yayımlanması | G-165 | Ürün sahibi metni onaylamadı. |

## Sayfa ölçüm yapmaz

Bu sayfa oturum istemez. Sayfa yüklenince ölçüm satıcısına istek gitmez. Sayfa yalnız kendi sitesinden dosya indirir. Bunu bir ağ testi denetler. Rıza kuralının gereksinimi G-134'tür.
