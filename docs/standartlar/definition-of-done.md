# Bir işi ne zaman “Bitti” yapabilirsiniz?

PO, takımın işlerini tanımlayan ürün sorumlusudur. PO işi kapatmadan önce kabul ölçütlerini ve inceleme kanıtlarını denetler. **Kural uyumu denetlenmeyen iş “Bitti” olmaz.**

## Kapatma koşulları

PO şu koşulların tamamını doğrular:

1. İş tanımı geçerli kural dosyalarını belirtir.
2. Geliştiricinin ilk yorumu uygulanacak kural kodlarını belirtir.
3. Geliştirici kabul ölçütlerinin sonucunu kanıtıyla yazar.
4. QA kendi inceleme yorumuna kural uyum listesini ekler.
5. Committer kendi inceleme yorumuna kural uyum listesini ekler.
6. İki liste de incelenen son commit kimliğini belirtir.
7. Geçerli kuralların bütün satırlarında “uygun” sonucu vardır.
8. “Kapsam dışı” satırlarının gerekçesini QA ve Committer doğrular.
9. Kural değişikliği varsa müşterinin kararı kayıtlıdır.

QA, işi deneyen kişidir. Committer, dalı inceleyen ve birleştirme sürecini yürüten kişidir. Commit, Git içindeki değişiklik kaydıdır.

Bir koşul eksikse PO işi kapatmaz. PO eksik kanıtı veya düzeltmeyi ilgili kişiden ister. PO yalnız geliştiricinin “tamamlandı” yorumuna dayanarak işi kapatmaz.

## Kabul edilen kanıt

Kural uyumunun kanıtı, [inceleme yorumundaki uyum listesidir](review-template.md). PO kapanış yorumuna QA ve Committer yorumlarının bağlantılarını yazar. PO dal adını ve incelenen commit kimliğini de ekler.

Test kaydı, gerçek komutu ve sonucu içerir. Çalıştırılmayan kontrol açıkça belirtilir. Zorunlu kontrol çalıştırılmadıysa iş “Bitti” olmaz.

Bir listede “uygun değil” veya “denetlenmedi” varsa dal birleşmez. Eksik liste de birleştirmeyi durdurur. Yeni commit gelirse etkilenen kuralların incelemesi yenilenir.

## Somut örnek

Bu örnek gerçek bir teslimin kanıtı değildir. Örnekte geliştirici kayıt güncelleme testinin geçtiğini yazar. Ancak QA yorumunda G-4 satırı yoktur.

G-4, [Python kuralları](frappe-python-standartlari.md) dosyasında tanımlıdır. Bu kural izin denetimini atlayan kullanımları sınırlar. PO kuralın incelendiğini doğrulayamadığı için işi kapatmaz.

QA ve Committer G-4 uyumunu kanıtıyla kendi yorumlarına yazar. Diğer koşullar da sağlanırsa PO işi “Bitti” yapar.

## Belge denetiminin sınırı

Otomatik belge denetimi, gerçek işin tamamlandığını kanıtlamaz. Denetim görev yorumlarını okumaz. PO inceleme yorumlarını ayrıca kontrol eder.

Bu süreç için gerçek okur denemesi önerilir. Gerçek okurla denenmedi.

