# DevOps runbook: repo taşıma ve takılı dal

Sahibi: Team B DevOps

Bu belge 28 Kasım 2026 Cumartesi günü yazıldı. Team A DevOps belgeyi okur.

Belgede iki bölüm var:

1. Repo taşıma kontrol listesi.
2. Takılı dal runbook'u.

## Kısa sözlük

- Runbook, adım adım uygulanan iş belgesidir.
- Kurulum numarası, GitHub uygulamasının bir hesaba kurulduğu kaydın numarasıdır. ProPR'da bu numaranın adı `GH_INSTALLATION_ID` olur.
- ProPR kopyası, ProPR'ın repoların kendine aldığı kopyasıdır. Kopya `propr-worker` adlı container içinde durur.
- Container, tek bir servisi ayrı çalıştıran kutudur.
- Yedek dosyası (`.bundle`), bir dalı bütün commit'leriyle saklayan dosyadır.

## Bu belgenin sınırları

- DevOps kontrol eder ve sonucu yazar.
- DevOps ProPR ayarını değiştirmez. Örneğin `.env` dosyasına yazmaz.
- DevOps havuz ayarını ve canlı sunucuyu değiştirmez.
- Ayar değişikliği gerekirse DevOps RTE'ye yazar. RTE işi orkestratöre iletir.
- Belgeye, yoruma ve sohbete sır yazılmaz. Kurulum numarasının değeri de yazılmaz.
- Codex açılmaz. Cron kurulmaz.

## Docker komutları için ortak ayar

ProPR kendi Colima profilinde çalışır. Profilin adı `propr` olur. Docker komutlarından önce bu iki satırı çalıştırın:

```bash
export DOCKER_CONFIG=~/.config/propr-docker
export DOCKER_HOST=unix://$HOME/.colima/propr/docker.sock
```

Bu iki satır olmazsa komut başka bir Colima profiline gider.

## 1. Repo taşıma kontrol listesi

### Liste ne zaman kullanılır

Şu durumlardan biri olunca listeyi baştan sona uygulayın:

- Bir repo başka bir hesaba ya da kuruluşa taşındı.
- Bir reponun adı değişti.
- GitHub uygulaması başka bir hesaba kuruldu.
- GitHub uygulaması kaldırılıp yeniden kuruldu.

27 Kasım 2026 Cuma günü repolar `metafrappe` kuruluşuna taşındı. ProPR'daki kurulum numarası eski kaldı. Bu yüzden iki takım durdu. Bu liste o sorunun tekrarını önler.

### Madde 1: ProPR'daki kurulum numarası

ProPR'daki numara, GitHub'daki numarayla aynı olmalı.

GitHub'daki numarayı bulun:

1. Uygulamanın kurulu olduğu hesabın sayfasını açın. Kuruluş için adres `https://github.com/organizations/<kuruluş>/settings/installations` olur.
2. Kişisel hesap için adres `https://github.com/settings/installations` olur.
3. ProPR uygulamasının satırında "Configure" düğmesine basın.
4. Adres çubuğunun sonundaki sayıya bakın. Bu sayı kurulum numarasıdır.

ProPR'daki numarayı denetleyin. Numara şu dosyadadır:

```text
~/Library/Application Support/ProPR Desktop/local-runtime/.env
```

Dosyayı ekrana basmayın. Dosyada sırlar da vardır. Bunun yerine şu komutla karşılaştırın:

```bash
E="$HOME/Library/Application Support/ProPR Desktop/local-runtime/.env"
grep -c "^GH_INSTALLATION_ID=<GitHub'daki sayı>$" "$E"
```

`<GitHub'daki sayı>` yazısının yerine 4. adımdaki sayıyı yazın.

- Çıktı `1` ise numara doğrudur.
- Çıktı `0` ise numara eskidir. Durumu RTE'ye yazın. Numarayı kendiniz değiştirmeyin.

Aynı yolla uygulama numarasını da denetleyin. ProPR'da adı `GH_APP_ID` olur. GitHub'da uygulamanın "General" sayfasında "App ID" olarak yazar.

### Madde 2: eski repoların izlemesi

Taşınan reponun eski adresi ProPR'da izlenmemeli. İzlenirse ProPR her işte eski adrese gider. İşler "Resource not accessible" hatasıyla düşer.

Nereden kontrol edilir:

