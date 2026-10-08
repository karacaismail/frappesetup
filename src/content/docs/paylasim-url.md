---
title: "URL, paylaşım ve bağlantı önizleme sözleşmesi"
nav: "URL ve paylaşım"
order: 11
---

Kapsam: kiracı paneli (`https://<kiracı>.app.<marka>.com.tr/panel` ya da kiracının özel alan adı) ve kiracı öncesi akışlarla Press ekranlarının çalıştığı `panel.<marka>.com.tr`. Bu host Press sitesinin public alan adıdır; panel → Press istekleri aynı origin'dedir, CORS gerekmez (G-75, G-119). Hedef: insan URL'yi okuyup ekranı anlar ve düzenleyerek gezinir (G-132); paylaşılan bağlantı doğru önizlenir ama yetkisiz hiçbir istemciye kiracı ya da kayıt verisi dönmez (G-130, G-131). Bu dokümantasyon sitesinin ve pazarlama sitesinin SEO'su ayrı konudur; panel yanıtları dizin dışıdır. Fazlar: URL sözleşmesi ve asgari koruma P1, kampanya atfı P2, önizleme kartı ve Paylaş P4.

Bu sayfa tasarım sözleşmesidir; önizleme ucu, URL kuralları ve paylaşım henüz uygulanmadı ve test edilmedi.

## Üç erişim biçimi

| Biçim | Kim görür | Önizleme tarayıcısına dönen | İnsana dönen | Açılan veri | Gereksinim |
| --- | --- | --- | --- | --- | --- |
| Kimlik doğrulamalı sayfa | Bu host'ta oturumu ve okuma izni olan kullanıcı | Oturumsuz istek güvenli önizlemeyi alır; çerezli istemci de yalnız veri içermeyen SPA kabuğunu görür | SPA kabuğu; kayıt API'den, sunucu tarafı yetki denetiminden sonra | İzinli alanlar (DocPerm, User Permission, permlevel); kişiye DocShare ile paylaşım da bu satırdır | G-119, G-121 |
| Güvenli public önizleme | Herkes: önizleme tarayıcısı, girişsiz insan | 200 ve küçük HTML: Open Graph, canonical, noindex | Aynı HTML ve doğrulanmış dönüşle giriş | Ürün adı, ekran türü, statik görsel; kiracı markası yalnız kiracı izniyle | G-130 |
| Yetkili paylaşım bağlantısı | Belirteci olan herkes; varsayılan kapalı (K-29) | Genel önizleme; ilk HTML'de kayıt verisi yok | Giriş gerektirmeyen salt okuma | Tek kayıt, hassas olmayan alan listesi | G-131 |

