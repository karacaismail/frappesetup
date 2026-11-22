# Backend ajan talimatları

Bu klasör platformun sunucu kodunu tutar. Deponun kökündeki `AGENTS.md` karar sitesini anlatır. Backend işinde önce bu dosyayı uygulayın.

## Okuma sırası

1. Bu dosyayı okuyun.
2. [Proje kaydını](PROJE-KAYDI.md) okuyun. Seviye MVP'dir.
3. [Sözleşmeleri](docs/sozlesmeler.md) okuyun. Bileşenler bu adlarla konuşur.
4. Kod standartlarını okuyun. Standartlar `docs/standartlar/` klasöründedir.
   - Python kodunda `frappe-python-standartlari.md` dosyasını uygulayın.
   - Öteki dosyalarda `frappe-python-disi-standartlari.md` dosyasını uygulayın.
   - Giriş temasında `headless-frontend-standartlari.md` dosyasının güvenlik ve erişilebilirlik kurallarını da uygulayın.
5. Karar sitesinin ilgili sayfasını okuyun. Sayfalar `src/content/docs/` klasöründedir.
   - Keycloak için `rail-4-keycloak.md` dosyasını okuyun.
   - Press için `rail-1-press.md` dosyasını okuyun.
   - Kiracı sitesi için `rail-2-gelistirme.md` ve `rail-2-yapilandirma.md` dosyalarını okuyun.
   - Yapay zekâ için `rail-5-ai.md` ve `ai-*.md` dosyalarını okuyun. `ai-bakis.md` dosyası özet kararları verir.

Karar sitesi proje kaydıyla çelişebilir. Bu durumda proje kaydını uygulayın. Çelişkiyi raporunuza yazın.

## Klasörler ve sahipleri

Her klasörün tek sahibi vardır. Başka işin klasörünü değiştirmeyin. Değişiklik gerekirse raporunuzda isteyin.

| Klasör | İçerik | Sahip iş |
| --- | --- | --- |
| `dev/` | Geliştirme ortamı, betikler, ortak compose dosyası | dev-ortam |
| `dev/compose.keycloak.yaml` | Keycloak ve onun veritabanı | kimlik-realm |
| `dev/compose.press.yaml` | Press bench'i | press-tr |
| `apps/platform_core/` iskeleti | `hooks.py`, `pyproject.toml`, `modules.txt` | dev-ortam |
| `apps/platform_core/platform_core/kimlik/` | Giriş, çıkış, kimlik bağı, servis belirteci | platform-core-kimlik |
| `platform_core/api/__init__.py`, `api/auth.py`, `api/identity.py` | Kimlik uçları | platform-core-kimlik |
| `apps/platform_core/platform_core/kabuk/` | Açılış verisi ve DocType tanımı | platform-core-kabuk |
| `platform_core/api/shell.py`, `api/meta.py`, `www/panel.*` | Kabuk uçları ve `/panel` sayfası | platform-core-kabuk |
| `apps/platform_core/platform_core/yapay_zeka/` | Yapay zekâ erişim katmanı | platform-core-yz |
| `apps/platform_core/platform_core/model_gecidi/`, `api/model.py` | Sağlayıcı kaydı ve model geçidi | platform-core-gecit |
| `apps/press_tr/` | Press'in Türkiye uygulaması | press-tr |
| `identity/keycloak/realm/` | Realm tanımı | kimlik-realm |
| `identity/keycloak/themes/atonota/` | Atonota giriş teması | kimlik-tema |
| `identity/identity_sync/` | Kullanıcı eşitleme servisi | identity-sync |
| `libs/oidc_verify/` | Ortak belirteç doğrulama kitaplığı | kimlik-realm |
| `apps/platform_core/platform_core/erisim/`, `api/access.py` | Erişim kuralı motoru | erisim-kurali |
| `dev/guvenlik/`, `dev/bin/guvenlik-denetimi` | Güvenlik kapısı | guvenlik-kapisi |
| `apps/platform_core/platform_core/mobil/`, `api/mobile.py` | Telefon eşitlemesinin sunucu tarafı | platform-core-mobil |
| `contracts/` | Uçların OpenAPI sözleşmeleri | Her uç kendi sahibinde |
| `docs/`, `AGENTS.md`, `PROJE-KAYDI.md` | Talimat, kayıt ve sözleşme | Orkestratör |

`hooks.py` ortak bir dosyadır. Yalnız kendi işinizin satırlarını ekleyin. Var olan satırları değiştirmeyin.

## Zorunlu çalışma kuralları

### Seviye ve test

