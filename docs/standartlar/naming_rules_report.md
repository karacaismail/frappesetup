# Ad verme kuralları raporu

Bu rapor koddaki adların nasıl seçileceğini anlatır. Rapor geliştiriciler ve yapay zekâ kod araçları içindir.

Raporu Claude, Codex ve Gemini birlikte hazırladı. Üç model önce ayrı ayrı araştırdı. Sonra Claude sonuçları birleştirdi. Codex ve Gemini birleşik metni iki turda inceledi ve onayladı. Ayrıntılar 14. bölümdedir. Tarih 22 Kasım 2026 Pazar günüdür.

Raporun açıklamaları Türkçedir. Kod örnekleri ve adlar İngilizcedir.

## 1. Proje sahibinin kararı

Proje sahibi 22 Kasım 2026 Pazar günü şu kararı verdi:

> codes, kodlar, coding, ingilizce olacak.

Kararın sonucu şudur:

- Bütün kod adları İngilizce olur.
- Varsayılan dil İngilizcedir.
- Adlarda yalnız İngilizce alfabenin harfleri kullanılır.
- Türkçe ekran metnini Frappe'nin çeviri sistemi üretir.

Bu karar üç temel kural olarak yazıldı.

**AV-1 (ZORUNLU).** Bütün kod adlarını İngilizce yazın.

Kod adı, kodda bir şeye verilen addır. Bu ada "tanımlayıcı" (identifier) da denir. Sınıf, işlev, değişken ve sabit bu kapsamdadır. Uygulama, modül, DocType ve alan adı da kapsamdadır. API alanı, dosya, klasör ve ortam değişkeni de kapsamdadır.

- Yanlış: `belge_turu`, `SP Denetim Kaydi`, `hesaplaKdv()`.
- Doğru: `document_type`, `SP Audit Log`, `calculateVat()`.

**AV-2 (ZORUNLU).** Kod adında yalnız ASCII karakter kullanın.

ASCII, İngilizce alfabenin harflerini, rakamları ve temel işaretleri kapsar. Türkçe harfler ASCII değildir: `ç`, `ğ`, `ı`, `İ`, `ö`, `ş`, `ü`.

Harfleri değiştirilmiş Türkçe de kullanmayın. Örneğin `kayit` ve `cagri` yazmayın. Bunlar ne İngilizcedir ne de doğru Türkçedir.

**AV-3 (ZORUNLU).** Ekran metnini İngilizce kaynak metinle yazın. Türkçesini çeviri dosyasına yazın.

Frappe'de Python metnini `_()` ile sarın. JavaScript metnini `__()` ile sarın. Türkçe karşılık `locale/tr.po` dosyasına girer. Ayrı arayüzde aynı işi çeviri kitaplığı yapar.

```python
frappe.throw(_("Invoice {0} is already paid").format(invoice.name))
```

Türkçe iş terimleri kodda yaşamaz. Bu terimler terim sözlüğünde yaşar. Sözlük 4.4. bölümde anlatılır.

## 2. Terimler

Bu raporda şu terimler geçer:

- **Kod adı (identifier).** Kodda bir şeye verilen addır. Örneğin `invoice_total`.
- **ASCII.** İngilizce harfleri, rakamları ve temel işaretleri kapsayan karakter kümesidir.
- **Yazım biçimi (case style).** Kelimelerin bir ada nasıl birleştiğini gösterir.
- **`snake_case`.** Küçük harf ve alt çizgi kullanır. Örnek: `due_date`.
- **`camelCase`.** İlk kelime küçük, sonrakiler büyük harfle başlar. Örnek: `dueDate`.
- **`PascalCase`.** Her kelime büyük harfle başlar. Örnek: `InvoiceTable`.
- **`kebab-case`.** Küçük harf ve kısa çizgi kullanır. Örnek: `invoice-table`.
- **`UPPER_SNAKE_CASE`.** Büyük harf ve alt çizgi kullanır. Örnek: `MAX_RETRY_COUNT`.
- **Ön ek (prefix).** Adın başına konan kısa parçadır. Örnek: `SP Audit Log` içindeki `SP`.
- **Harf duyarlılığı (case sensitivity).** Büyük ve küçük harfin farklı sayılıp sayılmadığıdır.
- **DocType.** Frappe'de bir kayıt türünün tanımıdır. Örneğin "Sales Invoice" bir DocType'tır.
- **Alan adı (fieldname).** DocType içindeki bir alanın kod adıdır. Örnek: `posting_date`.
- **Terim sözlüğü (glossary).** İş terimlerini ve kod adlarını eşleyen dosyadır.
- **Ajan.** Kod yazan yapay zekâ aracıdır. Örneğin Claude, Codex ve Gemini.
- **Vibecoding.** Geliştiricinin kodu yapay zekâ aracıyla birlikte yazmasıdır.

Kural düzeyleri şunlardır:

- **ZORUNLU.** Kural her zaman uygulanır.
- **ÖNERİLİR.** Kural uygulanır. Geçerli bir neden varsa nedeni yazılır ve kural atlanabilir.
- **SEÇMELİ.** Ekip isterse uygular.

## 3. En önemli 12 kural

1. Kod adlarını İngilizce yazın (AV-1).
2. Kod adında yalnız ASCII kullanın (AV-2).
3. Ekranın Türkçesini çeviri dosyasına yazın (AV-3).
4. Adı, kodun ne yaptığını anlatacak biçimde seçin (AV-7).
5. Aynı kavrama her yerde aynı adı verin (AV-11).
6. Her uygulama için bir terim sözlüğü tutun (AV-12).
7. Ajana sözlüğü ve ad kurallarını baştan verin (AV-16).
8. Adı değiştirirken bütün kullanım yerlerini arayın (AV-19).
9. Yalnız harf farkıyla ayrılan iki ad kullanmayın (AV-27).
10. Frappe'de alan adını her zaman elle ve açıkça yazın (AV-60).
11. Frappe adlarına uygulama ön ekini koyun (AV-69).
12. Ad kurallarını araçla otomatik denetleyin (AV-71).

## 4. Kendini anlatan kod

Bu bölüm beş yaklaşımı anlatır. Beş yaklaşım da İngilizce kod adlarıyla uygulanır.

### 4.1. Self-Documenting Code (kendini anlatan kod)

Kendini anlatan kod, açıklamaya az ihtiyaç duyan koddur. Okur, kodun ne yaptığını adlardan anlar. Steve McConnell bu konuyu "Code Complete" kitabının 32. bölümünde anlatır.

Yorum, kodun içine yazılan açıklamadır. Kod çalışırken yorumu okumaz. Bu yüzden yorum zamanla koddan kopabilir. Ad ise kodla birlikte değişir.

**AV-4 (ZORUNLU).** Kodu önce iyi adlarla açıklayın. Yorumu sonra ekleyin.

```python
# Kötü: Yorum, kötü adı açıklamaya çalışıyor.
# d: gün sayısı
d = (today - inv.due).days

# İyi: Ad kendini anlatıyor.
days_overdue = (today - invoice.due_date).days
```

**AV-5 (ZORUNLU).** Açık kodu yorumda tekrar etmeyin. Yorumda çoğunlukla nedeni yazın. Gerekirse varsayımı ve sınırı da yazın.

```python
# Kötü: Kodu tekrar ediyor.
retry_count += 1  # retry_count'u bir artır

# İyi: Nedeni anlatıyor.
# Banka servisi ilk istekte sık sık zaman aşımı veriyor.
retry_count += 1
```

**AV-6 (ZORUNLU).** Sihirli sayı yerine adı olan sabit kullanın. Sihirli sayı, anlamı yazılmamış sayıdır.

```typescript
// Kötü
if (fileSize > 5242880) { rejectUpload(); }

// İyi
const MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024;
if (fileSize > MAX_UPLOAD_SIZE_BYTES) { rejectUpload(); }
```

**ÖNERİLİR.** Karmaşık koşulu adı olan bir değişkene koyun. Bu değişkene "açıklayan değişken" (explaining variable) denir.

```python
is_eligible_for_discount = customer.is_active and order.total >= MIN_DISCOUNT_TOTAL
if is_eligible_for_discount:
    apply_discount(order)
```

Ad her şeyi anlatamaz. Şu durumlarda yorum ya da belge gerekir:

- İşin nedeni koddan anlaşılmıyorsa.
- Bir yasa ya da dış kural uygulanıyorsa. Örneğin KVKK kuralı.
- Bir hatanın etrafından dolanılıyorsa. Hata kaydının bağlantısını ekleyin.
- Dışarıya açık bir işlev ya da uç yazılıyorsa. Bu durumda docstring yazın.

### 4.2. Intention-Revealing Names (niyeti gösteren adlar)

Bu ilke Robert C. Martin'in "Clean Code" kitabından gelir. Kitabın 2. bölümünün adı "Meaningful Names"dir. Bölümü Tim Ottinger yazdı.

Bu ilkeye göre ad üç soruyu cevaplamalı.

