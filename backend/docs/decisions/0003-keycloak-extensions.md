# 0003. Keycloak eklentileri: sihirli bağlantı ve Apple ile giriş

Bu not T-2 kuralına göre yazıldı. Karar 22 Kasım 2026 Pazar günü kimlik-realm işinde alındı. Proje sahibi kararı ajana bıraktı (Proje kaydı D-10 ve O-6).

## İhtiyaç

Proje sahibi iki giriş yolunu MVP'ye aldı (O-6). Birincisi sihirli bağlantıdır. Kullanıcı e-postasına gelen bağlantıya tıklar ve parola yazmadan girer. İkincisi Apple ile giriştir. Keycloak 26.8.2 bu iki yolu hazır sunmaz. Eklenti gerekir. Eklentinin lisansı Apache-2.0 ya da MIT olmalıdır.

## Seçenekler

### Sihirli bağlantı

| Eklenti | Lisans | Son sürüm | Son değişiklik | Keycloak 26 uyumu | Not |
| --- | --- | --- | --- | --- | --- |
| `sky-cloak/keycloak-magic-link` | Apache-2.0 | v0.3.0, 20 Haziran 2026 | 13 Eylül 2026 | Keycloak 25 ve 26. Her gönderimde 25.0.6, 26.0.7 ve 26.6.x ile sınanır. | Bağlantı tek kullanımlık ve kısa ömürlü. Aynı tarayıcı koşulu var. Hız sınırı var. Hesap varlığını açığa vermez. Yönetici ucu da var. |
| `cloudflightio/keycloak-magic-link` | Apache-2.0 | Yayın yok | 4 Haziran 2025 | Belirtilmemiş | Tek kullanımlık anahtar rastgele UUID. Bir yıldan uzun süredir değişmedi. |
| `p2-inc/keycloak-magic-link` (Phase Two) | Elastic License 2.0 | v0.94 | 16 Kasım 2026 | Keycloak 26 | Lisans açık kaynak değildir. Elenir. |

### Apple ile giriş

| Eklenti | Lisans | Son sürüm | Son değişiklik | Keycloak 26 uyumu | Not |
| --- | --- | --- | --- | --- | --- |
| `klausbetz/apple-identity-provider-keycloak` | Apache-2.0 | 1.17.0, 15 Ocak 2026 | 18 Ocak 2026 | Uyum tablosu: Keycloak 26.5 ve sonrası için 1.17.0 ve sonrası | Tarayıcı girişi ve token exchange. Apple'ın POST dönüşünü ve `.p8` anahtarıyla imzalı istemci sırrını yönetir. Keycloak'ın eklenti sayfasında listelidir. |
| `BenjaminFavre/keycloak-apple-social-identity-provider` | Apache-2.0 | v1.0.2, 29 Ekim 2020 | 9 Mart 2023 | Yok | Bakımı durmuş. Elenir. |

## Karar

- Sihirli bağlantı için önce `sky-cloak/keycloak-magic-link` v0.3.0 seçilmişti. Güvenlik incelemesi sonrası yerine `cloudflightio/keycloak-magic-link` geldi. Ayrıntı aşağıdaki durum bölümündedir.
- Apple ile giriş için `klausbetz/apple-identity-provider-keycloak` 1.17.0 seçildi.

### Gerekçe

1. İkisi de Apache-2.0 lisanslıdır. Phase Two eklentisi Elastic License taşır ve elenir.
2. İkisi de bakımlıdır ve Keycloak 26 serisini hedefler. Cloudflight eklentisinin yayını yok ve bir yıldır değişmedi. BenjaminFavre eklentisi 2023'ten beri değişmedi.
3. Skycloak eklentisi güvenlik varsayılanlarını doğru kurar. Bağlantı tek kullanımlık ve kısa ömürlüdür. Bağlantı yalnız isteyen tarayıcıda çalışır. E-posta tarayıcıları bağlantıyı tüketemez. Hız sınırı vardır. Hesap varlığı açığa çıkmaz. Bunlar G-78 ve G-144 ile uyumludur.
4. İki eklenti de tek bir jar dosyasıdır. Ek servis gerekmez. Jar dosyaları imaja sürüm ve SHA-256 özetiyle eklenir.

## Sürüm uyumu

- Keycloak sürümü 26.8.2'dir. Skycloak eklentisi 26.6.x ile sınandı. 26.8.2 ile çalıştığı bu işin canlı testleriyle gösterildi.
- Apple eklentisinin tablosu 26.5 ve sonrası için 1.17.0 der. Eklentinin yüklendiği canlı testle gösterildi. Gerçek Apple girişi denenmedi, çünkü Apple geliştirici anahtarı yok.

## Güvenlik ve bilinen açıklar

- İki eklenti de Keycloak'ın iç arayüzlerini kullanır. Keycloak yükseltmesinde eklenti uyumu yeniden sınanır. Bu, teknik borç tablosuna girer.
- Skycloak eklentisinin yönetici ucu (`/realms/platform/skycloak-magic-link`) `manage-users` rolü ister. Bu uç hesaba giriş vermekle eşdeğerdir. Bu turda hiçbir servis bu ucu çağırmaz.
- İki depoda da yayımlanmış bir güvenlik açığı kaydı bulunmadı (GitHub Security Advisories, 22 Kasım 2026).

