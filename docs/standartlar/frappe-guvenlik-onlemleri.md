## **Öneri listesi 1**

**Semgrep**  
Ne yapar: Kendi kuralını yazabilirsin. böylelikle düzenli  tekrarlanan açıklar olmaz.  
\--------------------  
**Bandit**  
Python'da bilinen tehlikeli kalıpları arar.Bizde nerede işe yarar: Dosya yolu, requests ve benzeri kullanımlar  
\--------------------  
**CodeQL**  
Ne yapar: GitHub'ın derin kod taraması yapmamızı sağlar.  
\--------------------  
**OWASP ZAP, Nuclei**  
Ne yapar: Çalışan siteye dışarıdan saldırı denemesi yapar. her gece Alpha repo üzerinde test edililebilir  
\--------------------  
**Schemathesis**  
Ne yapar: API'yi otomatik olarak rastgele girdilerle dener.  
\--------------------  
Yukarıdaki araçların hepsinde json olarak çıktı alabiliriz .  
\--------------------  
**/claude-security**   
Ne yapar: Kodu tarar, her bulgu için bir düzeltme  dosyası üretir ve düzeltmeyi testlerle ayrıca kontrol ettirir.  
\--------------------  
**Regresyon testi**  
Ne yapar: Bir yazılımda yeni bir özellik eklendiğinde, bir hata düzeltildiğinde veya kod değişikliği yapıldığında, mevcut işlevlerin bu değişiklikten olumsuz etkilenip etkilenmediğini kontrol etmek için yapılan test türüdür.  
---

## **Öneri listesi 2**

1- API Güvenliği : { URL, GET, POST, PUT, PATCH, DELETE } ve gönderilen parametreler değiştirilse bile yetkisiz işlem yapılamamalı.  
2- Yetki Güvenliği : Her rol için izin verilen ve yasaklanan işlemleri belirleyelim. Kullanıcı kendisini yönetici yapmaya çalıştığında sistem engellesin.  
3- İşlem Güvenliği : Sipariş, ödeme, indirim, bakiye ve iade tutarlarını sunucuda yeniden hesaplayalım. Dışarıdan değiştirilen değerleri kabul etmeyelim.  
4- Veritabanı Güvenliği : Kullanıcı girdilerinin veritabanı komutuna dönüşmesini engelleyelim. Tehlikeli sorgu kullanımını kod kontrolünde otomatik yakalayalım.  
5- İstek Sınırlandırması : Aynı kullanıcının binlerce istek göndermesini sınırlayalım. Ödeme ve sipariş gibi işlemlerin yanlışlıkla iki kez gerçekleşmesini engelleyelim.   
6- Gizli Bilgi Güvenliği : Şifre ve API anahtarlarını koddan ayıralım. GitHub'a gönderilmelerini otomatik engelleyelim. Açığa çıkan anahtarları geçersiz kılalım.  
7- Bağımsız AI Denetimi : Geliştirmeyi yapan AI dışında başka bir AI, kodu saldırgan gözüyle incelesin. Bulduğu açıkları testle doğrulasın.  
8- Kalıcı Açık Kontrolü : Bulunan her güvenlik açığını otomatik teste dönüştürelim. Aynı açık yeniden oluşursa geliştirme pivot edilsin ve tdd içeriği güncellensin.  
9- Güvenlik Sınır Testleri : Her yeni özellik için hatalı veri, yetkisiz kullanıcı, değiştirilmiş istek ve kötüye kullanım senaryoları oluşturulsun ve otomatik olarak çalıştıralım.  
10- Bir müşteri, başka bir müşterinin verisini hiçbir koşulda görememeli. Bunu kod değil, veritabanı engellemeli.  
11- Kullanıcı, istek içine fazladan alan ekleyerek kendi yetkisini ya da rolünü değiştirememeli.  
12- Giriş, şifre sıfırlama ve doğrulama kodu ekranlarında deneme sayısı sınırlı olmalı.  
---

## **Öneri listesi 3**

**GELİŞTİRMEDEN ÖNCE :**

- **Ortak güvenlik kapısı**: Her uca (API) ayrı kilit takmak yerine binaya tek turnike koyarız — güvenlik varsayılan olarak açık gelir, unutulamaz. **Çıktı**: merkezi kapı kodu  
- **Şifre taraması**: Koda yanlışlıkla yazılmış şifre ve anahtarları yakalayan bekçi kurarız — sızıntı GitHub'a gitmeden durur. **Çıktı**: tarayıcı kurulumu  
- **Kartta 3 soru**: Her işe başlamadan "kim yapabilir, veri kimin, girişsiz biri neyini görür" cevaplanır — boşluk bırakılırsa ben gereğinden geniş açarım. **Çıktı**: kart şablonu

