# Mobil oturum iptali

`mobile_identity_sync_url` kimlik servisinin adresidir.
Üretimde bu adres HTTPS olmalıdır.
Keycloak belirteç adresi her ortamda HTTPS olmalıdır.

## Geliştirme sitesi

`mobile_allow_development_http` varsayılan olarak kapalıdır.
Yerel HTTP için `developer_mode` ve `mobile_allow_development_http` değerlerini `1` yapın.
Örneğin `mobile_identity_sync_url` için `http://identity-sync.localhost:6115` kullanın.
`localhost`, `127.0.0.1` ve `[::1]` de kabul edilir.
Bu üç adres, isteği aynı makineye gönderir.
