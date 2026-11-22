# Yapay zekâ uygunluk kapısı

## Denetimler ve bulguların kapanışı

Depo kökünde `backend/dev/bin/ai-readiness` komutunu çalıştırın.
Kapı her bulgu için dosyayı, satırı ve kuralı gösterir.
Programdan okumak için komuta `--json` ekleyin.

- `0` hiçbir hata bulgusu olmadığını gösterir.
- `1` en az bir hata bulgusu olduğunu gösterir.
- `2` komut veya çalışma ortamı hatasını gösterir. Örneğin Git yolu bulunmayabilir.

Tablodaki **Her kipte** ifadesi, kural çalışıp hata bulduğunda kapının durduğunu belirtir.
Yalnız uyarı veya `not_run` sonucu kapıyı durdurmaz.
`not_run`, denetimin bir kısmının veya tamamının çalışmadığını belirtir.
Kapı tek tek denetimleri kapatan bir seçenek sunmaz.
Orkestratör, ad denetiminin kipini `backend/dev/naming/enforcement.json` dosyasından yönetir.

| Kural | Kapı neyi bulur? | Kapı ne zaman durur? | Bulguyu nasıl kapatırsınız? |
| --- | --- | --- | --- |
| `input` | Okunamayan dosya, bozuk kaynak veya eksik modül sınırı. | Her kipte. | Dosyayı veya modül sınırı kaydını düzeltin. |
| `doctype` | Kayıt türünde veya alanında eksik açıklama. | Her kipte. | Eksik açıklamayı DocType tanımına ekleyin. |
| `endpoint`, `test-endpoint` | Ağ işleviyle OpenAPI sözleşmesinin uyuşmaması veya ağdan açılan test işlevi. | Her kipte. | İşlevi ve sözleşmeyi eşleyin. Test işlevini ağ erişimine kapatın. |
| `provider`, `model` | Yasak sağlayıcı kitaplığı veya uygulama koduna yazılan model adı. | Her kipte. | Sağlayıcı işlemini model geçidine taşıyın. Model adını kayıt listesine yazın. |
| `scheduler` | Kanca veya kayıt yoluyla eklenen zamanlanmış iş. | Her kipte. | Zamanlamayı kaldırın. İş için onaylı elle başlatma yolunu kullanın. |
| `hook-dynamic` | `hooks.py` içinde yıldızlı içe aktarma veya dolaylı kanca kaydı. | Her kipte. | Kancayı dosyanın en üst düzeyinde tek atamayla yazın. |
| `ai-tool` | Eksik araç işlevi, açıklama veya yazma önizlemesi. Kapı, ağdan çağrılabilen yazma işlevini de bulur. | Her kipte. | Geçerli işlevleri ve açıklamaları ekleyin. Önizlemeyi ayırın. Yazmayı ortak insan onayı yoluna bağlayın. |
| `sql` | Yapay zekâ araçlarında ham SQL veya doğrudan veritabanı erişimi. Kapı çözülemeyen araç kancasını da bildirir. | Her kipte. | Frappe'nin izin denetleyen veri yolunu kullanın. Kanca adresini düzeltin. |
| `website-user` | İzin listesinde eksik, ağdan kapalı veya yöneticiye ya da servise ayrılmış yöntem. | Her kipte. | Uygun olmayan yöntemi listeden çıkarın. Hazır Frappe yöntemleri için sözleşmenin 5. bölümünü kullanın. |
| `decision-number` | Aynı dört haneli numarayı taşıyan karar notları. | Her kipte. | Orkestratörün verdiği boş numarayı kullanın. Bağlantıları da güncelleyin. |
| `forbidden-name` | Git'in izlediği ad, içerik ve kayıt mesajlarında D-13 ihlali. Kapı Git taraması hatasını da bildirir. | Her kipte. | Adı proje kararındaki karşılığıyla değiştirin. Kayıt geçmişi için orkestratöre bulgu adresini bildirin. |
| `naming.*` | Ad betiğinin bulduğu kural ihlali. | `advisory` kipinde uyarı. `enforce` kipinde yalnız `legacy-name`, `turkish-name`, `module-name` ve `translation-binding` durdurur. | Bildirilen adı veya çeviri bağını düzeltin. |
| `naming-config`, `naming` | Geçersiz ad ayarı veya çalışmayan ad betiği. | Hatalı kip dosyası veya bozuk betik her kipte durdurur. Betik yoksa yalnız `enforce` durdurur. | Kip dosyasını düzeltin. Gereken ad betiğini geri yükleyin. |
| `translation-columns`, `translation-duplicate` | Üç sütun taşımayan kayıt veya yinelenen kaynak ve bağlam çifti. | Her kipte. | Kaynak, çeviri ve bağlam sütunlarını tamamlayın. Yinelenen çifti tek kayda indirin. |
| `translation-core` | Frappe ile aynı bağlamsız kaynağa verilen farklı çeviri veya okunamayan katalog. | Her kipte. Katalog yoksa `not_run` görünür. | Çekirdek çevirisini kullanın veya farklı anlama bağlam ekleyin. Katalog okuma hatasını giderin. |
| `dependency-frappe` | Frappe 16.56.0'ın kesin sürümünü dışarıda bırakan uygulama kuralı. | Her kipte. Kaynak veya desteklenen sürüm kuralı yoksa ilgili karşılaştırma `not_run` kalır. | `pyproject.toml` kuralının Frappe sürümüne izin vermesini sağlayın. |
| `dependency-rule`, `dependency-input` | Uygulamalar arasında farklı sürüm kuralı veya okunamayan bağımlılık dosyası. | Her kipte. Desteklenmeyen biçim `not_run` olarak atlanır. | Sürüm kurallarını eşleyin. Varsa TOML dosyasındaki okuma hatasını düzeltin. |
| `shellcheck.SC…` | Kabuk betiklerinde söz dizimi, tırnak veya taşınabilirlik sorunu. | Her kipte uyarı. Sabit imaj yoksa `not_run` görünür. | Sahip iş, bildirilen satırı ShellCheck kuralına göre düzeltir. |

Frappe kaynağının yolunu `FRAPPE_SOURCE` değişkenine yazın.
İsterseniz yolu `--frappe-root <yol>` seçeneğiyle verin. Bu seçenek önceliklidir.
Kaynak yoksa çekirdek karşılaştırmaları atlanır.
Kip dosyası yoksa kapı ad denetimini `advisory` kipinde çalıştırır.

`backend/dev/bin/ai-readiness --list-interfaces` modül arayüzlerini listeler.
İç işlev aktarımları listeye uyarı olarak girer.
Testleri çalıştırmak için `backend/dev/bin/ai-readiness --self-test` kullanın.
Düzeltmeden sonra aynı taramayı yeniden çalıştırın.

- [0010 karar notu](../../docs/kararlar/0010-ai-readiness-gate.md)
- [Arka uç sözleşmeleri](../../docs/sozlesmeler.md)
