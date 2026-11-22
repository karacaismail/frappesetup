# Eksik işler listesi

Bu liste 22 Kasım 2026 Pazar günü yazıldı. Kaynak, proje sahibinin kural dosyalarıyla yapılan karşılaştırmadır (D-15). Karşılaştırmayı yedi bağımsız inceleme yaptı. Ayrıca ad betiği ve mobil dal ayrıca incelendi.

Kurallar şunlardır:

- Her işçi kendi bölümündeki maddeleri yapar.
- Davranış değişiyorsa önce test yazılır.
- Biten madde durum dosyasına kanıtıyla yazılır. Kanıt bir test adı ya da komut çıktısıdır.
- Kural kimlikleri `docs/standartlar/` klasöründeki dosyalardandır. O kimlikleri proje kaydındaki kararlardır.

## kimlik-realm

1. Olay dinleyici eklentisinde 1. seçenek seçildi. `sashyo/keycloak-webhook-listener` çatallanır. Lisans dosyası ve kaynak notu korunur. İmza sözleşmenin 7. bölümüne uyar: zaman damgası, kip ve `<zaman>.<kip>.<gövde>` biçimi. Gövde `realmId` taşır. Eski zaman damgalı istek reddedilir.
2. Telefon paketi için açık (public) bir istemci kurun. İstemci PKCE S256 ister ve gizli anahtar taşımaz.
3. `press` istemcisi de PKCE S256 istesin.
4. SMTP ayarlarının hepsi ortam değişkeninden gelsin. Üretimde şifreli bağlantı ve kimlik doğrulama açık olsun.
5. Üretimde `sslRequired` değeri `all` olsun. Geliştirmede `external` kalabilir.
6. Karar 19 sürelerini kurun (O-25). Çalışan 1 saat boşta kalınca yeniden kimlik doğrulasın. Açık Keycloak çerezi bu adımı atlatmasın. Bunu canlı testle gösterin.
7. Eski yenileme belirtecinin reddedildiğini canlı testle gösterin.
8. Passkey kayıt adımı zorunlu adımlar listesinde açık olsun. Kapalı sağlayıcılar giriş ekranında görünmesin.
9. `oidc_verify` anahtar indirirken yönlendirme izlemesin ve yalnız HTTPS kullansın (G-13). Geliştirme adresi açık bir istisna olur.
10. Görünen marka adı bir değişkenden gelsin (D-4).
11. Müşteri için Keycloak'ın hesap silme adımını açın (O-27). Çalışan kendi hesabını açamaz.

## platform-core-kimlik

1. Telefon belirteci için `auth_hooks` kancası.
2. Frappe'nin `/login` sayfası Atonota girişine gitsin. Giriş başlatan GET ucu sözleşmeye yazılsın.
3. Frappe oturum süresi 1 saat boşta kalma olsun (O-25).
4. Kimlik bağı DocType'ı `ai_write_closed_doctypes` kancasına girsin (O-28).
5. Sözleşmedeki insan uçlarına 401 yanıtı eklensin (SZ-8).
6. `oidc_verify` bağımlılığı `pyproject.toml` dosyasında yazılsın.

## identity-sync

1. Olay alıcısı kimlik-realm'in çatal eklentisiyle canlı denensin. Bozuk imza ve eski zaman damgası reddedilsin.
2. `POST /v1/sessions/revoke` ucunu yazın (sözleşme 7. bölüm).
3. Hesap silme akışını yazın (`POST /v1/account-deletions`, O-27).
4. Kapatılan kullanıcının telefon kurulumları da iptal edilsin.

## press-tr

1. `oidc_verify` bağımlılığı yazılsın ve imaja girsin.
2. Portlar `PANE_PORT` değerinden türesin.
3. İmajlar özetle sabitlensin.
4. Parola komut satırında görünmesin. Örneğin ortam değişkeni ya da dosya kullanın.
5. `patch-py314.sh` yalnız geliştirme imajında çalışsın (O-18). Üretim imajında çalışmadığını bir testle gösterin.
6. Press giriş akışı PKCE S256 kullansın.
7. Press kimlik bağı DocType'ı `ai_write_closed_doctypes` kancasına girsin.

