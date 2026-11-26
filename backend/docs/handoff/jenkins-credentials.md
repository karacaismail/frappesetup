# Jenkins kimlik kayıtları

Bu not DevOps sorumlusu içindir.
Notta Jenkins'te açılacak kimlik kayıtlarının adları vardır.
Kayıtların değerleri bu notta yoktur.
Değerleri yalnız Jenkins'e girin. Değerleri depoya, yoruma ve Jenkinsfile dosyasına yazmayın.

Jenkinsfile gizli değeri yalnız kayıt adıyla okur.
Örneğin `withCredentials([usernamePassword(credentialsId: 'atonota-registry', ...)])` ya da `sshagent(credentials: [...])` kullanılır.
`backend/deploy/tests/test_jenkins_gates.py` bu listeyi Jenkinsfile dosyalarıyla karşılaştırır.
Yeni kayıt adı gelirse tabloya satır ekleyin.

## Kayıtlar

| Kayıt adı | Türü | Jenkins klasörü | Ne için |
| --- | --- | --- | --- |
| `atonota-registry` | Kullanıcı adı ve parola | `atonota-delivery` | GHCR imaj deposuna giriş. Parola alanına GHCR tokeni girilir. |
| `atonota-deploy-ssh-alpha` | SSH kullanıcı adı ve özel anahtar | `atonota-delivery` | alpha sunucu kullanıcısına bağlantı. |
| `atonota-deploy-ssh-beta` | SSH kullanıcı adı ve özel anahtar | `atonota-delivery` ve `atonota-release` | beta sunucu kullanıcısına bağlantı. |
| `atonota-deploy-ssh-rc` | SSH kullanıcı adı ve özel anahtar | `atonota-release` | rc sunucu kullanıcısına bağlantı. |
| `atonota-deploy-ssh-prod` | SSH kullanıcı adı ve özel anahtar | `atonota-release` | prod sunucu kullanıcısına bağlantı. |

Her ortamın anahtarı ayrıdır. Bir anahtar yalnız kendi ortamını açar.
rc ve prod anahtarlarını `atonota-delivery` klasörüne koymayın.
Bu klasördeki işler `main` dalına her push ile kendiliğinden başlar.

## Kurulum sırası

1. DevOps sorumlusu Jenkins'te iki klasörü açar: `atonota-delivery` ve `atonota-release`.
2. DevOps sorumlusu tablodaki kayıtları ilgili klasöre ekler.
3. DevOps sorumlusu `atonota-build` etiketli ajanı hazırlar. Ajanın ihtiyaçları `backend.Jenkinsfile` dosyasının başında yazılıdır.
4. DevOps sorumlusu işleri açar. İş adları Jenkinsfile dosyalarının başında yazılıdır.
5. DevOps sorumlusu ilk koşuyu izler. Her `Gate: ` aşaması ayrı görünmelidir.

## Kurallar

- Zamanlanmış tetikleyici eklemeyin. `cron` ve `pollSCM` kullanmayın. İşi yalnız GitHub push tetikler.
- Sunucu adresini Jenkinsfile dosyasına yazmayın. Adresler `backend/deploy/environments/` dosyalarındadır.
- Alan adı gerekirse tek ayardan okuyun. Sabit alan adı yazmayın.
