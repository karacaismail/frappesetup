# Karar notu 0010: hesap konsolu için küçük Keycloak eklentisi

Not 22 Kasım 2026 Pazar günü yazıldı. Sahibi kimlik-tema işidir. Bu bir T-2 notudur: yeni bir araç ve yeni bir kod türü ekler.

## İhtiyaç

Hesap ekranı Press'teki silme sayfasına bir bağlantı gösterir (proje kaydı O-27, sözleşme 7. bölüm). Bağlantıyı yalnız müşteri görür, çalışan görmez. Kararı sunucu verir. Çalışana giden sayfada bağlantı hiç bulunmaz.

Tema bunu tek başına yapamaz. Nedenleri şunlardır:

- Hesap konsolu Keycloak'ın kendi React uygulamasıdır. Tema uygulamanın HTML'ini değiştiremez.
- Keycloak sayfa şablonuna kullanıcıyı ve rollerini vermez. Kaynak `AccountConsole.java` dosyasıdır (Keycloak 26.8.2).
- Keycloak'ın hazır silme bölümü `manage-account` ya da `delete-account` rolünü yeterli sayar. Kaynak `AccountConsole.java` içindeki `hasOneOfRole(AccountRoles.MANAGE_ACCOUNT, AccountRoles.DELETE_ACCOUNT)` satırıdır. Varsayılan roller `manage-account` rolünü içerir. Bu yüzden çalışan da bölümü görür.
- Bunu çalışan sunucuda ölçtüm. Hazır konsol, silme eylemi açıkken rolü olmayan kullanıcıya özelliği açık gönderdi ve bölümü gösterdi.
- `manage-account` rolü olmayan kullanıcıda konsol açılmadı: gezinme ve form çizilmedi. Bunu da çalışan sunucuda bir kez denedim. Nedenini kaynakta doğrulamadım.

## Seçenekler

| Seçenek | Sonuç |
| --- | --- |
| Bölümü CSS ya da betikle gizlemek | Reddedildi. Karar tarayıcıda kalır. Bağımsız inceleme bunu yetersiz buldu. |
| Çalışana `manage-account` rolünü vermemek | Reddedildi. Konsol o kullanıcıda açılmıyor. |
| Keycloak'ın hesap konsolu şablonunu temaya kopyalamak | Reddedildi. Şablon kullanıcının rolünü bilmiyor. |
| Keycloak'ın `account-resource` eklenti noktası | Seçildi. Tema ayarı `accountResourceProvider` eklentiyi seçer. Bu ayarı Keycloak'ın `AccountLoader` sınıfı okur. |

## Seçim

Eklenti iki küçük Java sınıfıdır. Kaynak `backend/identity/keycloak/themes/atonota/account-provider/` klasöründedir.

- `AccountDeletionLinkConsole`, Keycloak'ın `AccountConsole` sınıfını genişletir. Sayfayı Keycloak üretir. Sınıf yalnız iki şey yapar: hazır silme özelliğini kapatır ve müşteriye bağlantıyı ekler.
- `AccountDeletionLinkConsoleFactory` eklentiyi `account-deletion-link` adıyla kaydeder.
- Müşteri, `request-account-deletion` adlı realm rolünü taşıyan kullanıcıdır. Bu rol Keycloak'ın `delete-account` rolünden ayrıdır. `delete-account` rolü Keycloak'ın kendi silme eylemine yetki verir. Müşteriye o rol verilseydi, eylem yanlışlıkla açıldığında müşteri hesabını Press'i atlayarak silebilirdi.
- Sözleşme müşteri ayrımını ve rolün adını yazmıyor. Orkestratörden bu rolü sözleşmeye yazmasını istiyorum.
- Adres `IDENTITY_ACCOUNT_DELETION_URL` ortam değişkeninden gelir. Eklenti yalnız `http` ve `https` adresini kabul eder.

Eklenti yeni bir bağımlılık getirmez. Yalnız Keycloak'ın kendi sınıflarını kullanır.

## Yeni araç

Eklentiyi derlemek için bir JDK imajı gerekir: `eclipse-temurin:21-jdk`. İmaj özetle (digest) sabitlendi. Derleme yalnız `javac` ve `jar` komutlarını kullanır. Maven ya da Gradle yoktur.

- Eclipse Temurin, GPL-2.0 lisansını Classpath istisnasıyla taşır. İmaj yalnız derlemede kullanılır, ürüne girmez.
- Keycloak Apache-2.0 lisanslıdır. Eklenti MIT lisanslı depo kodudur.
- Derleme adımı `themes/atonota/test/Dockerfile` dosyasının ikinci aşamasıdır.

## Riskler ve bakım

- Keycloak bu eklenti noktasını “iç” sayar. Başlarken bir uyarı yazar: “This SPI is internal and may change without notice”. Keycloak sürümü değişince eklenti yeniden derlenmeli ve testler çalışmalıdır.
- Derleme `-Xlint:all -Werror` ile yapılır. Keycloak bir sınıfı değiştirirse derleme durur.
- Eklenti kurulu değilse hesap konsolu 404 yanıtı verir. Bu bilerek seçildi. Aksi hâlde görünürlük kuralı sessizce kaybolurdu.
- Adres ve kaçış kurallarını bağımlılıksız bir Java denetimi ölçer. Denetim imaj derlenirken `java -ea` ile çalışır ve başarısız olursa derlemeyi durdurur.
- Sayfa davranışını tarayıcı testleri ölçer: `tests/delete-account.spec.ts` ve `tests/realm-settings.spec.ts`.
- Müşteri bağlantıyı alamazsa eklenti günlüğe uyarı yazar. Beklenmedik hata hesap konsolunu bozmaz.

## Geri dönüş

1. `account/theme.properties` dosyasından `accountResourceProvider` ve `accountDeletionUrl` satırlarını silin.
2. Jar dosyasını Keycloak'tan kaldırın.

Bu durumda hesap konsolu Keycloak'ın hazır hâline döner ve bağlantı görünmez. Veri değişmez.

## Kimlik-realm işinden istenenler

1. Eklentiyi kendi Keycloak imajında derleyin ve `/opt/keycloak/providers/` klasörüne koyun.
2. Keycloak'a `IDENTITY_ACCOUNT_DELETION_URL` değişkenini verin.
3. `request-account-deletion` adlı realm rolünü açın. Rolü müşterilere verin, çalışanlara vermeyin.
4. `delete_account` gerekli işlemini kapalı tutun. `delete-account` rolünü kimseye vermeyin.
5. Kurulumdan sonra müşteri ve çalışan hesabıyla birer kez deneyin.
