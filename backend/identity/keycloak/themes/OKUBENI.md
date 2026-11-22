# Temalar

Bu klasördeki her alt klasör Keycloak imajına `/opt/keycloak/themes/` altına kopyalanır. Kopyalamayı `../Dockerfile` yapar.

- `atonota/` klasörü kimlik-tema işinindir. Giriş teması `atonota/login`, e-posta teması `atonota/email` klasöründedir.
- `atonota/test/` klasörü imaja girmez. Dışarıda bırakma kuralı `../.dockerignore` dosyasındadır.
- Bu klasördeki `.md` dosyaları imaja girmez. Keycloak yalnız klasörleri tema sayar.
