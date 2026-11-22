# İş: press-tr

Bu iş Press'i geliştirme ortamında kurar. `press_tr` uygulamasının kimlik bölümünü de yazar. Press, kiracı sitelerini yöneten kontrol düzlemidir.

Önce `backend/AGENTS.md`, `backend/PROJECT-RECORD.md` ve `backend/docs/contracts.md` dosyalarını okuyun. Sonra karar sitesinin `rail-1-press.md` ve `rail-4-keycloak.md` sayfalarını okuyun. Rail 4 sayfasının 6. bölümü Press girişini anlatır (G-12).

## Güncelleme: 22 Kasım 2026 Pazar

Proje sahibi iki karar verdi. Bu bölüm aşağıdaki Frappe 15 bilgilerinin yerine geçer.

1. Bütün uygulamalar Frappe 16 ile yazılır. `press_tr` aralığı `>=16.0.0,<17.0.0` olur (D-7).
2. Bu Mac'te bir Press deneme kurulumu var (D-8). Sürümleri Frappe v16.50.0, ERPNext v16.50.0, Press v0.154.1, Python 3.14.8 ve MariaDB 11.8'dir.
3. Var olan kurulumu değiştirmeyin. Onun container'larını durdurmayın ve içine uygulama kurmayın.
4. Kurulumun imajını ve betiklerini yeniden kullanın. Betikleri `backend/dev/press/` altına alın. Sır taşıyan `.env` dosyasını almayın.
5. Press bu sürümde yalnız yamalarla açılır. Ansible ve sunucu kurma çalışmaz. Bu tur için bu kabul edilir (O-9).
6. Frappe 16'da `on_social_login` kancası var olabilir. Kaynakta doğrulayın. Kanca ya da kendi dönüş ucunuz arasında seçim yapın. Seçimi kontrol noktası 2'den önce raporlayın.

## Sahip olduğunuz yerler

- `backend/dev/compose.press.yaml`
- `backend/apps/press_tr/`
- `backend/contracts/press_tr.openapi.yaml`

## Kontrol noktası 1: Press bench'i ve iskelet

1. Press'in v0.154 serisindeki sürümünü resmî depodan doğrulayın. Tam etiketle sabitleyin.
2. `compose.press.yaml` dosyasını yazın. Dosyada Frappe 15, Press, MariaDB ve Redis olsun.
   - Python sürümü 3.11 olsun.
   - Web portu `PANE_PORT+3`, anlık bağlantı portu `PANE_PORT+4` olsun.
   - Web servisi ağda `press.localhost` takma adını taşısın.
3. `colima` bağlamında `frappe/erpnext:v15.124.5` imajı var. Bu imajı kullanabilirsiniz. Kullanacaksanız `colima-factory` bağlamına kopyalayın.
4. Press'in kendi ajanını, sunucularını ve Ansible kurulumunu bu turda kurmayın. Yalnız Press uygulaması ve sitesi yeterlidir.
5. Container içinde `bench new-app press_tr --no-git` ile iskeleti üretin. Lisans AGPL-3.0 olsun (O-8). Uygulama klasörüne lisans dosyasını koyun. Yayıncı e-postası olarak `noreply@example.test` yazın.
6. `required_apps` listesine `press` ekleyin. Frappe aralığı `>=15.0.0,<16.0.0` olsun.
7. Modül olarak `Press Identity` ekleyin. Klasör adı `press_identity` olsun.
8. `press.localhost` sitesini açın. Press'i ve `press_tr` uygulamasını kurun.
9. Duman testini yazın ve çalıştırın.
10. Commit atın ve `ready` raporlayın. Raporda çalışan sürümleri ve komutları yazın.

## Kontrol noktası 2: Press girişi

1. Önce `contracts/press_tr.openapi.yaml` dosyasını yazın.
2. `Press Identity Link` DocType'ını yazın. Alanlar sözleşmenin 4. bölümündedir. Tekilliği veritabanında sağlayın (V-8).
3. Press, Frappe 15 üzerinde çalışır. `on_social_login` kancasının Frappe 15'te olmadığını kaynakta doğrulayın. Sonra kendi dönüş ucunuzu yazın (AU-4).
4. Uçları sözleşmenin 6. bölümüne göre yazın:
   - `get_login_url`: `state`, `nonce` ve PKCE S256 değerini sunucuda üretir.
   - `keycloak_callback`: `state` değerini denetler, kodu belirteçle değiştirir, kimlik belirtecini doğrular.
   - Kullanıcıyı `(iss, sub)` ile bulur. İlk bağı yalnız doğrulanmış e-postayla kurar.
   - Takım yoksa Press'in kendi takım açma yolunu kullanır. Bu yolu Press kaynağında bulun.
   - Keycloak `sid` değerini Press oturumuyla eşleştirir.
   - `keycloak_backchannel_logout`: çıkış belirtecini doğrular ve oturumu kapatır.
5. Belirteç doğrulamayı `backend/libs/oidc_verify` kitaplığıyla yapın. Kitaplığı kimlik-realm işi paralel yazıyor. Arayüz sözleşmenin 3. bölümündedir.
   - Kitaplık dalınıza gelene kadar testlerde arayüzün sahte bir uyarlamasını kullanın.
   - Kitaplığın kodunu kopyalamayın. Kendi doğrulama kodunuzu yazmayın.
6. G-12'deki Press giriş, kayıt, OTP, parola ve 2FA uçlarını 403 ile kapatın. Engeli `before_request` kancasıyla kurun. `/login`, `/signup` ve `/dashboard/login` adreslerini panele yönlendirin.
7. Her kapalı uç için HTTP isteğiyle test yazın (D-6).
8. Commit atın ve `ready` raporlayın.

## Kontrol noktası 3: servis uçları

1. `ensure_team` ve `remove_team_member` uçlarını yazın.
2. Uçlar yalnız `identity-sync` istemcisinin servis belirtecini kabul etsin. `aud` değeri `press` olsun.
3. Aynı istek iki kez gelirse aynı sonuç dönsün.
4. Yetki reddini, yanlış `aud` değerini ve yanlış `azp` değerini HTTP isteğiyle sınayın.
5. Commit atın ve `done` raporlayın.

## Kapsam dışı

- iyzico, TRY, KDV ve e-belge işleri sonraki turdadır.
- Keycloak realm'i kimlik-realm işinindir. Realm'de değişiklik gerekirse raporda isteyin.
- Press'in kodunu değiştirmeyin (M-4).
