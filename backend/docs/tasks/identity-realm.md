# İş: kimlik-realm

Bu iş Keycloak'ı geliştirme ortamında kurar. `platform` realm'ini kod olarak yazar. Ortak belirteç doğrulama kitaplığını da yazar. Kimlik markası Atonota'dır.

Önce `backend/AGENTS.md`, `backend/PROJECT-RECORD.md` ve `backend/docs/contracts.md` dosyalarını okuyun. Sonra karar sitesinin `src/content/docs/rail-4-keycloak.md` sayfasını okuyun.

## Sahip olduğunuz yerler

- `backend/dev/compose.keycloak.yaml`
- `backend/identity/keycloak/realm/`
- `backend/libs/oidc_verify/`
- `backend/contracts/` altında yeni dosya gerekmez.

## Kontrol noktası 1: Keycloak ve realm

1. Keycloak 26.8 serisinin son yama sürümünü resmî kaynaktan doğrulayın. Sürümü tam numarayla sabitleyin.
2. `compose.keycloak.yaml` dosyasını yazın. Dosyada şunlar olsun:
   - Keycloak,
   - Keycloak'ın PostgreSQL veritabanı,
   - test e-posta kutusu olarak Mailpit.
3. Portları sözleşmeye göre verin. Keycloak `PANE_PORT`, Mailpit ekranı `PANE_PORT+6` olsun.
4. Sözleşmenin 9. bölümündeki adres yolunu deneyin. Keycloak ağda `id.localhost` takma adını taşısın.
5. Realm'i `backend/identity/keycloak/realm/` altında JSON olarak tutun. Realm açılışta içe alınsın.
6. Realm sözleşmenin 2. bölümünü uygulasın:
   - görünen ad “Atonota”,
   - varsayılan dil Türkçe, ikinci dil İngilizce,
   - istemciler `site-tenant1`, `press`, `identity-sync` ve `press-service`,
   - hedef kapsamları `aud-site-tenant1` ve `aud-press`,
   - G-78 ve G-144 politikaları,
   - TOTP ve passkey.
7. Giriş teması bu turda `keycloak.v2` kalsın. Atonota teması ayrı iştir.
8. İstemci sırlarını depoya yazmayın. Keycloak'ın içe almada ortam değişkeni desteğini kaynakta doğrulayın. Sırları `.env` dosyasından verin.
9. Google girişini kapalı bir sağlayıcı olarak hazırlayın. Gerçek anahtar yoktur.
10. Örnek kullanıcıları ayrı bir dosyada tutun. Alan adı `example.test` olsun. Bu kullanıcılar yalnız geliştirmede yüklensin.
11. Testleri yazın. Testler şunları göstersin:
    - `identity-sync` istemcisi `aud-site-tenant1` kapsamıyla belirteç alır,
    - belirteçte `aud` tek değerdir ve `site-tenant1` olur,
    - kapsam istenmezse belirteçte `site-tenant1` yoktur,
    - yönetim konsolu ve Admin API yetkileri bu belirtece girmez.
12. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: `oidc_verify` kitaplığı

1. Kitaplığın arayüzü sözleşmenin 3. bölümündedir. Arayüzü değiştirmeyin. Değişiklik gerekirse raporda isteyin.
2. Kitaplık Python 3.11 ve sonrasında çalışsın. Frappe'ye bağlı olmasın.
3. PyJWT ve `cryptography` Frappe'nin içinde zaten var. Frappe 15 ve 16 imajlarındaki sürümleri doğrulayın. İki sürümle de çalışan bir aralık seçin.
4. Önce birim testlerini yazın. Testler yerelde üretilen RSA anahtarlarını kullansın. Testler şu durumları kapsasın:
   - doğru belirteç,
   - yanlış imza ve `none` algoritması,
   - yanlış `iss`, `aud` ve `azp`,
   - birden çok `aud`,
   - süresi dolmuş belirteç ve 30 saniyelik pay,
   - bilinmeyen `kid` ve anahtar listesinin bir kez yenilenmesi,
   - geçerli ve geçersiz çıkış belirteci,
   - yanlış `nonce`.
5. Canlı Keycloak'tan alınan belirteçle bütünleşme testi yazın.
6. Kitaplığın `pyproject.toml` dosyasını yazın. Lisans MIT olsun.
7. Commit atın ve `ready` raporlayın.

## Kontrol noktası 3: sihirli bağlantı ve Apple ile giriş

1. Bu iki yol MVP'ye girer (O-6). Keycloak ikisini hazır sunmaz.
2. Açık kaynak eklentileri karşılaştırın. Lisans Apache-2.0 ya da MIT olsun. Keycloak 26.8 uyumunu ve bakımı yazın.
3. T-2 notunu `backend/docs/decisions/0003-keycloak-extensions.md` dosyasına yazın. Seçimi gerekçesiyle yapın. Soru sormayın.
4. Eklentiyi compose kurulumuna ekleyin. Apple için gerçek anahtar yoktur. Sağlayıcıyı kapalı hazırlayın.
5. Sihirli bağlantının kısa ömrünü ve tek kullanımını test edin.
6. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Atonota teması ayrı iştir. Tema Keycloak'ın kendi tema yapısıyla kurulacak (O-4).
- Kiracı ve Press kurulumu başka işlerindir.
- HA kurulumu ve sunucu ayarı DevOps sorumlusunundur.
