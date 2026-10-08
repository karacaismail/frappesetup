# press-ai

Press operasyonları ve Frappe özel uygulama geliştirme için yerel stdio MCP sunucusu, operasyon kontratı,
skill'ler ve agent rolleri. Python 3.9+ yalnız standart kütüphane; ek bağımlılık, servis veya dinleyici yok.
Parçalar arasındaki sözleşme [INTERFACE.md](INTERFACE.md) dosyasındadır.

| Dizin | İçerik |
| --- | --- |
| `press_ai/`, `server.py` | MCP sunucusu (14 araç) ve insan onay CLI'si |
| `contracts/` | 77 işlemlik kontrat (43'ü uygulanmış): kılavuzun 67 adımı, API ve kaynak satırları, ön koşul, başarı, hata, devir |
| `skills/`, `agents/`, `references/` | Görev seçimi ve sıra kuralları; teşhis, operasyon, geliştirme ve bağımsız inceleme rolleri |
| `tests/` | Sahte Press, fixture uygulamalar, protokol, güvenlik, alan ve kontrat testleri |
| `config/` | Örnek yapılandırma; gerçek secret içermez |

## Yetki sınırı

- Sunucu, kullanıcının kendi Press API anahtarıyla HTTPS üzerinden konuşur. Press kendi izinlerini uygular; bu paket
  ayrıca işlem izin listesi, canlı ön koşul ve insan onayı ekler. Shell, SSH, Server Script, ham SQL veya ham Python yoktur.
- İki rol: `team` (Dashboard API, takım başlığı yapılandırmadan gelir) ve `operator` (Press sitesinde System User; kılavuzdaki
  Desk yolu). System User `@protected` denetimini atladığı için mutasyonu açık operator yapılandırmasında `team`
  zorunludur; ön koşullar grup, candidate, build ve site sahipliğini bu takıma göre denetler.
- Mutasyonlar varsayılan kapalıdır. İnsan, yapılandırmada `press.enabled_mutations` listesine işlem kimliği ekler.
- Her mutasyon önce öneridir. İnsan ayrı terminalde onaylar; sunucuda onay aracı yoktur, `confirm` gibi alanlar reddedilir.
  Onay özete bağlıdır, tek kullanımlıktır ve süresi dolar.
- Onay, sunucuyla aynı OS hesabıyla yazılır ve yalnız bir hız kesicidir: model MCP üzerinden onay veremez, ama aynı hesapta
  shell erişimi olan bir süreç onay CLI'sini çalıştırabilir veya durum dizinini düzenleyebilir. Bu bir OS veya kriptografik
  güvenlik sınırı değildir. Ayrı onaylayıcı hesabı desteklenmez; `approval.approver_uid` yapılandırmada reddedilir.
- Yürütme aynı (işlem, hedef) için kilitlidir; istek gönderilmeden önce sonuç `unknown` olarak kalıcı yazılır. Süreç
  yarıda ölse bile o hedefe yeni öneri, insan `resolve` ile sonucu kapatana kadar engellenir.
- Yerel özel SSH MCP'si (root, ControlMaster, `--full-admin` keyfi komut) bu paketten ayrıdır; bu paket onu çağırmaz,
  değiştirmez ve yerine geçmez.

## Uygulama geliştirme araçlarının kapsamı

`app_inspect` ve `app_check` uygulamayı çalıştırmadan okur ve kural denetler (monkey patch, izin atlama, SQL biçimleme,
hooks, patches, fixtures, DocType şeması, sürüme bağlı özellikler). `app_propose_change` iki tür değişiklik üretir:

- İskelet: app iskeleti, DocType/child table şeması ve boş controller, boş `execute()` patch, fixture filtresi, `pass`
  gövdeli doc_event handler, yalnız `super()` çağıran override/extend sınıfı, boş test. Bunlar davranış değildir.
- `write_file`: geliştiricinin (veya geliştirici agent'ın) yazdığı gerçek iş mantığı, controller davranışı, genişletme
  kodu ve test içeriği; tek dosya, diff ve sha256 ile önizlenir, insan onaylar, `app_apply` atomik yazar. Kod
  çalıştırılmaz ve import edilmez; yalnız sözdizimi ve kural denetimi yapılır.

Davranışın doğru olduğu ancak `bench run-tests` (yerelde insan komutu) gerçek çıktısıyla söylenir. Önerilen yol özel
uygulamada hooks ve genişletme noktalarıdır. Orijinal core dosyaları (resmi uygulamalar, `press` dahil) varsayılan
olarak reddedilir: ilk istek yalnız `core_warning` döner; kullanıcı aynı değişikliği açıkça yeniden isterse öneri oluşur ve
insan ayrı terminalde `APPROVE <digest12>` ile `CORE <uygulama>` yazarak onaylar. Özel uygulama dosyaları normal yetkili
akıştadır: özel DocType izinleri ve izin/rol fixture'ları engellenmez, özel koddaki resmi modül yaması (EXT001) da
engellenmez; ikisi de önizlemede not/uyarı olarak görünür. Secret, `.git` ve gizli yol sınırı mutlaktır.

## Kurulum

1. Yapılandırmayı repo dışına kopyalayın: `config/press-ai.example.json` → örneğin `~/.config/press-ai/press-ai.json`.
2. Kimlik bilgisi (biri):
   - Keychain: `security add-generic-password -s press-ai -a press.example.com -w` (değer `api_key:api_secret`).
   - Dosya: `config/credentials.example.json` biçiminde, repo ve workspace dışında, `chmod 600`.
   - Ortam değişkeni (`{"source": "env", "key_env": ..., "secret_env": ...}`) en zayıf seçenektir.
3. MCP istemcisine ekleyin (örnek `config/mcp.example.json`; Codex için aynı komut `[mcp_servers.press-ai]` altında).
   Bu repo hiçbir istemciye kendiliğinden kaydolmaz.
4. Skill ve agent'lar Claude Code plugin'i olarak yüklenir (`.claude-plugin/plugin.json`): oturumluk
   `claude --plugin-dir packages/press-ai`. Doğrulama: `claude plugin validate packages/press-ai --strict` ve
   `claude --plugin-dir packages/press-ai plugin details press-ai` (4 skill, 4 agent; MCP sunucusu plugin'e gömülü değildir,
   3. adımla ayrı kaydedilir). Kalıcı kullanım için `skills/*` ve `agents/*` kendi `.claude/skills` ve `.claude/agents`
   dizinine kopyalanabilir; o durumda skill'lerin `../../references/` bağlantıları kopyalanmazsa `contract_get` esastır.

```sh
python3 -I packages/press-ai/server.py serve --config ~/.config/press-ai/press-ai.json
python3 -I packages/press-ai/server.py approve <proposal_id> --config ~/.config/press-ai/press-ai.json   # insan, TTY
python3 -I packages/press-ai/server.py proposals --config ~/.config/press-ai/press-ai.json
```

## Akış ve sonuç dili

`press_propose` → insan `approve` → `press_execute` (sonuç en iyi ihtimalle `accepted`) → `press_track`
(`in_progress`, `succeeded`, `failed`, `no_op`, `unknown`). Kuyruğa alınma veya HTTP 200 başarı değildir. Zaman aşımı
`unknown` olur ve aynı hedefe yeni öneri, insan `resolve` ile sonucu kapatana kadar engellenir. Build ve deploy ayrı
işlemlerdir; deploy önerisi build Success ve tüm adımlar Success olmadan oluşmaz.

## Doğrulama

```sh
python3 -I -m unittest discover -s packages/press-ai/tests
PRESSGUIDE_DATA=<pressguide>/src/data python3 -I packages/press-ai/server.py check-contract \
  --guide "$PRESSGUIDE_DATA/guide.json" --sitemap "$PRESSGUIDE_DATA/press-sitemap.json"
```

Testler yerel sahte Press'e karşı koşar; birim testleri ve `check-contract` (pressguide verisi olmadan) depodaki `ci.yml` ve
`deploy.yml` kapısında da koşar. Canlı Press ve gerçek MCP istemcisi oturumu `not_run`dır. Kontrat frappe/press `ebf3e22` (develop) kaynağına göre statik doğrulanmıştır;
kurulu Press'in sürümü farklıysa uç nokta farkı `press_not_found` olarak görünür.

Lisans: kod MIT (`LICENSE`). `LICENSE-CONTENT` (CC BY 4.0) yalnız sitenin `src/content/` ve `src/data/` içeriğini ve
bunlardan üretilen sayfaları kapsar; indirme ZIP'lerinde iki dosya da bulunur. Üçüncü taraf kaynaklar yalnız yol ve
commit ile atıflanır, kod kopyalanmaz.