**noindex erişim kontrolü değildir:** noindex yalnız taranabilen sayfayı arama sonuçlarından çıkarır ([Google](https://developers.google.com/search/docs/crawling-indexing/block-indexing)), robots.txt gizleme aracı değildir ([Google](https://developers.google.com/search/docs/crawling-indexing/robots/intro)); veri yalnız oturum (G-119) ve sunucu tarafı yetkiyle (G-121) korunur.

## WhatsApp akışı

İK yöneticisi bir izin talebini muhasebeciye gönderir. Sınırlar [WhatsApp link önizleme belgesinden](https://developers.facebook.com/documentation/business-messaging/whatsapp/link-previews/); belge önizlemeyi garanti etmez, betik çalıştırma, robots.txt ve önbellek davranışını söylemez (doğrulanacak), bu yüzden akış önizlemesiz de çalışır.

1. **Paylaş → Bağlantıyı kopyala** (mobilde **Paylaş…**) yalın kanonik adresi verir: `https://acme.app.<marka>.com.tr/panel/ik/izin-talebi/HR-LAP-2026-00042`. Meta'nın istediği gibi oturum değişkeni, kullanıcıyı tanıtan parametre ve sayaç yoktur.
2. WhatsApp adresi HTTP GET ile çeker. Sistem User-Agent'a bakmaz: geçerli oturumu olmayan her istek aynı yanıtı alır.
3. Site rota kalıbından genel HTML döner (200): `og:title` "İzin talebi", `og:description`, `og:url`, `og:image`, `og:image:alt`. Etiketler `<head>` içinde ve ilk 300 KB'ta; `og:image` mutlak URL, en az 300 px genişlik, en-boy oranı en çok 4:1, 600 KB altı. Kayıt okunmaz; var olan ve olmayan kayıt için yanıt aynıdır.
4. Muhasebeci dokunur; bu host'ta oturumu yoksa doğrulanmış dönüş adresiyle Keycloak girişine gider ve aynı kayda döner (G-119).
5. SPA kaydı API'den ister; sunucu yetkiyi denetler (G-121); izin varsa kayıt açılır.
6. İzin yoksa ekran "Bu kayıt yok ya da görme izniniz yok" der ve **Erişim iste** sunar; onay DocShare üretir, adımlar denetime yazılır (G-131).

## Önizleme yanıtı kuralları (G-130)

| Kural | Düzey | Sahip | Kabul |
| --- | --- | --- | --- |
| Yanıt yalnız oturuma göre seçilir, User-Agent'a göre değişmez; içerik ürün genelindeki rota kaydından üretilir, kayıt ve kiracının kurulu uygulamaları okunmaz | MUST | Platform ekibi | Farklı User-Agent'larda ve uygulaması kurulu olan/olmayan kiracıda gövde aynı |
| Yoldaki kimlik yalnız kaçışlanarak `og:url` ve canonical'a yansır; ikisi mutlak, slug'sız ve sorgusuzdur, liste rotasında da: oturumsuz yanıt sorgu değerini yansıtmaz. Oturumlu SPA'daki liste canonical'ı ise tanınan filtreleri taşır (aşağıda, G-132) ([OGP](https://ogp.me/)) | MUST | Frontend ekibi | Slug'lı, `?utm_source=x` ve `?durum=acik` taşıyan istekte `og:url` sorgusuz; gövdede kayıt başlığı ve alan değeri yok |
| `og:image` ekran türüne ait statik, oturumsuz erişilebilir HTTPS görseldir; öneri 1200×600 PNG/JPEG; Meta görseli URL'ye göre önbelleklediği için URL içerik özeti taşır ([Meta](https://developers.facebook.com/docs/sharing/webmasters/)) | MUST (WhatsApp sınırları), SHOULD (öneri) | Frontend ekibi | CI görselin boyutunu, oranını ve ağırlığını denetler |
| Başlıklar: `X-Robots-Tag: noindex, nofollow`, `Cache-Control: private, no-store`, `Vary: Cookie`; robots.txt panel yollarını engellemez | MUST | Platform ekibi + Hüseyin Cengiz (nginx) | Başlık testi; oturumlu yanıt hiçbir katmanda oturumsuz isteğe dönmez |
| Kiracı adı ve logosu yalnız kiracı ayarı açıksa görünür; varsayılan ürün markasıdır | MUST | Ürün sahibi + Frontend ekibi | Ayarı kapalı kiracıda host adı dışında kiracı izi yok |
| Önizleme API çağırmaz, satıcı betiği yüklemez, `page_view` üretmez; SPA kabuğu HTML'i de kayıt verisi gömmez | MUST | Frontend ekibi | Ağ kaydı ve kabuk HTML denetimi |
| Dönüş adresi aynı host'ta, `/` ile başlayan, `//`, şema ve ters bölü içermeyen, rota kaydındaki bir yoldur; değilse panel ana sayfası ([OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)); Frappe'nin kendi denetimi (doğrulanacak) | MUST | Platform ekibi | `//kotu.example`, `https://kotu.example`, `/\kotu.example` reddedilir |

## URL sözleşmesi (G-132)

Sahip: Frontend ekibi (rota kaydı, SPA), Platform ekibi (çözümleme, yönlendirme), Hüseyin Cengiz (nginx başlıkları). Yollar panel kökü `/panel` altındadır (G-75).

| Öğe | Kural | Örnek | Düzey |
| --- | --- | --- | --- |
| Kiracı | Kapsam host'tur; kiracı kimliği yola ve sorguya girmez; özel alan adı birincil host olabilir, diğer host'lar ona yönlenir (G-26) | `acme.app.<marka>.com.tr` | MUST |
| Panel host'u | Takım yolu `press_tr`'deki tekil, okunur takım kısa adıyla kurulur; Press Team adı [hash'tir](https://github.com/frappe/press/blob/v0.155.3/press/press/doctype/team/team.json) | `/t/acme/faturalama` | MUST |
| Liste ve kayıt | `/<uygulama>/<belge-türü>` ve `/<uygulama>/<belge-türü>/<kimlik>`; Türkçe, ASCII küçük harf, kısa çizgili okunur kelimeler ([Google](https://developers.google.com/search/docs/crawling-indexing/url-structure)); kimlik Frappe belge adıdır ([`HR-LAP-.YYYY.-`](https://github.com/frappe/hrms/blob/v16.50.0/hrms/hr/doctype/leave_application/leave_application.json)) | `/ik/izin-talebi/HR-LAP-2026-00042` | MUST |
| Okunur slug | İsteğe bağlı, kalıcı kimliğin önünde (`<slug>--<kimlik>`); yalnız kişisel veri içermeyen, URL'ye uygun işaretli başlık alanından; çözümleme kimlikle yapılır | `…/aylik-kapanis--a1b2c3d4e5` | MAY; kişisel veri yasağı MUST |
| Vekil kimlik | Adı kişisel veri olan türlerde URL ve Link filtre değerleri vekil kalıcı kimlik taşır: User adı [e-postadır](https://github.com/frappe/frappe/blob/v16.51.0/frappe/core/doctype/user/user.py#L199-L205), [Employee](https://github.com/frappe/hrms/blob/v16.50.0/hrms/overrides/employee_master.py#L15-L26) "Full Name" adlandırmasında ad soyaddır, Contact | `/ik/calisan/k7m2q9` | MUST |
| Filtre, sıralama, sayfa | Okunur sorgu parametreleri: anahtar Türkçe URL adı ya da meta `fieldname`; `sirala` (`-` azalan), `sayfa`, `gorunum`, `sekme`; tanınmayan parametre yok sayılıp adresten atılır; serbest arama metni URL'ye yazılmaz | `?durum=acik&sirala=-tarih&sayfa=2` | MUST |
| Kanonik | Oturumlu SPA'da mutlak; birincil host + yol + kanonik parametreler; slug'sız; kayıtta parametre yok, listede yalnız tanınan filtreler (sıralı); Paylaş bunu kopyalar. Oturumsuz önizleme yanıtı sorgusuz adresi kullanır (G-130) | `/ik/izin-talebi?durum=acik` | MUST |
| Yönlendirme | Kalıp takma adı herkese 301; yeniden adlandırma ve slug değişimi yalnız oturumlu ve okuma izni olan isteğe 301; oturumsuz istek yönlendirilmez, çünkü kaydın varlığını sızdırır | `/hr/leave-application` → `/ik/izin-talebi` | MUST |
| Derin bağlantı | Adres ekranı geri kurar (tür, kayıt, sekme, filtre, sıralama, sayfa, görünüm); elle yazılan `sayfa=3` çalışır; geçersiz değer varsayılana döner, bildirim verir, adres `replaceState` ile düzelir | `?sayfa=99` → son sayfa ve bildirim | MUST |
| Gizli değer | Yol ve sorguda parola, belirteç, API anahtarı, oturum kimliği, e-posta, telefon, TCKN/VKN yok ([OWASP](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)); istisna yalnız süreli yetenek bağlantıları (davet, K-29) | — | MUST |
| Referrer-Policy | `strict-origin-when-cross-origin` açıkça gönderilir ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): belirtilmezse de varsayılan budur); belirteçli sayfada `no-referrer` | — | MUST |

## Paylaş düğmesi (G-131)

Sahip: Frontend ekibi (düğme), Platform ekibi (DocShare, belirteç, denetim); K-29 kararı Ürün sahibi ve Hukuk'tadır.

| Seçenek | Kural | Düzey |
| --- | --- | --- |
| Bağlantıyı kopyala | Kanonik adresi panoya yazar ve `aria-live` ile duyurur; pano yoksa adres seçili metin alanında görünür; alıcı kendi yetkisiyle görür | MUST |
| Paylaş… | `navigator.share({ title, url })` yalnız tıklamayla ve HTTPS'te çalışır ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share)); API yoksa ya da hata dönerse kopyalamaya düşer, iptal sessizdir; `Permissions-Policy` `web-share`'i kapatmaz (G-75); `title` ekran türü ve ürün adıdır, kayıt başlığı ya da kişi adı içermez | SHOULD |
| Kişiye erişim ver | Frappe [DocShare](https://github.com/frappe/frappe/blob/v16.51.0/frappe/core/doctype/docshare/docshare.json) (`read`, `write`, `share`, `submit`); paylaşanın `share` izni gerekir; bildirim ve denetim kaydı | MUST |
| Erişim iste | Yetkisiz ekran kayıt yok ve yetki yok durumunda aynıdır; istek kayıt sahibine ve `share` izni olanlara gider, kullanıcı başına sınırlıdır; onay DocShare üretir | MUST |
| Bağlantıya sahip herkes | Varsayılan kapalı (K-29). Açılırsa tek kayıt, salt okuma, süreli, iptal edilebilir (410), denetimli, hassas alansız; sayfa `no-referrer` ve noindex ile, satıcı betiği olmadan sunulur; belirteç oturum ya da izleme parametresi değildir. Seçenek: belirteç URL parçasında (`#`) taşınırsa sunucuya ve Referer'a gitmez ([MDN](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment)) | MUST (açıksa) |

## Kampanya atıf parametreleri (G-133)

Varsayılan sözleşmedir. Tanınan parametreler: `utm_*` (`utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`), `gclid`, `gbraid`, `wbraid`, `fbclid`, `yclid`, `msclkid`, `ttclid`, `li_fat_id`; liste yapılandırmadır. Sahip: Frontend ekibi + Platform ekibi; saklama dayanağı Hukuk (K-28).

| Adım | Kural | Düzey | Gereksinim |
| --- | --- | --- | --- |
| 1. Yakala | Giriş noktasında (public site, `panel.` kayıt ve checkout) ilk istekte okunur; uzunluk ve karakter denetiminden geçer; e-posta, telefon ya da TCKN desenli değer atılır. Kiracı uygulama panelinde yakalanmaz ve saklanmaz, yalnız 4. adımdaki gibi adresten temizlenir | MUST | G-133 |
| 2. Koru | Giriş ve kayıt yönlendirmelerinde OIDC `state` içinde, doğrudan ya da sunucu kaydına işaret eden rastgele anahtarla taşınır | MUST | G-133, G-119 |
| 3. Sakla | İlk ve son temas sunucu tarafında (Account Request, ardından Team) zaman ve giriş rota şablonuyla birinci taraf atıf kaydında tutulur; kampanya → oturum → izinli kullanıcı/işlem bağı bu kayıttan kurulur, satıcıya aktarım gerekmez ([Ölçüm](/frappesetup/olcum-gozlem/)); cihazda saklama yalnız rızayla | MUST | G-133, G-134, K-28 |
| 4. Temizle | Yakalamadan sonra `history.replaceState` ile adres çubuğundan silinir; adapterlar değeri yakalanan kayıttan alır (satıcı desteği adapter başına doğrulanacak) | MUST | G-133, G-134 |
| 5. Dışarıda tut | Kanonik adrese, `og:url`'e, Paylaş bağlantısına ve ürün içi bağlantılara girmez; analitiğe giden adres rota şablonudur (`/ik/izin-talebi/:kimlik`), belirteç, OIDC `code`/`state` ve arama metni ayıklanır | MUST | G-133, G-134 |
| 6. Yetki vermez | İzleme parametresi hiçbir zaman yetki ya da oturum vermez; yetki ve paylaşım belirteci izleme parametresi gibi taşınmaz, ölçüme gitmez | MUST | G-131, G-133 |

## Kabul testleri

- **Önizleme:** oturumsuz `curl -A "WhatsApp/2.23.20.0 A"` ile var olan ve olmayan kayıt 200 ve kimlik dışında aynı gövde döner; kayıt başlığı, kişi adı, alan değeri yoktur; `X-Robots-Tag`, `Cache-Control` ve `Vary` başlıkları vardır; etiketler `<head>` içinde, ilk 300 KB'tadır; görsel sınırları sağlanır.
- **Gerçek cihaz:** iOS ve Android WhatsApp'ta önizleme sonucu emülasyondan ayrı `pass/fail/not_run` yazılır; [Sharing Debugger](https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/) çıktısı kayda geçer; hiçbir durumda kayıt verisi görünmez.
- **Giriş dönüşü:** oturumsuz tıklama girişten sonra aynı kayda döner; açık yönlendirme denemeleri panel ana sayfasına düşer.
- **Yetki ve paylaşım:** yetkisiz kullanıcı ekranda ve API'de veri almaz; Erişim iste → DocShare → erişim zinciri çalışır; iptal edilen herkese açık bağlantı 410 döner; olaylar denetimdedir.
- **URL:** rota sözleşme testleri geçer; `sayfa=3` düzenlemesi çalışır; geçersiz değer bildirim verir; tanınmayan parametre atılır; slug'lı ve slug'sız adres aynı kaydı açar; yeniden adlandırma yalnız oturumlu ve izinli istekte yönlenir.
- **Atıf:** `?utm_source=test&gclid=abc` ile kayıt → Keycloak → checkout sonunda Account Request ve Team'de ilk ve son temas doludur; adres çubuğu, canonical, `og:url` ve Paylaş bağlantısı temizdir; analitik adresi şablondur.
- **Kişisel veri taraması:** E2E boyunca toplanan URL'lerde (adres çubuğu, ağ istekleri, örnek nginx günlüğü) e-posta, telefon, TCKN/VKN deseni sıfırdır.
