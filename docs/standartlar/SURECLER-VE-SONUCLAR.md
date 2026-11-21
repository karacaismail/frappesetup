# Süreçler ve sonuçlar

Bu dosya kural dosyalarının nasıl yazıldığını ve denetlendiğini anlatır. Tarih 21 Kasım 2026 Cumartesi günüdür.

Kararlar `KARARLAR.md` dosyasındadır. Bekleyen işler `ACIK-ISLER.md` dosyasındadır.

## Dört kural dosyası

| Dosya | Kapsam | Boyut | Sınır | Kural |
|---|---|---:|---:|---:|
| `frappe-python-standartlari.md` | Frappe'deki Python kodu | 38.000 | 38.000 | 93 |
| `frappe-python-disi-standartlari.md` | Frappe'deki öteki dosyalar | 32.345 | 32.768 | 110 |
| `headless-frontend-standartlari.md` | Ayrı arayüz | 29.967 | 32.768 | 110 |
| `mobile.md` | PWA ve Capacitor uygulaması | 35.989 | 36.000 | 114 |

Boyut ve sınır bayt cinsindendir. Boyut `wc -c` komutuyla ölçüldü.

Her dosyanın kural kodu harfleri farklıdır:

- Python dosyası `A`, `T`, `O`, `M`, `B`, `S`, `V`, `G`, `D`, `P` ve `R` harflerini kullanır.
- Python dışı dosya `H`, `L`, `F`, `J`, `Y`, `K`, `E`, `W`, `C`, `I`, `Q`, `X`, `N` ve `U` harflerini kullanır.
- Ayrı arayüz dosyası iki harfli kodlar kullanır. Bunlar `HZ`, `OL`, `SZ`, `TS`, `RE`, `AD`, `AX`, `ST`, `IC`, `GV`, `MB`, `BY`, `MD`, `TE` ve `KR` kodlarıdır.
- Mobil dosya da iki harfli kodlar kullanır. Bunlar `KP`, `PK`, `OZ`, `GR`, `VR`, `ES`, `CK`, `BL`, `GN`, `OD`, `MG`, `AU` ve `MT` kodlarıdır.

Dört dosya aynı klasörde durmalıdır. Dosyalar birbirine bağlantı verir.

## Kopyalar

- Asıl kopya ajanların ortak kural klasöründedir. Claude ve Codex dosyaları oradan okur.
- `rules ai` klasöründe ve çalışma klasöründe birer kopya vardır.
- frappesetup deposunun `docs/standartlar/` klasöründe de bir kopya vardır.
- İki Frappe uygulama deposunda yalnız Python ve Python dışı dosya durur.
- Kopyalar 21 Kasım 2026 Cumartesi akşamı karşılaştırıldı. Hepsi aynıdır.

Bir dosya değişirse bütün kopyalar yenilenmelidir. Yoksa ajanlar farklı kural okur.

## Doğrulama durumu

Şu denetimler geçti:

- Yapı denetimi dört dosyada geçti. Kodlar sıralıdır. Göndermeler tanımlıdır.
- Türkçe denetimi dört dosyada hata bulmadı. İki uzun liste cümlesi uyarı olarak kaldı.
- Frappe davranışları 15.126.1 ve 16.56.0 sürümlerinin kaynak kodunda okundu.
- Python dışı dosyanın deneyleri geçti. Örneğin YAML okuyucu ve Jinja kaçış deneyleri geçti.
- Ayrı arayüz dosyasının deneyleri geçti. Örneğin Ant Design, TypeScript, Vite ve Sass deneyleri geçti.
- Kitaplık sürümleri 21 Kasım 2026 Cumartesi günü kayıt servisinden okundu.

Şu denetimler yapılmadı:

- Frappe kodu çalıştırılmadı. Çalışan bir Frappe sitesinde deneme yapılmadı.
- Gerçek telefonda ve gerçek Safari'de deneme yapılmadı.
- Ekran okuyucuyla deneme yapılmadı.
- Firefox testi proje sahibinin kalıcı kuralı gereği çalıştırılmadı.
- Projelerin kendi derleme ve testleri çalıştırılmadı.
- Python dosyasının tamamı kaynak kodla baştan sona yeniden karşılaştırılmadı.
- Dosyalar gerçek bir işte ve gerçek okurla denenmedi.

