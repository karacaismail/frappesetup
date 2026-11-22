# Geçmiş kod adlarını değiştirme kararı

Karar 40, eski ve yeni kod adlarını kapsar. D-14, geçmiş adları düzeltme görevini tanımlar.
D-15 gereği çalışma yalnız Frappe 16'yı hedefler.

## Adların seçimi

Uygulamanın terim sözlüğü, Türkçe terimi ve İngilizce kod adını birlikte tutar.
Dal birleşince geçici sözlüğü ilgili uygulamanın `docs/glossary.yaml` yoluna alın.
Frappe'de bir kayıt türünün tanımına DocType denir.
Yeni DocType adları uygulama ön ekini alır.
`platform_core` için `PLT`, `press_tr` için `PTR` ve `hrms_tr` için `HRT` kullanılır.
Her iki uygulama adındaki `tr`, Türkiye'nin ülke kodudur.
`Identity` platforma, `Press Identity` Press uygulamasına aittir.
Bu ayrım, iki uygulamanın aynı Frappe modül adını kullanmasını önler.

## Geçiş yolu

Bu uçlar henüz yayımlanmadı. Uç, başka kodun ağ üzerinden çağırdığı işlevdir.
Bu yüzden iş dalları yeni adlara birlikte geçebilir.
Yayımlanmış bir uçta eski adı koruyun. Kullananlar geçince eski adı kaldırın.

`backend/dev/naming/rename-map.json` üzerinde uzlaşılan kod adlarını tutar.
Betik bu listede yazan adları değiştirir.
Betik belge içeriğini, kod yorumlarını ve görünen cümleleri korur.
Her iş sahibi kendi etiketlerini ve iletilerini sonra çevirir (O-21).
Betik yalnız değişen adların çeviri anahtarlarını günceller. Türkçe karşılıkları korur.
Eski proje kaydı ve sözleşme yollarında tek satırlık bağlantı kalır (O-22).
Standart belgeleri ve Pane dal adları geçiş kapsamı dışındadır.
Betik geliştirme sitesine, veritabanına veya Git geçmişine yazmaz.
Yeni site adları ve ayar anahtarları yerel kurulumda da kullanılmalıdır.

## Geliştirme sitelerini yeniden kurma

O-20 yalnız gerçek veri içermeyen geliştirme siteleri için geçerlidir.
Bu geçişte veri yaması ve `frappe.rename_doc` kullanılmaz.
Eski siteye `bench migrate` uygulamak eski tabloyu yeni ada taşımaz.

1. Geçişten önce eski Compose proje adınızı doğrulayın.
2. Kendi geliştirme projenizi eski komutla kapatın.
3. Yalnız yeniden kurulacak test ortamının birimlerini silin.
4. Ad geçişini “Dalda uygulama” bölümündeki sırayla yapın.
5. Yeni örnek dosyadan yerel ortam ayarlarını hazırlayın.
6. Kiracı ve Press test sitelerini yeniden kurun.
7. Keycloak test alanını yeni istemci adlarıyla kurun.
8. İlgili işin testlerini yeniden çalıştırın.

Kiracı projesi `fs-dev-ortam-${PANE_PORT}` adını kullanır.
İşçi kapatırken siteyi açtığı Pane portunu ve Colima profilini kullanır.

```sh
backend/dev/bin/compose down --remove-orphans
```

Keycloak projesinin varsayılan adı `fs-kimlik-realm` olur.
Farklı adla açtıysanız aynı `COMPOSE_PROJECT_NAME` değerini kullanın.
Press projesi `compose.press.yaml` dosyasında `fs-press-tr` adını kullanır.
İlgili dalda kendi projenizi şu komutla kapatın.

```sh
backend/identity/keycloak/bin/kc-dev.sh down --remove-orphans
backend/dev/press/compose.sh down --remove-orphans
```

O-20, yeniden kurulacak geçici sitenin birimlerini silmeye izin verir.
Kapatma komutu bu birimleri silmez. Siteyi açan işçi sahipliği doğrular.
Silme kapsamı aşağıdaki adlarla sınırlıdır.

