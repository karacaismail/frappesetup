# Theme test image. Owned by the kimlik-tema work stream. Used for local testing only.
# Colima's factory profile does not mount the repository folder into the virtual machine.
# So the theme and the test realm are copied into the image. Keycloak's own code is unchanged.

# Stage 1: the stock Keycloak image, pinned by digest. Its jars are the compile-time classpath of the provider.
FROM quay.io/keycloak/keycloak:26.8.2@sha256:7e66a96e4739239070aeaf72e4c5decf0f7f682cfc725b9f7ea2b336eaba38b3 AS keycloak

# Stage 2: builds the account console provider with a plain JDK. The step itself is account-provider/build.sh.
# The image is pinned by digest (JDK 21.0.13).
FROM eclipse-temurin:21-jdk@sha256:8ad118b146aa92da815b576441acd6b42b38236797ad0b6edc8c200b85bb0734 AS provider
COPY --from=keycloak /opt/keycloak/lib/lib /keycloak-lib
COPY account-provider /provider
# The build step lives in one script. Other images call the same script.
RUN /provider/build.sh /keycloak-lib /provider/src /out

# Stage 3: Keycloak with the themes, the provider and the test realm.
FROM keycloak
COPY --from=provider --chown=1000:0 /out/account-deletion-link-provider.jar /opt/keycloak/providers/account-deletion-link-provider.jar
COPY --chown=1000:0 login /opt/keycloak/themes/atonota/login
COPY --chown=1000:0 email /opt/keycloak/themes/atonota/email
COPY --chown=1000:0 account /opt/keycloak/themes/atonota/account
COPY --chown=1000:0 test/realm/theme-test-realm.json /opt/keycloak/data/import/theme-test-realm.json