## İlk sorunun cevabı

Proje sahibi ilk Python teslim raporunun doğru olup olmadığını sordu. Claude raporu diskte ve dosyada denetledi.

**Rapor büyük ölçüde doğruydu.** Şu bilgiler diskte doğrulandı:

- dosyanın boyutu ve beş kopyası,
- Codex'in onayı ve saati,
- 6 engelleyici ve 113 önemli bulgu,
- “4,4 KB” uyarısının kaynağı.

**Altı nokta yanlış ya da eksikti:**

1. 74 küçük bulgu raporda anılmamıştı.
2. Karar tablosu Codex'in son değişikliklerinden önce yazılmıştı.
3. “Bir denetçi hiç çalışmadı” sözü tam doğru değildi. Denetçi çalıştı ama hesap sınırına takıldı.
4. 32.768 bayt sınırı proje sahibinin isteği değildi. Sınırı Claude ve Codex koydu.
5. Altı ara notta noktalı virgül ve uzun cümle vardı.
6. Rapordaki bazı bağlantılar kopyalama sırasında bozulmuştu.

**Dosya isteğe büyük ölçüde uygundu.** Bağımsız denetçi isteği 26 ihtiyaca ayırdı. 21 ihtiyaç karşılanıyordu. 5 ihtiyaç kısmen karşılanıyordu. Hiç karşılanmayan ihtiyaç yoktu.

**Üç önemli eksik vardı:**

1. Yeni Python dosyası için yazım kuralı azdı. Örneğin ad, açıklama satırı ve günlük kuralları azdı.
2. Seviyeye göre kapsam net değildi. 84 zorunlu kuraldan yalnız biri seviye etiketi taşıyordu.
3. Kuralları çoğunlukla ajanın kendi raporu denetliyordu.

Düzeltme turu bu eksikleri giderdi. Denetçiye göre iki ihtiyaç yine kısmen karşılanıyordu. Bunlar “öneriler” ve “kapsamı seviyeye göre uygulamak” ihtiyaçlarıdır. Denetçi bu puanı taslak için verdi. Son dosya yeniden puanlanmadı.

## 19 maddelik değerlendirme

Proje sahibi üç dosyayı 19 soruyla değerlendirdi. Claude 5. soruyu üçe ayırdı. Böylece 21 soru oldu. O günkü sonuç şuydu:

- 12 soruda cevap “evet” idi.
- 3 soruda cevap “evet, ama eksiği var” idi.
- 1 soruda cevap “kısmen” idi.
- 4 soruda cevap “önlem var, garanti yok” idi.
- 1 soruda cevap “hayır” idi.

| No | Soru | O günkü cevap | Sonra ne oldu? |
|---|---|---|---|
| 1 | UI dilini etkilemiyor mu? | Büyük ölçüde doğru. Ama dosyalar arayüz kurallarını taşıyordu. | Görsel kurallar çıktı. |
| 2 | Arayüz tamamen ayrı mı olacak? | Hayır. Dosyalar bunu söylemiyordu. | Karar dosyaların girişine yazıldı. |
| 3 | Mimari yaklaşımı karşılıyor mu? | Evet. | Değişmedi. |
| 4 | Mühendislik yaklaşımını karşılıyor mu? | Evet. | Değişmedi. |
| 5a | Performans sorunu çıkmaz mı? | Garanti yok, risk azalır. | Değişmedi. |
| 5b | Güvenlik sorunu çıkmaz mı? | Garanti yok, risk azalır. Sunucu güvenliği dosyaların dışındadır. | Değişmedi. |
| 5c | Sürdürülebilir mi? | Evet, proje kaydı tutulursa. | Proje kaydı hâlâ yok. |
| 6 | Vibecoding sorunlarına önlem var mı? | Evet. | Değişmedi. |
| 7 | Oracle problem yaşanmaz mı? | Önlem var, garanti yok. | Değişmedi. |
| 8 | OOP ve MVC sorunları yaşanmaz mı? | Önlem var, garanti yok. | Değişmedi. |
| 9 | Her şey önce modüler monolit mi? | Evet, fiilen. | Planlama sırası kurala yazıldı. |
| 10 | Bütünsel ilişki karşılanıyor mu? | Evet. | Değişmedi. |
| 11 | Düşük bağımlılık karşılanıyor mu? | Evet. | Modül sınırı denetimi zorunlu oldu. |
| 12 | Önce test karşılanıyor mu? | Evet. | Değişmedi. |
| 13 | Mobil öncelik karşılanıyor mu? | Evet. | Görsel kısım kalıcı talimatlara kaldı. |
| 14 | Mobil uygulamanın arka ucu planlı mı? | Kısmen. | `mobile.md` yazıldı. |
| 15 | Boşluk analizi yapılacak mı? | Evet. | Değişmedi. |
| 16 | SOLID denetleniyor mu? | Evet, ama araçla değil. | Modül sınırı denetimi zorunlu oldu. |
| 17 | Olgunluk seviyesi karşılanıyor mu? | Evet, üç eksikle. | Enterprise cümlesi düzeldi. Proje kaydı hâlâ yok. |
| 18 | Yeni teknoloji öncesi uyum kontrolü var mı? | Evet. | Değişmedi. |
| 19 | İkinci teknoloji yasak mı? | Evet. | Değişmedi. |