| Ortam | Geçici birimler | Yerel imaj etiketi |
| --- | --- | --- |
| Kiracı | `fs-dev-ortam-${PANE_PORT}_kiraci-db`, `fs-dev-ortam-${PANE_PORT}_kiraci-sites`, `fs-dev-ortam-${PANE_PORT}_kiraci-logs` | `fs-kiraci-dev:${PANE_PORT}` |
| Keycloak | `fs-kimlik-realm_keycloak-db` | `fs-keycloak-atonota:dev-${KC_PORT}` |
| Press | `fs-press-tr_db`, `fs-press-tr_bench` | Paylaşılan `fs-press-tr-base:py3.14.8` korunur |

Ayrı Keycloak proje adı kullandıysanız birim de o ön eki taşır.
Keycloak olay kutusu `fs-kimlik-realm-event-sink:dev` etiketini kullanır.
Bu etiketi yalnız kendi geçici derlemenize aitse silin.
Paylaşılan imajları ve başka işlerin birimlerini koruyun.

Aşağıdaki denetim eski ayar anahtarlarını gösterir. Ayar değerlerini yazdırmaz.

```sh
python3.14 backend/dev/naming/apply_renames.py --check-settings backend/dev/.env /path/to/site_config.json
```

## Kaydedilen seçenekler ve durumlar

Seçim alanı, kullanıcının listedeki değerlerden birini seçmesini sağlar.
Seçim değerleri ve iş akışı durumları veritabanına kaydedilebilir.
Git taramasında taşınacak uygulama değeri bulunmadı.
Türkçe seçenekler, sonunda kendi kayıtlarını silen bir testte bulundu.
Betik bu seçenekleri `Red` ve `Blue` olarak düzeltir.
Test verisi için taşıma yaması eklenmedi.
İlk yayından sonra veri taşıma yaması gerekir.
Yama alanı ve eski değeri açıkça belirtmelidir.
Yamayı önce eski verinin bir kopyasında sınayın.

## Dalda uygulama

### Orkestratör

Orkestratör komutları `backend` dalının kökünde çalıştırır.
Çalışma ağacı temiz olmalıdır. İlk komut değişiklikleri önizler.

```sh
test -z "$(git status --porcelain=v1 --untracked-files=all)" &&
  python3.14 -B backend/dev/naming/apply_renames.py --repo "$PWD" --dry-run
```

Önizlemeyi inceleyin. Onaylı yama `backend/dev/naming/docs-rename.patch` yolundadır.
Taban değişmişse ve yama denetimi kalırsa adlandırma işi yamayı yeniler.
Ardından aşağıdaki komutları tek blok olarak çalıştırın.

```sh
cp2_docs_patch="${cp2_docs_patch:-backend/dev/naming/docs-rename.patch}"
test -z "$(git status --porcelain=v1 --untracked-files=all)" &&
  git apply --check "$cp2_docs_patch" &&
  git apply "$cp2_docs_patch" &&
  python3.14 -B backend/dev/naming/apply_renames.py --repo "$PWD" &&
  python3.14 -B backend/dev/naming/apply_renames.py --repo "$PWD" --check-modules &&
  python3.14 -B backend/dev/naming/check_names.py --root "$PWD" --transition &&
  python3.14 -B -m unittest discover -s backend/dev/tests
```

Bir denetim kalırsa komut hata koduyla durur. Git kaydı oluşturmayın.
Belgeyi kodla karşılaştıran testler için yamayı ad geçişiyle aynı Git kaydına alın.

### İşçi dalı

1. Orkestratör önce `backend` dalında ad geçişini tamamlar.
2. İşçi temiz çalışma ağacında `backend` dalını birleştirir.
3. İşçi birleşen dalın betiğiyle önizleme yapar.
4. İşçi önizlemede dosyaları ve çakışmaları inceler.
5. İşçi uygulama komutunu kendi dalında çalıştırır.

Geçiş için Python 3.14 kullanın. Betik Python 3.12 öncesinde durur.
Aşağıdaki komutları kendi Git çalışma alanınızın kökünde çalıştırın.

```sh
env -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL git merge refs/heads/backend
python3.14 backend/dev/naming/apply_renames.py --repo "$PWD" --dry-run
PYTHON=python3.14 backend/dev/naming/apply-to-branch -- \
  python3.14 -B -m unittest discover -s backend/dev/tests
```

