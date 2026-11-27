# Yeni işin kurallarını yazın

PO, takımın işlerini tanımlayan ürün sorumlusudur. PO her yeni işte bu şablonu kullanır. İş tanımı, geliştiriciye uygulanacak kuralları ve beklenen sonucu gösterir.

## İş tanımını hazırlama adımları

PO şu adımları izler:

1. İstenen sonucu ve işin sınırını yazın.
2. Değişecek dosyaları veya bölümleri yazın.
3. İşe uyan kural dosyalarını aşağıdaki listeden seçin.
4. Seçtiğiniz dosyaların yollarını iş tanımına yazın.
5. Uygulanacak kural kodlarını kaynak dosyadan alın.
6. Her kural için denetlenecek sonucu yazın.
7. İlgili müşteri kararını [KARARLAR.md](KARARLAR.md) dosyasından bağlayın.
8. Eksik kararları ve beklenen yanıtı açıkça yazın.

Bir iş birden çok kural dosyasını kapsayabilir. PO yalnız dosya adını yazmakla yetinmez. PO geçerli kural kodlarını da belirtir.

## Kural dosyasını seçin

İşin değişen bölümüne göre şu dosyaları kullanın:

| İşin bölümü | Kural dosyası | Mevcut kod örneği |
| --- | --- | --- |
| Frappe içindeki Python kodu | [frappe-python-standartlari.md](frappe-python-standartlari.md) | G-4 |
| Frappe içindeki Python dışı dosyalar | [frappe-python-disi-standartlari.md](frappe-python-disi-standartlari.md) | J-1 |
| Frappe dışında çalışan ekran uygulaması | [headless-frontend-standartlari.md](headless-frontend-standartlari.md) | HZ-1 |
| Telefon uygulaması | [mobile.md](mobile.md) | KP-1 |

Bu kodlar örnektir. PO işin gerektirdiği diğer kuralları da seçer. PO mevcut kodları değiştirmez veya yeni kod uydurmaz.

## Doldurulacak iş alanları

PO şu alanları iş açıklamasına ekler:

| Alan | Yazılacak bilgi |
| --- | --- |
| Amaç | İş bitince oluşacak sonuç |
| Kapsam | Değişecek ve değişmeyecek bölümler |
| Kural dosyaları | Geçerli dosyaların depo içindeki yolları |
| Kural kodları | Her kodun kaynağı ve işteki karşılığı |
| Müşteri kararı | Karar başlığı ve karar kaydının bağlantısı |
| Kabul ölçütleri | Denenecek davranış ve beklenen sonuç |
| Kanıt | Test komutu, sonuç ve inceleme yorumunun bağlantısı |
| Eksik bilgi | Beklenen karar ve bu kararı isteyen kişi |

## Somut örnek

Bu örnek gerçek bir işin tamamlandığını göstermez. Örnek işte kullanıcı bir kayıt seçer. Geliştirici kayıt güncelleme işlemini düzeltir.

PO iş tanımına şu bilgileri yazar:

- Kural dosyası `docs/standartlar/frappe-python-standartlari.md` dosyasıdır.
- G-4 bu işe uygulanır.
- Kullanıcı hedef kaydı seçtiği için `ignore_permissions=True` kullanılmaz.
- Test, yetkisiz kullanıcının seçilen kaydı değiştiremediğini doğrular.
- QA, yani işi deneyen kişi, G-4 sonucunu inceleme yorumuna yazar.

Geliştirici kuralları [ilk yorumunda](developer-first-comment.md) belirtir. PO işi kapatırken [“Bitti” tanımını](definition-of-done.md) kullanır.

