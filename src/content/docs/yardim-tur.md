---
title: "Yardım, onboarding turu ve keşif sözleşmesi"
nav: "Yardım ve tur"
order: 13
---

Yardım kulakçığı, kendi kendine destek modu, tur ve keşif motoru kabuğun (`@platform/shell`) tek katmanıdır; aynı sağ yuvayı ve efektif meta'yı (G-63) kullanır. Panel sırasıyla mod anahtarını, sayfa yardımını, sık görevleri ve keşif önerilerini, sayfanın turlarını ve destek bağlantılarını (G-101, SA-30) içerir. Katman sunucu yetkisinin yerine geçmez, veri yazmaz, izin açmaz; içerik kiracı verisi taşımaz. Kulakçık ve içerik modeli P1 (G-137, G-138), tur ve keşif P4'tür (G-139, G-140, G-141); AI paneli aynı yuvaya P3'te girer (G-88).

Bu sayfa tasarım sözleşmesidir; yardım, tur ve keşif katmanları henüz uygulanmadı ve test edilmedi.

## Yardım kulakçığı ve panel

| Kural | Düzey | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| **Dar düzen** (içerik sütunu ile panelin asgari genişliği yan yana sığmadığında; eşik içerikten belirlenir, test genişlikleri eşik değildir): kulakçık üst bardaki "Yardım" düğmesine dönüşür; panel tam ekran kipli çekmecedir (`aria-modal`, alttaki sayfa `inert`) ve AI paneliyle aynı yuvayı paylaşır | MUST | Frontend ekibi | G-137, G-88 | 320'de yatay taşma yok; form alanı örtülmez |
| **Yatay telefon:** sanal klavye açıkken kulakçık gizlenir; panel tam yükseklik kipli çekmecedir; yalnız genişlik arttı diye tablet düzenine geçilmez | MUST | Frontend ekibi | G-137, G-74 | Yön değişiminde açık panel, odak ve girdi korunur |
| **Tablet ve masaüstü:** yapışkan sağ kulakçık içerikte kendi boşluğunda durur; panel sağ yuvada sütundur (dar tablette kipli çekmece); yardım ve AI panelinden aynı anda biri açıktır | MUST | Frontend ekibi | G-137, G-88 | Odaktaki öğe örtülmez (WCAG 2.4.11); geçişte iki panelin durumu korunur |
| **Klavye:** kulakçık `button`, `aria-expanded`, `aria-controls` taşır; açılınca odak panel başlığına gider; Escape kapatır, odağı açan öğeye döndürür; kısayol metin girişinde çalışmaz | MUST | Frontend ekibi | G-137, G-67 | Tab/Shift+Tab sırası tutarlı; tek `:focus-visible` göstergesi |
| **Ekran okuyucu:** panel sütunda adlandırılmış `complementary`, çekmecede adlandırılmış kipli `dialog` öğesidir; yüklenen konu `aria-live` ile duyurulur | MUST | Frontend ekibi | G-137 | "Yardım" ve "Yardım paneli" adları ARIA testinde |
| **Dokunma ve hareket:** hover'a bağlı yardım yok; görünür kapatma düğmesi var; azaltılmış harekette animasyon yok | MUST | Frontend ekibi | G-67, G-74 | Dokunma ve reduced-motion profillerinde geçer |

## Kendi kendine destek modu

| Kural | Düzey | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| **Anahtar:** `role="switch"` ve `aria-checked`; tercih kullanıcı başına sunucuda saklanır, `get_bootstrap` ile gelir; varsayılan kapalı | MUST | Frontend ekibi | G-137, G-63 | Tercih başka cihazda aynı gelir |
| **İşaretler:** mod açıkken okunabilir her alanın (Custom Field dahil), pano bileşeninin ve sayfa başlığının yanında `button`; adı "İzin türü alanı için yardım"; tooltip değildir, yardımı panelde açar | MUST | Frontend ekibi | G-137, G-61 | Gizli veya okunamayan alanın işareti DOM'da yok |
| **Yönlendirici:** ilgili tur, yardım makalesi, destek talebi ve AI açıksa "AI'ye sor"; bağlam yalnız yardım anahtarı ve rota kalıbıdır | SHOULD | Frontend ekibi | SA-30, G-88 | Talepte ve AI bağlamında belge değeri yok |
| **Kapalı mod ve sınır:** işaret katmanı yüklenmez; mod tercih kaydı dışında veri yazmaz, gizli alan açmaz, yetki değiştirmez | MUST | Frontend ekibi | G-137 | Mod ve panel kapalıyken ağda yardım isteği yok |

## Yardım içeriği modeli

`platform_core` içindeki `Help Topic` alanları: anahtar (uygulama + belge türü + alan adı, bileşen kimliği = `data-tour-id` ya da rota kalıbı `/ik/izin-talebi/:kimlik`; Custom Field dahil), kapsam (Platform, Uygulama, Kiracı), dil (`tr`, `en`; G-73), sürüm, hedef roller, sahip, durum (Taslak → İncelemede → Yayında → Arşiv), kısa Markdown gövde.

