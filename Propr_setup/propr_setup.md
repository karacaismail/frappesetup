# ProPR kurulum belgesi

Bu belge 22 Kasım 2026 Pazar günü yazıldı.

Belge, ProPR'ı bu Mac'te baştan kurmayı anlatır. Adımları sırayla izleyin. Bir adım bitmeden sonrakine geçmeyin.

## Bu klasörde ne var

Bu klasör depoda `Propr_setup` adıyla durur. Klasörde beş dosya vardır:

- `propr_setup.md` dosyası bu belgedir.
- `open-propr.sh` betiği ProPR'ı doğru ayarla açar.
- `set-oauth-secret.sh` betiği GitHub istemci sırrını gizli olarak alır.
- `devir-notu-devops.md` dosyası `main` dalının korunması için devir notudur.
- `restart-propr-stack.mjs` betiği ProPR servislerini ProPR'ın kendi koduyla yeniden kurar.

İki betiğin asıl yeri `~/.config/propr-docker` klasörüdür. Devir notunun asıl yeri `~/.config/frappesetup-pr` klasörüdür. Buradaki dosyalar yedektir.

## Kısa sözlük

- ProPR, GitHub'daki PR'ları izleyen bir uygulamadır.
- PR, bir dalı ana dala katma isteğidir.
- CI, GitHub'ın her PR için çalıştırdığı otomatik testlerdir.
- Colima, Mac'te container çalıştıran araçtır. Docker Desktop yerine bunu kullanıyoruz.
- Profil, Colima'nın ayrı bir sanal makinesidir.
- İmaj, bir servisin hazır paketidir.
- `.env` dosyası, ProPR'ın ayar dosyasıdır. Bu dosyada sırlar da vardır.
- MCP, yapay zekâ ajanlarının başka uygulamaların araçlarını kullanma yoludur.
- HTTPS, şifreli web bağlantısıdır. HTTPS için sertifika gerekir.
- Vekil, gelen isteği başka bir servise ileten aracı servistir.

## 1. ProPR bizim kurulumumuzda ne yapar

ProPR yalnız `metafrappe` depolarında çalışır. ProPR, `karacaismail/frappesetup` deposuna erişemiyor.

Müşteri 27 Kasım 2026 Cuma günü birleştirme ve commit kimliği kuralını koydu (K-64). Müşteri 28 Kasım 2026 Cumartesi günü depo ayrımını netleştirdi (AJA-2553). Kural değişmez. Kural şudur:

1. `metafrappe` depolarında PR'ları ProPR birleştirir.
2. `metafrappe` depolarında ProPR'ın her commit'inde yazar ve committer `karacaismail <35493655+karacaismail@users.noreply.github.com>` olur.
3. `metafrappe` depolarında GitHub'ın birleştirme servisi son birleşme commit'inin committer alanına GitHub yazar. Müşteri bu tek istisnayı yalnız `metafrappe` depoları için kabul etti.
4. `karacaismail/frappesetup` deposunda PR'ları orkestratör yerelde `--no-ff` ile birleştirir ve GitHub'a gönderir. Commit kimliği `karacaismail` olur. Yazar koruması açık kalır.

ProPR kuralı `metafrappe` depolarında ProPR'ın üç commit türünü kapsar:

- ana dalı PR dalına birleştiren commit,
- çakışma çözen commit,
- ProPR'ın yazdığı düzeltme commit'i.

### Commit kimliği değişkenleri (`metafrappe` depoları)

`metafrappe` depolarında kimliği iki değişken verir. Değişkenler ProPR'ın `.env` dosyasındadır. Dosyanın yolu şudur:

```text
~/Library/Application Support/ProPR Desktop/local-runtime/.env
```

İki değişken şu değerleri taşır:

```text
PROPR_AGENT_COMMIT_AUTHOR_NAME=karacaismail
PROPR_AGENT_COMMIT_AUTHOR_EMAIL=35493655+karacaismail@users.noreply.github.com
```

Bu iki değişkeni boş bırakmayın. Bu iki değişkeni silmeyin. Değişken boş kalırsa ProPR yazar alanına `propr-dev[bot]` yazar.

ProPR Git'i hook'lar kapalı çalıştırır. Hook, Git'in her commit'te çalıştırdığı denetimdir. Bu yüzden `metafrappe` depolarında yazar koruması ProPR commit'lerini denetlemez. Kimliği yalnız bu iki değişken korur. `karacaismail/frappesetup` deposunda birleştirmeyi orkestratör yerelde yapar. Bu depoda yazar koruması açık kalır.

