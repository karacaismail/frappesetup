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

- Sihirli bağlantı için `sky-cloak/keycloak-magic-link` v0.3.0 seçildi.
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

## Kurulum

- `backend/identity/keycloak/Dockerfile` iki jar dosyasını `/opt/keycloak/providers/` klasörüne ekler. Özetler sabittir.
- Realm'in tarayıcı akışı `atonota-browser` adını taşır. Kullanıcı önce parola ve passkey ekranını görür. “Başka yol dene” bağlantısı sihirli bağlantıyı açar.
- Sihirli bağlantı ömrü 300 saniyedir. Bu süre realm'in e-posta eylem bağlantılarıyla aynıdır. Kullanıcı kendiliğinden açılmaz. Bir IP dakikada 20, bir e-posta dakikada 3 bağlantı isteyebilir.
- Apple sağlayıcısı realm'de kapalı durur. Anahtarlar `.env` dosyasındaki yer tutuculardan gelir. Gerçek anahtar yoktur.

## Geri dönüş

- Eklentiyi kaldırmak için Dockerfile'daki `ADD` satırı silinir ve realm akışındaki ilgili yürütme çıkarılır.
- Sihirli bağlantı kapatılırsa kullanıcı yalnız parola ve passkey ile girer. Veri kaybı olmaz.
- Apple sağlayıcısı kapatılırsa Apple ile açılmış hesaplar kalır. Bu kullanıcılar parola sıfırlama ile girer.

## Lisans etkisi

İki eklenti de Apache-2.0'dır. Keycloak imajına eklenir. `platform_core` koduna karışmaz. MIT lisanslı kodumuzu etkilemez.