- Bu şey neden var?
- Ne yapar?
- Nasıl kullanılır?

Bir ad yorum gerektiriyorsa, ad niyeti göstermiyor demektir.

**AV-7 (ZORUNLU).** Adı, kodun niyetini gösterecek biçimde seçin.

| Kötü ad | İyi ad | Neden |
|---|---|---|
| `data` | `pending_invoices` | Neyin verisi olduğu belli olur. |
| `list1` | `overdue_customers` | Listenin içeriği belli olur. |
| `flag` | `is_email_verified` | Neyi gösterdiği belli olur. |
| `process()` | `send_payment_reminder()` | Yaptığı iş belli olur. |
| `handle(x)` | `approveLeaveRequest(request)` | Hem iş hem girdi belli olur. |
| `dt` | `reference_doctype` | Kısaltma kalkar. |

Frappe alanında da aynı ilke geçerlidir:

```json
{ "fieldname": "status2", "fieldtype": "Select" }
```

Bu alan adı niyeti göstermez. Şu ad gösterir:

```json
{ "fieldname": "approval_status", "fieldtype": "Select" }
```

**AV-8 (ZORUNLU).** Genel ve boş adları kullanmayın.

Şu kelimeler tek başına anlam taşımaz: `data`, `info`, `item`, `obj`, `value`, `result`, `temp`, `tmp`, `stuff`, `misc`, `manager`, `helper`, `utils`, `handler`, `process`.

Bu kelimeleri ancak açık bir kelimeyle birlikte kullanın. Örneğin `utils.py` yerine `date_formatting.py` yazın.

Tek harfli ad kullanmayın. İki istisna var. Kısa döngüde `i` kullanılabilir. Tür değişkeninde `T` kullanılabilir. PEP 8 bu kullanımı önerir.

### 4.3. Clean Code (temiz kod)

"Clean Code" kitabı 2008'de yayımlandı. Kitap, okunması kolay kod için kurallar verir. Ad verme kuralları şunlardır:

**AV-9 (ÖNERİLİR).** Clean Code'un ad kurallarını uygulayın.

1. **Yanıltmayın.** `account_list` adlı değişken liste değilse bu adı kullanmayın.
2. **Anlamlı fark yaratın.** `customer_info` ile `customer_data` arasındaki fark anlaşılmaz.
3. **Söylenebilir ad seçin.** `genymdhms` yerine `generated_at` yazın.
4. **Aranabilir ad seçin.** `7` yerine `MAX_CLASSES_PER_STUDENT` yazın.
5. **Türü ada eklemeyin.** `str_name` ve `IUserService` yazmayın. Bu yönteme Macar gösterimi (Hungarian notation) denir.
6. **Sınıfa isim, işleve fiil verin.** `Invoice` bir sınıftır. `send_invoice()` bir işlevdir.
7. **Bir kavram için bir kelime seçin.** Aynı iş için `fetch`, `get` ve `retrieve` kelimelerini karıştırmayın. Örneğin veritabanından okumaya `get_` deyin. Ağdan okumaya `fetch_` deyin. Bu eşlemeyi sözlüğe yazın.
8. **Kelime oyunu yapmayın.** Farklı işlere aynı kelimeyi vermeyin.
9. **İş alanının kelimelerini kullanın.** Bu konu 4.4. bölümdedir.
10. **Bağlam ekleyin, fazlasını eklemeyin.** `Address` sınıfında `address_street` yazmayın. `street` yeterlidir.

Clean Code eleştirilir de. Eleştirilerin özü şudur:

- John Ousterhout daha çok yorum ister. Ousterhout'un kitabının adı "A Philosophy of Software Design"dır. Ousterhout'a göre arayüzün yorumu gereklidir. İki yazar bu konuyu 2024 ve 2025 yıllarında tartıştı.
- qntm adlı yazar 2020'de bir yazı yazdı. Yazıya göre kitabın örnekleri kendi kurallarıyla çelişir.
- Casey Muratori 2023'te kitabın bazı kurallarını hız yönünden eleştirdi.
- Kitabın bazı örnekleri çok küçük işlevler önerir. Bu durum kodu takip etmeyi zorlaştırabilir.

Eleştirilerin çoğu ad kurallarına değil, işlev boyutuna ve yorumlara yöneliktir.

Bu rapor dengeli yolu seçer. Ad kurallarını uygulayın. Herkese açık işlevde docstring yazın. Nedeni yorumda anlatın.

### 4.4. Ubiquitous Language (ortak dil)

Bu ilke Domain-Driven Design yaklaşımından gelir. Eric Evans bu yaklaşımı 2003'te yayımlanan kitabında anlattı. Domain-Driven Design kısaca DDD diye yazılır.

Ortak dilde iş uzmanı ve geliştirici aynı terimleri kullanır. Aynı terimler kodda, belgede ve konuşmada geçer.

Sınırlı bağlam (bounded context), bir terimin tek anlam taşıdığı alandır. Bu projede sınırlı bağlam çoğunlukla bir Frappe uygulamasına denk gelir. Ama bu kendiliğinden doğru değildir. Her terimin bağlamını sözlüğe açıkça yazın. Örneğin "Order" kelimesi satış uygulamasında satış siparişidir. Depo uygulamasında başka bir anlam taşıyabilir.

Proje sahibinin kararıyla kod İngilizcedir. İş konuşması ise Türkçedir. Bu iki dili terim sözlüğü bağlar.

**AV-10 (ZORUNLU).** Her iş kavramına bağlamı içinde tek İngilizce ad verin. Bu eşlemeyi ve bağlamı terim sözlüğüne yazın.

**AV-11 (ZORUNLU).** Aynı kavrama bütün katmanlarda aynı adı verin.

Örneğin "denetim kaydı" kavramını düşünün. Sözlükte karşılığı `audit_log` olsun. O zaman adlar şöyle olur:

| Katman | Ad |
|---|---|
| DocType | `SP Audit Log` |
| Python sınıfı | `SPAuditLog` |
| Alan adı | `audit_log` |
| API alanı | `audit_log` |
| TypeScript türü | `AuditLog` |
| Ekranın kaynak metni | "Audit Log" |
| Ekranın Türkçe çevirisi | "Denetim Kaydı" |

**AV-12 (ZORUNLU).** Her uygulamanın kökünde bir terim sözlüğü tutun. Sözlüğü işin başında açın.

Sözlüğün yeri `docs/glossary.yaml` dosyasıdır. Sözlük makinenin de okuyacağı biçimde olsun. Böylece denetim aracı sözlüğü kullanabilir.

```yaml
- term_tr: Denetim Kaydı
  code: audit_log
  doctype: SP Audit Log
  definition_tr: Bir işlemi kimin ve ne zaman yaptığını tutan kayıt.
  avoid: [audit_record, inspection_log, log_entry]
```

Sözlükteki `avoid` alanı, kullanılmayacak eş anlamlıları listeler. Ajan bu listeyi okuyunca yeni eş anlamlı uydurmaz.

Her sözlük satırında dört bilgi bulunur. Bunlar Türkçe terim, İngilizce kod adı, kullanım yeri ve tanımdır.

Bir terim iki uygulamada iki anlam taşıyabilir. Bu durumda her uygulama terimi kendi sözlüğünde tanımlar. İki kod adının ön eki de farklı olur.

Sözlükteki Türkçe terim `tr.po` dosyasındaki çeviriyle aynı olur. Böylece kullanıcı ekranda sözlükteki terimi görür.

Türkiye'ye özgü kavramlar için şu yolu izleyin:

- İngilizce genel bir karşılık varsa onu kullanın. Örneğin vergi numarası için `tax_id` yazın.
- Kavram bir özel addaysa kısaltmasını ASCII olarak kullanın. Örneğin `mersis_number`. Bu adı sözlüğe yazın.

### 4.5. Literate Programming (okunur programlama)

Donald Knuth bu yaklaşımı 1984'te yayımladı. Knuth'a göre program önce insan için yazılmalıdır. Program, bir yazı gibi okunmalıdır. Kod ve açıklama aynı belgede iç içe durur. Knuth bunun için WEB adlı aracı yazdı. Sonra CWEB geldi.

Bugün bu yaklaşımın tam hâli az kullanılır. Ama izleri her yerdedir. Örneğin docstring, Jupyter defteri ve README dosyası bu yaklaşıma yakındır.

Bu projede yaklaşım ölçülü uygulanır.

**AV-13 (ZORUNLU).** Üç tür işleve docstring yazın:

1. Dışarıya açık uçlar.
2. Paylaşılan servis işlevleri.
3. Davranışı adından anlaşılmayan işlevler.

Docstring, işlevin başındaki açıklama metnidir. `@frappe.whitelist()` işlevi HTTP ile çağrılabilir yapar. Bu yüzden her uç dışarıya açıktır. Giriş yapmamış kullanıcı için ayrıca `allow_guest=True` gerekir. Docstring İngilizce olur. Docstring işlevin amacını, girdisini, çıktısını ve yan etkisini anlatır.