1. ProPR arayüzünde repo listesini açın.
2. Eski adresli her reponun satırına bakın.
3. Eski repoda "Monitor" anahtarı kapalı olmalı.
4. Yeni repoda "Monitor" anahtarı açık olmalı.

28 Kasım 2026 Cumartesi günü iki eski repo kapatıldı. Repolar `karacaismail/frappesetup` ve `karacaismail/atonota-web` idi.

Anahtar yanlış durumdaysa RTE'ye yazın. Anahtarı kendiniz değiştirmeyin.

ProPR kopyasında hangi sahiplerin klasörü olduğunu bu komut gösterir:

```bash
docker exec propr-worker ls /tmp/git-processor/clones
```

Eski sahibin klasörü kalabilir. Klasörü silmeyin.

### Madde 3: uygulamanın yeni repolara erişimi

GitHub uygulaması yeni repoları görebilmeli.

Nereden kontrol edilir:

1. Madde 1'deki kurulum sayfasında "Configure" düğmesine basın.
2. "Repository access" bölümüne bakın.
3. "All repositories" seçiliyse erişim tamamdır.
4. "Only select repositories" seçiliyse her yeni repo listede olmalı.

Bir repo listede yoksa RTE'ye yazın. Listeyi kendiniz değiştirmeyin.

Yeni reponun adresini de denetleyin:

```bash
gh api repos/<sahip>/<repo> --jq .full_name
```

Çıktı yeni adresi göstermeli. Örnek çıktı `metafrappe/backend` olur.

### Madde 4: branch koruması ve auto-merge ayarı

Taşınan repoda `main` dalı korumalı olmalı. Auto-merge ayarı da açık olmalı.

Branch korumasını denetleyin:

1. Reponun `https://github.com/<sahip>/<repo>/settings/branches` sayfasını açın.
2. Kural seti varsa `https://github.com/<sahip>/<repo>/settings/rules` sayfasına da bakın.
3. Zorunlu denetimlerin adlarını komutla okuyun:

```bash
gh api repos/<sahip>/<repo>/branches/main/protection --jq '.required_status_checks.contexts'
```

4. Zorunlu denetim adları reponun CI iş adlarıyla aynı olmalı. CI iş adları `.github/workflows/` klasöründeki dosyalarda yazar. Örneğin `metafrappe/frontend` reposunda iki zorunlu denetim var: "Lint, typecheck ve birim testleri" ve "Playwright".
5. Zorla push kapalı olmalı. Aynı komutta `--jq '.allow_force_pushes.enabled'` yazın. Çıktı `false` olmalı.
6. Dal silme kapalı olmalı. Aynı komutta `--jq '.allow_deletions.enabled'` yazın. Çıktı `false` olmalı.

Komut "Branch not protected" yanıtı verirse dal korumasızdır. Durumu RTE'ye yazın.

Auto-merge ayarını denetleyin:

1. Reponun `https://github.com/<sahip>/<repo>/settings` sayfasını açın.
2. "Allow auto-merge" kutusu seçili olmalı.
3. Aynı bilgiyi komutla da okuyabilirsiniz:

```bash
gh api repos/<sahip>/<repo> --jq .allow_auto_merge
```

Çıktı `true` olmalı.

`auto-merge` etiketini denetleyin. ProPR bu etiketi gördüğü PR için otomatik birleştirmeyi kurar.

```bash
gh label list -R <sahip>/<repo> --search auto-merge
```

Çıktıda `auto-merge` etiketi görünmeli. Etiket yoksa RTE'ye yazın.

### Listenin sonucu

Her madde için sonucu iş kaydına yazın. Örnek:

- Madde 1: uygun.
- Madde 2: uygun.
- Madde 3: fark var. `metafrappe/safeboard` listede yok.
- Madde 4: uygun.

Fark varsa ayrıntıyı RTE'ye yazın. Sır ve kurulum numarasının değerini yazmayın.

## 2. Takılı dal runbook'u

### Belirti

ProPR bir dalda çalışamaz. Kayıtta şu hata görünür:

```text
Cannot create worktree: Local branch '<dal>' has <sayı> commit(s) that are not on origin/<dal>
```

Hatayı iki yerde görebilirsiniz:

1. ProPR, PR'a bir yorum yazar. Yorumun başı "Failed to" ile başlar. Yorumun içinde aynı hata vardır.
2. ProPR'ın iş kaydında da aynı hata vardır. Kaydı şu komut süzer:

```bash
docker logs --since 24h propr-worker 2>&1 | grep -F "not on origin"
```

Kayıtta dalın adı, commit sayısı ve son commit (`local tip`) yazar.

### Neden olur

ProPR kopyasındaki dalda GitHub'a gönderilmemiş commit'ler vardır. ProPR bu commit'leri silmez. ProPR bu commit'leri GitHub'a da göndermez. Bu yüzden iş durur.

27 Kasım 2026 Cuma günü `metafrappe/backend` reposunda bu oldu. `ci/aja1721-pip-hash` dalında 6 commit vardı. Commit'ler eski bir birleştirme denemesiydi. PR 35 bu yüzden takıldı.

### Kurallar

- Dalı silmeyin.
- Zorla push etmeyin.
- Takılı commit'leri GitHub'a göndermeyin.
- Bir adım hata verirse durun. Hatayı RTE'ye yazın.

### Hazırlık

Docker için ortak ayarı çalıştırın. Sonra değişkenleri yazın:

```bash
R=/tmp/git-processor/clones/<sahip>/<repo>
D=<dal>
T=$(date +%Y-%m-%d)
Y="yedek/$(printf '%s' "$D" | tr / -)-$T"
```

`<sahip>/<repo>` yerine reponun adını yazın. Örnek `metafrappe/backend` olur. `<dal>` yerine hatadaki dal adını yazın.

Takılı commit'leri görün:

```bash
docker exec propr-worker git -C "$R" log --oneline "origin/$D..$D"
```

Çıktıdaki commit sayısı hatadaki sayıyla aynı olmalı.

### Adım 1: Dalı yedekleyin

1. Yedek dosyasını container içinde oluşturun:

```bash
docker exec propr-worker git -C "$R" bundle create /tmp/takili-dal.bundle "refs/heads/$D"
```

2. Yedek dosyasını Mac'e alın:

```bash
docker cp propr-worker:/tmp/takili-dal.bundle ~/Documents/paperclip-yedek/"$(basename "$R")-takili-dal-$T.bundle"
```

3. Container içindeki geçici dosyayı silin:

```bash
docker exec propr-worker rm /tmp/takili-dal.bundle
```

4. Yedeği denetleyin:

```bash
git bundle list-heads ~/Documents/paperclip-yedek/"$(basename "$R")-takili-dal-$T.bundle"
```

Çıktıda dal adı görünmeli. Satırın başındaki commit, hatadaki `local tip` ile aynı olmalı.

Yedekler `~/Documents/paperclip-yedek/` klasöründe durur. Örnek yedek `pr35-takili-dal-2026-11-28.bundle` dosyasıdır.

### Adım 2: Dalın adını yedek adına çevirin

1. Dalın adını değiştirin:

```bash
docker exec propr-worker git -C "$R" branch -m "$D" "$Y"
```

2. Yeni adı denetleyin:

```bash
docker exec propr-worker git -C "$R" branch --list "$Y" "$D"
```

Çıktıda yalnız yedek adı görünmeli. Eski ad görünmemeli.

Komut "checked out" hatası verirse durun. Dal bir çalışma kopyasında açıktır. Hatayı RTE'ye yazın.

Örnek yedek adı `yedek/ci-aja1721-pip-hash-2026-11-28` olur.

### Adım 3: İşi yeniden başlatın

1. Takılı PR'ı GitHub'da açın.
2. ProPR'ın hatadan önce istenen komutunu bulun.
3. Aynı komutu PR'a yeni yorum olarak yazın. Örneğin çakışma çözümü için komut `/merge` olur.
4. ProPR işi yeniden alır. Bu kez dalı GitHub'dan yeniden açar.

Sonucu denetleyin:

- ProPR PR'a yeni bir yorum yazar.
- Yorumda "Cannot create worktree" hatası olmamalı.
- Şu komut yeni bir hata satırı göstermemeli:

```bash
docker logs --since 1h propr-worker 2>&1 | grep -F "not on origin"
```

Hata yeniden çıkarsa durun. Durumu RTE'ye yazın.

### Kayıt

İş bitince iş kaydına şunları yazın:

- reponun ve dalın adı,
- yedek dosyasının adı,
- yedek dalın adı,
- yeniden yazılan komut ve PR numarası.
