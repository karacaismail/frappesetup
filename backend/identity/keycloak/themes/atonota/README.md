# Atonota Keycloak teması

Bu klasör Keycloak'ın giriş ve e-posta ekranlarını Atonota markasıyla giydirir. Tema Keycloak'ın kendi tema yapısıyla kurulur (proje kaydı O-4). Keycloakify kullanılmaz.

Hedef sürüm Keycloak 26.8.2 sürümüdür. Giriş teması `keycloak.v2` temasından türer.

## Klasörler

| Klasör | İçerik |
| --- | --- |
| `login/` | Giriş teması. Giriş, kayıt, parola sıfırlama, TOTP ve passkey ekranlarını kapsar. |
| `email/` | E-posta teması. |
| `account/` | Hesap konsolu teması. Kullanıcı parolasını, ikinci doğrulamasını ve oturumlarını bu ekranda yönetir. |
| `account-provider/` | Hesap konsolunun küçük sunucu eklentisi. Hesap silme bağlantısını yalnız müşteriye ekler. |
| `test/` | Deneme ortamı ve Playwright testleri. Bu klasör Keycloak imajına girmez. |

TOTP, telefondaki doğrulama uygulamasının ürettiği tek kullanımlık koddur. Passkey, parola yerine kullanılan geçiş anahtarıdır.

## Temayı Keycloak'a koyma

1. `login/`, `email/` ve `account/` klasörlerini imaja kopyalayın. Hedef yol `/opt/keycloak/themes/atonota/` olur.
2. Realm'de giriş temasını `atonota` yapın.
3. Realm'de e-posta temasını `atonota` yapın.
4. Realm'de hesap konsolu temasını `atonota` yapın.
5. Marka adını `IDENTITY_BRAND_NAME` değişkeniyle verin. Ayrıntı “Marka adı” bölümündedir.

Realm dosyası kimlik-realm işinindir. Bu klasör realm dosyasını değiştirmez.

## Marka adı

Marka adı temaya yazılmaz. Marka adı tek bir değişkenden gelir: `IDENTITY_BRAND_NAME`.

| Tema | Marka adını nereden okur |
| --- | --- |
| Giriş teması | Realm'in görünen adından (`displayName`) |
| E-posta teması | Realm'in görünen adından (`realmName`) |
| Hesap konsolu teması | `title` tema ayarından |

Değişkeni iki yere bağlayın:

1. Realm dosyasında görünen adı değişkenden okuyun: `"displayName": "${IDENTITY_BRAND_NAME}"`. Keycloak bu değeri realm'i içe alırken ortamdan okur.
2. Keycloak sunucusuna aynı ortam değişkenini verin. Hesap konsolu teması `title=${env.IDENTITY_BRAND_NAME:Account}` satırıyla bu değişkeni okur.

Değişken yoksa hesap konsolu “Account” yazar. Bu söz marka adı değildir, yansız bir yedektir.

Hesap konsolu Keycloak'ın kendi uygulamasıdır ve yalnız bir logo resmi gösterir. Tema uygulamanın HTML'ini değiştirmez. Bu yüzden ad şöyle çizilir:

1. Keycloak `title` ayarını sayfa başlığına yazar.
2. `account/resources/js/atonota-focus.js` betiği başlığı `--at-brand-name` CSS değişkenine kopyalar.
3. Stil dosyası adı marka işaretinin yanına çizer.

Uzun marka adı dar ekranda üç noktayla kesilir. On harfli ad 320 pikselde kesilmeden sığar. Bunu bir test ölçer.

Deneme ortamı marka adını bilerek “Sample Brand” yapar. Böylece temaya sabit yazılmış bir ad testlerde hemen görünür.

## Görsel kimlik

Atonota bir kimlik ve güven markasıdır. Tema üç şeye dayanır:

- sakin bir kâğıt zemini,
- koyu mürekkep rengi,
- küçük bir mühür noktası.

Bütün renk, yazı, boşluk, köşe ve hareket değerleri `login/resources/css/atonota.css` dosyasının başındadır. Değerler `--at-` ile başlayan CSS değişkenleridir. Kuralların içine sabit değer yazmayın. Örneğin yeni bir renk gerekiyorsa önce bir değişken ekleyin.

