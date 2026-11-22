# Uçtan uca entegrasyon testleri

## Sonuçlar

| Senaryo | Sonuç | Eksik parça |
| --- | --- | --- |
| Atonota girişi kiracı oturumunu açar. | `not_run` | Keycloak, giriş teması ve kiracı girişi. |
| Kullanıcı eşitleme servisi “Website User” açar. | `not_run` | Keycloak, eşitleme servisi ve kiracı kimlik ucu. |
| Keycloak çıkışı kiracı oturumunu 60 saniyede kapatır. | `not_run` | Keycloak ve kiracı çıkış ucu. |
| Aracı belirteci yalnız izinli kayıtları listeler. | `not_run` | Yapay zekâ erişim katmanı. |
| Kayıt yalnız insan onayından sonra değişir. | `not_run` | Yapay zekâ erişim katmanı. |
| Model geçidi 429 yanıtından sonra ikinci adresi kullanır. | `not_run` | Model geçidi. |
| Erişim kuralı liste ve tek kayıt için aynı sonucu verir. | `not_run` | Erişim kuralı motoru. |

Kiracı ortamı açıldı. Kiracı, `ping` isteğine yanıt verdi.
Container içinde Frappe 16.56.0 ve ERPNext 16.55.0 çalıştı.

Playwright 1.64.0 dokuz test buldu.
Chromium ve WebKit ön denemeleri giriş düğmesini bulamadı.
Bu sonuç, kiracı girişi henüz birleşmediği için bekleniyordu.

Sahte sağlayıcı **429** ve **200** sırasını doğruladı.
Kiracı ağı da sahte sağlayıcıya ulaştı.

| İlgili dal | Birleştirme notu |
| --- | --- |
| `kimlik-realm`, `press-tr` | Dosyalar birleşince ana Compose dosyasına ekleyin. Açma betiği için servis ve port adlarını doğrulayın. |
| `platform-core-kimlik`, `platform-core-kabuk` | Tarayıcı ön denemesi `/panel` sayfasında “Atonota ile oturum aç” düğmesini bulamadı. Bu akışı dallar birleşince tekrar sınayın. |
| `identity-sync`, `platform-core-yz`, `platform-core-gecit`, `erisim-kurali` | İlgili uçlar birleşince örnek veriyi hazırlayın. Sonra testleri çalıştırın. |

## Çalıştırma

Komutları depo kökünden ve kendi Pane ortamınızda çalıştırın.
Pane, `PANE_PORT` değişkeniyle bu çalışma alanına port ayırır.

1. Kiracıyı `backend/e2e/environment.sh up` komutuyla açın.
2. Aşağıdaki örnek veriyi hazırlayın.
3. İlgili test grubunu çalıştırın.
4. Ortamı `backend/e2e/environment.sh down` komutuyla kapatın.

`down` veritabanı birimlerini korur. Yalnız bu Pane'in ortamını kapatır.

```sh
npx --no-install playwright test -c backend/e2e/playwright.config.ts --list
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=chromium --project=webkit
npx --no-install playwright test -c backend/e2e/playwright.config.ts --project=api
```

## Örnek veri

Yalnız yerel test ortamını kullanın. Gerçek hesap veya veri kullanmayın.
Parolaları, oturum çerezlerini ve anahtarları yalnız yerel ortam değişkenlerine koyun.

- **Tarayıcı.** Keycloak'a doğrulanmış `e2e-user@example.test` hesabını ekleyin. Parolasını `E2E_KEYCLOAK_PASSWORD` değişkenine verin. Kiracı ile Keycloak'ı kendi yerel adreslerinde bağlayın.
- **Kullanıcı eşitleme.** Keycloak'a doğrulanmış `e2e-sync@example.test` hesabını ekleyin. Kullanıcı kimliğini `E2E_SYNC_SUBJECT` değişkenine verin. Servis ile teste aynı `IDENTITY_SYNC_WEBHOOK_SECRET` değerini verin. Bu hesap deneme öncesinde kiracıda bulunmamalı.
- **Yetki ve onay.** Örnek kayıt türünü `E2E_DOCTYPE` değişkenine verin. Örnek kayıt adlarını `E2E_VISIBLE_RECORD` ve `E2E_HIDDEN_RECORD` değişkenlerine verin. Okuyucu yalnız ilk kayda erişebilmeli. Yetkili test hesabı ilk kaydı değiştirebilmeli. Yazılabilir metin alanının adını `E2E_UPDATE_FIELD` değişkenine verin.
- **Oturumlar.** Okuyucu için `E2E_READER_COOKIE` ve `E2E_READER_CSRF` kullanın. Yetkili hesap için `E2E_OPERATOR_COOKIE` ve `E2E_OPERATOR_CSRF` kullanın. CSRF değeri, sitenin yazma isteğini doğruladığı oturum anahtarıdır.
- **Model geçidi.** `backend/e2e/environment.sh provider` komutuyla sahte sağlayıcıyı açın. `e2e-local-only` yoluna iki kimliksiz Ollama uyumlu adres ekleyin. İlk adres `http://e2e-provider:<PANE_PORT+7>/limited` olur. İkinci adres `http://e2e-provider:<PANE_PORT+7>/fallback` olur. İkinci API kaydının adını `E2E_FALLBACK_API` değişkenine verin. Bu yola gerçek sağlayıcı eklemeyin. Tekrar öncesi ilk adresin bekleme süresi dolmalı.
