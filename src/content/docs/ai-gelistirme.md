---
title: "AI · Kendi skill, MCP ve ajanlarımız"
nav: "Geliştirme planı"
order: 25
---

Bu sayfa [Press yetkinliğindeki](/frappesetup/ai-press-yetkinlik/) boşlukları kapatan `packages/press-ai` paketinin kararlarını, kurulumunu, kabul ölçütlerini ve kalan sınırlarını verir. Kural: hazır olanı kullan, eksik olanı küçük ve denetlenebilir parçalarla yaz. Mimari [Rail 5](/frappesetup/rail-5-ai/) ile uyumludur; bütün SaaS mimarisi bu pakette koda çevrilmez. Durum: kod taslakları var; bağımsız statik inceleme yapıldı, bulguların düzeltmeleri test sonuçlarıyla son koşuda doğrulanır; canlı Press doğrulaması `not_run`.

## Ne hazır alınır, ne yazılır

| Alan | Hazır kullan | Yaz | Gerekçe |
| --- | --- | --- | --- |
| Frappe uygulama geliştirme bilgisi | `frappe/skills` (`frappe-app-dev`, `deep-app-audit`), atıfla | `frappe-custom-app`, `frappe-app-extension` | Resmi ve derin; lisans dosyası yok, metin kopyalanmaz |
| Press teşhisi | Press içi MCP (`enable_mcp`) | `press-build-triage`, `press-diagnoser` | Araçlar hazır, teşhis sırası yok |
| Press kurulum ve dağıtım | — | `press-ai` MCP, `press-operations`, `press-operator` | Hiçbir hazır depo onaylı biçimde karşılamıyor |
| Site içi veri araçları | `frappe/mcp` çatısı ya da kullanıcı kimlikli sunucu | `platform_core` araçları (Rail 5) | Kullanıcı kimliği ve denetim izi gerekir |
| Kullanıcıya dönük asistan | Flow izlenir (not: sınıf C); Jarvis ve Huf staging'de denenir | Agent servisi (Rail 5) | Keycloak delege token, kiracı kotası, Press kredi ölçümü hiçbirinde yok |

AGPL bileşenleri (Flow, huf, Jarvis, Ask ALYF, Raven) kendi kodumuzla aynı süreçte birleştirilmeden önce lisans uyumu kullanıcıyla netleştirilir; yeni depolara lisans onaysız seçilmez.

## Paketin parçaları

| Parça | Yol | Durum |
| --- | --- | --- |
| Arayüz sözleşmesi | `packages/press-ai/INTERFACE.md` | İşlem kimlikleri, araç adları, statü sözlüğü buradan değişir |
| Operasyon kontratı | `packages/press-ai/contracts/` | Statik kaynak doğrulaması; kapsamı Press yetkinliği sayfasında |
| MCP runtime ve onay CLI | `packages/press-ai/server.py`, `packages/press-ai/press_ai/` | Taslak; fixture testleri ve CI'da paket testleri |
| Skill'ler | `packages/press-ai/skills/` | Dört skill; davranış senaryoları yazıldı, koşu `not_run` |
| Ajanlar | `packages/press-ai/agents/` | Dört tanım; araç listeleri rol ayrımına göre |
| Paylaşılan başvurular | `packages/press-ai/references/` | Press modeli ve gizli alanlar, devirler, Frappe modeli, senaryolar |
| Testler | `packages/press-ai/tests/` | Sonuç sayısı son koşudan; bu sayfada sayı yazılmaz |

## İndir

Tüm paket ZIP'i depo yerleşimini izler: kökte lisans dosyaları ve `packages/press-ai/`. Aşağıdaki komutlar ZIP'in açıldığı dizinde de aynen çalışır.

<div data-embed="dl-package"></div>

## Kurulum ve çalıştırma

1. Depo public ve açık kaynaktır (kod MIT, içerik CC BY 4.0): `git clone https://github.com/karacaismail/frappesetup.git` ya da yukarıdaki tüm paket ZIP'i. Python 3.9+ yeterlidir; ek paket yoktur.
2. Yapılandırma: base host, rol (`team` ya da `operator`), takım ve izinli workspace kökü. API anahtarı keychain'de ya da yalnız sahibinin okuyabildiği dosyadadır; depoya, sohbete ve belgelere yazılmaz.
3. Denetim ve testler:

   ```sh
   python3 -I packages/press-ai/server.py check-contract --guide <pressguide>/src/data/guide.json --sitemap <pressguide>/src/data/press-sitemap.json
   python3 -I -m unittest discover -s packages/press-ai/tests
   ```

4. MCP kaydı (yerel kapsam; ajan araç listeleri `mcp__press-ai__` önekini bekler):

   ```sh
   claude mcp add press-ai -- python3 -I /mutlak/yol/packages/press-ai/server.py serve --config /mutlak/yol/yapılandırma
   ```

5. Skill ve ajanlar: oturumluk `claude --plugin-dir packages/press-ai` (önce `claude plugin validate packages/press-ai --strict`) ya da `.claude/` altına kopya (adımlar [Skills](/frappesetup/ai-skills/) sayfasında). MCP sunucusu eklentiye gömülü değildir, 4. adımla ayrıca kaydedilir.
6. İnsan onayı her öneri için ayrı terminalde, TTY ile:

   ```sh
   python3 -I packages/press-ai/server.py approve <öneri-kimliği> --config /mutlak/yol/yapılandırma
   ```

## Kabul ölçütleri

