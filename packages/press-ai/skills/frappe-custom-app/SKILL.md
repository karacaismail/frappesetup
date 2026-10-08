---
name: frappe-custom-app
description: Yeni ya da mevcut bir Frappe özel uygulamasını press-ai MCP'nin app araçlarıyla workspace içinde geliştirir; yapıyı ve hedef sürüm (v15, v16) uyumunu statik denetler, iskelet üretir (DocType ve child table şeması, izinler, hooks, fixture filtresi, patch, test) ve iş mantığını tek dosyalık kod önerisiyle yazar. Her dosya öneri, insan onayı ve apply ile yazılır; davranış yalnız geliştiricinin koştuğu test çıktısıyla doğrulanır. Resmi bir uygulamanın davranışını değiştirmek için frappe-app-extension kullanılır.
---

# Frappe özel uygulama geliştirme

Workspace içindeki bir Frappe uygulamasının yapısını okur, statik kuralları denetler, iskelet üretir ve gerçek kodu tek
dosyalık önerilerle yazar. Her dosya değişikliği `app_propose_change` ile önerilir, insan ayrı terminalde onaylar,
`app_apply` yazar. Ajan dosyayı doğrudan yazmaz, bench veya kabuk çalıştırmaz. Paket taslak aşamasındadır; araçlar fixture
testleriyle doğrulanır.

## İskelet, kod, davranış

- İskelet türleri: app iskeleti; DocType ve child table şeması ile boş (`pass`) denetleyici; boş `execute()` taşıyan patch
  modülü; fixture filtresi; boş `doc_events` işleyicisi; yalnız `super().validate()` çağıran extend veya override sınıfı;
  boş test dosyası. İskelet tamamlanmış davranış değildir.
- Gerçek kod: iş mantığı, denetleyici davranışı, doğrulamalar, patch gövdesi ve test içeriği `write_file` türüyle
  (`app_file.write`) önerilir: uygulamaya göre göreli yol, tam dosya metni (en çok 200 KiB), amaç, mevcut dosya için
  zorunlu beklenen sha256 (yeni dosyada boş). Mevcut dosyanın içeriği ve sha256'sı aynı okumada
  `app_inspect {app_path, files}` ile alınır (en çok 20 dosya; gizli ve secret yollar okunmaz). İçerik desen maskelemesi
  olmadan birebir döner (yalnız yapılandırılmış Press kimlik değerleri maskelenir); gizli değere benzeyen metin
  `contains_secret_like_text: true` ile işaretlenir ve ajan bu metni yanıtında tekrarlamaz. Mevcut dosyada olmayan
  `[REDACTED]` içeriği reddedilir: tam metin her zaman bu birebir okumadan kurulur. Var olan her yol bileşeni diskteki adla
  harfi harfine yazılır; ad karşılaştırması harften bağımsızdır ve uyuşmazlık `case_mismatch` ile reddedilir. İzinli
  uzantılar: py, js, ts, vue, json, html, css, scss, md, txt, csv, po, pot.
  Onay ekranı diff'i önerideki içerikten üretir ve her dosyanın sha256'sını içerikle doğrular; onay özeti bu içeriği
  kapsar, `app_apply` tam o içeriği yazar ve taban değiştiyse reddeder.
- MCP kodu çalıştırmaz ve içe aktarmaz; yalnız Python ve JSON sözdizimini denetler. Sunucu Python'u uygulamanın
  `requires-python` alt sınırına yetişiyorsa ayrıştırma o sürümün dilbilgisiyle yapılır ve hata kesindir (ör. `>=3.10`
  uygulamada `type X = …` reddedilir). Yetişmiyorsa (ör. 3.9 sunucu) dosya UNCHECKED olur: metin taraması yine koşar, öneri
  `UNCHECKED <yol>` onay ifadesiyle çift onaya düşer ve kod elle incelemeye ve teste bırakılır.
- Reddedilen: f-string ya da format ile kurulmuş SQL (SEC002) ve misafir uçta `ignore_permissions` (SEC003). Mutlak sınırlar:
  secret, `.git`, `.github`, `.env`, çalışma zamanı dizinleri (`sites`, `env`, `logs`, `node_modules`), workspace dışı,
  `case_mismatch`, `[REDACTED]`, yapılandırma, veritabanı ve ikili dosyalar.
