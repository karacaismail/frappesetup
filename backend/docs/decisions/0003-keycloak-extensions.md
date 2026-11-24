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
- G-162 bu kararı 24 Kasım 2026 Salı günü yeniden açtı. Çatal kararı aşağıdaki G-162 bölümündedir.
- Giriş ve e-posta şablonları eklentinin jar dosyasından gelir. Türkçe metinler kimlik-tema işinin `atonota` temasında verilir.

### identity-sync rolleri (sözleşme 26a274c)

identity-sync davet ve kuruluş hazırlama için Keycloak'a yazar. Servis hesabı şu rolleri taşır: `view-users`, `query-users`, `manage-users`, `view-organizations`, `manage-organizations`, `view-identity-providers`. `manage-clients`, `manage-realm` ve `impersonation` yoktur. Roller yalnız `scope=admin-api kc-admin-api` belirtecine girer. Kiracı hedefli belirteç bu rolleri taşımaz ve Admin API'de 401 ya da 403 alır.

En az rol kümesi Keycloak 26.8.2 kaynağından çıkarıldı:

| İş | Keycloak ucu ve denetimi | Gereken rol |
| --- | --- | --- |
| Kullanıcı açma, davet e-postası (`execute-actions-email`) | `UsersResource` ve `UserResource`: `auth.users().requireManage()` | `manage-users` |
| Kullanıcı okuma ve arama | `auth.users().requireView()` ve `requireQuery()` | `view-users` (bileşik: `query-users`, `query-groups`) |
| Kuruluş açma | `services/src/main/java/org/keycloak/organization/admin/resource/OrganizationsResource.java`: `auth.orgs().requireManage()` | `manage-organizations` |
| Kuruluşa üye ekleme ve çıkarma | `OrganizationMemberResource.java`: `auth.orgs().requireManage(organization)` ve `auth.users().requireView(member)` | `manage-organizations` ve `view-users` |
| Kuruluş daveti | `OrganizationInvitationResource.java`: `auth.orgs().requireManage(organization)` | `manage-organizations` |
| Kuruluş okuma ve arama | `auth.orgs().requireView(organization)` ve `requireQuery()` | `view-organizations` (bileşik: `query-organizations`) |
| Giriş platformlarını okuma (AJA-459) | `GET /admin/realms/<realm>/identity-provider/instances`. Kaynak satırı bu işte açılmadı. Canlı Keycloak denemesi gerekir. | `view-identity-providers` |

Bileşik roller `services/src/main/java/org/keycloak/services/managers/RealmManager.java` 285 ile 289. satırlarında tanımlıdır. `manage-*` rolleri `view-*` rollerini içermez. Bu yüzden `view-users` ve `view-organizations` açıkça verilir. Rol adları `server-spi-private/src/main/java/org/keycloak/models/AdminRoles.java` dosyasındadır.

Canlı test (`test_identity_sync_admin_scope_can_create_user_and_organization`) admin-api belirteciyle kullanıcı ve kuruluş açar (201). Aynı belirteçle istemci açma 403 alır. Kiracı hedefli belirteç Admin API'de 401 ya da 403 alır (`test_kiraci_belirtecinde_yonetim_yetkisi_yok`).

### AtonotA Login okuma uçları (AJA-459)

Bu bölüm 24 Kasım 2026 Salı günü eklendi. Kaynak güvenlik incelemesidir (AJA-458).

1. Panel iki şeyi okur: giriş platformlarını ve kullanıcının bağlı hesaplarını.
2. Okumayı `identity-sync` yapar. Kiracı sitesi Keycloak yönetim rolü taşımaz.
3. `identity-sync` hesabına yalnız `view-identity-providers` rolü eklendi. Rol yalnız `admin-api kc-admin-api` kapsamlı belirtece girer.
4. `manage-identity-providers` rolü verilmez. Site servis hesabının rolleri değişmez.
5. Platform listesi kiracıya göre süzülür. Başka kiracının kurumsal platformu listeye girmez.
6. Sırrı olmayan platform listeye girmez. Servis bunu `config.clientSecret` alanından anlar. Boş değer ve çözülmemiş `${...}` değeri sır sayılmaz.
7. Keycloak yönetim yanıtı sırrı `**********` diye gizler. Keycloak boş sırrı da böyle gizleyebilir. Bu durumda asıl denetim platformun açık olmasıdır. Kapalı platform listeye hiç girmez. Bu davranış canlı Keycloak 26 denemesiyle doğrulanmalıdır.
8. Servis platform listesini 30 saniye tutar. Kapatılan bir platform bu süre boyunca listede kalabilir.