Kendini anlatan iç işleve docstring yazmayın. Frappe'nin `validate` gibi olay yöntemlerinde de kodu tekrar eden docstring yazmayın.

```python
@frappe.whitelist()
def list_overdue_invoices(customer: str, limit: int = 20) -> list[dict]:
    """Return unpaid invoices whose due date has passed.

    Only invoices the current user can read are returned.
    """
```

**AV-14 (ÖNERİLİR).** Her modül klasörüne kısa bir `README.md` koyun. Dosya modülün işini ve sınırını anlatsın.

**AV-15 (ÖNERİLİR).** Önemli tasarım kararını bir karar kaydına yazın. Karar kaydına İngilizcede ADR (Architecture Decision Record) denir. Kayıt kararı, nedenini ve sonucunu tutar.

Örneğin bu raporun dil kararı için şu dosyayı açın: `docs/adr/0001-code-names-in-english.md`.

**SEÇMELİ.** Yeni modülde önce README dosyasını yazabilirsiniz. Kodu sonra yazın. Bu yönteme "README-driven development" denir.

**SEÇMELİ.** Veri incelemesi için Jupyter defteri kullanabilirsiniz. Defteri iş koduna bağlamayın.

## 5. Yapay zekâyla kod yazma (vibecoding)

"Vibecoding" terimini Andrej Karpathy Şubat 2025'te kullandı. Terim, kodu yapay zekâ aracına yazdırmayı anlatır.

Ajan adları kendisi seçer. Ajan her oturumda projeyi yeniden okur. Bu yüzden şu sorunlar sık görülür:

- Ajan aynı kavrama farklı adlar verir. Örneğin bir yerde `customer`, başka yerde `client` der.
- Ajan Türkçe ve İngilizceyi karıştırır. Örneğin `get_belge_list` yazar.
- Ajan `data`, `result`, `helper` gibi genel adlar sever.
- Ajan adı değiştirirken bazı kullanım yerlerini unutur.

Aşağıdaki kurallar bu sorunları önler.

**AV-16 (ZORUNLU).** Ajana ad kurallarını ve terim sözlüğünü işin başında verin.

Ajanın kalıcı talimat dosyası `AGENTS.md` dosyasıdır. Codex bu dosyayı okur. Claude Code `CLAUDE.md` dosyasını okur. `CLAUDE.md` dosyasına `@AGENTS.md` satırını yazın. Gemini CLI varsayılan olarak `GEMINI.md` dosyasını okur. Gemini ayarında `context.fileName` listesine `AGENTS.md` ekleyin. Ajanın kuralları gerçekten okuduğunu bir denemeyle doğrulayın.

`AGENTS.md` dosyasına şunları yazın:

1. Bu raporun yerini.
2. Terim sözlüğünün yerini.
3. "Bütün kod adları İngilizce ve ASCII olur" cümlesini.

**AV-17 (ZORUNLU).** Ajan yeni bir iş terimi gerektiğinde sözlüğe bakar. Terim sözlükte yoksa ajan bir ad önerir. İnsan onaylayınca ad sözlüğe girer.

**AV-18 (ÖNERİLİR).** Ajandan, eklediği yeni adları raporun sonunda listelemesini isteyin.

İstemde şu cümle kullanılabilir:

```text
Use only English ASCII identifiers. Follow docs/glossary.yaml.
Keep identifier length proportional to scope. Avoid sentence-long names.
Propose missing domain terms for docs/glossary.yaml first.
At the end, list every new DocType, field, API endpoint, class and glossary term.
```

**AV-19 (ZORUNLU).** Ajan bir adı değiştirince bütün kullanım yerlerini arar.

Arama şu biçimlerin hepsini kapsar:

- Adın tam yazımı. Örnek: `audit_log`.
- Adın öteki yazım biçimleri. Örnekler: `AuditLog`, `auditLog`, `audit-log`, `Audit Log`.
- Frappe'nin ürettiği biçimler. Örnekler: `SPAuditLog`, `sp_audit_log` ve `tabSP Audit Log`.
- Büyük ve küçük harf farkı gözetmeyen arama. Örnek: `rg -i "audit.?log"`.
- Bütün dosya türleri. Örnekler Python, TypeScript, JavaScript, SQL ve JSON dosyalarıdır. Şablon, `.po` çevirisi, yama, rapor, `hooks.py` ve `fixtures` dosyaları da kapsamdadır.
- Frappe'nin ad taşıyan kayıtları. Örnekler Custom Field kaydındaki `dt` ve `options` alanlarıdır. Property Setter ve Dynamic Link değerleri de kapsamdadır.

- Veritabanında saklanan kod. Örnekler Client Script ve Server Script kayıtlarıdır. Rapor sorgusu ve yazdırma şablonu da kapsamdadır. Bunlar dosyada değil, kayıtta durur.

Değişiklikten sonra ilgili akışları test edin. Ad dışarıya açıksa eski adı bir süre koruyun. Bu konu AV-26'dadır.

**AV-20 (ZORUNLU).** Ajanın kodu birleştirilmeden önce adlar gözden geçirilir. Gözden geçiren kişi şu soruları sorar:

1. Ad sözlükteki terimi mi kullanıyor?
2. Ad niyeti gösteriyor mu?
3. Ad İngilizce ve ASCII mi?
4. Aynı kavram için yeni bir eş anlamlı mı geldi?

Araçlar adın biçimini, ASCII kuralını ve sözlükteki yasak adları denetler. Adın anlamını ve iş terimine uyumunu insan denetler. Araçlar 11. bölümdedir.

**AV-21 (ZORUNLU).** Ajan yorumda kodu tekrar etmez. Ajan nedeni yazar. Ajan dışarıya açık işleve docstring yazar.

## 6. Genel ad kuralları

Bu kurallar bütün diller için geçerlidir.

**AV-22 (ÖNERİLİR).** Kısaltma kullanmayın.

Yerleşik kısaltmalar serbesttir. Örnekler: `id`, `url`, `api`, `http`, `json`, `uuid`, `pdf`, `vat`.

Kısaltmayı `PascalCase` ve `camelCase` içinde normal kelime gibi yazın. Örnek: `HttpClient`, `parseJson`. Python sınıfında PEP 8 kısaltmayı büyük yazmaya izin verir. Örnek: `HTTPServerError`. Bir projede tek yolu seçin.

**AV-23 (ÖNERİLİR).** Tek şeye tekil, topluluğa çoğul ad verin.

- Tek kaydın adı `invoice` olur.
- Listenin adı `invoices` olur.
- DocType adı her zaman tekildir. Örnek: `Sales Invoice`.

**AV-24 (ÖNERİLİR).** Doğru ya da yanlış değer taşıyan adı olumlu yazın. Bu değere "mantıksal değer" (boolean) denir.

- Doğru: `is_active`, `has_attachment`, `can_approve`.
- Yanlış: `is_not_valid`, `disable_check`.

Olumsuz ad çift olumsuzluk üretir. Örneğin `not is_not_valid` okunması zordur.

**AV-25 (ÖNERİLİR).** Zamanı ve birimi adın sonuna ekleyin.

| Değer | Ek | Örnek |
|---|---|---|
| Tarih ve saat | `_at` | `created_at` |
| Yalnız tarih | `_date` | `due_date` |
| Süre | `_ms`, `_days` | `timeout_ms` |
| Boyut | `_bytes` | `file_size_bytes` |
| Oran | `_percent` | `discount_percent` |

Para tutarının yanında para birimi alanı da olsun. Örnek: `total_amount` ve `currency`.

**AV-26 (ZORUNLU).** Yayımlanmış bir adı tek adımda değiştirmeyin.

Yayımlanmış ad, başka bir sistemin kullandığı addır. Veritabanı sütunu, API alanı ve MCP aracı böyledir. Frappe uç yolu ve olay adı da böyledir.

Değişiklik iki adımda olur:

1. Yeni adı ekleyin. Bir süre iki adı birlikte okuyun.
2. Bütün kullananlar geçince eski adı kaldırın.

Bu yönteme "genişlet ve daralt" (expand and contract) denir. Mağazadan yüklenen telefon uygulaması geç güncellenir. Bu yüzden telefonun kullandığı adlarda bekleme süresi uzun olur.

**AV-27 (ZORUNLU).** Yalnız büyük ve küçük harfle ayrılan iki ad kullanmayın.

Örneğin `userId` ve `userid` aynı yerde olmasın. `TradeHub Core` ve `Tradehub Core` aynı projede olmasın. Bu konu 9. bölümdedir.

**AV-28 (ZORUNLU).** Ayrılmış adları kullanmayın.

Ayrılmış ad, bir dilin ya da aracın kendine ayırdığı addır. Python'da `class` ve `def` böyledir. SQL'de `order`, `group` ve `select` böyledir. Frappe'nin ayrılmış adları 10. bölümdedir.

Python'un hazır adlarını da ezmeyin. Örnekler `type`, `id`, `list` ve `input` adlarıdır.

