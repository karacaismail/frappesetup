# HRMS TR geliştirme ortamı

Bu komutlar depoda, ayrı bir test sitesi kurar.
Platform Core, “Access Rule” kayıt türünü sağlamalıdır.
Yapay zekâ testi için Platform Core yapay zekâ uçlarını da sağlamalıdır.

Factory profilinde yalnız mevcut imajı ve test sitesini kullanın.
Factory profilinde imaj derlemeyin veya yeni site açmayın.
Yeni ortam gerekiyorsa aşağıdaki adımları izleyin.

1. Varsayılan Colima profilinde boş belleği ölçün.

   ```sh
   colima ssh -- free -g
   ```

   `available` sütununda en az 2 GB bellek varsa devam edin.
   Yeni ortam için profili seçin.

   ```sh
   export FS_COLIMA_PROFILE=default
   ```

2. Depo kökünden mevcut imajları kullanın. Eksik imajı varsayılan profilde derleyin.

   ```sh
   docker --context colima image inspect fs-kiraci-dev:v16.55.0 >/dev/null 2>&1 ||
     docker --context colima build -t fs-kiraci-dev:v16.55.0 -f backend/dev/Dockerfile.kiraci backend
   docker --context colima image inspect fs-ilk-dikey-dilim:hrms_tr >/dev/null 2>&1 ||
     docker --context colima build -t fs-ilk-dikey-dilim:hrms_tr -f backend/dev/hrms/Dockerfile backend
   ```

3. `.env.example` dosyasını aynı klasöre `.env` adıyla kopyalayın.
   Örnek parolaları yeni test parolalarıyla değiştirin.
4. Veritabanını ve Redis hizmetini başlatın. Ardından test sitesini kurun.

   ```sh
   backend/dev/hrms/compose up -d --no-build kiraci-db kiraci-redis
   backend/dev/hrms/compose run --rm web env/bin/python /workspace/dev/bootstrap.py \
     test-hrms-tr.localhost --app hrms --app platform_core --app hrms_tr
   backend/dev/hrms/compose up -d --no-build web
   ```

5. Uydurma kayıtları ekleyin. Testleri web konteynerinde çalıştırın.

   ```sh
   backend/dev/hrms/compose exec -T web env/bin/python /workspace/hrms/seed.py \
     --site test-hrms-tr.localhost --manifest /tmp/hrms_tr-manifest.json
   backend/dev/hrms/compose exec -T web sh -c \
     'env/bin/python /workspace/hrms/test_http.py --url "http://127.0.0.1:$KIRACI_WEB_PORT" \
      --site test-hrms-tr.localhost --manifest /tmp/hrms_tr-manifest.json --with-ai'
   ```

   Yapay zekâ katmanı eksikse `--with-ai` seçeneğini çıkarın.
   Test, taslak durumunu değiştirir. Her tam koşu için boş test sitesi kullanın.

6. Deneme bitince yalnız bu işin geçici sitesini ve veri birimlerini silin.
   Komut bu Compose projesinin test verisini siler. Aynı anda bir test sitesi açık tutun.

   ```sh
   backend/dev/hrms/compose down --volumes
   ```

## Yerel yükseltme denemesi

Yalnız bu işe ait test sitesini yükseltin.
Siteyi yükselttikten sonra Frappe'nin rol kuyruğunu boşaltın.
Yerel ortamda bu kuyruğu sürekli işleyen bir hizmet yoktur.

```sh
backend/dev/hrms/compose exec -T web bench --site test-hrms-tr.localhost migrate --skip-search-index
backend/dev/hrms/compose exec -T web bench worker --queue long --burst
```

İkinci yükseltme denemesinden önce ilk kuyruğun bitmesini bekleyin.

## O-31 performans ölçümü

Güncel HRMS TR imajıyla boş bir `perf-hrms-tr.localhost` sitesi kurun.
Site ayarında `allow_performance_fixture` değerini sayı olarak 1 yapın.
Kuyrukta bekleyen veya çalışan iş varsa komut veri oluşturmadan durur.
Ölçüm komutu 200 çalışan ve 2.000 izin kaydı üretir.

```sh
backend/dev/hrms/measure perf-hrms-tr.localhost .pane/prompts/durum.md
```

Komut her yolu 50 kez çağırır. Onay ve iptal aynı 50 test kaydında çalışır.
Ölçüm Frappe’nin yanıtı üretme süresini kapsar. Ağ ve hazırlık süreleri dışarıda kalır.
Okuma sınırı 500 ms, yazma sınırı 1.000 ms’dir. Sınırlar p95 için geçerlidir.
p95, ölçülen çağrıların yüzde 95’inin tamamlandığı süredir.
Komut tabloyu durum dosyasına ekler. Bir sınır aşılırsa komut başarısız olur.
Komut, ölçümde kullandığı izin ve devam kayıtlarını türü ve adıyla seçip siler.
Onaylı kalmış kayıtlar ve kurulum verisi geçici sitede kalır.
Ölçüm bitince geçici siteyi silin.
Tekrar ölçüm için yeni ve boş bir site kullanın.
