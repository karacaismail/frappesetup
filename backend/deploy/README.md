# Dağıtım hattı

Bu klasör canlı ortamların Jenkins hattını tutar. Tasarım [ortamlar belgesindedir](../docs/dagitim/ortamlar.md).

Bu klasördeki kod henüz gerçek sunucuda çalışmadı.

## Marka ayarı

Ürün adı ve kök alan adı `backend/brand.env` dosyasından gelir.
Dosya yalnız `PRODUCT_NAME` ve `BRAND_DOMAIN` anahtarlarını taşır.
Bu dosyaya gizli bilgi yazmayın.

Ortam dosyaları `ATONOTA_HOST_LABEL` anahtarını taşır.
Değer alpha, beta ve rc için ortamın adıdır.
Prod için değer boştur.
`release.py`, bu etiketten ve kök alan adından beş adres üretir.
Adresler ana adres, giriş adresi, Press adresi, kiracı bölgesi ve örnek kiracı adresidir.

Çözülen ayarı şu komut gösterir:

```sh
python3 -I backend/deploy/release.py env-show alpha
```

`pack-deploy`, çözülen değerleri sürüm paketine yazar.
Paketin dosya özetleri bu değerleri de korur.
Yeni marka ayarı eski paketi değiştirmez.
Yeni değerler için yeni paket hazırlayın.
Sağlık denetimi paketteki adresleri kullanır.
Yarım kalan dağıtım sürdürülürse denetim, tamamlanan sürümün adreslerini sunucudan okur.
Bağlantı bilgileri çalışma dalındaki ortam ayarından gelir.
Kabuk betikleri ayarları veri olarak okur.
Betikler `brand.env` dosyasını `source` veya `eval` ile çalıştırmaz.

Compose, Keycloak için `IDENTITY_BRAND_NAME` değerini paketteki `PRODUCT_NAME` değerinden alır.
Sunucunun `keycloak.env` dosyasında ikinci marka değeri varsa dağıtım durur.
DevOps sorumlusu bu ikinci değeri kaldırmalıdır.

Dağıtım, kiracı sitesindeki `identity_brand_name` değerini yedekten sonra yazar.
Ardından siteyi yeni sürüme hazırlar.
Sitede farklı bir marka değeri varsa dağıtım ön kontrolde durur.
DevOps sorumlusu farkın nedenini incelemelidir.

Marka denetimini şu komutla çalıştırın:

```sh
python3 -I -m unittest discover -s backend/deploy/tests -p test_brand.py -v
```

Dağıtım komutları Python 3.9 ve sonrasını destekler.
Tüm testler için Python 3.12 veya üstünü kullanın.
Bazı testler uygulama kaynaklarını da okur.
Bu kaynaklarda yeni Python yazımı vardır.
Compose denetimi kurulu komut aracını kullanır. Servis başlatmaz.
Sunucu betiği testleri sahte komutlarla çalışır.

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
