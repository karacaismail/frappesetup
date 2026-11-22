# Atonota Keycloak teması

Bu klasör Keycloak'ın giriş ve e-posta ekranlarını Atonota markasıyla giydirir. Tema Keycloak'ın kendi tema yapısıyla kurulur (proje kaydı O-4). Keycloakify kullanılmaz.

Hedef sürüm Keycloak 26.8.2 sürümüdür. Giriş teması `keycloak.v2` temasından türer.

## Klasörler

| Klasör | İçerik |
| --- | --- |
| `login/` | Giriş teması. Giriş, kayıt, parola sıfırlama, TOTP ve passkey ekranlarını kapsar. |
| `email/` | E-posta teması. |
| `account/` | Hesap konsolu teması. Kullanıcı parolasını, ikinci doğrulamasını ve oturumlarını bu ekranda yönetir. |
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
| Sihirli bağlantı | `skycloak-magic-link-email.ftl` |

Sihirli bağlantı, parola yazmadan oturum açtıran e-posta bağlantısıdır. Bu e-postayı `sky-cloak/keycloak-magic-link` eklentisi gönderir. Eklentiyi kimlik-realm işi seçti.

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
| İleti dosyası | `account/messages/messages_tr.properties` 242 iletiyi yalın Türkçeyle yazar. İngilizce kaynak Keycloak'ın kendi dosyasıdır. |

- Tokenlar giriş temasıyla aynıdır. İki stil dosyasının başındaki token bölümü birebir aynı olmalıdır. Bir test iki bölümü karşılaştırır. Token değişince iki dosyayı birlikte değiştirin.
- Outfit yazı tipi dosyaları `account/resources/fonts/` klasöründe de durur. Keycloak her tema türüne ayrı kaynak klasörü verir.
- Geçerli sayfa kalın yazı ve yüzey tonuyla gösterilir. Temel temanın renkli kenar çizgisi kapatıldı.

### Hesap silme

Kullanıcı hesabını hesap konsolundan silebilir (proje kaydı O-27).

1. Kullanıcı “Kişisel bilgiler” sayfasında “Hesabı silin” bölümünü açar.
2. Kullanıcı “Silin” düğmesine basar.
3. Keycloak onay ekranını açar. Bu ekran giriş temasına aittir.
4. Kullanıcı “Silmeyi onaylayın” düğmesine basar. Keycloak hesabı siler.

Bölümün görünmesi için realm'de iki ayar gerekir. Bu ayarlar kimlik-realm işindedir:

- `delete_account` adlı gerekli işlem açık olmalıdır.
- Müşteri, `account` istemcisinin `delete-account` rolünü taşımalıdır.

Konsol bölümü rolü olmayan kullanıcıya da gösterir. Keycloak o kullanıcının isteğini reddeder ve “Bu hesabı silme izniniz yok.” der. Bu yüzden rolü her müşteriye verin.

Uyarı metni O-27 kararını anlatır: hesap silinir, iş kayıtları kalır ve kayıtlardan ad silinir. Keycloak'ın hazır metni “bütün veriler silinir” der. Bu metin İngilizcede de değiştirildi (`account/messages/messages_en.properties`).

Hesap konsolunun bilinen sınırları şunlardır:

- Hesap silme uyarısının başlığı `h4` öğesidir ve `h1` başlığından hemen sonra gelir. Tema bu sırayı değiştiremez. axe testi bu bölümde `heading-order` kuralını muaf tutar.
- Keycloak bazı “daha fazla” düğmelerine erişilebilir ad vermez. Tema uygulamanın HTML'ini değiştiremez. axe testi bu düğmeleri bilerek dışarıda bırakır.
- Yükleme yazısı İngilizcedir. Bu metin Keycloak'ın şablonunda sabit durur.
- Sayfa başlığı marka adıdır. Başlık bütün dillerde aynıdır.
- Yazarak aranan seçim alanının odak çizgisi için kural yazıldı ama sınanmadı. Deneme realm'inde böyle bir alan yok.
- Etiketsiz onay kutusunun odak göstergesi yok. Konsolun böyle bir kutu kullandığı doğrulanmadı.
- Betik çalışmazsa başlıkta marka adı görünmez, yalnız marka işareti durur.
- Seyrek koşularda tarayıcı Keycloak'ın bir yazı tipi dosyasını aynı sunucudan istedi. Nedeni doğrulanmadı. Test bu dosyaya adıyla izin verir, başka yazı tipi isteğini reddeder. Ekrandaki metin Outfit ile çizilir.
- Bağlı hesaplar, gruplar ve kuruluşlar sayfaları testle sınanmadı. Deneme realm'inde bu özellikler kapalıdır.

## Temel temadan kopyalanan şablonlar

Altı şablon Keycloak 26.8.2 kaynağından kopyalandı ve değiştirildi. Keycloak sürümü değişince bu dosyaları yeni temel şablonla karşılaştırın.

| Dosya | Fark |
| --- | --- |
| `login/template.ftl` | Dört fark vardır: sayfa simgesi, marka başlığı, dil bağlantıları ve girişi başlatan adresin gösterimi. Farklar dosyada `ATONOTA` notuyla işaretlidir. |
| `login/login-config-totp.ftl` | İki etiketin `for` değeri kendi giriş alanını gösterir. Temel şablonda bu değer yanlıştır. |
| `login/select-authenticator.ftl` | Her giriş yolu gerçek bir düğmedir. Temel şablondaki satır Enter ve Space tuşuyla çalışmaz. |
| `login/login-verify-email.ftl` | Yeniden gönderme bağlantısı tam bir cümledir. Temel şablon cümleyi parçalardan birleştirir. |
| `login/webauthn-register.ftl` | Formun üstünde geçiş anahtarını anlatan bir açıklama vardır. |
| `login/login-page-expired.ftl` | İki bağlantı tam birer cümledir. Bu ekran testle sınanmadı. |

## Deneme ortamı

Komutları deponun kökünden çalıştırın. Container ortamı Colima'dır ve bağlam `colima-factory` olur.

1. İmaj yoksa önce derleyin: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh build`
   `colima-factory` diski dardır. İmaj varsa yeniden derlemeyin. Tema değişince `sync` komutunu kullanın.
2. Ortamı açın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh up`
3. Portları bu bilgisayara taşıyın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh tunel`
4. Tema dosyası değişince dosyaları kopyalayın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh sync`
   Yalnız bir bölümü kopyalamak için `sync login`, `sync email` ya da `sync account` yazın.