Geri düşüşte ilk bulunan gösterilir: kiracı içeriği (standart alanda da önce gelir) → uygulama veya platform içeriği → Frappe alanının `description` değeri → genel boş yardım ve "Yardım iste". Talep özel alanda kiracı adminine ToDo açar, standart alanda anahtar bazında kimliksiz sayılır; belge verisi taşımaz.

| Kural | Düzey | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| **Yetki:** son kullanıcı `Help Topic`'i doğrudan okumaz; yardım ucu (ad önerisi `platform_core.api.help`) efektif meta ile süzer; hedef roller güvenlik sınırı değildir | MUST | Platform ekibi | G-61, G-138 | Okunamayan alanın yardımı ve varlığı dönmez |
| **Gövde:** sunucuda `sanitize_html`, istemcide `SafeHtml`; şablon değildir, belge değeri veya kişisel veri içermez | MUST | Platform ekibi | G-145 | XSS yük seti yardım gövdesinde etkisiz |
| **Yazarlık:** kiracı konusunu yalnız Tenant Admin yazar ve yayımlar; uygulama konusu ön ekli fixture ile gelir, kiracıda salt okunurdur | MUST | Platform ekibi | G-62, G-107, G-153 | Başka rolün yazma isteği 403 |
| **Kapsama raporu:** uygulama ve belge türü başına `Help Topic`'i olan veri alanı oranı; yalnız `description` ile karşılananlar ve "Yardım iste" sayısı ayrı | MUST | App ekibi | G-138, G-141 | X-09 betiği eşik altını yayın engeli sayar; eşik Ürün sahibinde |

## Tur ve onboarding motoru

| Kayıt | Alanlar | Kural |
| --- | --- | --- |
| Tur ve hedef kitle | Anahtar (`cronhr.ilk-izin-talebi`), uygulama, rota kalıbı, sürüm; rol, plan ve özellik (`has_feature`, G-106), uygulama durumu (G-127), yetki (ör. `create`) | Tur kısadır, ilk anlamlı işi tamamlatır; koşullar sunucuda değerlendirilir |
| Tetik | İlk ziyaret, el ile, sürüm yeniliği, etkinleştirme sonrası ilk giriş (G-95) | Otomatik tetik yalnız davet kartı açar, odağı taşımaz |
| Adım | Hedef: belge türü + alan adı (Custom Field dahil) veya `data-tour-id`; tür: açıklama veya anlamlı görev (ör. ilk Leave Type kaydı); `since_version` | Metin etiketi meta'dan alır; görev tamamlanmasını sunucu onaylar |
| İlerleme | `platform_core` içinde kullanıcı + tur + sürüm; durum, son adım anahtarı, erteleme bitişi | Belge verisi saklanmaz |

| Kural | Düzey | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| **Atla ve ertele:** kapatılan tur kendiliğinden açılmaz; Escape veya "Sonra" erteler, süre K-35'tedir | MUST | Frontend ekibi | G-139, K-35 | Kapatılan veya ertelenen tur yeniden yüklemede açılmaz |
| **Yeniden başlat ve devam:** yeniden başlatma yalnız o kullanıcıyı sıfırlar; yeniden yüklemede son adımdan sürer | MUST | Platform ekibi | G-139 | Başka kullanıcı etkilenmez; aynı adım açılır |
| **Sürüm ve eksik hedef:** sürüm yükselince yalnız yeni adımlar gösterilir; hedef gizli, okunamaz veya yoksa adım atlanır ve sayılır | MUST | Frontend ekibi | G-139, G-61 | Eski adım tekrar çıkmaz; eksik hedef hata üretmez |
| **Girdi korunur:** tur kirli formu onaysız terk ettirmez, alan değeri yazmaz veya silmez, yazarken odak çalmaz, işaretçiyi engellemez | MUST | Frontend ekibi | G-139, G-71 | İlerleme, erteleme ve kapanışta yazılan metin aynı kalır |
| **Erişilebilirlik:** kipsiz `dialog`; Geri, İleri, Sonra ve Kapat klavyeyle çalışır; adım `aria-live` ile duyurulur; balon hedefi örtmez, dar düzende alt çekmecedir | MUST | Frontend ekibi | G-139, G-74 | Tab sırası balon ile hedef arasında kopmaz |

Frappe kayıtları (doğrulandı, version-16 `6b450a1`): Form Tour (adımları `fieldname` hedefli) ile Module Onboarding ve Onboarding Step yalnız içerik kaynağıdır. İlerleme için kullanılmazlar: Onboarding Step `is_complete`/`is_skipped` site düzeyindedir; `User.onboarding_status` tek ve sürümsüz bir JSON'dur; `update_user_status` telemetri `capture` çağırır (G-134 kapısı); `reset_tour` herkesi sıfırlar ve System Manager ister (G-53); JS `next_step_condition` çalıştırılmaz (G-123).