**AV-29 (ZORUNLU).** Geçici ek kullanmayın.

Şu ekler kalıcı koda girmez: `_new`, `_old`, `_v2`, `_temp`, `_final`, `_backup`, `2`.

Sürümü adres yolunda ya da Git geçmişinde tutun. Örnek: `/api/v2/`.

**AV-30 (ZORUNLU).** Marka adını ve alan adını koda sabit yazmayın. İkisi de ayardan gelir. Bu kural proje sahibinin kararıdır.

## 7. Yazım biçimleri

Her dilin kendi yerleşik biçimi vardır. Aşağıdaki tablo hangi yerde hangi biçimin kullanılacağını gösterir.

| Yer | Biçim | Örnek |
|---|---|---|
| Python modül ve dosya | `snake_case` | `tax_calculator.py` |
| Python sınıf | `PascalCase` | `TaxCalculator` |
| Python işlev ve değişken | `snake_case` | `calculate_vat()` |
| Python sabit | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_SIZE` |
| Python hata sınıfı | `PascalCase` ve `Error` eki | `QuotaExceededError` |
| Python test | `test_` öneki | `test_vat_is_rounded()` |
| TS ve JS değişken ve işlev | `camelCase` | `fetchInvoices()` |
| TS sınıf, tür, arayüz, enum | `PascalCase` | `InvoiceFilter` |
| TS modül sabiti | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| React bileşeni ve dosyası | `PascalCase` | `InvoiceTable.tsx` |
| React hook | `use` ve `camelCase` | `useInvoices.ts` |
| TS ve React test dosyası | hedef dosyanın adı ve `.test` | `InvoiceTable.test.tsx` |
| Öteki TS dosyaları ve klasörler | `kebab-case` | `date-format.ts` |
| CSS sınıfı | `kebab-case` ve ön ek | `.sp-invoice-card` |
| CSS değişkeni | `kebab-case` | `--surface-primary` |
| Sass değişkeni | `kebab-case` | `$surface-primary` |
| Sass parça dosyası | `_` ve `kebab-case` | `_tokens.scss` |
| Kendi API alanımız | `snake_case` | `due_date` |
| SQL tablo ve sütun | `snake_case` | `audit_log` |
| Ortam değişkeni | `UPPER_SNAKE_CASE` | `PLATFORM_API_URL` |
| URL yolu | `kebab-case` | `/api/v1/audit-logs` |
| Alt alan adı | küçük harf ve tire | `id.example.com` |
| Git dalı | tür ve `kebab-case` | `feat/invoice-search` |
| Git etiketi | `v` ve sürüm | `v1.2.3` |
| Docker imajı ve servis | küçük harf ve tire | `platform-api` |
| Keycloak realm ve client | `kebab-case` | `platform-web` |
| Capacitor uygulama kimliği | ters alan adı, küçük harf | `com.example.platform` |

Tablonun kaynakları 16. bölümdedir.

Tablonun ayrıntıları şu kurallardadır:

**AV-31 (ZORUNLU).** Python adlarında PEP 8'i izleyin. PEP 8, Python'un resmî yazım rehberidir.

**AV-32 (ZORUNLU).** TypeScript ve JavaScript adlarında tablodaki biçimleri izleyin.

- Arayüz adına `I` öneki koymayın. `IUser` yerine `User` yazın.
- Her `const` değişkenini büyük harfle yazmayın. Büyük harf yalnız gerçek sabit içindir.
- React bileşeni büyük harfle başlar. React aracı bileşeni bu yolla tanır.
- Özel hook adı `use` ile başlar. React kuralları bunu ister.

**AV-33 (ZORUNLU).** Bir aracın belirlediği adı değiştirmeyin.

Araçların belirlediği adlara örnekler şunlardır:

- `package.json` içindeki `devDependencies`
- `Dockerfile`, `README.md` ve `AGENTS.md`
- `__init__.py`

JSON ve YAML'de anahtarın biçimini o dosyayı okuyan araç belirler.

**AV-34 (ÖNERİLİR).** Kendi API alanlarımızda `snake_case` kullanın.

Frappe alanları `snake_case` kullanır. API aynı biçimi kullanırsa çeviri katmanı gerekmez. TypeScript türlerini API sözleşmesinden üretin. Örneğin `openapi-typescript` aracıyla üretin. Gelen bütün anahtarları otomatik `camelCase` biçimine çevirmeyin.

**AV-35 (ÖNERİLİR).** CSS sınıf adına uygulamanın ön ekini koyun. Örnek: `.sp-invoice-card`. Ön ek, uygulamalar arasındaki çakışmayı önler.

**SEÇMELİ.** BEM yöntemini kullanabilirsiniz. BEM, bileşen parçasını ve durumunu adlandırır. Örnek: `.sp-invoice-card__title--muted`. CSS Modules da kullanılabilir.

**AV-36 (ZORUNLU).** Ortam değişkeninde `UPPER_SNAKE_CASE` ve uygulama ön eki kullanın.

Tarayıcıya giden değişkende `VITE_` önekini başa koyun. Örnek: `VITE_SP_API_URL`. Gizli değere `VITE_` öneki koymayın. Vite bu önekli değerleri tarayıcıya gönderir.

**AV-37 (ÖNERİLİR).** URL yolunu küçük harf ve `kebab-case` yazın. Koleksiyon adını çoğul yazın. Örnek: `/api/v1/audit-logs`. Frappe'nin kendi yollarını değiştirmeyin.

**AV-38 (ÖNERİLİR).** Git dalını tür ve açıklama ile adlandırın. Örnek: `fix/vat-rounding`.

Commit mesajında Conventional Commits biçimini kullanın. Örnek: `fix(api): handle empty order list`. Tür ve kapsam İngilizce olur.

**AV-39 (ZORUNLU).** Docker imaj adının depo bölümünü küçük harfle yazın. Docker büyük harfi reddeder. Compose servisinde `kebab-case` kullanın.

**AV-40 (ÖNERİLİR).** Olay, iş ve önbellek anahtarlarını şöyle adlandırın:

- Olay (event) olmuş işi anlatır: `invoice.paid`.
- Arka plan işi yapılacak işi anlatır: `send_payment_reminders`.
- Önbellek anahtarı kapsamı taşır: `platform:{tenant}:v1:invoice:{id}`.
- Ayrı arayüzün çeviri anahtarı anlamı taşır: `invoices.form.save_button`.

**AV-41 (ZORUNLU).** OpenAPI `operationId` değeri benzersiz olur. Biçimi `camelCase` ve fiil ile isimdir. Örnek: `listInvoices`.

MCP araç adı uygulama ön eki ve `snake_case` kullanır. Örnek: `sp_list_invoices`. MCP, yapay zekâ araçlarının bağlantı kuralıdır.

**AV-42 (ZORUNLU).** Capacitor `appId` değerini marka adından ayırın. Bu kimlik mağazada kalıcıdır. Marka değişince kimlik değişmez.

## 8. Alt çizgiyle başlayan adlar

Alt çizginin anlamı dile göre değişir. Bu bölüm her yer için kuralı verir.

### Python

**AV-43 (ZORUNLU).** Python'da alt çizgiyi şöyle kullanın:

| Biçim | Anlamı | Ne zaman |
|---|---|---|
| `_name` | İç kullanım | Modül ya da sınıf dışına açılmayan ad. |
| `__name` | Ad karıştırma | Yalnız alt sınıf çakışmasını önlemek için. |
| `__name__` | Python'un özel adı | Yalnız Python'un tanımladığı adlar. Örnek: `__init__`. |
| `name_` | Anahtar kelime çakışması | Örnek: `class_`, `type_`. |
| `_` | Kullanılmayan değer | Frappe dosyası dışında. |

`_name` erişimi engellemez. Bu yalnız bir uyarıdır. Kendi `__name__` biçimli adınızı uydurmayın.

**AV-44 (ZORUNLU).** Frappe Python dosyasında tek `_` adını değişken olarak kullanmayın.

Frappe'de `_` çeviri işlevidir. Değişken olarak kullanılırsa çeviri işlevi bozulur.

```python
from frappe import _

# Yanlış: Döngü, _ çeviri işlevini eziyor.
for _, row in enumerate(rows):
    ...
frappe.throw(_("Row is invalid"))  # Hata verir.

# Doğru
for _row_index, row in enumerate(rows):
    ...
```

### TypeScript ve JavaScript

**AV-45 (ZORUNLU).** Gizlilik için `_` öneki kullanmayın.

- Gerçek gizli alan için `#token` kullanın. Bu alan dışarıdan okunamaz.
- Derleme sırasında gizlilik yeterliyse TypeScript `private` kullanın. Bu alan da çalışırken sıradan alandır. `JSON.stringify` çıktısına girer.
- `_name` biçimi sıradan bir addır. `JSON.stringify` çıktısına girer.

Kullanılmayan parametre `_` ile başlayabilir. Örnek: `(_event) => close()`.

### Frappe

**AV-46 (ZORUNLU).** Alan adını `_` ile başlatmayın.