## platform-core-kabuk

1. Alan türünü bileşene eşleyen sürümlü bir katalog yazın. Yanıta `catalog_version` ekleyin (RE-11).
2. `depends_on` gibi ifadeleri bildirimsel biçime çevirin. Örnek: `{field, op, value}`. Çevrilemeyen ifade çıkarılır ve alan işaretlenir.
3. DocType ve alan için `sensitivity` değeri ekleyin. Telefon için izin listesi kurun.
4. Etiket, açıklama ve seçenekleri kullanıcının dilinde sunucuda çevirin. `fieldname` ve seçenek değeri ham kalır.
5. Açılış verisine saat dilimi, para birimi, sayı biçimi ve yuvarlama ekleyin (SZ-9).
6. Sözleşmeye 401 yanıtını ve oturum yoklama ucunu ekleyin (SZ-8).
7. Kenar çubuğu alanlarını izin listesiyle seçin. Şemada `additionalProperties: false` olsun.
8. Gerçek 200, 304 ve 403 yanıtlarını sözleşmeyle doğrulayan test yazın.
9. Sözleşmeye uydurma veriyle örnek yanıt ekleyin (SZ-12).
10. `safe_url` yalnız izinli sunuculara izin versin. Üretimde `http` adresi reddedilsin.
11. `/api/v2/doctype/<ad>/meta` ucu Website User için kapansın. Frappe 16 bu ucu süzmüyor.

## platform-core-yz

1. `expires_at` saat farkıyla ISO 8601 biçiminde dönsün.
2. İnsan uçlarına 401 yanıtı eklensin.
3. Önizleme kaydedilmeden önce şemayla denetlensin. Anahtarlar `fieldname`, `old` ve `new` olur.
4. `ai_write_closed_doctypes` listesini sınayan test yazın. Listedeki her DocType'ın sitede var olduğunu da sınayın.
5. Okuma sonuçları `as_of`, `site` ve `source` taşısın. Öneri `created_at` taşısın.
6. Okuma sonucuna bayt ve satır sınırı koyun. Sınır aşılınca `truncated` dönsün.
7. Öneri listesi veritabanında süzülsün ve sayfalansın.
8. GET isteği günlüğe yalnız reddi yazsın.

## platform-core-gecit

1. AI Route hedefleri JSON yerine alt tabloda tutulsun.
2. Çeviri dosyası bağlam sütunu taşısın (O-23).
3. Tutar ondalık metin olarak ve `currency` alanıyla dönsün.
4. AI API adresi özel ağ adresine gidemesin. Denetim bağlantı anında çözülen adrese yapılır.
5. AI API ve AI Account `ai_write_closed_doctypes` kancasına girsin.
6. Sözleşmeye örnek yanıt ekleyin.

## erisim-kurali

1. Access Rule `ai_write_closed_doctypes` kancasına girsin.
2. Öteki modüllerin kullandığı işlevleri ve kancaları listeleyin. Orkestratör listeyi kayda yazar.

## platform-core-mobil

1. Onay katmanıyla çalışma testi depoya girsin. Katman yoksa test atlansın.
2. Kurulum kayıt anında `sid` saklasın. İptal identity-sync'in `/v1/sessions/revoke` ucunu çağırsın. Aynı `sid` ile gelen belirteç reddedilsin.
3. Kurulum kimliği deseni `^` ve `$` ile sabitlensin.
4. Temizlik aracı `kind: read` olsun.
5. İki iptal aracı için `versioned` denetimi eklensin.
6. `MobileError` hatası `frappe.ValidationError` hatasına çevrilsin.
7. Tekli iptal sonucunun adı hesap durum kaydının adı olsun.
8. Komut kuralına şu cümle yazılsın: `apply` yalnız işlem içi veritabanı yazısı yapar.
9. Sunucu son gerçek kullanıcı işleminin zamanını tutsun (`last_user_activity_at`). Arka plan eşitlemesi bu zamanı değiştirmez.
10. PWA eşitlemesi için çerezle çalışan yol eklensin.
11. Kullanıcı kendi cihazını iptal edebilsin.
12. Kapatılan kullanıcının kurulumları iptal edilsin.
13. Yanıtlar `server_time` taşısın.
14. CORS ve ters vekil ayarı belgelensin.
15. Bildirim gönderecek olayların listesi yazılsın.
16. Telefon kurulumu `ai_write_closed_doctypes` kancasına girsin.
17. DocType etiketleri İngilizceye çevrilsin. Türkçesi çeviri dosyasına girsin (O-21).