### Eski kurulumdan kalan bölümler

Bu belge önce 22 Kasım 2026 Pazar günü yazıldı. O gün ProPR `karacaismail/frappesetup` için yalnız gözlemci olarak kuruldu. Birleştirmeyi kapı betiği yapıyordu. Betiğin yolu şuydu:

```text
~/.config/frappesetup-pr/pr_gate.py
```

Belgedeki `karacaismail/frappesetup` GitHub izinleri ve depo seçimi o günkü kurulumu anlatır. "Yapmayın" bölümündeki birleştirme ve yazma izni maddeleri de o güne aittir. `metafrappe` depolarındaki ProPR izinleri yeni kurala göre henüz gözden geçirilmedi. Açık işler listesinin 7. maddesi bu işi anlatır.

## 2. Ön koşullar

### Neden ayrı bir Colima profili kullanıyoruz

Bu Mac'te iki Colima profili zaten çalışır. Adları `default` ve `factory` olur. Bu profillerde başka projeler vardır.

ProPR'ı bu profillere koymuyoruz. ProPR kendi `propr` profilinde çalışır. Böylece öteki projeler etkilenmez.

`propr` profili yalnız ProPR'ın veri klasörünü görür. Ana Claude ve Codex hesaplarının klasörlerini görmez.

### Adımlar

1. Colima'nın kurulu olduğunu denetleyin.

```bash
colima version
```

2. ProPR veri klasörünü oluşturun. Klasör varsa bu komut zarar vermez.

```bash
install -d -m 700 "$HOME/Library/Application Support/ProPR Desktop"
```

3. `propr` profilini başlatın.

```bash
colima start propr --activate=false --cpus 4 --memory 8 --disk 60 --vm-type vz --vz-rosetta --mount-type virtiofs --mount "$HOME/Library/Application Support/ProPR Desktop:w"
```

Bu komuttaki seçeneklerin anlamı şudur:

- `--activate=false` seçeneği genel Docker ayarını değiştirmez.
- `--vz-rosetta` seçeneği amd64 imajlarını çalıştırır. ProPR'ın ajan imajı amd64'tür.
- `--mount` seçeneği sanal makineye yalnız ProPR klasörünü gösterir.

4. Genel Docker bağlamını denetleyin.

```bash
docker context ls
```

Yıldız işareti `colima` satırında olmalı. Yıldız `colima-propr` satırındaysa durun. Bu durumda genel ayar bozulmuştur.

5. ProPR için ayrı Docker ayar klasörünü oluşturun.

```bash
install -d -m 700 ~/.config/propr-docker
printf '{\n  "cliPluginsExtraDirs": ["%s/.docker/cli-plugins"]\n}\n' "$HOME" > ~/.config/propr-docker/config.json
chmod 600 ~/.config/propr-docker/config.json
```

Genel Docker ayarı `osxkeychain` adlı bir yardımcı ister. Bu yardımcı bu Mac'te yoktur. Bu yüzden imaj indirme hata verir. Ayrı ayar klasörü bu sorunu çözer.

6. Bu klasöre geçin. Sonra betikleri asıl yerlerine kopyalayın.

```bash
cp -p open-propr.sh set-oauth-secret.sh ~/.config/propr-docker/
```

7. amd64 imajının çalıştığını deneyin.

```bash
DOCKER_CONFIG=~/.config/propr-docker DOCKER_HOST=unix://$HOME/.colima/propr/docker.sock docker run --rm --platform linux/amd64 alpine:3.20 uname -m
```

Ekranda `x86_64` yazmalı.

### ProPR'ı her zaman nasıl açacağız

ProPR'ı her zaman bu betikle açın:

```bash
~/.config/propr-docker/open-propr.sh
```

ProPR'ı Dock'tan açmayın. Dock'tan açılan ProPR genel Docker ayarını kullanır. Genel ayar `default` profiline bağlıdır. O zaman ProPR yanlış sanal makineye gider.

ProPR zaten açıksa önce kapatın. ProPR menüsünden "Quit ProPR" seçin. Sonra betiği çalıştırın. Betik, açık bir uygulamaya ayar veremez.

## 3. GitHub uygulamasını oluşturma

