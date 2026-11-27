# Bir kuralın değişmesini nasıl istersiniz?

Takım mevcut kurala uyar. Takım kuralı değiştirmek isterse önce müşterinin kararını alır. **Müşteri kararı olmayan kural değişikliği birleşmez.**

## Karar alma adımları

Takım şu sırayı izler:

1. Geliştirici mevcut kural kodunu ve kaynak dosyayı yazar.
2. Geliştirici mevcut sorunu somut bir örnekle açıklar.
3. Geliştirici önerilen yeni metni yazar.
4. Geliştirici değişikliğin etkilediği işleri ve riskleri belirtir.
5. PO öneriyi müşterinin kararına sunar.
6. Müşteri öneriyi kabul eder veya reddeder.
7. PO kararı [KARARLAR.md](KARARLAR.md) dosyasına yazar.
8. Müşteri kabul ederse geliştirici onaylanan değişikliği uygular.
9. QA değişikliği kararın kapsamıyla karşılaştırır.
10. Committer karar kaydını denetler.

PO, takımın işlerini tanımlayan ürün sorumlusudur. QA, işi deneyen kişidir. Committer, dalı inceleyen ve birleştirme sürecini yürüten kişidir.

Müşteri yanıt vermezse öneri onaylanmış sayılmaz. Geliştirici karar bekleyen kural değişikliğini uygulamaz. Takım diğer bağımsız işleri sürdürebilir.

## Karar kaydının alanları

PO, `KARARLAR.md` kaydına şu bilgileri yazar:

| Alan | Yazılacak bilgi |
| --- | --- |
| Kural | Mevcut kod ve kaynak dosya |
| Eski metin | Değişmesi istenen hüküm |
| Yeni metin | Müşteriye sunulan öneri |
| Gerekçe | Sorun, somut örnek ve beklenen etki |
| Müşterinin kararı | Kabul veya ret ve kararın kapsamı |
| Tarih | Gün, ay adı, yıl ve gün adı |
| Kanıt | Müşterinin kararını gösteren kayıt bağlantısı |
| Etkilenen işler | Değişikliğin uygulanacağı görevler |

PO müşteri adına karar uydurmaz. Ajanın önerisi müşterinin onayı değildir. QA ve Committer yalnız kayıt başlığına bakmaz. İnceleyen kişiler kararın kaynağını ve kapsamını da doğrular.

## Somut örnek

GILT, ürünü farklı dil ve bölgelere hazırlama işlerinin ortak adıdır. İlgili kurallar [ayrı ekran kuralları](headless-frontend-standartlari.md) dosyasındadır. IC-9, çeviri anahtarlarının İngilizce ve ASCII yazılmasını ister. ASCII, bu örnekte Türkçe harf içermeyen karakter kümesini belirtir.

AJA-1309 kaynak işinde GILT için müşteri onayının kayıtlı olmadığı belirtilir. Bu eksiklik, kuralı değiştirme izni değildir.

Örneğin takım IC-9 içindeki İngilizce anahtar şartını kaldırmak istesin. PO bu öneriyi müşteriye sunar. PO müşterinin kararını `KARARLAR.md` dosyasına kaydeder. Müşteri kabul etmeden geliştirici bu değişikliği uygulamaz.

Karar yoksa Committer değişiklik dalını birleştirmez. Bu belge GILT için müşteri onayı vermez. Bu belge mevcut IC-9 kuralını değiştirmez.

## İnceleme ve kapatma

QA ve Committer karar kaydını [inceleme yorumunda](review-template.md) belirtir. PO işi kapatırken [“Bitti” tanımını](definition-of-done.md) kullanır. Otomatik belge denetimi müşteri onayını doğrulamaz.

