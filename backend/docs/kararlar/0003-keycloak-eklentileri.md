# 0003. Keycloak eklentileri: sihirli bağlantı ve Apple ile giriş

Bu not T-2 kuralına göre yazıldı. Karar 22 Kasım 2026 Pazar günü kimlik-realm işinde alındı. Proje sahibi kararı ajana bıraktı (Proje kaydı D-10 ve O-6).

## İhtiyaç

Proje sahibi iki giriş yolunu MVP'ye aldı (O-6). Birincisi sihirli bağlantıdır. Kullanıcı e-postasına gelen bağlantıya tıklar ve parola yazmadan girer. İkincisi Apple ile giriştir. Keycloak 26.8.2 bu iki yolu hazır sunmaz. Eklenti gerekir. Eklentinin lisansı Apache-2.0 ya da MIT olmalıdır.

## Seçenekler

### Sihirli bağlantı

| Eklenti | Lisans | Son sürüm | Son değişiklik | Keycloak 26 uyumu | Not |
| --- | --- | --- | --- | --- | --- |
| `sky-cloak/keycloak-magic-link` | Apache-2.0 | v0.3.0, 20 Haziran 2026 | 13 Eylül 2026 | Keycloak 25 ve 26. Her gönderimde 25.0.6, 26.0.7 ve 26.6.x ile sınanır. | Bağlantı tek kullanımlık ve kısa ömürlü. Aynı tarayıcı koşulu var. Hız sınırı var. Hesap varlığını açığa vermez. Yönetici ucu da var. |
| `cloudflightio/keycloak-magic-link` | Apache-2.0 | Yayın yok | 4 Haziran 2025 | Belirtilmemiş | Tek kullanımlık anahtar rastgele UUID. Bir yıldan uzun süredir değişmedi. |
| `p2-inc/keycloak-magic-link` (Phase Two) | Elastic License 2.0 | v0.94 | 16 Kasım 2026 | Keycloak 26 | Lisans açık kaynak değildir. Elenir. |

### Apple ile giriş

| Eklenti | Lisans | Son sürüm | Son değişiklik | Keycloak 26 uyumu | Not |
| --- | --- | --- | --- | --- | --- |
| `klausbetz/apple-identity-provider-keycloak` | Apache-2.0 | 1.17.0, 15 Ocak 2026 | 18 Ocak 2026 | Uyum tablosu: Keycloak 26.5 ve sonrası için 1.17.0 ve sonrası | Tarayıcı girişi ve token exchange. Apple'ın POST dönüşünü ve `.p8` anahtarıyla imzalı istemci sırrını yönetir. Keycloak'ın eklenti sayfasında listelidir. |
| `BenjaminFavre/keycloak-apple-social-identity-provider` | Apache-2.0 | v1.0.2, 29 Ekim 2020 | 9 Mart 2023 | Yok | Bakımı durmuş. Elenir. |

## Karar

- Sihirli bağlantı için `sky-cloak/keycloak-magic-link` v0.3.0 seçilmişti. Güvenlik incelemesi sonrası MVP'den çıkarıldı. Ayrıntı aşağıdaki durum bölümündedir.
- Apple ile giriş için `klausbetz/apple-identity-provider-keycloak` 1.17.0 seçildi.

### Gerekçe

1. İkisi de Apache-2.0 lisanslıdır. Phase Two eklentisi Elastic License taşır ve elenir.
2. İkisi de bakımlıdır ve Keycloak 26 serisini hedefler. Cloudflight eklentisinin yayını yok ve bir yıldır değişmedi. BenjaminFavre eklentisi 2023'ten beri değişmedi.
3. Skycloak eklentisi güvenlik varsayılanlarını doğru kurar. Bağlantı tek kullanımlık ve kısa ömürlüdür. Bağlantı yalnız isteyen tarayıcıda çalışır. E-posta tarayıcıları bağlantıyı tüketemez. Hız sınırı vardır. Hesap varlığı açığa çıkmaz. Bunlar G-78 ve G-144 ile uyumludur.
4. İki eklenti de tek bir jar dosyasıdır. Ek servis gerekmez. Jar dosyaları imaja sürüm ve SHA-256 özetiyle eklenir.

## Sürüm uyumu

- Keycloak sürümü 26.8.2'dir. Skycloak eklentisi 26.6.x ile sınandı. 26.8.2 ile çalıştığı bu işin canlı testleriyle gösterildi.
- Apple eklentisinin tablosu 26.5 ve sonrası için 1.17.0 der. Eklentinin yüklendiği canlı testle gösterildi. Gerçek Apple girişi denenmedi, çünkü Apple geliştirici anahtarı yok.

## Güvenlik ve bilinen açıklar