ProPR'ın kendi hizmeti "ProPR Connect" adını taşır. Bu hizmetin izinleri sabittir ve yazma izni içerir. Bu yüzden kendi GitHub uygulamamızı kurduk.

1. Chrome'da GitHub'a `karacaismail` hesabıyla girin.
2. Aşağıdaki adresi açın. Adres formu hazır doldurur.

```text
https://github.com/settings/apps/new?name=frappesetup-propr-gate&description=ProPR+read-only+PR+gate+for+karacaismail%2Ffrappesetup&url=https%3A%2F%2Fgithub.com%2Fkaracaismail%2Ffrappesetup&public=false&webhook_active=false&metadata=read&contents=read&pull_requests=read&issues=read&checks=read&statuses=read&actions=read
```

3. Formdaki değerleri değiştirmeyin.
4. Sayfanın altında "Only on this account" seçili olmalı.
5. "Create GitHub App" düğmesine basın.

Uygulamanın yedi izni vardır. Yedisi de yalnız okumadır:

- Actions
- Checks
- Commit statuses
- Contents
- Issues
- Metadata
- Pull requests

Webhook kapalıdır. ProPR olayları kendisi sorar.

### Uygulamayı depoya kurma

1. Uygulama sayfasının sol menüsünde "Install App" seçin.
2. `karacaismail` satırında "Install" düğmesine basın.
3. "Only select repositories" seçeneğini seçin.
4. Listeden yalnız `karacaismail/frappesetup` deposunu seçin.
5. "Install" düğmesine basın.

Kurulumdan sonra adres çubuğunun sonunda bir sayı görünür. Bu sayı kurulum numarasıdır.

### Özel anahtarı üretme

1. Uygulama sayfasının sol menüsünde "Credentials" seçin.
2. "Key pairs" sekmesini açın.
3. "New key" düğmesine basın.
4. Chrome bir `.pem` dosyası indirir.
5. Dosyanın iznini daraltın. Dosya tarayıcının indirme klasörüne iner. Komuttaki `<indirilen-pem-dosyası>` yazısının yerine bu dosyanın yolunu yazın.

```bash
chmod 600 <indirilen-pem-dosyası>
```

ProPR bu dosyanın iznine bakar. İzin `600` değilse ProPR dosyayı kabul etmez.

### Bizim değerlerimiz

Bu değerler gizli değildir:

- App ID değeri `5873713` olur.
- Installation ID değeri `184642152` olur.
- Client ID değeri uygulamanın "General" sayfasında yazar. Bu belgede `<CLIENT_ID>` olarak geçer.

## 4. Kurulum sihirbazı

1. ProPR'ı betikle açın.
2. "Set up this computer" seçeneğini seçin.
3. "Check the essentials" ekranında "Continue" düğmesine basın.
4. "Private local storage" ekranında "Continue" düğmesine basın.
5. "Connect GitHub" ekranında "Custom GitHub App" seçin.
6. "App ID" alanına `5873713` yazın.
7. "Installation ID" alanına `184642152` yazın.
8. "Choose private key" düğmesine basın.
9. İndirilenler klasöründeki `.pem` dosyasını seçin.
10. "Continue" düğmesine basın.
11. "GitHub event intake" ekranında "Polling" seçin.
12. "Select coding agents" ekranında yalnız "Codex" seçili kalsın.
13. "Allowed GitHub users" alanına `karacaismail` yazın.
14. "Ready to install" ekranında "Install ProPR" düğmesine basın.

İmajlar iner. Toplam boyut yaklaşık 7 GB olur. İndirme birkaç dakika sürer.

"Polling" seçeneğinde dışarıdan bağlantı açılmaz. ProPR, GitHub'a belirli aralıklarla kendisi sorar.

## 5. Karşılaştığımız hatalar ve çözümleri

### Hata 1: imaj indirme `osxkeychain` hatası veriyor

Ekranda `docker-credential-osxkeychain` hatası görünür.

Bu hatanın nedeni genel Docker ayarıdır. Çözüm, 2. bölümdeki ayrı ayar klasörüdür. ProPR'ı açma betiğiyle açın.

### Hata 2: ProPR penceresinin görüntüsü alınamıyor

Bu sorun yalnız ajanlar için geçerlidir.

