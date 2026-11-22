# Devir notu: `main` dalı için koruma kuralı

Bu not 22 Kasım 2026 Pazar günü yazıldı.

Not DevOps sorumlusu içindir.

## Durum

`karacaismail/frappesetup` deposunda `main` dalı korumasızdır. GitHub “Branch not protected” yanıtı veriyor. Depoda kural seti de yoktur.

Bu yüzden “zorunlu test” bugün yalnız yerel kapı betiğinde tanımlıdır. Betik `ci.yml` içindeki `build-and-test` işinin geçmesini ister.

`ci.yml` ve `deploy.yml` dosyalarına dokunulmadı.

## Birleştirme yolu

PR'lar GitHub düğmesiyle birleştirilmez. GitHub birleştirmesi committer alanına GitHub yazar. Bu, yazar kuralına aykırıdır.

Kapı betiği CI geçince `main` dalını PR'ın son commit'ine hızlı ileri alır. Bu iş zorlamasız bir `git push` ile yapılır. Yeni commit oluşmaz.

## İstenen ayar

Aşağıdaki kuralı bir kural seti olarak `main` dalına ekleyin:

1. `build-and-test` denetimini zorunlu yapın.
2. Zorla push etmeyi engelleyin.
3. Dal silmeyi engelleyin.
4. Doğrusal geçmiş isteyin.

“Require a pull request before merging” kuralını açmayın. Bu kural hızlı ileri push'u engeller. Açmak gerekirse depo sahibine atlama izni verin.

## Kabul ölçütü

1. Zorla push reddedilir.
2. CI'ı geçmemiş bir commit `main` dalına push edilemez.
3. CI'ı geçmiş PR commit'i hızlı ileri push ile `main` dalına alınır.
4. GitHub PR'ı “Merged” olarak gösterir.