## Arayüz kuralları

- Yazı tipi Outfit'tir. Dosyalar `login/resources/fonts/` klasöründedir. Lisans SIL OFL 1.1'dir ve `OFL.txt` dosyasındadır. Tema dış yazı tipi istemez.
- Okunabilir her metin en az 14 CSS pikseldir.
- Tasarım 320 CSS piksel genişlikte başlar.
- Tek başına duran kontrolün etkili alanı en az 44 pikseldir. Dokunmatik ekranda bu alan 48 pikseldir.
- Çevreleyen odak halkası yoktur. Klavye odağı öğenin altındaki düz bir çizgiyle görünür.
- Odak çizgisi yalnız klavye kipinde görünür. Kipi `Tab` ve `Shift+Tab` açar. Fare ve dokunma kipi kapatır. Kipi `login/resources/js/atonota-focus.js` yönetir.
- Köşesi yuvarlak kutunun tek kenarına renkli çizgi konmaz.
- Hareket eğrisi `cubic-bezier(.65, 0, .35, 1)` olur. Kullanıcı azaltılmış hareket isterse geçişler kalkar.
- Dil seçimi işletim sisteminin açılır listesi değildir. Dil seçimi kartın altındaki bağlantı listesidir.

## İletiler

- Türkçe varsayılan dildir. İkinci dil İngilizcedir.
- İletiler `login/messages/` klasöründedir. İki dosya aynı anahtarları taşır.
- İletileri yalın Türkçeyle yazın. Kısa ve tam cümle kurun. “Siz” diye seslenin.
- Marka adını iletiye yazmayın. Marka adı realm'in görünen adından gelir.

## E-posta teması

E-posta teması `email/` klasöründedir. Tema dört e-postayı kapsar:

| E-posta | Şablon |
| --- | --- |
| E-posta doğrulama | `email-verification.ftl` |
| Parola sıfırlama | `password-reset.ftl` |
| Yöneticinin istediği işlem | `executeActions.ftl` |
| Sihirli bağlantı | `magiclink-email.ftl` |

Sihirli bağlantı, parola yazmadan oturum açtıran e-posta bağlantısıdır. Bu e-postayı `cloudflightio/keycloak-magic-link` eklentisi gönderir. Eklentiyi kimlik-realm işi seçti.

- Her e-postanın HTML ve düz metin sürümü vardır.
- Ortak düzen `email/html/template.ftl` dosyasındadır. Renk ve yazı değerleri bu dosyanın başındadır.
- E-posta dış betik, dış stil, dış yazı tipi ve dış görsel çağırmaz. Stil satır içidir.
- Düğmenin altında bağlantının düz hâli de durur. Düğme çalışmazsa kullanıcı adresi kopyalar.
- Düz adres satırı harf arasından kırılır. Bu açık bir istisnadır. Adres sözcük değildir ve 320 piksele başka yolla sığmaz.
- Keycloak'ın öteki hazır e-postaları yeni düzeni kullanır. Metinleri Keycloak'ın kendi Türkçesidir.

## Hesap konsolu teması

Hesap konsolu Keycloak'ın kendi React uygulamasıdır. Tema bu uygulamayı değiştirmez ve çatallamaz. Tema `keycloak.v3` temasından türer.

Tema yalnız Keycloak'ın desteklediği ayarları kullanır. Bu ayarlar Keycloak 26.8.2 kaynağında doğrulandı. Kaynak `keycloak-account-ui-26.8.2.jar` içindeki `theme/keycloak.v3/account/index.ftl` dosyasıdır.

