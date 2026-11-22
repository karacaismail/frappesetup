# Karar notu 0001: identity-sync teknolojisi ve olay kaynağı

Bu not bir T-2 karar notudur. T-2, yeni araç eklemeden önce yazılan değerlendirmedir. Not 22 Kasım 2026 Pazar günü yazıldı. Karar aynı gün verildi. Seçilen yol eklentisiz yoldur. Ayrıntı “Seçilen yol” bölümündedir.

## İhtiyaç

`identity_sync` servisi Keycloak'taki kullanıcı değişikliklerini Press'e ve kiracı sitelerine taşır (G-81). Servisin şu değişiklikleri öğrenmesi gerekir:

- kullanıcı kaydoldu ve e-postasını doğruladı,
- kullanıcının e-postası değişti,
- hesap silindi ya da kapatıldı,
- yönetici kullanıcıyı değiştirdi,
- kullanıcının Organization üyeliği değişti.

Organization, Keycloak'ta bir müşteri kuruluşunu temsil eden kayıttır.

Zamanlanmış iş yasaktır (Proje kaydı D-6). Bu yüzden servis Keycloak'ı belli aralıkla yoklayamaz. Değişiklik servise ya Keycloak'tan gelmeli ya da bizim işlemimizle başlamalıdır.

## Soru 1: Servis hangi dilde yazılır?

Seçim Python 3.11 ve sonrasıdır.

- Ortak `oidc_verify` kitaplığı Python 3.11 ve sonrasını ister. Servis bu kitaplığı kullanır.
- Frappe 16 siteleri Python 3.14 kullanır. Servis bu sürümde de çalışmalıdır.
- Ekip ikinci dil eklemez (T-1).
- Testler bu makinede Python 3.11.18 ve Python 3.14.7 ile koşar. Sonuç iş raporundadır.

## Soru 2: HTTP sunucusu için yeni paket gerekir mi?

Seçim yeni paket eklememektir. Python'un kendi kitaplığı yeter.

| İş | Python'un kendi modülü |
| --- | --- |
| Olayı alan HTTP sunucusu | `http.server` |
| Keycloak, Press ve kiracı çağrıları | `urllib.request` |
| Gelen isteğin imzasını doğrulama | `hmac` ve `hashlib` |
| Bekleme kuyruğu ve işlenen olay kaydı | `sqlite3` |
| Testler | `unittest` |

- `http.server` isteği tek tek işler. Servisin yükü düşüktür. Bu sıra aynı kullanıcının iki olayının çakışmasını da önler.
- Python belgesi `http.server` modülünü internete açık kullanım için önermez. Servis yalnız iç ağda dinler. Servis her istekte imzayı ve gövde boyutunu denetler.
- Yük artarsa sunucu katmanı değiştirilir. İş mantığı sunucudan ayrıdır. Bu geçiş ayrı bir T-2 notu ister.

## Soru 3: Keycloak olayları servise nasıl gelir?

Keycloak 26.8 serisinin son sürümü 26.8.2 sürümüdür. Bu sürüm 5 Kasım 2026 Perşembe günü çıktı. Keycloak'ın kendisinde HTTP ile olay gönderen hazır bir parça yoktur. Hazır dinleyiciler günlük ve e-posta gibi işler içindir. Bu yüzden üç yol vardır.

### Yol A: Açık kaynak bir Keycloak olay eklentisi

Eklenti, Keycloak'ın içine kurulan ek koddur. Aşağıdaki bilgiler 22 Kasım 2026 Pazar günü depolardan okundu. Hiçbir eklenti Keycloak 26.8.2 üzerinde çalıştırılmadı. Uyum bilgisi yalnız derleme dosyasından ve tanıtım metninden gelir.