**GELİŞTİRME SIRASINDA:**

- **Omuz üstü tarayıcı:** Kod yazıldığı saniyede otomatik güvenlik kontrolünden geçer ve uyarı doğrudan Claude'a gider — hata, geliştiriciye ulaşmadan düzeltilir. **Çıktı**: hook ayarı \+ betik  
- **Yasaklı kalıp listesi**: "Yetki kontrolünü atla" gibi satırları uyarı değil engel yaparız — o satır koda bir daha hiç giremez. **Çıktı**: engel listesi  
- **Projeye özel tarayıcı kuralları**: Hazır araçlar Frappe'yi bilmediği için kendi kurallarımızı yazarız — "turnikesiz uç gördün, bağır" der. **Çıktı**: 8 tarama kuralı  
- **Her uca 2 zorunlu test**: Girişsiz çağrı reddedilmeli, yabancı hesabın verisi bulunmamalı — bu ikisi yoksa modül bitmiş sayılmaz. **Çıktı**: test çifti  
- **Testin kanıtı**: Korumayı silip testi koştururuz — kırmızı vermiyorsa o test hiçbir şey ölçmüyordu.  
  **Çıktı**: kırmızı kanıtı

**GELİŞTİRMEDEN SONRA:**

- **Otomatik kontrol kapısı**: Yüklediğin kodu test ve taramadan geçiren, bozuksa durduran kapıyı kurarız — bugün projede dağıtan 6 iş var, kontrol eden hiç yok. **Çıktı**: ci.yml dosyası  
- **Modül sonu güvenlik incelemesi**: Biten işi iki ayrı göz güvenlik gözüyle okur — yerleşik komut ve senin ajanın (ajanı önce güncellemek şart, bayat). **Çıktı**: inceleme raporu  
- **Sürüm raporu:** Dağıtımdan önce "bu sürümle dışarıya ne açtık" listesi üretilir — 154 misafir ucun nasıl biriktiğinin cevabı budur. **Çıktı**: tek sayfa liste  
- **Canlıda duman testi**: Aynı saldırı setinin kısası dağıtımdan sonra canlıda koşar — yerelde açık olan koruma canlıda kapalı olabilir. **Çıktı**: canlı test seti  
- **Haftalık karne**: Haftada bir sayılar, paket açıkları ve ret artışları raporlanır — ölçülmeyen sayı azalmaz. **Çıktı**: haftalık rapor

---

## **Öneri listesi 4**

**GELİŞTİRMEDEN ÖNCE**   
Abuse Cases(Kötüye Kullanım Senaryoları) first olarak icebox’a eklenmeli.   
\-Authentication (AuthN) \- Authorization(AuthZ) \- Session lifecycle management(iptal edilmiş oturumun çalışması)  
\-SSRF Protection(sunucu üzerinden iç ağa ulaşma)  
\-SQL ve XSS injection  saldırı testleri yapılmalı.  
\-RBAC,ABAC,ReBAC (role,özelliklere,ilişkiye(yetki)) senaryolarının testi.  
\-Idempotancy(örnek aynı anda ödeme için 10 kere butona bastığımda ilk bastığımdan sonrakiler işleme dahil edilmicek çözüm isteğe key atanır.)  
\-Concureency Control (eşzamanlı isteklerde istek, bakiye veya onay sınırını aşamaz)  
\-Replay Protection(eski webhook,token veya işlem kanıtı yeniden kullanılamaz)  
\-Secret Scanning(geliştirme bittikten sonra kod ve geçmişte key/password arar)  
\-DAST(çalışan uygulamayı http üzerinde test eder)  
\-Zero Trust(0 güven) B2B kullanıcısı olarak süreçlerde kullanıcı kimliğimin, cihazımın ve erişim yetkilerimin kontrol edilmesini istiyorum.  
---

## **Ortak tahta**

Periyodik \[haftalık, aylık, 3 aylık, yıllık\] kontrol ve tarama.   
AI \-\> Güvenlik kural setleri  
LLM Yeni model çıkınca, yada mevcut model yükselince, full rapor.  
Mythos claude başvurusu  
Icebox form güvenlik kriterleri  
Çıktılarda sızma testleri  
Her gece güvenlik testleri