| Ayar | Ne yapar |
| --- | --- |
| `styles` | `account/resources/css/atonota-account.css` dosyasını yükler. |
| `scripts` | `account/resources/js/atonota-focus.js` dosyasını yükler. Bu betik klavye odak kipini yönetir. |
| `logo` | Başlıktaki marka işaretini verir. |
| `favIcon` | Sayfa simgesini verir. |
| `accountResourceProvider` | Hesap konsolunun sunucu eklentisini seçer. Ayrıntı “Hesap silme bağlantısı” bölümündedir. |
| İleti dosyası | `account/messages/messages_tr.properties` Keycloak'ın 242 iletisini yalın Türkçeyle yazar. İngilizce kaynak Keycloak'ın kendi dosyasıdır. Temanın kendi anahtarları `messages_en.properties` dosyasında da durur. |

- Tokenlar giriş temasıyla aynıdır. İki stil dosyasının başındaki token bölümü birebir aynı olmalıdır. Bir test iki bölümü karşılaştırır. Token değişince iki dosyayı birlikte değiştirin.
- Outfit yazı tipi dosyaları `account/resources/fonts/` klasöründe de durur. Keycloak her tema türüne ayrı kaynak klasörü verir.
- Geçerli sayfa kalın yazı ve yüzey tonuyla gösterilir. Temel temanın renkli kenar çizgisi kapatıldı.

### Hesap silme bağlantısı

Müşteri hesabını Press'teki silme sayfasında siler (proje kaydı O-27, sözleşme 7. bölüm). Hesap konsolu o sayfaya bir bağlantı gösterir.

- Keycloak'ın kendi `delete_account` eylemi kapalıdır. Bu eylem kullanıcıyı ilk adımda siler. Konsol bu eylemi hiç sunmaz.
- Bağlantı “Kişisel bilgiler” sayfasının altında görünür. Metni “Hesap silme sayfasına gidin” olur.
- Bağlantının adresi ayardan gelir: `IDENTITY_ACCOUNT_DELETION_URL` ortam değişkeni.
- Bağlantıyı yalnız müşteri görür. Müşteri, `request-account-deletion` adlı realm rolünü taşıyan kullanıcıdır.
- Çalışan bu rolü taşımaz. Sunucu çalışana giden sayfaya bağlantıyı hiç koymaz.
- Bu rol Keycloak'ın `delete-account` rolü değildir. O rol Keycloak'ın kendi silme eylemine yetki verir. O rolü kimseye vermeyin.

Görünürlük kararını sunucu verir, tarayıcı vermez. Kararı küçük bir Keycloak eklentisi verir. Eklenti `account-provider/` klasöründedir.

| Parça | Görevi |
| --- | --- |
| `account/theme.properties`, `accountResourceProvider` satırı | Eklentiyi seçer. Bu, Keycloak'ın desteklediği tema ayarıdır. |
| `account/theme.properties`, `accountDeletionUrl` satırı | Adresi ortam değişkeninden okur. |
| `account-provider/.../AccountDeletionLinkConsole.java` | Kullanıcının rolüne bakar. Rol varsa bağlantıyı sayfanın sonuna ekler. |
| `account/messages/`, `atAccountDeletionIntro` ve `atAccountDeletionLink` | Bağlantının metinleri |

Eklenti şu durumlarda bağlantıyı eklemez:

- kullanıcı oturum açmamışsa,
- kullanıcının `request-account-deletion` rolü yoksa,
- adres boşsa,
- adres `https` ile başlamıyorsa. Örneğin `javascript:` adresi reddedilir. Düz `http` adresi yalnız `localhost` için kabul edilir.
- adres sunucu adı taşımıyorsa ya da kullanıcı bilgisi taşıyorsa. Örneğin `https://kullanici@site` reddedilir.
- bağlantının iki metninden biri ileti dosyasında yoksa.
- adresin sunucu adında alt çizgi ya da Türkçe harf varsa. Böyle bir adı ASCII biçimiyle yazın.

Müşteri bağlantıyı alamazsa eklenti Keycloak günlüğüne bir uyarı yazar. Uyarı “Account deletion link is not shown” diye başlar. Beklenmedik bir hata hesap konsolunu bozmaz: eklenti hatayı günlüğe yazar ve sayfayı bağlantısız gönderir.

Adres ve kaçış kurallarını küçük bir Java denetimi ölçer: `account-provider/src/test/java/.../AccountDeletionLinkConsoleCheck.java`. Denetim imaj derlenirken çalışır. Denetim başarısız olursa imaj derlenmez.

