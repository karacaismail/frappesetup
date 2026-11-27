# G-138 bağlantılarının güncel backend dalına taşınması

Bu kayıt 26 Kasım 2026 Perşembe günü hazırlandı.
Görev AJA-1111 olarak geçer.
Ana görev AJA-1037 olarak geçer.

## Dal ve kapsam

Dal `pc/aja1037-g138-baglantilar-2` adını taşır.
Kaynak değişiklik `103fc3a2` commit'inden alındı.
İlk taban `1048bba7` commit'iydi.
Çalışma sırasında `backend` dalı `1be4324d` commit'ine ilerledi.
Dal yeni tabana taşındı.
Kod commit'i `25284706` olarak kaydedildi.

Yardım kayıtları üç isteğe bağlı bağlantı taşır.
Alanlar `tour_url`, `doc_url` ve `support_url` adlarını taşır.
Boş değerler yanıtta `null` olur.
Bileşen yardımı `component_id` ile seçilir.
Bileşen yardımı alan yardımıyla aynı seçim sırasını kullanır.
Eşleşme yoksa uç `200` durumuyla `message: null` döndürür.
Sunucu yalnız HTTPS adreslerini ve site içindeki göreli yolları kabul eder.
HTTPS, şifreli web bağlantısıdır.

Mevcut yardım kodu ve dil testleri korundu.
Yeni uç izin listesine ve modül sınırına eklendi.
OpenAPI sözleşmesi ve test imajının sözleşme kopyası güncellendi.
OpenAPI, uçların istek ve yanıt biçimini tanımlar.

## Önce test kanıtı

Testler koddan önce taşındı.
İlk koşuda 33 test çalıştı ve 34 hata oluştu.
Hatalar eksik bağlantı alanları ve işlevlerden kaynaklandı.
İlk kayıt testi, boşluk içeren adresin temizlenmediğini gösterdi.
Kaynak değişiklikteki temizleme satırı taşındı.
Bağımsız inceleme, bir hata metninde çeviri eşleşmesi buldu.
Hata metni çeviri kaydıyla eşlendi.

## İlgili testler

Aşağıdaki komut depo kökünde çalıştı.

```sh
PYTHONPATH=backend/apps/platform_core uv run --offline --no-project \
  --python "$HOME/.local/bin/python3.14" \
  --with PyYAML==6.0.3 --with jsonschema==4.26.0 python -B -m unittest \
  platform_core.shell.test_help_content platform_core.shell.test_help_links \
  platform_core.shell.test_help_contract platform_core.shell.test_help_topic_source
```

Saf işlev ve sözleşme testlerinin 34 tanesi geçti.
HTTP, gerçek web isteği yoludur.
Gerçek HTTP yolundaki 13 test geçti.
Frappe kayıt denetimindeki 13 test geçti.
Mevcut dil testleri bu kapsama dahildir.
İki kiracı aynı bileşen kimliğiyle farklı içerikler döndürdü.
Başka kiracıya taşınan oturum reddedildi.
Misafir ve rol nedeniyle ret durumları da geçti.

HTTP komutu test konteynerinin `sites` klasöründe çalıştı.

```sh
PLT_SHELL_TEST_SITE=test-shell.localhost \
PLT_SHELL_TEST_PORT=46381 \
PLT_HELP_FOREIGN_TEST_SITE=test-help-foreign.localhost \
/home/frappe/frappe-bench/env/bin/python -B -m unittest -v platform_core.api.test_help
```

Kayıt komutu test konteynerinin bench klasöründe çalıştı.

```sh
bench --site test-shell.localhost run-tests --app platform_core \
  --module platform_core.shell.test_help_api
```

İki test sitesinde `bench --site <site> migrate --skip-search-index` komutu çalıştı.
Kaynak görevin `fs-dev-ortam-46380` test ortamı yeniden kullanıldı.
Konteynerler mevcut imajla açıldı.
Güncel kaynaklar test konteynerine kopyalandı.
Başka projelerin kaynaklarına dokunulmadı.
Ağ havuzu dolduğu için göreve özel `10.254.111.0/24` aralığı kullanıldı.
Bu aralığın başka bir konteyner ağıyla çakışmadığı doğrulandı.
Testlerden sonra yalnız görev ortamı kapatıldı.
Birimler korundu.
Canlı sunucu ve canlı veri kullanılmadı.

## Sürümler ve biçim

