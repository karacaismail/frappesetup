# İş: security-tooling

Bu iş güvenlik taramalarını elle başlatılan komutlar olarak yazar. Proje sahibinin güvenlik kuralları bazı araçları ister. Bu araçlar henüz yok. Zamanlanmış tarama kurulmaz (D-6, O-29).

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`, özellikle “Container kuralları” ve “Bilinen ortam sorunları”
2. `backend/PROJECT-RECORD.md`, özellikle D-6, D-15 ve O-29
3. `backend/docs/security-requirements.md`. Bu liste proje sahibinin güvenlik önlemlerinden çıkarıldı.
4. `backend/dev/bin/security-audit` ve `backend/dev/security/`. Bu var olan kapıdır. Yeni komutlar onun biçimini izler.
5. `backend/docs/gap-backlog.md`

## Sahip olduğunuz yerler

- `backend/dev/security/` (yeni klasör)
- `backend/dev/bin/security-full`, `backend/dev/bin/dast-scan`, `backend/dev/bin/release-report`, `backend/dev/bin/security-scorecard` (yeni komutlar)
- `backend/dev/security/` ve `backend/dev/bin/security-audit`. Önceki iş bitti. Bu yerler artık sizindir.
- `backend/docs/handoff/ci-security.md` (yeni devir notu)
- `backend/docs/decisions/0011-security-tooling.md` (yeni karar notu)

Yeni dosya, işlev ve değişken adları İngilizce olur (D-12).

## Komutlar

1. **`security-full`.** Var olan kapıyı ve şu taramaları sırayla çalıştırır:
   - Bandit ile Python taraması. Sürüm sabit olur.
   - Gizli bilgi taraması bütün Git geçmişinde yapılır. Var olan gitleaks imajını kullanın.
   - Bağımlılık açığı taraması. Örneğin `pip-audit` ya da `osv-scanner`.
   - Sözleşme tabanlı API testi. Schemathesis, `backend/contracts/` dosyalarını çalışan yerel siteye karşı dener. Site kapalıysa bu adım `not_run` yazar.
2. **`dast-scan`.** Çalışan yerel siteye ZAP temel taraması yapar. Hedef yalnız `127.0.0.1` ya da `*.localhost` olabilir. Başka adres reddedilir.
3. **`release-report`.** Son taramaların sonucunu tek bir Markdown raporunda toplar. Her satırda araç, sürüm, komut ve sonuç bulunur. Sonuç `pass`, `fail`, `not_run` ya da `not_applicable` olur.

4. **`security-scorecard`.** Güvenlik sayılarını tek tabloda verir. Örnekler açık bulgu sayısı, paket açıkları ve reddedilen istek sayısıdır. Komut elle başlatılır. Zamanlanmış iş yoktur.

Her komut için bir HTTP ucu yazılmaz. Bu komutlar geliştirme aracıdır, ürün işlemi değildir.

## Kurallar

- Her aracın sürümünü sabitleyin. İmajı özetle sabitleyin.
- Bulunan sorunu düzeltmeyin. Sorunu dosyası ve satırıyla raporlayın. Düzeltmeyi orkestratör ilgili işe verir.
- Yanlış alarmı susturmak için gerekçeli bir istisna dosyası kullanın. Her istisnada neden ve sahip yazılır.
- Disk dar. `colima-factory` profilinde 22 Kasım 2026 Pazar günü 4,2 GB boş yer vardı. ZAP imajını `colima` profilinde çalıştırın. Önce `colima ssh -- free -g` ile en az 3 GB boş bellek ölçün.
- Dış servise istek atmayın. Açık veritabanları yalnız indirme için kullanılabilir.

## Devir notu

CI kurulumunun teknik sahibi DevOps sorumlusudur. Ajanlar CI dosyasını değiştirmez. `backend/docs/handoff/ci-security.md` dosyasına şunları yazın:

1. CI'da koşacak işlerin listesi. Örneğin `security-full` ve CodeQL.
2. Her işin komutu ve çalışma klasörü.
3. Başarısız tarama birleştirmeyi durdurur. Kabul ölçütünü bu cümleyle yazın.
4. Gereken sırlar. Yalnız adlarını yazın, değerlerini yazmayın.

## Kontrol noktaları

1. `security-full` yazıldı ve testleri var. Bilinen kötü bir örnek dosya her taramada yakalanır.
2. `dast-scan` ve `release-report` yazıldı.
3. Devir notu ve karar notu yazıldı.

Her kontrol noktasında `ready` raporlayın ve sonraki noktaya geçin.