Frappe bu adları kendine ayırır: `_user_tags`, `_comments`, `_assign`, `_liked_by`, `_seen`. Kaynak: `frappe/database/database.py:94` ve `frappe/model/__init__.py:98`.

Kaydedilmeyecek geçici durumu `doc.flags` içinde taşıyın. Forma ek veri göndermek için `doc.set_onload()` kullanın.

**AV-47 (ZORUNLU).** `hooks.py` içindeki kanca adlarını `_` ile başlatmayın.

Frappe, `_` ile başlayan üst düzey adları kanca saymaz. Bu adları sessizce atlar. Kaynak: `frappe/__init__.py:976-982`. Yardımcı işlevi `_` ile başlatabilirsiniz.

**AV-48 (ZORUNLU).** Kayıt olayı yöntemini `_` ile başlatmayın.

Frappe'nin `run_method` işlevi `_` ile başlayan yöntemi reddeder. Kaynak: `frappe/model/document.py:1514-1518`.

### JSON ve API

**AV-49 (ZORUNLU).** API alanını `_` ile başlatmayın.

Protokolün kendi alanları istisnadır. Örnek: MCP'deki `_meta`.

Gelen JSON'da şu anahtarları reddedin: `__proto__`, `constructor`, `prototype`. Bu anahtarlar JavaScript nesnesini bozabilir. Bu saldırıya "prototype pollution" denir.

### CSS, Sass, ortam değişkeni ve dosya

**AV-50 (ZORUNLU).** Alt çizgiyi yalnız araç istiyorsa kullanın.

- CSS sınıfı `_` ile başlamaz.
- Sass parça dosyası `_` ile başlar. Örnek: `_tokens.scss`. Sass bu dosyadan ayrı CSS üretmez.
- Sass modülünde `_` ya da `-` ile başlayan üye dışarıya açılmaz.
- Sass adlarda tireyi ve alt çizgiyi aynı sayar. `$font-size` ve `$font_size` aynı değişkendir.
- Ortam değişkeni `_` ile başlamaz.
- Dosya adı yalnız araç gerektirirse `_` ile başlar. Örnekler: `__init__.py`, `__main__.py`, `__snapshots__`.

## 9. Harf duyarlılığı ve Türkçe harfler

Bazı sistemler büyük ve küçük harfi farklı sayar. Bazıları aynı sayar. Fark hataya yol açar.

### Dosya sistemi

macOS dosya sistemi çoğunlukla harf duyarsızdır. Linux dosya sistemi harf duyarlıdır. Geliştirici bilgisayarı macOS, sunucu Linux'tur.

Bu yüzden şu hata sık görülür. Kod macOS'ta `./invoicetable` adını bulur. Gerçek dosya `InvoiceTable.tsx` adındadır. Aynı kod Linux'ta dosyayı bulamaz.

**AV-51 (ZORUNLU).** İçe aktarma yolunu dosyanın gerçek harfleriyle yazın.

**AV-52 (ZORUNLU).** Dosya adının yalnız harf biçimini değiştirirken iki adım izleyin:

```bash
git mv InvoiceTable.tsx invoice-table-tmp.tsx
git mv invoice-table-tmp.tsx invoice-table.tsx
```

Git'in `core.ignorecase` ayarı dosya sistemini değiştirmez. Bu ayara güvenmeyin.

**AV-53 (ZORUNLU).** TypeScript ayarında `forceConsistentCasingInFileNames` açık olsun. Derleme ve testi Linux'ta da çalıştırın. Mac bilgisayardaki başarıyı Linux başarısı saymayın.

### Veritabanı

Frappe, MariaDB'de `utf8mb4_unicode_ci` karşılaştırma kuralını kullanır. Kaynak: `frappe/database/mariadb/database.py:131-132`. Karşılaştırma kuralına "collation" denir.

Bu kural MariaDB 11.8.9 üzerinde denendi. Sonuç şudur:

| Karşılaştırma | Sonuç |
|---|---|
| `A` ile `a` | Aynı |
| `İ` ile `i` | Aynı |
| `ş` ile `s` | Aynı |
| `ü` ile `u` | Aynı |
| `ı` ile `i` | Farklı |

Yani bu kural metin değerlerinde büyük ve küçük harfi ayırmaz. `ç`, `ğ`, `ö`, `ş` ve `ü` harflerini de düz harften ayırmaz. Tablo adlarında ise başka bir ayar belirleyicidir. Bu ayarın adı `lower_case_table_names` ayarıdır.

**AV-54 (ZORUNLU).** Kayıt adının harf ya da aksan farkıyla ayrılacağını varsaymayın.

Örneğin `field:` ile adlandırılan iki kayıt düşünün. "Sube" ve "Şube" adlı iki kayıt aynı sayılır. İkinci kayıt "zaten var" hatası verir. Harf duyarlı kimlik gerekiyorsa UUID ya da sayaç kullanın.

PostgreSQL farklı çalışır. Varsayılan ayarda metin değerlerini harf ve aksan duyarlı karşılaştırır. Yani "Sube" ve "Şube" farklı sayılır. Tablo ve sütun adlarında ise tırnaksız adları küçük harfe çevirir. Tırnaklı adların harfini korur.

### Öteki yerler

**AV-55 (ZORUNLU).** Şu farkları bilin ve bir sistemin kuralını ötekine taşımayın:

| Yer | Harf duyarlı mı? |
|---|---|
| Alan adı (domain) | Hayır |
| URL yolu | Evet |
| HTTP başlık adı | Hayır |
| E-posta adresinin `@` öncesi | Olabilir |
| JSON anahtarı | Evet |
| Linux ortam değişkeni | Evet |
| npm paket adı | Yalnız küçük harf kabul edilir |
| Docker depo adı | Yalnız küçük harf kabul edilir |
| Python içe aktarma | Evet |

### Türkçe harfler

Türkçede `I` harfinin küçüğü `ı` olur. `İ` harfinin küçüğü `i` olur. İngilizcede `I` harfinin küçüğü `i` olur. Bu fark kodu bozar.

Python'da şu deneme yapıldı:

```python
"İl".lower()        # 'i̇l' olur. Sonuçta ayrıca görünmez bir nokta işareti var.
"KDV ORANI".lower() # 'kdv orani' olur. Türkçede 'kdv oranı' olmalıydı.
```

JavaScript'te `"ID".toLocaleLowerCase("tr-TR")` sonucu `"ıd"` olur. Bu sonuç anahtar eşleşmesini bozar.

**AV-56 (ZORUNLU).** Kod adı ve anahtar üzerinde dile bağlı harf çevirisi yapmayın.

- Kod adı için `toLowerCase()` ve Python `lower()` kullanın.
- Kullanıcının Türkçe metni için JavaScript'te `toLocaleLowerCase("tr-TR")` kullanın.
- Python'da Türkçe metni küçültmeden önce `İ` ve `I` harflerini çevirin. Örnek: `text.replace("İ", "i").replace("I", "ı").lower()`. Tek başına NFC biçimi `"İl".lower()` sonucundaki görünmez noktayı silmez.
- Türkçe sıralama için `Intl.Collator("tr")` kullanın.
- Kullanıcıdan gelen metni NFC biçimine getirin. NFC, aynı görünen harflerin tek biçimde saklanmasını sağlar.

AV-2 kuralı bu sorunların çoğunu baştan önler. ASCII adda Türkçe harf sorunu çıkmaz.

## 10. Frappe kuralları

Bu bölümdeki Frappe iddiaları Frappe 16.56.0 kaynak kodunda doğrulandı. Satır numaraları o sürüme aittir.

### Uygulama ve modül

**AV-57 (ZORUNLU).** Uygulama adını İngilizce, kısa ve `snake_case` yazın. Örnek: `platform_core`.

`bench new-app` komutu adı `frappe.scrub` ile `snake_case` biçimine çevirir. Kaynak: `frappe/utils/boilerplate.py:23-30`. `frappe.scrub` boşluğu ve tireyi alt çizgi yapar. Sonra harfleri küçültür. Türkçe harfi değiştirmez. Kaynak: `frappe/__init__.py:842-844`.

**AV-58 (ZORUNLU).** Modül adını İngilizce yazın. Her kelimenin ilk harfi büyük olsun. Örnek: `Platform Core`. Yerleşik kısaltma büyük kalır. Örnek: `SEO Core`.

Modül adı üç yerde birebir aynı yazılır:

1. `modules.txt` dosyasında.
2. "Module Def" kaydında.
3. Her DocType dosyasındaki `"module"` alanında.

Klasör adı `frappe.scrub` sonucudur. Örnek: `platform_core`.

### DocType

**AV-59 (ZORUNLU).** DocType adını İngilizce, tekil ve uygulama ön ekiyle yazın. Kelimeler arasına boşluk koyun. Tek istisna ayar türüdür. Ayar türünün adı `Settings` ile biter.

