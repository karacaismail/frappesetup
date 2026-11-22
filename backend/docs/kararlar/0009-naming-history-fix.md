# Geçmiş kod adlarını değiştirme kararı

D-12 yeni adları kapsar. D-14 geçmiş adları da bu görev kapsamında düzeltir.

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
Belge başlıkları ve Türkçe anlatım korunur. Belge yolları ve teknik atıflar güncellenir.
Kodda geçen cümlelerin çevirisi ayrı bir kontrol noktasında yapılır.
Çeviri dosyaları, standartlar ve Pane dal adları geçiş kapsamı dışındadır.
Betik geliştirme sitesine, veritabanına veya Git geçmişine yazmaz.
Yeni site adları ve ayar anahtarları yerel kurulumda da kullanılmalıdır.
İkinci kontrol noktasında yerel siteyi yeniden kurma adımları belgelenir.

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
