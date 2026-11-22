# 0015. Anahtar indirmesinde tek iş ve süre sınırı

Bu not `oidc_verify` kitaplığının anahtar indirmesini anlatır. Karar orkestratörün kararıdır. Not, üçüncü birleştirme incelemesinin O4 bulgusundan sonra yazıldı. Tarih 22 Kasım 2026 Pazar günüdür.

## Sorun

Kitaplık, belirteç imzasını doğrulamak için Keycloak'ın anahtar listesini indirir.

İndirme uzarsa yenileme kilidi tutulur. Bekleyen çağrılar da takılır.

Önceki düzeltme çağrıyı ve kilidi süreyle sınırladı. Ama ağ işi arka planda sürebiliyordu. Adres araması takılırsa her yeni yenileme yeni bir iş başlatabiliyordu.

## Karar

1. Her önbellek için aynı anda en çok bir indirme işi çalışır.
2. İş sürerken gelen çağrı yeni iş başlatmaz. Çağrı önceki işi en çok `total_timeout` saniye bekler.
3. Önceki iş biterse yeni iş başlar.
4. Önceki iş bitmezse çağrı hata alır. Önbellekte geçerli eski anahtar varsa çağrı o anahtarı kullanır. Yoksa `JwksUnavailable` alır.
5. Toplam süre ilk ağ adımında başlar. Adres araması, bağlantı, şifreli bağlantı kurulumu, başlıklar ve gövde bu süreye girer.
6. Süre dolunca açık bağlantı kesilir.
7. Süresi dolan iş, adres araması bittikten sonra bağlantı açmaz.

## Bilinen sınır

Python adres aramasını kesemez. Bu yüzden takılan bir adres araması kendi süresi dolana kadar sürer.

En kötü durumda bir önbellekte bir indirme işi açık kalır. Yeni iş başlamaz. Açık iş, adres araması bitince bağlantı açmadan kapanır.

## Kanıt

Testler `backend/libs/oidc_verify/tests/test_jwks_total_deadline.py` dosyasındadır:

- `test_repeated_timeouts_keep_at_most_one_open_download`: art arda dört süre dolumunda en çok bir iş açık kalır.
- `test_expired_download_does_not_connect_after_name_resolution`: süresi dolan iş, adres araması bittikten sonra bağlantı açmaz.
- `test_total_deadline_covers_name_resolution` ve `test_total_deadline_covers_the_tls_handshake`: çağrı ve kilit süre dolunca serbest kalır.

## Geri dönüş

Bu davranış yalnız kitaplığın içindedir. Kitaplığın dış arayüzü değişmedi. Geri almak için `jwks.py` dosyasının önceki sürümü kullanılır.
