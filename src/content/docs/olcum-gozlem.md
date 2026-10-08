---
title: "Ölçüm adapterları, rıza kapısı ve gözlemlenebilirlik"
nav: "Ölçüm ve gözlem"
order: 12
---

Bu sayfa tasarım sözleşmesidir; adapterlar ve rıza kapısı henüz uygulanmadı ve test edilmedi.

Google Tag Manager (GTM), Google Analytics 4 (GA4), Google Ads, Yandex Metrica, Meta Pixel, Criteo, AdRoll ve Metabase platformda varsayılan olarak hazır ve **etkindir**: kod, kayıt ve olay eşlemesi her sürümle gelir ve kapatılmaz. **Etkin olmak veri aktarmak değildir:** satıcıya ilk istek ancak yapılandırma ve yetki, ilgili amaç için rıza veya kayıtlı hukuki dayanak ve hassas olmayan yüzey birlikte sağlanınca çıkar. Plan: adapter çerçevesi ve yedi tarayıcı adapteri P2 (G-134, G-135), Metabase P6 (G-136), birinci taraf RUM P1 (G-149), log, metrik ve iz P0 (G-113). Bu çalışma gerçek bir analitik veya reklam hesabı bağlamaz, veri aktarmaz ve bunlara yetki vermez; testler sahte uç noktalarla koşar. Kampanya parametrelerinin yakalanması, korunması, temizlenmesi ve kanonik adres kuralı [URL ve paylaşım](/frappesetup/paylasim-url/) sayfasındadır (G-133).

## Roller: kim neyi ölçer

| Rol | Araç | Veri | Dayanak ve rıza | Sahip | Gereksinim |
| --- | --- | --- | --- | --- | --- |
| Pazarlama analitiği ve reklam ölçümü | GTM, GA4, Google Ads, Yandex Metrica, Meta Pixel, Criteo, AdRoll | Normalleştirilmiş olay, rota şablonu, kampanya atfı; gerçek kişisel veri ve kimlik doğrulama/paylaşım belirteci yok; izinliyse yalnız satıcı kapsamlı takma kimlik | Amaç ve gerektiğinde satıcı bazında rıza; yurt dışı aktarım dayanağı | Frontend ekibi; platform hesapları Ürün sahibi; rıza metni Hukuk | G-134, G-135, G-133 |
| Ürün analitiği | G-134 olay yolunun birinci taraf toplayıcısı (kendi sunucumuz) | Etkinleşme hunisi; yardım, tur ve keşif olayları; belge değeri yok | Takma kimliksiz toplu sayım Kriter B adayıdır; kullanıcı/oturum sürekliliği takma kimlikle kişisel veridir, anonim sayılmaz ve dayanak/rıza kapısından geçer (K-27) | Platform ekibi + Frontend ekibi | G-134, G-139, G-140 |
| İş zekâsı | Metabase | MRR, churn, tahsilat, AI kredi tüketimi, destek metrikleri | Etiket değildir; tarayıcı rızası yerine operatör rolü ve veri en aza indirme | Hüseyin Cengiz (kurulum) + Platform ekibi + Finans/Muhasebe | G-136 |
| Log, metrik, iz | Monitor Server (Prometheus/Grafana), Log Server (Elasticsearch/Kibana), GlitchTip | Teknik olay, süre, hata; kişisel veri `before_send` ile temizlenir. Korelasyon kimliği `X-Request-Id` yalnız bu roldedir, pazarlama araçlarına gönderilmez | İşletme ve güvenlik; saklama G-52 | Hüseyin Cengiz | G-113 |
| Birinci taraf RUM | web-vitals → kendi toplayıcımız → Grafana (p75/p95) | Web Vitals, rota şablonu, örnekleme; üçüncü taraf yok | Kriter B koşulları; hassas ekranda çalışan tek ölçüm | Frontend ekibi + Platform ekibi | G-149 |
| Denetim kaydı | Version, Activity Log, AI Action Log, Access Log; günlük operatör raporu | Kim, neyi, ne zaman yaptı | Saklama matrisi (SA-36); ölçüm ve pazarlamada kullanılmaz | Platform ekibi | G-64, SA-26 |

## Etkin ile veri aktarımı arasındaki kapı