Oracle problem, testin doğru sonucu nereden bileceği sorusudur. Dosyalarda doğru sonucun kaynağı proje sahibinin onayıdır.

Claude son soruya şöyle cevap verdi. Dosyalar güvenli ve sürdürülebilir geliştirmeyi kolaylaştırır. Ama tek başına garanti etmez. Beş neden var:

1. Yazılı kural yaptırım değildir. Ajan bir kuralı atlayabilir.
2. Projelerde proje kaydı yok.
3. Dosyalar gerçek bir işte denenmedi.
4. Sunucu güvenliği bu dosyaların dışındadır.
5. Seviye ve sınırlar proje sahibinin kararını ister.

## Dosyalar nasıl hazırlandı?

Dört dosya aynı yolla hazırlandı:

1. Claude ve Codex aynı isteği aldı. İkisi ayrı taslak yazdı.
2. Claude iki taslağı birleştirdi.
3. Codex birleşik dosyayı inceledi ve düzeltti.
4. Bağımsız denetçiler dosyayı inceledi. Denetçi, metni yazmayan ayrı bir yardımcı modeldir.
5. Claude bulguları işledi. Teknik iddialar Frappe kaynak kodunda doğrulandı.
6. Codex son metni onayladı. Mobil çalışmada Gemini de onay verdi.
7. Dosyalar kopya yerlerine kondu.

Mobil dosya daha geniş bir yolla yazıldı:

- Claude, Codex ve Gemini görüşlerini önce bağımsız yazdı.
- Claude'un dört yardımcısı araştırma yaptı. Konular veri, mağaza, giriş, Huawei ve bildirimdi.
- Bir yardımcı frappesetup sitesini özetledi.
- Codex ve Gemini on üç turda metni inceledi.
- Dört bağımsız denetim yapıldı.

| Denetim | Engelleyici | Önemli | Küçük |
|---|---:|---:|---:|
| 1. İsteğe uygunluk | 1 | 11 | 15 |
| 2. Teknik doğruluk | 2 | 12 | rapor içinde |
| 3. Okur ve ajan | 4 | 31 | 24 |
| 4. Son metin | 0 | 2 | 14 |

Engelleyici yedi bulgunun hepsi metne işlendi. Dördüncü denetim engelleyici bulgu bulmadı. Dördüncü denetimin iki önemli bulgusu da işlendi.

Proje sahibinin açık cevabı hiçbir turda değiştirilmedi. Bir model cevabı daraltınca öteki model ya da denetçi itiraz etti.

Bir model haftalık kullanım sınırına takıldı. İş başka bir Claude modeliyle sürdü.

## Bir kural dosyası nasıl değiştirilir?