## Durum: sihirli bağlantı güvenli kurulumla MVP'de (22 Kasım 2026, orkestratör kararı)

Proje sahibinin kararı açıktır: sihirli bağlantı ve Apple ile giriş MVP'ye girer (KARARLAR.md, Karar 17). İkinci güvenlik incelemesinden sonra orkestratör beş koşul koydu. Sihirli bağlantı bu koşullarla kalır.

| Koşul | Nasıl sağlandı | Kanıt |
| --- | --- | --- |
| 1. Bağlantı akışın içinde bir adım. Tıklamadan sonra akış sürer, ikinci doğrulama atlanmaz. | `cloudflightio/keycloak-magic-link` eklentisinin “normal” doğrulayıcısı seçildi. Bağlantı, akışın kendi `login-actions/authenticate` adresine `magickey` ekler. Tıklama `authenticate()` içinde doğrulanır ve `context.success()` ile akış sürer (`MagicLinkAuthenticatorNormal.java`). Realm'de `magiclink` adımından sonra koşullu ikinci adım alt akışı gelir. | `test_link_does_not_skip_totp`: TOTP'li kullanıcı bağlantıdan sonra OTP formu görür. Yanlış kod reddedilir. Doğru kod girişi tamamlar. |
| 2. Bağlantı giriş isteğine ve tarayıcı oturumuna bağlı. | Bağlantı o giriş isteğinin yürütme adresidir. Doğrulayıcı kullanıcıyı tarayıcının kimlik doğrulama oturumundan okur. Başka tarayıcıda oturum yoktur. | `test_link_logs_in_only_in_the_requesting_browser_and_only_once` ve `test_other_user_cannot_use_a_link_meant_for_someone_else`: başka tarayıcı kod alamaz. |
| 3. En çok 300 saniye, tek kullanım, e-posta önizlemesi tüketmez (MT-7). | `magickey.validity.duration = 300`. Anahtar doğrulamada silinir (`removeMagicLinkSession`). Önizleme tarayıcı oturumu taşımadığı için doğrulayıcıya ulaşmaz ve anahtar tüketilmez. | Aynı testler: yabancı tarayıcının denemesinden sonra asıl tarayıcı giriş yapar. İkinci tıklama kod vermez. Ömür dosya ve canlı ayardan okunur. |
| 4. Servis hesabı ya da kiracı belirteciyle bağlantı üreten yönetim ucu yok. | Eklentinin bağlantı üreten ucu yoktur. Çapraz cihaz “continuation” REST kaynağı ve doğrulayıcısı Keycloak SPI ayarıyla kapalıdır: `KC_SPI_REALM_RESTAPI_EXTENSION__MAGICLINK_LOGIN__ENABLED=false` ve `KC_SPI_AUTHENTICATOR__MAGICLINK_CONTINUATION__ENABLED=false`. | `test_rest_resource_answers_404` ve `test_continuation_authenticator_is_not_available`. Eski eklentinin ucu da 404 verir. |
| 5. Lisans Apache-2.0 ya da MIT. | Depodaki `LICENSE` dosyası Apache License 2.0 (resmî depo, 22 Kasım 2026). | Bu not. |

### Seçim

`sky-cloak/keycloak-magic-link` v0.3.0 koşul 1 ve 4'ü sağlamaz. Bağlantı işleyicisi akışı `redirectToRequiredActions` ile bitirir ve bir yönetici ucu vardır. Bu yüzden çıkarıldı.

`cloudflightio/keycloak-magic-link` seçildi. Yayımlanmış sürümü yoktur. Kaynak `7b4ee949a39a7ee953987162479ae1da2c57c3cb` commit'ine sabitlendi (4 Haziran 2025). Arşivin SHA-256 özeti Dockerfile'da sabittir. Eklenti imaj derlemesinde Maven ile derlenir. Derleme hedefi `-Dkeycloak.version=26.8.2` verilir. Böylece uyumsuzluk derlemede görünür. Maven imajı özetle sabittir. Eklenti veritabanına `MAGIC_LINK_SESSION` tablosunu ekler (Liquibase).

### Borç

- Eklentinin kendi hedefi Keycloak 26.1.4'tür. 26.8.2 ile derlendi ve canlı testleri geçti. Keycloak yükseltmesinde yeniden derlenir ve sınanır.
- Eklenti bir yıldır değişmedi. Güvenlik düzeltmesi gerekirse çatal alınır. Bu karar o zaman yeniden açılır.
- Giriş ve e-posta şablonları eklentinin jar dosyasından gelir. Türkçe metinler kimlik-tema işinin `atonota` temasında verilir.

### identity-sync rolleri (sözleşme 26a274c)

identity-sync davet ve kuruluş hazırlama için Keycloak'a yazar. Servis hesabı şu rolleri taşır: `view-users`, `query-users`, `manage-users`, `view-organizations`, `manage-organizations`. `manage-clients`, `manage-realm` ve `impersonation` yoktur. Roller yalnız `scope=admin-api kc-admin-api` belirtecine girer. Kiracı hedefli belirteç bu rolleri taşımaz ve Admin API'de 401 ya da 403 alır.

En az rol kümesi Keycloak 26.8.2 kaynağından çıkarıldı:

| İş | Keycloak ucu ve denetimi | Gereken rol |
| --- | --- | --- |
| Kullanıcı açma, davet e-postası (`execute-actions-email`) | `UsersResource` ve `UserResource`: `auth.users().requireManage()` | `manage-users` |
| Kullanıcı okuma ve arama | `auth.users().requireView()` ve `requireQuery()` | `view-users` (bileşik: `query-users`, `query-groups`) |
| Kuruluş açma | `services/src/main/java/org/keycloak/organization/admin/resource/OrganizationsResource.java`: `auth.orgs().requireManage()` | `manage-organizations` |
| Kuruluşa üye ekleme ve çıkarma | `OrganizationMemberResource.java`: `auth.orgs().requireManage(organization)` ve `auth.users().requireView(member)` | `manage-organizations` ve `view-users` |
| Kuruluş daveti | `OrganizationInvitationResource.java`: `auth.orgs().requireManage(organization)` | `manage-organizations` |
| Kuruluş okuma ve arama | `auth.orgs().requireView(organization)` ve `requireQuery()` | `view-organizations` (bileşik: `query-organizations`) |

Bileşik roller `services/src/main/java/org/keycloak/services/managers/RealmManager.java` 285 ile 289. satırlarında tanımlıdır. `manage-*` rolleri `view-*` rollerini içermez. Bu yüzden `view-users` ve `view-organizations` açıkça verilir. Rol adları `server-spi-private/src/main/java/org/keycloak/models/AdminRoles.java` dosyasındadır.

Canlı test (`test_identity_sync_admin_scope_can_create_user_and_organization`) admin-api belirteciyle kullanıcı ve kuruluş açar (201). Aynı belirteçle istemci açma 403 alır. Kiracı hedefli belirteç Admin API'de 401 ya da 403 alır (`test_kiraci_belirtecinde_yonetim_yetkisi_yok`).

### Olay dinleyici eklentisi (sözleşme 26a274c, Proje kaydı A-10)

İhtiyaç: Keycloak kullanıcı ve yönetim olaylarını `identity_sync` servisinin `/v1/events` ucuna imzalı göndersin. İmza biçimi identity-sync sözleşmesindedir (`contracts/identity_sync.openapi.yaml`, `webhookSignature`): başlık `X-Identity-Sync-Signature: sha256=<onaltılık özet>`, başlık `X-Identity-Sync-Timestamp` (Unix saniye), HMAC-SHA256 anahtarı `IDENTITY_SYNC_WEBHOOK_SECRET`, imzalanan içerik `<zaman damgası>.<kip>.<ham gövde>`, kip `execute` ya da `preview`. Servis zaman damgasını 300 saniye payla denetler ve aynı imzayı bir kez kabul eder.

Adaylar (22 Kasım 2026):

| Eklenti | Lisans | Son değişiklik | İmza | Uyum |
| --- | --- | --- | --- | --- |
| `p2-inc/keycloak-events` | Elastic License 2.0 | 17 Kasım 2026 | `X-Keycloak-Signature`, HMAC gövde üzerinde | Lisans açık kaynak değil. Elenir. |
| `vymalo/keycloak-webhook` | MIT | 5 Kasım 2025 | İmza yok. Yalnız temel kimlik doğrulama (`WEBHOOK_HTTP_AUTH_*`). | İmza koşulu sağlanmaz. |
| `sashyo/keycloak-webhook-listener` | Apache-2.0 | 23 Ekim 2026 | `X-Keycloak-Signature: sha256=<özet>`, HMAC yalnız gövde üzerinde. Zaman damgası yok. Başlık adı ve imzalanan içerik kodda sabittir (`WebhookEventListenerProvider.java` 87 ve 101. satırlar). | Başlık adı, zaman damgası ve `<zaman>.<kip>.<gövde>` biçimi tutmaz. Yeniden gönderim koruması yok. |
| `evilnet/keycloak-webhook-spi` | Depoda lisans dosyası yok | 20 Kasım 2026 | `X-Webhook-Signature: t=<saniye>,v1=<özet>`, HMAC `<t>.<gövde>` üzerinde. | Lisans belirsiz. Başlık adı ve biçim tutmaz. Kip parçası yok. |
| `jessylenne/keycloak-event-listener-http` | Apache-2.0 | 13 Kasım 2025 | İmza yok. | İmza koşulu sağlanmaz. |

Sonuç: Sözleşmedeki imza biçimini olduğu gibi üreten açık kaynak eklenti bulunamadı. Gövde biçimi de tutmaz: sashyo kendi alan adlarını yazar (`realm` adı, `realmId` yok). Sözleşme `realmId` ister.

Seçenekler, orkestratörün kararına sunuldu:

1. `sashyo/keycloak-webhook-listener` çatallanır (Apache-2.0, üç dosya, 8 KB). Başlık adları, zaman damgası ve `<zaman>.<kip>.<gövde>` imzası sözleşmeye göre eklenir. Gövde Keycloak'ın kendi olay biçiminde (`realmId` ile) gönderilir. Çatal bu depoda `identity/keycloak/event-listener/` altında durur ve imaj derlemesinde Maven ile derlenir. Bakımı bizde kalır. Önerilen yol budur.
2. identity-sync sözleşmesi sashyo eklentisinin biçimine uyarlanır: `X-Keycloak-Signature`, yalnız gövde imzası. Yeniden gönderim koruması kaybolur. Sözleşme sahibi karar verir.
3. Olay eklentisi bu turda kurulmaz. identity-sync olayları kendi işlemleriyle başlatır (karar notu 0001'deki eklentisiz yol).

Bu karar verilene kadar olay eklentisi kurulmadı. Durum raporu `blocked` olarak verildi.

### Sosyal girişte ikinci adım (O6)

Google ve Apple sağlayıcıları `postBrokerLoginFlowAlias` olarak `atonota-post-broker` akışını kullanır. Akış, kullanıcının kurulu TOTP ya da güvenlik anahtarını ister. Gerçek sosyal giriş denenmedi, çünkü sağlayıcı anahtarı yok. Akışın bağlı olduğu canlı testle gösterildi.

## Kurulum

- `backend/identity/keycloak/Dockerfile` Apple jar dosyasını ve derlenen sihirli bağlantı jar dosyasını `/opt/keycloak/providers/` klasörüne ekler. Özetler sabittir.
- Realm'in tarayıcı akışı `atonota-browser` adını taşır. Kullanıcı parola ve passkey ekranını görür. “Başka yol dene” bağlantısı sihirli bağlantı yolunu açar. İki yolda da ikinci adım sorulur.
- Apple sağlayıcısı realm'de kapalı durur. Anahtarlar `.env` dosyasındaki yer tutuculardan gelir. Gerçek anahtar yoktur.

## Geri dönüş

- Eklentiyi kaldırmak için Dockerfile'daki `ADD` satırı silinir ve realm akışındaki ilgili yürütme çıkarılır.
- Sihirli bağlantı kapatılırsa kullanıcı yalnız parola ve passkey ile girer. Veri kaybı olmaz.
- Apple sağlayıcısı kapatılırsa Apple ile açılmış hesaplar kalır. Bu kullanıcılar parola sıfırlama ile girer.

## Lisans etkisi

İki eklenti de Apache-2.0'dır. Keycloak imajına eklenir. `platform_core` koduna karışmaz. MIT lisanslı kodumuzu etkilemez.

## G-162 ek iş: tek kaynak başkasının girişini engelleyemez (24 Kasım 2026 Salı günü, B Takımı mimarı, AJA-413)

Bu bölüm `pc/g162-rate-limit` dalındaki G-162 düzeltmesinin üstüne kurulur. Düzeltmenin tasarımı yukarıdaki "G-162 düzeltmesi" bölümündedir. O bölüm dal `backend` dalına girince bu dosyada görünür.

### Sorun

Oracle bu riski AJA-375 incelemesinde buldu.

- Sayaç yalnız adrese göre sayar. Anahtar realm kimliği ve adres özetinden oluşur (`MagicLinkSendLimiter.java`).
- Saldırgan Ayşe'nin adresiyle 3 istek gönderir. Sonra Ayşe 15 dakika boyunca bağlantı alamaz.
- Saldırgan bunu her 15 dakikada yineler. Böylece Ayşe sihirli bağlantıyla hiç giremez.

PO kararları şunlardır:

- Aynı adrese 15 dakikada en çok 3 e-posta gider. Bu kural kalır.
- Yanıt herkes için aynı kalır. Hesabın varlığı ele verilmez.
- Tek bir yerden gelen istekler başkasının girişini sürekli engellememeli.

### Terimler

- **Kaynak** isteğin geldiği yerdir. IPv4 adresinde kaynak adresin tamamıdır. IPv6 adresinde kaynak adresin ilk 64 bitidir. Bir ev ya da bir telefon genelde tek bir IPv6 /64 bloğu alır.
- **Yuva** sayaçtaki tek bir haktır. Her yuva 900 saniye sonra kendiliğinden boşalır. Yuva yöntemi yukarıdaki "Sayacın yeri" bölümündedir.

### Çözüm yollarının karşılaştırması

| Yol | Tek kaynağın saldırısını durdurur mu? | Hesabı ele verir mi? | Not |
| --- | --- | --- | --- |
| 1. Yalnız kaynak başına ek sınır | Hayır. Saldırgan 3 istekle Ayşe'nin hakkını yine bitirir. 3 istek her kaynak sınırının altındadır. | Hayır | Yalnız toplu denemeyi yavaşlatır. |
| 2. Adres sınırını kaynağa göre bölmek | Evet. Bir kaynak bir adresin en çok 2 yuvasını alır. 3. yuva başka kaynağa kalır. | Hayır | Seçilen yolun çekirdeğidir. |
| 3. Sınırı adres ve kaynak çiftine göre saymak | Evet | Hayır | Adrese giden toplam e-posta sınırsız olur. PO kuralını bozar. Elenir. |
| 4. Ters vekil sunucuda sınır | Hayır. Ters vekil adresi görmez. Yalnız IP adresine göre sayar. | Hayır | Ayrıntı aşağıdadır. |
| 5. Sınırı tarayıcı çerezine bağlamak | Hayır. Saldırgan çerezi her istekte siler. | Hayır | Elenir. |

### Ters vekil sunucuda sınır

Ters vekil sunucu Caddy'dir (`backend/deploy/compose/edge.yaml`). Bu yol elendi. Gerekçeler şunlardır:

1. Caddy imajı `caddy:2.10.2-alpine` resmî imajdır. Bu imajda `rate_limit` modülü yoktur. Modül için özel Caddy derlemesi gerekir. Bu, yayın imajını ve bakımı değiştirir.
2. Caddy formdaki adresi okumaz. Yalnız IP adresine göre sayar. Bu yüzden 1. yoldan farkı yoktur. Ayşe'nin hakkını korumaz.
3. Bütün giriş adımları aynı adrese gönderilir: `login-actions/authenticate`. Parola formu da bu adrese gider. Caddy'deki sınır parola girişini de keser.

Caddy'nin bu işte başka bir görevi vardır. Caddy, Keycloak'a gerçek istemci adresini iletir. Ayrıntı "Önkoşul" bölümündedir.

### Karar

2. yol seçildi. 1. yol buna ek katman olarak eklenir. İkisi de aynı eklenti çatalında, Keycloak'ın içinde çalışır. Dört kural vardır:

| Kural | Değer | Ayar anahtarı |
| --- | --- | --- |
| Adres sınırı. PO kuralıdır, değişmez. | Bir adrese 900 saniyede en çok 3 e-posta | `magiclink.send.limit` ve `magiclink.send.window.seconds` (var olan) |
| Kaynak payı | Bir kaynak bir adresin 3 yuvasından en çok 2'sini alır | `magiclink.send.source.share`, değer `2` |
| Kaynak tavanı | Bir kaynak 900 saniyede en çok 20 bağlantı isteği yapar. Var olmayan adresler de sayılır. | `magiclink.request.source.limit`, değer `20` |
| Kuyruk tavanı | En çok 1000 e-posta işi aynı anda bekler | `magiclink.send.queue.max`, değer `1000` |

Gerekçeler şunlardır:

- Kaynak payı adres sınırının altındadır. Bu yüzden tek kaynak bir adresin bütün hakkını alamaz.
- Payın değeri `limit - 1` olarak seçildi. Böylece Ayşe kendi cihazından bir kez daha isteyebilir. Pay 1 olsaydı Ayşe 15 dakikada yalnız bir e-posta alırdı.
- Adres sınırı değişmez. Bu yüzden adrese 15 dakikada yine en çok 3 e-posta gider.
- Kaynak tavanı tek kaynağın çok adrese istek yağdırmasını keser. Bu tavan kuyruğu da korur.
- Kuyruk tavanı Oracle'ın 4. bulgusunu kapatır. Ayrıntı aşağıdadır.
- Bütün sınırlar arka planda ya da yanıttan bağımsız çalışır. Yanıt ve süresi değişmez. Bu yüzden hesap ele verilmez.

### Tek kaynaktan gelen saldırı nasıl durur

Örnek şöyledir:

1. Saldırgan tek bir yerden Ayşe'nin adresiyle 3 istek gönderir.
2. Sistem ilk 2 istek için e-posta gönderir. Kaynak payı burada dolar.
3. Sistem 3. istek için e-posta göndermez. Saldırgan yine aynı yanıtı görür.
4. Ayşe kendi telefonundan bağlantı ister. Ayşe'nin kaynağı başkadır.
5. Sistem adresin 3. yuvasını Ayşe'ye verir. Ayşe e-postayı alır ve girer.

Saldırgan her 15 dakikada yinelese de en çok 2 yuva alır. 3. yuva her zaman başka bir kaynağa kalır.

### Arka plan işinin yeni sırası

Sistem istek sırasında kaynağı bulur. Kaynağı `context.getConnection().getRemoteAddr()` verir. Keycloak bu adresi `KC_PROXY_HEADERS=xforwarded` ayarıyla Caddy'den alır. Kaynak, arka plan işine verilir. İstek sırasında başka iş eklenmez.

Arka plan işi şu sırayla çalışır:

1. Kaynak geçerliyse iş kaynak tavanında yuva arar. Yuva yoksa iş e-posta göndermeden biter. Bu adım kullanıcı aranmadan önce yapılır. Böylece var olmayan adresler de sayılır.
2. Kullanıcı yoksa iş biter.
3. İş kullanıcının kayıtlı adresini okur.
4. Kaynak geçerliyse iş kaynak payında yuva arar. Yuva yoksa iş biter.
5. İş adres sınırında yuva arar. Yuva yoksa iş biter.
6. İş `MAGIC_LINK_SESSION` kaydını yazar ve e-postayı gönderir.

Sıra önemlidir. Kaynak payı adres sınırından önce denenir. Böylece payı dolan kaynak adresin yuvasını harcayamaz. Ters sırada saldırgan 3. yuvayı yine tüketirdi.

Yuva anahtarları şunlardır:

- Kaynak tavanı: `magiclink-req:<realm kimliği>:<kaynak özeti>:<sıra>`
- Kaynak payı: `magiclink-send-src:<realm kimliği>:<adres özeti>:<kaynak özeti>:<sıra>`
- Adres sınırı: `magiclink-send:<realm kimliği>:<adres özeti>:<sıra>` (var olan)

Kaynak özeti, kaynağın SHA-256 özetidir. Önbellekte açık IP adresi durmaz.

### Geçersiz kaynak

Bazı adresler gerçek istemciyi göstermez. Örneğin Docker ağ geçidinin adresi böyledir. Bu adresler şunlardır:

- Yerel adresler: `127.0.0.0/8` ve `::1`
- Özel ağlar: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` ve `fc00::/7`
- Bağlantı yerel adresleri: `169.254.0.0/16` ve `fe80::/10`

Kaynak bu adreslerdense sistem kaynak payını ve kaynak tavanını uygulamaz. Yalnız adres sınırı çalışır. Bu, bugünkü davranıştır.

Gerekçe şudur: Bu adreslerin arkasında çok kişi olabilir. Onları tek kaynak saymak herkesi birlikte engeller.

IPv4 adresi IPv6 içinde gelebilir. Örneğin `::ffff:203.0.113.7` böyledir. Sistem bu adresi IPv4 adresi sayar.

### Önkoşul: gerçek istemci adresi Keycloak'a ulaşmalı

Seçilen yol gerçek istemci adresine dayanır. Depoda iki kanıt var:

- `stack.yaml` dosyasında Keycloak'ın dış portu yoktur. Keycloak'a yalnız Caddy ulaşır. Bu doğrudur.
- Caddy, istemcinin gönderdiği `X-Forwarded-For` başlığına güvenmez. Caddy bu başlığı kendi gördüğü adresle yazar. Depoda `trusted_proxies` ayarı yoktur. Bu da doğrudur.

Bir açık var. `site.caddy.template` dosyası bunu yazar: "a public IPv6 client can reach Caddy from the Docker gateway address." Yani IPv6 ile gelen kişiyi Caddy, Docker ağ geçidi adresinden görür. Bu adres özel ağdadır. Bu yüzden sistem IPv6 kişileri için yalnız adres sınırını uygular. Saldırgan IPv6 kullanırsa Ayşe'yi yine engelleyebilir.

Bu açığı kapatmak altyapı işidir. İş Hüseyin Cengiz'e aittir. PO bu işi açar. Önerilen teknik yol şudur:

1. Docker'da IPv6 açılır. Caddy'nin ağı IPv6 adresi alır.
2. Docker'ın `userland-proxy` aracı kapatılır. Böylece kaynak adres korunur.
3. Bu iki adım olmazsa Caddy `network_mode: host` ile çalışır. Seçimi Hüseyin Cengiz yapar.

Hüseyin Cengiz sonucu şöyle doğrular: IPv6 ile bir istek gönderilir. Caddy kaydında Docker ağ geçidi değil, gerçek IPv6 adresi görünmelidir. Bu iş canlı sunucuya dokunur. Bu yüzden bu not bu işi yapmaz.

### Ayşe'nin öbür giriş yolları

İş, Ayşe'nin parola ve başka yollarla girişinin açık kalıp kalmadığını sordu. Keycloak 26.8.2 kaynağı ve realm dosyası okundu. Canlı deneme yapılmadı.

| Yol | Saldırgan engelleyebilir mi? | Kanıt |
| --- | --- | --- |
| Parola | Evet. Bu yeni bir bulgudur. | Kaba kuvvet koruması yanlış girişleri kişiye göre sayar, kaynağa göre saymaz. Realm ayarları `failureFactor: 5`, `bruteForceStrategy: MULTIPLE`, `maxFailureWaitSeconds: 900` şeklindedir. Saldırgan 5 yanlış parolayla Ayşe'nin parola girişini kilitler. Kilit 60 saniyeden başlar ve 900 saniyeye çıkar. `UsernamePasswordForm`, `AbstractUsernameFormAuthenticator.enabledUser()` içinde bu kilidi denetler. |
| Passkey | Kodda kilit denetimi bulunmadı. | Realm'de `webAuthnPolicyPasswordlessPasskeysEnabled: true` vardır. `UsernamePasswordForm` passkey formunu doğrudan `webauthnAuth.action()` yöntemine verir. `WebAuthnAuthenticator.java` dosyasında kilit çağrısı yoktur. Canlı denenmedi. |
| Sihirli bağlantı | Bu iş bitince hayır. Önkoşul gerekir. | Eklentinin `MagicLinkAuthenticatorNormal.java` dosyası kilidi denetlemez. Bu yüzden parola kilitliyken bağlantı yolu açık kalır. |
| İkinci adım (TOTP) | Evet, parola kilidiyle aynı sayaç | `OTPFormAuthenticator` da `AbstractUsernameFormAuthenticator` sınıfından gelir. Kilitli kişi bağlantıdan sonra da TOTP adımında durur. |
| Parola sıfırlama | Denetlenmedi | `resetPasswordAllowed: true` vardır. Sıfırlama e-postasının sıklık sınırı bu işte okunmadı. |

Tek bir saldırgan bugün iki yolu birlikte kapatabilir. Parolayı kaba kuvvet kilidiyle kapatır. Bağlantıyı adres sınırıyla kapatır. Bu iş bağlantı yolunu açık tutar. Parola kilidi ayrı bir risktir. PO bu riske karar verir. Seçenekler şunlardır:

- Kilit kalır. Ayşe bağlantı ya da passkey ile girer. Bu iş bunu sağlar.
- Kilit kaynağa göre de sayılır. Keycloak bunu hazır sunmaz. Ek eklenti gerekir.

TOTP'li kişide durum farklıdır. Kilitli kişi bağlantıyla da TOTP adımına takılır. Bu durumda Ayşe yalnız passkey ile girebilir. Passkey canlı denenmedi.

### Oracle'ın küçük bulguları

1. **Arka plan kuyruğu sınırsız.** Keycloak 26.8.2 kaynağı okundu. `DefaultExecutorsProviderFactory.createPoolEmbedded()` kuyruğu `new LinkedBlockingQueue<>()` ile kurar. Bu kuyruğun sınırı yoktur. Havuz 4 iş parçacığıyla çalışır. SMTP yavaşlarsa kuyruk büyür ve bellek dolabilir. Bu yüzden kuyruk tavanı eklenir. Sistem bekleyen işleri sayar. Sayı 1000'e ulaşırsa sistem yeni işi kuyruğa koymaz ve uyarı yazar. Yanıt değişmez. Kaynak tavanı da kuyruğa giren işi azaltır.
2. **Büyük harfli adres ve kullanıcı adı testi eksik.** Kod bu durumları doğru sayar. Test bunu denetlemez. Geliştirici aşağıdaki testi ekler.
3. **`test_magic_link.py` dosyasının 278. satırındaki açıklama eski.** Açıklama, eklentinin e-postayı yanıttan önce gönderdiğini söyler. Bu artık doğru değil. Yeni açıklama şöyle olur: "The mail goes out in a background job after the answer. The answer does the same work for an existing and an unknown address."
4. **Sayaç anahtarı tuzsuz özet kullanır.** Bu iş bunu değiştirmez. Anahtar yalnız Keycloak'ın iç önbelleğindedir. Kaynak özeti de aynı biçimdedir.

### K-38 ile ilişki

K-38 yolu değişmez. `cloudflightio/keycloak-magic-link` eklentisi kalır. Kaynak yine sabit commit `7b4ee949` ve SHA-256 özetiyle indirilir. Değişiklikler yalnız `magic-link-fork/` klasöründeki dosyalardadır. Phase Two eklentisi kullanılmaz. Ters vekil sunucuya modül eklenmez.

### Düşen testler

Geliştirici önce bu testleri yazar. Testler bugünkü kodda düşmelidir. Sonra kodu yazar.

Testler kaynakları `X-Forwarded-For` başlığıyla taklit eder. Bunun için yerel Keycloak `KC_PROXY_HEADERS=xforwarded` ile çalışır. Yerel Keycloak yalnız `127.0.0.1` adresini dinler. Bu yüzden ayar dışarıya açılmaz. Test adresleri belgeleme aralıklarındandır: `203.0.113.0/24` ve `198.51.100.0/24`.

`backend/identity/keycloak/tests/test_magic_link.py` dosyasına şu canlı testler eklenir:

1. `test_one_source_cannot_use_up_another_persons_mails`
   - Test yeni bir adres açar. Sınır realm dosyasındaki değere döner.
   - Saldırgan `203.0.113.7` kaynağından 3 istek gönderir. Test tam 2 e-posta bekler.
   - Ayşe `198.51.100.9` kaynağından 1 istek gönderir. Test Ayşe'nin isteğinden sonra 1 yeni e-posta bekler.
   - Bütün yanıtlar aynı olmalıdır. Test bunu `_without_session_values` ile denetler.
   - Bugün bu test düşer. Saldırganın 3 isteği 3 yuvayı da alır. Ayşe'ye e-posta gitmez.
2. `test_two_sources_still_get_at_most_three_mails`
   - Test yeni bir adres açar.
   - İki kaynak sırayla 3'er istek gönderir. Test toplam tam 3 e-posta bekler.
   - Bu test PO kuralını korur.
3. `test_source_request_ceiling_counts_unknown_addresses`
   - Test kaynak tavanını geçici olarak 5 yapar. Bu, var olan sınır yükseltme yöntemiyle yapılır. Test bitince eski değer geri yazılır.
   - Bir kaynak 5 kez var olmayan adres ister. Sonra aynı kaynak var olan yeni bir adres ister. Test e-posta beklemez.
   - Başka bir kaynak aynı adresi ister. Test 1 e-posta bekler.
4. `test_private_source_gets_no_source_limit`
   - Test başlık göndermez. Kaynak Docker ağ geçidi adresi olur.
   - Test yeni bir adrese 3 istek gönderir. Test tam 3 e-posta bekler.
   - Bu test IPv6 kişilerinin birlikte engellenmesini önler.
5. `test_upper_case_address_and_username_share_the_address_limit`
   - Test yeni bir adres ve kullanıcı adı açar.
   - Aynı kaynak yerine iki kaynak kullanılır. Böylece kaynak payı sonucu bozmaz.
   - İstekler sırayla küçük harfli adres, büyük harfli adres ve kullanıcı adıyla gönderilir. 4. istek yine büyük harfli adresle gönderilir.
   - Test tam 3 e-posta bekler.
   - Bu test bugün geçebilir. Test Oracle'ın 6. bulgusunu kapatır. Gelecekteki bir hatayı yakalar.

`MagicLinkFileTest` sınıfına şu dosya testleri eklenir:

1. `test_source_limits_are_in_the_realm_file` testi realm dosyasını denetler. Realm dosyasında `magiclink.send.source.share` değeri `2`, `magiclink.request.source.limit` değeri `20` ve `magiclink.send.queue.max` değeri `1000` olmalıdır. Kaynak payı adres sınırından küçük olmalıdır.
2. `test_send_queue_has_a_ceiling` testi çatal kodunu denetler. Çatal kodu `magiclink.send.queue.max` ayarını okumalıdır.

`backend/deploy/tests` altına şu dosya testi eklenir:

1. `test_keycloak_sees_the_real_client_address` testi yayın dosyalarını denetler. `stack.yaml` dosyasında Keycloak'ın `ports` alanı olmamalıdır. `KC_PROXY_HEADERS` değeri `xforwarded` olmalıdır. Caddy dosyalarında `trusted_proxies` olmamalıdır.

Var olan testler ve eşikler gevşetilmez. `SEND_LIMIT` 3, `TIMING_TOLERANCE_SECONDS` 0,002 olarak kalır. Var olan testler başlık göndermez. Bu yüzden onların kaynağı özel ağdadır. Kaynak kuralları onları etkilemez.

Kuyruk tavanı canlı test edilemez. SMTP'yi yavaşlatmak gerekir. Bu durum `not_run` olarak yazılır.

### Geliştiricinin değiştireceği dosyalar

İş `pc/g162-rate-limit` dalının üstüne yapılır. O dal `backend` dalına girdiyse iş `backend` dalından açılır.

1. `backend/identity/keycloak/magic-link-fork/src/main/java/io/cloudflight/keycloak/magiclink/sending/MagicLinkSendLimiter.java` dosyası değişir. Kaynak tavanı ve kaynak payı yöntemleri eklenir. Kaynağı bulan ve geçersiz kaynağı ayıran kod da buraya gelir. IPv6 adresi ilk 64 bite indirgenir.
2. `backend/identity/keycloak/magic-link-fork/src/main/java/io/cloudflight/keycloak/magiclink/authenticators/AbstractMagicLinkAuthenticator.java` dosyası değişir. `action()` kaynağı okur ve arka plan işine verir. `sendInBackground()` yukarıdaki sırayla çalışır. `scheduleSend()` bekleyen işleri sayar ve kuyruk tavanını uygular. Dosya başındaki değişiklik listesi güncellenir.
3. `backend/identity/keycloak/magic-link-fork/src/main/java/io/cloudflight/keycloak/magiclink/authenticators/AbstractMagicLinkAuthenticatorFactory.java` dosyası değişir. Üç yeni ayar tanımlanır. Böylece ayarlar yönetim konsolunda görünür.
4. `backend/identity/keycloak/magic-link-fork/NOTICE` dosyası değişir. Yeni değişiklik ve tarih yazılır.
5. `backend/identity/keycloak/realm/platform-realm.json` dosyası değişir. `atonota-magic-link` ayarına üç değer eklenir.
6. `backend/dev/compose.keycloak.yaml` dosyası değişir. Yerel Keycloak'a `KC_PROXY_HEADERS: xforwarded` eklenir.
7. `backend/identity/keycloak/tests/test_magic_link.py` dosyası değişir. Yukarıdaki testler eklenir. 278. satırdaki açıklama düzeltilir.
8. `backend/deploy/tests/` klasörü değişir. Gerçek istemci adresi testi eklenir. Uygun dosya `test_remote.py` ya da yeni bir dosyadır. Seçimi geliştirici yapar.
9. `backend/docs/decisions/0003-keycloak-extensions.md` dosyası değişir. İş bitince kanıt yazılır. Kanıt, geçen testlerin adı ve commit kimliğidir.

Değişmeyecek dosyalar şunlardır: `backend/identity/keycloak/Dockerfile`, `backend/deploy/compose/Caddyfile` ve `backend/deploy/compose/edge.yaml`.

### Kabul

- `PANE_PORT=<boş port> COMPOSE_PROJECT_NAME=<ayrı ad> bin/kc-dev.sh test` komutu bütün testleri geçer.
- Yeni canlı testlerden 1, 2, 3 ve 4 numaralı testler önce düşer. Düşüş kanıtı commit'te görünür.
- Gerçek SMTP ile deneme yapılmadı. IPv6 önkoşulu canlı sunucuda doğrulanmadı.

### Kalan risk

- Saldırgan çok kaynak kullanırsa Ayşe'yi yine engelleyebilir. Örneğin iki ayrı ev bağlantısı yeterlidir. PO'nun kararı tek kaynağı kapsar. Bu risk açık kalır.
- IPv6 önkoşulu bitene kadar IPv6 saldırganı tek kaynak sayılmaz. O zamana kadar bu koruma yalnız IPv4 için çalışır.
- Aynı ağı paylaşan kişiler tek kaynak sayılır. Örneğin bir ofis tek IPv4 adresiyle çıkabilir. Bu kişiler kaynak tavanını paylaşır. Tavan 20 istek olarak bu yüzden geniş seçildi.
- Kümede sayaç ve bekleyen iş sayısı düğüme göre değişebilir. Çok düğümlü kurulumda sınırlar yeniden sınanır.