- Özel koddaki resmi modül monkey patch'i (EXT001) engellenmez; önizlemede `Warning EXT001 line N` risk uyarısıdır. Önerilmez:
  hooks, override ya da extend tercih edilir.
- Resmi uygulama (core) dosyaları (Press dahil) varsayılan olarak reddedilir: ilk istek `core_warning` döner ve öneri
  oluşmaz. Ajan uyarıyı (uygulamalar, dosyalar, gerekçeler, diff) kullanıcıya gösterir ve durur; kendiliğinden tekrar
  çağırmaz. Kullanıcı aynı değişikliği açıkça yeniden isterse aynı argümanlarla bir kez daha çağırır; öneri ayrı terminalde
  `APPROVE <digest12>` ve `CORE <uygulama>` (doğrulanmamış dosyada `CORE UNCHECKED <uygulama>`) onayı ister; `app_apply`
  CORE onayı olmayan core yolunu `core_not_approved` ile reddeder. Önerilen yol yine özel uygulama ve genişletme
  noktalarıdır; canlı Press'e dağıtım `press.code_fix` devridir, yerel press checkout düzenlemesi bu core akışıdır.
- Davranış yalnız geliştiricinin koştuğu `bench --site <site> run-tests --app <app>` gerçek çıktısıyla "geçti" sayılır;
  çıktı yoksa sonuç `not_run`dır. `bench migrate` ve testler yerelde insan komutudur.

## Kullan, kullanma

Kullan: "yeni app", "DocType ekle", "child table ekle", "izinleri ayarla", "patch yaz", "fixture ekle", "test ekle",
"bu app'i Press'e hazırla", "v15 ya da v16 uyumunu denetle".

Kullanma: ERPNext, HRMS, CRM gibi resmi uygulamanın davranışını değiştirmek (frappe-app-extension); Press'te build ve deploy
(press-operations).

## Önkoşullar

1. press-ai app araçları (`app_inspect`, `app_check`, `app_propose_change`, `app_apply`) yoksa dur, `not_run` raporla.
2. `kit_status`: workspace yazma izni ve izinli kök. Uygulama yolu bu kökün dışındaysa dur.
3. Hedef Frappe sürümü (`target_frappe`: `v15` ya da `v16`; dal adları `version-15`, `version-16`). Bilinmiyorsa sor; sürüme
   bağlı kural `unknown` kalır ve o değişiklik önerilmez.
4. Yeni app için lisansı kullanıcı seçer; varsayılan yoktur. Uygulama adı, modül adı ve yayımcı bilgisi kullanıcıdan gelir.

## Sıra

1. `app_inspect {app_path}`: app adı, modüller, DocType'lar, hooks anahtarları, patch'ler, fixture'lar, testler.
2. `app_check {app_path, target_frappe}`: başlangıç bulguları; `unknown` kuralları kaydet.
3. Küçük plan: bir öneride tek değişiklik, `write_file` için tek dosya. Sıra genelde app → DocType → child table →
   hooks, patch, fixture → denetleyici ve iş mantığı (`write_file`) → test içeriği (`write_file`).
4. `app_propose_change {app_path, change}`: dosya planını, diff'i ve sha256'yı göster; dur. İnsan onayı ayrı terminalde:

   ```sh
   python3 -I packages/press-ai/server.py approve <öneri-kimliği> --config <yapılandırma-yolu>
   ```

5. `proposal_get`: yalnız `approved` ise `app_apply` bir kez. Taban dosya hash'i değiştiyse apply reddedilir; yeniden
   `app_inspect`, yeni öneri. Çok dosyalı yazımda hata olursa yazım geri alınır; geri alma da başarısız olursa sonuç
   `failed_partial` ve geri alınamayan yollar döner, insan `git status` ve `git diff` ile bakar.
6. `app_check` yeniden; başlangıçla karşılaştır.
7. Yerel komutları insana ver (`app.install_local`, `app.migrate_local`, `app.run_tests_local`); çıktısı gelmeden sonuç
   `not_run`dır. Komutlar: [references/change-recipes.md](references/change-recipes.md).
