# İş: ilk-dikey-dilim

Bu iş yol haritasındaki ilk dikey dilimin backend'ini hazırlar. Dilim “İzin talebi” (Leave Application) akışıdır. Akış bütün katmanlardan uçtan uca geçer. Ayrıntı karar sitesinin `yol-haritasi.md` sayfasının “İlk dikey dilim” bölümündedir.

Önce şu dosyaları okuyun:

1. `backend/AGENTS.md`
2. `backend/PROJE-KAYDI.md`
3. `backend/docs/sozlesmeler.md`
4. Karar sitesinde `yol-haritasi.md`, `app-cercevesi.md` ve `kararlar.md` (K10)

## Sahip olduğunuz yerler

- `backend/apps/cronhr/`
- `backend/dev/hrms/`
- `backend/contracts/cronhr.openapi.yaml`
- `backend/docs/kararlar/0008-ilk-dikey-dilim.md`

## Kararlar

- CronHR ayrı bir Frappe uygulamasıdır. Uygulama `frappe/hrms` uygulamasının `version-16` dalına dayanır (K10).
- `hrms` GPL-3.0 lisanslıdır. `cronhr` hrms'i aynı süreçte kullanır. Bu yüzden `cronhr` lisansı GPL-3.0 olur (O-16). Hukuk görüşü alınmadı.
- Gerçek bordro hesabı bu işte yoktur. Türkiye bordro kuralları mali müşavir onayı ister.

## Kontrol noktası 1: tasarım ve ortam

1. Tasarım notunu yazın. Notta şu sorular cevaplansın:
   - Roller nelerdir? Örneğin `CronHR Employee`, `CronHR Manager` ve `CronHR HR` (G-104).
   - Erişim kuralları nasıl kurulur? Çalışan kendi izinlerini görür. Yönetici `reports_to` ekibini görür. İK hepsini görür.
   - `leave_balance` alanı izin seviyesiyle nasıl kapanır?
   - Kenar çubuğu “Workspace” kaydından nasıl türer (G-94)?
   - Yapay zekâ aracı `cronhr_approve_leave` nasıl çalışır? Araç önizleme üretir ve insan onayı ister (G-129).
2. `backend/dev/hrms/` altında hrms'i ekleyen geliştirme imajını yazın. Temel imaj `backend/dev/Dockerfile.kiraci` dosyasının ürettiği imajdır. hrms sürümünü tam etiketle sabitleyin.
3. Diski ölçün. Boş yer 5 GB'ın altındaysa raporlayın.
4. Commit atın ve `ready` raporlayın.

## Kontrol noktası 2: uygulama

1. `cronhr` iskeletini `bench new-app cronhr --no-git` ile üretin. `required_apps` listesine `hrms` ekleyin.
2. Rolleri ve “Role Profile” kayıtlarını ön ekli fixture olarak yazın.
3. Erişim kuralı şablonlarını yazın. Şablonlar erisim-kurali işinin “Access Rule” DocType'ını kullanır. O iş birleşmediyse şablonları ayrı dosyada hazırlayın ve testi `not_run` yazın.
4. `cronhr_approve_leave` aracını `ai_tools` kancasıyla bildirin. Biçim `contracts/platform_core-yapay-zeka.openapi.yaml` dosyasının `x-ai-tools-hook` bölümündedir. platform-core-yz birleşmediyse aracı hazırlayın ve testi `not_run` yazın.
5. Testler gerçek HTTP isteğiyle şunları göstersin:
   - çalışan yalnız kendi izin talebini görür,
   - yönetici ekibinin taleplerini görür ve onaylayabilir,
   - `leave_balance` alanı yetkisiz kullanıcıya dönmez,
   - yapay zekâ aracı onaysız yazmaz.
6. Örnek veriyi uydurma kişilerle hazırlayın. Alan adı `example.test` olsun.
7. Commit atın ve `done` raporlayın.

## Kapsam dışı

- Panel ekranı ve URL'leri sonraki turdadır.
- Destek prototipi (SA-40) bu işte yoktur.
- Bordro, SGK ve vergi hesabı yoktur.