Bu Mac'te Stage Manager açıktır. Arka plandaki pencere küçük bir resim olarak durur. Ajan bu pencerenin görüntüsünü alamaz.

Pencereyi öne getirmek için şu komutu çalıştırın:

```bash
open -a /Applications/propr-desktop.app
```

ProPR'ın form alanlarına arka planda yazı yazılamaz. Ajan bu alanlar için tam ekran denetimi ister.

### Hata 3: "no instance administrator is configured"

Kurulum yönetici bulamadığı için durur.

1. ProPR'ın ayar dosyasında yöneticiyi yazın.

```bash
E="$HOME/Library/Application Support/ProPR Desktop/local-runtime/.env"
sed -i '' -E 's/^PROPR_ADMIN_USERS=.*/PROPR_ADMIN_USERS=karacaismail/' "$E"
chmod 600 "$E"
```

2. ProPR'da "Retry setup" düğmesine basın.

### Hata 4: `bind source path does not exist: ~/.claude.json`

Servisler başlamaz.

ProPR, bu Mac'teki ajan hesaplarını kendisi bulur. Sonra bu klasörleri servislere bağlamak ister. `propr` sanal makinesi bu klasörleri görmez. Bu yüzden başlatma durur.

Bu durum aslında iyidir. ProPR ana hesapların giriş bilgisine erişmemeli.

1. ProPR'ın ana hesap klasörlerini bağlamasını kapatın.
2. Codex için ayrı ve boş bir klasör verin.

```bash
B="$HOME/Library/Application Support/ProPR Desktop"
install -d -m 700 "$B/agent-homes/codex"
E="$B/local-runtime/.env"
sed -i '' -E 's#^(HOST_CLAUDE_DIR|HOST_ANTIGRAVITY_DIR|HOST_OPENCODE_XDG_DIR|HOST_OPENCODE_DATA_DIR|HOST_VIBE_DIR|HOST_CLAUDE_JSON)=.*#\1=#' "$E"
sed -i '' -E "s#^HOST_CODEX_DIR=.*#HOST_CODEX_DIR=$B/agent-homes/codex#" "$E"
chmod 600 "$E"
```

3. ProPR'da "Retry setup" düğmesine basın.

### Hata 5: "Sign in required" ve `web_auth_not_configured`

ProPR'ın web girişi kapalıdır. Web girişi için GitHub uygulamasının OAuth bilgisi gerekir.

1. GitHub uygulamasının "General" sayfasını açın.
2. "Redirect URI" alanına bu adresi yazın.

```text
http://localhost:4000/api/auth/github/callback
```

3. Sayfanın altında "Save changes" düğmesine basın.
4. "Credentials" sayfasında "Client secrets" sekmesini açın.
5. "New secret" düğmesine basın.
6. Sırrı kopyalayın. GitHub sırrı yalnız bir kez gösterir.
7. Terminalde şu komutu çalıştırın.

```bash
~/.config/propr-docker/set-oauth-secret.sh <CLIENT_ID>; exit
```

`<CLIENT_ID>` yerine uygulamanın Client ID değerini yazın.

8. Sırrı bir kez yapıştırın. Sonra Enter tuşuna basın.
9. Betik sırrın biçimini denetler ve sırrı kaydeder. Sonra terminal sekmesi kapanır.
10. ProPR'ın iki servisini yeniden başlatın.

```bash
DOCKER_CONFIG=~/.config/propr-docker DOCKER_HOST=unix://$HOME/.colima/propr/docker.sock docker restart propr-api propr-daemon
```

11. Girişin GitHub'a gittiğini denetleyin.

```bash
curl -s -L --max-redirs 4 -o /dev/null -w '%{url_effective}\n' http://127.0.0.1:4000/api/auth/github | cut -c1-60
```

Çıktı `https://github.com/login?client_id=<CLIENT_ID>` ile başlamalı.

Giriş ayarları için `docker restart` yetti. MCP ayarları için 7. bölümdeki yeniden kurma gerekir.

### Hata 6: sır iki kez yapıştırılırsa

Sır ilk yapıştırmada kaydedilir. İkinci yapıştırma terminale komut olarak gider. O zaman sır ekranda görünür. Sır komut geçmişine de yazılabilir.

Bunu önlemek için betiği `; exit` ile çalıştırın. Betik bitince sekme kapanır.

Bu hata yine olursa sırrı yenileyin:

1. GitHub'da "New secret" ile yeni sır üretin.
2. Yeni sırrı betikle kaydedin.
3. `propr-api` ve `propr-daemon` servislerini yeniden başlatın.
4. GitHub'da eski sırrı silin.

GitHub tek sırrı silmeye izin vermez. Bu yüzden önce yeni sır üretilir.

## 6. Giriş ve depo ekleme

### GitHub kod onayı

Kurulum sırasında ProPR tek kullanımlık bir kod gösterir.

1. ProPR'da "Open GitHub" düğmesine basın.
2. Tarayıcıda kodu girin.
3. Hesap olarak `karacaismail` seçin.
4. İzin sayfasını okuyun. Sayfa "Full control of private repositories" yazıyorsa onaylamayın.
5. Sayfada bu yazı yoksa onaylayın.
6. ProPR "Continue as @karacaismail?" diye sorar. "Use this account" düğmesine basın.

### Tarayıcıdan giriş

Servisler başlayınca ProPR "Sign in required" ekranını gösterir.

1. "Sign in in browser" düğmesine basın.
2. GitHub izin sayfasında uygulamanın adı `frappesetup-propr-gate` olmalı. Adı doğruysa onaylayın.
3. ProPR "Save @karacaismail for this instance?" diye sorar. "Save @karacaismail" düğmesine basın.

### Depoyu ekleme

1. Sol menüde "Repositories" seçin.
2. "+ Add Repository" düğmesine basın.
3. "Repository" alanına `karacaismail/frappesetup` yazın.
4. "Automatic CI follow-up" kutusunu boş bırakın.
5. "Visual previews" kutusunu boş bırakın.
6. "Add Repository" düğmesine basın.

Panoda "No AI Agent Configured" uyarısı görünür. Bu uyarıyı bilerek bıraktık. ProPR'da ajan olmadığı için ProPR kod yazamaz.

## 7. MCP köprüsü

MCP, yapay zekâ ajanlarının başka uygulamaların araçlarını kullanma yoludur. ProPR'ın MCP sunucusu PR'ları ve görevleri okuma araçları sunar.

### Neden yerel bir HTTPS vekili var

ProPR'ın MCP sunucusu yalnız HTTPS adresle çalışır. ProPR'ın hazır tüneli servisi internete açar. Bu yüzden tüneli seçmedik.

ProPR'ın önüne bu bilgisayarda çalışan bir HTTPS vekili koyduk. Vekil, gelen isteği ProPR'a iletir. Vekil yalnız bu bilgisayardan açılır.

### Yapı

- Vekil konteynerinin adı `propr-tls-proxy` olur.
- Konteynerin imajı `caddy:2.8.4-alpine` olur.
- Vekil, ProPR'ın `propr-net` ağında `172.18.0.250` adresini kullanır.
- Vekil yalnız `127.0.0.1:4443` adresinde açılır.
- MCP adresi `https://localhost:4443/api/mcp` olur.
- Kapsam tavanı yalnız `read` olur. Ajanlar ProPR'da yalnız okuyabilir.

### Sertifika

Sertifika bu Mac için üretilen yerel bir kök sertifikayla imzalıdır. Sertifika yalnız `localhost` ve `127.0.0.1` adlarını kapsar.

Kök sertifika sistem anahtar zincirine eklenmedi. Claude Code kök sertifikayı `NODE_EXTRA_CA_CERTS` değişkeninden okur.

Tarayıcı ilk açılışta "güvenli değil" uyarısı verir. Bu uyarı beklenen bir durumdur.

Bizim sertifikamız 24 Aralık 2027 günü sona erer. Kök sertifika 21 Kasım 2028 günü sona erer.

### Vekili kurma adımları

1. Sertifika klasörünü oluşturun ve klasöre geçin.

```bash
D="$HOME/Library/Application Support/ProPR Desktop/tls"
install -d -m 700 "$D"
cd "$D"
```

2. Yerel kök sertifikayı üretin.

```bash
openssl req -x509 -newkey rsa:3072 -nodes -keyout ca.key -out ca.crt -days 730 -subj "/CN=ProPR local CA (this Mac only)"
```

3. `localhost` sertifikasını üretin ve kök sertifikayla imzalayın.

```bash
openssl req -newkey rsa:2048 -nodes -keyout localhost.key -out localhost.csr -subj "/CN=localhost"
printf 'subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n' > san.ext
openssl x509 -req -in localhost.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out localhost.crt -days 397 -extfile san.ext
rm localhost.csr san.ext
chmod 600 ca.key localhost.key
```

