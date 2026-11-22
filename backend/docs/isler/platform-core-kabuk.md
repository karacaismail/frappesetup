# İş: platform-core-kabuk

Bu iş ayrı arayüzün sunucudan aldığı verileri hazırlar. Açılış verisini, kenar çubuğunu ve DocType tanımını döner. `/panel` sayfasını da kurar. Arayüz bu verilerle çalışır. Hiçbir menü elle kodlanmaz (K5, K6).

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJE-KAYDI.md`
3. `backend/docs/sozlesmeler.md`, özellikle 5 ve 10. bölümler
4. Karar sitesinde `rail-2-gelistirme.md`, `rail-3-frontend.md` ve `admin-shell.md` sayfaları. G-45, G-63 ve G-94 kurallarını bulun.

## Sahip olduğunuz yerler

- `backend/apps/platform_core/platform_core/kabuk/`
- `backend/apps/platform_core/platform_core/api/shell.py`, `api/meta.py`
- `backend/apps/platform_core/platform_core/www/panel.*`
- `backend/contracts/platform_core-kabuk.openapi.yaml`
- `hooks.py` içinde yalnız bu işin satırları

## Önkoşul

`platform_core` iskeleti dev-ortam işinden gelir. Orkestratör iskeleti `backend` dalına birleştirince bu iş başlar.

## Kontrol noktası 1: açılış verisi ve tanım

1. Önce OpenAPI sözleşmesini yazın. Her alana ve her uca açıklama verin (D-9). Yapay zekâ katmanı da bu açıklamaları kullanacak.
2. `shell.get_bootstrap` ucunu yazın. Uç şunları dönsün:
   - kullanıcının adı, dili ve rolleri,
   - kurulu uygulamalar,
   - kullanıcının görebildiği kenar çubuğu.
3. Kenar çubuğunu “Workspace” ve “Workspace Sidebar” kayıtlarından ve izinlerden türetin (G-94).
4. `meta.get_doctype` ucunu yazın.
   - Uç sitedeki gerçek tanımı dönsün. Özel alanlar ve alan ayarları da girsin.
   - Kullanıcının okuyamadığı izin seviyesindeki alanları çıkarın.
   - Yanıta `ETag` başlığı koyun. `If-None-Match` eşleşirse 304 dönün.
5. Önbelleği G-63'e göre kurun. Önbellek anahtarı kullanıcının yetkisini de içersin (P-5).
6. Testleri önce yazın. Testler şunları göstersin:
   - iki farklı kullanıcı farklı tanım ve farklı `ETag` alır,
   - izin değişince eski tanım dönmez,
   - görünmeyen Workspace kenar çubuğuna girmez,
   - oturumsuz istek reddedilir.
7. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: `/panel` sayfası

1. `www/panel` sayfasını yazın. Sayfa şimdilik yer tutucu bir kabuk sunar. Ön yüz bu turda yazılmaz.
2. Sayfaya CSRF belirtecini güvenli biçimde koyun (G-45).
3. Sayfada ortak önbelleği kapatın (`no_cache = 1`, W-5).
4. Oturumu olmayan kullanıcıyı giriş adresine yönlendirin.
5. Testlerle CSRF belirtecinin oturuma bağlı olduğunu gösterin.
6. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Giriş ve çıkış platform-core-kimlik işinindir.
- Yapay zekâ araçları platform-core-yz işinindir. Bu işin uçlarını o iş kullanır.
- React arayüzü bu turda yazılmaz.
