# Kimlik, rol ve parola işlerinin devri

Bu belge AJA-167 görevinin kapsamını ve kalan işleri açıklar.
AJA-163 kararı, bu işi mevcut davranışların testleriyle sınırlar.
A Takımı PO, kalan ürün işlerini AJA-165 üzerinden ayırmalıdır.

G-43, G-53 ve G-62 açık kalır.
Görev panosunda üç gereksinimin durumu `in-progress` değerindedir.
Bu değer, işin sürdüğünü belirtir.

## Mevcut testler

HTTP, tarayıcı ile sunucu arasındaki istek biçimidir.
Testler Frappe'nin gerçek HTTP istek yolunu kullanır.
Keycloak, kimlik doğrulama hizmetidir. Testler Keycloak yanıtını taklit eder.
Bu testler gerçek Keycloak sunucusuyla giriş yapıldığını kanıtlamaz.

`apps/platform_core/platform_core/identity/tests/test_login_policy.py` dosyasına iki test eklendi:

1. Parolayla giriş kapalıyken sunucu geçerli bilgileri de reddetmelidir.
   Test `/api/method/login` ve `cmd=login` yollarını kapsar.
   Yanıt 401 olmalıdır. API yolunda hata türü `AuthenticationError` olmalıdır.
   Kök yol genel bir HTML hata sayfası döner. Bu sayfada hata türü yazmaz.
   Kullanıcı misafir kalmalıdır. Sunucu yeni oturum kaydı oluşturmamalıdır.
2. Yetkisiz uygulama kullanıcısı `/desk` ve `/app` sayfalarını açamamalıdır.
   Yanıt 403 olmalıdır. Kullanıcının mevcut oturumu açık kalmalıdır.
   Kullanıcı türü ve roller değişmemelidir.

Oturum sınırı testleri mevcut `test_session_boundary_contract.py` dosyasında korunmuştur.
Dosya `apps/platform_core/platform_core/identity/tests/` klasöründedir.

- Kullanıcı 3599 saniye boşta kalınca oturum açık kalır.
- Kullanıcı tam 3600 saniye boşta kalınca oturum silinir.
- Ek yetki başlığı, süresi dolan oturumu uzatamaz.

Bu üç test AJA-167 doğrulamasında yeniden çalıştı ve geçti.
Önceki sonuçların ayrıntıları [önceki devir belgesindedir](identity-role-test-gaps.md).

## G-43: Parola ve başarısız giriş ayarları

`session_policy.py`, yalnız `session_expiry` ayarını yazar.
Dosya `apps/platform_core/platform_core/identity/` klasöründedir.
O-25 kararı, boşta kalan oturum için bir saat sınırı belirler.
Gereksinim metnindeki eski `12:00` değeri bu testin beklentisi değildir.

Frappe parola ayarlarını uygulayan kurulum kodu yoktur.
Başarısız giriş ayarlarını uygulayan kurulum kodu da yoktur.
Parolayla girişin reddedilmesi, bu ayarların uygulandığını kanıtlamaz.

G-43 kaydı şu değerleri ister:

| Ayar | İstenen değer |
| --- | --- |
| `enable_password_policy` | `1` |
| `minimum_password_score` | `3` |
| `allow_consecutive_login_attempts` | `5` |
| `allow_login_after_fail` | `300` |
| `logout_on_password_reset` | `1` |
| `reset_password_link_expiry_duration` | `900` |
| `password_reset_limit` | `3` |
| `document_share_key_expiry` | `7` |

Tablo, gereksinimdeki ham ayar değerlerini korur.
Bu görev ayarları değiştirmez.
Frappe parola kuralları yönetici ve acil erişim hesapları içindir.

Sonraki işte A Takımı PO, ayarların uygulanmasını ayrı göreve vermelidir.
Geliştirici, kurulu Frappe sürümünde alanları ve birimlerini doğrulamalıdır.
Geliştirici kurulum davranışını ve tekrar çalıştırma sonucunu test etmelidir.
QA, parola reddini ve başarısız giriş sınırını ayrı denemelidir.
QA, parola sıfırlanınca oturumların kapanmasını da denemelidir.
Keycloak oturumlarıyla gerçek uyum ayrıca doğrulanmalıdır.

## G-53: Kiracı yöneticisinin sınırları

Kiracı, platformu kullanan ayrı müşteri kuruluşudur.
`Tenant Admin`, planlanan kiracı yöneticisi rolünün adıdır.
Bu rol kaynakta yoktur.
`apps/platform_core/platform_core/fixtures/role.json` yalnız `PLT AI Manager` rolünü içerir.

Mevcut ret testleri `Website User` türündeki uygulama kullanıcısını sınar.
Bu testler kiracı yöneticisinin bütün sınırlarını kanıtlamaz.
Mevcut 403 yanıtı, planlanan uygulama sayfasına yönlendirme davranışını da kanıtlamaz.