- Deploy önerisi yalnız aynı build'in tüm adımları Success iken açılır; build ile deploy'u birleştiren yol uygulanmaz.
- Yürütme sonucu "kabul edildi"dir; başarı yalnız Press durumundan okunur.
- Yürütme aynı işlem ve hedef için uçuş kilidi alır (süreç ölünce işletim sistemi bırakır), istekten önce sonucu `unknown` kaydeder; zaman aşımı, kesilen yürütme ve sonucu yazılmamış tüketilmiş öneri `unknown`dır ve insan `resolve` ile kapatana kadar o hedefe yeni öneriyi engeller.
- Onay özete bağlı, tek kullanımlık ve sürelidir; modelde onay aracı ya da `confirm` alanı yoktur.
- Takım yapılandırmadan gelir; `team` rolünde Press'in çözdüğü takım yapılandırılanla eşleşmeden mutasyon yoktur; operatör rolünde de hedef kaydın takıma ait olduğu okunur.
- Gizli alanlar (build token, özel anahtar, Agent Job istek verisi, GitHub token, imzalı yedek adresi) hiç istenmez.
- Yeni release, aynı App Source'u `enable_auto_deploy` açık kullanan bir grup varken, Press'te deploy işareti tanımlıyken ya da bu okunamıyorken önerilmez; insan karar verir.
- Deploy önizlemesi otomatik güncellenecek site kümesini (Broken siteler ayrı) listeler ve onay ifadesi otomatik migrate'i içerir; 500'den fazla sitede önizleme eksikse öneri engellenir. Build, image, sunucu platformu ve site kümesi önizlemede sabitlenir, yürütmede farklıysa yürütme engellenir.
- Deploy başarısı her beklenen sunucuda okunur: bench Active, New Bench işi Success ve bench'in build'i onaylanan build.
- Uygulama kurulumu ücretli plan seçmez; ücretli Marketplace planı hesap sahibindedir.
- Uygulama kodu tek dosyalık onaylı öneriyle yazılır, çalıştırılmaz; resmi uygulama dosyası varsayılan olarak reddedilir, yalnız uyarı, kullanıcının açık tekrarı ve `CORE <uygulama>` onayıyla yazılır; "geçti" yalnız geliştiricinin test çıktısıyla söylenir.

## Kalan sınırlar

- Canlı Press ve gerçek MCP istemci oturumu `not_run`; kurulu Press'in commit'i bilinmiyor. CI (ci.yml, deploy.yml) paket birim testlerini ve kontrat denetimini koşar; kılavuz sırası ve sitemap denetimi yalnız yerelde kılavuz verisiyle (`PRESSGUIDE_DATA`) yapılır.
- Kimlik kişisel API anahtarı ya da System User'dır; planlanan OAuth2 delegasyonu (G-28) ve servis kimlikleri (G-82) yoktur.
- Onay sunucuyla aynı işletim sistemi hesabında yazılır (`same_os_account`); aynı hesapta kabuk erişimi olan bir süreç onay CLI'sini çalıştırabilir. Bu hız kesicidir, güvenlik sınırı değildir. Ayrı onaylayıcı hesabı desteklenmez; `approval.approver_uid` yapılandırmada reddedilir.
- AI denetim izi ve Press defterine kredi ölçümü (G-87, G-92) pakette yoktur.
- Uygulanmayan işler: site oluşturma, yasal kutu, ödeme, geri yükleme, sunucu ekleme, SSH, registry, DNS, Press kod düzeltmesinin kurulumu.
- Frappe sürüm kuralları v15 ve v16 dallarının statik okumasıdır; hedef sürüm bilinmeden sürüme bağlı karar `unknown` kalır.
- Prompt injection savunması (G-89) ajan kurallarında Press çıktısını güvenilmeyen veri saymaktan ibarettir; güvenlik test programı (X-14) koşulmadı.

## Sonraki aşamalar

| Aşama | Görev | Sahip | Bağımlılık | Kabul |
| --- | --- | --- | --- | --- |
| A1 | Fixture testleri, bağımsız inceleme, senaryo koşusu | Geliştirme ekibi | — | Testler ve senaryolar geçer; başarısız vaka gevşetilmez |
| A2 | Canlı olmayan bir Press ortamında yalnız okuma araçları | Geliştirme ekibi; ortam Hüseyin Cengiz | A1 | Okuma sonuçları kontrat alanlarıyla eşleşir; gizli alan dönmez |
| A3 | Aynı ortamda tek zincir: app ekleme, release, candidate, build, deploy | Geliştirme ekibi; altyapı Hüseyin Cengiz | A2 | Her adımda insan onayı; build Success olmadan deploy önerisi reddedilir |
| A4 | DNS gereksinimi çıktısı | Hüseyin Cengiz hazırlar, Asistan Hüseyin GoDaddy'de uygular, Hüseyin Cengiz doğrular | A3 | Ajan DNS'e dokunmaz; yalnız kayıt gereksinimi üretir |
| A5 | OAuth2 delegasyonu ve AI denetim izi | Geliştirme ekibi | Rail 5 | G-28 ve G-87 kabul ölçütleri |

## Riskler

- `press.api.*` kararlı genel sözleşme değildir; her Press sürümünde kontrat yeniden doğrulanır.
- Yazma yetkili bir MCP tek hatada canlı sitelere dokunabilir. Deploy ve migrate çift onaylıdır; deploy onayı, otomatik güncellemesi açık sitelerin kendiliğinden migrate olmasını da kapsar. Mutasyonlar yapılandırmada açılmadıkça kapalıdır.
- Bu sayfa statik kaynak okumasına dayanır; hiçbir araç bizim ortamımızda doğrulanmadan "çalışıyor" sayılmaz.