4. Caddy ayar dosyasını yazın.

```bash
cat > Caddyfile <<'EOF'
{
	admin off
	auto_https disable_redirects
}

https://localhost:4443 {
	tls /certs/localhost.crt /certs/localhost.key
	reverse_proxy propr-api:4000 {
		flush_interval -1
	}
}
EOF
```

5. Vekil konteynerini başlatın.

```bash
export DOCKER_CONFIG=~/.config/propr-docker
export DOCKER_HOST=unix://$HOME/.colima/propr/docker.sock
docker run -d --name propr-tls-proxy --restart unless-stopped --network propr-net --ip 172.18.0.250 -p 127.0.0.1:4443:4443 -v "$D/localhost.crt:/certs/localhost.crt:ro" -v "$D/localhost.key:/certs/localhost.key:ro" -v "$D/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8.4-alpine
```

6. ProPR'ın ayar dosyasına iki değer yazın.

```bash
E="$HOME/Library/Application Support/ProPR Desktop/local-runtime/.env"
for kv in MCP_PUBLIC_ORIGIN=https://localhost:4443 PROPR_TRUSTED_PROXY_PEERS=172.18.0.250; do
  k=${kv%%=*}
  if grep -q "^$k=" "$E"; then sed -i '' "s#^$k=.*#$kv#" "$E"; else echo "$kv" >> "$E"; fi
done
chmod 600 "$E"
```

7. ProPR servislerini yeniden kurun. `Propr_setup` klasöründe şu komutu çalıştırın.

```bash
node restart-propr-stack.mjs
```

ProPR konteynerleri bu iki ayarı yalnız kurulurken okur. Bu yüzden `docker restart` yetmez.

8. Vekilin hâlâ çalıştığını denetleyin.

```bash
docker ps --format '{{.Names}} | {{.Ports}}' | grep propr-tls-proxy
```

9. ProPR'da "Settings" sayfasını açın.
10. "Integrations & MCP" bölümünde "Enable MCP server" seçeneğini açın.
11. Kapsam tavanında yalnız `read` bırakın. `plan` ve `review` seçeneklerini kaldırın.
12. MCP adresinin yanıt verdiğini denetleyin.

```bash
curl --cacert "$D/ca.crt" -s -o /dev/null -w '%{http_code}\n' https://localhost:4443/.well-known/oauth-protected-resource/api/mcp
```

Çıktı `200` olmalı.

### Claude Code hesabını bağlama

Her Claude hesabı ayrı bağlanır. Aşağıdaki adımlar bir hesap içindir.

1. Hesabı ve kök sertifikayı seçin. Örnekte Claude 03 hesabı vardır.

```bash
export CLAUDE_CONFIG_DIR="$HOME/.config/claude-denetim/accounts/03"
export NODE_EXTRA_CA_CERTS="$HOME/Library/Application Support/ProPR Desktop/tls/ca.crt"
```

2. ProPR'da sabit dönüş adresi için bir istemci kaydı açın.

```bash
curl --cacert "$NODE_EXTRA_CA_CERTS" -s https://localhost:4443/register -H 'Content-Type: application/json' -d '{"client_name":"Claude Code","redirect_uris":["http://localhost:38765/callback"],"token_endpoint_auth_method":"none","grant_types":["authorization_code","refresh_token"],"response_types":["code"]}'
```

Yanıttaki `client_id` değeri kayıt kimliğidir. Bu kayıt sır içermez.

Claude Code'un hazır kaydı her seferinde başka bir port kullanır. ProPR ise dönüş adresinin birebir aynı olmasını ister. Hazır kayıtla "Exact registered redirect_uri required" hatası çıkar. Bu yüzden sabit port kullanıyoruz.

3. Sunucuyu Claude Code'a ekleyin. `<kayıt kimliği>` yerine yanıttaki değeri yazın.

```bash
claude mcp add --transport http --scope user --callback-port 38765 --client-id <kayıt kimliği> propr https://localhost:4443/api/mcp
```

4. Girişi başlatın.

```bash
claude mcp login propr
```

Komut, onay bitene kadar açık kalmalı. Komut kapanırsa tarayıcı hata sayfası gösterir.

