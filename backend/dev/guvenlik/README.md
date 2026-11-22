# Backend güvenlik denetimi

Depo kökünde `backend/dev/bin/guvenlik-denetimi` komutunu çalıştırın.
Komut için Python 3.9 veya üstü, `uvx` ve çalışan Colima gerekir.
İlk çalıştırmada araç paketlerinin ve Gitleaks imajının indirilmesi gerekebilir.

Komut aşağıdaki işleri yapar.

1. Semgrep kurallarını doğru ve hatalı örneklerle sınar.
2. Backend kaynak kodunu Semgrep ile denetler.
3. Gitleaks ile koda yazılmış gizli bilgileri arar.
4. Uç listesi betiğinin birim testlerini çalıştırır.
5. Tüm uçları ve misafire açık uçları ayrı ayrı listeler.
6. Her uç için iki yetki testi adı arar.

Bir adım başarısız olursa komut hata koduyla çıkar.
Gitleaks Git'in izlediği ve dışlamadığı yeni backend dosyalarını tarar.
Tarama, Git geçmişini kapsamaz.
Gitleaks sonucu gösterirken gizli değerleri örter.

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

Semgrep kodda tanımlı kalıpları arar. Yardımcı işlevlerin içini izleyerek karar vermez.
Misafir uçta Frappe'nin `rate_limit` işaretini kullanın.
`rate_limit` satırını `whitelist` satırının altına yazın.
Uç listesi bu sırayı ve işaretin içe aktarıldığı yeri denetler.
Her uçta HTTP yöntemlerini boş olmayan bir liste veya demetle yazın.
Çağrının içine doğrudan yazılan sorgu ve süre seçenekleri denetlenir.
Kod incelemesinde değişkene taşınan seçenekleri de denetleyin.
Zorunlu bir istisnayı ilgili işin karar kaydında açıklayın.

Uç listesi `backend/apps/<uygulama>/<paket>/` altındaki Python kaynaklarını okur.
Çalışırken eklenen uçlar için Frappe yapılandırmasını ayrıca inceleyin.
Sınıf yöntemini listede sınıf ve yöntem adıyla bulabilirsiniz.
Uygulama klasörü yoksa kapı hata verir.
