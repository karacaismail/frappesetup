# Hazır kayıt temizliğini doğrulayın

Bu iş G-8 gereksinimidir. Git dalı `pc/g7-g8-press-cleanup` adını taşır.

Frappe güncelleme sırasında önce Press'in hazır kayıtlarını yükler. Hazır kayda fixture denir. Sonra Frappe `after_migrate` listesindeki işleri çalıştırır. Bu listede `press_tr.fixture_cleanup.disable_cloud_defaults` işi vardır. Temizlik kayıt silmez. Temizlik yalnız alan değerini değiştirir.

## Temizliğin yaptığı işler

1. Temizlik Press dosyasındaki 686 Site Plan kaydını kapatır.
2. Press dosyasında olmayan planlar bizimdir. Temizlik bu planları açık bırakır.
3. Temizlik `press.signup_e2e.run_signup_e2e` işini durdurur.
4. Onaylı tablo varsa temizlik Team Tier değerlerini bu tabloya eşitler.
5. Bölge listesi varsa temizlik kullanılmayan Cluster kaydını gizler.
6. Aynı durumda temizlik bu Cluster kaydına bağlı Server Plan kaydını kapatır.

Cloud Region kaydında açma ve kapatma alanı yoktur. Temizlik bu kayda dokunmaz.

## İnsan kararı bekleyen değerler

İki değer site ayarından okunur. Değer yoksa ilgili adım hiçbir şeyi değiştirmez.

- `press_tr_team_tiers` ayarı Team Tier tablosudur. Ürün sahibi bu tabloyu verir. Fiyat kapısı G-166 kapalıdır.
- `press_tr_enabled_clusters` ayarı kullanılan Cluster adlarının listesidir. Altyapı sorumlusu bu listeyi verir.

Team Tier tablosu her Press Team Tier kaydını bir kez içermelidir. Her satırda `amount` ve `last_invoice_amount` alanı olmalıdır. `paying_user_since` alanı isteğe bağlıdır. Değerler sıfır ya da daha büyük sayı olmalıdır. Tablo eksikse temizlik hata verir ve hiçbir Team Tier kaydını değiştirmez.

Press, Team Tier `amount` değerini ekibin harcama sınırı yapar. Press bu sınırı dolar fiyatıyla karşılaştırır. Bu yüzden tablodaki tutarlar dolar karşılığıdır.

Cluster kaydını gizleme yöntemi mimar onayı ister. SAFe System Architect bu öneriyi onaylamalıdır.

## Ayrı deneme sitesinde yapılacaklar

1. Dalı ayrı bir Press deneme sitesine kurun.
2. Press'in `site_plan.json` dosyasında 686 kayıt olduğunu doğrulayın.
3. Deneme sitesine ayrı adlı bir yerel plan ekleyin.
4. Deneme sitesinde `bench --site <test-site> migrate` komutunu çalıştırın.
5. Hazır planların `enabled=0` olduğunu doğrulayın.
6. Yerel planın açık kaldığını doğrulayın.
7. `press.signup_e2e.run_signup_e2e` işinde `stopped=1` olduğunu doğrulayın.
8. Aynı güncellemeyi yeniden çalıştırın.
9. Plan ve iş sayılarının aynı kaldığını doğrulayın.

Tablo ve bölge listesi gelince üç adım daha yapın:

1. İki değeri deneme sitesinin ayarına yazın.
2. Güncellemeyi yeniden çalıştırın.
3. Team Tier, Cluster ve Server Plan değerlerini doğrulayın.

Canlı sunucuda ve çalışan 7400 ortamında veri güncellemesi yapılmadı.