1. Değişikliği bir betiğe yazın.
2. Betiğe eski cümleyi, yeni cümleyi ve nedeni yazın.
3. Betiği son onaylı kopyaya uygulayın.
4. Boyutu `wc -c` komutuyla ölçün.
5. Sınırı aşmayın. Gerekirse sınır artışını proje sahibine sorun.
6. Kodları yeniden numaralamayın.
7. Çıkan kodu “Kullanımdan kalkan kodlar” satırına yazın.
8. Türkçe denetimini ve yapı denetimini çalıştırın.
9. Değişikliği Codex'e ve Gemini'ye onaylatın.
10. Son metni proje sahibinin cevaplarına göre denetletin.
11. Bütün kopyaları yenileyin.

Türkçe denetimi şu komutla çalışır:

```bash
node ~/.claude/skills/coding-standards/scripts/yalin-turkce-denetim.mjs --tur talimat dosya.md
```

Bu betik proje sahibinin bilgisayarındadır. Herkese açık depoda yoktur.

## Çok modelli çalışmadan çıkan dersler

1. Modeller proje sahibinin açık cevabını daraltabilir. Örneğin canlı güncelleme ilk yayında kapatılmıştı. Bağımsız denetçi bunu yakaladı.
2. Codex sınıra sığdırmak için onaylı cümleleri yeniden yazabilir. Böyle bir öneri kabul edilmedi. Sınır artışı proje sahibine soruldu.
3. Bir model önceki turda kabul ettiği kararı geri alabilir. Örneğin CSS ve Sass kuralları böyle oldu. Uzlaşılamayan fark proje sahibine soruldu.
4. Onay turundan sonra da bağımsız denetim gerekir. Dördüncü denetçi iki önemli bulgu buldu.
5. Proje sahibinin kısa cevabı kesin karar sayılmamalı. Önce açıklama yapılmalı, sonra ayrıca sorulmalı.
6. Takdir kararlarında modeller çok ayrışabilir. Ortak bir standarda dayanmak gerekir. Örneğin oturum sürelerinde NIST belgesi kullanıldı.
7. Teknik bir engel anlatılırken neden eksik kalmamalı. Ne olduğu, neyin engellendiği, nedeni ve kalan yollar birlikte anlatılmalı.
8. Sayılar dosyadan sayılmalı, bellekten yazılmamalı. Claude bir turda itiraz sayısını bir fazla yazdı.
9. Frappe ile ilgili her iddia kaynak kodda doğrulanmalı. Codex, Claude'un iki iddiasını düzeltti.

## “4,4 KB” uyarısının kaynağı

İlk isteğin ilk maddesi bu uyarıdır. Uyarı başka bir arayüz projesinde çıktı. Uyarı, toplam JavaScript boyutunun sınıra yaklaştığını söylüyordu.

- Uyarıyı Claude 20 Kasım 2026 Cuma günü saat 15.15'te yazdı.
- Sınır, bütün JavaScript dosyalarının sıkıştırılmış toplam boyutudur. Sınır 1.125.000 bayttır.
- Proje sahibi bu sınırı 19 Kasım 2026 Perşembe günü onaylamıştı.

Ayrı arayüz dosyası bu tür uyarıların yazımını kurala bağlar. Ajan önce olanı ve etkisini yazar. Ajan teknik terimi ilk geçtiği yerde açıklar. Ajan kararı kimin vereceğini yazar. Bu kurallar BY-6 ve KR-3'tür.

## Sınırlar neden bu boyutta?

Proje sahibi 36.000 baytın ne demek olduğunu sordu. Claude'un cevabı şuydu:

- 36.000 bayt yaklaşık 4.400 Türkçe kelimedir.
- Bir insan bu metni yaklaşık 25 ile 45 dakikada okur.
- Bir dosya basılınca yaklaşık 9 A4 sayfası tutar.
- Kural dosyasının uzunluğu için uluslararası bir standart yok.
- Codex `AGENTS.md` dosyasını 32.768 bayta kadar okur. Fazlasını sessizce keser.
- Claude Code, `CLAUDE.md` 40.000 karakteri geçince uyarı verir.
- Kural dosyaları bu iki dosya türünden değildir. Ajan onları ihtiyaç olunca açar.
- Yalın dil için uluslararası standart ISO 24495-1'dir. Standart okurla sınamayı da önerir.

Bir kural dosyası `AGENTS.md` olarak kullanılacaksa sınır 32.768 bayt olmalıdır.