## ilk-dikey-dilim

1. Önizleme anahtarları `fieldname`, `old` ve `new` olsun.
2. İnsan onay ucu `version` parametresi alsın. Uyuşmazlıkta 417 dönsün.
3. Genel kayıt ucunun alanları, süzgeci ve yanıt şeması sözleşmeye yazılsın. 401 ve 403 eklensin.
4. Öneri kaydı yalnız gerekli kişi bilgisini tutsun.

## kimlik-tema

1. Hesap ekranında hesap silme bağlantısı görünsün (O-27).
2. Marka adı değişkenden gelsin.

## integration-e2e

Dallar birleşince yedi senaryoyu yeniden koşun. Şu senaryoları ekleyin:

1. Müşteri hesabını siler. Press, kiracı ve telefon tarafı kapanır.
2. Yönetici telefonu iptal eder. Keycloak oturumu da kapanır.
3. Çalışan 1 saat boşta kalır. Sonraki istekte yeniden kimlik doğrular.

## naming-history-fix

Bağımsız incelemenin bütün bulguları düzeltilir. Rapor Pane'in `inceleme-claude.md` dosyasındadır. Ek kararlar şunlardır:

1. O-20, O-21 ve O-22 kararlarını uygulayın.
2. Şu adları eşleşme tablosuna ekleyin: operationId adları, MCP araç adları (`plt_` ve `hrt_`), sözleşme etiketleri ve güvenlik adları, ortam değişkeni önekleri, düzen alanı adları, test dosyası adları.
3. Çift ön ekli adları kısaltın. Örnek: "PTR Identity Link".
4. `dogrulama` için tek terim `verification` olsun.
5. Sözlükleri uygulama köklerine taşıyın.
6. Ruff'ta `N`, `A`, `PLC2401` ve `PLC2403` kurallarını açın.
7. AV-72 ad denetim betiğini yazın. ai-readiness-gate bu betiği 8. denetim olarak çağırır.

## ai-readiness-gate

1. Ham SQL yasağı modül adını sabit yazmasın. Eski ve yeni modül adlarının ikisinde de çalışsın.
2. naming-history-fix'in ad denetim betiğini 8. denetim olarak çağırın.

## security-tooling

Bu iş yeni açıldı (O-29). Maddeler görev dosyasındadır.

## Orkestratör

1. `hooks.py` ve `tr.csv` birleştirmeleri (O-19, O-23).
2. Modüller arası izinli işlev ve kanca listesi.
3. Sunucu saatleri NTP ile eşitlenir. Fark en çok 30 saniye olur.
4. Geliştirme ortamında biriken veri birimlerinin listesi.
5. Karar notu numaraları çakışıyor. Numaraları orkestratör şöyle verdi:
   - `0008-hrms-tr-first-vertical-slice.md` numarasını korur.
   - `0009-naming-history-fix.md` numarasını korur.
   - `0010-ai-readiness-gate.md` numarasını korur.
   - `0011-security-tooling.md` numarasını korur.
   - platform-core-kimlik işinin kimlik bağı notu `0012` olur.
   - platform-core-kimlik işinin hesap anonimleştirme notu `0013` olur.
   - kimlik-tema işinin silme bağlantısı notu `0014` olur.
   - Yeni karar notu sıradaki boş numarayı alır. Sıradaki boş numara `0015` olur.
