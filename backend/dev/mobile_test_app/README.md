# O-31 mobil ölçümü

Frappe 16 ile boş ve yalıtılmış bir `perf-mobile.localhost` sitesi hazırlayın.
Sitede ERPNext, HRMS, `platform_core` ve `mobile_test_app` kurulu olmalı.
Önce site ayarında `allow_performance_fixture` değerini 1 yapın.
Bu ayarı `mobile_test_app` kurulumundan önce yazın.

```bash
bench --site perf-mobile.localhost set-config --parse allow_performance_fixture 1
```

Bench kuyruğu doluysa komut veri oluşturmadan durur.
İmleç anahtarı için `mobile_cursor_key` ayarına test değeri verin.

Bench klasöründen komutu çalıştırın. Test uygulaması Python yolunda olmalı.

```bash
env/bin/python -m mobile_test_app.measure_performance --site perf-mobile.localhost --status-file /yol/durum.md
```

Komut sonuç tablosunu durum dosyasına ekler. Sınır aşılırsa komut 1 döndürür.
Komut ölçüm sonunda oluşturduğu kayıtları tür ve ad ile siler.

- Ölçüm 200 çalışan ve 2.000 izin kaydı oluşturur.
- İlk 50 telefon HTTP üzerinden kaydolur. Diğer 150 kurulum önceden hazırlanır.
- Kayıt ölçümü bitince her çalışanın tek kurulumu doğrulanır.
- Gönderme, ilk çekme ve etkinlik uçları 50 kez çağrılır.
- Bir telefon 1.000 bekleyen değişikliği on sayfada çeker. Bu ölçüm beş kez yapılır.
- Sunucu süresi kimlik denetimini, isteği ve veritabanı işlemini kapsar.
- Mobil uçlar örnek izin görünümünü kullanır. Canlı HRMS iş akışı çalışmaz.
- `hrms_tr` izin görünümü mobil eşitlemeye bağlanınca iki O-31 ölçümünü yeniden çalıştırın.
- Yeni ölçümlerde gerçek izin görünümünü kullanın. Sonuçları durum dosyasına kaydedin.

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
env/bin/python -m mobile_test_app.measure_concurrent --site perf-mobile.localhost --workers 4 --status-file /yol/durum.md
```

50 telefon birlikte 50 gönderme ve 50 çekme isteği açar.
Komut, her uç için p95 süresini ve hata oranını yazar.
MariaDB'deki satır kilidi bekleme sayısını ve toplam süreyi de yazar.
Kilit sayaçları iki işin ortak sonucudur.
Komut Gunicorn işçilerini, yanıt kodlarını ve MariaDB hata numaralarını da yazar.
Eski Werkzeug yükünü karşılaştırmak için boş bir sitede `--workers 0` kullanın.
İstemci süresine Gunicorn kuyruğu da girer. O-31 sınırı sunucu süresine uygulanır.
Komut, hata veya sınır aşımı varsa 1 döndürür.

## Üretim işçi sayısı için kapasite denemesi

Üretime denk bir deneme ortamında ayrı bir `perf-*.localhost` sitesi hazırlayın.
Aynı işlemci, bellek, veri tabanı ve ağ koşullarını kullanın.
Canlı siteye ölçüm verisi göndermeyin.

```bash
env/bin/python -m mobile_test_app.measure_concurrent \
  --site perf-mobile.localhost --worker-candidates 4 8 12 --repeats 3 \
  --client-p95-limit-ms 1000 --status-file /yol/isci-olcumu.md
```

Komut, her işçi sayısıyla 50 telefonun 100 eşzamanlı isteğini ölçer.
Her koşu ayrı ölçüm verisi kurar ve sonunda o veriyi temizler.
Komut bütün koşularda sınırları karşılayan en küçük sayıyı önerir.
Hiçbir sayı sınırları karşılamazsa komut sonuçları yazar ve 1 döndürür.
İstemci p95 sınırı öneri içindir. O-31 sınırı sunucu süresine uygulanır.

Ölçüm örnek izin görünümünü ve yerel HTTP yolunu kullanır.
Üretim seçimi için ters vekil, gerçek izin görünümü ve diğer yükleri de ölçün.
Hüseyin Cengiz, üretime denk ölçümden sonra işçi sayısını seçer.
