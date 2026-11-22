# İş: guvenlik-kapisi

Bu iş backend için otomatik bir güvenlik kapısı kurar. Kapı her değişiklikte çalışır. Açık bulursa denetim başarısız olur. Ekip bu önlemleri önerdi. Öneriler aşağıdaki listededir.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJECT-RECORD.md`
3. `backend/docs/contracts.md`
4. `docs/standartlar/frappe-python-standartlari.md`, özellikle 6. bölüm (G-1 ile G-16)
5. Karar sitesinde `src/content/docs/kalite-kurallari.md`

## Sahip olduğunuz yerler

- `backend/dev/security/`
- `backend/dev/bin/security-check`
- `backend/docs/decisions/0005-security-gate.md`

## Ekibin önerdiği önlemler

- Kendi tarama kurallarımızı yazalım. Hazır araçlar Frappe'yi tanımaz.
- Python'daki tehlikeli kalıpları arayalım.
- Koda yazılmış şifre ve anahtarları yakalayalım.
- API'yi rastgele girdilerle deneyelim.
- Her uca iki zorunlu test olsun. Girişsiz çağrı reddedilsin. Başkasının verisi bulunmasın.
- Korumayı silip testi koşalım. Test kırmızı vermiyorsa hiçbir şey ölçmüyordur.
- Kimin dışarıya hangi ucu açtığını gösteren bir liste üretelim.
- Tutarı ve indirimi sunucuda yeniden hesaplayalım. Dışarıdan gelen değeri kabul etmeyelim.
- İstek içine fazladan alan ekleyerek rol değiştirilemesin.
- Aynı ödeme ya da sipariş iki kez işlenmesin.
- Giriş ve doğrulama ekranlarında deneme sayısı sınırlı olsun.

## Kontrol noktası 1: araç kararı

1. T-2 karar notunu yazın. Şu araçları karşılaştırın: Semgrep, Bandit, gitleaks, Schemathesis.
2. Her aracın lisansını, son sürümünü ve bakımını resmî kaynaktan doğrulayın.
3. Açık kaynak lisanslı araçları seçin. Seçimi gerekçesiyle yazın. Soru sormayın (D-10).
4. Araçları genel kurulumla yüklemeyin. Sürümü sabit container imajıyla ya da sabit sürümlü `uvx` komutuyla çalıştırın.
5. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: Frappe kuralları

Kendi Semgrep kurallarınızı yazın. Kurallar şu kalıpları yakalasın:

- izin denetimi yapmayan `@frappe.whitelist` ucu,
- `ignore_permissions=True` kullanımı,
- `frappe.db.sql` içinde f-string, `format` ya da `+` ile kurulan sorgu,
- `allow_guest=True` olup istek sınırı olmayan uç,
- `methods` seçeneği yazılmamış uç (G-6),
- istek yolunda `frappe.db.commit` (V-2),
- Jinja'da `| safe`,
- `eval`, `exec` ve `shell=True`,
- süre sınırı verilmemiş dış HTTP isteği (G-13),
- model sağlayıcısı kitaplığının içe aktarılması (D-9).

Her kural için bir hatalı ve bir doğru örnek dosya yazın. Test, kuralın hatalı örnekte uyardığını ve doğru örnekte susmadığını gösterir (N-5).

## Kontrol noktası 3: uç denetimi

1. Bütün `@frappe.whitelist` uçlarını listeleyen bir betik yazın. Python'un `ast` modülü yeterlidir.
2. Betik misafire açık uçları ayrı bir raporda göstersin.
3. Her uç için iki testin varlığını denetleyin: girişsiz ret ve başka kullanıcının verisi. Test yoksa denetim başarısız olsun.
4. Testlerin adlandırma kuralını `backend/dev/security/README.md` dosyasına yazın.
5. Yeni özellik için kötüye kullanım kartı şablonunu yazın. Kart üç soru sorar: Kim yapabilir? Veri kimin? Girişsiz biri neyi görür?
6. Bütün denetimleri `backend/dev/bin/security-check` komutunda toplayın.
7. Commit atın ve `done` raporlayın.

## Sınırlar

- Zamanlanmış tarama kurmayın (D-6). “Her gece” önerisi elle başlatılan komut olur.
- Git kancası kurmayın. Kullanıcının yazar koruması `core.hooksPath` ayarını kullanır.
- Çalışan siteye saldırı denemesi (ZAP, Nuclei) bu turda yoktur. Notta sonraki adım olarak yazın.
- GitHub Actions dosyası bu turda yazılmaz.
