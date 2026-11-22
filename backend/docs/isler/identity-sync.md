# İş: identity-sync

Bu iş kullanıcı eşitleme servisinin teknoloji kararını hazırlar. Servisin çekirdek mantığını da yazar. Servis Keycloak'taki kullanıcı değişikliklerini Press'e ve kiracı sitelerine taşır (G-81).

Önce `backend/AGENTS.md`, `backend/PROJE-KAYDI.md` ve `backend/docs/sozlesmeler.md` dosyalarını okuyun. Sonra karar sitesinin `rail-4-keycloak.md` sayfasının 4. bölümünü okuyun.

## Sahip olduğunuz yerler

- `backend/identity/identity_sync/`
- `backend/contracts/identity_sync.openapi.yaml`
- `backend/docs/kararlar/0001-identity-sync.md`

## Önemli kısıt

Zamanlanmış iş yasaktır (Proje kaydı D-6). Karar sitesi saatlik yoklama ve gece mutabakatı anar. Bu ikisini kurmayın. Olaylar ya Keycloak'tan gelir ya da bizim işlemimizle başlar. Mutabakat elle başlatılan bir komuttur.

## Kontrol noktası 1: teknoloji kararı

1. T-2 karar notunu `backend/docs/kararlar/0001-identity-sync.md` dosyasına yazın.
2. Notta şu soruları cevaplayın:
   - Servis hangi dilde ve sürümde yazılır? Python 3.11 ve sonrası önerilir. Ekip ikinci dil eklemesin (T-1).
   - HTTP sunucusu için yeni paket gerekir mi? Python'un kendi kitaplığı yeter mi?
   - Keycloak olayları servise nasıl gelir?
3. Olay kaynağı için seçenekleri karşılaştırın:
   - açık kaynak bir Keycloak olay eklentisi,
   - kendi yazdığımız Java eklentisi,
   - eklentisiz yol: Press'te ilk girişte takım açma, davette bizim çağrımız, elle mutabakat.
4. Her eklenti için lisansı, bakımı, son sürümü ve Keycloak 26.8 uyumunu yazın. Yalnız açık kaynak lisansları kabul edin. Örneğin “Elastic License” açık kaynak değildir.
5. En yalın açık kaynak seçeneği seçin ve notta gerekçesini yazın (D-10, O-11). Soru sormayın.
6. Commit atın ve 2. kontrol noktasına geçin.

## Kontrol noktası 2: çekirdek mantık

Bu bölümde yeni paket kullanmayın. Yalnız Python'un kendi kitaplığını kullanın.

1. Önce `contracts/identity_sync.openapi.yaml` dosyasını yazın.
2. Olay ile eylem eşlemesini saf işlev olarak yazın. Saf işlev ağa ve veritabanına dokunmaz. Eşleme şu olayları kapsasın:
   - kayıt ve e-posta doğrulama,
   - e-posta değişikliği,
   - hesabın silinmesi ve kapatılması,
   - yöneticinin kullanıcıyı değiştirmesi,
   - Organization üyeliğinin değişmesi.
3. Her işlem tekrar edilebilir olsun. Aynı olay iki kez gelirse sonuç değişmesin.
4. Başarısız olay ayrı kuyrukta beklesin. Kuyruğu elle yeniden işleten bir komut yazın.
5. Keycloak Admin API istemcisini yazın. İstemci şunları yapsın:
   - Organization açar ve kullanıcıyı ekler,
   - davet e-postasını `execute-actions-email` ile gönderir,
   - `site-<kiracı>` istemcisini ve sırrını açar.
6. Press ve kiracı uçlarının istemcilerini sözleşmenin 5. ve 6. bölümüne göre yazın.
7. Mutabakat komutunu yazın. Komut Keycloak, Press ve kiracı kullanıcılarını karşılaştırsın. Komut yalnız farkı raporlasın.
8. Testleri önce yazın. Ağ çağrılarını sahte sunucuyla sınayın.
9. Commit atın ve `ready` raporlayın.

## Kapsam dışı

- Canlı Keycloak ile bütünleşme testi, realm birleştirildikten sonra yapılır.
- Servisin container dosyası T-2 onayından sonra yazılır.
- Sırları depoya yazmayın. Servis sırları ortam değişkeninden okusun.
