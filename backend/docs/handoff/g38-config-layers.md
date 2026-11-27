# G-38 Press doğrulaması

Yerel test, Frappe'nin aynı bench içindeki iki siteye ortak ayarı verdiğini gösterdi.
Press'in mevcut bench'e ayarı göndermesi ayrı bir doğrulama gerektirir.

Yetkili deneme ortamı hazır olduğunda platform ekibi şu adımları uygular.

1. İki deneme sitesi olan mevcut bir Release Group seçin.
2. Grup ayar tablosunda `mail_port` değerini değiştirin.
3. Press'in `update_config` işinin tamamlandığını doğrulayın.
4. İki sitede `bench show-config` ile yeni değeri doğrulayın.
5. İki sitenin ayrı `db_name` değerlerini koruduğunu doğrulayın.
6. Tam ayar çıktısını paylaşmadan sonucu görev kaydına yazın.

Press Settings içindeki `bench_configuration` yalnız yeni bench için kullanılır.
Mevcut bench'e yayılma kanıtı Release Group üzerinden alınır.

## Yazışma kanalı

Ortak işlerde ekip proje Telegram grubunda yazışır. Bu kural 26 Kasım 2026 Perşembe günü konuldu. Grubun adresi ve kişi adları depoya yazılmaz.
