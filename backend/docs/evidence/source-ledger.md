# Kaynak ve doğrulama defteri

G-128 kayıtları `source-ledger.json` dosyasındadır.
Her kayıt iddiayı, kaynağı, sürümü, yöntemi ve doğrulama tarihini içerir.

`KD` kayıtları site defterindeki iddiaları ve tarihleri korur.
`evidence` alanı, kayıt metninin sabit Git sürümünü gösterir.
Site defteri kaynak olarak güncel bir belgeyi de gösterebilir.
Sabit Git bağlantısı, site defterinin ne yazdığını kanıtlar.
Dış kaynağın bugün aynı bilgiyi verdiğini kanıtlamaz.

`PRESS-PYTHON314` kaydı, yerel Press sürüm taramasının sonucunu gösterir.

## Bakım

1. İddianın dayandığı kaynağı açın.
2. İddiayı yeni sürümde doğrulayın.
3. Sürümü, yöntemi ve doğrulama tarihini yazın.
4. Sabit kanıt bağlantısını ekleyin.
5. Depo kökünde aşağıdaki denetimi çalıştırın.

```sh
backend/dev/bin/check-source-ledger
```

Denetim, site defterinin ve Press taramasının kayıtlarını karşılaştırır.
Denetim ağ isteği göndermez.