Bağlantı bir yetki denetimi değildir. Proje kaydına göre silme sayfası kullanıcıyı yeniden doğrular (O-27). Bu davranış Press'e aittir ve burada sınanmadı.

Rol bir gruptan ya da bileşik bir rolden de gelebilir. Çalışanı bu rolü taşıyan bir gruba eklemeyin. Yoksa çalışan da bağlantıyı görür.

Eklentiyi Keycloak'a kurmak için kimlik-realm işi şunları yapmalıdır:

1. Eklentiyi `account-provider/build.sh` betiğiyle derleyin. Betik yalnız JDK 21 ister. Betik Java denetimini de çalıştırır. Derleme adımını başka bir dosyaya kopyalamayın. Örnek kullanım `test/Dockerfile` dosyasındadır.
2. Çıkan `account-deletion-link-provider.jar` dosyasını `/opt/keycloak/providers/` klasörüne koyun.
   Keycloak `start --optimized` ile çalışıyorsa jar eklendikten sonra `kc.sh build` komutunu çalıştırın. Yoksa eklenti kaydolmaz.
3. Keycloak container'ına `IDENTITY_ACCOUNT_DELETION_URL` değişkenini verin.
4. Realm'de `request-account-deletion` adlı bir realm rolü açın. Rolü müşterilere verin, çalışanlara vermeyin.
5. `delete_account` gerekli işlemini kapalı tutun. `delete-account` rolünü kimseye vermeyin.
6. Kurulumdan sonra deneyin: müşteri hesabıyla girin ve bağlantıyı görün. Çalışan hesabıyla girin ve bağlantının olmadığını görün.
7. Hesap konsolu 404 veriyorsa eklenti kurulu değildir. Bu durumu sınayan otomatik test yoktur, elle deneyin.

Eklenti kurulu değilse hesap konsolu 404 yanıtı verir. Bu, bilerek seçilmiş güvenli davranıştır: tema eklentisiz çalışırsa görünürlük kuralı sessizce kaybolurdu.

Eklenti Keycloak'ın iç sınıflarını genişletir. Keycloak başlarken bunu bir uyarıyla bildirir. Keycloak sürümü değişince eklentiyi yeniden derleyin ve testleri çalıştırın. Karar notu `backend/docs/kararlar/` klasöründedir.

Hesap konsolunun bilinen sınırları şunlardır:

- Keycloak bazı “daha fazla” düğmelerine erişilebilir ad vermez. Tema betiği bu düğmelere ileti dosyasından ad verir. Betik çalışmazsa düğmeler adsız kalır.
- Yükleme yazısı İngilizcedir. Bu metin Keycloak'ın şablonunda sabit durur.
- Sayfa başlığı marka adıdır. Başlık bütün dillerde aynıdır.
- Yazarak aranan seçim alanının odak çizgisi için kural yazıldı ama sınanmadı. Deneme realm'inde böyle bir alan yok.
- Etiketsiz onay kutusunun odak göstergesi yok. Konsolun böyle bir kutu kullandığı doğrulanmadı.
- Betik çalışmazsa başlıkta marka adı görünmez, yalnız marka işareti durur.
- Seyrek koşularda tarayıcı Keycloak'ın bir yazı tipi dosyasını aynı sunucudan istedi. Nedeni doğrulanmadı. Test bu dosyaya adıyla izin verir, başka yazı tipi isteğini reddeder. Ekrandaki metin Outfit ile çizilir.
- Bağlı hesaplar, gruplar ve kuruluşlar sayfaları testle sınanmadı. Deneme realm'inde bu özellikler kapalıdır.

## Temel temadan kopyalanan şablonlar

Tema, Keycloak 26.8.2 kaynağındaki on bir şablonun değiştirilmiş kopyasını kullanır. Keycloak sürümü değişince bu dosyaları yeni temel şablonla karşılaştırın.