- Seviye MVP'dir. MVP kurallarını uygulayın. Örneğin modül sınırını otomatik denetleyin (B-10).
- Önce sözleşmeyi yazın (SZ-3). Uç değişince `contracts/` dosyasını da değiştirin.
- Önce testi yazın (D-2). Testin beklenen nedenle başarısız olduğunu görün ve kaydedin.
- Beklenen sonucu sözleşmeden ya da karar sitesinden alın (D-1). Değişen koddan kopyalamayın.
- Yetkiyi gerçek giriş yolunda sınayın (D-6). Ret durumunu da sınayın.

### Veri ve sırlar

- Gerçek kişi verisi kullanmayın. Yalnız uydurma örnek veri kullanın.
- Gerçek sırrı dosyaya, commit mesajına ve rapora yazmayın.
- Geliştirme sırlarını `.env` dosyasında tutun. `.env` Git'e girmez.
- `.env.example` aynı anahtarları sahte değerle taşısın.
- Dış servise gerçek istek atmayın. Örneğin Google, Apple ve iyzico için sahte ayar kullanın.

### Zamanlanmış iş yasağı

Proje sahibi `cron` kurulumunu istemedi. Bu yüzden şunları kurmayın:

- `scheduler_events` kaydı,
- zamanlanmış “Server Script”, “Auto Repeat” ya da “Auto Email Report”,
- belli aralıkla çalışan yoklama döngüsü,
- gece mutabakatı ya da saatlik yedek iş.

Karar sitesi bazı yerlerde saatlik ya da gecelik iş anar. Bu işleri elle başlatılan komut olarak yazın.

### Yapay zekâ erişimi

Proje sahibi her şeyin yapay zekâyla yönetilebilir olmasını istedi (D-9). Ayrıntı sözleşmenin 10. bölümündedir.

- Her DocType alanına `description` verin.
- Her uca OpenAPI açıklaması yazın.
- Elle başlatılan her komut için bir HTTP ucu da yazın.
- Model sağlayıcısı kitaplığı eklemeyin. Kodda model adı yazmayın.
- Yapay zekâya izin atlayan yol açmayın. Ham SQL ya da kabuk aracı yazmayın.

### Container kuralları

- Container ortamı Colima'dır. Docker Desktop kullanmayın.
- Komutlarda `docker --context colima-factory` kullanın. Bu Colima profili 64 GB bellek taşır.
- Başka projenin container'ına dokunmayın. Onları durdurmayın, silmeyin ve yeniden başlatmayın.
- Compose proje adını `fs-<iş adı>` biçiminde verin. Örneğin `fs-kimlik-realm` yazın.
- Ana bilgisayar portlarını yalnız `127.0.0.1` adresine bağlayın.
- Port tabanını `PANE_PORT` değişkeninden alın. Her Pane'in kendi 10 portluk aralığı vardır.
- İşiniz bitince kendi container'larınızı `docker compose down` ile kapatın. Birimleri silmeyin.

### Bilinen ortam sorunları

kimlik-realm işi 22 Kasım 2026 Pazar günü bu sorunları buldu. Çözümler öteki projelere dokunmaz.

1. **Klasör bağlama çalışmaz.** `colima-factory` profili yalnız `/Users/w6x/Developer/software-factory` klasörünü görür. Depo klasörünü bağlarsanız container'da boş klasör görünür. Kodu imaja `COPY` ile koyun ya da `docker cp` ile kopyalayın. Örnek: `backend/identity/keycloak/Dockerfile`.
2. **Yeni portlar bilgisayara açılmaz.** Profilin port yönlendirmesi bozuk. Portu bilgisayara ayrı bir ssh tüneliyle taşıyın. Örnek: `backend/identity/keycloak/bin/kc-dev.sh tunel`.
3. **`docker pull` hata verebilir.** Docker ayarındaki şifre yardımcısı eksik. İmajı boş bir `DOCKER_CONFIG` klasörüyle çekin. Kullanıcının Docker ayarını değiştirmeyin.
4. **Disk dar.** `colima-factory` profilinin Docker diski 22 Kasım 2026 Pazar günü %99 doldu. Kullanılmayan derleme önbelleği silindi. Boş yer yaklaşık 8 GB'tır.
   - Büyük imaj kurmadan önce `colima ssh -p factory -- df -h /var/lib/docker` ile boş yeri ölçün.
   - Frappe için yeni temel imaj üretmeyin. `frappe/erpnext:v16.55.0` ve `press-local-bench:latest` imajlarını temel alın.
   - Kendi eski `fs-*` imajlarınızı ve derleme önbelleğinizi silin. Başka projenin imajına dokunmayın.
   - Boş yer 5 GB'ın altına inerse raporlayın. Gerekirse `colima` profili kullanılır. O profilde 64 GB boş disk ama 8 GB bellek var.
5. **Colima'yı yeniden başlatmayın.** Kalıcı çözüm `colima restart factory` ister. Bu komut başka projelerin container'larını yeniden başlatır.


### Tarayıcı testi

