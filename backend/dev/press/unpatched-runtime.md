# Press geliştirme yamasını kaldırma yolu

`check_unpatched_runtime.sh` betiği, aday Bench ortamını sınar.
Betik, geliştirme işaretini ve Press kaynak farkını kontrol eder.
Sonra Python 3.14 ve Frappe 16 üzerinde üç Press modülünü açar.
Bu modüller Ansible, `TypedDict` ve ürün denemesi telemetrisini kullanır.

Aday Bench klasöründe çalıştırın. Betiğin yolunu kendi deponuza göre yazın.

```sh
sh /path/to/repo/backend/dev/press/check_unpatched_runtime.sh
```

Mevcut deneme ortamında test 1 kodu verdi. Press kaynakları sabit sürümden farklıydı.

## Önerilen sıra

1. Python 3.14 destekleyen bir Press sürümü seçin.
2. Sürümün bağımlılıklarını temiz bir ortamda çözün.
3. Playwright, Telegram, Stripe ve Ansible uyumunu ayrı ayrı sınayın.
4. `TypedDict` ve Frappe telemetri değişikliklerini yukarı akışta doğrulayın.
5. Eksik düzeltmeleri Press'e küçük değişiklikler hâlinde gönderin.
6. Kabul edilen sürümden yamayı içermeyen bir aday imaj oluşturun.
7. Aday imajda bu testi ve Press HTTP test paketini çalıştırın.
8. Ayrı hazırlık ortamında Press sunucu kurma testini çalıştırın.
9. Kabul koşulları sağlanınca geliştirme yamasını kaldırın.

Mevcut sürümde bağımlılık çözümü de engeldir. Playwright eski Greenlet sürümünü ister.
Bu bağımlılık Python 3.14 üzerinde derlenemez.
Aday sürümün bağımlılık çözümünü ve çalıştırılan paket sürümlerini kaydedin.

Bu testin geçmesi, modüllerin açıldığını gösterir.
Borç, yamasız Press açılışı ve HTTP paketi doğrulanınca kapanır.
Press'in kabul ettiği bir düzeltme de proje kaydındaki kapanma koşulunu sağlar.

[Press Python 3.14 kurulum kaydı](https://github.com/frappe/press/issues/7033)

[Sunucu kurma yolu](provisioning-readiness.md)
