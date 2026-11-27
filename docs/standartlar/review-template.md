# Kural uyumunu inceleme yorumuna yazın

QA, işi deneyen kişidir. Committer, dalı inceleyen ve birleştirme kararını yazan kişidir. Dalı `backend` dalına yalnız orkestratör birleştirir. QA ve Committer kendi inceleme yorumlarında kural uyum listesini doldurur.

## İnceleme adımları

İnceleyen kişi şu adımları izler:

1. İş tanımını ve geliştiricinin ilk yorumunu okuyun.
2. Değişen dosyaları inceleyin.
3. Bu dosyalara uygulanan kural listesini doğrulayın.
4. Her kuralın işteki karşılığını denetleyin.
5. Her satıra kural kodunu ve sonucu yazın.
6. Her satıra kanıtı veya eksikliği ekleyin.
7. İncelenen son commit kimliğini yazın.
8. Birleştirme kararını gerekçesiyle yazın.
9. Karar olumluysa yorumun sonuna “orkestratör birleştirsin” yazın.

Commit, Git içindeki değişiklik kaydıdır. QA ve Committer aynı son commit'i inceler. Geliştirici yeni commit eklerse etkilenen kurallar yeniden incelenir.

## Birleştirmeyi orkestratör yapar

frappesetup dallarını yalnız orkestratör birleştirir. Birleştirme kapıları birleştirmenin parçasıdır. Ajan dalı birleştirirse bu kapılar koşmaz.

- Committer `backend` dalına `git merge` yapmaz.
- Committer dalı `backend` dalına göndermez.
- Committer inceleme yorumunu yazar. Karar olumluysa yorumun sonuna “orkestratör birleştirsin” yazar.
- Orkestratör kapıları çalıştırır. Kapılar geçerse orkestratör dalı birleştirir.

Bu kural orkestratörün 27 Kasım 2026 Cuma günkü kararıdır. Karar AJA-1426 işinde yazılıdır.

## Yorum şablonu

İnceleyen kişi yorumda adını veya görevini belirtir. İncelenen dalı, commit kimliğini ve iş bağlantısını yazar. Sonra şu listeyi doldurur:

| Kural kodu | Kaynak dosya | Sonuç | Kanıt veya gerekçe |
| --- | --- | --- | --- |
| İşteki mevcut kod | Kodun tanımlı olduğu dosya | Uygunluk sonucu | Dosya, test sonucu veya eksik bilgi |

Sonuçlar şu anlamlara gelir:

| Sonuç | Anlamı |
| --- | --- |
| uygun | İnceleyen kişi kuralın karşılandığını kanıtla doğruladı. |
| uygun değil | İnceleyen kişi kurala aykırılık buldu. |
| denetlenmedi | Kural için yeterli inceleme veya kanıt yok. |
| kapsam dışı | Kural değişen işi kapsamıyor. Gerekçe aynı satırdadır. |

**Bir satır “uygun değil” ise dal birleşmez.** Committer birleştirmeyi durdurur. QA veya Committer işi gerekçesiyle geliştiriciye geri verir. Geliştirici düzeltince ilgili inceleme tekrarlanır.

“Denetlenmedi” sonucu da birleştirmeyi durdurur. “Kapsam dışı” sonucunun gerekçesini QA ve Committer doğrular. Eksik kural satırı varsa inceleme tamamlanmış sayılmaz.

## Somut örnek

Bu örnek gerçek bir inceleme sonucu değildir. Örnekte kullanıcı hedef kaydı seçer. Kod bu kayıt için izin denetimini atlar.

QA şu satırı yazar:

| Kural kodu | Kaynak dosya | Sonuç | Kanıt veya gerekçe |
| --- | --- | --- | --- |
| G-4 | [frappe-python-standartlari.md](frappe-python-standartlari.md) | uygun değil | Kullanıcının seçtiği kayıtta `ignore_permissions=True` kullanılıyor. |

Committer aynı aykırılığı kendi yorumuna yazar. Committer dalı birleştirmez. Geliştirici izin atlamasını düzeltir. QA düzeltmeyi yeniden dener.

## Otomatik denetimin sınırı

`tests/consistency.spec.ts` beş süreç belgesinin varlığını denetler. Test, somut örnek başlıklarını da denetler. Kullanılan kural kodlarının kaynakta tanımlı olduğunu doğrular. Test, görev yorumlarını veya gerçek kod uyumunu denetlemez.

QA ve Committer gerçek uyumu ayrıca inceler. Yalnız testin geçmesi birleştirme onayı değildir.

Depo kökünde önce siteyi derleyin:

```bash
npm run build
```

Ardından beş belgeyi denetleyin:

```bash
npm run test:e2e -- tests/consistency.spec.ts --project=chromium \
  --grep "rule process document"
```

Bu denetim tarayıcı açmaz. Komuttaki `chromium` seçimi yalnız test grubunu belirler.