- Denetim kaydının DocType adı `SP Audit Log` olur.
- Alt tablo, başka bir kaydın içindeki satırlardır. Alt tablonun adı `SP Audit Log Item` olur.
- Tek kayıtlı ayar türüne "Single DocType" denir. Bu türün adı `SP Settings` olur.

Frappe 16 DocType adında şu kuralları zorunlu tutar. Kaynak: `frappe/core/doctype/doctype/doctype.py:43-44` ve `1083-1113`.

- Ad en çok 61 karakterdir. Çünkü tablo adı `tab` ile başlar ve sınır 64 karakterdir.
- Ad harfle başlar. Rakamla ya da `_` ile başlayamaz.
- Ad yalnız ASCII harf, rakam, boşluk, `_` ve `-` içerir.
- Türkçe harf reddedilir. Örneğin "SP Denetim Kaydı" adı kabul edilmez.

### Alan adı

**AV-60 (ZORUNLU).** Alan adını her zaman elle ve açıkça yazın.

Frappe alan adını boş bulursa etiketten üretir. Etiket Türkçeyse ad Türkçe harf taşıyabilir. Bu yüzden alan adını etikete bırakmayın.

**AV-61 (ZORUNLU).** Alan adını şu kurallarla yazın:

- İngilizce ve ASCII `snake_case`. Desen: `^[a-z][a-z0-9_]*$`.
- En çok 64 karakter. Kaynak: `frappe/database/schema.py:406-408`.
- Bölüm ayırıcıda `_section`, sütun ayırıcıda `_column`, sekmede `_tab` eki.
- Bağlantı (Link) alanının adı hedef kavramın tekil adıdır. Örnek: `customer`.
- Alt tablo alanının adı çoğuldur. Örnekler: `items` ve `entries`.
- Değişken bağlantıda iki alan kullanın: `reference_doctype` ve `reference_name`.
- Select alanının seçeneklerini İngilizce ve ASCII yazın. Örnekler: `Draft` ve `Approved`. İş akışı durum adları da aynı kurala uyar. Bu değerler veritabanına kod olarak yazılır. Türkçesini `tr.po` dosyasına yazın.

Frappe alan adında Unicode harfi teknik olarak kabul eder. Kaynak: `frappe/database/schema.py:9`. Ama `İ` harfi küçültülünce bozulur. ASCII kuralı bu yüzden projede zorunludur.

**AV-62 (ZORUNLU).** Frappe'nin ayrılmış alan adlarını kullanmayın.

- Standart alanları kullanmayın. Bunlar `name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx` ve `doctype` alanlarıdır. Kaynak `frappe/model/__init__.py:84-93` satırlarıdır.
- Alt tablonun alanlarını kullanmayın. Bunlar `parent`, `parenttype` ve `parentfield` alanlarıdır.
- `file_list`, `flags` ve `autoname` adlarını da kullanmayın. Kaynak `doctype.py:494-508` ve `1336-1356` satırlarıdır.
- `_` ile başlayan sistem alanları. AV-46'ya bakın.
- Document sınıfının yöntem ve özellik adları. Örnekler: `save`, `insert`, `submit`, `get`. Kaynak: `doctype.py:2042-2052`.

### Custom Field

Custom Field, başka bir uygulamanın DocType'ına eklenen alandır.

**AV-63 (ZORUNLU).** Custom Field kaydının `fieldname` değerini `custom_` önekiyle ve elle yazın. Kaydın kendi adı `<DocType>-<fieldname>` biçimindedir. Kaynak: `custom_field.py:130`.

`custom_` önekinden sonra uygulamanın kısa ön ekini de yazın. Örnek: `custom_sp_tax_office`. Bu da zorunludur. Çünkü Custom Field kaydının adı site genelinde tektir. İki uygulama aynı alanı eklerse kayıtlar çakışır.

Frappe `custom_` önekini yalnız ad boşsa ekler. Ad elle verilirse önek eklenmez. Kaynak: `frappe/custom/doctype/custom_field/custom_field.py:134-165`. Kodla ya da `fixtures` ile eklenen alanda öneki siz yazın.

### Kayıt adı

**AV-64 (ZORUNLU).** Kayıt adlandırma yolunu kaydın türüne göre seçin.

- İş belgesi için numara serisi kullanın. Örnek: `SP-INV-.YYYY.-.#####`.
- Çok sık yazılan teknik kayıt için `hash` ya da `UUID` kullanın. Örnek: denetim izi.
- Kalıcı ve tekil bir kodu olan ana veri için `field:` kullanın. AV-54'ü unutmayın.

Seri kalıbında `#` işaretinin önünde nokta olmalıdır. Kaynak: `frappe/model/naming.py:72-75`. Seri öneki İngilizce kısaltma ve büyük ASCII harf olur.

`UUID` seçeneği Frappe 16'da vardır. Frappe 16 bu seçenekte UUIDv7 üretir. Kaynak: `frappe/model/naming.py:165-174`.

### Kod dosyaları ve uçlar

**AV-65 (ZORUNLU).** Controller sınıf adını Frappe'nin kuralına bırakın.

Frappe sınıf adını DocType adından boşluk ve tireyi silerek üretir. `SP Audit Log` için `SPAuditLog` bekler. Kaynak: `frappe/model/document.py:126-141` satırlarındaki `import_controller` işlevi. Klasör ve dosya adı `sp_audit_log` olur. Test dosyası `test_sp_audit_log.py` olur.

**AV-66 (ZORUNLU).** Beyaz listedeki uç adını fiil ve isimle yazın. Örnek: `list_overdue_invoices`.

Beyaz listedeki uç, `@frappe.whitelist()` ile ağa açılan işlevdir. Uçları `<app>/api/` klasöründe toplayın. Uç adresi işlevin tam Python yoludur. Örnek: `/api/method/platform_core.api.invoices.list_overdue_invoices`.

Bu adres bir sözleşmedir. İşlevi taşırsanız eski adresi koruyun. `hooks.py` içindeki `override_whitelisted_methods` ayarı bu işe yarar.

**AV-67 (ZORUNLU).** Yama dosyasını şöyle adlandırın: `<app>/patches/v1_2/backfill_audit_log_tenant.py`.

Yama, eski veriyi bir kez düzelten koddur. Yama işlevinin adı `execute` olur.

Yayımlanmış yamanın satırını değiştirmeyin. Frappe çalışmış yamayı satırın metniyle tanır. Satır değişirse yama yeniden çalışır. Kaynak: `frappe/modules/patch_handler.py:68` ve `162-169`.

**AV-68 (ZORUNLU).** Paket dosyasını `<app>_<ad>.bundle.<uzantı>` biçiminde adlandırın. Frappe şu uzantıları derler: `js`, `ts`, `jsx`, `css`, `scss`, `sass`, `less` ve `styl`. Kaynak: `esbuild/esbuild.js:258`. Paket adı aynı Bench içinde benzersiz olsun. Bench, Frappe uygulamalarını birlikte çalıştıran kurulumdur.

### Ön ek

**AV-69 (ZORUNLU).** Her uygulamanın tek bir kısa ön eki olsun.

Ön ek 2 ile 4 büyük ASCII harftir. Örnekler: `SP`, `SEO`. Ön eki şu adlara koyun:

- DocType
- Rapor (Report)
- Rol (Role)
- Çalışma alanı (Workspace)
- Yazdırma biçimi (Print Format)

Frappe bu kayıtları site genelinde tek adla tutar. İki uygulama aynı adı kullanırsa biri ötekini ezer. Ön ekleri proje kaydında bir listede tutun.

### Çeviri

**AV-70 (ZORUNLU).** Çeviri işlevlerini şöyle kullanın:

- Python'da `_("Invoice {0} is overdue").format(name)` yazın.
- JavaScript'te `__("Invoice {0} is overdue", [name])` yazın.
- Kaynak metin İngilizcedir.
- Çeviri işlevinin içinde f-string kullanmayın. Çeviri aracı f-string metnini okuyamaz.
- Cümleyi parçalardan birleştirmeyin.
- Belirsiz kısa kelimede bağlam verin. Örnek: `_("Open", context="Status")`.

Frappe 15 ve 16 çevirileri `locale/tr.po` dosyasında tutar. Frappe çalışırken bu dosyadan derlenen `.mo` dosyasını okur. Eski `translations/tr.csv` dosyasını da hâlâ okur. Yeni çeviriyi `.po` dosyasına yazın. Kaynak: `frappe/translate.py:174-192` ve `frappe/gettext/translate.py:343`.

## 11. Otomatik denetim

Yazılı kural tek başına yetmez. Araç kuralı her değişiklikte denetlemelidir.

**AV-71 (ZORUNLU, MVP ve üstü).** Ad kurallarını şu araçlarla denetleyin:

| Alan | Araç ve kural |
|---|---|
| Python ad biçimi | Ruff `N` kuralları |
| Python hazır adların ezilmesi | Ruff `A` kuralları |
| Python ASCII dışı ad | Ruff `PLC2401` ve `PLC2403` |
| Frappe `_` ezilmesi | Ruff `F402` yalnız döngüyü yakalar. Atama ve parametre için AV-72 betiği gerekir. |
| TypeScript ad biçimi | `@typescript-eslint/naming-convention`. React bileşeni ve `snake_case` API alanı için ayrı ayar yazın. |
| Dosya harfi | TypeScript `forceConsistentCasingInFileNames` |
| CSS ve Sass | Stylelint `selector-class-pattern`, `custom-property-pattern` ve `scss/dollar-variable-pattern` |
| Commit mesajı | commitlint |
| Git dalı | `git check-ref-format --branch` geçerliliği denetler. Biçim ve ASCII için ayrı desen denetimi gerekir. |
| OpenAPI | Spectral |

Frappe'nin yeni uygulama şablonu Ruff ayarı içerir. Ama bu ayarda `N` kuralları yoktur. Kaynak: `frappe/utils/boilerplate.py:364-378`. Yeni uygulamada `N` kurallarını `pyproject.toml` dosyasına siz ekleyin.

**AV-72 (ZORUNLU, MVP ve üstü).** Frappe adları için küçük bir denetim betiği yazın. Betik her değişiklikte çalışsın. Betik şunları denetler:

1. Alan adları `^[a-z][a-z0-9_]*$` desenine uyuyor mu?
2. DocType ve modül adları ASCII mi?
3. DocType dosyasındaki modül adı `modules.txt` ile harfi harfine aynı mı?
4. Kayıt türü adları uygulama ön ekiyle başlıyor mu? Bu madde DocType, rapor ve rol adlarını kapsar. Çalışma alanı ve yazdırma biçimi de kapsamdadır.
5. Custom Field `fieldname` değerleri `custom_` ve uygulama ön ekiyle başlıyor mu?
6. Küçük harfe çevrilince çakışan iki dosya yolu var mı?
7. `frappe.scrub` sonucu çakışan iki DocType var mı?
8. Kod adları sözlükteki `avoid` listesinde mi? AV-8 ve AV-29'daki yasak adlar var mı?
9. Her DocType'ın sözlükte bir karşılığı var mı?
10. Frappe Python dosyasında `_` adına atama ya da parametre var mı?
11. Git dalı projenin desenine uyuyor mu? Desen örneği: `^(feat|fix|chore|docs|refactor|test)/[a-z0-9-]+$`.

Betik bir kural ihlali bulunca değişiklik reddedilir.

**AV-73 (ZORUNLU).** Biçimlendiriciyi yalnız değişen dosyalarda çalıştırın. Bu kural projenin mevcut kuralıdır. Denetim ve test ise etkilenen kullanım yerlerini de kapsar. Projenin zorunlu denetimlerini atlamayın.

## 12. Mevcut projelerdeki ad sorunları

Bu sorunlar 22 Kasım 2026 Pazar günü bulundu. Bu rapor hiçbir adı değiştirmedi. Her düzeltme ayrı bir iştir. Düzeltme AV-26 kuralına göre yapılır.

1. **TradeHub'da modül adı iki biçimde yazılmış.** `modules.txt` "Tradehub Core" diyor. 287 DocType aynı adı kullanıyor. Dört DocType ise "TradeHub Core" yazıyor. Bunlar Seller Product, Buybox Selection, Catalog Product ve Product Mapping'dir. Dört dosyanın modül adı `modules.txt` ile eşitlenmeli.
2. **TradeHub DocType'larında ön ek yok.** Örnekler "Seller Product" ve "Catalog Product" adlarıdır. Başka bir uygulama aynı adı açarsa çakışma olur.
3. **Sales Partner adları Türkçe.** Örnekler "SP Denetim Kaydi", "SP Arac Cagrisi" ve `belge_turu` adlarıdır. Bu adlar AV-1 ve AV-2 ile çelişir. Geçiş için yeniden adlandırma ve veri taşıma gerekir.
4. **Platform modüllerinin dili karışık.** `platform_core` İngilizcedir. `yapay_zeka` ve `model_gecidi` Türkçedir. Bu adlar yeni olduğu için geçiş daha kolaydır.
5. **`press_tr` adının anlamı belli değil.** `tr` Türkiye'nin ülke kodu olarak okunabilir. Bu durumda ad İngilizce sayılır. Bu anlam sözlüğe yazılmalı.
6. **Arayüzden açılan Custom Field adları denetlenmeli.** Etiketten üretilen ad Türkçe harf taşıyabilir. Kodla açılan alanda `custom_` öneki eksik olabilir. Bu durum projelerde henüz taranmadı.

### Önerilen İngilizce adlar

Aşağıdaki adlar öneridir. Kesin adı uygulamanın terim sözlüğü belirler.

| Şimdiki ad | Önerilen ad |
|---|---|
| `SP Denetim Kaydi` | `SP Audit Log` |
| `SP Arac Cagrisi` | `SP Tool Call` |
| `SP Taslak` | `SP Draft` |
| `SP Taslak Surumu` | `SP Draft Version` |
| `SP Proje` | `SP Project` |
| `SP Karar` | `SP Decision` |
| `SP Kullanici Profili` | `SP User Profile` |
| `SP Asistan Calismasi` | `SP Assistant Run` |
| `SP Asistan Olayi` | `SP Assistant Event` |
| `belge_turu` | `document_type` |
| `belge_adi` | `document_title` |
| `karar_no` | `decision_number` |
| `yapay_zeka` | `ai` ya da `ai_access` |
| `model_gecidi` | `model_gateway` |

`belge_adi` için `document_name` önerilmedi. Bu ad Frappe'nin `name` alanıyla karışır.

### Geçiş sırası

Eski adları güncellerken şu sırayı izleyin:

1. Uygulamanın terim sözlüğünü yazın.
2. Her eski ad için yeni adı sözlüğe ekleyin.
3. Bütün kullanım yerlerini AV-19 kuralıyla bulun.
4. Frappe'nin yeniden adlandırma işlevlerini kullanın.
5. Dışarıya açık adlarda eski adı bir süre okuyun.
6. Türkçe ekran adlarını `tr.po` dosyasına yazın.
7. Denetim betiğini çalıştırın. Bu betik AV-72 kuralındadır.

Frappe'nin yeniden adlandırma işlevleri şöyle kullanılır:

- **DocType adı.** `frappe.rename_doc("DocType", old_name, new_name)` çağrısını kullanın. Kaynak: `frappe/model/rename_doc.py:108`. Bu dosyadaki `rename_doctype` işlevini doğrudan çağırmayın. O işlev yalnız bağlantıları günceller. Kod dosyalarını ve klasörleri ayrıca güncelleyin.
- **Alan adı.** Önce yeni alanı DocType'a ekleyin. Yamada `frappe.reload_doc` ile yeni tanımı veritabanına yükleyin. Sonra `rename_field` ile eski veriyi taşıyın. Kaynak: `frappe/model/utils/rename_field.py:11-60`. Bu işlev sütunun adını değiştirmez. Veriyi yeni sütuna kopyalar. Yeni alan yoksa hiçbir şey yapmadan döner. Taşınan veriyi sayarak doğrulayın.
- **Kayıt adı.** Tek bir kaydın adı için de `frappe.rename_doc` kullanılır.

Ad değişikliğini bir yama içinde yapın. Yama kuralı AV-67'dedir. Önce yedek alın. Değişikliği önce deneme sitesinde çalıştırın.

## 13. Mevcut kural dosyalarıyla ilişki

Bu rapor `rules ai` klasöründeki kural dosyalarıyla birlikte okunur. Üç model kural dosyalarında iki fark buldu:

1. Python dışı kural dosyasında bir ÖNERİLİR kural vardı. Kural yalnız "DocType ve modül adını ASCII harfle seçin" diyordu.
2. Aynı dosyada F-4 kuralı vardı. Kural "Kaynak metni projenin kaynak dilinde yazın" diyordu.

Claude kural dosyalarını 22 Kasım 2026 Pazar günü güncelledi. Codex ve Gemini değişikliği onayladı. Değişiklikler şunlardır:

| Dosya | Kural | Yeni hâli |
|---|---|---|
| Python | M-8 | Kod adları İngilizce ve ASCII olur. Görünen metin İngilizce yazılır ve `frappe._` ile sarılır. |
| Python dışı | H-10 | Eski ÖNERİLİR kuralın yerini aldı. Bütün kod adları İngilizce ve ASCII olur. Değişken, sabit, `class` ve `id` de kapsamdadır. |
| Python dışı | F-4 | Kodda ve tanım dosyalarında kaynak metin İngilizcedir. |
| Ayrı arayüz | TS-9 | Bütün kod adları İngilizce ve ASCII olur. Çeviri anahtarı ve dosya adı da kapsamdadır. |
| Ayrı arayüz | IC-1 | Çevirinin kaynak metni İngilizcedir. |

Kural dosyaları iki düzey kullanır: ZORUNLU ve ÖNERİLİR. Bu rapor üçüncü düzey olarak SEÇMELİ kullanır.

