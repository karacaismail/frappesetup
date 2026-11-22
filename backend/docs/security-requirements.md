# Güvenlik gereksinimleri

Bu liste proje sahibinin güvenlik önlemleri dosyasından çıkarıldı. Asıl dosya bu depoda değildir. Asıl dosyada kişi adları var. Depo herkese açık olduğu için yalnız gereksinimler buraya alındı.

Liste 22 Kasım 2026 Pazar günü yazıldı. Her satırda gereksinim, onu karşılayan iş ve kaynak vardır. Durum sütunu yoktur. Durumu işin kendi durum dosyası ve bağımsız inceleme gösterir.

Zamanlanmış tarama kurulmaz (D-6). Asıl dosya bazı taramaları her gece ya da her hafta ister. Bu taramalar elle başlatılan komut olur.

## Araçlar

| Gereksinim | Karşılayan iş | Not |
| --- | --- | --- |
| Projeye özel Semgrep kuralları | security-tooling | Var olan güvenlik kapısındadır. |
| Bandit ile Python taraması | security-tooling | `security-full` komutu |
| CodeQL ile derin kod taraması | DevOps sorumlusu | GitHub'da çalışır. Devir notu `docs/handoff/ci-security.md` dosyasındadır. |
| ZAP ya da Nuclei ile çalışan siteye dışarıdan deneme | security-tooling | `dast-scan` komutu. Yalnız yerel adres hedeflenir. |
| Schemathesis ile API'ye rastgele girdi | security-tooling | Sözleşme dosyaları kullanılır. |
| Bütün araçlardan JSON çıktı | security-tooling | `release-report` bu çıktıları toplar. |
| Kodda ve Git geçmişinde gizli bilgi taraması | security-tooling | Gitleaks bütün geçmişi tarar. |

## API ve yetki

| Gereksinim | Karşılayan iş | Not |
| --- | --- | --- |
| Adres, yöntem ya da parametre değişse de yetkisiz işlem yapılamaz. | Her uç sahibi | Her uçta girişsiz ve yabancı hesap testi bulunur. |
| Her rolün izinli ve yasak işlemleri yazılır. Kullanıcı kendini yönetici yapamaz. | erisim-kurali, platform-core-kimlik | Rol kaynağı Keycloak'tır. |
| Kullanıcı isteğe fazladan alan ekleyerek rolünü değiştiremez. | Her uç sahibi | Tür ipuçlu whitelist ve `extra=forbid` kullanılır. |
| Bir müşteri başka müşterinin verisini göremez. Bunu veritabanı engeller. | Press ve kiracı yapısı | Her kiracının ayrı veritabanı vardır. |
| Ortak güvenlik kapısı her uca uygulanır. Kapı varsayılan olarak açıktır. | security-tooling | Uç denetimi `dev/guvenlik/endpoints.py` dosyasındadır. |
| Her işe başlamadan üç soru cevaplanır: kim yapabilir, veri kimin, girişsiz biri ne görür. | Her iş | Cevap görev dosyasına ya da karar notuna yazılır. |

## İşlem güvenliği

| Gereksinim | Karşılayan iş | Not |
| --- | --- | --- |
| Tutarlar sunucuda yeniden hesaplanır. Dışarıdan gelen tutar kabul edilmez. | platform-core-gecit, press-tr | Tutar ondalık metin ve para birimiyle taşınır. |
| Aynı işlem iki kez yapılmaz. İstek bir anahtar taşır. | identity-sync, platform-core-mobil, platform-core-yz | Örneğin öneri onayı tek seferliktir. |
| Eşzamanlı istek sınırı aşamaz. | platform-core-mobil, platform-core-yz | Kilit ve sürüm denetimi kullanılır. |
| Eski webhook, belirteç ya da işlem kanıtı yeniden kullanılamaz. | identity-sync, kimlik-realm | Olay imzası zaman damgası taşır. |
| Kullanıcı girdisi veritabanı komutuna dönüşmez. Tehlikeli sorgu otomatik bulunur. | security-tooling, ai-readiness-gate | Ham SQL yasağı kapıdadır. |
| SQL ve XSS saldırı testleri yapılır. | Her uç sahibi ve security-tooling | |
| Sunucu iç ağa istek atmaz. | platform-core-gecit | Özel ağ adresi bağlantı anında reddedilir. |

## Giriş ve oturum

| Gereksinim | Karşılayan iş | Not |
| --- | --- | --- |
| Giriş, parola sıfırlama ve doğrulama kodu ekranlarında deneme sayısı sınırlıdır. | kimlik-realm | Keycloak kaba kuvvet koruması kullanılır. |
| İptal edilen oturum çalışmaz. | kimlik-realm, platform-core-kimlik, platform-core-mobil | Karar 19 ve O-25 |
| Kullanıcının kimliği, cihazı ve yetkisi her istekte denetlenir. | platform-core-kimlik, platform-core-mobil | Sıfır güven ilkesi |
| Aynı kullanıcının çok sayıda isteği sınırlanır. | Her uç sahibi | Frappe 16 `rate_limit` kullanılır. |

## Süreç

| Gereksinim | Karşılayan iş | Not |
| --- | --- | --- |
| Kodu yazan yapay zekâdan başka bir yapay zekâ kodu saldırgan gözüyle inceler. | Orkestratör | Codex kodunu Claude, Claude kodunu Codex inceler. |
| Bulunan her açık bir teste dönüşür. | Her iş | Önce test yazılır. |
| Korumayı silip test koşulur. Test kırmızı vermiyorsa yeniden yazılır. | Her iş | Kırmızı kanıtı durum dosyasına yazılır. |
| Her uçta iki zorunlu test vardır: girişsiz çağrı reddedilir, yabancı hesabın verisi görünmez. | Her uç sahibi | |
| Kötüye kullanım senaryoları işten önce yazılır. | Her iş | Örnek kart `dev/guvenlik/kotuye-kullanim-karti.md` dosyasındadır. |
| Dağıtımdan önce dışarıya açılan uçların listesi çıkar. | security-tooling | `release-report` komutu |
| Dağıtımdan sonra canlıda kısa saldırı seti koşar. | DevOps sorumlusu | Canlı ortam kurulunca başlar. |
| Güvenlik sayıları düzenli raporlanır. | security-tooling | Elle başlatılan karne komutu. Zamanlanmış iş yoktur. |
| Yeni model çıkınca ya da model yükselince tam güvenlik raporu alınır. | Orkestratör | Elle başlatılır. |