| Dosya | Fark |
| --- | --- |
| `login/template.ftl` | Dört fark vardır: sayfa simgesi, marka başlığı, dil bağlantıları ve girişi başlatan adresin gösterimi. Farklar dosyada `ATONOTA` notuyla işaretlidir. |
| `login/login-config-totp.ftl` | İki etiketin `for` değeri kendi giriş alanını gösterir. Temel şablonda bu değer yanlıştır. |
| `login/select-authenticator.ftl` | Her giriş yolu gerçek bir düğmedir. Temel şablondaki satır Enter ve Space tuşuyla çalışmaz. |
| `login/login-verify-email.ftl` | Yeniden gönderme bağlantısı tam bir cümledir. Temel şablon cümleyi parçalardan birleştirir. |
| `login/webauthn-register.ftl` | Formun üstünde geçiş anahtarını anlatan bir açıklama vardır. |
| `login/login-page-expired.ftl` | İki bağlantı tam birer cümledir. |
| `login/login-recovery-authn-code-config.ftl` | Uyarı çevrilir. Başlık sırası düzeltilir. Dosya ve çıktı tarihi ekranın dilini kullanır. |
| `login/logout-confirm.ftl` | Onay düğmesi doğal Tab sırasını izler. |
| `login/login.ftl` | E-posta yalnız yazı olarak görünüyorsa form gizli bir kullanıcı adı alanı taşır. |
| `login/login-password.ftl` | Form gizli bir kullanıcı adı alanı taşır. |
| `login/login-update-password.ftl` | Form gizli bir kullanıcı adı alanı taşır. Tarayıcı yeni parolayı doğru hesaba kaydeder. |

### Parola formları ve parola yöneticisi

Parola yöneticisi kaydı bir hesaba bağlar. Bunun için formda `autocomplete="username"` taşıyan bir alan gerekir. Keycloak bazı ekranlarda e-postayı yalnız yazı olarak gösterir. O ekranlarda böyle bir alan yoktu. Tarayıcı yeni parolayı kaydetmeyi önermiyordu ya da yanlış hesabı seçiyordu (AJA-648).

Ortak alan `login/account-field.ftl` dosyasındadır. Alanın özellikleri şunlardır:

- Alan gizlidir. Klavye ve ekran okuyucu alana ulaşmaz.
- Alanın `name` değeri yoktur. Sunucu bu alanı hiç almaz.
- Alanın türü `text` olur. Parola yöneticileri `hidden` türündeki alanı okumaz.
- Değer Keycloak'ın verdiği kullanıcı adıdır. Bu realm'de kullanıcı adı e-postadır.

Parola değiştirme yolları ve şablonları şunlardır:

| Yol | Ekran | Şablon |
| --- | --- | --- |
| Hesap konsolundan parola değiştirme | “Yeni parola belirleyin” | `login-update-password.ftl` |
| “Parolanızı mı unuttunuz?” bağlantısı ve e-postadaki bağlantı | “Yeni parola belirleyin” | `login-update-password.ftl` |
| Yöneticinin zorunlu kıldığı parola değişikliği | “Yeni parola belirleyin” | `login-update-password.ftl` |
| Yöneticinin e-postayla gönderdiği işlem | “Yeni parola belirleyin” | `login-update-password.ftl` |

Giriş ekranlarında parola alanı `current-password` taşır. Yeni parola alanları `new-password` taşır. `tests/password-autocomplete.spec.ts` bu öznitelikleri ölçer. Gerçek bir parola yöneticisinin kayıt önerisini bu test göremez. Bu denetimi kişi elle yapar.

## Deneme ortamı

Komutları deponun kökünden çalıştırın. Container ortamı Colima'dır ve bağlam `colima-factory` olur.

1. İmaj yoksa önce derleyin: `backend/identity/keycloak/themes/atonota/test/bin/theme-dev.sh build`
   `colima-factory` diski dardır. İmaj varsa yeniden derlemeyin. Tema değişince `sync` komutunu kullanın.
