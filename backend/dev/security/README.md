# Backend güvenlik denetimi

Depo kökünde `backend/dev/bin/security-audit` komutunu çalıştırın.
Komut için Python 3.9 veya üstü, `uv`, `uvx` ve çalışan Colima gerekir.
Bandit adımı sabitlenmiş Python 3.12 ortamında çalışır.
İlk çalıştırmada araç paketlerinin ve Gitleaks imajının indirilmesi gerekebilir.

Komut aşağıdaki işleri yapar.

1. Bandit ile Git’in izlediği backend Python dosyalarını tarar.
2. Semgrep kurallarını doğru ve hatalı örneklerle sınar.
3. Backend kaynak kodunu Semgrep ile denetler.
4. Gitleaks ile koda yazılmış gizli bilgileri arar.
5. Uç listesi betiğinin birim testlerini çalıştırır.
6. Tüm uçları ve misafire açık uçları ayrı ayrı listeler.
7. Her uç için iki yetki testi adı arar.

Bir adım başarısız olursa komut hata koduyla çıkar.
Gitleaks Git'in izlediği ve dışlamadığı yeni backend dosyalarını tarar.
Tarama, Git geçmişini kapsamaz.
Gitleaks sonucu gösterirken gizli değerleri örter.
Bandit önce bilinen hatalı örneği sınar. Ardından örnek klasörlerini kapsam dışında tutar.
Bandit, Python ile başlayan uzantısız betikleri de tarar.
`# nosec` yorumu tarama sonucunu değiştirmez.
Kullanılmayan Bandit istisnası ya da açık bulgu kapıyı durdurur.

## Her uç için iki test

Uç, sunucunun istek kabul eden bir işlemidir.
`@frappe.whitelist` işareti Frappe'ye işlemi dışarıdan çağırma izni verir.
`notlar.py` içindeki `oku` ucu için aynı klasöre `test_notlar.py` ekleyin.

- `test_oku_guest_denied` girişsiz isteğin korunan işlemi yapamadığını doğrular.
- `test_oku_foreign_data_denied` kullanıcının başkasına ait korunan kayda erişemediğini doğrular.

İşlev bir sınıftaysa test adında sınıfı da yazın.
Örneğin `Not.oku` için `test_Not_oku_guest_denied` adını kullanın.
Uç `__init__.py` içindeyse test dosyası `test___init__.py` olur.
Testleri dosya düzeyinde veya test sınıfında tanımlayabilirsiniz.

Testleri gerçek istek yolundan çalıştırın. Uydurma kişi ve kayıt kullanın.
Misafire açık uçta, girişsiz kişinin korunan veriyi alamadığını sınayın.
Eksik test adı kapıyı durdurur. Betik testin içeriğini veya sonucunu ölçmez.
İlgili uygulamanın test komutu bu davranışı ayrıca sınar.

## Kuralların kapsamı

Semgrep kodda tanımlı kalıpları arar.
Yeni kurallar aynı işlev içinde verinin kaynaktan kullanıldığı yere akışını izler.
Kurallar, yardımcı işlevler ve dosyalar arasındaki akışı kapsamaz.

- Ham istek adresi ve yanıt gövdesi günlükte görünmemeli.
- Testin hata iletisi ham yanıt içermemeli. Durum kodu yeterliyse onu kullanın.
- İşletim sistemine verilen komut argümanında gizli değer bulunmamalı.
  Aracın desteklediği korumalı giriş yolunu kullanın.

Olumlu ve olumsuz denemeler `backend/dev/security/fixtures/` altındadır.
Misafir uçta Frappe'nin `rate_limit` işaretini kullanın.
`rate_limit` satırını `whitelist` satırının altına yazın.
Uç listesi bu sırayı ve işaretin içe aktarıldığı yeri denetler.
Her uçta HTTP yöntemlerini boş olmayan bir liste veya demetle yazın.
Çağrının içine doğrudan yazılan sorgu ve süre seçenekleri denetlenir.
Kod incelemesinde değişkene taşınan seçenekleri de denetleyin.
Zorunlu bir istisnayı ilgili işin karar kaydında açıklayın.

Press istisnalarının gerekçeleri `semgrep-exceptions.json` dosyasındadır.
Kapı, listedeki dosyaların ve Semgrep kural dosyasının özetini karşılaştırır.
Özet taramadan önce veya sonra farklıysa kapı istisnayı uygulamaz.
Dosya, satır ve kural kimliği de birebir eşleşmelidir.
Listedeki dosyalardan biri veya Semgrep kuralı değişirse istisnaları yeniden inceleyin.
İnceleme bitince depo kökünde şu komutu çalıştırın.

```sh
python3 -B backend/dev/security/semgrep_exceptions.py --snapshot
```

Komut her kapsam için bir özet yazdırır.
Özet `null` ise kapsama ait onayları yenilemeyin.
Onayları inceleyince yeni özeti aynı kapsamın `sha256` alanına yazın.
Ardından `backend/dev/bin/security-audit` komutunu çalıştırın.

Press onaylarının tam listesi ilk kaydın `files` alanındadır.
`--snapshot` çıktısında bu kayıt `backend` anahtarının altında görünür.
Liste şu dosyaları kapsar.

- `backend/apps/press_tr/press_tr/api/` altındaki beş onaylı uç dosyası.
- `press_identity/` altındaki hesap, kimlik, oturum ve anonimleştirme dosyaları.
- Aynı klasördeki silme, servis, OIDC, makine ucu ve istek denetimi yardımcıları.
- Kimlik bağının ve oturum eşlemesinin DocType tanımı ile kodu.
- Press kancaları, Press paket bildirimi ve `backend/libs/oidc_verify/` doğrulama kitaplığının kaynakları.
- OIDC kitaplığının paket bildirimi.

Takım alanının tekilliğini tanımlayan `press_identity/custom/team.json` da özete girer.
Press belgeleri ve test çalıştırma betikleri bu özete girmez.
Ansible köprüsü yalnız yükleyiciyi ayarlar. Yetki kararı vermediği için özete girmez.

Erişim onayları yalnız listelenen dosyalara bağlıdır.
Aşağıdaki yollar `backend/apps/platform_core/platform_core/` klasörüne göredir.

- `access/link_search.py` ve `api/access.py`, incelenen beş ucu tanımlar.
- `access/explain.py`, yetki açıklamasını ve kapsam özetini üretir.
- `access/rules.py`, belge türünün erişim kurallarını okur.
- `access/engine.py` ve `access/subject.py`, yetki kararını ve kullanıcı kapsamını hesaplar.
- `hooks.py` ve `access/hooks.py`, Frappe izin ve arama kancalarını bağlar.
- `access/reports.py`, izin kancasındaki rapor ve rapor dosyası koşullarını sağlar.

Kapsam dışındaki dosya değişikliği bu özeti değiştirmez.
İki onay kapsamı çakışırsa kapı hata verir.

Uç listesi `backend/apps/<uygulama>/<paket>/` altındaki Python kaynaklarını okur.
Çalışırken eklenen uçlar için Frappe yapılandırmasını ayrıca inceleyin.
Sınıf yöntemini listede sınıf ve yöntem adıyla bulabilirsiniz.
Uygulama klasörü yoksa kapı hata verir.
