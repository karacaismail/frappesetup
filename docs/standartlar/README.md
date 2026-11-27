# Kod standartları ve kararlar

Bu klasör platformun kod standartlarını toplar. Klasörde proje sahibinin kararları da var.

Kod yazan yapay zekâ araçları bu kurallara uyar. Bu araçlara ajan denir. Kurallar insan geliştiriciler için de geçerlidir.

## Tek doğruluk kaynağı

Bu klasör kuralların tek doğruluk kaynağıdır. Kuralı önce bu klasörde değiştirin.

Kuralların kopyaları iki yerde durur:

- ajanların ortak kural klasöründe,
- atonota-web deposunda.

Kopyalar bu klasörden eşitlenir. Kopyada yapılan değişiklik asıl kural sayılmaz. Örneğin bir kuralı yalnız atonota-web deposunda değiştirmeyin.

## Kural dosyaları

1. [frappe-python-standartlari.md](frappe-python-standartlari.md) Frappe'deki Python kodu içindir.
2. [frappe-python-disi-standartlari.md](frappe-python-disi-standartlari.md) Frappe'deki öteki dosyalar içindir. Örneğin JSON ve YAML dosyaları bu kapsamdadır.
3. [headless-frontend-standartlari.md](headless-frontend-standartlari.md) Frappe'nin dışında çalışan ekran uygulaması içindir.
4. [mobile.md](mobile.md) telefon uygulaması içindir. Uygulama PWA ya da Capacitor paketidir.
5. [naming_rules_report.md](naming_rules_report.md) koddaki adların nasıl seçileceğini anlatır. Bütün kod adları İngilizce olur.
6. [radius.md](radius.md) köşe yuvarlaklığı içindir. Dosya müşterinin yönergesidir. Başında bir odak istisnası notu var.
7. [frappe-guvenlik-onlemleri.md](frappe-guvenlik-onlemleri.md) müşterinin güvenlik önerilerini içerir. Kişi başlıkları yerine genel başlıklar kullanılır.

## Karar dosyaları

1. [KARARLAR.md](KARARLAR.md) proje sahibinin kararlarını toplar.
2. [SURECLER-VE-SONUCLAR.md](SURECLER-VE-SONUCLAR.md) dosyaların nasıl yazıldığını ve denetlendiğini anlatır.
3. [ACIK-ISLER.md](ACIK-ISLER.md) bekleyen kararları ve bitmemiş işleri toplar.

## Süreç belgeleri

Bu belgeler işin her adımında kurallara nasıl uyulacağını anlatır. Belgeleri A Takımı yazdı.

1. [task-template.md](task-template.md) PO'nun yeni işe kuralları nasıl yazacağını anlatır.
2. [developer-first-comment.md](developer-first-comment.md) geliştiricinin ilk yorumda hangi kuralları yazacağını anlatır.
3. [review-template.md](review-template.md) QA ile Committer'ın kural uyumunu nasıl inceleyeceğini anlatır.
4. [definition-of-done.md](definition-of-done.md) bir işin ne zaman “Bitti” olacağını anlatır.
5. [rule-change-process.md](rule-change-process.md) bir kuralın değişmesinin nasıl isteneceğini anlatır.

## Bilmeniz gerekenler

- Bu klasör sitenin bir parçası değildir. Site sayfaları bu dosyalardan üretilmez.
- Yeni kararlar sitenin karar sayfalarına henüz işlenmedi. Liste `ACIK-ISLER.md` dosyasındadır.
- Kural dosyaları aynı klasörde durmalıdır. Dosyalar birbirine bağlantı verir.
- Klasöre yeni dosya eklerseniz bu README'ye de bağlantısını ekleyin. Bir test bunu denetler.
- SaaS henüz kurulmadı. Kurallar gereksinimdir. Kurallar uygulanmış güvenlik gibi okunmamalıdır.
- Hukuki notlar hukuki görüş değildir. Son metni bir avukat onaylamalıdır.