2. Ortamı açın: `backend/identity/keycloak/themes/atonota/test/bin/theme-dev.sh up`
3. Portları bu bilgisayara taşıyın: `backend/identity/keycloak/themes/atonota/test/bin/theme-dev.sh tunnel`
4. Tema dosyası değişince dosyaları kopyalayın: `backend/identity/keycloak/themes/atonota/test/bin/theme-dev.sh sync`
   Yalnız bir bölümü kopyalamak için `sync login`, `sync email` ya da `sync account` yazın.
5. İş bitince ortamı kapatın: `backend/identity/keycloak/themes/atonota/test/bin/theme-dev.sh down`

Ortamı `colima` profilinde açmak için komutun önüne `FS_COLIMA_PROFILE=default` yazın. Önce `colima ssh -- free -g` ile en az 2 GB boş bellek ölçün.

Betik ilk çalışmada `test/.env` dosyasını üretir. Bu dosya Git'e girmez. Port tabanı `PANE_PORT` değişkeninden gelir. Keycloak taban portu, Mailpit ekranı bir sonraki portu kullanır. Mailpit, gönderilen e-postaları yakalayan deneme posta kutusudur.

Depoda sabit deneme parolası ve TOTP gizli değeri yoktur. Betik `up` komutunda iki rastgele değer üretir ve `test/.env` dosyasına yazar. Değer üretilemezse betik hata koduyla durur ve var olan dosyaya dokunmaz. Değişkenlerin adı `IDENTITY_TEST_PASSWORD` ve `IDENTITY_TEST_TOTP_SECRET` olur. Değer yoksa testler açık bir hatayla durur.

Deneme realm'inin adı `theme-test` olur. Tema yalnız bu realm'de seçilidir.

## Testler

Testler Playwright ile yazıldı. Tarayıcılar Chromium ve WebKit'tir. Firefox testi yoktur.

```bash
cd backend/identity/keycloak/themes/atonota/test
npx playwright test
```

| Dosya | Sınadığı şey |
| --- | --- |
| `tests/layout.spec.ts` | Yatay taşma, yazı boyutu, yazı tipi, dış istek, dokunma alanı ve büyük kök yazı |
| `tests/focus.spec.ts` | Tab sırası, klavye odak kipi, odak çizgisinin biçimi ve zorlanmış renkler |
| `tests/flow.spec.ts` | Kayıt, giriş, parola sıfırlama, doğrulama kodu ve geçiş anahtarı |
| `tests/flow.spec.ts` | Kurtarma kodu kurulumu, oturum kapatma ve giriş yöntemi silme |
| `tests/screens-text.spec.ts` | Yedi ekranda Türkçe metin, düğme adları ve bağlantı adları |
| `tests/locale.spec.ts` | Türkçe varsayılan dil, dil bağlantıları ve ileti anahtarları |
| `tests/motion.spec.ts` | Hareket eğrisi, süre, azaltılmış hareket ve stil kaynağı denetimi |
| `tests/accessibility.spec.ts` | axe denetimi, açık ve koyu tema |
| `tests/email.spec.ts` | E-posta şablonları ve Mailpit |
| `tests/account.spec.ts` | Hesap konsolu: yerleşim, odak, hareket, axe, Türkçe iletiler ve token eşliği |
| `tests/focus-diff.ts` | Odak çizgisini ölçen ortak yardımcı |
| `tests/delete-account.spec.ts` | Hesap silme bağlantısı: müşteri görür, çalışan görmez, adres ayardan gelir |
| `tests/session-states.spec.ts` | Misafir, oturumlu kullanıcı ve sunucuda biten oturum: giriş, hesap konsolu ve silme bağlantısı doğru davranır |
| `tests/dev-script.spec.ts` | Deneme betiği rastgele değerleri güvenle yazar. Üretim başarısızsa dolu ayar dosyası değişmez. |
| `tests/realm-settings.spec.ts` | Keycloak'ın silme eylemi yanlışlıkla açılsa da konsol onu sunmaz. Test bu yanlış ayarı ayrı bir realm'de kurar. Adı `theme-test-delete-action-on` olur. Asıl deneme realm'inin ayarını hiçbir test değiştirmez. |
| `tests/security.spec.ts` | Güvenlik başlıkları, XSS denemeleri, tarayıcı deposu ve kaynak denetimi |
| `tests/brand.spec.ts` | Marka adı değişkenden gelir: giriş, e-posta, hesap konsolu ve kaynak denetimi |
| `tests/password-autocomplete.spec.ts` | Parola formlarında kullanıcı adı alanı ve `autocomplete` değerleri |
| `tests/visual.spec.ts` | Bağımsız inceleme için ekran görüntüsü üretimi |

