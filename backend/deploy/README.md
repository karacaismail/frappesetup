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
| `tests/` | Paket kuralı ve sunucu betiği testleri |

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
- İmajı etiketle değil, özetle çağırın.
- Taşımada kodu yeniden derlemeyin.
- Veritabanı değişikliğini "genişlet, sonra daralt" kuralıyla yazın.
- Zamanlanmış iş eklemeyin. Yedek yalnız dağıtımda ya da elle alınır.
