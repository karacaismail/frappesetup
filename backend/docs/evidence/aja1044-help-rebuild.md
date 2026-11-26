# G-138 dalının yeniden kurulması

Bu kayıt 26 Kasım 2026 Perşembe günü hazırlandı.
İş kaydı AJA-1044 olarak geçer.
Yeni dal `pc/aja1043-g138-yeniden` adını taşır.
Taban commit `72c2eeca21d6274b5ba17e3674510b87d2f78354` değeridir.
Kaynak dal `pc/aja1037-g138-baglantilar` adını taşır.
Kaynak uç `103fc3a2865abc459b3dc716dd48514ce0932086` değeridir.
Birleştirme commit'i `a945639cd76082739b4e8a65281d51c6c9f8c8b4` değeridir.
Yeni dal iki kaydın da geçmişini içerir.
Kaynak dalın geçmişi değiştirilmedi.

## Çakışmaların çözümü

- Çeviri dosyası tabandaki bütün satırları korur. Yardım için 58 satır eklenmiştir.
- Çeviri denetimi yeni yinelenen anahtar veya bozuk sütun bulmadı.
- `Dockerfile.tenant` bayi sözleşmesini korur. Yardım sözleşmesini aynı kopyalama adımına ekler.
- `semgrep-exceptions.json` dosyası taban commit ile birebir aynıdır. Kayıtlar ve özet korunmuştur.

Üç yardım bağlantısı yeni dalda vardır.
Alan adları `tour_url`, `doc_url` ve `support_url` olarak kalır.
Bileşen yardımı ucu `platform_core.api.help.get_component_help` adını taşır.
İzin listesi, modül sınırı ve OpenAPI sözleşmesi korunmuştur.

## Önce test

Mevcut yardım testleri önce taban commit üzerine alındı.
Yardım kodu gelmeden 9 test çalıştı ve 10 hata oluştu.
Eksik modüller ve kayıt tanımları beklenen hatayı verdi.
Birleştirme sonrasında aynı kapsamda 34 test geçti.

Gerçek site testlerinde iki kayıt testi ilk koşuda başarısız oldu.
Testler İngilizce içerik istiyordu. Frappe örnek kayda Türkçe varsayılan dilini veriyordu.
OpenAPI yalnız eşleşen dili veya dil belirtilmeyen içeriği kabul eder.
Test örneğinin dili açıkça `en` yapıldı.
Beklenen sonuçlar ve izin denetimleri değiştirilmedi.
Sonraki koşuda 11 kayıt testi geçti.

Frappe kaynağı bu varsayılan davranışını doğruladı.
Kaynaklar `frappe/model/document.py:1338` ve `frappe/model/create_new.py:50` konumlarıdır.
Kaynak, kullanılan test imajından okundu.

## Dokuz kapı

Komutlar depo kökünde çalıştı.
Birinci ve ikinci kapıda `python3`, Python 3.14.7 sürümünü seçti.
İlk denemede sistemin Python 3.9.6 sürümü bu iki kapıyı durdurmuştu.
Tablo, uygun Python sürümüyle alınan son sonuçları gösterir.

| Kapı | Komut | Sonuç |
| --- | --- | --- |
| 1 | `backend/dev/bin/module-boundaries` | `pass`. İhlal yoktur. |
| 2 | `backend/dev/bin/security-audit` | `fail`. Yalnız korunan Platform Core özeti güncel değildir. |
| 3 | `backend/dev/bin/ai-readiness` | `pass`. İki çekirdek alt denetimi `not_run` kaldı. |
| 4 | `python3.14 -B -m unittest discover -s backend/dev/tests` | `pass`. 178 test çalıştı. İki test atlandı. |
| 5 | `python3.14 -B -m unittest discover -s backend/dev/naming/tests` | `pass`. 68 test geçti. |
| 6 | `python3 -I -m unittest discover -s packages/press-ai/tests` | `pass`. Python 3.9.6 ile 164 test çalıştı. Bir test atlandı. |
| 7 | `python3.14 -I -m unittest discover -s backend/deploy/tests` | `pass`. 198 test çalıştı. 44 test atlandı. |
| 8 | `python3.14 -I -m unittest discover -s packages/press-ai/tests` | `pass`. 164 test çalıştı. Bir test atlandı. |
| 9 | `python3.14 -I packages/press-ai/server.py check-contract` | `pass`. Sözleşme hatası yoktur. |

