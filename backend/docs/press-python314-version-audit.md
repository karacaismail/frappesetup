# Press sürüm taramasının sonucu

Tarama 22 Kasım 2026 Pazar günü tamamlandı.
İncelenen yeni sürümlerde yamasız yol bulunamadı. Bu araştırma kolu kapatıldı.
O-18 borcu açık kaldı. Çalışan Press sürümü yükseltilmedi.
Mevcut geliştirme yaması korunuyor.

## Kapsam

Resmî depoda 714 sürüm etiketi bulundu. Hepsi sürüm numarası taşıyordu.
`0.2.0`, `0.2.1` ve `0.3.0` etiketlerinde `v` öneki yoktur.
Diğer 711 etikette `v` öneki vardır.
Bu üç eski etiket, sonraki 162 etiketin sayısını değiştirmez.
`v0.154.1` sonrasındaki 162 etiket ayrı ayrı incelendi.
Bu aralık `v0.155.0` ile başlar. Son etiket `v0.204.1` olur.

Varsayılan dal `develop` olarak doğrulandı. `master` dalı da incelendi.
İki dosyanın dal geçmişleri ayrıca tarandı.
İlk tarihsel tarama yalnız `cache_utils.py` ve ürün denemesi modülünü kapsar.
Ek tarama aynı 269 kaynakta `cookies.py` dosyasını da denetledi.
Başlangıç kaynağı bu kümede zaten vardır. Ek tarama yeni commit eklemedi.
Çerez dosyasının kendi değişiklik geçmişi ayrıca taranmadı.
Test dosyasındaki ikinci `TypedDict` ve bağımlılık bildirimi sürüm taramasında yoktur.

| Kaynak | Kapsam |
| --- | --- |
| Sonraki sürüm etiketleri | 162 etiket |
| `v0.154.1..develop` dosya geçmişi | 87 commit |
| `v0.154.1..master` dosya geçmişi | 31 commit |
| Güncel dal uçları | `develop` ve `master` |
| Farklı kaynak durumları | 269 commit |
| İlk iki dosyanın farklı içerikleri | 22 Git blobu |
| Aynı 269 kaynakta çerez dosyasının farklı içerikleri | 1 Git blobu |

Git blobu, Git'in sakladığı tek dosya içeriğidir.
Aynı blob kimliği, dosya içeriğinin aynı olduğunu gösterir.

`v0.154.1`, `develop` dalının atası değildir.
Bu nedenle develop geçmişi tarih bakımından daha eski kayıtlar da içerir.
Tablodaki 87 kayıt yalnız sonraki tarihli değişiklikler anlamına gelmez.
Git'in iki kaynak arasındaki erişilebilirlik farkının tamamı incelendi.
Aynı kayıt iki geçmişte bulunabilir. Sayılar doğrudan toplanarak farklı commit sayısı çıkarılmaz.

## Sabit kaynaklar

| Kaynak | Doğrulanan commit kodu |
| --- | --- |
| Başlangıç `v0.154.1` | `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` |
| Son etiket `v0.204.1` | `8ff1813f465cb18354a762479477ebad14ab3d7c` |
| Varsayılan `develop` dalı | `d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410` |
| `master` dalı | `a9a7acd487902e54253d38bd9ef79ce52be9bc86` |

Son etiket ve iki dal ucu 20 Kasım 2026 Cuma günü oluşturuldu.
İmaj denemesi dal adına bağlanmadı. Tam develop commit koduna sabitlendi.

## Kaynak kanıtı

İlk dosya `press/press/doctype/deploy_candidate/cache_utils.py` yolundadır.
Bu dosya 269 kaynak durumunun tamamında aynı içeriği taşıyor.
Blob kimliği `a599d6d5a083a2985eef6e5d016644d06fc8212d` olarak doğrulandı.
Dosyanın 11. satırı doğrudan `typing.TypedDict` alır.
Dosyanın 13. satırındaki tanım `cwd=str` gibi anahtar argümanlar kullanır.
Python 3.14 bu çağrıyı reddeder.

İkinci dosya `press/saas/doctype/product_trial_request/product_trial_request.py` yolundadır.
Bu dosyada 21 farklı içerik bulundu.
Bütün içeriklerde üst düzey `init_telemetry` import'u korunuyor.
Dosya eksikliği veya bu import'u kaldıran ara durum bulunmadı.
Son etiket ve iki dal ucunda ikinci dosyanın içeriği de aynıdır.
Bu içeriğin blob kimliği `7dd7680cf84fc2f41d192e42740026e4a436ff6f` olur.

