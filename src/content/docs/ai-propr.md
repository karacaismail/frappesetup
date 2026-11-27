---
title: "ProPR ile PR denetimi"
nav: "ProPR"
order: 26
---

Bu sayfa ProPR'ın bu projede nasıl kullanıldığını anlatır. Kurulum bilgileri 22 Kasım 2026 Pazar günü yerel kurulumda doğrulandı. Birleştirme kuralı 27 Kasım 2026 Cuma günü eklendi. Adım adım kurulum belgesi depoda [`Propr_setup`](https://github.com/karacaismail/frappesetup/tree/main/Propr_setup) klasöründedir.

## Kullanım amacı

ProPR, GitHub'daki PR'ları izleyen açık kaynak bir uygulamadır. ProPR bu bilgisayarda yerel olarak çalışır.

## Birleştirme kuralı

Müşteri 27 Kasım 2026 Cuma günü bu kuralı koydu. Kural değişmez. Sitedeki karar kaydı K-64'tür.

1. PR'ları ProPR birleştirir.
2. ProPR'ın her commit'inde yazar ve committer `karacaismail` hesabı olur.
3. GitHub'ın birleştirme servisi son birleşme commit'inin committer alanına GitHub yazar. Müşteri bu tek istisnayı kabul etti.

Kural ProPR'ın üç commit türünü kapsar:

- ana dalı PR dalına birleştiren commit,
- çakışma çözen commit,
- ProPR'ın yazdığı düzeltme commit'i.

Kimliği ProPR'ın iki ayar değişkeni verir. Değişkenlerin adı `PROPR_AGENT_COMMIT_AUTHOR_NAME` ve `PROPR_AGENT_COMMIT_AUTHOR_EMAIL` şeklindedir. Değişkenler boş bırakılmaz ve silinmez. Değerler kurulum belgesinde yazılıdır.

ProPR Git'i hook'lar kapalı çalıştırır. Hook, Git'in her commit'te çalıştırdığı denetimdir. Bu yüzden yazar koruması ProPR commit'lerini denetlemez. Kimliği yalnız bu iki değişken korur. Committer her PR'da commit kimliğini ayrıca denetler.

## Eski kurulum

Bu sayfanın kalan bölümleri 22 Kasım 2026 Pazar günkü kurulumu anlatır. O gün ProPR yalnız gözlemciydi. O gün ProPR şu üç işi yapıyordu:

- `karacaismail/frappesetup` deposundaki PR'ları ve CI sonuçlarını okur.
- Durumu kendi panosunda gösterir.
- Yalnız depo sahibinin tetiklemesine izin verir.

O kurulumda birleştirmeyi kapı betiği yapıyordu. GitHub izinleri ve güvenlik kararları yeni kurala göre henüz gözden geçirilmedi.

## PR akışı

22 Kasım 2026 Pazar günü PR'lar `main` dalına şu sırayla giriyordu:

1. Pane işçisi işi kendi dalında bitirir.
2. Bağımsız bir inceleme dalı denetler. Karar `pass` olmalı.
3. Kapı betiği dalı push eder ve PR açar.
4. GitHub, `ci.yml` iş akışındaki testleri çalıştırır.
5. ProPR PR'ı ve test sonucunu izler.
6. Testler geçerse kapı betiği `main` dalını hızlı ileri alır.

Son adımda yeni commit oluşmaz. `main` dalı yalnız PR'ın son commit'ine ilerler. GitHub bu PR'ı birleşmiş olarak gösterir.

Testler kalırsa kapı betiği hatayı dalın çalışma klasörüne yazar. Pane işçisi hatayı düzeltir. Sonra iş yeniden incelenir.

Kapı betiği depoda değildir. Betik geliştirici bilgisayarında yerel bir araçtır.

## GitHub bağlantısı

ProPR, GitHub'a kendi GitHub uygulamamızla bağlanır. Uygulamanın adı `frappesetup-propr-gate` olur.

Uygulamanın yedi izni vardır. Yedisi de yalnız okumadır:

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

Paradev'de PR akışı için `site-pr-flow` adında bir çalışma alanı vardır. Bu alandaki ajan kapı betiğini çalıştırır. Ajan kod yazmaz. Ajan yalnız PR açma ve birleştirme adımını yürütür.

Paradev'e birden çok ajan hesabı tanımlıdır. Her hesap ayrı bir ajan olarak eklendi. Hesap, ortam değişkeniyle seçilir.

### Pane

Site ve backend kodunu Pane işçileri yazar. Her iş için bağımsız bir inceleme raporu üretilir. Kapı betiği yalnız `pass` kararı alan dalı kabul eder.

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

Bu liste 22 Kasım 2026 Pazar günkü kurulumu anlatır. Liste yeni birleştirme kuralına göre henüz gözden geçirilmedi.

- ProPR'ın GitHub izinleri yalnız okumadır.
- ProPR MCP kapsamı yalnız okumadır.
- MCP vekili yalnız bu bilgisayardan açılır.
- ProPR'da kodlama ajanı tanımlı değildir.
- CI hatasını otomatik düzeltme kapalıdır.
- ProPR'ı yalnız depo sahibi tetikleyebilir.
- Sırlar ProPR'ın `.env` dosyasında durur. Dosyayı yalnız sahibi okuyabilir.
- Sırlar, anahtarlar ve `.env` dosyası depoya eklenmez.
- ProPR'ın verisi geliştirici bilgisayarında kalır.

## Açık işler

1. ProPR MCP için öteki Claude hesapları ve Codex hesapları bağlanmadı. Araçla okuma denemesi yapılmadı.
2. `main` dalı için GitHub koruma kuralı yoktur. Kural önerisi DevOps sorumlusuna devredildi. Devir notu [`Propr_setup`](https://github.com/karacaismail/frappesetup/tree/main/Propr_setup) klasöründedir.
3. Kapı betiği şimdilik yalnız site dallarını kabul eder.
4. GitHub izinleri ve güvenlik kararları K-64 kuralına göre gözden geçirilmedi. ProPR'ın gerçek bir commit'i denetlenmedi.
