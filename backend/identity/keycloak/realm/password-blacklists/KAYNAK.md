# Yaygın parola listesi

`yaygin-parolalar.txt` dosyası Keycloak'ın `passwordBlacklist` politikasına girer. Keycloak bu klasörü `/opt/keycloak/data/password-blacklists/` yoluna bağlı okur.

## Kaynak

- Liste SecLists deposundaki `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt` dosyasından alındı.
- Depo adresi <https://github.com/danielmiessler/SecLists> şeklindedir.
- Listenin lisansı MIT'dir.
- Liste 19 Kasım 2025 tarihli `1a7bb9127eca9e6ff2fc0301c597fe6e16a0cb56` numaralı commit'ten alındı.

## Süzme

Realm parola politikası en az 12 karakter ister. Bu yüzden listeden yalnız 12 ve daha uzun satırlar alındı. Kısa satırlar zaten uzunluk kuralına takılır. Süzülen liste 1.212 satırdır. Dosya UTF-8 ve Unix satır sonu kullanır. Keycloak büyük ve küçük harfi ayırmadan karşılaştırır.

Listeyi yenilemek için aynı kaynağı indirin. Sonra 12 karakterden kısa satırları atın.
