# Tema deneme imajı. Sahibi kimlik-tema işidir. Yalnız yerel denemede kullanılır.
# Colima'nın factory profili depo klasörünü sanal makineye bağlamaz.
# Bu yüzden tema ve deneme realm'i imaja kopyalanır. Keycloak'ın kendi kodu değişmez.
FROM quay.io/keycloak/keycloak:26.8.2
COPY --chown=1000:0 login /opt/keycloak/themes/atonota/login
COPY --chown=1000:0 email /opt/keycloak/themes/atonota/email
COPY --chown=1000:0 account /opt/keycloak/themes/atonota/account
COPY --chown=1000:0 test/realm/tema-deneme-realm.json /opt/keycloak/data/import/tema-deneme-realm.json
