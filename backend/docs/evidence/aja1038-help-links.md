# G-138 yardım bağlantıları ve bileşen yardımı

Bu kayıt 26 Kasım 2026 Perşembe günü hazırlandı.
İş kaydı AJA-1038 olarak geçer.
Kaynak dal `pc/aja1015-g138-semgrep` dalıdır.
Kaynak commit `9aa0b878` değeridir.
Teslim dalı `pc/aja1037-g138-baglantilar` dalıdır.

## Davranış

Her yardım kaydı üç isteğe bağlı bağlantı taşır.
`tour_url` tur adresini taşır.
`doc_url` belge adresini taşır.
`support_url` destek adresini taşır.
Boş bağlantı yanıtta `null` olur.
Sunucu bağlantıları seçilen yardım kaydından alır.
Başka yardım katmanından bağlantı tamamlamaz.

Sunucu yalnız HTTPS adreslerini ve site içindeki göreli yolları kabul eder.
HTTPS, şifreli web bağlantısıdır.
Sunucu diğer şemaları ve `//host` biçimini reddeder.
Ters eğik çizgi, kontrol karakteri ve adres içindeki kullanıcı bilgisi de reddedilir.
Kayıt denetimi geçersiz adresin kaydedilmesini engeller.
Yanıt denetimi eski geçersiz adresleri de gizler.

Yeni uç `platform_core.api.help.get_component_help` adını taşır.
Uç, `component_id` ve isteğe bağlı `language` değerlerini kabul eder.
Sunucu yalnız etkin kiracının veritabanını okur.
Sunucu kullanıcının oturumunu ve rollerini denetler.
İstek başka kiracı, kullanıcı veya sürüm seçemez.

Sunucu önce kiracı yardımını seçer.
Sonra uygulama yardımını seçer.
Dil, sürüm ve güncelleme sırası alan yardımıyla aynıdır.
Sunucu sürümü yardım kaydının uygulamasından okur.
Bileşenin Frappe alan açıklaması yoktur.
Eşleşme yoksa uç `200` durumuyla `message: null` döndürür.
Rol nedeniyle gizlenen yardım da aynı yanıtı verir.

Uç, panel kullanıcılarının izin listesine eklendi.
Modül sınırındaki sahibi `platform_core.shell` olarak kaldı.
Uç yolu ortak modül listesine de yazıldı.
OpenAPI sözleşmesinin sürümü `0.2.0` oldu.
Test imajı yardım sözleşmesini de içerir.

## Sürümler

Paket Python `>=3.14,<3.15` aralığını ister.
Paket Frappe `>=16.56.0,<17.0.0` aralığını ister.
Test imajı ERPNext `v16.55.0` etiketi ve mevcut özetine sabittir.
Bu iş bağımlılık kilitlerini değiştirmedi.
Yerel Python sürümü `3.14.7` olarak ölçüldü.
Test ortamındaki Python sürümü `3.14.10` olarak ölçüldü.
Test ortamındaki Frappe sürümü `16.56.0` olarak ölçüldü.
Test ortamındaki Pydantic sürümü `2.12.5` olarak ölçüldü.
Ruff sürümü `0.14.10` olarak kullanıldı.

## Test kanıtı

İlk koşuda 15 test çalıştı.
Eksik bağlantılar ve işlevler 33 hata üretti.
Bu koşu kod değişikliğinden önce yapıldı.
Kayıt `/tmp/aja1038-red.log` dosyasındadır.

Kod sonrasında 34 saf işlev ve sözleşme testi geçti.
Gerçek HTTP yolundaki 12 test geçti.
Frappe kayıt denetimindeki 11 test de geçti.
İlk kayıt koşusunda yeni test yanlış oturumla çağrı yaptı.
Testin oturumu düzeltildi ve aynı kapsam yeniden geçti.
Ruff denetimi ve biçim denetimi geçti.

Testler yalnız göreve ait Colima ortamında çalıştı.
Ortamın Compose adı `fs-dev-ortam-46380` olarak seçildi.
Test siteleri `test-shell.localhost` ve `test-help-foreign.localhost` olarak kuruldu.
Başka siteye taşınan oturum reddedildi.
Aynı bileşen kimliği iki sitede farklı içerikle denendi.
Her oturum yalnız kendi sitesinin içeriğini aldı.
Canlı sunucu ve canlı veri kullanılmadı.

Saf test komutu şöyledir:

```bash
PYTHONPATH=backend/apps/platform_core uv run --offline --no-project \
  --python "$HOME/.local/bin/python3.14" \
  --with PyYAML==6.0.3 --with jsonschema==4.26.0 python -B -m unittest \
  platform_core.shell.test_help_content platform_core.shell.test_help_links \
  platform_core.shell.test_help_contract platform_core.shell.test_help_topic_source
```

Gerçek HTTP testi, test konteynerinin `sites` klasöründe çalıştı:

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

## Birleştirme kapıları

İlk güvenlik koşusu eski kaynak özetini reddetti.
İzin kontrollerini taşıyan yardımcı dosyalar da özet kapsamına eklendi.
İstisnaların kuralı, satırı ve gerekçesi değiştirilmedi.

Dokuz birleştirme kapısı da geçti.
Güvenlik kapısı yenilenen kaynak özetiyle geçti.
Geliştirme testlerinde 159 test çalıştı ve 2 test atlandı.
Ad denetiminde 68 test geçti.
Press AI testlerinde 163 test çalıştı ve 1 test atlandı.
Bu paket, listedeki iki ayrı komutla denendi.
Dağıtım testlerinde 198 test çalıştı ve 44 test atlandı.
Press AI sözleşme denetimi hatasız bitti.
Kılavuz sırası ve site haritası denetimleri veri eksikliği nedeniyle çalışmadı.
Yapay zekâ uygunluk denetimi iki eksik kaynak bildirdi.
Frappe çekirdeğinin çeviri kataloğu ve paket bildirimi yerelde yoktu.
Bu alt kontroller `not_run` olarak kaldı.

## Bağımsız inceleme

Geçici `standards-reviewer` incelemesi düzeltme gerektiren kusur bulmadı.
İnceleyici paylaşılan kaynakları, farkları ve test sonuçlarını okudu.
İnceleyici dosya değiştirmedi ve komut çalıştırmadı.
Önceki 10 güvenlik istisnasını baştan incelemedi.
Bu istisnaların gerekçeleri ve satırları değişmedi.
İnceleyici iki kiracıdaki içerik ayrımının ayrıca gösterilmediğini belirtti.
Ek test iki ayrı oturumla geçti.

## Doğrulama sınırları

Bu işte CI çalıştırılmadı.
Yerel sonuçlar CI sonucu sayılmaz.
Tam Platform Core test paketi çalıştırılmadı.
Yalnız yardım işinin ilgili testleri çalıştırıldı.
Tarayıcı testi bu sunucu değişikliğinin kapsamında değildir.
Üretim veritabanında şema güncellemesi denenmedi.
Kurulumdaki alanlar iki ayrı test sitesinde oluşturuldu.
Gerçek okurla denenmedi.
