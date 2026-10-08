---
title: "Karar kataloğu"
nav: "Karar kataloğu"
order: 26
---

Kullanıcının araştırma notlarından çıkan kararlar; her ihtiyaç bir kez, bir satırda. Notlar karardır: repodaki aktif veriyle çelişenler **Çelişki** olarak işaretlendi ve repo verisi değişmedi. Repoda zaten yazılı kararlar (320-first, `issuer + sub`, ROPC yasağı, belirteç tarayıcıya inmez, hibrit giriş, gerçek cihaz ayrı rapor vb.) tekrar edilmedi. Açık ve çelişkili satırlar [Açık kararlar](/frappesetup/acik-kararlar/) sayfasındaki K-37..K-60'a bağlıdır.

**Durum:** Kesin · Koşullu (koşul sağlanınca) · Açık (karar bekliyor) · Çelişki (repo verisiyle zıt, onay bekliyor).
**Kaynak:** KC kimlik rehberi · AE AI ekosistemi · KS Kaizen şartnamesi · KP Kaizen paketi · AM, A1, A2 adaptif arayüz notları. Dosya adları: [İzlenebilirlik](/frappesetup/izlenebilirlik/) KD-38..KD-44.

## Kimlik (KM)

| ID | Karar | Durum | Kaynak | Yer |
| --- | --- | --- | --- | --- |
| KM-01 | Keycloak çekirdeği fork edilmez; sürüm seri düzeyinde sabitlenir (26.7 serisinin güncel yaması). | Çelişki | KC | K-45 |
| KM-02 | Keycloak Organizations MVP'de kullanılmaz; yalnız kurumsal müşteri kendi kimlik sağlayıcısını isterse değerlendirilir. | Çelişki | KC | K-46 |
| KM-03 | Frappe girişi kendi küçük köprü uygulamasıyla yapılır; Social Login ve hazır köprüler kullanılmaz. İlk bağ yalnız doğrulanmış e-postayla, e-posta değişikliği köprüde yansıtılır. | Çelişki | KC | K-47 |
| KM-04 | Tenant modeli: tek Frappe site + organizasyon izolasyonu ya da müşteri başına site; veri modelini belirler, Faz 1 bitmeden kapanır. | Çelişki | KC | K-37 |
| KM-05 | Frappe tarafında Kimlik Bağı, Organizasyon, Üyelik, Uygulama, Uygulama Yetkisi, KYC/KYB, Onboarding ve Rıza DocType'ları; Keycloak, Frappe ve OTP gateway verisi ayrı, biri diğerine yazmaz. | Çelişki | KC | K-48 |
| KM-06 | Tek ana alan: `accounts.` Keycloak, `app.` panel ve uygulamalar (`/crm` gibi yollar, `/api` Frappe'ye), `www.` frontpages. | Çelişki | KC | K-49 |
| KM-07 | Passkey yönetici ve KYC inceleyicisi için zorunlu, müşteri için isteğe bağlı; SMS kodu yalnız müşteri girişinde. | Çelişki | KC | K-50 |
| KM-08 | Dört depo: identity-infra, frappe-apps, frontends, otp-gateway. | Çelişki | KC | K-51 |
| KM-09 | Lisans kapısı her PR'da SBOM üretir: izinli MIT, Apache-2.0, BSD, ISC; yasak AGPL, SSPL, BUSL, Elastic, lisanssız. Belirsiz lisans insan incelemesine gider. | Çelişki | KC | K-52 |
| KM-10 | Magic link açık gereksinimdir; e-posta kodu tamamlanınca kapanmış sayılmaz. | Açık | KC | K-38 |
| KM-11 | Telefon numarasını yazıp giriş tasarım kararı bekler (Frappe kullanıcı modeli e-posta ister). | Açık | KC | K-39 |
| KM-12 | E-postasız hesap kararı bekler. | Açık | KC | K-40 |
| KM-13 | Casdoor güvenlik kaydı hedef sürümde düzeldiği gösterilene kadar çekirdek aday değil; Better Auth ve Logto öncelikli değil. | Açık | KC | K-44 |
| KM-14 | Oturum süreleri (Keycloak boşta/azami, Frappe) ürün kararıdır; tek çıkış bildirimi kaçarsa kısa Frappe oturum süresi yedektir. | Açık | KC | K-41 |
| KM-15 | Yük altında kabul edilen giriş süresi hedefi belirlenmemiştir. | Açık | KC | K-42 |
| KM-16 | Teknik inceleyici (ekipten geliştirici ya da dış güvenlik danışmanı) belirlenir; faz kapılarını yürütür. | Açık | KC | K-43 |
| KM-17 | Ticari dağıtım modeli (yalnız SaaS ya da müşteriye kurulum) AGPL ve GPL yükümlülüklerini belirler. | Açık | KC | K-1 |
| KM-18 | Hazır giriş yöntemleri: parola + e-posta doğrulaması, Google, passkey. Aday (prototip): Apple, SMS, WhatsApp/Telegram, e-posta kodu; kabul testi geçmeden canlıya çıkmaz. | Kesin | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-19 | Eklenti seçimi altı koşulla: lisans kapısı, sabit sürümle derleme, kendi testleri, yakın sürüm ve güvenlik yolu, bağımsız kod incelemesi, kabul testleri. Başarısızlıkta özel kod yazılmaz; önce neden, sonra başka bileşen, daraltma ya da güvenlik incelemeli özgün geliştirme. | Kesin | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-20 | Kimlik kabul testleri gruplar hâlinde: giriş yöntemleri, SSO, tek çıkış, köprü, eşleme, şirket izolasyonu, yetki ve KYC/KYB, oturum, kötüye kullanım, yapılandırma ve yükseltme, yük. Kapsam yüzdesi tek başına kanıt değildir. | Kesin | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-21 | Branding (giriş, kayıt, sıfırlama ekranları ve e-postalarda üçüncü taraf ad/logo) ve güvenlik (imaj, bağımlılık, kötüye kullanım testi) kapıları CI'dadır; her kapıda insan adımı kalır. | Kesin | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-22 | Realm yapılandırması git'te `keycloak-config-cli` ile, yönetici parolası yerine servis hesabıyla uygulanır; panelden elle değişiklik yasak, gecelik fark raporu. | Kesin | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-23 | OTP gateway kod üretmez ve doğrulamaz; kod saklanmaz, numara hash'lenir, sağlayıcı anahtarı ortam değişkenindedir; numara, IP ve ülke başına gönderim sınırı ve maliyet alarmı. | Koşullu | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-24 | Yapay zekâ kimlik kodunu yazar; çekirdeğe (eklenti, realm akışı, köprü, OTP sınırı) dokunan değişikliği yazmayan ajan ve teknik kişi inceler. main'e doğrudan push yok, kimse kendi PR'ını onaylamaz. | Kesin | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |
| KM-25 | KVKK ve İYS satırları hukuki görüş değildir; dağıtım modeli ve lisanslarla birlikte hukukçuya teyit ettirilir. | Koşullu | KC | [Rail 4](/frappesetup/rail-4-keycloak/) |

## Yapay zekâ ekosistemi (AI)

| ID | Karar | Durum | Kaynak | Yer |
| --- | --- | --- | --- | --- |
| AI-01 | Resmi AI katmanı üretime hazır değil (`frappe/mcp` ve Flow deneysel, `frappe/skills` geliştirici aracı). Raven 1 Ocak 2026'dan resmi: mesajlaşma sınıf A, Raven AI ajanları B ve kapalı. | Kesin | AE | [Agents](/frappesetup/ai-agents/) |
| AI-02 | Sınıf üretim güvenliği ve olgunluktur (A, B, C), depo başına gerekçeli. | Kesin | AE | [Agents](/frappesetup/ai-agents/) |
| AI-03 | Dört yetki seviyesi: yalnız okur, öneri verir, veriyi değiştirir, otomatik aksiyon alır. | Kesin | AE | [AI genel bakış](/frappesetup/ai-bakis/) |
| AI-04 | Seviye 3 ve 4 yalnız taslak üretir, submit yetkisi olmaz; öğrenci, ücret ve muhasebe doctype'larında kapalıdır (EDU sitesi). | Çelişki | AE | K-53 |
| AI-05 | MCP: yalnız okuma araçları, ayrı AI kullanıcısı, gerekli doctype'lar, staging verisi; kullanıcı başına OAuth, yazmada ayrı onay, her çağrı denetim kaydı, sağlayıcıyla DPA. Yasak: Administrator anahtarı, açık `run_python_code`, `run_database_query`, `delete_document`, lisanssız repo, ham REST/SQL aracı. | Kesin | AE | [MCP](/frappesetup/ai-mcp/) |
| AI-06 | Frappe Assistant Core en olgun MCP (sınıf B, tek kişiye bağlı); yalnız staging'de Python, SQL ve silme araçları kapalı denenir. Lisans v2.0.0'da MIT'den AGPL'ye geçti. | Koşullu | AE | [MCP](/frappesetup/ai-mcp/) |
| AI-07 | Geliştirici skill paketleri geliştirme ortamında kurulur, siteye kurulmaz; üretilen kod yine incelenir. | Kesin | AE | [Skills](/frappesetup/ai-skills/) |
| AI-08 | Staging'de denenecek: Jarvis (hazırla-onayla, Trigger kapalı), Huf (Ollama, LiteLLM sürümü sabit), Builder Bob (yalnız pazarlama sayfası, onay açık). | Koşullu | AE | [AI genel bakış](/frappesetup/ai-bakis/) |
| AI-09 | İzlenecek: Flow tam sürümü, Grove, Studio, frappectl, yerel OCR belge kuyruğu, Helpdesk AI, Raven V3 sağlayıcıları, `frappe/mcp` kararlı sürümü. | Kesin | AE | [AI genel bakış](/frappesetup/ai-bakis/) |
| AI-10 | Kaçınılacak: otomatik ana veri üreten OCR ve submit yetkili ajan. | Kesin | AE | [AI genel bakış](/frappesetup/ai-bakis/) |
| AI-11 | Öğrenci verisine dokunan yapay zekâ yerel modelle sınırlı; dış LLM yalnız anonim içerik ve kod geliştirme için. GPU'suz sunucuda yalnız 7–8B model, yalnız sınıflandırma ve özetleme. | Çelişki | AE | K-54 |
| AI-12 | Huf'ta LiteLLM PyPI tedarik zinciri olayı (24 Mart 2026): LiteLLM sürümü sabitlenir (güvenli ≤ 1.82.6). | Kesin | AE | [Agents](/frappesetup/ai-agents/) |
| AI-13 | Özel geliştirme gerektiren boşluklar: LMS/Education AI, Türkçe kişisel veri maskeleme, kota ve maliyet, prompt injection savunması, Türkçe doğruluk. | Kesin | AE | [AI genel bakış](/frappesetup/ai-bakis/) |
| AI-14 | n8n yalnız tekrarlayan işlerde; AI yalnız etiket önerir, kaydı onaylamaz. | Koşullu | AE | [AI genel bakış](/frappesetup/ai-bakis/) |
| AI-15 | Notta anlatılan Sena-Services/frappe-mcp-server, myrmline/erpnext_bot_ai, Tariquaf/invoice-ocr-enhanced 8 Ekim'de 404; OpenAEC lisansı notta MIT, klonda LGPL v3 metni. | Çelişki | AE | K-59 |

## Adaptif arayüz (AU)

| ID | Karar | Durum | Kaynak | Yer |
| --- | --- | --- | --- | --- |
| AU-01 | Mimarinin adı: Capability-Adaptive Mobile-First Progressive Enhancement, Capability-First Adaptive UI Delivery Architecture ya da Real Adaptive Delivery Architecture; teslimat katmanı Server-Assisted Differential Delivery. | Açık | AM A1 KP | K-60 |
| AU-02 | 320 CSS px yerleşim hedefidir, fiziksel piksel değil; "iPhone 4 desteği" eski işletim sistemi ve tarayıcı desteği değildir. | Kesin | AM A1 A2 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-03 | Yoğunluk modları comfortable, compact, dense; B2B varsayılanı compact. Dar ekranda önce süs boşluğu azalır; sonra öncelikli sütun, ayrıntı çekmecesi, tablo içi kaydırma. | Kesin | A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-04 | Boşluk başlangıç tablosu: 320'de sayfa kenarı 12, aralık 8, yoğun veri 4 px; 390'da 16/12/8; 768'de 24/20/12; 1440 ve üstü en çok 40/24/16. Ölçümle uyarlanır. | Koşullu | AM | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-05 | Notta gövde yazısı 15 px'lik clamp ve ince işaretçi hedefi 32 px geçer; kalıcı kurallar (metin ≥ 1rem, hedef 44 px, kaba girişte 48 px) korunur. | Çelişki | AM A2 | K-58 |
| AU-06 | TV ve oturma odası ürün yüzeyidir, genişlikten çıkarılmaz; kaba dokunma 56 px, birincil 64 px, güçlü odak, uzamsal klavye gezinmesi. | Koşullu | AM A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-07 | Viewport matrisi: dikey 320×480, 320×568, 360, 375, 390, 393, 412, 430; yatay 480×320, 568×320, 667×375, 844×390; tablet 600, 744, 768, 820, 1024; masaüstü 1280, 1366, 1440, 1920. 4K, 5K, 8K test boyutudur, kırılma noktası değil. | Kesin | AM A1 A2 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-08 | Her kırılma N için N−1, N, N+1 testi; kısa yükseklik, sanal klavye ve yön değişimi ayrı senaryo. | Kesin | AM A2 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-09 | Media query yalnız seçilen profilin içinde; başka profilin paketini indirip media query ile dönüştürmek yasak. Yeniden kullanılan bileşende container query. | Kesin | A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-10 | Koşullu teslimat: `<link media>` indirmeyi engellemez; profile özgü CSS sınıflandırmadan sonra DOM'a eklenir, JS dinamik `import()` ile. İlk yanıt küçük evrensel HTML ve çok küçük bootstrap. | Kesin | AM A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-11 | Client Hints sonraki isteklerde optimizasyondur, önkoşul değil; User-Agent ayrıştırma son çare; Service Worker ilk istek dedektörü değil. Sunucu önbelleği yalnız kaba kovalarla (evrensel, telefon eğilimli, hafif). | Kesin | AM A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-12 | Yerleşim paketleri (telefon, tablet, masaüstü, oturma odası) karşılıklı dışlayıcı, giriş paketleri (kaba, hassas, uzamsal) toplanabilir; veri, yetki ve doğrulama ortak. Ayrı kabuk yalnız deneyim gerçekten değişince. | Kesin | AM A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-13 | Ağ izolasyonu testi: telefon masaüstü ve tablet paketini, masaüstü telefon paketini istemez; gereken paket gelir ve görev tamamlanır, boş ekran başarı değildir. | Kesin | AM A1 KP | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-14 | Playwright birincil; Percy veya Applitools ek katmandır ve ücretli servis otomatik kurulmaz. | Koşullu | AM | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-15 | Görsel doğrulama üç katman: aynı ortamda piksel, bulanık/yapısal analiz, insan. Gerçek cihaz kaydı model, OS, tarayıcı, viewport, DPR, giriş ve ağ taşır. | Kesin | AM A1 A2 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-16 | Core Web Vitals p75: LCP ≤ 2,5 s, INP ≤ 200 ms, CLS ≤ 0,1; TTI birincil kapı değil. | Kesin | AM A1 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-17 | Başlangıç bütçeleri: kritik CSS 20 KB (AM) ya da 8 KB (A2), ilk JS 150 KB, rota JS 250 KB (AM) ya da 120 KB (A2), aktarım 500 KB. Ölçümle sıkılaştırılır. | Çelişki | AM A2 | K-57 |
| AU-18 | Destek seviyeleri: A tam, B işlevsel, C özel kapsam (TV, kiosk), D kapsam dışı. "Son iki sürüm" müşteri kitlesi görülmeden evrensel kural değil. | Koşullu | A2 | [Rail 3](/frappesetup/rail-3-frontend/) |
| AU-19 | Her bileşenin daralınca neye dönüştüğü ve neyi asla kaybetmediği yazılır; tabloyu karta çevirmek genel kural değil; sürükleme için alternatif, grafik için veri alternatifi, yazdırma için ayrı düzen. | Kesin | A2 | [Rail 3](/frappesetup/rail-3-frontend/) |

## Kalite ve sürekli iyileştirme (KZ)

| ID | Karar | Durum | Kaynak | Yer |
| --- | --- | --- | --- | --- |
| KZ-01 | Agent Kaizen üç döngü: görev içi düzeltme, CAPA/DÖF, ölçülmüş süreç iyileştirmesi. Başarı: kalite korunurken kabul edilmiş görev başına maliyet ve yeniden işleme azalır; tek yeşil sonuç kanıt değildir. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-02 | Paket kurulu sistem değil şartname ve şablondur; `policy.json` var olmakla kontrol etkinleştirmez. ISO belgelendirme iddiası yoktur, eşikler başlangıç önerisidir. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-03 | Kurulum sırası: gözlem modu, güvenilir evaluator (bilinen kusurlu örnekle sınanır), bütçeli yeniden deneme, CAPA, challenger deneyleri (otomatik terfi kapalı). | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-04 | Otorite ajanın değiştiremediği yerdedir: CI işi, sabit evaluator sürümü, salt okunur politika, ayrı onay kimliği. Holdout görevleri ajana verilmez. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-05 | Durum makinesi NEW, CONTRACT_READY, BASELINE_CHECK, IMPLEMENTING, VERIFYING, ACCEPTED; hatada TRIAGE, REPRODUCING, FIX_PROPOSED. Bloke görev başarılı sayılmaz. | Kesin | KS | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-06 | On iki küçük modül: tetik adaptörü, ortam yoklaması, test planlayıcı, koşucu adaptörleri, kanıt deposu, hata sınıflayıcı, parmak izi, bütçeli onarım, CAPA defteri, metrik raporu, deney koşucusu, terfi kapısı. | Kesin | KS | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-07 | Geçiş kapısı: doğru kaynak ağacı ve build, gerekli testler bulunmuş ve çalışmış, zorunlu atlama yok, gerçek artifact. Exit code 0 tek başına yetmez; checksum bütünlük içindir, yetki değil. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-08 | Onarım en çok 3 deneme; yeni kanıt yokken aynı parmak izi 2 kez dönerse yönlendir ya da dur. Bütçe tanımsızsa gözetimsiz döngü başlamaz. | Kesin | KS | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-09 | Yükleme disiplini: global metin kısa; yalnız kapsamı eşleşen en çok 3 onaylı ders yüklenir. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-10 | Claude hook'ları (SessionStart, PreToolUse, PostToolUse, Stop) kurulur ve yüklendiği ayrı test edilir. | Çelişki | KS KP | K-55 |
| KZ-11 | Paket global talimat dosyasına birleştirme adımı içerir. | Çelişki | KP | K-55 |
| KZ-12 | Kanıt sonuç değerleri pass, fail, blocked, unknown. | Çelişki | KP | K-56 |
| KZ-13 | Evaluator 24 senaryoyla sınanır (QA-001..QA-024: sıfır test keşfi, eski commit raporu, yanlış port, çift olay, sızan holdout, hata mesajındaki talimat, iptal…); her biri kusurlu örnekte FAIL, korumalı sistemde PASS verir. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
| KZ-14 | Kanıta gizli veri girmez; hata mesajındaki talimat veri olarak saklanır, uygulanmaz. İlk sürümde SQLite + JSONL; her kayıt project_id, task_id, run_id taşır. | Kesin | KS KP | [Kalite kuralları](/frappesetup/kalite-kurallari/) |