- İki eklenti de Keycloak'ın iç arayüzlerini kullanır. Keycloak yükseltmesinde eklenti uyumu yeniden sınanır. Bu, teknik borç tablosuna girer.
- Skycloak eklentisinin yönetici ucu (`/realms/platform/skycloak-magic-link`) `manage-users` rolü ister. Bu uç hesaba giriş vermekle eşdeğerdir. Bu turda hiçbir servis bu ucu çağırmaz.
- İki depoda da yayımlanmış bir güvenlik açığı kaydı bulunmadı (GitHub Security Advisories, 22 Kasım 2026).

## Durum: sihirli bağlantı eklentisi MVP'den çıkarıldı (22 Kasım 2026, ikinci güvenlik incelemesi)

Bağımsız güvenlik incelemesi iki engelleyici buldu. Orkestratör eklentiyi MVP'den tamamen çıkardı.

- E1: Eklentinin v0.3.0 sürümü bağlantıya tıklanınca tarayıcı akışının kalan adımlarını çalıştırmıyor. `MagicLinkActionTokenHandler.handleToken` doğrudan `redirectToRequiredActions` çağırıyor (119 ve 121. satırlar). İkinci doğrulama atlanıyor. Bu durum canlı testle gösterildi.
- E2: Eklentinin yönetici ucu (`/realms/platform/skycloak-magic-link`) belirtecin hedefini ve rolünü denetlemiyor. Hesabın kayıtlı rolüne bakıyor (`MagicLinkResource.java` 334 ve 346. satırlar). Kiracı hedefli bir servis belirteci ele geçirilirse bu uçla giriş bağlantısı üretilebilir.

Yapılan şudur: Dockerfile eklentiyi yüklemez. Realm'de ilgili yürütme ve ayar yoktur. Kullanıcı parola ve passkey ile girer.

### Teknik borç ve geri dönüş koşulu

Sihirli bağlantı ancak şu iki koşulu sağlayan bir sürümle geri gelir:

1. Eklenti, bağlantıdan sonra tarayıcı akışını sürdürür ya da ikinci doğrulamayı kendisi ister. Kabul testi: TOTP'li kullanıcı bağlantıdan sonra OTP formu görür. Yanlış kod reddedilir. Doğru kod girişi tamamlar.
2. Eklentinin yönetici ucu belirtecin hedefini ve belirteçteki rolü denetler. Kabul testi: kiracı hedefli servis belirteci bu uca gönderilir ve 401 ya da 403 alır.

Bugünkü kabul testi eklentinin uçlarının 404 döndüğünü gösterir: `tests/test_eklentiler.py` içindeki `test_magic_link_endpoints_are_gone`. Sorumlusu kimlik-realm işidir. Eklenti deposuna sorun kaydı açmak proje sahibinin kararıdır.

### identity-sync en az yetki

Aynı incelemenin eki: identity-sync servis hesabı yalnız `view-users` ve `query-users` rollerini taşır. `manage-users`, `manage-clients` ve `view-organizations` kaldırıldı. Canlı test bu hesabın Admin API'den kullanıcı okuyabildiğini gösterir. Aynı test kullanıcı oluşturma isteğinin 403 aldığını gösterir. identity-sync Keycloak'a yazmaz. Yazma gerekirse bu karar yeniden açılır.

### Sosyal girişte ikinci adım (O6)

Google ve Apple sağlayıcıları `postBrokerLoginFlowAlias` olarak `atonota-post-broker` akışını kullanır. Akış, kullanıcının kurulu TOTP ya da güvenlik anahtarını ister. Gerçek sosyal giriş denenmedi, çünkü sağlayıcı anahtarı yok. Akışın bağlı olduğu canlı testle gösterildi.

## Kurulum

- `backend/identity/keycloak/Dockerfile` Apple jar dosyasını `/opt/keycloak/providers/` klasörüne ekler. Özet sabittir.
- Realm'in tarayıcı akışı `atonota-browser` adını taşır. Kullanıcı parola ve passkey ekranını görür.
- Apple sağlayıcısı realm'de kapalı durur. Anahtarlar `.env` dosyasındaki yer tutuculardan gelir. Gerçek anahtar yoktur.

## Geri dönüş

- Eklentiyi kaldırmak için Dockerfile'daki `ADD` satırı silinir ve realm akışındaki ilgili yürütme çıkarılır.
- Sihirli bağlantı kapatılırsa kullanıcı yalnız parola ve passkey ile girer. Veri kaybı olmaz.
- Apple sağlayıcısı kapatılırsa Apple ile açılmış hesaplar kalır. Bu kullanıcılar parola sıfırlama ile girer.

## Lisans etkisi

İki eklenti de Apache-2.0'dır. Keycloak imajına eklenir. `platform_core` koduna karışmaz. MIT lisanslı kodumuzu etkilemez.
