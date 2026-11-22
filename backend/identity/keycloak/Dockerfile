# Atonota Keycloak imajı. Sahibi kimlik-realm işidir.
# Realm dosyası ve parola listesi imajın içine kopyalanır. Böylece container'ın
# ana bilgisayar klasörüne erişmesi gerekmez. Colima profilleri her klasörü bağlamaz.
# Keycloak'ın kendi kodu değişmez. Yalnız veri dosyaları eklenir.
# Magic link extension (docs/kararlar/0003-keycloak-eklentileri.md): built from a pinned source commit
# against the running Keycloak version. No release jar exists upstream.
FROM maven:3.9.16-eclipse-temurin-21@sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320 AS magiclink-build
ARG MAGICLINK_COMMIT=7b4ee949a39a7ee953987162479ae1da2c57c3cb
ADD --checksum=sha256:fbcf7ec1ce2343d60c79ccdc4bb287e0ecb62b9f82eab181599c27faa8611792 \
    https://github.com/cloudflightio/keycloak-magic-link/archive/${MAGICLINK_COMMIT}.tar.gz /tmp/magiclink.tar.gz
WORKDIR /build
RUN tar -xzf /tmp/magiclink.tar.gz --strip-components=1 \
    && cd keycloak-magic-link \
    && mvn -q -B -DskipTests -Dkeycloak.version=26.8.2 package \
    && cp target/keycloak-magic-link-*.jar /build/keycloak-magic-link.jar

FROM quay.io/keycloak/keycloak:26.8.2 AS prod
COPY --from=magiclink-build --chown=1000:0 /build/keycloak-magic-link.jar /opt/keycloak/providers/keycloak-magic-link-7b4ee94.jar
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
