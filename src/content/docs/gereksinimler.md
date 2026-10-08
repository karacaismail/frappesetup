---
title: "Gereksinim çerçevesi"
nav: "Gereksinimler"
order: 14
---

Bu bölüm, önceki bölümlerde ray ray gerekçelendirilen tüm gereksinimleri tek bir ana listede toplar. Tek doğruluk kaynağı `src/data/requirements.json` dosyasıdır: yukarıdaki gezgin ve aşağıdaki dağılım özeti bu dosyadan derleme anında üretilir; elle tutulan tablo kopyası yoktur. Ana seri G sıralıdır (G-1..G-118 ilk sürüm; G-119 ve sonrası değerlendirme raporu ve yeni ürün gereksinimleriyle eklendi, mevcut kimlikler korunur); Rail 6 operasyon düzlemi ayrı SA serisindedir. Gezginde ray, öncelik, faz ve kaynağa göre süzebilir, kimlikle arayabilirsiniz; tam gerekçe ve kod kanıtı ilgili ray veya sözleşme bölümündedir.

## Okuma kılavuzu

- **Öncelik:** MUST = sabit kararların veya mevzuatın doğrudan sonucu; SHOULD = bağlamsal öneri; MAY = isteğe bağlı.
- **Kaynak:** native = Press/Frappe/Keycloak yerleşik mekanizma; configure = yalnızca ayar/kayıt; develop = özel kod (yaşadığı uygulama metinde adlandırılır: press\_tr, `press_tr_finance`, `press_ops_bridge`, platform\_core, tr\_localization, agent servisi, panel monorepo); integrate = dış servis bağlanır.
- **Sahip:** Altyapı işleri Hüseyin Cengiz, GoDaddy/DNS işleri Asistan Hüseyin; "Platform ekibi" yazan kalemler platform geliştirme ekibi ve ürün sahibindedir.
- **Güven:** "(doğrulandı)" = Press/Frappe/Keycloak kaynak kodunda, resmi dokümanda veya sürüm notunda teyit edildi ve [kaynak defterinde](/frappesetup/izlenebilirlik/#kaynak-defteri) sürüm/commit ile kayıtlıdır (G-128); "(doğrulanacak)" = olası veya hukuk/mali müşavir/kurulum teyidi bekleyen iddia.
- **Faz:** gereksinimin kabulünün ilk kanıtlanması gereken fazdır; sonraki fazdaki genişleme ayrıntıda yazılır. Faz hedefleri ve çıkış ölçütleri [yol haritasındadır](/frappesetup/yol-haritasi/).

## Dağılım özeti

Sayılar derleme anında `requirements.json` dosyasından hesaplanır.

<div data-embed="req-summary"></div>

## Çapraz boşluk kalemlerinin ana listeye bağlanması

Eleştiri turunda tespit edilen çapraz boşluklar (X-01..X-21) yeni numara almadan mevcut G-kalemlerine dağıtılmıştır; aşağıdaki eşleme izlenebilirlik içindir:

- **Kiracı yaşam döngüsü (X-01):** G-31 → G-42 → G-30/G-95 → G-19/G-20 → G-24 → G-116 → G-57/G-81 zinciri; E2E kapsamı G-111; operasyon tarafı SA-19 → SA-20.
- **Ortam matrisi (X-02) ve CI/CD bütünü (X-03):** G-110, G-111, G-114.
- **Sürüm/uyumluluk matrisi (X-04):** G-1, G-54, G-66.
- **Gözlemlenebilirlik ve correlation-id (X-05):** G-113, G-87, G-91.
- **DR planı (X-06):** G-114, G-55, G-76, G-49.
- **Maliyet modeli ve AI ölçümü (X-07):** G-92, G-87, G-113, SA-15.
- **Destek ve incident süreci (X-08):** G-18, G-36, G-101, SA-27..SA-31.
- **Admin Shell Uyumluluk Listesi (X-09):** G-102..G-107 + G-29/G-32.
- **Yetki katmanlarının tek doğruluk kaynağı (X-10):** G-16 (Press Role), G-57/G-77 (Keycloak kimlik ve org üyeliği), G-60..G-62 (veri yetkisi), G-85 (MCP), G-94 (sidebar), SA-1/SA-25 (operatör).
- **Çok siteli kullanıcı (X-11):** G-16, G-57, G-79, G-81.
- **Meta önbelleği ve geçersizleme (X-12):** G-63, G-69.
- **Performans bütçeleri (X-13):** G-66, G-46, G-89.
- **Güvenlik test programı (X-14):** G-115, G-89, G-91.
- **Müşteri veri göçü (X-15):** G-97 (Data Import).
- **Keycloak giriş teması (X-16):** G-80.
- **Sır envanteri ve rotasyon (X-17):** G-112, G-39, G-49.
- **Saat dilimi ve takvim sözleşmesi (X-18):** G-14 (deploy\_hours UTC), G-5 (yedek saatleri), G-24 (dunning günleri), G-117 (SLA).
- **Dokümantasyon seti (X-19):** G-114 (runbook + ADR), G-101 (yardım).
- **Zincir E2E test stratejisi (X-20):** G-74, G-111.
- **Özelleştirilmiş kiracılarda güncelleme ön testi (X-21):** G-14, G-40, G-114.