Kapılar sırayla değerlendirilir; biri kapalıysa satıcı betiği indirilmez. Bu düzen Google'ın temel Consent Mode'una denktir: temel modda etiketler rıza ekranıyla etkileşime kadar yüklenmez, gelişmiş modda baştan yüklenir ve rıza yokken çerezsiz ölçüm gönderir ([Consent Mode](https://developers.google.com/tag-platform/security/concepts/consent-mode)). K-27 gelişmiş modu seçerse G-134'ün "rıza yok → satıcıya istek yok" kabulü yeniden yazılır.

| Kapı | Koşul | Düzey | Sahip | Kabul (ağ kanıtı) |
| --- | --- | --- | --- | --- |
| 1. Platformda etkin | Adapter kodu, kaydı ve olay eşlemesi her sürümde açıktır; olay şeması `window.dataLayer`'da akar; satıcı betiği indirilmez | MUST | Frontend ekibi | Yapılandırma yokken `dataLayer` olay içerir, satıcı origin'lerine istek sıfırdır |
| 2. Yapılandırma ve yetki | Hesap kimliği kiracı ayarında (yalnız kiracı admini) veya platform ayarında (Ürün sahibi) durur; depoda ve derleme çıktısında bulunmaz; değişiklik denetime yazılır (G-64). Satıcı G-116 veri envanterindedir; yurt dışı aktarım için uygun güvence gerekir ([KVKK](https://www.kvkk.gov.tr/Icerik/2053/Yurtdisina-Aktarim)); sürekli piksel akışının arızi aktarım sayılmayacağı Hukuk teyidindedir. Kiracı hesabında dayanak kiracı sözleşmesine bağlanır | MUST | Ürün sahibi, kiracı admini; Hukuk | Kimlik boşken adapter yüklenmez; kimlik değişikliği Version kaydında |
| 3. Rıza veya hukuki dayanak | Amaç bazındadır (analitik, reklam, oturum kaydı); Criteo ayrıca satıcıya özgü onay ister. [KVKK Çerez Rehberi](https://www.kvkk.gov.tr/SharedFolderServer/CMSFiles/fb193dbb-b159-4221-8a7b-3addc083d33f.pdf) (Temmuz 2025): davranışsal reklam çerezleri açık rıza ister; yalnız anonim istatistik üreten, çapraz takipte kullanılmayan birinci taraf analitik Kriter B kapsamında değerlendirilebilir; "Kabul et", "Reddet" ve "Tercihler" düğmelerinin renk, boyut ve puntoda eşit sunulması iyi uygulamadır. Google etiketlerinde her sayfada ölçüm komutlarından önce reddedilmiş varsayılan (`gtag('consent','default',…)`), kullanıcı seçince hemen `update` çalışır ([Google](https://developers.google.com/tag-platform/security/guides/consent)). Kayıt SA-36; nihai model K-27, atıf saklama K-28 | MUST; eşit düğmeler SHOULD | Hukuk (metin); Frontend ekibi (rıza arayüzü) | "Reddet" sonrası istek yok; "Kabul et" sonrası yalnız onaylanan amaç ve satıcının adapteri yüklenir |
| 4. Yüzey | Rotanın yüzey sınıfı adaptere izin verir; hassas rota hiçbirine izin vermez | MUST | App ekibi (sınıf), Frontend ekibi | Hassas rotada yalnız birinci taraf RUM isteği |
| Aktarım | Dört kapı geçince adapter dinamik yüklenir ve yalnız o andan sonraki olaylar gider; rıza öncesi olaylar sonradan gönderilmez (öneri) | MUST; geçmiş olay kuralı SHOULD | Frontend ekibi | İlk satıcı isteği rıza kaydından sonra |

## Yüzey sınıfları

Sınıf, AppModule rota kaydında (G-103) bildirilir; sınıfı olmayan rota hassas sayılır (MUST; sınıfı App ekibi bildirir, Frontend ekibi uygular). Kabul: her yüzeyde ağ kaydı izinli adapter listesiyle eşleşir.

| Yüzey | Örnek | İzinli adapterlar (kapılardan sonra) | Oturum kaydı | Not |
| --- | --- | --- | --- | --- |
| Public pazarlama | Pazarlama sitesi (platform hesabı); kiracının Webshop vitrini (yalnız kiracı hesabı, P5) | Tümü | Açılabilir; giriş alanları maskeli | Platform etiketi kiracı vitrininde, kiracı etiketi pazarlama sitesinde çalışmaz |
| Kayıt ve ödeme hunisi | `panel.<marka>.com.tr`, Press sitesinin kendi alan adı: kayıt, deneme, plan seçimi, checkout | Tümü, yalnız platform hesabıyla | Checkout ve ödeme adımında kapalı | Faturalama, ödeme yöntemi ve takım ekranları hassastır |
| Uygulama paneli | `<kiracı>.app.<marka>.com.tr`, özel alan adı | Birinci taraf ürün analitiği ve RUM; satıcı adapterı kiracı yapılandırmasıyla (kiracı hesabı) ya da kiracı onayıyla (platform hesabı); kiracının GTM kapsayıcısı yüklenmez (keyfi etiket; öneri) | Varsayılan kapalı; kiracı açarsa giriş alanları maskeli | Satıcı betiği aynı origin'de DOM'a erişir; belgenin CSP'si yalnız etkin adapter origin'lerini içerir (SEC-05, G-145) |
| Hassas | İK ve bordro, finans ve faturalama, destek oturumu (SA-42), giriş ve hesap güvenliği (`id.`), operatör yüzeyleri (`ops.`, `press.`) | Hiçbiri; yalnız birinci taraf RUM | Kapalı | Tur ve yardım ölçümü burada istemci olayından değil `platform_core` ilerleme kayıtlarından raporlanır |

## Olay şeması, dataLayer ve tekilleştirme

| Konu | Kural | Düzey | Sahip | Kabul |
| --- | --- | --- | --- | --- |
| Şema | Olaylar: `page_view`, `sign_up`, `trial_started`, `app_activated`, `purchase`; yardım, tur ve keşif için `help_opened`, `tour_started`, `tour_completed`, `tour_dismissed`, `suggestion_shown`, `suggestion_accepted`, `suggestion_dismissed`. Zorunlu alanlar: `event`, `event_id`, `schema_version`, `route` (G-132 kalıbı, ör. `/ik/izin-talebi/:kimlik`), `surface`, `consent` (amaç bazında durum ve rıza metni sürümü), `ts`. Kiracı kapsamı birinci taraf toplayıcıda rastgele `scope_id` ile tutulur ve satıcıya gitmez; satıcıya yalnız aşağıdaki takma kimlik gidebilir (G-134, G-137, G-139, G-140) | MUST | Frontend ekibi + Platform ekibi | CI'da şema doğrulaması; satıcı yükünde `scope_id` yok |
| Yasak alanlar | E-posta, telefon, ad soyad, TCKN/VKN, gerçek kullanıcı kimliği (User adı, e-posta, `sub`) ve bunlardan türetilmiş her karma, belge adı ve değeri, arama metni, `X-Request-Id`, paylaşım ve davet belirteci, OIDC `code` ve `state`. Satıcının otomatik form ve kişisel veri toplama özellikleri kapalıdır (ayar adları adapter başına doğrulanacak). `page_location` origin ile rota şablonundan oluşur, `page_title` kayıt başlığı değil ekran türüdür; Google Analytics'e URL yolu ve parametreleri dahil kişisel veri gönderilmez ([politika](https://support.google.com/analytics/answer/6366371)) (G-134, G-133) | MUST | Frontend ekibi | Satıcı isteklerinde desen taraması sıfır eşleşme |
| dataLayer ve rota | `window.dataLayer` GTM parçacığından önce tanımlanır, olaylar `dataLayer.push({event: …})` ile girer ([GTM](https://developers.google.com/tag-platform/tag-manager/datalayer)). Yönlendiricinin gezinme tamamlandı noktasındaki tek emitter gezinme başına bir `page_view` yazar ve gezinme kimliğine göre idempotenttir; render, efekt tekrarı, `replaceState` temizliği ve filtre, sıralama ya da sayfa değişimi `page_view` üretmez (G-134) | MUST | Frontend ekibi | Beş gezinme, beş `page_view` |
| GA4 tek kaynak | Enhanced Measurement'ın tarayıcı geçmişi seçeneği ile elle `page_view` hiçbir zaman birlikte açık değildir; platform elle `page_view` seçer: `send_page_view: false` ve geçmiş seçeneği kapalı, çünkü bu seçenek `send_page_view: false` olsa da `page_view` gönderir ([GA4](https://developers.google.com/analytics/devguides/collection/ga4/views?client_type=gtag)); GTM ile kullanımda GA4'ün otomatik geçmiş izlemesi açılmaz, yoksa sayfa görüntüleme iki kez sayılır ([SPA](https://developers.google.com/analytics/devguides/collection/ga4/single-page-applications)) (G-135) | MUST | Frontend ekibi | Yapılandırma denetimi; çift `page_view` yok |
| Atıf | Kampanya değerleri G-133 akışıyla gelir; adapter değeri adresten değil yakalanan kayıttan alır; tıklama kimliğinde harf dönüşümü yapılmaz, GBRAID büyük/küçük harfe duyarlıdır ([Google Ads](https://support.google.com/google-ads/answer/16297842)) | MUST | Frontend ekibi + Platform ekibi | Yakalanan ve aktarılan değer aynı |
| `event_id` | Her olayda UUID; sunucuda doğan dönüşümlerde (`sign_up`, `trial_started`, `app_activated`, `purchase`) kimliği sunucu üretir ve istemciye bir kez verir, sayfa yenilemesi olayı tekrarlamaz; sunucu olayları Platform Event kuyruğundan aynı anahtarla idempotent gider (G-134) | MUST | Platform ekibi + Frontend ekibi | Yenileme ve yeniden deneme ikinci olay üretmez |
| Satıcı tekilleştirmesi | Meta: Pixel `eventID` ile Conversions API `event_id` ve olay adı aynıdır, eşleşme penceresi 48 saattir ([Meta](https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events)). GA4: `purchase` olayında `transaction_id` Press Invoice adıdır; GA4 aynı kimlikli satın almaları yalnız web akışında tekilleştirir, kimlik kullanıcılar arasında paylaşılmaz ([GA4](https://support.google.com/analytics/answer/12313109)) (G-135) | MUST | Frontend ekibi + Platform ekibi | İstemci ve sunucu olayında kimlik aynı |

## Takma kimlik ve birinci taraf atıf

Kullanıcı ve kampanya takibi yalnız bu kurallarla yapılır; takma kimlikli veri kişisel veridir ve raporlarda anonim diye sunulmaz. Sahip: Platform ekibi + Frontend ekibi; dayanak, saklama ve rotasyon süresi Hukuk (K-27, K-28).

| Kural | Düzey | Kabul |
| --- | --- | --- |
| Takma kimlik rastgeledir (CSPRNG) ve (kiracı, amaç, satıcı) üçlüsü başına ayrıdır; e-posta, telefon, TCKN/VKN, User adı veya `sub` değerinden karma ya da türetme yapılmaz (öneri olarak bile) | MUST | Kod incelemesi ve test: takma kimlik üreticisi yalnız rastgele kaynak kullanır |
| Kullanıcı ve oturum sürekliliği: rıza sonrası birinci taraf oturum kimliği; girişten sonra eşleme (kullanıcı, kiracı, amaç, satıcı, oluşturma, rotasyon) yalnız birinci taraf sunucuda tutulur, satıcıya yalnız takma kimlik gider | MUST | Satıcı yükünde kullanıcı kimliği yok; takma kimlik kiracı ve satıcıya göre farklı |
| Rotasyon ve silme: rıza geri alınınca, kiracı değişince ve Hukuk'un belirlediği sürede yeni takma kimlik üretilir; hesap silme, rıza geri alma veya KVKK talebinde eşleme silinir, satıcı silme arayüzü varsa çağrılır (adapter başına doğrulanacak) | MUST | Geri alma sonrası eski takma kimlikle istek yok; silme kaydı denetimde |
| Kiracılar arası ilişkilendirme yoktur: aynı kişi farklı kiracılarda farklı takma kimlik taşır; platform düzeyinde birleşik kullanıcı kimliği satıcıya gitmez | MUST | İki kiracıda aynı kullanıcının takma kimlikleri farklı |
| Birinci taraf atıf varsayılandır: kampanya parametresi (G-133) → birinci taraf atıf kaydı (oturum) → kayıt/girişte izinli kullanıcı ve Team → dönüşüm (deneme, satın alma) aynı kayıtta; raporlama Metabase'de (G-136). Satıcıya dönüşüm aktarımı gerekmez; yalnız reklam optimizasyonu için rıza ve yapılandırmayla, tıklama kimliği ve takma kimlikle yapılır | MUST; satıcı aktarımı MAY | Rıza yokken atıf raporu birinci taraf kayıttan üretilir, satıcı isteği yok |
| Kapsam: bu karar `panel.` kayıt/ödeme hunisi ve kiracı Webshop vitrini içindir; kiracı uygulama panelindeki iş ekranlarında kampanya atfı ve satıcı takma kimliği yoktur | MUST | Uygulama paneli ağ kaydında satıcı takma kimliği yok |

## Adapter matrisi

Her adapter G-135 sözleşmesini bildirir: yapılandırma anahtarları, satıcı origin listesi (ağ testi ve CSP bunu kullanır), izinli yüzeyler, rıza amacı, olay eşlemesi, SPA yöntemi, tekilleştirme, maskeleme ve geri alma. Sahip: Frontend ekibi; kabul: her adapter için rıza, SPA, tekilleştirme ve geri alma sözleşme testi.

| Adapter | Varsayılan | Rıza amacı | SPA yöntemi | Tekilleştirme | Geri alma |
| --- | --- | --- | --- | --- | --- |
| GTM | Etkin; aktarım kapıda | Kapsayıcı en az bir Google amacı onaylanınca yüklenir; içinde yalnız Google etiketleri (öneri) | Etiketler `dataLayer` olaylarıyla tetiklenir | Tek olay kaynağı `dataLayer` | Consent Mode `update`, ilgili türler `denied` |
| GA4 | Etkin; aktarım kapıda | Analitik (`analytics_storage`) | Elle `page_view` (yukarıda) | `transaction_id`, `event_id` parametresi | Consent Mode `update` |
| Google Ads | Etkin; aktarım kapıda | Reklam (`ad_storage`, `ad_user_data`, `ad_personalization`) | Dönüşüm olayları (`sign_up`, `purchase`) `dataLayer`'dan | İşlem kimliği (Ads davranışı doğrulanacak) | Consent Mode `update` |
| Yandex Metrica | Etkin; aktarım kapıda | Analitik; Session Replay ayrı amaç | `defer: true` otomatik görüntüleme gönderimini kapatır ([SPA](https://yandex.com/support/metrica/en/code/counter-spa-setup.html)); rota başına `ym(id,'hit',url,{referer})` ([hit](https://yandex.com/support/metrica/en/objects/hit.html)) | Gezinme başına tek `hit` | Geri alma çağrısı (doğrulanacak); gönderim durur, sayfa yenilenir |
| Meta Pixel | Etkin; aktarım kapıda | Reklam | `fbq('track','PageView')` yalnız emitter'dan, ilk yükleme dahil rota başına bir kez; History API değişiminde kendiliğinden gönderim (doğrulanacak) varsa kapatılır | `eventID` = Conversions API `event_id` | `fbq('consent','revoke')` ([Meta](https://developers.facebook.com/docs/meta-pixel/implementation/gdpr)) |
| Criteo OneTag | Etkin; aktarım kapıda | Reklam; Criteo'ya özgü onay ([Criteo](https://help.criteo.com/kb/guide/en/transparency-and-consent-framework-bbFLejr6XZ/Steps/1842462)) | Rota başına OneTag olayı: `viewHome`, `viewItem`, `viewBasket`, `trackTransaction` ([OneTag](https://developers.criteo.com/retailer-integration/docs/onetag)); SPA çağrı biçimi (doğrulanacak) | Sipariş kimliği (doğrulanacak) | Gönderim durur, sayfa yenilenir; rıza API'si (doğrulanacak) |
| AdRoll | Etkin; aktarım kapıda | Reklam; piksel ziyaretçinin onay eyleminden sonra ([AdRoll](https://help.adroll.com/hc/en-us/articles/360003797191)) | Rota başına `adroll.track("pageView")` ([SPA](https://help.adroll.com/hc/en-us/articles/212014288)) | Gezinme başına tek çağrı | Gönderim durur, sayfa yenilenir; rıza API'si (doğrulanacak) |
| Genişleme (ör. Microsoft Clarity, LinkedIn Insight, TikTok Pixel) | Sözleşme testiyle eklenince etkin; aktarım kapıda | Adapter bildirir | Adapter bildirir | `event_id` | Adapter bildirir; oturum kaydı yapan adapter Session Replay kurallarına uyar |

## Rıza geri alma sırası

1. Olay yolu geri alınan amacın kuyruğunu hemen kapatır ve gönderilmemiş olayları siler (Frontend ekibi).
2. Yüklü satıcının rıza API'si çağrılır: Google'da `gtag('consent','update',…)` ilgili türleri `denied` yapar (Google bu komutu `granted`'dan `denied`'a geçiş için de tanımlar), Meta'da `fbq('consent','revoke')`; diğer satıcılarda çağrı doğrulanana kadar yalnız durdurma uygulanır (Frontend ekibi).
3. Platformun bu alan adında satıcı adına yazdığı çerez ve depolama anahtarları adapterin bildirdiği listeyle silinir; satıcının kendi alan adındaki çerezi tarayıcı bize sildirmediği için 2. adım atlanmaz. Yüklü betik belgeden kaldırılamaz: sayfa yeniden yüklenir, betik bir daha indirilmez (Frontend ekibi).
4. Değişiklik SA-36 Legal Document Acceptance kaydına rıza metni sürümü ve zamanla yazılır; anonim ziyaretçide rastgele rıza kimliği kullanılır (öneri; Platform ekibi + Hukuk).
5. Sunucu tarafı olaylar (ör. Conversions API) gönderimden hemen önce güncel rızayı okur; rıza geri alınmışsa olay iptal edilir (Platform ekibi).

## Kiracı izolasyonu ve hassas ekran maskeleme

| Kural | Düzey | Sahip | Kabul |
| --- | --- | --- | --- |
| Adapter yapılandırması belgenin host'undan çözülür; kiracı A'nın hesap kimlikleri B'nin belgesinde yüklenmez; olay ve kimlik kiracılar arasında taşınmaz (host'a bağlı oturum, G-119) | MUST | Platform ekibi + Frontend ekibi | A'nın kimliğiyle B'de istek sıfır |
| Platform hesabının etiketi kiracı uygulama ekranında kiracı onayı (SA-36 kaydı) olmadan çalışmaz; kiracı etiketi pazarlama sitesinde ve `panel.` host'unda çalışmaz | MUST | Frontend ekibi | Yüzey başına ağ kaydı |
| Hassas rotada satıcı ve oturum kaydı yoktur. SPA'ya yüklenen satıcı betiği rota değişince kaldırılamadığı için satıcı yüklü belgeden hassas rotaya geçiş tam sayfa yüklemeyle satıcısız belgeye yapılır (yöntem öneri) | MUST | Frontend ekibi + App ekibi | Hassas rotada `gtag`, `ym` ve `fbq` tanımsız |
| Oturum kaydı açık ekranda her giriş alanı `ym-disable-keys` (değer yıldızla kaydedilir), kişisel veri gösteren öğe `ym-hide-content` (hiç kaydedilmez) sınıfını ortak bileşenden alır ([Yandex](https://yandex.com/support/metrica/en/webvisor/settings.html)) | MUST | Frontend ekibi | Input, Select ve Textarea bileşen testi |
| Frappe Pulse telemetrisi aynı kapıya bağlıdır. version-16 (`6b450a1`) kodunda Pulse, site yapılandırmasında `pulse_api_key` yoksa göndermez; varsa `pulse_force_enabled` ile ya da geliştirici kipi dışında System Settings `enable_telemetry` ile açılır ([kod](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/utils/telemetry/pulse/client.py#L10-L20)); Form Tour durum güncellemesi de bu yolu çağırır ([Yardım ve tur](/frappesetup/yardim-tur/)). G-52'deki `enable_telemetry=0` tek başına yetmez; kiracı ve operasyon sitelerinde `pulse_api_key` tanımlanmaz. Press'in bu anahtarı site yapılandırmasına yazıp yazmadığı (doğrulanacak) | MUST | Hüseyin Cengiz + Platform ekibi | Site yapılandırmasında `pulse_api_key` yok; `boot_config` yanıtı `{"enabled": false}` |

## Metabase

Metabase etiket değil iş zekâsı aracıdır: platformda etkindir; veri yalnız kurulum (Hüseyin Cengiz), salt okur kaynak (replika veya ayrı rapor şeması) ve operatör rolü hazır olunca akar; tarayıcı rıza kapısı yerine erişim denetimi ve veri en aza indirme uygulanır (G-136, P6). Bilgiler Metabase v0.64 belgelerine göredir.

- **Operatör gömme (MUST):** guest gömme açık kaynak sürüm dahil tüm planlarda vardır ([giriş](https://www.metabase.com/docs/latest/embedding/introduction)); her istek gizli anahtarla imzalanmış JWT ister, kilitli parametre filtreyi son kullanıcıya açmaz ([guest](https://www.metabase.com/docs/latest/embedding/guest-embedding)). Belgeler statik gömmeyi eski yöntem sayar ([statik](https://www.metabase.com/docs/latest/embedding/static-embedding)); G-136'daki imzalı gömme guest gömmeyle karşılanır.
- **Kiracıya gömülü BI ve lisans (K-30):** tam uygulama gömme ([full app](https://www.metabase.com/docs/latest/embedding/full-app-embedding)) ve satır/sütun güvenliği ([row/column](https://www.metabase.com/docs/latest/permissions/row-and-column-security)) yalnız Pro ve Enterprise planlarındadır; açık kaynakta kalınırsa kiracı ayrımı kilitli parametre ya da kiracı başına ayrı veri kaynağıyla yapılır (SHOULD). Açık kaynak sürüm AGPL'dir ([lisans](https://www.metabase.com/license)); lisans uyumu Hukuk kararıdır.

## Kabul testleri

Sözleşme testleri Playwright ile sahte satıcı uç noktalarına karşı koşar; gerçek hesap kullanılmaz. Sonuçlar `pass`/`fail`/`not_run` olarak kaydedilir, gerçek cihaz sonuçları emülasyondan ayrı yazılır (G-74). Sahip: Frontend ekibi; Pulse ve Metabase için Hüseyin Cengiz + Platform ekibi.

- **Etkin varsayılan:** her derlemede yedi tarayıcı adapteri kayıtlı ve etkindir, sözleşme testinden geçer; yapılandırma boşken `dataLayer` olay içerir ve satıcı origin'lerine istek sıfırdır.
- **Kapılar:** yapılandırma yok, rıza yok, "Reddet" ve hassas rota durumlarının her birinde satıcı isteği sıfırdır; dört kapı geçince yalnız onaylanan amaç ve satıcının adapteri istek atar. Rıza arayüzü 320 px'ten masaüstüne klavye ve ekran okuyucuyla çalışır, metni ≥1rem'dir (G-67).
- **SPA ve tekilleştirme:** beş rota gezintisi her adapterda tam beş sayfa olayı üretir; `replaceState` ve filtre değişimi olay üretmez; satın alma sayfası yenilenince ikinci olay yoktur; Pixel `eventID` sunucu olayının `event_id` değerine, `transaction_id` Press Invoice adına eşittir.
- **Geri alma:** sahte `gtag` ve `fbq` nesneleri `update` ve `revoke` çağrısını kaydeder; sonrasında satıcı isteği ve listelenen çerezler yoktur; SA-36 kaydı yazılır; sunucu kuyruğundaki olay iptal edilir.
- **İzolasyon, kişisel veri ve maskeleme:** kiracı A ile B arasında kimlik ve olay karışmaz; satıcı isteklerinin URL ve gövdeleri e-posta, telefon, TCKN/VKN, belirteç, `code` ve `X-Request-Id` desenlerine karşı taranır, eşleşme sıfırdır; hassas rotada `gtag`, `ym` ve `fbq` tanımsızdır ve yalnız RUM isteği çıkar; oturum kaydı açık ekranda her giriş alanı `ym-disable-keys` taşır.
- **Pulse ve Metabase:** kiracı ve operasyon sitelerinde Pulse `boot_config` yanıtı `{"enabled": false}` olur; operatör rolü dışındaki hesap gömülü panoyu açamaz, kilitli parametre istemciden değiştirilemez (G-136).

## Kaynaklar

Satır içi bağlantıların tümü birincil kaynaktır (resmi doküman, sabit commit'teki kod) ve 2026-10-08'de kontrol edildi; kontrol edilemeyen davranışlar "(doğrulanacak)" diye işaretlidir.