- Firefox testi çalıştırmayın. Proje sahibinin kalıcı kuralı bunu yasaklar.
- Chromium ve WebKit kullanabilirsiniz.

### Git

- Yalnız kendi dalınızda çalışın. `main` ve `backend` dallarına yazmayın.
- Pane panelinde commit için şu biçimi kullanın:

  ```bash
  env -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL git commit -m "mesaj"
  ```

- `--no-verify` kullanmayın. Yazar korumasını ve `core.hooksPath` ayarını değiştirmeyin.
- Push yapmayın. Pull request açmayın. Dalları orkestratör birleştirir.
- Commit mesajını yalın Türkçe yazın. Yapay zekâ imzası ve ortak yazar satırı eklemeyin.

### Alt ajanlar

Proje sahibi çok sayıda paralel ajan istedi. Bu yüzden alt ajan kullanabilirsiniz. Alt ajan, sizin başlattığınız yardımcı ajandır.

- Birbirine bağlı olmayan işleri alt ajanlara bölün. Örneğin araştırma, test yazma ve bağımsız inceleme böyledir.
- İki alt ajana aynı dosyayı yazdırmayın.
- Alt ajanın sonucunu kendiniz doğrulayın. Testleri kendiniz çalıştırın.
- Alt ajan da bu dosyadaki kurallara uyar.
- Alt ajan sizin hesabınızın kullanım hakkını harcar. Gereksiz alt ajan açmayın.

### Yeni paket ve araç

- Önce Frappe'nin ve kurulu paketlerin hazır yolunu arayın (A-1, T-1).
- Yeni paket gerekiyorsa T-2 karar notu yazın. Not `docs/kararlar/` klasörüne girer.
- Notta ihtiyacı, seçenekleri, lisansı, bakımı ve geri dönüşü yazın.
- Paket açık kaynak lisanslıysa ve gerekçe yazılıysa ekleyebilirsiniz (D-10). AGPL lisanslı paketi `platform_core` içine almayın (O-12).

### Frappe davranışı

- Frappe ile ilgili her iddiayı kaynak kodda doğrulayın. Kaynağı container içindeki kurulumdan okuyun.
- Doğrulanan davranışı raporda dosya ve satırla yazın.
- Frappe'nin ve Press'in kodunu değiştirmeyin (M-4). Kanca ve kendi uygulamanızı kullanın.

## Rapor ve soru

Her çalışma parçasını tek komutla bitirin:

```bash
runpane report --state <ready|blocked|failed|done> --summary-file <durum dosyası>
```

- Durum dosyasını `.pane/prompts/durum.md` yoluna yazın. Bu klasör Git'e girmez.
- Durum dosyasına her denetimin komutunu ve sonucunu yazın. Sonuç `pass`, `fail`, `not_run` ya da `not_applicable` olur.
- Kontrol noktasında `ready` raporlayın. Orkestratör dalınızı inceler ve birleştirir.
- Rapordan sonra durmayın. Beklemeden sonraki kontrol noktasına geçin. Proje sahibi işin hiç durmamasını istedi.
- Bütün kontrol noktaları bitince `done` raporlayın. Orkestratör size yeni iş verir.
- Bir önkoşul henüz gelmediyse onu beklemeyin. O işe bağlı olmayan bölümü yapın. Örneğin testleri ve sözleşmeyi önce yazın.
- Proje sahibi kararları ajana bıraktı (D-10). Proje sahibine soru sormayın.
- Karar gerekiyorsa en güvenli ve en yalın seçeneği seçin. Kararı gerekçesiyle durum dosyasına ve gerekiyorsa `docs/kararlar/` notuna yazın. Sonra işe devam edin.
- Orkestratör kararı birleştirmede inceler. Gerekirse değiştirir.
- Yalnız şu durumda `blocked` raporlayın: iş ilerleyemiyor ve seçim geri alınamaz bir sonuç doğuruyor. Örneğin veri silme ya da dış servise yazma böyledir. Soruyu ve seçenekleri şöyle verin:

  ```bash
  runpane report --state blocked --question 'Soru metni' --choices '[{"label":"Seçenek","detail":"Sonucu","recommended":true},{"label":"Öteki seçenek","detail":"Sonucu"}]'
  ```

- Seçenekleri soru metnine parantezle yazmayın. Pane bu soruyu reddeder.
- Sorunun beklemediği işi sürdürün.

## Yazım

- Belgeleri ve raporları yalın Türkçe yazın. Kısa ve tam cümle kurun.
- Terimi ilk geçtiği yerde açıklayın.
- Türkçe metni teslimden önce denetleyin:

  ```bash
  node ~/.claude/skills/coding-standards/scripts/yalin-turkce-denetim.mjs dosya.md
  ```

- Depo herkese açıktır. Kişi adı, e-posta ve özel bilgi yazmayın. Rolleri adıyla değil göreviyle yazın.