| Eklenti | Lisans | Son sürüm | Bakım | Keycloak 26.8 uyumu | Sonuç |
| --- | --- | --- | --- | --- | --- |
| [p2-inc/keycloak-events](https://github.com/p2-inc/keycloak-events) | Elastic License 2.0 | 0.70 sürümü, 17 Kasım 2026 Salı günü | Etkin | Evet. Derleme dosyası 26.8.0 yazar. | Kabul edilmez. Bu lisans açık kaynak değildir. |
| [vymalo/keycloak-webhook](https://github.com/vymalo/keycloak-webhook) | MIT | 0.10.0-rc.1 deneme sürümü, 2 Ekim 2025 Perşembe günü | Zayıf. Son değişiklik 26 Temmuz 2026 Pazar günü. 24 açık kayıt var. | Doğrulanmadı. Derleme dosyası 26.4.0 yazar. | Uygun değil. İmza desteği yok. Üyelik olayında kullanıcı kimliği eksik (98 numaralı açık kayıt). |
| [aznamier/keycloak-event-listener-rabbitmq](https://github.com/aznamier/keycloak-event-listener-rabbitmq) | Apache-2.0 | 3.0.5 sürümü, 20 Mart 2024 Çarşamba günü | Durmuş | Hayır. Derleme dosyası 21.1.2 yazar. | Uygun değil. Ayrıca RabbitMQ sunucusu ister. |
| [monte97/keycloak-webhook-provider](https://github.com/monte97/keycloak-webhook-provider) | MIT | 1.16.6 sürümü, 15 Nisan 2026 Çarşamba günü | Tek kişi. Kullanan başka proje görülmedi. | Doğrulanmadı. Derleme dosyası 26.5.6 yazar. | Uygun değil. Keycloak veritabanına tablo ekler. Özellikleri kodda doğrulanmadı. |
| [sashyo/keycloak-webhook-listener](https://github.com/sashyo/keycloak-webhook-listener) | Apache-2.0 | Sürüm yok. Tek değişiklik 23 Ekim 2026 Cuma günü. | Yok | Doğrulanmadı. Yalnız 26.4.0 ile denenmiş. | Uygun değil. Yalnız örnek kod olarak işe yarar. |
| [jessylenne/keycloak-event-listener-http](https://github.com/jessylenne/keycloak-event-listener-http) | Apache-2.0 | Sürüm yok. Son değişiklik 21 Eylül 2022 Çarşamba günü. | Durmuş | Hayır | Uygun değil. |

Yol A'nın sonucu şudur: Keycloak 26.8'i hedefleyen tek eklentinin lisansı açık kaynak değildir. Açık kaynak lisanslı eklentiler ya bakımsızdır ya da 26.8 ile denenmemiştir.

Bir not daha var. İncelenen eklentilerin çoğu teslimi garanti etmez. Örneğin p2-inc eklentisi kuyruğu bellekte tutar. Keycloak yeniden başlarsa bekleyen olaylar kaybolur. Bu yüzden eklenti seçilse bile elle mutabakat gerekir. Mutabakat, iki tarafın kayıtlarını karşılaştırma işidir.

### Yol B: Kendi yazdığımız Java eklentisi

Eklenti Keycloak'ın olay dinleyici arayüzünü uygular. Bu arayüzün adı “Event Listener SPI” olur. Eklenti her olayı imzalı bir HTTP isteğiyle servise gönderir.

- **İş miktarı.** Tahmin 150 ile 250 satır Java kodudur. Bu sayı ölçülmedi. İki arayüz ve bir kayıt dosyası gerekir.
- **Lisans.** Gereken Keycloak kitaplıkları Apache-2.0 lisanslıdır. Bu kitaplıklar yalnız derlemede kullanılır.
- **Araç.** Derleme için JDK 17 ya da 21 ve Maven gerekir. Bu, ekibe ikinci bir dil ekler. T-1 kuralı bunu istemez. Karar sitesi bu eklentiye tek istisna olarak izin verir (G-81, G-152).
- **Risk.** Keycloak bu arayüzü “iç arayüz” sayar. Keycloak belgesi arayüzün haber verilmeden değişebileceğini yazar. Bu yüzden her Keycloak sürümünde eklentiyi yeniden sınamak gerekir.
- **Teslim.** Keycloak dinleyicideki hatayı yakalar ve yalnız günlüğe yazar. Başarısız gönderim sessizce kaybolur. Kalıcı yeniden deneme ek iş ister. Elle mutabakat yine gerekir.
- **Eksik bilgi.** Keycloak 26.8.2 üye ekleme olayına kullanıcının kimliğini yazmaz. Olay yalnız Organization'ı söyler. Bu davranış Keycloak kaynağında okundu. Bu yüzden eklenti yeni üyenin kim olduğunu bildiremez. Bu eksik Yol A için de geçerlidir.
- **Kurulum.** JAR dosyası Keycloak'ın `providers/` klasörüne konur. Sonra `kc.sh build` komutu çalışır. Bu, Keycloak container imajını değiştirir.

### Yol C: Eklentisiz yol

Bu yolda Keycloak'a hiçbir ek kod kurulmaz. Her değişiklik bizim işlemimizle başlar.

| Değişiklik | Eklentisiz karşılığı |
| --- | --- |
| Kayıt ve e-posta doğrulama | Kullanıcı Press'e ilk girdiğinde `press_tr` takımı açar (G-12). Bu uç ortak sözleşmede zaten var. |
| Davet | Press `identity_sync` servisini çağırır. Servis kullanıcıyı açar ve davet e-postasını gönderir. |
| E-posta değişikliği | Kullanıcı e-postasını kendi değiştiremez (G-57). Değişikliği yönetici bizim komutumuzla başlatır. |
| Hesabın kapatılması ve silinmesi | Yönetici işlemi bizim komutumuzla başlatır. Komut önce Keycloak'ı, sonra siteleri değiştirir. |
| Organization üyeliği | Üyeliği yalnız bizim çağrımız değiştirir. |
| Kaçan değişiklik | Yönetici mutabakat komutunu elle çalıştırır. Komut farkı raporlar. |

- **Kazanç.** Yeni dil, yeni paket ve yeni Keycloak imajı gerekmez. Keycloak sürümü değişince kırılacak eklenti olmaz.
- **Eksik.** Yönetici Keycloak ekranından doğrudan değişiklik yaparsa servis bunu öğrenmez. Örneğin yönetici bir hesabı Keycloak ekranından kapatabilir. Bu fark ancak mutabakat komutu çalışınca görünür.
- **Eksiğin etkisi.** Kapatılan kullanıcı yeniden giriş yapamaz. Çünkü bütün girişler Keycloak'tan geçer. Keycloak çıkış bildirimiyle açık oturumları da kapatır. Sitede kalan kayıt yalnız eski bir kayıttır. E-posta farkı ise bildirim e-postalarını etkiler.
- **Kural.** Ekip kullanıcıyı Keycloak ekranından değil bizim komutumuzla değiştirmelidir. Bu kural işletme belgesine yazılmalıdır.

## Karşılaştırma

| Ölçüt | Yol A | Yol B | Yol C |
| --- | --- | --- | --- |
| Açık kaynak lisansı | 26.8'i hedefleyen eklentide yok | Var | Gerekmez |
| Keycloak 26.8 uyumu | Kanıtlanmadı | Biz sınarız | Etkilenmez |
| İkinci dil | Yok | Java gelir | Yok |
| Keycloak imajı değişir mi? | Evet | Evet | Hayır |
| Keycloak ekranındaki değişikliği anında görür mü? | Evet | Evet | Hayır |
| Elle mutabakat gerekir mi? | Evet | Evet | Evet |
| Sürüm yükseltme riski | Eklentinin sahibine bağlı | Bizde | Yok |

## Seçilen yol

Seçilen yol Yol C'dir, yani eklentisiz yoldur. Bu seçim MVP içindir. MVP, ilk kullanılabilir sürümdür.

Proje sahibi kararları ajana bıraktı (Proje kaydı D-10). Olay kaynağını bu iş seçer (Proje kaydı O-11). Orkestratör de aynı yolu onayladı. Proje sahibi bu kararı değiştirebilir.

Seçimin gerekçesi şudur:

- Yol A şu anda seçilemez. Uygun lisanslı ve 26.8 ile denenmiş eklenti yoktur.
- Yol B çalışır. Ama ikinci dili ve sürekli bakım yükünü şimdi getirir.
- Yol C en az parçayla çalışır. Eksiği bellidir ve mutabakat komutuyla görünür olur.

Servisin olay ucu her üç yolda aynıdır. Uç `POST /v1/events` adresidir. Yol C'de bu ucu bizim işlemlerimiz çağırır. Sonradan bir eklenti eklenirse eklenti aynı uca gönderir. Servisin kodu değişmez.

Uç bu yüzden şöyle korunur:

- Uç imzalı istek kabul eder. İmza HMAC-SHA256 ile üretilir. Eklentiler bu imzayı üretebilir.
- Servis Keycloak'ın kendi olay biçimini servis zarfına çevirebilir. Çeviri kodu yazıldı ve sınandı.
- Servis eylemi olayın içeriğinden değil kullanıcının güncel durumundan seçer. Bu yüzden eksik ya da geç gelen olay yanlış sonuç üretmez.

## Geri dönüş

- Yol C'den Yol B'ye geçiş yalnız eklentiyi eklemeyi gerektirir. Servis aynı kalır.
- Yol B'den geri dönmek için JAR dosyası `providers/` klasöründen silinir. Sonra Keycloak yeniden derlenir.
- Bu not hiçbir paket eklemez. Geri alınacak bağımlılık yoktur.

## Doğrulanmayan noktalar

- Hiçbir eklenti Keycloak 26.8.2 üzerinde çalıştırılmadı.
- Keycloak 26.8 için desteklenen JDK sürümleri resmî tablodan doğrulanmadı.
- Kimlik sağlayıcı kullanıcıyı Organization'a kendiliğinden ekleyebilir. Bu durumda olay çıkıp çıkmadığı sınanmadı.
- Yol B'nin satır sayısı tahmindir.

## Kaynaklar

- [Keycloak sürümleri](https://github.com/keycloak/keycloak/releases)
- [Keycloak sunucu geliştirme belgesi, olay dinleyici bölümü](https://www.keycloak.org/docs/latest/server_development/index.html)
- [Keycloak 26.8.2 olay türleri](https://github.com/keycloak/keycloak/blob/26.8.2/server-spi-private/src/main/java/org/keycloak/events/EventType.java)
- [Keycloak 26.8.2 yönetici olayı kaynak türleri](https://github.com/keycloak/keycloak/blob/26.8.2/server-spi-private/src/main/java/org/keycloak/events/admin/ResourceType.java)
- [Keycloak 26.8.2 üyelik olaylarını üreten kod](https://github.com/keycloak/keycloak/blob/26.8.2/services/src/main/java/org/keycloak/organization/admin/resource/OrganizationMemberResource.java)
- [Keycloak Admin REST API belgesi](https://www.keycloak.org/docs-api/latest/rest-api/index.html)
- [p2-inc eklentisinin lisans dosyası](https://github.com/p2-inc/keycloak-events/blob/main/COPYING)
- [p2-inc eklentisinin teslim belgesi](https://github.com/p2-inc/keycloak-events/blob/main/docs/webhooks.md)