Geçiş komutuna kendi işinizin Python testlerini verin.
Komut temiz çalışma ağacı ister. Komut yerel `backend` dalının birleştiğini denetler.
Komut adları uygular. Sonra eski adları ve verilen testi denetler.
Komut ad haritasındaki eski adları bulursa durur.
Komut genel ad kurallarının bulgularını uyarı olarak gösterir.
Tüm denetimler geçerse komut değişiklikleri tek Git kaydına alır.
Denetim durursa değişiklikler inceleme için çalışma ağacında kalır.
Yeni değişiklik yoksa komut yeni Git kaydı oluşturmaz.
Eski modül atfı kalırsa işçi dosya ve satırı adlandırma işine bildirir.
İşçi eski adı elle değiştirmez. Adlandırma işi dar kuralı ekler.
İşçi güncel kuralla temiz kopyada denemeyi tekrarlar.

İş yarıda kesilirse önce `git status` ve `git diff HEAD` çalıştırın.
Yalnız geçişe ait kaydedilmemiş değişiklikler varsa bunları geri alabilirsiniz.
`git reset --hard HEAD` izlenen dosyalardaki kaydedilmemiş değişiklikleri siler.
Kendi düzenlemeniz varsa bu komutu çalıştırmayın.
`git status` altında kalan izlenmeyen dosyaları tek tek inceleyin.
Çalışma ağacı temiz olunca uygulama komutunu tekrar çalıştırın.

## Bütün çalışma ağaçlarında önizleme

[Orkestratörün çalışma ve geri dönüş adımları](../../dev/naming/README.md#ikinci-kontrol-noktası) README dosyasındadır.

Komutu depo kökünde çalıştırın. Sürücü her çalışma ağacının Git kaydını kopyalar.
Sürücü geçici kopyalarda ad geçişini ve testleri çalıştırır.
Sürücü sonuçları tek JSON raporuna yazar. Hata varsa 1 koduyla çıkar.
Varsayılan kip yeni Git kaydı oluşturmaz. Sürücü kopyaları sonunda kaldırır.

```sh
python3.14 -B backend/dev/naming/run_cp2.py
```

Sürücü varsayılan olarak `backend/dev/tests` testlerini çalıştırır.
Başka bir test komutu vermek için komutu `--` sonrasına yazın.
Bir dal güncel `backend` kaydını içermiyorsa geçiş komutu durur.
Sürücü bu sonucu rapora yazar ve diğer kopyalara geçer.

Orkestratör Pane oturumunda `--apply` seçeneğini kullanabilir.
Bu kip Git kayıtlarını yalnız geçici kopyalarda oluşturur.
Sürücü yazar korumasının çalıştığını denetler.
Rapor, Git kaydı oluşan kopyanın yolunu gösterir.
Sürücü `backend` ve `main` kopyalarını yalnız önizler.

## Uygunluk kapısında ad denetimi

O-30 gereği kapı, ad denetimi kipini `backend/dev/naming/enforcement.json` dosyasından okur.
`advisory` kipinde kapı ad bulgularını uyarı olarak yazar.
Dosya yoksa kapı `advisory` kipini kullanır ve bunu çıktıda belirtir.
Bütün dallarda ad değişimi bitince orkestratör değeri `enforce` yapar.
`enforce` kipinde şu dört kuralın bulguları kapıyı durdurur:

- `legacy-name`
- `turkish-name`
- `module-name`
- `translation-binding`

Kapı diğer ad bulgularını her iki kipte de uyarı olarak yazar.

## Belgelerdeki eski kod adları

Orkestratör, belgelerde kalan eski kod adlarının listesini yönetir.
Aşağıdaki komut listeyi dosya ve satır bilgisiyle verir.
Komut Markdown dosyalarını değiştirmez.

```sh
python3.14 backend/dev/naming/apply_renames.py --repo "$PWD" --report-docs
```

Bir dal eski proje kaydına ya da sözleşmeye satır eklediyse çakışma çıkabilir.
İşçi eklediği satırı yeni dosyaya taşır. Eski yoldaki bağlantıyı korur.
Taşınan bir klasöre yeni dosya eklenmişse dosyayı yeni klasör yoluna alın.
İki dal aynı kod satırını değiştirdiyse ilgili sahipler iki değişikliği karşılaştırır.