Üçüncü dosya `press/api/cookies.py` yolundadır.
Dosya, aynı 269 kaynak durumunun tamamında bulunur.
Blob kimliği hepsinde `3f2b4f41377b2405923f0da9ebfcc5e43394d77d` olur.
Yedinci satır, `frappe.oauth` içinden `get_cookie_dict_from_headers` işlevini alır.
Başlangıç kaynağı `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` da aynı içeriği taşır.
Bu nedenle üçüncü import engeli incelenen kaynakların tamamında korunur.

Tam eşlemeler [makineyle okunabilen kanıt dosyasındadır](evidence/press-python314-versions.json).
`refs` alanı sürüm ve dal adlarını commit kodlarına bağlar.
`histories` alanı iki dal için taranan geçmiş kayıtlarını taşır.
`snapshots` alanı her commit kodunu telemetri dosyasının blobuna bağlar.
`cache_blob` alanı bütün bu kayıtlardaki ortak ilk dosyayı gösterir.
`telemetry_blobs` alanı her farklı içerikteki import satırını kaydeder.
`cookies_snapshots` alanı aynı commit kümesini çerez dosyasının blobuna bağlar.
`cookies_blobs` alanı çerez import'unu ve satırını kaydeder.
`cookies_baseline` alanı başlangıç kaynağının bu kümede olduğunu açıkça doğrular.
`unprefixed_semver_tags` alanı, `v` öneki olmayan üç etiketi kaydeder.

Sürüm araştırmasını ayrı ajan yaptı. Ana ajan bütün eşlemeleri yeniden doğruladı.
Ana ajan resmî ref listesini yeniden aldı.
Ardından her kaydın iki blob kimliğini Git üzerinden karşılaştırdı.
Geçmiş listelerinin tamlığı ve 22 farklı dosyanın içeriği de doğrulandı.

