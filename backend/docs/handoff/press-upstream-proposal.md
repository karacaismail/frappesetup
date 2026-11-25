# Press'e gidecek öneriyi gönderme

Bu not, Press uyum önerisinin nasıl gönderileceğini anlatır.
Öneri 23 Kasım 2026 Pazartesi günü depoda hazırlandı.
Öneri Press'e gönderilmedi.
Gönderim proje sahibinin onayını bekler.
Ajanlar öneriyi göndermez. Karar O-57 kaydındadır.

## Önerinin parçaları

Öneri iki dosyadan oluşur.
İki dosya da `backend/docs/upstream/press-python314/` klasöründedir.

- `0001-python-313-frappe-16-imports.patch` dosyası yama dizisidir. İçinde üç commit vardır.
- `pull-request.md` dosyası İngilizce açıklama metnidir. Başlık ve gövde bu dosyadadır.

Yama üç engeli kaldırır.
Bu engeller `TypedDict` tanımı, telemetri import'u ve çerez import'udur.
Ayrıntı [Press uyum notundadır](../press-python314-upstream.md).

Yama iki konuyu kapsamaz.

- Bağımlılık sürümleri yamaya girmez. Her sürüm değişikliği ayrı tartışma ister.
- Telegram değişikliği yamaya girmez. Press'in `develop` dalı bu sorunu kendisi çözdü.

## Yerel kanıt

Yama Press `v0.154.1` etiketine temiz uygulanır.
Etiketin commit kodu `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` şeklindedir.
Deneme yerel bilgisayarda yapıldı. Komut şudur:

```bash
git -C <press-v0.154.1-klasoru> apply --check -v backend/docs/upstream/press-python314/0001-python-313-frappe-16-imports.patch
```

Komut dört dosyayı denetledi ve 0 koduyla çıktı.

Press'in `develop` dalı da 23 Kasım 2026 Pazartesi günü denendi.
Dalın ucu `adb197c54ab8ff96c465cf08d9823793fc94db34` commit'iydi.
Üç dosya bu dala da temiz uygulandı.
`product_trial_request.py` dosyası uygulanmadı.
Bu dosyaya yeni bir import satırı eklenmiş. Değişiklik aynı kalır, yalnız satır komşuları değişti.

## Gönderim adımları

Bu adımları proje sahibi onay verdikten sonra uygulayın.
Onay yoksa hiçbir adımı uygulamayın.

1. Proje sahibinden yazılı onay alın. Onayı bu nota ve O-57 kaydına yazın.
2. GitHub'da `frappe/press` deposunun bir kopyasını açın. Kopya proje sahibinin hesabında olsun.
3. Kopyayı yerel bilgisayara indirin.
4. `develop` dalından `fix/python-313-frappe-16-imports` adlı bir dal açın.
5. Yamayı `git am -3 <yama dosyası>` komutuyla uygulayın.
6. `product_trial_request.py` dosyasında çakışma çıkarsa yeni import satırını koruyun. Sonra `git am --continue` çalıştırın.
7. `uvx ruff@0.13.1 check` komutunu değişen dört dosyada çalıştırın. Yeni bulgu çıkmamalı.
8. Commit yazarının `karacaismail` olduğunu `git log` ile denetleyin.
9. Dalı proje sahibinin kopyasına gönderin.
10. `frappe/press` deposunda `develop` dalına bir PR açın.
11. PR başlığını ve gövdesini `pull-request.md` dosyasından kopyalayın.
12. PR adresini bu nota ve teknik borç satırına yazın.

## Gönderimden sonra

Press bakımcıları değişiklik isteyebilir.
Bu durumda değişikliği depodaki yamaya da işleyin.
Press düzeltmeyi kabul edip yayımlarsa sırayla şunları yapın:

1. Press sürümünü yeni sürüme taşıyın.
2. Üretim imajındaki karşılık yamaları silin. Bunlar `0001`, `0002` ve `0003` yamalarıdır.
3. `dev/press/patch-py314.sh` betiğinden `TypedDict` ve telemetri adımlarını silin.
4. O-18 ve O-52 kayıtlarını güncelleyin.

Gerçek okurla denenmedi.
