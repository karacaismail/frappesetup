# Değişiklik tarifleri

Her tarif: ne zaman, öneriden önce ne okunur, onaydan sonra ne doğrulanır, insanın çalıştıracağı komut, Press etkisi.
Parametrelerin kesin şeması runtime'dadır (`contract_get` ve öneri sonucu). Yer tutucular: `<app>`, `<site>`,
`<test-site>`, `<modül>`, `<DocType>`.

| Tür | Ne zaman | Önce | Sonra | Press etkisi |
| --- | --- | --- | --- | --- |
| `new_app` | Yeni uygulama | Lisans, ad, yayımcı, hedef sürüm kullanıcıdan | `app_check`; depo ve ilk commit insanda | İnsan App ve App Source açar; `release_group.add_app` |
| `new_doctype` | Yeni kayıt türü | DocType adı kurulu app'lerde yok; modül modules.txt'de; alan adları standart sütunlarla çakışmıyor | `app_check`; yerel migrate | Yeni release, build, deploy, site migrate |
| `add_child_table` | Belgeye satır listesi | Üst DocType bu app'te; child adı tekil | `app_check`; yerel migrate | Aynı |
| `add_patch` | Veri taşıma, yeniden adlandırma | Bölüm seçimi: eski şemayı okuyan `pre_model_sync`, yeni şemayı gerektiren `post_model_sync`; ikinci çalışmada etkisiz mi | Yerel migrate iki kez: ikinci koşu değişiklik yapmamalı | Site migrate sırasında bir kez çalışır |
| `add_fixture_filter` | Custom Field, Property Setter, Role gibi kayıtları kodla taşımak | Filtre yalnız bu app'in kayıtlarını seçiyor (modül ya da ad öneki) | İnsan dışa aktarır, fixture dosyasını gözden geçirir | Her migrate'te zorla uygulanır; sitedeki elle düzenleme geri döner |
| `add_doc_event` | Kaydetme, gönderme, iptal gibi olaya yan etki | Olay adı ve işleyici yolu çözülüyor; işleyicide commit yok | Test; yerel deneme | Yeni release, build, deploy |
| `add_test` | Değişen davranışa regresyon testi (iskelet) | Hedef sürüm biliniyor (v15 FrappeTestCase, v16 IntegrationTestCase) | İçerik `write_file` ile; testi insan koşar | Yok |
| `write_file` | İş mantığı, denetleyici davranışı, patch gövdesi, test içeriği (gerçek kod) | Yol uygulamaya göre göreli; resmi uygulama dosyası core akışına girer (uyarı, kullanıcının açık tekrarı, CORE onayı); uzantı izinli; mevcut dosyanın içeriği ve zorunlu sha256'sı `app_inspect {app_path, files}` ile; özel izin değişikliği önizlemede not olarak görünür; kod çalıştırılmaz, yalnız sözdizimi denetlenir | `app_check`; geliştirici testi koşar ve çıktıyı verir | Yeni release, build, deploy; şema değiştiyse migrate |

`extend_doctype_class` türü resmi uygulama sınıflarını genişletmek içindir; karar frappe-app-extension skill'indedir.

## İnsan komutları

Ajan bunları çalıştırmaz; metni verir, çıktı gelmeden sonuç `not_run`dır. Bench dizininde çalıştırılır.

```sh
# app.install_local
bench get-app <repo-adresi-veya-yerel-yol>
bench --site <site> install-app <app>

# app.migrate_local
bench --site <site> migrate

# app.run_tests_local (test sitesinde)
bench --site <test-site> set-config allow_tests true
bench --site <test-site> run-tests --app <app>
bench --site <test-site> run-tests --doctype "<DocType>"

# Asset ve fixture
bench build --app <app>
bench --site <site> export-fixtures --app <app>
```

## Press'e çıkış kontrol listesi

1. pyproject.toml: `requires-python` ve Frappe bağımlılık aralığı hedef grubun sürümüyle uyumlu; package.json `engines`
   grubun Node sürümünü kapsıyor.
2. hooks.py: app_name paket adıyla aynı; `required_apps` eksiksiz; bağımlı app'ler grupta önce.
3. Branch: hedef sürüm dalı repoda var; Press'e verilecek commit push edilmiş.
4. Testler insan tarafından koşulmuş ve çıktısı kaydedilmiş; koşulmadıysa `not_run` yazılır.
5. Ardından press-operations sırası: App ve Source (insan, gerekiyorsa), `release_group.add_app`, `app_release.create`,
   candidate, build, deploy, site işi.