Yerleşim testleri yedi görünümde koşar: 320, 360, 375, 390, yatay telefon, tablet ve masaüstü. Öteki testler 320 ve masaüstü görünümünde koşar.

Ekran görüntülerini şu komut üretir:

```bash
VISUAL=1 npx playwright test visual --project=chromium-320 --project=webkit-desktop
```

Hesap konsolu görüntülerini şu komut üretir:

```bash
VISUAL=1 npx playwright test account -g screenshot --project=chromium-320 --project=webkit-desktop
```

Tür denetimi için `test/tsconfig.json` dosyası vardır. Depoda TypeScript paketi kurulu değildir. Bu bilgisayarda kurulu bir `tsc` ile şu komut çalışır:

```bash
tsc -p backend/identity/keycloak/themes/atonota/test/tsconfig.json
```

Görüntüler `test/reference/` klasörüne yazılır. Bu görüntüler macOS'ta üretildi. Görüntüler otomatik karşılaştırma kapısı değildir. Görüntüyü üreten kişi kendi görüntüsünü onaylamaz.

## Bilinen sınırlar

- İletiler kullanıcı adının e-posta adresi olduğunu varsayar. Realm bu ayarı kapatırsa iletileri güncelleyin.
- Tema, kendi çevirisi yoksa Keycloak’ın Türkçe metnini kullanır. Hesap bağlama ve kullanım koşulu ekranları bu metni kullanır.
- Kayıt formuna seçmeli alan eklenirse Keycloak işletim sisteminin açılır listesini çizer. Bu liste markalı değildir. Realm'e seçmeli profil alanı eklemeyin.
- Geçiş anahtarının tarihini ve bağlantı türünü Keycloak yazar. Örneğin “USB” yazısı Keycloak'tan gelir.
- Tema deneme imajı e-posta bağlantısı eklentisini içermez. Giriş seçeneğini eklentili Keycloak imajında sınayın.
- E-posta testi, eklenti arşivindeki şablon adlarını ve konu anahtarını temayla karşılaştırır.
- Test giriş iletilerini de iki dilde denetler. İleti anahtarları `magiclink-display-name`, `magiclink-help-text` ve `magiclink-emailSentText` değerleridir. Test boş e-posta hatasının `Email cannot be empty` anahtarını da arar.
- Eklenti kaynağı `cloudflightio/keycloak-magic-link` deposundaki `7b4ee949a39a7ee953987162479ae1da2c57c3cb` kaydıdır. [Keycloak Dockerfile](../../Dockerfile) eklentiyi Keycloak 26.8.2 için derler.
- `MAGIC_LINK_PROVIDER_JAR` için ürün imajındaki `/opt/keycloak/providers/keycloak-magic-link-7b4ee94.jar` dosyasını kullanın. `docker cp` ile arşivi kendi deneme klasörünüze alın.
- Eklentili Keycloak adresini `MAGIC_LINK_KC_URL` ile verin. Deneme hesabı açmak için `MAGIC_LINK_ADMIN_TOKEN` gerekir. Canlı test bağlantıyı giriş ekranından ister.
- E-postalar gerçek e-posta programlarında denenmedi. Örneğin Gmail ve Outlook denenmedi.

- Gerçek telefon ve gerçek Safari denemesi yapılmadı. WebKit öykünmesi gerçek Safari değildir.
- Passkey akışının tamamı yalnız Chromium'da sınandı. WebKit'te sanal anahtar yoktur.
- Keycloak passkey adını tarayıcının soru penceresiyle sorar. Bu pencere temayla giydirilemez.
- axe otomatik kuralları kapsar. Bu sonuç tam WCAG 2.2 AA uyumu iddiası değildir.
