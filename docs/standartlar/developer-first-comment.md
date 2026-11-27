# İşe başlarken kuralları yazın

Geliştirici kod yazmadan önce işin kural dosyalarını okur. Geliştirici ilk görev yorumunda uygulayacağı kural kodlarını yazar. Bu yorum, kurala uyulduğunun kanıtı değildir.

## İlk yorumu hazırlama adımları

Geliştirici şu adımları izler:

1. İş tanımını ve kabul ölçütlerini okuyun.
2. İşte belirtilen kural dosyalarını okuyun.
3. İlgili kararları [KARARLAR.md](KARARLAR.md) dosyasından okuyun.
4. İşin gerektirdiği eksik kural dosyalarını belirleyin.
5. Okuduğunuz dosyaları ilk görev yorumuna yazın.
6. Uygulayacağınız kodları kaynak dosyadaki biçimiyle yazın.
7. Her kodun işteki karşılığını açıklayın.
8. İlk çalıştıracağınız testi ve beklenen sonucu yazın.

Kural veya karar belirsizse geliştirici eksikliği PO'ya bildirir. PO, takımın işlerini tanımlayan ürün sorumlusudur. Geliştirici belirsizliğe bağlı değişikliği bekletir. Geliştirici kalan bağımsız işi sürdürür.

## İlk yorumun alanları

Geliştirici şu bilgileri görev yorumuna yazar:

| Alan | Yazılacak bilgi |
| --- | --- |
| Okunan kaynaklar | Kural dosyalarının yolları ve ilgili karar başlığı |
| Uygulanacak kurallar | Kural kodu, kaynak dosya ve yapılacak iş |
| İlk test | Test komutu ve beklenen başarısızlık |
| Eksik bilgi | Beklenen karar veya açıklama |
| Çalışma dalı | Değişikliği taşıyan Git dalının adı |

Git dalı, değişikliklerin ayrı tutulduğu çalışma koludur. İşin kapsamı değişirse geliştirici yeni bir yorum yazar. Geliştirici hangi kuralların eklendiğini açıkça belirtir.

## Somut örnek

Aşağıdaki yorum yalnız örnektir. Örnek iş, ayrı ekran uygulamasındaki arama alanını düzeltir.

> `docs/standartlar/headless-frontend-standartlari.md` dosyasını okudum.
> HZ-1 uyarınca önce ortak arama bileşenini inceleyeceğim.
> TE-1 uyarınca önce hatayı gösteren testi yazacağım.
> Test, arama temizlendiğinde kayıtların geri gelmesini denetleyecek.
> Testin beklenen nedenle başarısız olduğunu göreceğim.
> Sonra düzeltmeyi yapacağım.
> Aynı testi yeniden çalıştıracağım.
> Sonuçları bu göreve yazacağım.

HZ-1 ve TE-1, [ayrı ekran kuralları](headless-frontend-standartlari.md) dosyasında tanımlıdır. Gerçek yorumda geliştirici kendi test komutunu da yazar. Geliştirici çalışma dalını ve ilgili karar kaydını ekler.

İş bitince geliştirici [inceleme şablonuyla](review-template.md) denetim ister.

