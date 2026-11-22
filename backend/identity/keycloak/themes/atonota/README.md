# Atonota Keycloak teması

Bu klasör Keycloak'ın giriş ve e-posta ekranlarını Atonota markasıyla giydirir. Tema Keycloak'ın kendi tema yapısıyla kurulur (proje kaydı O-4). Keycloakify kullanılmaz.

Hedef sürüm Keycloak 26.8.2 sürümüdür. Giriş teması `keycloak.v2` temasından türer.

## Klasörler

| Klasör | İçerik |
| --- | --- |
| `login/` | Giriş teması. Giriş, kayıt, parola sıfırlama, TOTP ve passkey ekranlarını kapsar. |
| `email/` | E-posta teması. |
| `test/` | Deneme ortamı ve Playwright testleri. Bu klasör Keycloak imajına girmez. |

TOTP, telefondaki doğrulama uygulamasının ürettiği tek kullanımlık koddur. Passkey, parola yerine kullanılan geçiş anahtarıdır.

## Temayı Keycloak'a koyma

1. `login/` ve `email/` klasörlerini imaja kopyalayın. Hedef yol `/opt/keycloak/themes/atonota/` olur.
2. Realm'de giriş temasını `atonota` yapın.
3. Realm'de e-posta temasını `atonota` yapın.
4. Realm'in görünen adını yazın. Tema marka adını bu ayardan okur.

Realm dosyası kimlik-realm işinindir. Bu klasör realm dosyasını değiştirmez.

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

## Temel temadan kopyalanan şablonlar

Beş şablon Keycloak 26.8.2 kaynağından kopyalandı ve değiştirildi. Keycloak sürümü değişince bu dosyaları yeni temel şablonla karşılaştırın.

| Dosya | Fark |
| --- | --- |
| `login/template.ftl` | Dört fark vardır: sayfa simgesi, marka başlığı, dil bağlantıları ve girişi başlatan adresin gösterimi. Farklar dosyada `ATONOTA` notuyla işaretlidir. |
| `login/login-config-totp.ftl` | İki etiketin `for` değeri kendi giriş alanını gösterir. Temel şablonda bu değer yanlıştır. |
| `login/select-authenticator.ftl` | Her giriş yolu gerçek bir düğmedir. Temel şablondaki satır Enter ve Space tuşuyla çalışmaz. |
| `login/login-verify-email.ftl` | Yeniden gönderme bağlantısı tam bir cümledir. Temel şablon cümleyi parçalardan birleştirir. |
| `login/login-page-expired.ftl` | İki bağlantı tam birer cümledir. Bu ekran testle sınanmadı. |

## Deneme ortamı

Komutları deponun kökünden çalıştırın. Container ortamı Colima'dır ve bağlam `colima-factory` olur.

1. Ortamı açın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh up`
2. Portları bu bilgisayara taşıyın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh tunel`
3. Tema dosyası değişince dosyaları kopyalayın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh sync`
4. İş bitince ortamı kapatın: `backend/identity/keycloak/themes/atonota/test/bin/tema-dev.sh down`

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
| `tests/gorsel.spec.ts` | Bağımsız inceleme için ekran görüntüsü üretimi |

Yerleşim testleri yedi görünümde koşar: 320, 360, 375, 390, yatay telefon, tablet ve masaüstü. Öteki testler 320 ve masaüstü görünümünde koşar.

Ekran görüntülerini şu komut üretir:

```bash
GORSEL=1 npx playwright test gorsel --project=chromium-320 --project=webkit-masaustu
```

Görüntüler `test/referans/` klasörüne yazılır. Bu görüntüler macOS'ta üretildi. Görüntüler otomatik karşılaştırma kapısı değildir. Görüntüyü üreten kişi kendi görüntüsünü onaylamaz.

## Bilinen sınırlar

- İletiler kullanıcı adının e-posta adresi olduğunu varsayar. Realm bu ayarı kapatırsa iletileri güncelleyin.
- Tema 195 iletiyi yalın Türkçeyle yazar. Öteki iletiler Keycloak'ın kendi Türkçe dosyasından gelir. Örneğin kurtarma kodu, hesap bağlama ve kullanım koşulu ekranları böyledir.
- Kayıt formuna seçmeli alan eklenirse Keycloak işletim sisteminin açılır listesini çizer. Bu liste markalı değildir. Realm'e seçmeli profil alanı eklemeyin.
- Geçiş anahtarı ekleme ekranında açıklama metni yoktur. Geçiş anahtarının tarihini ve bağlantı türünü Keycloak yazar.
- Sihirli bağlantı eklentisinin giriş ekranı iletileri çevrilmedi. Deneme ortamında eklenti kurulu değildir.

- Gerçek telefon ve gerçek Safari denemesi yapılmadı. WebKit öykünmesi gerçek Safari değildir.
- Passkey akışının tamamı yalnız Chromium'da sınandı. WebKit'te sanal anahtar yoktur.
- Keycloak passkey adını tarayıcının soru penceresiyle sorar. Bu pencere temayla giydirilemez.
- axe otomatik kuralları kapsar. Bu sonuç tam WCAG 2.2 AA uyumu iddiası değildir.
