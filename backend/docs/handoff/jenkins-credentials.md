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

## Yazışma kanalı

Bu işle ilgili yazışmalar proje Telegram grubunda yapılır.
Sorunuz olursa soruyu proje Telegram grubuna yazın.
Grubun adresini depoya, yoruma ve Jenkinsfile dosyasına yazmayın.
Gizli değerleri gruba da yazmayın.

## Ortam onaylayıcısı

Uzak sunucudaki her değişikliği bir kişi onaylar. Bu notta bu kişiye ortam onaylayıcısı denir.
Ortam onaylayıcısının adı depoya yazılmaz.
Jenkins'te onay düğmesini `atonota-deployers` ve `atonota-release-managers` grupları görür.
prod onayı yalnız `atonota-release-managers` grubundadır.
DevOps sorumlusu ortam onaylayıcısını bu gruplara ekler.

Uzak sunucuya giden adımlar şunlardır:

1. alpha ortamından beta ortamına geçiş için ortam onaylayıcısından onay alın. Geçişi `Move to beta` aşaması başlatır.
2. beta ortamından `rc` ortamına geçiş için ortam onaylayıcısından onay alın. Geçişi `atonota-release/atonota-promote` işi yapar.
3. `rc` ortamından `prod` ortamına geçiş için ortam onaylayıcısından onay alın. Geçişi aynı `atonota-promote` işi yapar.
4. `rc` ve `prod` geri alması için ortam onaylayıcısından onay alın. Sürdürme işi de bu onayı ister.

Onay gelmezse geçişi başlatmayın.
Jenkins onay adımında bekler. Onaylanmayan iş sunucuya dokunmaz.

## Kurulum sırası

1. DevOps sorumlusu Jenkins'te iki klasörü açar: `atonota-delivery` ve `atonota-release`.
2. DevOps sorumlusu tablodaki kayıtları ilgili klasöre ekler.
3. DevOps sorumlusu `atonota-build` etiketli ajanı hazırlar. Ajanın ihtiyaçları `backend.Jenkinsfile` dosyasının başında yazılıdır.
4. DevOps sorumlusu işleri açar. İş adları Jenkinsfile dosyalarının başında yazılıdır.
5. DevOps sorumlusu ortam onaylayıcısını onay gruplarına ekler.
6. DevOps sorumlusu ilk koşuyu izler. Her `Gate: ` aşaması ayrı görünmelidir.

## Kurallar

- Zamanlanmış tetikleyici eklemeyin. `cron` ve `pollSCM` kullanmayın. İşi yalnız GitHub push tetikler.
- Sunucu adresini Jenkinsfile dosyasına yazmayın. Adresler `backend/deploy/environments/` dosyalarındadır.
- Alan adı gerekirse tek ayardan okuyun. Sabit alan adı yazmayın.