Kalan risk şudur: ele geçirilmiş bir kiracı sitesi kendi üyelerinin bağlı hesaplarını okuyabilir. Site başka kiracının üyelerini okuyamaz. `identity-sync` kişinin kiracı üyesi olup olmadığına bakar. Bu sınır `/v1/sessions/revoke` ucundaki sınırla aynıdır. Güvenlik incelemesi bu riski kabul etti.

Panel hesabı Frappe'de “Website User” türündedir. Frappe bu hesaba yalnız izin listesindeki yöntemleri açar. İki okuma yöntemi `platform_core/hooks.py` içindeki `website_user_allowed_methods` listesine eklendi. Yöntemler kişiyi yalnız oturumdan alır. `subject` ve `user` parametrelerini reddeder.

#### Yerel yığında servis belirteci

Bu karar 24 Kasım 2026 Salı günü yazıldı.

1. Kiracı sitesi servis belirtecini Keycloak'tan HTTPS ile alır. Kod HTTP adresini her ortamda reddeder. Geliştirme bayrakları açıkken de reddeder. `test_keycloak_requires_https_even_with_both_development_flags` testi bu kuralı korur.
2. Bu kural gevşetilmedi. Üretimde HTTP kabul eden yeni bir ayar eklenmedi.
3. Yerel yığında Keycloak HTTP kullanır. Bu yüzden iki okuma ucu yerel yığında 503 verir. Telefon oturumu kapatma ucu da aynı nedenle yerelde çalışmaz.
4. Yerel çözüm, birleştirme önizlemesindeki HTTPS aktarıcısıdır: `e2e/preview/session-tls.sh`. Aktarıcı `identity-sync` kapsayıcısında çalışır. Keycloak belirteç ucunu 9444 portunda, `identity-sync` uçlarını 9443 portunda HTTPS ile sunar.
5. Aktarıcı yalnız adı yazılı yolları geçirir. İki okuma ucu bu listeye eklendi.
6. Gerekçe şudur: belirteç bir sırla alınır. Sırrın düz HTTP ile gitmesine kod izin vermemelidir. Yerel kolaylık için üretim kodunda istisna açılmaz.

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

## G-162 düzeltmesi: tasarım kararı (24 Kasım 2026 Salı günü, B Takımı mimarı)

Testçi iki eksik buldu. Testler `backend/identity/keycloak/tests/test_magic_link.py` dosyasındadır. İki test bilerek düşer.

1. Var olan adreste yanıt daha geç gelir. Ölçülen fark yaklaşık 4 ile 5 ms'dir.
2. Gönderim sınırı yoktur. 8 istek 8 e-posta gönderdi.

PO kararları şunlardır:

- Aynı adrese 15 dakikada en çok 3 e-posta gider.
- Sınır aşılınca sistem e-posta göndermez. Kişi yine "E-postanızı kontrol edin." yanıtını görür.
- Var olan ve olmayan adreste yanıt süresi aynı olur. E-posta gönderimi yanıtı geciktirmez.
- K-38 yolu değişmez. `cloudflightio/keycloak-magic-link` eklentisi kalır. Phase Two eklentisi kullanılmaz.

### Sorunun kaynağı

Sorun eklentinin `action()` yöntemindedir. Dosya `AbstractMagicLinkAuthenticator.java` şeklindedir. Kaynak sabit commit `7b4ee949` ile okundu.

- Kullanıcı varsa yöntem anahtar üretir. Sonra `MAGIC_LINK_SESSION` tablosuna kayıt yazar.
- Sonra e-postayı aynı istekte gönderir. Yanıt e-posta gidene kadar bekler.
- Kullanıcı yoksa yöntem yalnız bilgi sayfasını gösterir.
- Sayım yapan bir yer yoktur.
- E-posta gönderilemezse yöntem 500 hatası döner. Bu hata da hesabın var olduğunu gösterir.

