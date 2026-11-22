# Atonota Keycloak imajı. Sahibi kimlik-realm işidir.
# Realm dosyası ve parola listesi imajın içine kopyalanır. Böylece container'ın
# ana bilgisayar klasörüne erişmesi gerekmez. Colima profilleri her klasörü bağlamaz.
# Keycloak'ın kendi kodu değişmez. Yalnız veri dosyaları eklenir.
FROM quay.io/keycloak/keycloak:26.8.2 AS prod
COPY --chown=1000:0 realm/platform-realm.json /opt/keycloak/data/import/platform-realm.json
COPY --chown=1000:0 realm/password-blacklists/yaygin-parolalar.txt /opt/keycloak/data/password-blacklists/yaygin-parolalar.txt

# Geliştirme hedefi örnek kullanıcıları da taşır. Üretim imajı prod hedefinden alınır.
FROM prod AS dev
COPY --chown=1000:0 realm/dev-users/platform-users-0.json /opt/keycloak/data/import/platform-users-0.json