5. Tarayıcıdaki onay sayfasında `karacaismail/frappesetup` kutusunu işaretleyin.
6. "Allow selected access" düğmesine basın.

Kutu boş kalırsa "Select at least one accessible repository" hatası çıkar.

7. Bağlantıyı denetleyin.

```bash
claude mcp list
```

`propr` satırında "Connected" yazmalı.

### Paradev ajanları

Paradev'deki beş Claude ajanının ortamına `NODE_EXTRA_CA_CERTS` değişkeni eklendi. Değişkenin değeri kök sertifikanın yoludur.

### Bugünkü durum

Bu durum 22 Kasım 2026 Pazar günü kaydedildi.

- Yalnız Claude 03 hesabı bağlı. `claude mcp list` komutu "Connected" gösterdi.
- Öteki Claude hesapları bağlanmadı. Bu hesaplar için yukarıdaki adımları ayrı yapın.
- Codex hesapları bağlanmadı. Codex sistemin sertifika deposunu kullanır. Kök sertifika sisteme eklenmedi.
- Araçla okuma denemesi `not_run` durumunda. Claude 03 hesabı o sırada kullanım sınırındaydı.

## 8. Doğrulama

Önce iki değişkeni ayarlayın. Sonraki komutlar bu değişkenleri kullanır.

```bash
export DOCKER_CONFIG=~/.config/propr-docker
export DOCKER_HOST=unix://$HOME/.colima/propr/docker.sock
```

1. Servislerin çalıştığını denetleyin.

```bash
docker ps --format '{{.Names}} | {{.Status}} | {{.Ports}}'
```

Yedi konteyner görünmeli. Adları `propr-ui`, `propr-api`, `propr-indexing-worker`, `propr-worker`, `propr-daemon`, `propr-redis` ve `propr-tls-proxy` olur.

2. Portların yalnız bu bilgisayara açık olduğunu denetleyin.

```bash
lsof -nP -iTCP:4000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:4443 -sTCP:LISTEN
```

Adres sütununda `127.0.0.1` yazmalı.

