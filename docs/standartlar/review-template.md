# Kural uyumunu inceleme yorumuna yazın

QA, işi deneyen kişidir. Committer, dalı inceleyen ve birleştirme sürecini yürüten kişidir. QA ve Committer kendi inceleme yorumlarında kural uyum listesini doldurur.

## İnceleme adımları

İnceleyen kişi şu adımları izler:

1. İş tanımını ve geliştiricinin ilk yorumunu okuyun.
2. Değişen dosyaları inceleyin.
3. Bu dosyalara uygulanan kural listesini doğrulayın.
4. Her kuralın işteki karşılığını denetleyin.
5. Her satıra kural kodunu ve sonucu yazın.
6. Her satıra kanıtı veya eksikliği ekleyin.
7. İncelenen son commit kimliğini yazın.
8. Committer her PR'da commit kimliğini denetler. Ayrıntı “Commit kimliği denetimi” bölümündedir.
9. Birleştirme kararını gerekçesiyle yazın.

Commit, Git içindeki değişiklik kaydıdır. QA ve Committer aynı son commit'i inceler. Geliştirici yeni commit eklerse etkilenen kurallar yeniden incelenir.

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

## Commit kimliği denetimi

Committer her PR'da commit kimliğini denetler. Bu kuralı müşteri 27 Kasım 2026 Cuma günü koydu. Kural `KARARLAR.md` dosyasında Karar 45 olarak yazılıdır.

PR'daki her commit'in iki kimlik alanı vardır. Yazar, değişikliği yazan kişidir. Committer, commit'i oluşturan kişidir. İki alan da şu değeri taşımalı:

```text
karacaismail <35493655+karacaismail@users.noreply.github.com>
```

Kural ProPR'ın commit'lerini de kapsar. Örneğin ana dalı PR dalına birleştiren commit bu kapsamdadır. Çakışma çözen commit ve ProPR düzeltme commit'i de bu kapsamdadır.

Tek istisna GitHub'ın son birleşme commit'idir. GitHub bu commit'in committer alanına GitHub yazar. Müşteri bu istisnayı kabul etti. Bu commit'in yazar alanı yine `karacaismail` olmalı.

Committer kimliği şu komutla listeler:

```bash
git log --format='%H %an <%ae> | %cn <%ce>' <hedef-dal>..<pr-dalı>
```

Bir commit'te başka bir ad varsa dal birleşmez. Örneğin `propr-dev[bot]` adı görünürse dal birleşmez. Committer sonucu inceleme yorumuna yazar. Committer işi gerekçesiyle geliştiriciye geri verir.

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