Semgrep taraması 58 bulgu bildirdi.
Press kapsamındaki 22 bulgunun onayı geçerli kaldı.
Platform Core kapsamındaki 36 bulgunun onayı eski özet nedeniyle uygulanmadı.
Bu 36 bulgunun tamamı korunan istisna kayıtlarıyla eşleşir.
Eşleşme dosya, satır ve kural üzerinden denetlendi.
Yeni istisna yazılmadı. Özet yenilenmedi.
Bağımsız güvenlik incelemesi AJA-1045 görevinde yapılacaktır.

Üçüncü kapı çekirdeğin çeviri kataloğunu ve paket bildirimini yerelde bulamadı.
Bu yüzden `translation_core` ve `dependency_core` alt denetimleri çalışmadı.
Dokuzuncu kapı kılavuz sırasını ve site haritasını denetlemedi.
Bu kontrollerin kaynak verileri verilmedi.

## Yardım testleri

| Denetim | Sonuç |
| --- | --- |
| Saf işlevler ve sözleşme | `pass`. 34 test geçti. |
| Gerçek HTTP istekleri | `pass`. 12 test geçti. |
| Frappe kayıt denetimleri | `pass`. 11 test geçti. |
| Ruff 0.14.10 | `pass`. Kod ve biçim denetimleri geçti. |
| Git fark denetimi | `pass`. Boşluk hatası yoktur. |

Saf test komutu şöyledir:

```bash
PYTHONPATH=backend/apps/platform_core uv run --offline --no-project \
  --python "$HOME/.local/bin/python3.14" \
  --with PyYAML==6.0.3 --with jsonschema==4.26.0 python -B -m unittest \
  platform_core.shell.test_help_content platform_core.shell.test_help_links \
  platform_core.shell.test_help_contract platform_core.shell.test_help_topic_source
```

HTTP testi, test konteynerinin `sites` klasöründe çalıştı:

```bash
PLT_SHELL_TEST_SITE=test-shell.localhost \
PLT_SHELL_TEST_PORT=46381 \
PLT_HELP_FOREIGN_TEST_SITE=test-help-foreign.localhost \
/home/frappe/frappe-bench/env/bin/python -B -m unittest platform_core.api.test_help
```

Kayıt testi, test konteynerinin bench klasöründe çalıştı:

```bash
bench --site test-shell.localhost run-tests --app platform_core \
  --module platform_core.shell.test_help_api
```

## Ortam ve sınırlar

Paket Python `>=3.14,<3.15` ve Frappe `>=16.56.0,<17.0.0` aralıklarını ister.
Bağımlılık kilitleri değiştirilmedi.
Yerel Python sürümü 3.14.7 olarak ölçüldü.
Test ortamında Python 3.14.10 ve Frappe 16.56.0 ölçüldü.
Pydantic sürümü 2.12.5 olarak ölçüldü.

Önceki G-138 test ortamının imajı ve veri birimleri kullanıldı.
İmaj yeniden derlenmedi. Yeni dalın kaynakları ayrı test konteynerine kopyalandı.
Kaynak karşılaştırmasında 526 dosya birebir eşleşti.
Sonraki test dili düzeltmesi de aynı konteynere kopyalandı.
İki test sitesinde şema güncellemesi tamamlandı.
Testler iki kiracının içerik ayrımını ve misafir reddini kapsadı.
Canlı sunucuya veya canlı veriye erişilmedi.
Test konteynerleri kapatıldı. Veri birimleri korundu.

Bu işte CI çalıştırılmadı. Tam Platform Core test paketi çalıştırılmadı.
Tarayıcı denetimi bu sunucu birleştirmesinin kapsamına girmez.
Bağımsız QA, AJA-1042 görevinde yeni dalı deneyecektir.
Gerçek okurla denenmedi.
