# Oturum ve rol testlerinin devri

AJA-72 mevcut kodun testlerini tamamlar. Bu iş dört gereksinimi bütünüyle kapatmaz.
Sistem mimarı kapsamı AJA-163 görevinde doğruladı. Karar O-57 olarak kaydedildi.
A Takımı PO kalan işleri AJA-165 görevinde ayırır.

## G-43: Oturum ve parola kuralları

Yeni dosya `apps/platform_core/platform_core/identity/tests/test_session_boundary_contract.py` yolundadır.
Üç test gerçek Frappe istek yolunu kullanır. Kimlik sağlayıcının yanıtı testte taklit edilir.

- Oturum, 3599 saniye boşta kalınca açık kalır.
- Oturum, tam 3600 saniye boşta kalınca sona erer.
- Ek yetki başlığı, süresi dolan çerezi geçerli kılamaz.
- Süresi dolan oturum, kayıttan silinir. İstek 401 koduyla reddedilir.

O-25 kararı bir saat sınırını belirler. Sitedeki eski on iki saat değeri uygulanmaz.
Keycloak süreleri `identity/keycloak/tests/test_session_lifetimes.py` dosyasında sınanır.
Başarısız giriş sınırı `identity/keycloak/tests/test_realm_files.py` dosyasında sınanır.

Frappe parola ve başarısız giriş ayarlarını kuran kod yoktur.
Bu yüzden G-43 açık kalır. Acil yönetici hesabının parola kuralları ayrıca uygulanmalıdır.
Gerçek Keycloak giriş denemeleri bu teslimde çalıştırılmadı.

## G-53: Kiracı yöneticisinin sınırları

Yeni dosya `apps/platform_core/platform_core/access/tests/test_identity_role_denials.py` yolundadır.
Test kullanıcısı `Website User` türündedir. Bu tür, uygulama kullanıcısını belirtir.

- Kullanıcı oturum ayarını değiştiremez. Ayar önceki değerini korur.
- Kullanıcı operatör hesabının rollerini değiştiremez. Hesap aynı kalır.
- Kullanıcı standart yönetici rolünü kapatamaz. Rol aynı kalır.

`Tenant Admin` rolü kaynakta yoktur. Bu testler kiracı yöneticisinin kabul testi değildir.
Korunan bütün ayarlar ve yönetim ekranının yönlendirmesi henüz doğrulanmadı.
Sunucu yönlendirmesi sonraki işte sınanmalıdır.
Yalnız arayüz gerektiren bölüm kapsam dışı: `atonota-web`.
G-53 açık kalır.

## G-62: Rol ve yetki yönetimi

Yeni dosya `apps/platform_core/platform_core/access/tests/test_identity_role_denials.py` yolundadır.
Yetkisiz izin verme çağrısı 403 koduyla reddedilir.
Test, ret sonrasında izin tablosunun aynı kaldığını da denetler.
Standart rol ve operatör hesabı için ret testleri de bu dosyadadır.

Sınırlı kiracı yöneticisi uçları yoktur. İzinli rol yönetimi bu yüzden sınanamadı.
Rol değişikliğinin günlüğe yazılması da bu teslimde doğrulanmadı.
PO rol yönetimini ayrı özellik olarak ayırmalıdır. G-62 açık kalır.

## G-121: Her veri yolunda aynı yetki

Yeni dosya `apps/platform_core/platform_core/access/tests/test_identity_role_denials.py` yolundadır.
Üç test, oturum açmış fakat kayıt türüne yetkisi olmayan kullanıcıyı kullanır.

1. Liste çağrısı 403 koduyla reddedilir.
2. Rapor çağrısı 403 koduyla reddedilir.
3. Dışa aktarma çağrısı 403 koduyla reddedilir.

Yanıtlar kayıt verisi içermez. Dışa aktarma yanıtı dosya eki içermez.
İstekler Frappe'nin gerçek istek dağıtıcısından geçer. Yetki denetimi taklit edilmez.