Bu raporun kural kodları `AV` ile başlar. Bu kod öteki kural dosyalarında kullanılmıyor.

## 14. Üç modelin uzlaşması

Üç model önce birbirini görmeden yazdı. Claude 127, Codex 65 ve Gemini 59 kural önerdi.

Üç model şu konularda aynı görüşteydi:

- Kod adları İngilizce ve ASCII olmalı.
- Türkçe ekran metni çeviri dosyasından gelmeli.
- Frappe DocType adı Türkçe harf taşıyamaz.
- Frappe adlarında uygulama ön eki gerekli.
- API alanları `snake_case` olmalı.
- Ad kuralları araçla denetlenmeli.
- TradeHub modül adı tek yazıma inmeli.

Görüş ayrılıkları şöyle çözüldü:

| Konu | Ayrılık | Karar |
|---|---|---|
| Kod dili | Codex dili proje sahibine bıraktı. Gemini İngilizceyi zorunlu yaptı. | Proje sahibi İngilizceyi seçti. |
| `custom_` öneki | Codex önerdi. Gemini zorunlu yaptı. | `custom_` ve uygulama ön eki zorunlu. Gemini 2. turda kayıt çakışmasını gösterdi. |
| Mantıksal değer öneki | Codex, Google'ın `is_` önekini istemediğini yazdı. | `is_` önerilir, zorunlu değil. |
| Seri kilidi | Gemini, sayaçta kilitlenme riski yazdı. | Çok sık yazılan kayıtta `hash` ya da `UUID` önerildi. |
| Denetim kaydının adı | Claude `SP Audit Record`, Claude orkestratörü `SP Audit Log` önerdi. | `SP Audit Log` seçildi. Kayıt yapılan işlemleri tuttuğu için "log" daha doğru. |
| Keycloak rol biçimi | Codex `kebab-case`, Gemini `alan:eylem` önerdi. | Açık karar olarak bırakıldı. |
| Kural kodu | Codex `AD`, Gemini `GN` ve öteki kodları kullandı. İkisi de mevcut kodlarla çakışıyordu. | `AV` seçildi. |

### 2. tur incelemesi

Codex 19, Gemini 22 bulgu gönderdi. İkisi de "düzeltme gerekli" dedi. Claude her teknik bulguyu kaynak kodda ya da belgede denetledi.

Kabul edilen önemli düzeltmeler şunlardır:

- Frappe'nin yeniden adlandırma işlevlerinin doğru kullanımı yazıldı.
- Select seçenekleri ve iş akışı durumları İngilizce kurala bağlandı.
- Terim sözlüğü baştan zorunlu yapıldı.
- Docstring kuralı daraltıldı. Kodu tekrar eden docstring yasaklandı.
- Araç tablosu düzeltildi. Örneğin Ruff `F402` yalnız döngüyü yakalar.

Reddedilen bulgular şunlardır:

| Bulgu | Neden reddedildi |
|---|---|
| Codex: Frappe 15 yalnız `translations/tr.csv` kullanır. | Frappe 15 deposunda `frappe/locale/tr.po` var. `.csv` dosyası yalnız eski yol olarak okunur. |
| Gemini: `import_controller` işlevi `base_document.py` dosyasındadır. | Frappe 16.56.0'da işlev `frappe/model/document.py:126` satırındadır. |
| Gemini: Kodsuz ÖNERİLİR ve SEÇMELİ maddelere kod verin. | Mevcut kural dosyaları da kodsuz ÖNERİLİR maddesi kullanır. Rapor bu biçimi korudu. |

### 3. tur onayı

Claude düzeltilmiş metni Codex ve Gemini'ye yeniden gönderdi. İki model de "onay" verdi. İkisi de engelleyici hata bulmadı.

Codex, Frappe 15 çeviri bulgusunu geri çekti. Gemini, reddedilen iki bulgusuna itiraz etmedi.

## 15. Açık kararlar

Bu konularda karar proje sahibinindir:

1. **Uygulamanın ön eki.** Örneğin `PLT` ya da `CORE`.
2. **Mevcut Türkçe adların geçiş takvimi.** Eski adlar canlı veride kullanılıyor olabilir.
3. **Keycloak rol adlarının biçimi.** Seçenekler `invoice-approver` ve `invoice:approve` biçimleridir.
4. **Commit mesajının açıklama dili.** Tür ve kapsam İngilizcedir. Açıklama Türkçe ya da İngilizce olabilir.

frappesetup projesinde Claude bu kararlardan üçünü kapattı. Kararlar `backend/PROJE-KAYDI.md` dosyasında D-14 maddesindedir:

- Ön ekler `PLT`, `PTR` ve `HRT` oldu. Bunlar `platform_core`, `press_tr` ve `hrms_tr` uygulamalarının ön ekleridir.
- Keycloak rol adları küçük harf ve tireyle yazılır.
- Commit mesajında tür ve kapsam İngilizce olur. Açıklama Türkçe kalır.

frappesetup'ta eski adların düzeltilmesi `naming-history-fix` işinde başladı. TradeHub ve Sales Partner için bu kararlar henüz verilmedi.

## 16. Kaynaklar

Dünya standartları:

- PEP 8, Python yazım rehberi: https://peps.python.org/pep-0008/
- PEP 257, docstring kuralları: https://peps.python.org/pep-0257/
- Google TypeScript rehberi: https://google.github.io/styleguide/tsguide.html
- Google API alan adları (AIP-140): https://google.aip.dev/140
- React hook adları: https://react.dev/learn/reusing-logic-with-custom-hooks
- typescript-eslint naming-convention: https://typescript-eslint.io/rules/naming-convention/
- Ruff kuralları: https://docs.astral.sh/ruff/rules/
- Sass parça dosyaları: https://sass-lang.com/documentation/at-rules/use/#partials
- MDN özel sınıf alanları: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Classes/Private_elements
- RFC 3986, URL yapısı: https://www.rfc-editor.org/rfc/rfc3986
- RFC 9110, HTTP: https://www.rfc-editor.org/rfc/rfc9110
- RFC 8259, JSON: https://www.rfc-editor.org/rfc/rfc8259
- MariaDB ad kuralları: https://mariadb.com/kb/en/identifier-case-sensitivity/
- npm paket adları: https://docs.npmjs.com/package-name-guidelines/
- Conventional Commits: https://www.conventionalcommits.org/en/v1.0.0/
- Git dal adı denetimi: https://git-scm.com/docs/git-check-ref-format
- MCP araç adları: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- Unicode büyük ve küçük harf kuralları: https://www.unicode.org/Public/UCD/latest/ucd/SpecialCasing.txt

Kitaplar ve yazılar:

- Robert C. Martin, "Clean Code", 2008. 2. bölüm "Meaningful Names", 4. bölüm "Comments".
- Steve McConnell, "Code Complete", 2. baskı, 2004. 11. bölüm adlar, 32. bölüm kendini anlatan kod.
- Eric Evans, "Domain-Driven Design", 2003.
- Martin Fowler, "Ubiquitous Language": https://martinfowler.com/bliki/UbiquitousLanguage.html
- Donald E. Knuth, "Literate Programming", The Computer Journal, 1984.
- John Ousterhout, "A Philosophy of Software Design", 2018.
- Michael Nygard, "Documenting Architecture Decisions", 2011: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- Knuth'un okunur programlama sayfası: https://www-cs-faculty.stanford.edu/~knuth/lp.html
- Martin Fowler, "Bounded Context": https://martinfowler.com/bliki/BoundedContext.html
- qntm, "It's probably time to stop recommending Clean Code", 2020: https://qntm.org/clean
- Ousterhout ve Martin tartışması: https://github.com/johnousterhout/aposd-vs-clean-code
- Casey Muratori, "Clean Code, Horrible Performance", 2023: https://www.computerenhance.com/p/clean-code-horrible-performance
- Tom Preston-Werner, "Readme Driven Development", 2010: https://tom.preston-werner.com/2010/08/23/readme-driven-development.html
- AGENTS.md ortak biçimi: https://agents.md/
- Claude Code bellek dosyaları: https://code.claude.com/docs/en/memory

Frappe kaynak kodu:

- Frappe 16.56.0, `apps/frappe` klasörü. Satır numaraları ilgili kuralların yanındadır.
- Frappe belgeleri: https://docs.frappe.io/framework/user/en/

## 17. Denetim notu

- Frappe iddiaları Frappe 16.56.0 kaynak kodunda okundu.
- MariaDB karşılaştırması MariaDB 11.8.9 üzerinde denendi.
- Frappe 15 bilgileri Codex'in ve Claude'un okuduğu `version-15` dalına dayanır. Orkestratör bu dalı ayrıca okumadı.
- Araç kurallarının adları belgelerden alındı. Araçlar bu projede çalıştırılmadı.
- Codex ve Gemini son metni 3. turda onayladı.
- Kural dosyaları bu rapora göre güncellendi. Değişiklikler 13. bölümdedir.
- Gerçek okurla denenmedi.
