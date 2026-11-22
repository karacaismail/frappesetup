# İş: kimlik-tema

Bu iş Keycloak'ın giriş ve e-posta ekranlarını Atonota markasıyla yeniden giydirir. Kullanıcı bu ekranları “Atonota ile oturum aç” düğmesinden sonra görür.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJECT-RECORD.md`, özellikle O-1 ve O-4
3. `backend/docs/contracts.md`, 1 ve 2. bölümler
4. `docs/standartlar/headless-frontend-standartlari.md` içindeki güvenlik ve erişilebilirlik kuralları
5. Ortak arayüz rehberleri: `~/.claude/skills/coding-standards/references/adaptive-ui.md`, `adaptive-qa.md`, `ui-motion.md` ve `ai-first-ui.md`

## Sahip olduğunuz yer

- `backend/identity/keycloak/themes/atonota/`

## Kararlar

- Tema Keycloak'ın kendi tema yapısıyla kurulur. Tema `keycloak.v2` temasından türer (O-4). Keycloakify kullanılmaz.
- Görsel kimliği markanın amacından türetin. Atonota bir kimlik ve güven markasıdır. Hazır temayı ya da başka projenin görünüşünü kopyalamayın.
- Renk, yazı, boşluk ve köşe değerlerini merkezi CSS değişkenlerinde tutun.

## Proje sahibinin kalıcı arayüz kuralları

- Yazı tipi Outfit'tir. Yazı tipini kendi sunucunuzdan verin. Dış yazı tipi isteği yapmayın.
- Okunabilir her metin en az 14 CSS pikseldir.
- Tasarım 320 CSS piksel genişlikte başlar.
- Çevreleyen odak halkası yasaktır. Klavye odağı çevrelemeyen tek bir göstergeyle görünür.
- Köşesi yuvarlak kutuya renkli kenar çizgisi koymayın.
- Hareket eğrisi `cubic-bezier(.65, 0, .35, 1)` olur. Azaltılmış hareket tercihine uyun.
- WCAG 2.2 AA düzeyini hedefleyin.

## Kontrol noktası 1: giriş teması

1. Giriş, kayıt, parola sıfırlama, TOTP ve passkey ekranlarını kapsayın.
2. Türkçe ve İngilizce metinleri yazın. Türkçe varsayılan olsun. Metni yalın Türkçeyle yazın.
3. Realm'de giriş temasını `atonota` yapma isteğini raporda orkestratöre iletin. Realm dosyası kimlik-realm işinindir.
4. Playwright ile testleri yazın. Chromium ve WebKit kullanın. Firefox kullanmayın.
   - Genişlikler 320, 360, 375, 390, tablet ve masaüstü olsun.
   - Tab ve Shift+Tab ile odak sırasını sınayın.
   - Metin boyutunu ve yatay taşmayı ölçün.
5. Görsel referans görüntülerini üretin. Görüntüleri bağımsız bir incelemeye verin. Kendi görüntünüzü kendiniz onaylamayın.
6. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: e-posta teması

1. Doğrulama, parola sıfırlama ve sihirli bağlantı e-postalarını kapsayın.
2. E-postada dış betik ve dış stil kullanmayın.
3. E-postayı Mailpit kutusunda sınayın.
4. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Panel arayüzü bu turda yazılmaz.
- Gerçek telefon ve gerçek Safari denemesi yapılamaz. Bunu raporda `not_run` olarak yazın.
