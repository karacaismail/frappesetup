---
title: "ProPR ile PR denetimi"
nav: "ProPR"
order: 26
---

Bu sayfa ProPR'ın bu projede nasıl kullanıldığını anlatır. Kurulum bilgileri 22 Kasım 2026 Pazar günü yerel kurulumda doğrulandı. PR akışı 27 Kasım 2026 Cuma günü değişti. Yeni akış Karar 47'dir. Adım adım kurulum belgesi depoda [`Propr_setup`](https://github.com/karacaismail/frappesetup/tree/main/Propr_setup) klasöründedir.

## Kullanım amacı

ProPR, GitHub'daki PR'ları izleyen açık kaynak bir uygulamadır. ProPR bu bilgisayarda yerel olarak çalışır.

ProPR bu projede PR'ları birleştirir. ProPR şu işleri yapar:

- `karacaismail/frappesetup` deposundaki PR'ları ve CI sonuçlarını okur.
- Durumu kendi panosunda gösterir.
- PR'ı hedef dala birleştirir. Gerekirse çakışmayı çözer.
- Yalnız depo sahibinin tetiklemesine izin verir.

ProPR'ın yazdığı her commit'in yazarı ve committer'ı depo sahibidir. Kimlik `karacaismail` hesabıdır. Bu kural birleştirme ve çakışma çözme commit'lerini de kapsar. Ayrıntı "Commit kimliği" bölümündedir.

22 Kasım 2026 Pazar günü ProPR yalnız gözlemciydi. O gün ProPR commit atmıyor ve PR birleştirmiyordu. Bu sınır 27 Kasım 2026 Cuma günü kalktı.

## PR akışı

`backend` dalı GitHub'dadır. `backend` dalına girişler PR ile olur. İş şu sırayla ilerler:

1. Geliştirici işi kendi dalında yapar. Dal güncel `origin/backend` ucundan açılır.
2. Geliştirici dalı GitHub'a gönderir.
3. Committer dalı `backend` dalına PR olarak açar.
4. GitHub, `ci.yml` iş akışındaki testleri çalıştırır.
5. QA ve Committer PR'ı kural listesiyle inceler.
6. ProPR PR'ı `backend` dalına birleştirir. Çakışma varsa ProPR çözer.

Hiçbir ajan `backend` dalına yerelde birleştirme yapmaz. Hiçbir ajan `backend` dalına doğrudan push etmez.

`main` dalına yayın ayrı bir PR ile girer. Her yayın `main` dalına tek commit olarak girer.

GitHub'ın birleştirme düğmesi kullanılmaz. Otomatik birleştirme de kapalıdır.

Testler kalırsa QA işi geliştiriciye geri verir. Geliştirici hatayı düzeltir. Sonra iş yeniden incelenir.

### Commit kimliği

ProPR'ın oluşturduğu her commit'in yazarı ve committer'ı `karacaismail` hesabıdır. Bu commit'ler şunlardır:

- hedef dalı PR dalına birleştiren commit'ler,
- çakışma çözen commit'ler,
- ProPR'ın kendi yazdığı düzeltme commit'leri.

ProPR Git'i hook'lar kapalı çalıştırır. Bu yüzden yerel yazar koruması ProPR commit'lerini denetlemez. Kimliği ProPR'ın iki ayar değişkeni verir. Değişkenler ProPR'ın `.env` dosyasındadır. Değişkenler boş kalırsa ProPR yazar olarak kendi bot adını yazar.

PR'ın son birleşme commit'ini GitHub'ın birleştirme servisi oluşturur. Bu commit'in committer alanına GitHub yazılır. Proje sahibi bu tek istisnayı kabul etti.

## GitHub bağlantısı

ProPR, GitHub'a kendi GitHub uygulamamızla bağlanır. Uygulamanın adı `frappesetup-propr-gate` olur.

22 Kasım 2026 Pazar günü uygulamanın yedi izni vardı. Yedisi de yalnız okumaydı:

- Actions
- Checks
- Commit statuses
- Contents
- Issues
- Metadata
- Pull requests

Uygulama yalnız bu depoya kuruldu. Webhook kapalıdır. ProPR değişiklikleri belirli aralıklarla GitHub'a sorar. Bu yönteme "polling" denir.

ProPR'ın kendi hazır hizmeti "ProPR Connect" adını taşır. Bu hizmeti seçmedik. Nedenleri şunlardır:

- Hazır hizmetin izinleri sabittir ve yazma izni içerir.
- Hazır hizmette erişim belirteçlerini dış bir sunucu üretir.
- Kendi uygulamamızda izinleri biz seçeriz.

ProPR'ın web girişi de aynı uygulamayı kullanır. Giriş, bu bilgisayardaki `localhost` adresine döner.

## Kurulum süreci

Kurulum yedi ana adımdan oluşur. Ayrıntılı komutlar kurulum belgesindedir.

1. ProPR için ayrı bir Colima profili açılır. Profilin adı `propr` olur.
2. ProPR'a ayrı bir Docker ayar klasörü verilir.
3. GitHub uygulaması oluşturulur ve depoya kurulur.
4. ProPR'ın kurulum ekranında kendi uygulamamız seçilir.
5. Depo sahibi GitHub'dan giriş yapar.
6. Depo ProPR'a eklenir.
7. MCP için yerel HTTPS vekili kurulur.

### Neden ayrı bir Colima profili

Geliştirme bilgisayarında başka projeler de container çalıştırır. ProPR bu projelerle aynı sanal makineyi paylaşmaz.

`propr` profili yalnız ProPR'ın veri klasörünü görür. Ajan hesaplarının giriş klasörleri bu profile bağlı değildir. Bu yüzden ProPR o hesapların giriş bilgisine erişemez.

ProPR servisleri yalnız `127.0.0.1` adresinde açılır. Servisler internete açık değildir.

### Kurulumda karşılaşılan sorunlar

Kurulumda beş sorun çıktı. Her sorunun çözümü kurulum belgesinde yazılıdır.

- Docker'ın parola yardımcısı eksikti. Ayrı Docker ayar klasörü bu sorunu çözdü.
- Kurulum bir yönetici hesabı istedi. Ayar dosyasına depo sahibi yazıldı.
- ProPR ajan hesaplarının klasörlerini bağlamak istedi. Bu bağlar kapatıldı.
- Web girişi kapalıydı. GitHub uygulamasına dönüş adresi ve istemci sırrı eklendi.
- Sırrı alan betik ilk sürümde açık kalıyordu. Betik artık iş bitince terminal sekmesini kapatır.

## Entegrasyon

### Paradev

Paradev, kodlama ajanlarını çalışma alanlarında çalıştıran bir masaüstü uygulamasıdır.

Eski akışta Paradev'de `site-pr-flow` adında bir çalışma alanı vardı. Bu alandaki ajan yerel bir kapı betiğini çalıştırırdı. Betik PR açar ve `main` dalını ilerletirdi. 27 Kasım 2026 Cuma gününden beri PR'ları ProPR birleştirir.

Paradev'e birden çok ajan hesabı tanımlıdır. Her hesap ayrı bir ajan olarak eklendi. Hesap, ortam değişkeniyle seçilir.

### Paperclip takımları

Site ve backend kodunu Paperclip takımları yazar. Geliştirici işi kendi dalında yapar. QA işi kabul ölçütüne göre dener. Committer dalı PR olarak açar.

### GitHub Actions

Zorunlu test `ci.yml` içindeki `build-and-test` işidir. `main` dalına ilerleme olunca `deploy.yml` siteyi yayına alır.

Testler dört parçaya bölünür. Parçalar aynı anda ayrı makinelerde koşar. `build-and-test` işi bütün parçaların sonucunu toplar. Bir parça bile geçmezse `build-and-test` kırmızı olur. Tarayıcılar ve sistem paketleri önbellekten kurulur. Böylece yavaş paket sunucusu testi geciktirmez.

## MCP

MCP, yapay zekâ ajanlarının başka uygulamaların araçlarını kullanma yoludur. ProPR'ın MCP sunucusu PR'ları ve görevleri okuma araçları sunar.

### Nasıl bağlandı

ProPR'ın MCP sunucusu yalnız HTTPS adresle çalışır. ProPR'ın hazır tüneli servisi internete açar. Bu yüzden tüneli seçmedik.

ProPR'ın önüne bu bilgisayarda çalışan bir HTTPS vekili konuldu. Vekil, Caddy adlı bir web sunucusudur. Vekil yalnız `127.0.0.1:4443` adresinde açılır. MCP adresi `https://localhost:4443/api/mcp` olur.

Vekilin sertifikası yerel bir kök sertifikayla imzalıdır. Sertifika yalnız `localhost` ve `127.0.0.1` adlarını kapsar. Kök sertifika sistemin güvenilir sertifikalarına eklenmedi. Claude Code bu sertifikayı `NODE_EXTRA_CA_CERTS` değişkeninden okur.

### İzin sınırı

- MCP kapsam tavanı yalnız `read` olur. Ajanlar ProPR'da yalnız okuyabilir.
- Her bağlantıda depo ayrıca seçilir. Seçilen depo `karacaismail/frappesetup` olur.
- Bağlantı OAuth ile kurulur. Onayı depo sahibi tarayıcıda verir.

### Bağlantı durumu

Bu durum 22 Kasım 2026 Pazar günü kaydedildi.

| Hesap | Durum |
| --- | --- |
| Claude 03 | Bağlı. `claude mcp list` komutu "Connected" gösterdi. |
| Öteki Claude hesapları | Bağlı değil. Her hesap ayrı bağlanmalı. |
| Codex hesapları | Bağlı değil. Codex sistemin sertifika deposunu kullanır. |

Araçla okuma denemesi `not_run` durumunda. Claude 03 hesabı o sırada kullanım sınırındaydı.

Kurulum adımları depodaki [`Propr_setup`](https://github.com/karacaismail/frappesetup/tree/main/Propr_setup) klasöründe, "MCP köprüsü" bölümündedir.

## Güvenlik kararları

- ProPR MCP kapsamı yalnız okumadır.
- MCP vekili yalnız bu bilgisayardan açılır.
- CI hatasını otomatik düzeltme kapalıdır.
- ProPR'ın commit kimliği `karacaismail` hesabıdır.
- ProPR'ı yalnız depo sahibi tetikleyebilir.
- Sırlar ProPR'ın `.env` dosyasında durur. Dosyayı yalnız sahibi okuyabilir.
- Sırlar, anahtarlar ve `.env` dosyası depoya eklenmez.
- ProPR'ın verisi geliştirici bilgisayarında kalır.

## Açık işler

1. ProPR MCP için öteki Claude hesapları ve Codex hesapları bağlanmadı. Araçla okuma denemesi yapılmadı.
2. `main` dalı için GitHub koruma kuralı yoktur. Kural önerisi DevOps sorumlusuna devredildi. Devir notu [`Propr_setup`](https://github.com/karacaismail/frappesetup/tree/main/Propr_setup) klasöründedir.
3. "GitHub bağlantısı" bölümündeki izin listesi 22 Kasım 2026 Pazar günkü durumdur. O gün yedi iznin hepsi yalnız okumaydı. PR birleştirmek yazma izni ister. ProPR'ın güncel izinleri bu sayfa için yeniden doğrulanmadı.