Arama, dosya, arka plan işi ve yapay zekâ yolları bu yeni testlerin dışında kaldı.
Bu yolların birleşik kabul denemesi ayrıca gerekir. G-121 bütünüyle kapanmadı.

## Doğrulama sınırı

Kanıt yalnız yerel test ortamına aittir. Çalışan 7400 yığını değiştirilmedi.
Test ortamı `fs-aja72` adlı ayrı Colima projesidir. Dışarıya açık portu yoktur.
Test verileri uydurmadır. Zamanlanmış iş kurulmadı.

Paket Python 3.14 ister. Frappe sürüm aralığı `>=16.56.0,<17.0.0` değeridir.
Yerel ortamda Python 3.14.10 ve Frappe 16.56.0 gözlendi.
ERPNext sürümü 16.55.0 olarak gözlendi. Bu üç sürüm ürünün bütün ortamlarını kanıtlamaz.

Yeni ürün davranışı eklenmedi. Bu yüzden önce düşen yeni davranış testi uygulanmaz.
QA, kabul ölçütlerine göre denetim yapan ekip üyesidir.
Bağımsız QA incelemesi ayrı görevde yapılacaktır.
Gerçek okurla denenmedi.

## Yerel kontrol sonuçları

Kontroller dalın çalışma klasöründe çalıştırıldı. Kontroller ortak kilitle sıraya alındı.
Dal `pc/p1-identity-tests-roles` adını taşır.

| Kontrol | Sonuç |
| --- | --- |
| `backend/dev/bin/module-boundaries` | `pass`. İhlal yok. |
| `UV_OFFLINE=1 backend/dev/bin/security-audit` | `pass`. |
| `backend/dev/bin/ai-readiness` | `pass`. Var olan uyarılar korundu. |
| `~/.local/bin/python3.14 -B -m unittest discover -s backend/dev/tests` | `pass`. 102 test çalıştı. İki test atlandı. |
| `~/.local/bin/python3.14 -B -m unittest discover -s backend/dev/naming/tests` | `pass`. 68 test çalıştı. |
| Yeni yetki testleri | `pass`. Yedi test çalıştı. |
| Yeni oturum testleri | `pass`. Üç test çalıştı. |
| Keycloak dosya testleri | `pass`. 28 test çalıştı. |
| Değişen Python dosyalarında Ruff | `pass`. Kod ve biçim denetimi geçti. |
| Türkçe yazım denetimi | `pass`. İki Markdown dosyası denetlendi. |
| Gerçek Keycloak girişleri, tarayıcı ve CI | `not_run`. CI, depodaki otomatik kontrol ortamıdır. |

Yeni testler şu komutlarla çalıştırıldı:

```bash
docker --context colima-factory exec fs-aja72-runner-1 \
  bench --site test-aja72.localhost run-tests \
  --module platform_core.access.tests.test_identity_role_denials

docker --context colima-factory exec fs-aja72-runner-1 \
  bench --site test-aja72.localhost run-tests \
  --module platform_core.identity.tests.test_session_boundary_contract

PYTHONPATH=backend/identity/keycloak/tests ~/.local/bin/python3.14 -B -m unittest \
  test_realm_files.RealmFileTest test_session_lifetimes.SessionLifetimeFileTest
```

İlk çalıştırmada iki test beklentisi düzeltildi. Ürün kodu değişmedi.
Frappe v2, hata türünü `errors[].type` alanında verir.
Kaynak `frappe/utils/response.py` dosyasının 54. satırıdır.
Oturum tablosunda `name` alanı yoktur. Test artık oturum satırlarını sayar.
Test, denemeden önce bir oturum bulunduğunu da doğrular.
Silme yolu `frappe/sessions.py` dosyasının 82. satırında başlar.
Bu kaynaklar yerel Frappe 16.56.0 kurulumundan okundu.

Yazım denetimindeki uzun kelime uyarıları elle incelendi.
Yeni açıklama cümleleri 15 kelime sınırını korur.
Proje kaydındaki eski uyarılar bu işte değiştirilmedi.
