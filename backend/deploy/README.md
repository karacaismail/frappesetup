# Dağıtım hattı

Bu klasör canlı ortamların Jenkins hattını tutar. Tasarım [ortamlar belgesindedir](../docs/dagitim/ortamlar.md).

Bu klasördeki kod henüz gerçek sunucuda çalışmadı.

## Klasörler

| Klasör | İçerik |
| --- | --- |
| `jenkins/` | Üç Jenkins hattı |
| `bin/` | Jenkins'in koştuğu betikler |
| `remote/` | Sunucuda çalışan betikler |
| `compose/` | Bir ortamın servisleri ve ön vekil |
| `images/` | Üretim imajlarının derleme dosyaları |
| `environments/` | Dört ortamın sır içermeyen ayarı |
| `settings/` | Sunucudaki sır dosyalarının anahtar listeleri. Değer yoktur |
| `tests/` | Paket kuralı, sunucu betiği ve Jenkins tarafı testleri |

## Testler

Testleri depo kökünde şu komutla çalıştırın:

```sh
python3 -I -m unittest discover -s backend/deploy/tests
```

Sunucu betiği testleri yalnız Linux'ta koşar. macOS'ta bu testler atlanır. GitHub'daki PR kapısı Linux'ta koşar.

Betikleri `shellcheck` ile denetleyin:

```sh
shellcheck -x -P backend/deploy/bin:backend/deploy/remote backend/deploy/bin/* backend/deploy/remote/*
```

## Kurallar

- Depoya sır yazmayın. Sırlar sunucuda `/etc/atonota/<ortam>/` klasöründe durur.
- Kod yeni bir üretim ayarı okursa ayarı `settings/` listesine ekleyin. Liste eksikse `tests/test_settings.py` düşer.
- `atonota_verification_secret` sırrını doğrulama sağlayıcısı verir. DevOps sorumlusu sırrı kiracı sitesinin `site_config.json` dosyasına yazar.
- Sunucuda bir ayar eksikse `remote/apply` hiçbir şeyi değiştirmeden durur ve eksik anahtarı yazar.
- İmajı etiketle değil, özetle çağırın.
- Taşımada kodu yeniden derlemeyin.
- Veritabanı değişikliğini "genişlet, sonra daralt" kuralıyla yazın.
- Depoya zamanlanmış iş eklemeyin. Geliştirme Mac'inde zamanlanmış iş kurulmaz.
- Frappe zamanlayıcısı ve düzenli yedek sunucularda açıktır (D-16, 26 Kasım 2026). İkisini DevOps sorumlusu sunucuda kurar.
- Her ortam kendi SSH anahtarını ve kendi sunucu kullanıcısını kullanır. Kullanıcı `deploy-<ortam>` adını taşır.
- Uzak komutu `bin/lib.sh` içindeki `remote` işleviyle çalıştırın. İşlev her sözcüğü tırnaklar.
- Otomatik geri dönüşe başarısız paketin kimliğini verin: `--failed <paket kimliği>`. Sağlıklı paket geri alınmaz.
- Paket kendi commit'inin dağıtım dosyalarını taşır. Derleme işi `release.py pack-deploy` komutunu çalıştırır. `bin/deploy` sunucuya yalnız bu kopyayı gönderir.
- Yarım kalan taşımada aynı paketi yeniden taşımayın. Taşımayı elle bitirin ve `resume` eylemini kullanın. Ya da `rollback-restore` seçin.
