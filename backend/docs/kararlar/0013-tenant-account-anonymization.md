# Karar notu 0013: kiracı sitesinde hesap silme

Platform kimlik ekibi bu kararı 22 Kasım 2026 Pazar günü yazdı. Orkestratör kararı birleştirme sırasında inceler.

## İhtiyaç

Müşteri kendi hesabını silebilir (Proje kaydı O-27). Hesap silme akışını identity-sync yürütür. Akışın 4. adımı kiracı sitesindeki kullanıcıyı kapatır. Aynı adım kişiyi gösteren alanları anonim yapar. İş kayıtları silinmez.

Uç `platform_core.api.identity.anonymize_user` olur. Yalnız `azp=identity-sync` servis belirteci çağırabilir. Kurallar `docs/sozlesmeler.md` 7. bölümdeki anonim yapma kurallarıdır.

## Frappe 16'nın hazır yolu neden kullanılmıyor

Frappe 16'da “Personal Data Deletion Request” adlı bir DocType var. Kaynak dosya `frappe/website/doctype/personal_data_deletion_request/personal_data_deletion_request.py` yolundadır.

- Kayıt açılınca kullanıcıya onay e-postası gider (satır 67).
- Bir “System Manager” onay verir (satır 118).
- İş uzun kuyruğa gönderilir (satır 132).
- Otomatik işleme `scheduler_events` kancasıyla çalışır (`frappe/hooks.py:282`). Proje zamanlanmış iş kurmaz.
- Motor bazı tablolarda tam adı bütün satırlarda arar ve değiştirir (satır 317). Aynı adı taşıyan başka bir kişinin yorumu da değişebilir. Bağımsız inceleme bunu engelleyici buldu.

Bu yüzden ne kaydın yaşam döngüsü ne de motor kullanılır. Kapsam yine Frappe'nin `user_data_fields` kancasından türer. Böylece her uygulama kendi kişi alanlarını kendisi bildirir.

## Seçim

### Silme kaydı

Yeni DocType “Platform Identity Deletion” silme kaydını tutar. Kayıt ham kimliği tutmaz. Kaydın adı `(iss, sub)` çiftinin HMAC-SHA256 özetidir. Anahtar `kimlik_deletion_hmac_key` site ayarıdır. Anahtar yoksa kimlik değiştiren uçlar 503 döner.

`provision`, `set_enabled` ve `change_email` önce bu kaydı denetler. Silinmiş kimlik 410 alır. Giriş de aynı kaydı denetler ve 403 döner.

### İki adım

1. Birinci adım kimlik bağını ve silme kaydını kilitler. Hesabı kapatır. API anahtarını, API gizlisini ve parolayı siler. Kaydı “Disabled” durumunda yazar ve commit eder. Sonra oturumları 100'lük sayfalarla kapatır.
2. İkinci adım aynı satırları yeniden kilitler. Kişisel veriyi anonim yapar. Kullanıcının adını `deleted-user-<16 onaltılık karakter>@deleted.invalid` yapar. Kimlik bağını siler, böylece ham `sub` gider. Kaydı “Anonymized” yapar.

İki adım da tekrar güvenlidir. İkinci adım yarıda keserse değişiklikleri geri alınır. Kayıt “Disabled” kalır ve yeni istek işi bitirir.

### Kilit sırası

Her yerde önce kimlik bağı, sonra silme kaydı kilitlenir. Giriş de aynı kilidi alır. Frappe oturum kaydını ekleyince commit eder (`frappe/sessions.py:301`). Bu yüzden giriş kilidi bundan sonra yeniden alır ve denetimi yineler. Silme araya girdiyse giriş kendi oturumunu kapatır.

### Kapsam

- Kapsam `user_data_fields` kancasından ve sözleşmedeki ek kayıtlardan türer. Kod `kimlik/anonymization_scope.py` dosyasındadır.
- Yalnız kullanıcıya bağlı satırlar değişir. Tam ad yalnız kullanıcının kendi satırlarında değişir.
- Bir “Contact” kaydı, bütün e-posta satırları kişinin adresiyse kişinindir. Başka bir adres de varsa kayıt ortaktır. Ortak kayıttan yalnız kişinin e-posta satırı silinir.
- Bir “Address” kaydı, bütün bağları kişinin kendi “Contact” kayıtlarına gidiyorsa kişinindir. Ortak adreste yalnız kişinin e-postası boşalır.
- Yalnız kişisel dosya silinir. Kişisel dosya, “User” kaydına ya da kişinin kendi “Contact” kaydına bağlı dosyadır. İş kaydına bağlı dosya kalır.
- E-posta alanlarında yalnız tam adres değişir. Adres listeleri tek tek ayrıştırılır.

### Modül sınırı

- Her uygulama kişi alanlarını `user_data_fields` kancasına yazar.
- Kimlik modülü yeni iş tablolarını bu kanca üzerinden öğrenir.
- `_ownership` işlevi kişisel ve ortak kayıtları ayırır.
- `test_anonymization` ve `test_python_rules` bu ayrımı sınar.

## Bilinen sınırlar ve geri dönüş

- Kişi alanı taşıyan her yeni DocType `user_data_fields` kancasına girmelidir. Girmezse alan anonim olmaz.
- Telefon kurulumları bu uçla kapanmaz. Onları `platform_core.api.mobile.revoke_user_installations` ucu kapatır.
- `kimlik_deletion_hmac_key` değeri sonradan değişirse eski kayıtlar okunamaz.
- Geri dönüş gerekirse ekip ucu kaldırır. Ekip silme adımını elle yürütür.