### İki yolun karşılaştırması

| Ölçüt | 1. yol: eklentinin çatalı ve yaması | 2. yol: eklentinin önünde ayrı Keycloak adımı |
| --- | --- | --- |
| Süre eşitliği | Sağlar. Kayıt ve gönderim istekten çıkar. | Sağlamaz. Gönderim eklentinin `action()` yöntemindedir. Önceki adım bu yönteme dokunamaz. |
| Sıklık sınırı | Sağlar. Sayım gönderimden hemen önce yapılır. | Zor. E-posta formu eklentinin adımına gönderilir. Önceki adım adresi görmez. |
| Adım kimliği | `magiclink` kalır. Realm akışı değişmez. | Yeni adım gerekir. Eklentiyi alt sınıfla sarmak da yeni kimlik ister. Var olan dosya testi `magiclink` kimliğini arar. |
| K-38 ve lisans | Aynı eklenti, Apache-2.0. Not çatalı zaten öngörür. | Aynı eklenti kalır. Ama sorun çözülmez. |
| Bakım | Değişen dosyalar bizdedir. Keycloak yükseltmesinde yeniden sınanır. | Ek adımın bakımı bizdedir. |

### Karar

1. yol seçildi. Eklenti sabit commit ve SHA-256 özetiyle indirilmeye devam eder. Derleme aşaması indirilen kaynağın üstüne bizim değişen dosyalarımızı kopyalar. Sonra Maven derler.

Gerekçeler şunlardır:

- Süre farkı eklentinin içindeki eşzamanlı gönderimden gelir. Bu farkı yalnız eklentinin içinde değişiklik kapatır.
- Adım kimliği ve realm akışı aynı kalır. Var olan testler değişmeden geçer.
- Arşiv sabit kalır. Değişiklik küçük ve okunur kalır. `test_extension_is_built_from_pinned_source_with_checksum` testi geçmeye devam eder.
- Maven imajında `patch` ve `git` araçları yoktur. 24 Kasım 2026 Salı günü imaj denetlendi. Bu yüzden yama dosyası yerine değişen dosyaların tam kopyası kullanılır. Ek paket kurulmaz.

### Sayacın yeri

Sayaç Keycloak'ın kendi `SingleUseObjectProvider` önbelleğinde tutulur. Bu arayüz Keycloak 26.8.2'de vardır. Arayüz `keycloak-server-spi` jar dosyasındadır. `putIfAbsent(anahtar, saniye)` yöntemi tek adımda çalışır.

Sayım şöyle çalışır:

1. Sistem adres için 3 yuva anahtarı kurar. Anahtar biçimi `magiclink-send:<realm kimliği>:<adres özeti>:<1, 2 ya da 3>` olur.
2. Adres özeti, küçük harfe çevrilmiş adresin SHA-256 özetidir. Önbellekte açık adres durmaz.
3. Sistem yuvaları sırayla `putIfAbsent(yuva, 900)` ile dener.
4. Bir yuva boşsa sistem yuvayı alır ve e-postayı gönderir.
5. Üç yuva doluysa sistem e-posta göndermez. Kişi yine aynı yanıtı görür.
6. Her yuva alındıktan 900 saniye sonra kendiliğinden boşalır.

Bu yöntem kayan bir süre penceresi kurar. Herhangi bir 15 dakikada aynı adrese en çok 3 e-posta gider. Aynı anda gelen 8 istek de en çok 3 e-posta gönderir.

Sayı ve süre realm dosyasından okunur. Ayarlar `atonota-magic-link` yapılandırmasına eklenir:

- `magiclink.send.limit` değeri `3` olur.
- `magiclink.send.window.seconds` değeri `900` olur.

Başka yerler elendi:

- Veritabanı tablosu elendi. Liquibase değişikliği ister. Eski satırları silmek için zamanlı iş gerekir.
- Önündeki ters vekil sunucu elendi. Ters vekil adresi görmez. Yalnız IP adresine göre sayar.
- Keycloak'ın kaba kuvvet koruması elendi. Bu koruma yanlış girişleri sayar. Gönderilen e-postaları saymaz.