5. İş bitince ortamı kapatın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh down`

Ortamı `colima` profilinde açmak için komutun önüne `FS_COLIMA_PROFILE=default` yazın. Önce `colima ssh -- free -g` ile en az 2 GB boş bellek ölçün.

Betik ilk çalışmada `test/.env` dosyasını üretir. Bu dosya Git'e girmez. Port tabanı `PANE_PORT` değişkeninden gelir. Keycloak taban portu, Mailpit ekranı bir sonraki portu kullanır. Mailpit, gönderilen e-postaları yakalayan deneme posta kutusudur.

Deneme realm'inin adı `tema-deneme` olur. Tema yalnız bu realm'de seçilidir.

## Testler

Testler Playwright ile yazıldı. Tarayıcılar Chromium ve WebKit'tir. Firefox testi yoktur.

```bash
cd backend/identity/keycloak/themes/atonota/test
npx playwright test
```

| Dosya | Sınadığı şey |
| --- | --- |
| `tests/yerlesim.spec.ts` | Yatay taşma, yazı boyutu, yazı tipi, dış istek, dokunma alanı ve büyük kök yazı |
| `tests/odak.spec.ts` | Tab sırası, klavye odak kipi, odak çizgisinin biçimi ve zorlanmış renkler |
| `tests/akis.spec.ts` | Kayıt, giriş, parola sıfırlama, TOTP ve passkey akışları |
| `tests/dil.spec.ts` | Türkçe varsayılan dil, dil bağlantıları ve ileti anahtarları |
| `tests/hareket.spec.ts` | Hareket eğrisi, süre, azaltılmış hareket ve stil kaynağı denetimi |
| `tests/erisilebilirlik.spec.ts` | axe denetimi, açık ve koyu tema |
| `tests/eposta.spec.ts` | E-posta şablonları ve Mailpit |
| `tests/account.spec.ts` | Hesap konsolu: yerleşim, odak, hareket, axe, Türkçe iletiler ve token eşliği |
| `tests/focus-diff.ts` | Odak çizgisini ölçen ortak yardımcı |
| `tests/delete-account.spec.ts` | Hesap silme bölümü, onay ekranı ve silme akışı |
| `tests/brand.spec.ts` | Marka adı değişkenden gelir: giriş, e-posta, hesap konsolu ve kaynak denetimi |
| `tests/gorsel.spec.ts` | Bağımsız inceleme için ekran görüntüsü üretimi |

Yerleşim testleri yedi görünümde koşar: 320, 360, 375, 390, yatay telefon, tablet ve masaüstü. Öteki testler 320 ve masaüstü görünümünde koşar.

Ekran görüntülerini şu komut üretir:

```bash
GORSEL=1 npx playwright test gorsel --project=chromium-320 --project=webkit-masaustu
```

Hesap konsolu görüntülerini şu komut üretir:

```bash
VISUAL=1 npx playwright test account -g screenshot --project=chromium-320 --project=webkit-masaustu
```

Görüntüler `test/referans/` klasörüne yazılır. Bu görüntüler macOS'ta üretildi. Görüntüler otomatik karşılaştırma kapısı değildir. Görüntüyü üreten kişi kendi görüntüsünü onaylamaz.

## Bilinen sınırlar

- İletiler kullanıcı adının e-posta adresi olduğunu varsayar. Realm bu ayarı kapatırsa iletileri güncelleyin.
- Tema 203 iletiyi yalın Türkçeyle yazar. Öteki iletiler Keycloak'ın kendi Türkçe dosyasından gelir. Örneğin kurtarma kodu, hesap bağlama ve kullanım koşulu ekranları böyledir.
- Kayıt formuna seçmeli alan eklenirse Keycloak işletim sisteminin açılır listesini çizer. Bu liste markalı değildir. Realm'e seçmeli profil alanı eklemeyin.
- Geçiş anahtarının tarihini ve bağlantı türünü Keycloak yazar. Örneğin “USB” yazısı Keycloak'tan gelir.
- Sihirli bağlantı eklentisinin giriş ekranı iletileri çevrildi ama canlı denenmedi. Deneme ortamında eklenti kurulu değildir.
- Sihirli bağlantı e-postası canlı denenmedi. Şablonun adı ve değişkenleri eklentinin jar dosyasından okundu. Eklentili bir Keycloak'ta `SIHIRLI_KC_URL` ve `SIHIRLI_ADMIN_TOKEN` değişkenleriyle `tests/eposta.spec.ts` testini çalıştırın.
- E-postalar gerçek e-posta programlarında denenmedi. Örneğin Gmail ve Outlook denenmedi.

- Gerçek telefon ve gerçek Safari denemesi yapılmadı. WebKit öykünmesi gerçek Safari değildir.
- Passkey akışının tamamı yalnız Chromium'da sınandı. WebKit'te sanal anahtar yoktur.
- Keycloak passkey adını tarayıcının soru penceresiyle sorar. Bu pencere temayla giydirilemez.
- axe otomatik kuralları kapsar. Bu sonuç tam WCAG 2.2 AA uyumu iddiası değildir.
