# Backend

Bu klasör platformun sunucu kodunu tutar. Karar sitesi deponun kökündedir. Backend ondan ayrı geliştirilir.

- Ajan talimatları [AGENTS.md](AGENTS.md) dosyasındadır.
- Seviye, sürümler ve kararlar [proje kaydındadır](PROJE-KAYDI.md).
- Bileşenlerin ortak adları [sözleşmeler](docs/sozlesmeler.md) dosyasındadır.

Kimlik markası Atonota'dır. Kullanıcılar uygulamalara “Atonota ile oturum aç” düğmesiyle girer. Atonota, Keycloak üzerinde çalışır.

## Yerel geliştirme ortamı

Komutları depo kökünde çalıştırın. Ortam, Colima'nın `factory` profilini kullanır.
Pane, çakışmaları önlemek için her çalışma alanına ayrı bir `PANE_PORT` verir.

1. Ortamı `backend/dev/bin/ac` ile açın.
2. Komutun yazdığı kiracı adresini tarayıcıda açın.
   Site ilk istekte yanıt vermezse birkaç saniye sonra tekrar deneyin.
3. `backend/dev/bin/test platform_core` ile kurulum testlerini çalıştırın.
4. İşiniz bitince `backend/dev/bin/kapat` ile ortamı kapatın.

Açma komutu yerel parolaları `backend/dev/.env` dosyasına yazar.
Yeni çalıştırmalarda aynı parolaları kullanır.
Kapatma komutu veritabanı birimlerini korur.

Kiracı adresinde `kiraci1.localhost` adını kullanın.
Frappe, adresin bu bölümünden siteyi seçer.
Açma komutu yerel bağlantı için SSH tünelini de başlatır.
Tüneli ayrı açmak için `backend/dev/bin/tunel ac` komutunu kullanın.
Farklı portlar gerekirse önce `backend/dev/bin/tunel kapat` komutunu çalıştırın.
Sonra `backend/dev/bin/tunel ac` komutuna gereken tüm portları yazın.

Test komutu `test-platform-core.localhost` sitesini kullanır.
`allow_tests` ayarı yalnız test sitesinde açıktır.
Bu ayar Frappe'nin testleri çalıştırmasına izin verir.
[Proje kaydında](PROJE-KAYDI.md) “Denetim komutları” bölümünü açın.
