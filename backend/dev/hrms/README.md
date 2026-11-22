# CronHR geliştirme ortamı

Bu komutlar depoda, ayrı bir test sitesi kurar.
Platform Core, “Access Rule” kayıt türünü sağlamalıdır.
Yapay zekâ testi için Platform Core yapay zekâ uçlarını da sağlamalıdır.

1. Colima diskinde boş yeri ölçün.

   ```sh
   colima ssh -p factory -- df -h /var/lib/docker
   ```

2. Depo kökünden iki imajı derleyin.

   ```sh
   docker --context colima-factory build -t fs-tenant-dev:v16.55.0 -f backend/dev/Dockerfile.tenant backend
   docker --context colima-factory build -t fs-ilk-dikey-dilim:cronhr -f backend/dev/hrms/Dockerfile backend
   ```

3. `.env.example` dosyasını aynı klasöre `.env` adıyla kopyalayın.
   Örnek parolaları yeni test parolalarıyla değiştirin.
4. Veritabanını ve Redis hizmetini başlatın. Ardından test sitesini kurun.

   ```sh
   backend/dev/hrms/compose up -d --wait tenant-db tenant-redis
   backend/dev/hrms/compose run --rm web env/bin/python /workspace/dev/bootstrap.py \
     test-cronhr.localhost --app hrms --app platform_core --app cronhr
   backend/dev/hrms/compose up -d web
   ```

5. Uydurma kayıtları ekleyin. Testleri web konteynerinde çalıştırın.

   ```sh
   backend/dev/hrms/compose exec -T web env/bin/python /workspace/hrms/seed.py \
     --site test-cronhr.localhost --manifest /tmp/cronhr-manifest.json
   backend/dev/hrms/compose exec -T web sh -c \
     'env/bin/python /workspace/hrms/test_http.py --url "http://127.0.0.1:$TENANT_WEB_PORT" \
      --site test-cronhr.localhost --manifest /tmp/cronhr-manifest.json --with-ai'
   ```

   Yapay zekâ katmanı eksikse `--with-ai` seçeneğini çıkarın.
   Test, taslak durumunu değiştirir. Her tam koşu için boş test sitesi kullanın.

6. Test ortamını kapatın. Compose veritabanı birimini saklar.

   ```sh
   backend/dev/hrms/compose down
   ```
