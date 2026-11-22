# Karar notu 0013: kiracı sitesinde hesap silme

Tarih: 22 Kasım 2026 Pazar. Sahibi: platform-core-kimlik işi. Orkestratör birleştirmede gözden geçirir.

## İhtiyaç

Müşteri kendi hesabını silebilir (Proje kaydı O-27). Hesap silme akışını identity-sync yürütür. Akışın 4. adımı kiracı sitesindeki kullanıcıyı kapatır. Aynı adım kişiyi gösteren alanları anonim yapar. İş kayıtları silinmez.

Uç `platform_core.api.identity.anonymize_user` olur. Yalnız `azp=identity-sync` servis belirteci çağırabilir.

## Frappe 16'nın hazır yolu

Frappe 16'da “Personal Data Deletion Request” adlı bir DocType var. Kaynak dosya `frappe/website/doctype/personal_data_deletion_request/personal_data_deletion_request.py` yolundadır. Dosyada iki parça vardır.

1. **Anonimleştirme motoru.** `_anonymize_data` yöntemi (satır 260) `user_data_fields` kancasını okur. Her kurulu uygulama bu kancaya kendi kişi alanlarını yazar. Frappe ve ERPNext bu kancayı doldurur. Motor alanları değiştirir, kayıtları silmez. Sonunda kullanıcının adını `deleted-user-<sıra>@<site>` yapar.
2. **İstek yaşam döngüsü.** Kayıt açılınca kullanıcıya onay e-postası gider (satır 67). Sonra bir “System Manager” onay verir (satır 118). İş uzun kuyruğa gönderilir (satır 132). İş bitince eski adrese yine e-posta gider (satır 142). Otomatik işleme `scheduler_events` kancasıyla çalışır (`frappe/hooks.py:282`).

## Seçim

Motor ve kanca kullanılır. Yaşam döngüsü kullanılmaz.

| Parça | Kullanılır mı | Neden |
| --- | --- | --- |
| `user_data_fields` kancası | Evet | Her uygulama kendi kişi alanlarını kendisi bildirir. HRMS TR da aynı kancaya yazar. |
| `_anonymize_data` motoru | Evet | Frappe'nin kendi kuralıyla alanları değiştirir ve kullanıcının adını çevirir. |
| Kaydın kendisi | Evet | İşin izini tutar. Durumu “Deleted” olur. |
| Onay e-postası | Hayır | Onayı identity-sync aldı. E-posta adresi yeniden “Email Queue” içine girerdi. |
| Yönetici onayı | Hayır | Servis çağrısı insan onayı bekleyemez. |
| Kuyruk | Hayır | identity-sync adımın bittiğini yanıttan bilmelidir. İş istek içinde çalışır. |
| Zamanlanmış işleme | Hayır | Proje zamanlanmış iş kurmaz. |

Uygulama şöyledir:

1. Uç bağ `(issuer, subject)` ile kullanıcıyı bulur. `Administrator` ve `Guest` 409 alır.
2. Uç kullanıcıyı kapatır. Frappe bütün oturumları kapatır (`frappe/core/doctype/user/user.py:362`).
3. Uç kaydı `db_insert` ile yazar. Böylece `after_insert` çalışmaz ve e-posta gitmez.
4. Uç `_anonymize_data` yöntemini aynı istekte çağırır.
5. Motor kayıtta özgün e-postayı bırakır. Uç bu alanı anonim adla değiştirir.
6. Kimlik bağı kalır ve anonim kullanıcıyı gösterir. Aynı istek ikinci kez gelince uç aynı gövdeyi döner.

## Bilinen sınırlar ve geri dönüş

- `_anonymize_data` alt çizgili bir yöntemdir. Frappe bu yöntemi değiştirebilir. Testler bu durumda başarısız olur. O zaman uç motoru kendi koduyla yazar.
- Motor her eşleşen “Contact” kaydını aynı anonim ada çevirir. Aynı e-postayla iki kişi kaydı varsa iş 417 ile durur. Fazla kayıt elle birleştirilir, sonra istek yinelenir.
- Telefon kurulumları bu uçla kapanmaz. Onları `platform_core.api.mobile.revoke_user_installations` ucu kapatır.
- Kişi alanı taşıyan her yeni DocType `user_data_fields` kancasına girmelidir. Girmezse alan anonim olmaz.
- Geri dönüş: Uç kaldırılır. Silme adımı elle “Personal Data Deletion Request” ekranından yürütülür.
