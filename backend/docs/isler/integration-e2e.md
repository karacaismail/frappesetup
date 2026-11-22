# İş: integration-e2e

Bu iş bütün backend parçalarını birlikte çalıştırır ve uçtan uca sınar. Parçalar ayrı dallarda yazıldı. Her biri kendi testini geçti. Bu iş, parçaların birlikte de çalıştığını kanıtlar.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`. Yeni dosya ve kod adları İngilizce olur (D-12).
2. `backend/PROJE-KAYDI.md`
3. `backend/docs/sozlesmeler.md`
4. `backend/README.md` ve `backend/dev/` klasörü

## Sahip olduğunuz yerler

- `backend/e2e/` (yeni klasör)
- `backend/dev/compose.yaml` içinde yalnız öteki compose dosyalarını birleştiren satırlar

## Parçalar ve durumları

Parçalar `backend` dalına birleştikçe senaryolara eklenir. Orkestratör her birleşmede haber verir.

| Parça | Dal | Durum |
| --- | --- | --- |
| Kiracı sitesi ve `platform_core` iskeleti | backend | Birleşti |
| Keycloak, realm ve `oidc_verify` | kimlik-realm | İncelemede |
| Atonota teması | kimlik-tema | Birleşmeyi bekliyor |
| Keycloak ile kiracı girişi | platform-core-kimlik | Yazılıyor |
| Kullanıcı eşitleme | identity-sync | İncelemede |
| Press girişi ve takım uçları | press-tr | Düzeltiliyor |
| Yapay zekâ katmanı | platform-core-yz | İkinci incelemede |
| Model geçidi | platform-core-gecit | İncelemede |
| Erişim kuralı motoru | erisim-kurali | İncelemede |

## Kontrol noktası 1: ortam

1. `backend/dev/compose.yaml` dosyasını genişletin. Dosya kiracı, Keycloak ve Press compose dosyalarını tek projede birleştirsin. Henüz birleşmemiş dosyayı eklemeyin.
2. Tek komutla bütün ortamı açan ve kapatan betik yazın. Betik `backend/e2e/` altında dursun.
3. Disk ve bellek kullanımını ölçün. `colima-factory` diski dardır. Boş yer 5 GB'ın altına inerse raporlayın.
4. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: senaryolar

Her senaryo için önce testi yazın. Parçası birleşmemiş senaryonun sonucu `not_run` olur.

1. Örnek kullanıcı Keycloak'ta “Atonota ile oturum aç” akışıyla girer. Kiracı sitesinde oturum açılır. Tarayıcı testi Playwright ile Chromium ve WebKit kullanır. Firefox kullanmayın.
2. identity-sync kullanıcıyı açar. Kullanıcı kiracıda “Website User” olarak görünür.
3. Keycloak'tan çıkış yapılınca kiracı oturumu 60 saniye içinde kapanır.
4. Aracı belirteciyle MCP üzerinden kayıt listelenir. Kısıtlı kullanıcı başkasının kaydını göremez.
5. Yapay zekâ bir güncelleme önerir. İnsan onaylamadan kayıt değişmez. Onaydan sonra değişir.
6. Model geçidi sahte bir sağlayıcıyla çağrılır. İlk API 429 dönünce ikinci API kullanılır.
7. Erişim kuralı listeyi ve tek kaydı aynı biçimde süzer.

Gerçek sağlayıcıya, gerçek Google'a ve gerçek Apple'a istek atmayın. Sahte servis kullanın.

## Kontrol noktası 3: rapor

1. Senaryoların sonucunu `backend/e2e/README.md` dosyasına tablo olarak yazın. Sonuçlar `pass`, `fail`, `not_run` ya da `not_applicable` olur.
2. Bulduğunuz her hatayı ilgili işin dalına yönelik kısa notla raporlayın. Başka işin kodunu siz düzeltmeyin.
3. Commit atın ve `done` raporlayın.