## Keşif motoru

| Kural | Düzey | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| **Kural ve yetki:** uygulama kuralı `hooks.py` içinde bildirir (ad önerisi `discovery_rules`); koşul `frappe.get_list` ile kullanıcının yetkisiyle değerlendirilir; okunamayan belge türünde kural uygulanmaz; önerilen eylemin izni ayrıca denetlenir | SHOULD | App ekibi + Platform ekibi | G-140, G-141 | Yetkisiz göreve öneri yok |
| **Gösterim ve sıklık:** yardım panelinde ve ana sayfada tek kart; kapatılan öneri aynı kural sürümünde dönmez; sıklık sınırı K-35'tedir | SHOULD | Platform ekibi | G-140, K-35 | Kapatılan öneri yeniden yüklemede görünmez |
| **Maliyet ve ölçüm:** kurallar panel veya ana sayfa açılınca değerlendirilir, sonuç kısa süre önbelleklenir; olaylar G-134 yolundan birinci taraf akar; ölçütler [Ölçüm ve gözlem](/frappesetup/olcum-gozlem/) sayfasında | SHOULD | Platform ekibi | G-140, G-134 | Sayfa yüklemesi beklemez; olayda kişisel veri yok |

## Erişilebilirlik ve kabul

- G-74 matrisine ek kapıdır (sahip Frontend ekibi); sonuç `pass`/`fail`/`not_run` yazılır, çalıştırılmayan kontrol başarılı sayılmaz.
- 320 → 360 → 375 → 390 → yatay telefon → tablet → masaüstü; Chromium, Firefox, WebKit × fare, dokunma, klavye; gerçek Safari ayrı raporlanır.
- Ekran okuyucu adları (kulakçık, panel, anahtar, işaret) ARIA testinde, VoiceOver ve NVDA ayrı kayıtta; metin ≥1rem (G-67), %200 metin (WCAG 1.4.4), 320 CSS px yeniden akış (WCAG 1.4.10), odak örtülmez (WCAG 2.4.11).
- Yön değişiminde ve tur boyunca açık panel, odak ve form girdisi korunur; azaltılmış harekette animasyon yok.
- Okunamayan alanın yardımı arayüzde ve API'de yok; içerik yoksa geri düşüş işler; mod ve panel kapalıyken yardım ağ isteği yok; tur (ilk ziyaret, devam, sürüm, eksik hedef) ve keşif (kapatılan öneri) testleri bulunur.

## Sahiplik ve yayın

| İçerik | Sahip | Yayın | Gereksinim |
| --- | --- | --- | --- |
| Kabuk yardımı, genel turlar, yardım menüsü (dokümantasyon, durum, destek talebi) | Platform ekibi; bileşen Frontend ekibi | Ürün sahibi onayı; platform sürümüyle; destek süreci (X-08) | G-137, G-138, G-101, SA-30 |
| Standart alan, sayfa ve bileşen yardımı; başlangıç turu | App ekibi | Ürün sahibi incelemesi; uygulama sürümüyle; X-09 kapsama eşiği ve en az bir tur | G-138, G-139, G-141, G-95 |
| Keşif kuralları | App ekibi; motor Platform ekibi | Yetki negatif testi ve şema doğrulaması | G-140, G-141 |
| Custom Field ve kiracıya özel yardım | Kiracı admini | Taslak → Yayında; platform yalnız temizler | G-138, G-153 |

## Kaynaklar

Doğrulama tarihi: 2026-10-08.

- [APG Disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), [APG Dialog (Modal)](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [APG Switch](https://www.w3.org/WAI/ARIA/apg/patterns/switch/): kulakçık, kipli çekmece ve anahtar desenleri; [APG Tooltip](https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/) taslaktır, alan yardımı bu yüzden düğmedir.
- WCAG 2.2: [1.4.4](https://www.w3.org/TR/WCAG22/#resize-text) %200 metin, [1.4.10](https://www.w3.org/TR/WCAG22/#reflow) 320 px yeniden akış, [2.4.11](https://www.w3.org/TR/WCAG22/#focus-not-obscured-minimum) odağın örtülmemesi (AA).
- Frappe version-16 `6b450a1`: [Form Tour Step](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/desk/doctype/form_tour_step/form_tour_step.json) `fieldname` ve JS `next_step_condition`; [`form_tour.py`](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/desk/doctype/form_tour/form_tour.py#L77-L105) kullanıcı durumu, telemetri, `reset_tour`; [Onboarding Step](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/desk/doctype/onboarding_step/onboarding_step.json) site düzeyi bayraklar; [Module Onboarding](https://github.com/frappe/frappe/blob/6b450a166e076dd842e4db7ea0843f62881e62ac/frappe/desk/doctype/module_onboarding/module_onboarding.json).
- [Frappe veritabanı API'si](https://docs.frappe.io/framework/user/en/api/database): `get_list` izin uygular, `get_all` uygulamaz.
