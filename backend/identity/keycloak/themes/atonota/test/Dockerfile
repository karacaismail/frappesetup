# Tema deneme imajı. Sahibi kimlik-tema işidir. Yalnız yerel denemede kullanılır.
# Colima'nın factory profili depo klasörünü sanal makineye bağlamaz.
# Bu yüzden tema ve deneme realm'i imaja kopyalanır. Keycloak'ın kendi kodu değişmez.

# Stage 1: the stock Keycloak image, pinned by digest. Its jars are the compile-time classpath of the provider.
FROM quay.io/keycloak/keycloak:26.8.2@sha256:7e66a96e4739239070aeaf72e4c5decf0f7f682cfc725b9f7ea2b336eaba38b3 AS keycloak

# Stage 2: compiles the account console provider with a plain JDK. No build tool and no extra dependency.
# The image is pinned by digest (javac 21.0.13).
FROM eclipse-temurin:21-jdk@sha256:8ad118b146aa92da815b576441acd6b42b38236797ad0b6edc8c200b85bb0734 AS provider
COPY --from=keycloak /opt/keycloak/lib/lib /keycloak-lib
COPY account-provider/src /src
RUN mkdir -p /out/classes /out/check-classes \
 && javac --release 21 -Xlint:all -Werror -proc:none -cp "/keycloak-lib/main/*:/keycloak-lib/boot/*" -d /out/classes $(find /src/main/java -name '*.java') \
 && cp -r /src/main/resources/META-INF /out/classes/META-INF \
 && jar --create --file /out/account-deletion-link-provider.jar -C /out/classes .
# The checks run with assertions on. A failed check stops the build. The check classes stay out of the jar.
RUN javac --release 21 -Xlint:all -Werror -proc:none -cp "/out/classes:/keycloak-lib/main/*:/keycloak-lib/boot/*" -d /out/check-classes $(find /src/test/java -name '*.java') \
 && java -ea -cp "/out/check-classes:/out/classes:/keycloak-lib/main/*:/keycloak-lib/boot/*" platform.identity.account.AccountDeletionLinkConsoleCheck

# Stage 3: Keycloak with the themes, the provider and the test realm.
FROM keycloak
COPY --from=provider --chown=1000:0 /out/account-deletion-link-provider.jar /opt/keycloak/providers/account-deletion-link-provider.jar
COPY --chown=1000:0 login /opt/keycloak/themes/atonota/login
COPY --chown=1000:0 email /opt/keycloak/themes/atonota/email
COPY --chown=1000:0 account /opt/keycloak/themes/atonota/account
COPY --chown=1000:0 test/realm/tema-deneme-realm.json /opt/keycloak/data/import/tema-deneme-realm.json