Sınırlar şunlardır:

- Keycloak yeniden başlarsa tek düğümde sayaç sıfırlanır. Bu kabul edildi.
- Kümede bu önbellek düğümler arasında paylaşılır. Bunu Keycloak'ın önbellek ayarı sağlar. Çok düğümlü kurulumda sınır yeniden sınanır.
- Yuva gönderimden önce alınır. E-posta gönderilemezse yuva yine dolu sayılır. Bu, kötüye kullanıma karşı güvenli taraftır.

### Yanıt süresini eşitleme yolu

E-posta arka planda gönderilir. İstek iki adreste de aynı işi yapar.

İstek sırasında yapılan işler şunlardır:

1. Sistem adresi arar. Bu arama iki durumda da yapılır.
2. Sistem anahtarı ve bağlantı kimliğini üretir. Bunu kullanıcı yoksa da yapar.
3. Sistem bağlantı kimliğini giriş oturumuna yazar. Bunu da iki durumda yapar.
4. Kullanıcı varsa sistem kullanıcıyı giriş oturumuna bağlar.
5. Sistem bir arka plan işi kuyruğa koyar. Bunu iki durumda da yapar.
6. Sistem bilgi sayfasını gösterir.

Arka plan işi `KeycloakModelUtils.runJobInTransaction` ile kendi oturumunda çalışır. İş, `ExecutorsProvider.getExecutor("atonota-magic-link")` havuzunda çalışır. İş, isteğin kaydı bittikten sonra kuyruğa girer. Bunun için `session.getTransactionManager().enlistAfterCompletion` kullanılır.

Arka plan işi şunları yapar:

1. Kullanıcı yoksa iş hiçbir şey yapmaz ve biter.
2. İş kullanıcıyı kimliğiyle yeniden okur. Realm'i oturuma koyar.
3. İş sayaçta yuva arar. Yuva yoksa e-posta göndermeden biter.
4. İş `MAGIC_LINK_SESSION` kaydını yazar. Kayıt e-postadan önce yazılır. Böylece bağlantı kayıttan önce gelemez.
5. İş e-postayı gönderir.
6. Gönderim başarısız olursa iş yalnız uyarı yazar. Uyarıda bağlantı ve anahtar yoktur. Kişi farkı görmez.

Bu yolla iki adreste yanıt aynı işi yapar. Veritabanı kaydı ve e-posta yanıt süresine girmez. 500 hatası da kalkar.

### Testlerle ilişki

- `SEND_LIMIT` 3 olarak kalır. `TIMING_TOLERANCE_SECONDS` 0,002 saniye olarak kalır. Eşikler gevşetilmez.
- Testler aynı adrese 15 dakikada 3'ten çok bağlantı ister. Örneğin süre testi tek adrese 15 istek gönderir. Bu yüzden canlı test sınıfı sınırı kendi süresince geçici olarak yükseltir. Bu, var olan `test_expired_link_is_refused` testindeki yöntemle yapılır. Test bitince eski ayar geri yazılır.
- Sıklık testi kendi adresini kullanır. Bu adres başka testte kullanılmaz. Test başında sınır realm dosyasındaki değere döner.
- Sıklık testi güçlenir. Test 8 istekte tam 3 e-posta bekler. Sıfır e-posta da hata sayılır.
- Yeni dosya testi realm dosyasında 3 ve 900 değerlerini denetler.
- Yeni dosya testi Dockerfile'ın değişen dosyaları kopyaladığını denetler.

### Geliştiricinin değiştireceği dosyalar

