# AJA-1288 düzeltme kaydı

27 Kasım 2026 Cuma günü hazırlandı.

Dal `pc/aja1053-epic-brand` adını taşır.
Dalın tabanı yerel `backend` dalındaki `30494610` commit'idir.

## Değişiklik

Epic adı ve düzey kuralı artık `PRODUCT_NAME` ayarından gelir.
Sayfa ve kural tablosu `fillBrandData` işlevini kullanır.
Gereksinim kimlikleri ve teknik adlar değişmedi.

Tarama, görev panosunun tamamını artık atlamaz.
Yalnız `audit.note` ve `update.note` geçmiş not olarak korunur.
Her istisnanın nedeni `backend/brand-exclusions.txt` dosyasında yazılıdır.
Alan yolu artık yoksa test başarısız olur.
Bozuk JSON dosyası da testi başarısız yapar.

## Önce başarısız test

Önce testler yazıldı ve çalıştırıldı.
Site testi dört durumda başarısız oldu.
Bu durumlar epic adı ve düzey kuralını kapsar.
Test hem ürün adını hem alan adını dener.

Tarama testinde eklenen dört kontrol de önce başarısız oldu.
Sonra kod düzeltildi.
Aynı testler düzeltmeden sonra geçti.

## Kontroller

Komutlar dalın ayrı çalışma klasöründe çalıştırıldı.

| Komut | Sonuç |
| --- | --- |
| `npm ci --no-audit --no-fund` | `pass` |
| `python3 -m unittest discover -s tests -p test_site_brand.py` | `pass`, 3 test geçti. |
| `python3 -m unittest discover -s backend/deploy/tests -p test_brand_hardcode.py` | `pass`, 16 test geçti. |
| `npm run test:brand-build` | `pass`, iki ayrı marka ile derleme yapıldı. |
| `npm run build` | `pass`, 31 sayfa üretildi. Ön marka testleri de geçti. |
| Hedefli tarayıcı denemesi | `pass`, 49 kontrol geçti. 25 kontrol atlandı. |
| `git diff --check` | `pass` |

Tarayıcı denemesinde şu komut kullanıldı:

```bash
PW_PORT=4468 npm run test:e2e -- tests/brand.spec.ts tests/consistency.spec.ts tests/smoke.spec.ts --grep 'brand setting|consistency|task board|network budget' --workers=2
```

Derleme testi, marka ayarını iş bitince geri yükledi.
Bu test 320 ve 1366 CSS px genişliklerini denedi.
CSS px, tarayıcıdaki yerleşim ölçüsüdür.
Epic süzgeci, kart satırı, kural metni ve gruplu görünüm denetlendi.
Uzun marka adında sayfa taşması görülmedi.

Tarayıcı denemeleri macOS `26.5.1` üzerinde çalıştı.
Chromium sürümü `156.0.8078.4`, WebKit sürümü `27.2` oldu.
iPhone 13 dokunma emülasyonu da çalıştı.
Görev panosu testleri 320 CSS px ve masaüstü görünümünü kapsadı.
Açık ve koyu görünümün otomatik erişilebilirlik kontrolleri geçti.
Chromium ağ bütçesi kontrolü geçti.
24 içerik kontrolü yalnız Chromium üzerinde çalışır.
Ağ bütçesi kontrolü de yalnız Chromium üzerinde çalışır.
WebKit için atlanan 25 kontrolün nedeni bu mevcut test düzenidir.

Yeni tarayıcı kontrolünde iki öğe seçicisi düzeltildi.
Düğme ve başlık adları görev sayısını da içerir.
Son koşuda bu kontroller geçti.

## Sürümler ve yazım

Manifest Node sürümünü `>=22.23.4` olarak ister.
Gözlenen Node sürümü `24.21.0`, Python sürümü `3.9.6` oldu.
Astro `7.4.7`, React `19.3.0` ve Mantine `9.7.1` kurulu durumda doğrulandı.
Playwright sürümü `1.64.0` oldu.
Bu dört paket sürümü kilit dosyasıyla eşleşti.

Türkçe denetim betiği değişen yönerge cümlelerinde hata bulmadı.
Uzun kelime uyarısı elle incelendi.
Yönerge dosyasının eski bölümlerindeki yazım uyarıları bu işte değiştirilmedi.

## Devir ve sınırlar

QA, bağımsız kabul denemesini ayrı görevde yeniden yapacak.
QA onayından sonra orkestratör birleştirsin.
Bu dal için GitHub PR açılmadı.

CI ve bütün site testleri `not_run` durumundadır.
Gerçek Safari ve gerçek telefon denemeleri `not_run` durumundadır.
Linux görsel karşılaştırması `not_run` durumundadır.
Görsel referanslar değiştirilmedi.
Gerçek okurla denenmedi.