[Son etiketin TypedDict kaynağı](https://github.com/frappe/press/blob/8ff1813f465cb18354a762479477ebad14ab3d7c/press/press/doctype/deploy_candidate/cache_utils.py#L11-L19)
[Develop telemetri kaynağı](https://github.com/frappe/press/blob/d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410/press/saas/doctype/product_trial_request/product_trial_request.py#L16)
[Master telemetri kaynağı](https://github.com/frappe/press/blob/a9a7acd487902e54253d38bd9ef79ce52be9bc86/press/saas/doctype/product_trial_request/product_trial_request.py#L16)
[Başlangıç kaynağının çerez import'u](https://github.com/frappe/press/blob/7a4384d5eec9f0f0dce4124e9dd48b106e51222f/press/api/cookies.py#L7)

## Taramayı yeniden üretme

Komutları depo kökünde aynı kabuk oturumunda çalıştırın.
Komutlar yalnız bu işin geçici klasörüne yazar.
Klon sığ olmamalıdır. Bu yüzden `--depth` kullanılmaz.
`--filter=blob:none`, dosya içeriklerini gerekince indirir. Commit geçmişini daraltmaz.

```sh
export PRESS_AUDIT_EVIDENCE="$PWD/backend/docs/evidence/press-python314-versions.json"
mkdir -p "$PWD/.pane/scratch/press-py314"
export PRESS_AUDIT_DIR="$(mktemp -d "$PWD/.pane/scratch/press-py314/version-audit.XXXXXX")"

git ls-remote --tags --refs https://github.com/frappe/press.git \
  > "$PRESS_AUDIT_DIR/tags.txt"
git ls-remote --heads https://github.com/frappe/press.git \
  > "$PRESS_AUDIT_DIR/heads.txt"
git ls-remote --symref https://github.com/frappe/press.git HEAD \
  > "$PRESS_AUDIT_DIR/default-head.txt"
git clone --filter=blob:none --bare https://github.com/frappe/press.git \
  "$PRESS_AUDIT_DIR/repo.git"
git -C "$PRESS_AUDIT_DIR/repo.git" rev-parse --is-shallow-repository

git -C "$PRESS_AUDIT_DIR/repo.git" rev-list --full-history \
  7a4384d5eec9f0f0dce4124e9dd48b106e51222f..d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410 \
  -- press/press/doctype/deploy_candidate/cache_utils.py \
  press/saas/doctype/product_trial_request/product_trial_request.py \
  > "$PRESS_AUDIT_DIR/develop-history.txt"
git -C "$PRESS_AUDIT_DIR/repo.git" rev-list --full-history \
  7a4384d5eec9f0f0dce4124e9dd48b106e51222f..a9a7acd487902e54253d38bd9ef79ce52be9bc86 \
  -- press/press/doctype/deploy_candidate/cache_utils.py \
  press/saas/doctype/product_trial_request/product_trial_request.py \
  > "$PRESS_AUDIT_DIR/master-history.txt"
```

Sığ klon denetimi `false` vermelidir.
`--full-history` seçeneği zorunludur. Seçenek olmadan aynı geçmiş listeleri oluşmaz.
Sabit uçlar kullanıldığı için dalın sonradan ilerlemesi geçmiş kapsamını değiştirmez.

Aşağıdaki komut, kaydedilen kanıtı Git nesneleriyle karşılaştırır.
Etiket nesnelerini commit koduna çevirirken `^{commit}` kullanır.
Uzak etiketler veya dallar değişirse canlı liste denetimi başarısız olabilir.
Bu durumda yeni liste, tarihli eski kanıtla aynı kabul edilmez.

```sh
python3 -B - <<'PY'
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

audit_dir = Path(os.environ["PRESS_AUDIT_DIR"])
evidence = json.loads(Path(os.environ["PRESS_AUDIT_EVIDENCE"]).read_text())
git_path = shutil.which("git")
assert git_path is not None

def git(*args):
    return subprocess.check_output(
        [git_path, "-C", str(audit_dir / "repo.git"), *args], text=True
    ).strip()

def remote_refs(filename):
    return dict(
        (ref, oid)
        for oid, ref in (
            line.split() for line in (audit_dir / filename).read_text().splitlines()
        )
    )

assert git("rev-parse", "--is-shallow-repository") == "false"
tags = remote_refs("tags.txt")
heads = remote_refs("heads.txt")
default_head = (audit_dir / "default-head.txt").read_text().splitlines()
assert "ref: refs/heads/develop\tHEAD" in default_head
assert len(tags) == evidence["published_tag_count"] == 714
versions = {}
for ref, oid in tags.items():
    name = ref.removeprefix("refs/tags/")
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", name)
    assert match is not None, name
    assert git("rev-parse", ref) == oid, name
    versions[name] = tuple(map(int, match.groups()))

unprefixed = sorted(name for name in versions if not name.startswith("v"))
assert unprefixed == evidence["unprefixed_semver_tags"] == ["0.2.0", "0.2.1", "0.3.0"]
later = {name for name, version in versions.items() if version > (0, 154, 1)}
assert len(later) == evidence["later_semver_tag_count"] == 162
observed_refs = {
    name: git("rev-parse", f"refs/tags/{name}^{{commit}}")
    for name in later | {evidence["baseline"]}
}
for branch in ("develop", "master"):
    observed_refs[branch] = heads[f"refs/heads/{branch}"]
    assert git("rev-parse", f"refs/heads/{branch}") == observed_refs[branch]
assert observed_refs == evidence["refs"]

snapshots = set(observed_refs.values())
for branch, expected_count in (("develop", 87), ("master", 31)):
    history = (audit_dir / f"{branch}-history.txt").read_text().splitlines()
    assert history == evidence["histories"][observed_refs[branch]]
    assert len(history) == expected_count
    snapshots.update(history)
assert len(snapshots) == evidence["source_snapshot_count"] == 269
assert snapshots == set(evidence["snapshots"]) == set(evidence["cookies_snapshots"])

for commit in snapshots:
    assert git("rev-parse", f"{commit}:{evidence['cache_path']}") == evidence["cache_blob"]
    assert git("rev-parse", f"{commit}:{evidence['telemetry_path']}") == evidence["snapshots"][commit]
    assert git("rev-parse", f"{commit}:{evidence['cookies_path']}") == evidence["cookies_snapshots"][commit]

cache_lines = git("show", evidence["cache_blob"]).splitlines()
assert cache_lines[evidence["cache_statement_line"] - 1].strip() == "CommandOutput = TypedDict("
for snapshot_key, blob_key in (("snapshots", "telemetry_blobs"), ("cookies_snapshots", "cookies_blobs")):
    assert set(evidence[snapshot_key].values()) == set(evidence[blob_key])
    for blob, statement in evidence[blob_key].items():
        lines = git("show", blob).splitlines()
        assert lines[statement["line"] - 1].strip() == statement["import"]
assert len(evidence["telemetry_blobs"]) == 21
assert len(evidence["cookies_blobs"]) == 1
baseline = observed_refs[evidence["baseline"]]
assert evidence["cookies_baseline"] == {
    "commit": baseline,
    "blob": evidence["cookies_snapshots"][baseline],
    "in_snapshots": baseline in snapshots,
}
print("pass: 714 tags, 162 later tags, 87/31 history entries, 269 snapshots")
print("pass: cache blob, 21 telemetry blobs, 1 cookies blob and baseline")
PY
```

Bu komut mevcut kanıt dosyasını değiştirmez.
269 kayıt, etiketlerin ve iki geçmiş listesinin küme birleşimidir.
Aynı commit, birleşimde yalnız bir kez sayılır.
Çerez taraması bu kümeyi yeniden kullanır. Kümeyi genişletmez.

## İlk sürüm karşılaştırmasının kabul testleri

Bu bölüm 22 Kasım 2026 Pazar günkü ilk develop denemesini kaydeder.
Test sayıları, inceleme sonrası genişletilen testlerin sonucu değildir.

Yeni Frappe temel imajı üretilmedi.
Deneme `frappe/erpnext:v16.55.0` temel imajında çalıştı.
Gerçek Python sürümü 3.14.10 oldu. Gerçek Frappe sürümü 16.56.0 oldu.
Derleme tek başına çalıştırıldı. Aynı anda başka ağır derleme başlatılmadı.
Başlangıçta kullanılabilir bellek 49 GiB oldu. Boş disk 87 GB oldu.

```sh
docker --context colima-factory build \
  --build-arg PRESS_REVISION=d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410 \
  -f backend/dev/press/Dockerfile.unpatched \
  -t fs-pd-press-py314:probe .

docker --context colima-factory compose \
  -f backend/dev/press/compose.unpatched.yaml run --rm probe
```

| Denetim | Sonuç |
| --- | --- |
| Develop adayının derlenmesi | `pass` |
| Tam commit kodu ve boş Press `git diff HEAD` | `pass` |
| Beklenmeyen yeni Press dosyası bulunmaması | `pass` |
| Python 3.14 ve Frappe 16 sürüm denetimi | `pass` |
| Press yürütücüsü ve yerel Ansible görevi | `pass` |
| Standart modüller, Telegram ve Stripe import'u | `pass` |
| `cache_utils` ve bağımsız `TypedDict` denemesi | `fail` |
| Ürün denemesi modülü ve bağımsız telemetri import'u | `fail` |
| Son etiket ve master için ayrı imaj derlemesi | `not_run` |
| Site, HTTP ve Press masası | `not_run` |

On testin altısı geçti. Dördü aynı iki kaynak engeliyle kaldı.
Test komutu 1 koduyla çıktı. Hatalar beklenen başarı olarak işaretlenmedi.
Press dosyaları değiştirilmedi. Standart kitaplık gölgelenmedi.
Kaynak kodu bellekte değiştirilmedi.

Bağımsız inceleme, aday testlerinde iki yanlış ret riski buldu.
Telemetri testi, seçili kaynağın gerçek import satırlarını izlemek zorundadır.
Kaynak bu import'u kaldırırsa eski hata ayrıca üretilmez.
TypedDict testi de geçerli sınıf biçimini kabul etmek zorundadır.
Bu iki durum için regresyon testleri eklendi.
Gerçek modül açılışı testleri her adayda zorunlu kaldı.

Son etiket ve master için aynı deneme yeniden derlenmedi.
İki engeli taşıyan dosyalar bu üç kaynakta birebir aynıdır.
Site açılışının ön koşulu başarısız olduğundan site ve masa denenmedi.
Deneme imajı ayrıca tam Press bağımlılık kurulumu değildir.
Bu kapsamın dışında kalan işlevler çalışıyor diye sunulmaz.

## Bağımsız incelemeyle tamamlanan kapsam

İnceleme, v0.154.1 kaynağında üçüncü kaynak engelini doğruladı.
`press/api/cookies.py:7`, Frappe'den `get_cookie_dict_from_headers` işlevini ister.
Kurulu Frappe 16.56.0 bu işlevi sunmaz. Çerez tercihi modülü açılamaz.
`Dockerfile.unpatched`, Press'i `--no-deps` seçeneğiyle kurar.
Bu seçim bağımlılık çözümünü atlar. Tam bağımlılık kilidi sağlamaz.
Press'in paket şartlarıyla aday sürümler arasında çelişkiler vardır.
Örneğin Ansible `3.4.0` şartını aday `14.0.0` karşılamaz.
`uv pip check` eksik paketleri ve bu çelişkileri reddeder.

Genişletilen kabul testleri iki yeni engeli ayrı ayrı denetler.
Testler, geliştirme işaretini ve yama betiğini de reddeder.
Kurulu paketlerdeki `.orig` yedekleri ve `press-local:` izleri ayrıca denetlenir.
Bu iz taraması, paket dosyalarının tam bütünlüğünü kanıtlamaz.
Önceki on testlik sonuç bu kapsamın çalıştırıldığı anlamına gelmez.
[Press önerisi](press-python314-upstream.md) güncel engelleri ve kabul sonuçlarını kaydeder.

22 Kasım 2026 Pazar günü genişletilen testler başlangıç kaynağıyla çalıştırıldı.
Bu devam denemesi `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` kaynağına sabitlendi.
On üç testin yedisi geçti. Altısı başarısız oldu.
`TypedDict` ve telemetri engelleri ayrı ayrı ikişer testi düşürdü.
Çerez import'u bir testi düşürdü. Bağımlılık denetimi de bir testi düşürdü.
Kaynak bütünlüğü ve yama izi denetimleri geçti.
`uv pip check`, 177 pakette 32 uyumsuzluk buldu.
Bu sayı eksik paketleri ve sürüm çelişkilerini birlikte içerir.
Bu yeni sonuç, bütün etiketlerin genişletilen testlerden geçtiği anlamına gelmez.

Hazır telemetri yardımcısı `press/utils/telemetry.py:14` içinde bulunur.
Öneri, bu yardımcıyı yeniden kullanmayı değerlendirir.
İkinci `TypedDict`, `test_deploy_candidate.py:39` satırındaki `AppInfo` tanımıdır.
Bu tanım `typing.TYPE_CHECKING` bloğundadır. Ek çalışma zamanı hatası sayılmaz.
İki dosyalık tarihsel taramanın commit kümesi korunur.
Kanıt dosyasına aynı kümedeki çerez dosyasının eşlemeleri eklendi.

## Diğer yolların sonucu

Alternatif yolları ikinci ajan inceledi.
Ana ajan kanca sırasını imajdaki gerçek Frappe dosyalarından doğruladı.

| Yol | Neden çözüm sağlamıyor? |
| --- | --- |
| `typing_extensions` veya farklı paket sürümü | Press doğrudan Python'un `typing` modülünü kullanır. Ek paket bu import'u değiştirmez. |
| `override_doctype_class` | Frappe önce özgün modülü yükler. Özel sınıf ancak bundan sonra uygulanır. |
| `extend_doctype_class` | Frappe genişletmeyi özgün sınıf yüklendikten sonra uygular. |
| Telemetriyi ayarla kapatma | Hata, ayar okunmadan önceki import satırında oluşur. |
| `posthog` paketini kurma | Paket, Frappe'den kaldırılan işlevi geri getirmez. |
| Python `-O` veya `-OO` seçeneği | Bu seçenekler normal modül atamasını ve import'u kaldırmaz. |
| Modülü geç yükleme veya atlama | Modül çalıştırıldığında aynı hata oluşur. Kabul koşulu karşılanmaz. |
| Eski modülü gölgeleme veya başlangıç yaması | Bu yollar kullanıcının açık sınırlarını ihlal eder. |
| Python veya Frappe ana sürümünü düşürme | Python 3.14 ve Frappe 16 hedefleri korunmaz. |

Kurulu Frappe kaynağında `frappe/model/document.py:140` özgün modülü yükler.
Özel sınıf seçimi bu çağrıdan sonra uygulanır.
Genişletme kancası `document.py:218` içinde okunur.
`frappe/modules/utils.py:291` standart DocType modülünü yükleyen işlevdir.
Bu işlev, özel sınıf kancasından bağımsız çalıştığını da belirtir.
Frappe telemetri kaynağında `init_telemetry` işlevi yoktur.

[Frappe denetleyici yükleme sırası](https://github.com/frappe/frappe/blob/v16.56.0/frappe/model/document.py#L126-L168)
[Frappe standart modül yükleyicisi](https://github.com/frappe/frappe/blob/v16.56.0/frappe/modules/utils.py#L291-L308)
[Python TypedDict sözleşmesi](https://docs.python.org/3.14/library/typing.html#typing.TypedDict)

## Kapanış kararı

İncelenen resmî sürümlerde ve belirtilen dal geçmişlerinde uygun kaynak bulunmadı.
Yeni Press sürümü seçilmedi. Geliştirme kaydı `v0.154.1` olarak kaldı.
Mevcut [Press önerisi](press-python314-upstream.md) geçerlidir. Öneri henüz gönderilmedi.
O-18 ve ilgili borç satırı açık kalır.
Bu sonuç yalnız kaydedilen tarama kapsamı ve tarih için geçerlidir.

Deneme container'ları ve geçici birimler kapatılıp silinir.
Bu görevin bütün imaj etiketleri de silinir.
Görev C için çalışan yamasız Press ortamı sağlanamadı.
Bu inceleme düzeltmeleri `5367105` üzerine eklenir. Geçmiş yeniden yazılmaz.

Gerçek okurla denenmedi.
