# Atonota Keycloak imajı. Sahibi kimlik-realm işidir.
# Realm dosyası ve parola listesi imajın içine kopyalanır. Böylece container'ın
# ana bilgisayar klasörüne erişmesi gerekmez. Colima profilleri her klasörü bağlamaz.
# Keycloak'ın kendi kodu değişmez. Yalnız veri dosyaları eklenir.
# Versions are written once here (standard H-7). event-listener/pom.xml carries the same Keycloak
# version as its default for builds outside Docker; a test keeps the two equal.
ARG KEYCLOAK_VERSION=26.8.2
ARG MAVEN_IMAGE=maven:3.9.16-eclipse-temurin-21@sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320

# Magic link extension (docs/decisions/0003-keycloak-extensions.md): built from a pinned source commit
# against the running Keycloak version. No release jar exists upstream.
# BORC(mvp): the extension targets Keycloak 26.1.4 and is built here against KEYCLOAK_VERSION. It uses
# Keycloak internals. Owner: kimlik-realm. Closes when upstream publishes a release for the running
# Keycloak line, or when every Keycloak upgrade re-runs tests/test_magic_link.py (debt note in 0003).
FROM ${MAVEN_IMAGE} AS magiclink-build
ARG KEYCLOAK_VERSION
ARG MAGICLINK_COMMIT=7b4ee949a39a7ee953987162479ae1da2c57c3cb
ADD --checksum=sha256:fbcf7ec1ce2343d60c79ccdc4bb287e0ecb62b9f82eab181599c27faa8611792 \
    https://github.com/cloudflightio/keycloak-magic-link/archive/${MAGICLINK_COMMIT}.tar.gz /tmp/magiclink.tar.gz
WORKDIR /build
RUN tar -xzf /tmp/magiclink.tar.gz --strip-components=1
# G-162: our changed files go over the pinned source (magic-link-fork/NOTICE). The archive stays pinned.
COPY magic-link-fork/src/ /build/keycloak-magic-link/src/
RUN cd keycloak-magic-link \
    && mvn -q -B -DskipTests -Dkeycloak.version=${KEYCLOAK_VERSION} package \
    && cp target/keycloak-magic-link-*.jar /build/keycloak-magic-link.jar

# Event listener (docs/decisions/0003-keycloak-extensions.md, decision D-10 option 1): a fork of
# sashyo/keycloak-webhook-listener kept in event-listener/. The JUnit tests run here and gate the image.
FROM ${MAVEN_IMAGE} AS event-listener-build
ARG KEYCLOAK_VERSION
WORKDIR /build
COPY event-listener/ /build/
RUN --mount=type=cache,target=/root/.m2 mvn -q -B -Dkeycloak.version=${KEYCLOAK_VERSION} package \
    && cp target/keycloak-webhook-listener-*.jar /build/keycloak-webhook-listener.jar

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION} AS keycloak-base

# The account theme selects this provider. Compile it with the same Keycloak jars the server uses.
FROM ${MAVEN_IMAGE} AS account-provider-build
COPY --from=keycloak-base /opt/keycloak/lib/lib /keycloak-lib
COPY themes/atonota/account-provider /provider
RUN /provider/build.sh /keycloak-lib /provider/src /out

FROM keycloak-base AS prod
COPY --from=account-provider-build --chown=1000:0 /out/account-deletion-link-provider.jar /opt/keycloak/providers/account-deletion-link-provider.jar
COPY --from=event-listener-build --chown=1000:0 /build/keycloak-webhook-listener.jar /opt/keycloak/providers/keycloak-webhook-listener-identity-sync.jar
COPY --from=magiclink-build --chown=1000:0 /build/keycloak-magic-link.jar /opt/keycloak/providers/keycloak-magic-link-7b4ee94.jar
# Eklenti (docs/decisions/0003-keycloak-extensions.md). Sürüm ve SHA-256 özeti sabittir.
ADD --checksum=sha256:4091dee2a1ec9e0771bef4bd46005197d86b0a2b1f25198c41738476b1d102bb --chown=1000:0 \
    https://github.com/klausbetz/apple-identity-provider-keycloak/releases/download/1.17.0/apple-identity-provider-1.17.0.jar \
    /opt/keycloak/providers/apple-identity-provider-1.17.0.jar
# Default configuration: the magic link side doors are off (merge review E1).
COPY --chown=1000:0 conf/keycloak.conf /opt/keycloak/conf/keycloak.conf
COPY --chown=1000:0 realm/platform-realm.json /opt/keycloak/data/import/platform-realm.json
COPY --chown=1000:0 realm/password-blacklists/common-passwords.txt /opt/keycloak/data/password-blacklists/common-passwords.txt
# Temalar (themes/README.md). atonota teması kimlik-tema işinindir. test klasörü .dockerignore ile dışarıda kalır.
COPY --chown=1000:0 themes/ /opt/keycloak/themes/

# Geliştirme hedefi örnek kullanıcıları da taşır. Üretim imajı prod hedefinden alınır.
FROM prod AS dev
COPY --chown=1000:0 realm/dev-users/platform-users-0.json /opt/keycloak/data/import/platform-users-0.json
# Plain HTTP for events only to the listed development hosts (contract section 11). Not in prod.
COPY --chown=1000:0 conf/webhook-plain-http-hosts.txt /opt/keycloak/conf/webhook-plain-http-hosts.txt

# Development-only receiver for the event listener tests (tests/test_event_listener.py). Not part of prod.
FROM ${MAVEN_IMAGE} AS event-sink
WORKDIR /sink
COPY event-sink/EventSink.java /sink/EventSink.java
USER 1000
CMD ["java", "/sink/EventSink.java"]
