# Atonota Keycloak imajı. Sahibi kimlik-realm işidir.
# Realm dosyası ve parola listesi imajın içine kopyalanır. Böylece container'ın
# ana bilgisayar klasörüne erişmesi gerekmez. Colima profilleri her klasörü bağlamaz.
# Keycloak'ın kendi kodu değişmez. Yalnız veri dosyaları eklenir.
FROM quay.io/keycloak/keycloak:26.8.2 AS prod
# Eklenti (docs/kararlar/0003-keycloak-eklentileri.md). Sürüm ve SHA-256 özeti sabittir.
ADD --checksum=sha256:4091dee2a1ec9e0771bef4bd46005197d86b0a2b1f25198c41738476b1d102bb --chown=1000:0 \
    https://github.com/klausbetz/apple-identity-provider-keycloak/releases/download/1.17.0/apple-identity-provider-1.17.0.jar \
    /opt/keycloak/providers/apple-identity-provider-1.17.0.jar
COPY --chown=1000:0 realm/platform-realm.json /opt/keycloak/data/import/platform-realm.json
COPY --chown=1000:0 realm/password-blacklists/yaygin-parolalar.txt /opt/keycloak/data/password-blacklists/yaygin-parolalar.txt
# Temalar (themes/OKUBENI.md). atonota teması kimlik-tema işinindir. test klasörü .dockerignore ile dışarıda kalır.
COPY --chown=1000:0 themes/ /opt/keycloak/themes/

# Geliştirme hedefi örnek kullanıcıları da taşır. Üretim imajı prod hedefinden alınır.
FROM prod AS dev
COPY --chown=1000:0 realm/dev-users/platform-users-0.json /opt/keycloak/data/import/platform-users-0.json
