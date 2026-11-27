# Press TR eklerinin yerel testi

## Ekler

- Frappe, istekten ve arka plan işinden önce Ansible bağlantısını hazırlar.
- Frappe, istek ve giriş kurallarını `press_tr` içinden yükler.
- Frappe, çıkışta Keycloak oturum bağını siler.
- Frappe, kapatılan kullanıcının API anahtarını iptal eder.
- Frappe, `Account Request` kaydında Press davetini engeller.
- Press takım kaydı, Keycloak kuruluş kimliğini özel alanda tutar.
- `Team` ayarı, performans ayarının varsayılan değerini `0` yapar.
- `PTR Identity Link` kaydı, Keycloak kimliğini Press kullanıcısına bağlar.
- `PTR Keycloak Session` kaydı, Keycloak ve Press oturumlarını eşler.
- Ağ uçları giriş, çıkış, kimlik eşleme, bakım ve hesap silme işlerini yürütür.
- Hesap silme sayfası ve Türkçe çeviriler `press_tr` içinde durur.
- `patches.txt` çalıştırılacak bir kayıt içermez.

## Yerel koşu

1. Ayrı bir test projesinde `press.localhost` sitesini kurun.
2. Siteye Press ve Press TR uygulamalarını kurun.
3. [Yerel HTTP test komutunu](../../apps/press_tr/README.md#local-http-tests) çalıştırın.
4. Çekirdek dosya farkı olup olmadığını test çıktısından kontrol edin.

Mevcut testler, Press davetini ve kimlik uçlarını sınar.
Yeni test, takım alanının veritabanında bulunduğunu denetler.
Dosya kontrolü, test komutundan önce ve sonra ölçüm alır.
O anda var olan uyum yamaları ilk ölçüme girer.
Kontrol, önbellek ve bağımlılık klasörlerini atlar.
İki ölçüm arasında geri alınan yazmalar gözden kaçabilir.
Test paketi, ilk uygulama kurulumu sırasında dosya ölçümü yapmaz.

Yerel dosya testi geçici bir çekirdek dosyasına yazdı.
Dosya değişince test komutu hata verdi.
Ayrı bir Press test sitesi çalışmadığı için HTTP paketi koşmadı.

## Yazışma kanalı

Ortak işlerde ekip proje Telegram grubunda yazışır. Bu kural 26 Kasım 2026 Perşembe günü konuldu. Grubun adresi ve kişi adları depoya yazılmaz.
