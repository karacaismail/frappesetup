# İş: dev-ortam

Bu iş geliştirme ortamını kurar. `platform_core` uygulamasının iskeletini de üretir. Öteki işler bu ortamda test çalıştırır. Bu yüzden ilk kontrol noktası önemlidir.

Önce `backend/AGENTS.md`, `backend/PROJECT-RECORD.md` ve `backend/docs/contracts.md` dosyalarını okuyun.

## Sahip olduğunuz yerler

- `backend/dev/` klasörü. Yalnız `compose.keycloak.yaml` ve `compose.press.yaml` başka işlerindir.
- `backend/apps/platform_core/` iskeleti: `pyproject.toml`, `hooks.py`, `modules.txt`, `patches.txt`, uygulama `__init__.py`, `.gitignore` ve araç ayarları.
- `backend/PROJECT-RECORD.md` dosyasında yalnız “Denetim komutları” bölümü.
- `backend/README.md` dosyasında kurulum bölümü.

## Kontrol noktası 1: iskelet ve kiracı sitesi

1. Docker bağlamı olarak `colima-factory` kullanın.
2. `frappe/erpnext:v16.55.0` imajı `colima` bağlamında var. `colima-factory` bağlamında yoksa kopyalayın. Kopyalama 4,5 GB'lık indirmeyi önler:

   ```bash
   docker --context colima save frappe/erpnext:v16.55.0 | docker --context colima-factory load
   ```

3. `backend/dev/compose.tenant.yaml` dosyasını yazın. Dosyada Frappe 16, MariaDB ve Redis olsun.
   - MariaDB sürümünü Frappe 16'nın resmî kurulum belgesinden doğrulayın.
   - Web portu `PANE_PORT+1`, anlık bağlantı portu `PANE_PORT+2` olsun.
   - Web servisi ağda `kiraci1.localhost` takma adını taşısın. Sözleşmenin 9. bölümündeki adres yolunu deneyin.
4. Container içinde `bench new-app platform_core --no-git` ile iskeleti üretin. Lisans MIT olsun. Yayıncı e-postası olarak `noreply@example.test` yazın. Kişisel e-posta yazmayın.
5. Üretilen iskeleti `backend/apps/platform_core/` klasörüne alın. Uygulama klasörünü container'a bağlayın. Uygulamayı düzenlenebilir kurulumla kurun.
6. `pyproject.toml` içinde Frappe aralığını `[tool.bench.frappe-dependencies]` bölümüne yazın. Aralık `>=16.0.0,<17.0.0` olsun.
7. Modül olarak `Identity` ve `Shell` ekleyin. Klasör adları `identity` ve `shell` olsun. Varsayılan modülü bırakmak gerekirse nedenini yazın.
8. `kiraci1.localhost` sitesini açın ve `platform_core` uygulamasını kurun.
9. İlk duman testini yazın. Test uygulamanın kurulu olduğunu doğrulasın. Testi `bench run-tests` ile çalıştırın.
10. Commit atın ve `ready` raporlayın. Raporda şu bilgiler olsun:
    - çalışan Frappe, ERPNext, Python ve MariaDB sürümleri,
    - siteyi açan ve testi çalıştıran komutlar,
    - adres yolunun sonucu.

## Kontrol noktası 2: betikler ve denetimler

1. `backend/dev/bin/` klasörüne betikler yazın. Betikler şunları yapsın:
   - ortamı aç ve kapat,
   - bir uygulamanın testlerini ayrı test sitesinde çalıştır,
   - Ruff denetimini çalıştır,
   - modül sınırı denetimini çalıştır.
2. Test sitesi `allow_tests` ayarını yalnız test sitesinde açsın (D-9).
3. Betikler compose proje adını ve portları `PANE_PORT` değişkeninden üretsin. Böylece iki Pane aynı anda çalışabilir.
4. Modül sınırı denetimini yeni paket eklemeden yazın. Python'un `ast` modülü yeterlidir. Denetim üç şeyi yakalasın:
   - izin listesinde olmayan modül bağı,
   - bağımlılık döngüsü,
   - başka modülün DocType'ına doğrudan yazma çağrısı.
5. İzin listesini `backend/dev/module-boundaries.json` dosyasında tutun. Proje kaydındaki bağımlılık yönünü kullanın.
6. Denetimi önce test edin. Bilerek bozuk bir örnek hazırlayın. Denetimin bu örneği reddettiğini gösterin (N-5).
7. `backend/dev/compose.yaml` dosyasını yazın. Dosya şimdilik yalnız kiracı dosyasını içersin. Öteki dosyaları orkestratör birleştirmede ekler.
8. “Denetim komutları” tablosunu doldurun. README'ye kurulum adımlarını yazın.
9. Commit atın ve `done` raporlayın.

## Doğrulayıp raporlayacağınız bilgiler

Öteki işler bu bilgileri bekliyor. Her birini Frappe 16 kaynak kodunda doğrulayın. Dosya ve satır yazın.

- `frappe.integrations.oauth2_logins.login_via_keycloak` ucu var mı?
- `on_social_login` kancası var mı? Kanca hangi bilgiyi alıyor?
- Rolü masaüstü erişimi taşımayan “Website User”, `/api/v2` ile DocType okuyabiliyor mu?
- Frappe 16 hangi Python sürümünü istiyor?
- Frappe 16 içinde PyJWT ve `cryptography` paketleri var mı? Sürümleri ne?

## Kapsam dışı

- Keycloak kurulumu kimlik-realm işinindir.
- Press kurulumu press-tr işinindir.
- Giriş ve ekran uçları başka işlerindir. Bu işte iş kuralı yazmayın.
- GitHub Actions dosyası bu turda yazılmaz.
