# Giriş sayfası tarayıcı testleri

Bu testler kiracının `/login` sayfasını Chromium ve WebKit ile sınar. Firefox proje kuralı gereği yoktur.

Ön koşullar:

1. Site `kimlik_yalniz_keycloak=1` ayarıyla çalışır.
2. Site ana bilgisayardan `http://kiraci1.localhost:8661` adresinden açılır. Colima'da port tüneli gerekir: `PANE_PORT=8660 backend/dev/bin/tunnel open 8661`.
3. Playwright tarayıcıları depo kökünde kuruludur.
4. Bench `--noreload` ile çalışır. Kod veya ayar değişince bu işin Bench sürecini yeniden başlatın.

WebKit bağlantıya Tab ile değil, Alt+Tab ile gider. Safari'nin varsayılanı budur. Test bu yüzden WebKit'te Alt+Tab kullanır.

Çalıştırma, depo kökünden:

```bash
npx playwright test -c backend/apps/platform_core/platform_core/identity/tests/e2e/playwright.config.ts
```

Başka adres için `IDENTITY_E2E_BASE_URL` değişkenini verin.

Parola formu testi `login-password.spec.ts` yalnız kapı kapalıyken çalışır. Kapı açıksa test atlanır. Bu testi `kimlik_yalniz_keycloak=0` ayarıyla ayrıca çalıştırın.

Tür denetimi, depo kökünden çalışır.

```bash
npm exec --package=typescript@5.9.3 -- tsc --noEmit --strict --skipLibCheck --module NodeNext --target ES2022 backend/apps/platform_core/platform_core/identity/tests/e2e/*.ts
```