1. `backend/identity/keycloak/magic-link-fork/src/main/java/io/cloudflight/keycloak/magiclink/authenticators/AbstractMagicLinkAuthenticator.java` dosyası yeni açılır. Bu dosya sabit commit'teki dosyanın değişen kopyasıdır. `action()` ve `sendLink()` yöntemleri değişir. Dosyanın başına değişiklik notu yazılır.
2. `backend/identity/keycloak/magic-link-fork/src/main/java/io/cloudflight/keycloak/magiclink/sending/MagicLinkSendLimiter.java` dosyası yeni açılır. Bu sınıf yuva sayımını yapar.
3. `backend/identity/keycloak/magic-link-fork/NOTICE` dosyası yeni açılır. Dosya değişen dosyaları ve tarihi yazar. Apache-2.0 lisansının 4. maddesi bunu ister.
4. `backend/identity/keycloak/Dockerfile` dosyasında `magiclink-build` aşaması değişir. Arşiv açıldıktan sonra `COPY magic-link-fork/ ...` satırı gelir. Sonra Maven derler. Arşivin adresi ve özeti değişmez.
5. `backend/identity/keycloak/.dockerignore` dosyasına `!magic-link-fork/` ve `!magic-link-fork/**` satırları eklenir. Bu satırlar olmazsa yeni klasör derlemeye girmez.
6. `backend/identity/keycloak/realm/platform-realm.json` dosyasında `atonota-magic-link` ayarına iki değer eklenir.
7. `backend/identity/keycloak/realm/dev-users/platform-users-0.json` dosyasına sıklık testi için yeni bir örnek kullanıcı eklenir.
8. `backend/identity/keycloak/tests/test_magic_link.py` dosyasında yukarıdaki test değişiklikleri yapılır. Eşikler ve var olan doğrulamalar gevşetilmez.
9. `backend/docs/decisions/0003-keycloak-extensions.md` dosyasına iş bitince kanıt yazılır. Kanıt, geçen testlerin adı ve commit kimliğidir.

### Kabul

- `bin/kc-dev.sh test` komutu bütün testleri geçer. İki düşen test de geçer.
- Komut şöyle çalıştırılır: `PANE_PORT=<boş port> COMPOSE_PROJECT_NAME=<ayrı ad> bin/kc-dev.sh test`.
- Gerçek SMTP ile süre denenmedi. Yerel ortam Mailpit kullanır. Gerçek SMTP ile de farkın yanıt süresine girmemesi beklenir. Bunun nedeni gönderimin arka planda olmasıdır.

### Uygulama ve kanıt (24 Kasım 2026 Salı günü, AJA-373)

Claude 02 ajanı tasarımı `pc/g162-rate-limit` dalında uyguladı. Düşen testler `5c3236b4` commit'indedir. Kod, bu bölümü taşıyan commit'tedir.

Tasarımdan iki sapma var:

1. Onuncu bir dosya değişti. Dosya `AbstractMagicLinkAuthenticatorFactory.java` şeklindedir. Keycloak, tanımlanmamış ayarı yönetim arayüzünde yıldızla gizler. Gizli değer geri yazılınca eski değer kalır. Bu yüzden iki ayar fabrikada tanımlandı. Ayarlar yönetim konsolunda da görünür.
2. Sıklık testi örnek kullanıcı dosyasını kullanmaz. Test her koşuda yeni bir adres açar. Koşu bitince adresi siler. Sabit adresin yuvaları 15 dakika dolu kalır. Testler bu sürede yeniden koşarsa sabit adrese e-posta gitmez. Bu yüzden `platform-users-0.json` dosyası değişmedi.

E-posta gönderimi, yuva sayımı ve kayıt arka plan işindedir. Her yuva kendi işleminde denenir. Böylece JPA deposu da aynı anda gelen iki isteğin birini reddeder.

Canlı kanıt yerel Keycloak 26.8.2 ve Mailpit ile alındı:

- `bin/kc-dev.sh test -p test_magic_link.py` komutu 19 testi geçti. Yeni testler `test_send_rate_is_limited_per_address`, `test_existing_and_unknown_address_take_the_same_time`, `test_send_limit_is_three_mails_in_fifteen_minutes` ve `test_image_builds_the_fork_files_over_the_pinned_source` şeklindedir.
- `bin/kc-dev.sh test` komutu 244 testi koştu. Hepsi geçti. 20 test ortam eksikliği yüzünden atlandı. Eksikler `PROD_KC_URL` ve ayrı MCP realm'idir.
- `bin/kc-dev.sh prod-check` komutu 8 testi geçti.

Testte bilinen bir sınır var. `fresh_totp_code` kullanılan kodları yalnız bir koşu içinde hatırlar. İki koşu 30 saniye içinde art arda yapılırsa `test_link_does_not_skip_totp` düşebilir. Bu davranış bu işten önce de vardı.

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