3. API'nin yanıt verdiğini denetleyin.

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4000/api/health
```

Çıktı `401` olmalı. Bu sayı, API'nin çalıştığını ve giriş istediğini gösterir.

4. ProPR'ın depoyu okuduğunu denetleyin.

```bash
docker logs --since 10m propr-daemon 2>&1 | grep "Polling cycle completed" | tail -1
```

En az bir satır görünmeli.

5. Bağlanan klasörleri denetleyin.

```bash
docker inspect propr-worker --format '{{range .Mounts}}{{println .Source}}{{end}}'
```

Listede `~/.claude` ve `~/.codex` klasörleri olmamalı.

6. Sanal makinenin ana hesap klasörlerini görmediğini denetleyin.

```bash
colima ssh -p propr -- ls -d "$HOME/.codex" "$HOME/.claude"
```

Çıktıda "No such file or directory" yazmalı.

7. Genel Docker bağlamının değişmediğini denetleyin.

```bash
docker context ls
```

Yıldız işareti `colima` satırında olmalı.

## 9. Paradev tarafı

Paradev, ajanları çalışma alanlarında çalıştıran masaüstü uygulamasıdır. Eski adı Superset'tir.

### Hesap ajanları

Paradev'in hesap bulma özelliği `~/.config/claude-denetim` klasörünü görmez. Bu yüzden her hesabı ayrı bir ajan olarak ekledik. Ajanlar ortam değişkeniyle hesap seçer.

| Ajan | Komut | Hesabı seçen ayar |
| --- | --- | --- |
| Claude 01 | `claude --permission-mode auto` | Ayar yok, varsayılan hesap |
| Claude 02 | `claude --permission-mode auto` | `CLAUDE_CONFIG_DIR=$HOME/.config/claude-denetim/accounts/02` |
| Claude 03 | `claude --permission-mode auto` | `CLAUDE_CONFIG_DIR=$HOME/.config/claude-denetim/accounts/03` |
| Claude 04 | `claude --permission-mode auto` | `CLAUDE_CONFIG_DIR=$HOME/.config/claude-denetim/accounts/04` |
| Claude 05 | `claude --permission-mode auto` | `CLAUDE_CONFIG_DIR=$HOME/.config/claude-denetim/accounts/05` |
| Codex 01 | `$HOME/.config/claude-denetim/codex-01.sh` | `CODEX_HOME=$HOME/.config/claude-denetim/codex-accounts/01` |
| Codex 02 | `$HOME/.config/claude-denetim/codex-02.sh` | `CODEX_HOME=$HOME/.config/claude-denetim/codex-accounts/02` |

Paradev ayarına `$HOME` yerine ev klasörünün tam yolunu yazın. Hesap klasörleri kopyalanmadı. Ajanların adında hesabın 22 Kasım 2026 Pazar günkü durumu yazar.

### Çalışma alanı ve görev

- Paradev'de `frappesetup` projesi vardır.
- Projede `site-pr-flow` adlı bir çalışma alanı vardır.
- Görev metninin yolu `~/.config/frappesetup-pr/paradev-pr-gorevi.md` olur.
- Görev, kapı betiğini kullanır. Görev kod yazmaz.

Paradev komut satırı için bir kez giriş gerekir:

```bash
~/.paradev/bin/paradev auth login
```

Komut bir bağlantı gösterir. Bağlantıyla Paradev'e girin. Sayfanın verdiği kodu terminale yapıştırın.

## 10. Açık işler

1. MCP köprüsü kuruldu. Öteki Claude hesapları ve Codex hesapları bağlı değil. Araçla okuma denemesi `not_run` durumunda. Ayrıntı 7. bölümdedir.
2. İstemci sırrı açığa çıkarsa sırrı hemen yenileyin. 5. bölümdeki Hata 6 adımlarını izleyin.
3. `main` dalı korumasızdır. DevOps sorumlusu için devir notu yazıldı. Not bu klasördedir: [devir-notu-devops.md](devir-notu-devops.md).
4. Terminal geçmişini denetleyin. Önce açık terminal sekmelerini kapatın. Sonra şu komutu çalıştırın.

```bash
LC_ALL=C grep -c -E '(^|;)[0-9a-f]{40}$' ~/.zsh_history
```

Çıktı `0` olmalı. Çıktı `0` değilse sır geçmişe yazılmıştır. O satırı silin.

```bash
LC_ALL=C sed -i '' -E '/(^|;)[0-9a-f]{40}$/d' ~/.zsh_history
```

5. İndirilenler klasöründeki `.pem` dosyasını çöp kutusuna taşıyabilirsiniz. ProPR bu dosyanın kendi kopyasını sakladı.
6. ProPR'da ajan tanımlı değildir. Bu durum bilinçli bir seçimdir.
7. `metafrappe` depoları için GitHub izinlerini ve "Yapmayın" bölümünü K-64 ile AJA-2553 kuralına göre gözden geçirin. `karacaismail/frappesetup` deposunda ProPR kullanılmaz; birleştirmeyi orkestratör yerelde `--no-ff` ile yapar ve yazar koruması açık kalır. Bu belge değişkenlerin çalıştığını doğrulamaz. ProPR'ın gerçek bir commit'i denetlenmedi.

## 11. Yapmayın

- ProPR'ı Dock'tan açmayın.
- Docker Desktop kurmayın.
- "ProPR Connect" seçeneğini seçmeyin.
- ProPR tünelini açmayın.
- Kök sertifikayı sistem anahtar zincirine eklemeyin.
- Vekili `127.0.0.1` dışındaki bir adrese açmayın.
- MCP kapsam tavanına `read` dışında izin eklemeyin.
- `propr` profilini `--activate=false` olmadan başlatmayın.
- `default` ve `factory` profillerini yeniden başlatmayın.
- GitHub uygulamasına yazma izni vermeyin.
- `HOST_CODEX_DIR` değerini `~/.codex` yapmayın.
- "Automatic CI follow-up" kutusunu işaretlemeyin.
- Sırrı iki kez yapıştırmayın.
- Sırrı, anahtarı ve `.env` içeriğini sohbete yazmayın.
- Sırrı, anahtarı ve `.env` dosyasını Git'e eklemeyin.
- PR'ları `gh pr merge` ile birleştirmeyin.
- GitHub'ın otomatik birleştirmesini açmayın.

## Günlük kullanım

ProPR'ı açmak için:

```bash
~/.config/propr-docker/open-propr.sh
```

ProPR'ın sanal makinesini durdurmak için:

```bash
colima stop propr
```

Bu komut yalnız `propr` profilini durdurur. Öteki profiller çalışmaya devam eder.
