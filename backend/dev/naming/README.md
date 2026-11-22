# Ad geçişi

## İkinci kontrol noktası

Orkestratör, geçiş onayı gelince Pane oturumundan çalışır.
Depo kökünde Python 3.14 kullanır. İlk denemede kapı `advisory` kipinde kalır.

### 1. Taban dalını hazırlama

Orkestratör, geçiş onayı gelince önce `backend` dalını hazırlar.
Sürücü `backend` ve `main` kopyalarında Git kaydı oluşturmaz.
Karar notunun “Orkestratör” bölümündeki komutları kullanın.
Notu geçişten önce `backend/docs/kararlar/0009-naming-history-fix.md` yolunda bulursunuz.
Geçişten sonra not `backend/docs/decisions/0009-naming-history-fix.md` yoluna taşınır.
O bölüm, belge yamasını, ad betiğini ve denetimleri sırayla çalıştırır.
Yama `backend/dev/naming/docs-rename.patch` yolundadır.
Denetim kalırsa taban kaydını oluşturmayın.
İşçi dalları bu tabanı alınca 2. adımdaki denemeyi çalıştırın.

### 2. Kuru çalıştırma

Orkestratör depo kökünde şu komutu çalıştırır.

```sh
python3.14 -B backend/dev/naming/run_cp2.py > "$PANE_SCRATCH_DIR/cp2-dry.json"
```

Orkestratör rapordaki `backend` ve `head` kayıtlarını kontrol eder.
Sürücü yalnız Git'te kayıtlı içeriği kopyalar. Bekleyen yerel düzenlemeleri almaz.
Sürücü `backend/dev/tests` testlerini çalıştırır. Gerekirse test komutunu `--` sonrasına yazın.
Rapor durma nedenini gösterir. Bir dal eksikse veya test kalırsa sahibi durma nedenini bildirir.
Sürücü hata varsa 1 koduyla çıkar. Diğer dalların sonucu da aynı raporda kalır.
Eski modül atfı kalırsa işçi dosya ve satırı adlandırma işine bildirir.
İşçi eski adı elle değiştirmez. Adlandırma işi dar kuralı hazırlar.
Kuru çalıştırma kopyaları sonunda silinir.

### 3. Geçici Git kayıtlarını oluşturma

Orkestratör denetimler geçince depo kökünde şu komutu çalıştırır.

```sh
python3.14 -B backend/dev/naming/run_cp2.py --apply > "$PANE_SCRATCH_DIR/cp2-apply.json"
```

Sürücü Git kayıtlarını geçici kopyalarda oluşturur.
Rapordaki `copies` alanı bu kopyaların ana klasörüdür.
Orkestratör her dalın kendi testlerini ilgili kopyada tamamlar.
Sonuçta hata varsa o dalın kaydını taşımaz.

### 4. Onaylı kaydı işçi dalına taşıma

Orkestratör raporda `passed` olan dalın çalışma ağacını açar.
`commit` alanı boşsa taşınacak yeni kayıt yoktur.
Rapordaki `branch` değerini `cp2_branch` değişkenine koyun.
Rapordaki `head` değerini `cp2_head` değişkenine koyun.
Rapordaki `copy` ve `commit` değerlerini `cp2_copy` ve `cp2_commit` değişkenlerine koyun.
Çalışma ağacı temizse ve son kayıt değişmediyse şu komutları çalıştırın.

```sh
test -z "$(git status --porcelain=v1 --untracked-files=all)" &&
test "$(git branch --show-current)" = "$cp2_branch" &&
test "$(git rev-parse HEAD)" = "$cp2_head" &&
git fetch --no-tags "$cp2_copy" "$cp2_commit" &&
env -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL git cherry-pick "$cp2_commit" &&
cp2_target_commit="$(git rev-parse HEAD)"
```

Geri dönüş için `cp2_target_commit` değerini rapora yazın.
Dal ucu değiştiyse yeni kopyayla 2. adıma dönün.
Yalnız bütün dallar ve kapı hazır olunca orkestratör `enforce` kipini açar.

### 5. Geri dönüş

Kuru çalıştırmadan sonra geri alma gerekmez. Sürücü kopyaları zaten siler.
Kaydı işçi dalına taşımadıysanız `copies` yolundaki geçici kopyaları kaldırın.
Kaydı taşırken çakışma çıkarsa `git cherry-pick --abort` çalıştırın.

Kayıt taşındıysa ilgili daldaki geçiş kaydını geri alın.
Önce çalışma ağacının temiz olduğunu doğrulayın.
`cp2_target_commit` için o dalda kaydettiğiniz değeri kullanın.
Kapı `enforce` kipindeyse, orkestratör geri dönüşten önce `advisory` kipini açar.

```sh
test -z "$(git status --porcelain=v1 --untracked-files=all)" &&
test "$(git branch --show-current)" = "$cp2_branch" &&
env -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL git revert "$cp2_target_commit"
```

Geri alma çakışırsa `git revert --abort` çalıştırın.
Geri alma sonrası dal testlerini yeniden çalıştırın.
