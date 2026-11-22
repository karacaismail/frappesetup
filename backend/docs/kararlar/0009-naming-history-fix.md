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

1. Orkestratör geçişi başlatınca eski Compose proje adını doğrulayın.
2. Kendi geliştirme projenizi eski Compose adıyla kapatın.
3. Ad değiştirme betiğini çalıştırın.
4. Yeni örnek dosyadan yerel ortam ayarlarını hazırlayın.
5. Kiracı ve Press test sitelerini yeni adlarla yeniden kurun.
6. Keycloak test alanını yeni istemci adlarıyla yeniden kurun.
7. İlgili işin test komutlarını yeniden çalıştırın.

Örneğin eski proje adı `fs-kiraci-dev` ise kapatma komutu şöyledir.

```sh
docker --context colima-factory compose -p fs-kiraci-dev -f backend/dev/compose.kiraci.yaml down
```

Aşağıdaki denetim eski ayar anahtarlarını gösterir. Ayar değerlerini yazdırmaz.

```sh
python3 backend/dev/naming/apply_renames.py --check-settings backend/dev/.env /path/to/site_config.json
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

1. Betiği `--dry-run` ile çalıştırın.
2. Listelenen dosyaları ve ad çakışmalarını inceleyin.
3. Aynı dosyalarda çalışan işlemleri bitirin.
4. Orkestratör geçişi başlatınca betiği kendi dalınızda çalıştırın.
5. Git farkını inceleyin ve ilgili testleri çalıştırın.

```sh
python3 backend/dev/naming/apply_renames.py --dry-run
```

Betik taşınacak dosyaları önce denetler. Hedef doluysa betik durur.
İş yarıda kesilirse Git farkını inceleyin. Sorunu giderince betiği yeniden çalıştırın.
Betik yalnız Git'in izlediği dosyaları taşır.
Betik ilgili uygulama varsa ortak sözlüğü uygulamanın köküne ekler.
