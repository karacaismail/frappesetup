# Giriş sayfası tarayıcı testleri

Bu testler kiracının `/login` sayfasını Chromium ve WebKit ile sınar. Firefox proje kuralı gereği yoktur.

Ön koşullar:

1. Site `kimlik_yalniz_keycloak=1` ayarıyla çalışır.
2. Site ana bilgisayardan `http://kiraci1.localhost:8661` adresinden açılır. Colima'da port tüneli gerekir: `PANE_PORT=8660 backend/dev/bin/tunel ac 8661`.
3. Playwright tarayıcıları depo kökünde kuruludur.
4. Bench `--noreload` ile çalışır. Kod ya da site ayarı değişince bu işin bench container'ını yeniden başlatın.

WebKit bağlantıya Tab ile değil, Alt+Tab ile gider. Safari'nin varsayılanı budur. Test bu yüzden WebKit'te Alt+Tab kullanır.

Çalıştırma, depo kökünden:

```bash
npx playwright test -c backend/apps/platform_core/platform_core/kimlik/tests/e2e/playwright.config.ts
```

Başka adres için `KIMLIK_E2E_BASE_URL` değişkenini verin.