8. Press'e çıkış: geliştirici commit ve push eder; ardından press-operations (gerekirse insan App ve App Source açar,
   `release_group.add_app`, `app_release.create`, candidate, build, deploy, `site.install_app` ya da `site.migrate`).

## Değişiklik türleri

| `change.kind` | Kontrat işlemi | Not |
| --- | --- | --- |
| `new_app` | `app.scaffold` | Lisans zorunlu; `target_frappe` app şablonunun Python aralığını belirler |
| `new_doctype` | `doctype.create` | Modül, alanlar, izin satırları, adlandırma |
| `add_child_table` | `child_table.create` | Child DocType ve üstteki Table alanı birlikte |
| `add_patch` | `patch.create` | Bölüm `pre_model_sync` ya da `post_model_sync` |
| `add_fixture_filter` | `fixtures.filter` | Filtresiz fixture önerilmez |
| `add_doc_event` | `hooks.doc_event` | İşleyici imzası `doc, method` |
| `extend_doctype_class` | `hooks.extend_class` | Daha çok frappe-app-extension kapsamı |
| `add_test` | `tests.scaffold` | Test tabanı sürüme göre |
| `write_file` | `app_file.write` | Tek dosya, tam metin; mevcut dosyada beklenen sha256 zorunlu |

Özel DocType izinleri (DocType JSON'unda izin değişikliği, izin taşıyan yeni DocType JSON'u) ve izin ya da rol fixture'ları
`write_file` ile önerilebilir; engellenmez, önizlemede rollerin önce ve sonrası not olarak görünür (Guest: giriş yapmamış
ziyaretçi, All: her kullanıcı). Bu notu kullanıcıya açıkça göster; Guest ya da All genişlemesi gerekçe ister. Ayrı tipli
`doctype.permissions`, `assets.include` ve `localization.translations` türleri planlıdır; bu dosyalar `write_file` ile onaylı
yazılır. Her durumda sonra `app_check`.

## Karar kuralları

- Uygulama adı paket adıdır ve hooks.py app_name, Press App adı ve App Source ile aynıdır.
- DocType adı kurulu tüm uygulamalarda tektir; alan adları standart sütun adlarıyla çakışmaz; özel önek kullanılır.
- Child table kendi iznini taşımaz; erişim üst belgeden gelir.
- İzinler en dar rol kümesiyle başlar; `has_permission` ve `permission_query_conditions` yalnız daraltır;
  `ignore_permissions` gerekçesiz kullanılmaz.
- hooks.py statik veridir; işleyicide `frappe.db.commit` yazılmaz.
- Fixture her migrate'te siteyi ezer: yalnız uygulamanın sahip olduğu kayıtlar, filtreyle.
- Patch tek sefer çalışır ve ikinci çalışmada etkisizdir; şemadan önce mi sonra mı çalışacağı açıkça seçilir.
- Uyum branch ucundan değil, release commit'inden okunur: `requires-python`, Frappe bağımlılık aralığı, Node `engines`,
  `required_apps`.
- Press sitesinde Desk'ten DocType oluşturulmaz; standart DocType yerel geliştirici bench'inde üretilip koda girer.
- Ayrıntı ve sürüm farkları: [frappe-app-model.md](../../references/frappe-app-model.md).

## Yapılmaz

Dosyayı doğrudan yazmak; bench, git veya kabuk çalıştırmak; lisans seçmek; üretim sitesinde geliştirici modunu açmak;
uygulama mantığını Server Script'e koymak; core akışı dışında resmi uygulama dosyasına yazmak; iskeleti ya da onaylanmış kodu çalışan davranış
saymak (test çıktısı yoksa `not_run`); kendi önerisini onaylamak.

## Başvurular

- Değişiklik tarifleri ve komutlar: [references/change-recipes.md](references/change-recipes.md)
- Frappe modeli ve sürüm kuralları: [frappe-app-model.md](../../references/frappe-app-model.md)
- Senaryolar: [scenarios.md](../../references/scenarios.md) (SC-14, SC-15)
