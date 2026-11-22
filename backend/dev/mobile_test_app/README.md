# O-31 mobil ölçümü

Frappe 16 ile boş ve yalıtılmış bir `test-mobile.localhost` sitesi hazırlayın.
Sitede ERPNext, HRMS, `platform_core` ve `mobile_test_app` kurulu olmalı.
Site ayarında `allow_tests` açık olmalı.
İmleç anahtarı için `mobile_cursor_key` ayarına test değeri verin.

Bench klasöründen komutu çalıştırın. Test uygulaması Python yolunda olmalı.

```bash
env/bin/python -m mobile_test_app.measure_performance --status-file /yol/durum.md
```

Komut sonuç tablosunu durum dosyasına ekler. Sınır aşılırsa komut 1 döndürür.
Yeni ölçüm için yeni bir boş site hazırlayın.
Komut mevcut çalışan, izin ve telefon kayıtlarını silmez.

- Ölçüm 200 çalışan ve 2.000 izin kaydı oluşturur.
- İlk 50 telefon HTTP üzerinden kaydolur. Diğer 150 kurulum önceden hazırlanır.
- Kayıt ölçümü bitince her çalışanın tek kurulumu doğrulanır.
- Gönderme, ilk çekme ve etkinlik uçları 50 kez çağrılır.
- Bir telefon 1.000 bekleyen değişikliği on sayfada çeker. Bu ölçüm beş kez yapılır.
- Sunucu süresi kimlik denetimini, isteği ve veritabanı işlemini kapsar.
- Mobil uçlar yalıtılmış test izin görünümünü kullanır. Canlı HRMS iş akışı çalışmaz.

## Telefon sözleşmesi örnekleri

Komut, her uçtaki istek ve yanıt örneklerini sözleşmenin şemasına göre denetler.
Depo kökünden çalıştırın.

```bash
uv run --no-project --with-requirements backend/dev/requirements-contract-tests.txt \
  python -m unittest discover -s backend/dev/mobile_test_app/tests
```

## Eşzamanlı telefon yükü

Aynı boş site koşullarını kullanın. MariaDB, bu test sitesine ayrılmış olmalı.

```bash
env/bin/python -m mobile_test_app.measure_concurrent --status-file /yol/durum.md
```

50 telefon birlikte 50 gönderme ve 50 çekme isteği açar.
Komut, her uç için p95 süresini ve hata oranını yazar.
MariaDB'deki satır kilidi bekleme sayısını ve toplam süreyi de yazar.
Kilit sayaçları iki işin ortak sonucudur.
Komut, hata veya sınır aşımı varsa 1 döndürür.