G-53 için şu parçalar eksiktir:

- Kiracı yöneticisinin izin verilen işleri tanımlanmalıdır.
- `System Manager` rolünün yalnız platform işletmecisinde kaldığı doğrulanmalıdır.
- `System Settings`, `Social Login Key` ve `Email Account` kayıtları korunmalıdır.
- Yönetim ekranına erişim ve uygulamaya yönlendirme kuralları uygulanmalıdır.
- Başlangıç ekranı ve yönetim bildirimleri gereksinime göre ayarlanmalıdır.

Sonraki işte A Takımı PO, bu parçaları ayrı kabul ölçütleriyle vermelidir.
Geliştirici izinli yönetim işlemlerini ve korunan kayıtların reddini birlikte test etmelidir.
QA, kiracı yöneticisini ve platform işletmecisini ayrı hesaplarla denemelidir.

## G-62: Rol ve yetki yönetimi

API ucu, programın sunucuya işlem isteği gönderdiği adrestir.
`platform_core`, rol yönetimi için gereken sınırlı uçları sunmaz.
Rol, Role Profile ve DocPerm yönetimi bu nedenle açık kalır.
Role Profile, birlikte verilen rol grubudur. DocPerm, kayıt türünün izin tanımıdır.

G-62 için sonraki iş şu parçaları kapsamalıdır:

1. Geliştirici yalnız uygulamaya ait özel rollerin yönetimini açmalıdır.
2. Geliştirici rol gruplarını ve kayıt izinlerini sınırlı uçlarla yönetmelidir.
3. Geliştirici kullanıcı izinleri ve erişim kuralları için yönetim kapsamını tamamlamalıdır.
4. Geliştirici standart rolleri ve işletmeci hesaplarını değişiklikten korumalıdır.
5. Geliştirici her değişikliği `Permission Log` adlı izin günlüğüne yazmalıdır.

`apps/platform_core/platform_core/api/access.py` içinde `explain_permission` ucu vardır.
Bu uç, izin sonucunu açıklar. Rol yönetimi sağlamaz.
İzin günlüğünü gösteren ekran ayrıca değerlendirilmelidir.

A Takımı PO, izin verilen işlemleri uygulamadan önce açıkça tanımlamalıdır.
QA hem izinli işlemi hem yetkisiz isteğin reddini sınamalıdır.
QA, ret sonrasında kayıtların değişmediğini doğrulamalıdır.
QA, işletmeci hesabına yetki yükseltme girişimini de sınamalıdır.

## Doğrulama ve sonraki adım

Doğrulama 24 Kasım 2026 Salı günü yapıldı. Yeni testler yerel test sitesinde geçti.
Ortam `fs-dev-ortam-7167` adlı ayrı Colima projesidir. Çalışan başka ortama dokunulmadı.
Test verileri uydurmadır. Zamanlanmış iş kurulmadı.

| Kontrol | Sonuç |
| --- | --- |
| `platform_core.identity.tests.test_login_policy` | `pass`. 12 test çalıştı. |
| `platform_core.identity.tests.test_session_boundary_contract` | `pass`. Üç test çalıştı. |
| `platform_core.access.tests.test_identity_role_denials` | `pass`. Yedi test çalıştı. |
| Dalın değiştirdiği üç Python dosyasında Ruff | `pass`. Kod ve biçim denetimi geçti. |
| Dal kapıları ve Playwright | `not_run`. Görev bu kapıları kapsam dışında bıraktı. |
| Gerçek Keycloak girişi ve CI | `not_run`. |

İlk koşuda bir test düştü. Kök yol yanıtı JSON değil, HTML idi.
Test yalnız API yolunda hata türünü denetleyecek biçimde düzeltildi.
Kök yolda 401 yanıtı, misafir kullanıcı ve sıfır oturum denetimi korunur.
Ürün kodu değişmedi.

Testler şu biçimde çalıştırıldı:

```bash
PANE_PORT=7167 backend/dev/bin/test platform_core --module <modül>
```

İlk komut siteyi kurdu. Sonraki modüller aynı sitede `bench run-tests` ile çalıştı.
Ortamda Python 3.14.10, Frappe 16.56.0 ve ERPNext 16.55.0 gözlendi.
Bu sürümler ürünün bütün ortamlarını kanıtlamaz.

Çalıştırılan modüller şunlardır:

```text
platform_core.identity.tests.test_login_policy
platform_core.identity.tests.test_session_boundary_contract
platform_core.access.tests.test_identity_role_denials
```

QA incelemesi AJA-75, dal incelemesi AJA-76 görevindedir.
Bu görev canlı sunucuya ve canlı veriye dokunmaz.
Gerçek okurla denenmedi.