Manifest Python `>=3.14,<3.15` ve Frappe `>=16.56.0,<17.0.0` aralıklarını ister.
Bu iş bağımlılık kilitlerini değiştirmedi.
Test imajı `frappe/erpnext:v16.55.0` özetini temel alır.
Yerel Python sürümü `3.14.7` olarak ölçüldü.
Test ortamında Python `3.14.10`, Frappe `16.56.0` ve Pydantic `2.12.5` ölçüldü.
Ruff `0.14.10` ile değişen 12 Python dosyası denetlendi.
`ruff check` ve `ruff format --check` komutları geçti.

Frappe kaynağı mevcut test imajında okundu.
`frappe/handler.py:56` boş dönüşte `message` alanını eklemiyor.
Yeni uç bu nedenle `frappe.response["message"] = None` değerini açıkça yazar.

## Dokuz kontrol

Dokuz komutun tümü yeni tabanda `0` çıkış koduyla bitti.
Aşağıdaki komutlar depo kökünde çalıştı.
`UV_OFFLINE=1` bütün komutlarda tanımlıydı.
`python3`, görevdeki geçici yol üzerinden Python `3.14.7` sürümüne bağlandı.
Kullanıcının genel ayarları değiştirilmedi.

```sh
backend/dev/bin/module-boundaries
backend/dev/bin/security-audit
backend/dev/bin/ai-readiness
"$HOME/.local/bin/python3.14" -B -m unittest discover -s backend/dev/tests
"$HOME/.local/bin/python3.14" -B -m unittest discover -s backend/dev/naming/tests
python3 -I -m unittest discover -s packages/press-ai/tests
"$HOME/.local/bin/python3.14" -I -m unittest discover -s backend/deploy/tests
"$HOME/.local/bin/python3.14" -I -m unittest discover -s packages/press-ai/tests
"$HOME/.local/bin/python3.14" -I packages/press-ai/server.py check-contract
```

| Kontrol | Sonuç |
| --- | --- |
| Modül sınırı | `pass` |
| Güvenlik | `pass` |
| Yapay zekâ uygunluğu | `pass` |
| Geliştirme testleri | `pass`, 182 testten 2 tanesi atlandı |
| Ad denetimi testleri | `pass`, 68 test |
| Press AI ilk koşu | `pass`, 164 testten 1 tanesi atlandı |
| Dağıtım testleri | `pass`, 198 testten 44 tanesi atlandı |
| Press AI ikinci koşu | `pass`, 164 testten 1 tanesi atlandı |
| Press AI sözleşmesi | `pass` |

Çekirdek çeviri kataloğu ve paket bildirimi yerelde yoktu.
Bu iki alt denetim `not_run` kaldı.
Press kılavuzu ve site haritası verisi de yoktu.
Bu iki sözleşme denetimi çalışmadı.
Tarama 443 dosyada 14 kuralı uyguladı.
Mevcut 58 bulgu kayıtlı gerekçeleriyle eşleşti.
İlk toplu koşu araç zaman aşımına uğradı.
Yukarıdaki sonuçlar tamamlanan son koşulardan alındı.

## Çakışma denemesi

Aşağıdaki komutlar `25284706` kod commit'inde `0` çıkış koduyla bitti.

```sh
git merge-base --is-ancestor refs/heads/backend HEAD
git merge-tree --write-tree --name-only refs/heads/backend HEAD
```

Karşılaştırılan `backend` ucu `1be4324d` commit'idir.
Birleşim ağacı `61425c2ee172b327cfe69244e8c5613a08a357c2` değeridir.
Deneme çakışma göstermedi.

## Güvenlik ve bağımsız inceleme

İlk güvenlik kontrolü eski kaynak özetini reddetti.
Bağımsız incelemeden sonra kaynak özeti yenilendi.
Yardım kaydının JSON ve Python dosyaları özet kapsamına eklendi.
İstisnaların kuralı, satırı ve gerekçesi değiştirilmedi.
Mevcut 58 istisna baştan incelenmedi.
İnceleyici, değişen kodun mevcut gerekçelere etkisini değerlendirdi.
İnceleyici son kod farkında eylem gerektiren bulgu bırakmadı.
İnceleyici komut çalıştırmadı ve dosya değiştirmedi.

## Sınırlar

CI çalıştırılmadı.
CI, uzak depodaki otomatik kontrol sürecidir.
Tam Platform Core test paketi çalıştırılmadı.
Tarayıcı testi bu sunucu değişikliğinin kapsamında değildir.
Üretim veritabanında şema güncellemesi denenmedi.
Gerçek okurla denenmedi.
Dalı uzak depoya gönderme işlemi yapılmadı.

Yazım denetimi otomatik araçla ve elle tamamlandı.
Uzun kelime uyarıları bağlam içinde incelendi.
