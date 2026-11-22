# Yaygın parola listesi

`common-passwords.txt` dosyası Keycloak'ın `passwordBlacklist` politikasına girer. Keycloak bu klasörü `/opt/keycloak/data/password-blacklists/` yoluna bağlı okur.

## Kaynak

- Liste SecLists deposundaki `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt` dosyasından alındı.
- Depo adresi <https://github.com/danielmiessler/SecLists> şeklindedir.
- Listenin lisansı MIT'dir.
- Liste 19 Kasım 2025 tarihli `1a7bb9127eca9e6ff2fc0301c597fe6e16a0cb56` numaralı commit'ten alındı.

## Süzme

Realm parola politikası en az 12 karakter ister. Bu yüzden listeden yalnız 12 ve daha uzun satırlar alındı. Kısa satırlar zaten uzunluk kuralına takılır. Süzme sonunda liste 1.212 satırdı.

Depo herkese açıktır. Bu yüzden e-posta biçimli 7 satır listeden çıkarıldı. Bu satırlarda `@` işaretinden sonra bir alan adı vardı. Örneğin `ad@ornek.test` böyle bir satırdır. Kalan liste 1.205 satırdır. Gözden geçirilmiş listenin SHA-256 özeti `8a89ad7eac1c6277d7cafe5eb5925949f1b54016288436a1efb5c73eb3b02c49` değeridir. Liste değişirse bu özeti de güncelleyin. Dosya UTF-8 ve Unix satır sonu kullanır. Keycloak büyük ve küçük harfi ayırmadan karşılaştırır.

Listeyi yenilemek için aynı kaynağı indirin. Sonra 12 karakterden kısa satırları atın. E-posta biçimli satırları da atın. `backend/identity/keycloak/tests/test_realm_files.py` testi bu satırları yakalar.
