# Karar 0006: Erişim kuralı motoru

Bu not 22 Kasım 2026 Pazar günü yazıldı. Notu erisim-kurali işi yazdı. Karar verildi. Orkestratör kararı birleştirmede inceler. Karar, karar sitesinin K8 kararına dayanır. G-60, G-61, G-62, G-85, G-104 ve G-121 maddelerine de dayanır.

## 1. Kısa karar

Motoru `platform_core` içinde, `erisim` modülünde yazıyoruz. Yeni paket eklemiyoruz.

Yetki üç katmanda çözülür. Her katmanın tek görevi vardır.

| Katman | Görevi | Kimin kodu |
| --- | --- | --- |
| Rol izni (“DocPerm”) | İşlemi açar. Örneğin okuma ya da yazma izni verir. | Frappe |
| Erişim kuralı (“Access Rule”) | Kayıtları daraltır. Örneğin çalışan yalnız kendi kaydını görür. | Bu motor |
| İzin seviyesi (`permlevel`) | Alanı kapatır. Örneğin maaş alanı dönmez. | Frappe |

Motor izin veremez. Motor yalnız daraltır. Frappe'nin kancası da yalnız reddedebilir. Bu davranış 4. bölümde kaynakla gösterildi.

Bu notun en önemli kararı şudur: Kural tek bir SQL koşuluna çevrilir. Liste bu koşulu kullanır. Tek kayıt denetimi de aynı koşulu kullanır. Böylece liste ile tek kayıt farklı sonuç veremez.

## 2. Terimler

- Kanca, Frappe'nin uygulamaya bıraktığı bağlantı noktasıdır. Uygulama kancaya kendi işlevini bağlar.
- Kural, bir “Access Rule” kaydıdır.
- Kurallı kayıt türü, en az bir etkin kuralı olan DocType'tır.
- Özne, isteği yapan kullanıcıdır. Motor öznenin çalışan kaydını, bölümünü ve şirketini okur.
- Kapsam, kuralın özneye göre seçtiği kayıt kümesidir. Örneğin “team” kapsamı ekibin kayıtlarını seçer.

## 3. “Access Rule” kaydı hangi alanları taşır?

Kayıt türünün adı “Access Rule” olur. Modülü `Erisim` olur. Kaydı yalnız “System Manager” rolü yönetir.

| Alan | Tür | Zorunlu | Anlamı |
| --- | --- | --- | --- |
| `title` | Data | Evet | Kuralın kısa adı. Açıklama ucunda görünür. |
| `is_active` | Check | Hayır | Kural etkin mi? Varsayılan 1'dir. |
| `document_type` | Link, DocType | Evet | Kuralın daralttığı kayıt türü. |
| `role` | Link, Role | Evet | Kuralın uygulandığı rol. |
| `scope` | Select | Evet | Kapsam: `own`, `team`, `department`, `company` ya da `all`. |
| `match_field` | Data | Kapsam `all` değilse evet | Kaydı özneye bağlayan alanın adı. Örneğin `employee` ya da `owner`. |
| `filters` | Code, JSON | Hayır | Ek koşullar. Hepsi birden sağlanmalıdır. |
| `allow_read` | Check | Hayır | Kural okumayı kapsar. |
| `allow_write` | Check | Hayır | Kural değiştirmeyi kapsar. |
| `allow_create` | Check | Hayır | Kural yeni kaydı kapsar. |
| `allow_delete` | Check | Hayır | Kural silmeyi kapsar. |
| `allow_submit` | Check | Hayır | Kural onaya göndermeyi kapsar. |
| `allow_cancel` | Check | Hayır | Kural iptali kapsar. |
| `priority` | Int | Hayır | Açıklama ucundaki sıra. Sonucu değiştirmez. |
| `description` | Small Text | Hayır | Kuralın neden var olduğu. |

Her alan `description` taşır (D-9). Açıklamalar İngilizce yazılır.

### Karar sitesinden iki fark

- Karar sitesi bayrakları `read` ve `delete` gibi adlarla yazar. Bu notta adlar `allow_read` ve `allow_delete` olur. Nedeni şudur: `delete` Frappe'de kaydın bir yöntemidir. Aynı adlı alan yöntemle karışır.
- Karar sitesi `app` alanını da sayar. Bu alan kural şablonları içindir. Şablonlar sonraki turdadır. Alan o turda eklenir (A-5).

### Kapsam ve `match_field`

`match_field` alanının bağlandığı tür kapsamı belirler. Motor türü kayıt sırasında denetler. Uymayan kural kaydedilmez.

| Kapsam | `match_field` neyi gösterebilir | Seçilen kayıtlar |
| --- | --- | --- |
| `own` | Kullanıcı ya da çalışan | Öznenin kendi kayıtları |
| `team` | Kullanıcı ya da çalışan | Öznenin ve ona bağlı çalışanların kayıtları |
| `department` | Bölüm, çalışan ya da kullanıcı | Öznenin bölümündeki ve alt bölümlerindeki kayıtlar |
| `company` | Şirket, çalışan ya da kullanıcı | Öznenin şirketindeki kayıtlar |
| `all` | Boş kalır | Bütün kayıtlar |

- `owner` alanı kullanıcıyı gösterir.
- `name` alanı kaydın kendisini gösterir. Örneğin “Employee” türünde `name` çalışanı gösterir.
- Bağlantı alanı hedef türünü gösterir. Örneğin `employee` alanı “Employee” türünü gösterir.

### `filters` alanı

`filters` bir JSON listesidir. Her satır `[alan, işleç, değer]` biçimindedir. Örnek:

```json
[["status", "=", "Open"], ["company", "=", "$user.company"]]
```

- İzinli işleçler `=`, `!=`, `in` ve `not in` olur.
- Alan, kayıt türünün gerçek bir sütunu olmalıdır.
- Değer sabit olabilir. Değer şu dört değişkenden biri de olabilir: `$user`, `$user.employee`, `$user.department`, `$user.company`.
- Motor başka metni kod olarak çalıştırmaz (G-10). Değerler sorguya parametre olarak girer (G-5).

### Kurallar nasıl birleşir?

Birleşim kuralı G-60 maddesinden gelir.

1. Kayıt türünün etkin kuralı yoksa motor karışmaz. Rol izni geçerlidir.
2. Kayıt türü kurallıysa motor öznenin rollerine uyan kuralları bulur.
3. Motor yalnız istenen işlemi kapsayan kuralları alır. Örneğin yazma için `allow_write` açık olmalıdır.
4. Uyan kurallardan biri kaydı seçiyorsa motor izin verir. Kurallar “ya da” ile birleşir.
5. Hiçbir kural uymuyorsa erişim yoktur.
6. Ret kuralı yoktur.

“Administrator” kullanıcısı kuraldan muaftır. Frappe de bu kullanıcıyı denetlemez (`frappe/permissions.py:108`). Başka hiçbir rol muaf değildir. “System Manager” rolü de kurala uyar.

Bu yüzden bir uyarı gerekir. Bir kayıt türüne ilk kural yazılınca öteki roller erişimi kaybeder. Motor kural kaydedilirken bu rolleri bir uyarıyla sayar. Uyarı kaydı durdurmaz.

### İşlem adları kurala nasıl eşlenir?

Frappe kancaya işlem adını verir. Motor adı bir bayrağa eşler.

| Frappe'nin işlem adı | Kuralda aranan bayrak |
| --- | --- |
| `read`, `select`, `print`, `email`, `export`, `report`, `share` | `allow_read` |
| `write` | `allow_write` |
| `create`, `amend` | `allow_create` |
| `delete` | `allow_delete` |
| `submit` | `allow_submit` |
| `cancel` | `allow_cancel` |
| Tanınmayan ad | `allow_write` |

Tanınmayan ad için en dar seçim yapıldı. Rol izni yine ayrıca gerekir.

### Kural yazılamayan kayıt türleri

Motor şu türlere kural kabul etmez:

- alt tablo türleri,
- tek kayıtlı türler (“Single”),
- sanal türler,
- “Access Rule” türünün kendisi,
- izin sistemini tutan türler. Örneğin “DocType”, “Role”, “Custom DocPerm” ve “User Permission” böyledir.

Nedeni şudur: Yönetici bu türlere kural yazarsa kendi yönetim yolunu kapatabilir.

## 4. Frappe 16'nın kanca davranışı

İnceleme `frappe/erpnext:v16.55.0` imajında yapıldı. İmaj `colima-factory` bağlamındadır. İmajdaki Frappe sürümü 16.56.0'dır (`frappe/__init__.py:58`). Yollar `apps/frappe/frappe/` klasörüne göredir.

### Tek kayıt: `has_permission` kancası

| Bulgu | Kaynak |
| --- | --- |
| Kanca `"*"` anahtarıyla bütün kayıt türlerine bağlanır. | `permissions.py:491`, `permissions.py:492` |
| Kanca `doc`, `ptype`, `user` ve `debug` girdilerini alır. | `permissions.py:495` |
| Kanca `None` dönerse Frappe erişimi reddeder. Boş her değer rettir. | `permissions.py:497`, `permissions.py:498` |
| Kanca izin veremez. Kanca `True` dönse bile rol izni ayrıca aranır. | `permissions.py:484`, `permissions.py:243` |
| Kanca reddederse o işlemin izni 0 olur. | `permissions.py:239`, `permissions.py:241` |
| Kanca yalnız kayıt verilince çalışır. Kayıtsız tür denetiminde çalışmaz. | `permissions.py:138`, `permissions.py:163` |
| “Administrator” için kanca hiç çalışmaz. | `permissions.py:108` |
| Kayıt adla verilirse Frappe kaydı veritabanından yükler. | `permissions.py:141` |
| Kaydın `check_permission` yöntemi aynı işlevi çağırır. | `model/document.py:635`, `model/document.py:652` |
| Yeni kayıt `create` işlemiyle denetlenir. | `model/document.py:715` |
| Kayıt değişince `write` işlemi denetlenir. Denetim yeni değerlerle yapılır. | `model/document.py:822` |

Sonuç şudur: Kanca her zaman açıkça `True` ya da `False` dönmelidir. Kuralsız kayıt türünde kanca `True` döner.

### Liste: `permission_query_conditions` kancası

| Bulgu | Kaynak |
| --- | --- |
| `frappe.get_list` yeni sorgu sınıfını kullanır. | `__init__.py:1378` |
| `frappe.get_all` izni hiç uygulamaz. | `__init__.py:1400` |
| Kanca `"*"` anahtarıyla bütün türlere bağlanır. | `database/query.py:1706`, `database/query.py:1707` |
| Kanca kullanıcıyı ve `doctype` girdisini alır. | `database/query.py:1710` |
| Kanca SQL metni ya da sorgu terimi dönebilir. Boş değer koşul eklemez. | `database/query.py:1710`, `database/query.py:1713` |
| Kanca koşulu öteki koşullarla “ve” ile birleşir. | `database/query.py:1672`, `database/query.py:1678` |
| Rol izni yoksa kanca hiç çağrılmaz. | `database/query.py:1654`, `database/query.py:1661` |
| Tablo takma adla sorgulanırsa Frappe koşulu alt sorguya sarar. | `database/query.py:1731`, `database/query.py:1736` |
| Eski sorgu sınıfı da aynı kancayı okur. | `model/db_query.py:1175` |

Sonuç şudur: Motor koşulu kayıt türünün asıl tablo adına göre yazar. Kuralsız türde boş değer döner.

### Karar sitesindeki iki satır numarası

Karar sitesi `permissions.py:491` ve `db_query.py:1166` satırlarını gösterir. İlki doğrudur. İkincisi eski sorgu sınıfındadır. Güncel yol `database/query.py:1706` satırıdır. Fark raporda orkestratöre bildirildi.

## 5. Kural listeye nasıl girer?

`hooks.py` dosyasına tek satır eklenir:

```python
permission_query_conditions = {"*": "platform_core.erisim.hooks.query_conditions"}
```

İşlev şu adımları izler:

1. Kullanıcı “Administrator” ise boş değer döner.
2. Kayıt türü kurallı değilse boş değer döner.
3. Öznenin rollerine uyan ve `allow_read` taşıyan kuralları alır.
4. Kural yoksa her zaman yanlış olan bir koşul döner. Liste boş gelir.
5. Her kuralı bir koşula çevirir. Koşulları “ya da” ile birleştirir.

Bir örnek verelim. Çalışan rolünün `own` kuralı ve yönetici rolünün `team` kuralı var. Kullanıcı iki rolü de taşıyor. Koşul “kayıt benim ya da kayıt ekibimin” olur.

Motor koşulu Frappe'nin sorgu kurucusuyla yazar. Değerler sorguya kaçışlı girer. Kullanıcı metni sorgu metnine eklenmez (G-5).

## 6. Kural tek kayda nasıl girer?

`hooks.py` dosyasına tek satır eklenir:

```python
has_permission = {"*": "platform_core.erisim.hooks.has_permission"}
```

İşlev şu adımları izler:

1. Kayıt türü kurallı değilse `True` döner.
2. İşlem adını bayrağa eşler. Uyan kuralları alır. Kural yoksa `False` döner.
3. Kayıt veritabanında varsa saklı değerleri sınar.
4. İşlem `create`, `write` ya da `submit` ise yeni değerleri de sınar.
5. Bütün sınamalar geçerse `True` döner. Aksi halde `False` döner.

### Saklı değer neden ayrıca sınanır?

Frappe yazma iznini yeni değerlerle denetler (`model/document.py:822`). Yalnız yeni değerlere bakan kural şu saldırıyı kaçırır:

1. Çalışan başkasının kaydını açar.
2. Çalışan `employee` alanına kendi adını yazar.
3. Yeni değerler kurala uyar. Kayıt artık çalışanın olur.

Bu yüzden motor önce saklı kaydı sınar. Saklı kayıt kurala uymuyorsa işlem reddedilir. Kaydı kapsam dışına taşıyan değişiklik de reddedilir. Bu ikinci kural G-60 maddesindedir.

### Tek değerlendirici

Motor saklı kaydı tek sorguyla sınar. Sorgu şunu sorar: “Bu adda ve kurala uyan kayıt var mı?” Koşul, listenin kullandığı koşulla aynıdır.

Yeni değerler de veritabanında sınanır. Motor aynı koşulda sütun adlarının yerine yeni değerleri koyar.

Yeni değer istemciden gelir. Motor sayıyı metne çevirir. Nedeni şudur: MariaDB `0 = 'HR-EMP-1'` karşılaştırmasını doğru sayar. Liste ve sözlük değeri boş sayılır. Boş değer hiçbir koşulu sağlamaz.

Karar sitesi tek kayıt için Python yüklemi önerir. Bu not o yolu seçmedi. Nedeni şudur: MariaDB metni büyük küçük harf ayırmadan karşılaştırır. Python ayırır. Boş değer de iki yerde farklı davranır. İki ayrı değerlendirici zamanla farklı sonuç verir. Tek değerlendirici bu farkı baştan kapatır (G-121).

### Onay ve iptal

Frappe onaydan ve iptalden önce `write` iznini de arar (`model/document.py:822`, `:1403`, `:1417`). Bu yüzden onay için kuralda `allow_write` ve `allow_submit` birlikte açık olmalıdır. İptal için `allow_write` ve `allow_cancel` birlikte açık olmalıdır.

### Kayıt olmayan denetimler

Frappe bazı denetimleri kayıt vermeden yapar. Örneğin “bu türde kayıt açabilir miyim” sorusu böyledir. Kanca bu denetimde çalışmaz (`permissions.py:163`). Sonucu rol izni belirler. Kayıt gerçekten yazılırken kanca çalışır ve kuralı uygular.

## 7. Hiyerarşi nasıl çalışır?

### Kaynak

ERPNext'te “Employee” bir ağaç türüdür. Üst alanı `reports_to` alanıdır.

| Bulgu | Kaynak |
| --- | --- |
| “Employee” türünde `is_tree` açıktır. Üst alan `reports_to` olur. | `erpnext/setup/doctype/employee/employee.json` |
| Sınıf `NestedSet` sınıfından türer. | `erpnext/setup/doctype/employee/employee.py:25`, `:114` |
| “Department” de ağaçtır. Üst alanı `parent_department` olur. | `erpnext/setup/doctype/department/department.json` |
| Ağaç türleri `lft` ve `rgt` sayılarını taşır. Frappe bu sayıları kayıt değişince günceller. | `frappe/utils/nestedset.py:41` |

`lft` ve `rgt`, bir düğümün ağaçtaki aralığını gösteren iki sayıdır. Bir çalışanın aralığı yöneticisinin aralığının içindedir.

### Çözüm

Motor zinciri adım adım gezmez. Motor tek alt sorgu yazar:

```sql
`tabIzin`.`employee` in (
  select `name` from `tabEmployee` where `lft` >= 10 and `rgt` <= 25
)
```

Buradaki 10 ve 25 yöneticinin kendi aralığıdır.

- Yönetici kendi kaydını da görür. Aralık yöneticinin kendisini içerir.
- Yönetici dolaylı bağlı çalışanları da görür. Örneğin ekibindeki yöneticinin ekibini görür.
- Yönetici başka yöneticinin ekibini görmez. O ekip aralığın dışındadır.
- `reports_to` değişince Frappe aralıkları günceller. Sonuç sonraki istekte değişir.

`department` kapsamı aynı yolu “Department” ağacında izler. `company` kapsamı çalışanın şirketini kullanır.

### Özne nasıl bulunur?

Motor öznenin çalışan kaydını `user_id` alanından bulur. Motor şu değerleri tek sorguyla okur: ad, `lft`, `rgt`, bölüm ve şirket. Değerler yalnız o istek boyunca saklanır.

Öznenin çalışan kaydı yoksa çalışana bağlı kapsamlar hiçbir kaydı seçmez. Motor güvenli tarafta kalır.

### Sorgu sayısı (P-1)

- Listede kural yüzünden kayıt başına sorgu açılmaz. Koşul listenin kendi sorgusuna girer.
- Özne için istek başına en çok 2 sorgu açılır. Biri çalışan, biri bölüm içindir.
- Kural listesi için istek başına 1 sorgu açılır.
- Tek kayıt denetimi kayıt başına 1 sorgu açar. Yazmada 1 sorgu daha açılır.

### Ölçüm

Ölçüm 22 Kasım 2026 Pazar günü test sitesinde yapıldı. Sitede 60 kayıt ve 3 kural vardı. Kullanıcı yönetici rolündeydi.

| İşlem | Kuralsız | Kurallı | Fark nereden gelir |
| --- | --- | --- | --- |
| Liste | 2 sorgu | 4 sorgu | Özne için 1 sorgu. Frappe'nin paylaşım sorgusu için 1 sorgu. |
| Tek kayıt denetimi | 2 sorgu | 4 sorgu | Özne için 1 sorgu. Saklı kayıt sınaması için 1 sorgu. |
| 10 kayıt denetimi | 11 sorgu | 22 sorgu | Kayıt başına 1 sorgu. Özne için toplam 1 sorgu. |

Her sütundaki sorgulardan biri kural listesinin okunmasıdır. Motor bu okumayı istek başına bir kez yapar. Kuralsız kayıt türünde de yapar.

- Listenin sorgu sayısı kayıt sayısıyla artmaz. Test 40 kayıt ekler ve sayının aynı kaldığını görür.
- Paylaşım sorgusunu Frappe açar. Frappe bu sorguyu her koşullu listede açar (`database/query.py:1681`).
- Tek kayıt denetimi kayıt başına 1 sorgu ekler. Bu yüzden kendi kodumuzda kayıtları döngüde tek tek denetlemeyin. Listeyi `frappe.get_list` ile okuyun.

## 8. Alan düzeyi nasıl çalışır?

Motor alan düzeyi için yeni kod yazmaz. Frappe'nin izin seviyesi bu işi yapar (A-1).

İzin seviyesi alanın `permlevel` sayısıdır. Seviye 0 herkese açık alandır. Seviye 1 ve üstü ayrı rol izni ister.

Bir örnek verelim. Maaş alanının seviyesi 1 olur. Çalışan rolünün seviye 1 izni yoktur. İnsan kaynakları rolünün seviye 1 okuma izni vardır. Çalışan kaydı okur ama maaş alanı dönmez.

| Bulgu | Kaynak |
| --- | --- |
| Rolün eriştiği seviyeler rol izinlerinden toplanır. | `model/meta.py:745` |
| Tek kayıt okunurken izinsiz alan kayıttan silinir. | `model/document.py:1200`, `model/document.py:1216` |
| REST okuma ucu bu silmeyi çağırır. | `api/v2.py:66`, `api/v2.py:69` |
| REST güncelleme ucu yanıtta bu silmeyi çağırır. | `api/v2.py:204` |
| Listede izinsiz alan istenirse Frappe izin hatası verir. | `database/query.py:1020`, `database/query.py:1050` |
| Listede izinsiz alanla süzme de aynı denetimden geçer. | `database/query.py:1018` |
| Yazmada izinsiz alanın değeri eski değere döner. | `model/document.py:1288`, `model/document.py:1300` |
| Sorgu raporunda alan seviyesi uygulanmaz. Yalnız maskeli alanlar maskelenir. | `desk/query_report.py:980` |

Frappe izinsiz alanı yanıttan her zaman çıkarmaz. Bazı yanıtlarda alan adı kalır ama değeri boş gelir. Örneğin para alanı 0 döner. Gerçek değer hiçbir durumda dönmez. Testler bunu sınar.

### Motorun eklediği iki uç

Alan seviyesini yönetmek için iki ince uç yazılır. Uçlar Frappe'nin hazır işlevlerini çağırır.

- `set_field_level` bir alanın seviyesini değiştirir. Değişiklik “Property Setter” kaydıyla tutulur.
- `set_level_access` bir role bir seviye için okuma ve yazma izni verir. Değişiklik “Custom DocPerm” kaydıyla tutulur.

İki uç da yalnız “System Manager” rolüne açıktır. İki uç da izin sistemini tutan türleri reddeder. Örneğin “Access Rule” türünde alan kapatılamaz. İkinci uç seviye 0'a dokunmaz. Böylece yönetici temel erişimi bu uçla bozamaz.

## 9. Liste, kayıt, rapor ve dışa aktarma aynı sonucu nasıl verir?

Aynı sonuç iki şeye dayanır. Birincisi tek değerlendiricidir (6. bölüm). İkincisi her yüzeyin Frappe'de hangi yoldan geçtiğidir.

| Yüzey | Frappe yolu | Kural nasıl girer | Kaynak |
| --- | --- | --- | --- |
| REST listesi | `frappe.get_list` | Liste kancası | `__init__.py:1378` |
| REST tek kayıt | `check_permission("read")` | Kayıt kancası | `api/v2.py:68` |
| REST güncelleme | `check_permission("write")` ve `save` | Kayıt kancası, iki kez | `api/v2.py:200`, `api/v2.py:203` |
| Liste raporu (“Report Builder”) | Yeni sorgu sınıfı | Liste kancası | `desk/reportview.py:19` |
| Liste dışa aktarması | Yeni sorgu sınıfı ve dışa aktarma izni | Liste kancası | `desk/reportview.py:540`, `:546` |
| Bağlantı araması | `frappe.get_list` | Liste kancası | `desk/search.py:263` |
| Yazdırma ve PDF | Kayıtla izin denetimi | Kayıt kancası | `www/printview.py:544`, `:549` |
| Paylaşma | `share` izni kayıtla denetlenir | Kayıt kancası | `share.py:143` |
| Bağlantı araması, özel işlevle | Uygulamanın arama işlevi | Kurallı türde reddedilir | `desk/search.py:133` |
| Sorgu raporu | Raporun kendi SQL'i | Kanca çalışmaz. Rapor kapısı karar verir. | `desk/query_report.py:968` |
| Hazır rapor dosyası | Özel dosya indirme | Kurallı veride kapalıdır | `core/doctype/file/file.py:976` |
| Sistem kodu | `frappe.get_all`, ham SQL | **Kanca çalışmaz** | `__init__.py:1400` |

### Sorgu raporu açığı

İki rapor türü veriyi kendi yoluyla okur. Sorgu raporu (“Query Report”) kendi SQL'ini çalıştırır. Betik raporu (“Script Report”) kendi kodunu çalıştırır. Frappe sonucu yalnız “User Permission” kayıtlarına göre süzer (`desk/query_report.py:971`, `:1199`). Liste kancası bu yolda çağrılmaz. Frappe bu yolda alanı izin seviyesine göre de çıkarmaz. Bu yüzden kural bu raporlara kendiliğinden girmez.

Karar şudur: Motor bu raporlara bir kapı koyar. Kapı güvenli tarafta kalır. MVP'de kurallar bilerek basit ve kesindir. Orkestratör bu kuralları üçüncü incelemeden sonra koydu.

#### Kapı nerede durur?

Rapor verisine giden her yol “Report” kaydının iki yönteminde biter. Yöntemler `execute_query_report` ve `execute_script_report` olur (`desk/query_report.py:93`). Kapı bu iki yöntemin başındadır.

Motor “Report” kayıt türünü Frappe'nin `extend_doctype_class` kancasıyla genişletir (`model/document.py:218`). Frappe'nin kodu değişmez (M-4). Böylece şu yolların hepsi aynı kapıdan geçer:

- HTTP ucundan rapor çalıştırma ve dışa aktarma,
- arka planda dışa aktarma işi,
- raporu Python'dan çağıran kod.

Arka plan işi veriyi okurken kapıdan yeniden geçer. Yetki sıraya alma ile çalışma arasında düşerse iş reddedilir.

Başka modüller kapıyı `platform_core.erisim.api.report_guard` işleviyle de sorabilir. Yapay zekâ katmanı raporu çalıştırmadan önce bu işlevi çağırır. Bu erken bir cevaptır. Asıl denetim rapor çalışırken yine yapılır.

#### Kurallar

Aşağıdaki kurallar sitede en az bir kurallı kayıt türü varken geçerlidir.

| Rapor türü | Kural |
| --- | --- |
| Liste raporu (“Report Builder”) | Çalışır. Veriyi `frappe.get_list` okur. Liste kancası ve alan seviyesi uygulanır. |
| Sorgu raporu (“Query Report”) | Yalnız “System Manager” rolüne çalışır. |
| Betik raporu (“Script Report”) | Yalnız “System Manager” rolüne çalışır. |

Sitede hiç kurallı tür yoksa kapı tek şeye bakar. Öznenin raporun ana türündeki bütün izin seviyelerinde okuma izni olmalıdır.

#### Kimler muaftır?

| Kural | “System Manager” rolü | “Administrator” kullanıcısı |
| --- | --- | --- |
| Kayıt kuralı | Muaf değil | Muaf |
| Sorgu ve betik raporu | Muaf | Muaf |
| Hazır rapor kapatması | Muaf değil | Muaf değil |
| Zamanlanmış e-posta raporu kapatması | Muaf değil | Muaf değil |
| Özel bağlantı araması | Muaf değil | Muaf değil |

- “System Manager” rolü sorgu ve betik raporu kuralından bilerek muaftır. Sitede bu raporları çalıştırabilen biri gerekir. Bu rol kuralları zaten yönetir.
- “Administrator” kayıt kuralından muaftır. Frappe bu kullanıcı için izin kancasını hiç çağırmaz (`permissions.py:108`).
- Özel aramada muafiyet yoktur. Frappe özel arama işlevini “Administrator” için de çalıştırırdı. Beşinci inceleme bu erken dönüşü buldu ve dönüş kaldırıldı.

#### Sorgu ve betik raporu neden kapalı?

Sorgu raporu yöneticinin yazdığı SQL'i çalıştırır. Betik raporu uygulamanın kodunu çalıştırır. Motor ikisinin de neyi okuduğunu doğrulayamaz. Raporun ana kayıt türü bir şey kanıtlamaz.

Sonucu şudur: Sitede bir kural varsa bütün sorgu ve betik raporları kapanır. Yalnız “System Manager” rolü çalıştırabilir. Raporun ana türü kuralsız olsa da kapanır. Bu, standart ERPNext raporlarını da kapsar.

#### Bildirim ve kod denetimi denendi ve kaldırıldı

Bir ara betik raporu için başka bir yol vardı. Uygulama raporun okuduğu türleri `access_rule_report_scopes` kancasıyla bildiriyordu. Motor rapor kodunu durağan olarak okuyordu. Kod yalnız `frappe.get_list` kullanıyorsa rapor daraltılmış kullanıcıya da açılıyordu.

Dördüncü inceleme bu denetimin iki atlatma yolunu buldu:

1. Kod `import frappe as f` yazıp `f.get_all` çağırabiliyordu. Denetim takma adı izlemiyordu.
2. Kod `frappe.get_list(..., user="Administrator")` yazabiliyordu. Çağrı izinli görünüyordu ama başka kullanıcı adına okuyordu. Aynı girdi sırayla da verilebiliyordu.

Bu iki yol kapatılabilirdi. Ama sorun kökte duruyor: Kodu okuyarak güvenli saymak eksiksiz yapılamaz. Her kapatılan yolun yanında bulunmamış bir yol kalabilir. Yetki kodunda “büyük olasılıkla güvenli” yetmez.

Bu yüzden orkestratör MVP kuralını sadeleştirdi. Bildirim kancası ve kod denetimi kaldırıldı. Hiçbir uygulama bu kancayı kullanmıyordu. Kancayı yazmanın artık etkisi yoktur. Aynı karar bağlantı aramasındaki izin listesini de kaldırdı.

Eski atlatma yolları artık ret testleridir. Takma adlı kod, kullanıcı girdili kod ve sıralı girdili kod kısıtlı kullanıcıda çalışmaz. Test raporun kodunun hiç çalışmadığını da sınar.

Bedeli şudur: Daraltılmış kullanıcı için tek rapor yolu liste raporudur. Uygulamaya özel bir rapor gerekebilir. O rapor liste raporu ya da ayrı bir uç olarak yazılmalıdır. Uç veriyi `frappe.get_list` ile okur.

#### Hazır rapor kapalıdır

Hazır rapor (“Prepared Report”) sonucu dosyada saklar. Saklı sonuç başka bir zamanda, başka bir kullanıcı için alınmış veri kopyasıdır. Motor o kopyayı sonradan daraltamaz.

Bu yüzden karar özelliği kapatmaktır. Kurallı veriye dokunan raporda hazır rapor herkes için kapalıdır. “Administrator” için de kapalıdır.

| Yol | Sonuç | Nasıl kapanır |
| --- | --- | --- |
| Hazır rapor oluşturma | Reddedilir | “Prepared Report” kaydı genişletildi |
| Saklı sonucu indirme | Reddedilir | Kayıt okuma izni ve içerik okuma kapalı |
| Rapor ucundan saklı sonucu okuma | Reddedilir | İçerik okuma kapalı (`desk/query_report.py:425`) |
| Dosyayı doğrudan indirme | Reddedilir | “File” kaydı genişletildi |
| Dosyayı ZIP içinde indirme | Reddedilir | Dosya içeriği okuma kapalı (`core/api/file.py:138`) |
| CSV'ye dönüştürme | Reddedilir | Kayıt okuma izni ve içerik okuma kapalı |

Var olan saklı sonuçlar ve dosyaları silinmez. Yalnız okunamaz. Dosyanın sahibi ve dosyanın paylaşıldığı kişi de okuyamaz. Frappe bu ikisine bağlı kayda bakmadan izin verir (`core/doctype/file/file.py:1097`). Motorun denetimi bu karardan önce çalışır.

Sırada bekleyen hazır rapor da kapalıdır. Bir kayıt kural yazılmadan önce sıraya alınmış olabilir. Arka plan işi kayıt oluşturma denetiminden geçmez (`core/doctype/prepared_report/prepared_report.py:107`).

Motor bu yüzden iş başında denetler. Frappe işçisi her işten önce `before_job` kancasını çağırır (`utils/background_jobs.py:269`). Motor bu kancaya bağlanır. İş hazır rapor işiyse ve rapor kurallı veriye dokunuyorsa motor işi reddeder. Frappe'nin iş işlevi hiç başlamaz. Kayıt “Error” durumuna geçer ve dosya yazılmaz.

Denetim bütün rapor türleri içindir. Liste raporu “Report” kaydındaki kapıya hiç uğramaz (`desk/query_report.py:93`). Yedinci inceleme bu açığı buldu. İş başı denetimi rapor türüne bakmaz.

İki ek güvence vardır. Rapor kapısı işin adına yine bakar. Kapalı hazır rapora dosya da eklenemez.

Bir rapor ne zaman kurallı veriye dokunur?

- Liste raporu, ana türü kurallıysa dokunur.
- Sorgu raporu ve betik raporu, sitede kurallı tür varsa dokunuyor sayılır.

#### Zamanlanmış e-posta raporu kapalıdır

“Auto Email Report” raporu sonradan çalıştırır ve sonucu e-postayla gönderir. Kullanıcı o sırada başında değildir.

Karar şudur: Kurallı veriye dokunan “Auto Email Report” hiç kimse için çalışmaz. “System Manager” rolü ve “Administrator” kullanıcısı da buna dahildir.

| İş | Sonuç |
| --- | --- |
| Böyle bir kayıt oluşturma | Reddedilir |
| Var olan kaydı etkin yapma | Reddedilir |
| Raporu indirme | Reddedilir |
| Raporu elle gönderme | Reddedilir |
| Zamanlayıcının raporu göndermesi | Reddedilir |
| Var olan kaydı kapalı tutarak kaydetme | Yapılır |
| Var olan kaydı silme | Yapılır |

Son iki satırın nedeni şudur: Kural bir kaydı etkin durumda kilitlememelidir. Yönetici kaydı kapatabilmeli ve silebilmelidir.

Motor kurulumdan ve her migrate işleminden sonra bir temizlik yapar. Kurallı veriye dokunan bütün etkin kayıtları kapatır (`enabled = 0`). Kayıt silinmez.

Kuralsız veriye dokunan kayıt Frappe'nin olağan davranışıyla çalışır.

##### Gerekçe

İki neden vardır:

1. Proje zamanlanmış iş kurmaz (D-6). Bu özellik zamanlanmış bir iştir.
2. İlk sürümün e-posta raporuna ihtiyacı yoktur.

Daha ince kurallar denendi ve her biri yeni bir açık verdi:

| Denenen kural | İncelemenin bulduğu açık |
| --- | --- |
| Rapor kuralları kayıttaki kullanıcıya uygulansın. | Rapor indiren kişinin oturumuyla çalışıyordu. |
| Rapor kayıttaki kullanıcının oturumuyla çalışsın. | Oturum değiştirmek oturum verisini siliyordu. “Report Manager” daha yetkili bir hesabı seçebiliyordu. |
| Kaydı yalnız “System Manager” kullansın. | Zamanlayıcı “Administrator” oturumuyla çalışıyor ve her rol denetimini geçiyordu. |
| “System Manager” kaydı onaylasın. Motor ayarların izini tutsun. | Rapor tanımı değişince eski onay geçerli kalıyordu. İz alan sınırlarını güvenli saklamıyordu. |

Her tur bir açığı kapattı ve bir yenisini gösterdi. Orkestratör bu yüzden özelliği kurallı veride tümüyle kapattı. Onay kaydı, onay izi ve onay kodu kaldırıldı.

##### Zamanlayıcı hangi oturumla çalışır?

Frappe zamanlayıcısı işi “Administrator” oturumuyla çalıştırır (`utils/scheduler.py:117`). Bu oturum rol denetimlerini geçer. Motorun reddi role bakmaz. Bu yüzden zamanlayıcı da reddedilir.

Motor oturumdaki kullanıcıyı hiçbir yerde değiştirmez. Frappe'nin `set_user` işlevi oturum verisini ve istek girdilerini siler (`frappe/__init__.py:381`).

Kuralsız veride Frappe'nin kendi davranışı geçerlidir. Frappe liste raporunu kayıttaki kullanıcı adına okur. Sorgu ve betik raporunu ise oturumdaki kullanıcı adına çalıştırır. Zamanlanmış çalışmada bu kullanıcı “Administrator” olur. Elle indirmede işlemi yapan kullanıcı olur.

#### Sınıf genişletme ve `super()`

Motor dört kayıt türünü genişletir: “Report”, “Prepared Report”, “Auto Email Report” ve “File”. Frappe genişletme sınıflarını asıl sınıfın önüne koyar (`model/document.py:207`). Başka uygulama da aynı türü genişletebilir.

Bu yüzden motorun her yöntemi denetimden sonra `super()` çağırır. Böylece sıradaki sınıfın yöntemi de çalışır. Bu yol yalnız Frappe 16'da vardır (D-15).

### Bağlantı araması

Bağlantı araması olağan yolda `frappe.get_list` kullanır. Liste kancası çalışır.

Bir bağlantı alanı ya da uygulama kendi arama işlevini verebilir. Frappe o işlevin sonucunu olduğu gibi döner (`desk/search.py:133`). Uygulama türün aramasını `standard_queries` kancasıyla da değiştirebilir (`desk/search.py:125`). Böyle bir işlev kuralı ve alan seviyesini atlayabilir. İşlev kayıtları gizli bir alana göre de seçebilir. Sonucu sonradan süzmek bunu düzeltmez.

Bu yüzden kural şudur. Kurallı kayıt türünde yalnız Frappe'nin standart araması çalışır.

Bütün özel arama işlevleri kurallı türde reddedilir. Ret bütün kullanıcılar içindir. “Administrator” için de geçerlidir. Kullanıcının bütün kayıtları görmesi sonucu değiştirmez. Kuralsız türde özel arama Frappe'nin olağan davranışıyla çalışır.

İzin listesi yoktur. Bir ara `access_rule_allowed_queries` kancası vardı. Listedeki işlevin kodu durağan olarak denetleniyordu. Bu denetim rapor kodundaki denetimle aynıydı ve aynı nedenle kaldırıldı.

Sonucu şudur: Bir kayıt türüne kural yazılınca o türün ERPNext'teki özel araması kapanır. Arama alanı standart aramaya dönmelidir.

Motor Frappe'nin iki arama ucunu `override_whitelisted_methods` kancasıyla sarar (`__init__.py:1577`). İki sarmalayıcı aramadan önce `select` iznini arar. Güvenlik kapısı her uçta açık izin denetimi ister. Bunun bir yan etkisi vardır. “DocType” türünde okuma izni olmayan kullanıcı kayıt türü adı arayamaz.

#### Python'dan çağrı

Kural HTTP ucunda kendiliğinden çalışır. Python kodu Frappe'nin arama işlevini doğrudan çağırırsa sarmalayıcıdan geçmez. Motor bunu Frappe'yi değiştirmeden engelleyemez (M-4).

Bu yüzden iki önlem vardır:

- Python kodu aramayı `platform_core.erisim.api.search_link` ile yapar. Bu işlev aynı kurala uyar. Yalnız denetim isteyen kod `link_search_guard` işlevini çağırır.
- Bir test `platform_core` paketini tarar. Frappe'nin arama işlevini doğrudan çağıran dosya bulursa test başarısız olur.

Bu tarama yalnız `platform_core` paketini kapsar. Başka uygulamaların kodu taranmaz.

### Kapsanmayan yüzeyler

Şu yüzeyler bu turda sınanmaz. Hepsi durum dosyasında `not_run` olarak yazılır.

- Dosya ve ekler,
- arka plan işleri,
- anlık bildirimler (“realtime”),
- genel arama.

## 10. Paylaşılmış kayıt kuralı nasıl etkiler?

Frappe'de paylaşım kancadan sonra gelir. Paylaşılan kayıt kuralı aşar.

| Bulgu | Kaynak |
| --- | --- |
| Tek kayıtta izin yoksa Frappe paylaşıma bakar. Kanca reddi de bu yola düşer. | `permissions.py:209`, `permissions.py:211` |
| Listede paylaşılan kayıtlar öteki koşullara “ya da” ile eklenir. | `database/query.py:1681`, `database/query.py:1684` |
| Frappe bu davranışı açıkça yazar: Paylaşılan kayıt bütün kısıtları aşar. | `database/query.py:1604` |
| Paylaşmak için kayıtta `share` izni gerekir. Bu denetim kayıtla yapılır. | `share.py:143` |
| Paylaşılabilen işlemler `read`, `write`, `share`, `submit`, `email` ve `print` olur. | `permissions.py:180` |

Karar şudur: Motor paylaşımı engellemez. Paylaşım bilinçli bir izin vermedir. Motor şunları sağlar:

1. Liste ve tek kayıt aynı sonucu verir. Paylaşılan kayıt ikisinde de görünür.
2. Kuralın dışındaki kullanıcı kaydı paylaşamaz. `share` işlemi kayıt kancasından geçer ve `allow_read` kuralını arar.
3. Açıklama ucu paylaşımı ayrı bir neden olarak gösterir.
4. Testler paylaşılmış kayıtla da çalışır (G-12).

Silme ve iptal paylaşılamaz. Paylaşılan kayıtta bu işlemler kurala takılır.

Sahipliğin zorunlu olduğu bir kayıt türü olabilir. Bu durumda uygulama sahipliği kendi ucunda ayrıca doğrular (G-12). Site yöneticisi paylaşımı “System Settings” içinden tümüyle de kapatabilir (`permissions.py:112`).

Karar sitesi paylaşım ilişkilerini G-122 maddesine bırakır. O madde P5 fazındadır. Bu not o maddeyi kapsamaz.

### ERPNext'in çalışan izni

ERPNext çalışana kullanıcı bağlanınca bir “User Permission” kaydı açabilir. Bunu “Employee” türündeki `create_user_permission` alanı belirler (`erpnext/setup/doctype/employee/employee.py:232`). Bu kayıt da kayıtları daraltır. Kullanıcı yalnız kendi çalışan kaydına bağlı kayıtları görür.

Bu katman motordan bağımsızdır. İki katman birlikte uygulanır. Bir kayıt ikisinden de geçmelidir.

Bunun bir sonucu vardır. Yöneticiye `all` kuralı yazılsa bile “User Permission” kaydı yöneticiyi daraltır. Kiracı yöneticisi iki katmandan birini seçmelidir. Bu motoru kullanan uygulama çalışanı `create_user_permission` kapalı açmalıdır. Testler de çalışanları böyle açar.

Açıklama ucu bu durumu `user_permission` nedeniyle gösterir.

## 11. Yapay zekâ katmanı aynı sonucu nasıl alır?

Yapay zekâ katmanı ayrı bir yetki yolu kurmaz. Katman kullanıcının kimliğiyle Frappe'nin aynı işlevlerini çağırır. Kancalar o işlevlerin içindedir.

`platform-core-yz` dalındaki kod okundu:

| Araç | Çağırdığı yol | Sonuç |
| --- | --- | --- |
| `list_documents` | `frappe.get_list` | Liste kancası çalışır. |
| `get_document` | `check_permission("read")` ve alan silme | Kayıt kancası ve izin seviyesi çalışır. |
| Yazma araçları | Onaydan sonra kaydın `save` yolu | Kayıt kancası çalışır. |
| `run_report` | `frappe.desk.query_report.run`, Python'dan | Rapor kapısı çalışır. Kapı “Report” kaydının içindedir. Katman önce `erisim.api.report_guard` işlevini de çağırır. |

- `erisim` modülü `yapay_zeka` modülünü içe aktarmaz. `yapay_zeka` da `erisim` modülünü içe aktarmaz. İki modül yalnız Frappe'nin kancalarında buluşur.
- Yapay zekâ kuralları genel kayıt araçlarıyla yönetir. “Access Rule” olağan bir kayıt türüdür. Yazma yine öneri ve insan onayı ister.
- Yapay zekâ alan seviyesini `yapay_zeka` modülünün yönetim araçlarıyla değiştirir. O dalda `set_field_property` ve `set_role_permission` araçları vardır.
### Motorun kendi araçları

Motor dört aracı `ai_tools` kancasıyla bildirir (D-9). Kod `erisim/ai_tools.py` dosyasındadır. Bildirim biçimi yapay zekâ sözleşmesinin `x-ai-tools-hook` bölümünden alındı.

| Araç | Türü | İşi |
| --- | --- | --- |
| `list_access_rules` | Okuma | Kuralları listeler. Yalnız “System Manager” görür. |
| `explain_access` | Okuma | Bir kullanıcının bir kayda neden eriştiğini ya da erişemediğini açıklar. |
| `propose_access_rule` | Yazma | Yeni kural önerir. |
| `propose_access_rule_change` | Yazma | Kayıtlı kuralda değişiklik önerir. Kuralı kapatmak da buradadır. |

- Yazan iki araç önizleme döner. Kaydı ancak insan onayından sonra katman yazar.
- Yazan iki araç `destructive` bayrağını taşır. Kural eklemek ve daraltmak erişimi kaldırabilir.
- Önizleme erişimi kaybedecek rolleri sayar.
- Değişiklik aracı `versioned` bayrağını taşır. Sürüm kaydın `modified` değeridir.
- Yeni kural önerisinin sürümü o kayıt türünün bütün kurallarının özetidir. Araya başka kural girerse onay reddedilir.
- Araçlar yalnız yapılandırılmış alan alır. SQL metni ya da ham koşul alan girdi yoktur. Girdi modeli bilinmeyen alanı reddeder.
- Süzgeç satırları elle yazılan kuralla aynı doğrulamadan geçer.
- Her araç iznini kendisi denetler. Araç `ignore_permissions` kullanmaz.
- “Access Rule” türü genel yazma araçlarına kapalıdır (O-28). Motor türü `ai_write_closed_doctypes` kancasına yazar. Kural yalnız yukarıdaki iki yazma aracıyla değişir. O araçlar kuralı doğrular ve erişimi kaybedecek rolleri sayar.

Yapay zekâ katmanı henüz `backend` dalında değildir. Testler araçları sözleşmenin anlattığı gibi çağırır: kullanıcı kimliğiyle ve doğrulanmış girdiyle. Araçlar gerçek MCP ucundan sınanmadı.

## 12. Önbellek

Kanca her izin denetiminde çalışır. Motor kural listesini istek başına bir kez okur. Liste yalnız o istek boyunca saklanır.

İstekler arasında ortak önbellek yoktur. İlk tasarımda vardı. İkinci bağımsız inceleme şu yarışı gösterdi ve bir test onu doğruladı:

1. Birinci istek eski, geniş kuralı okur.
2. Yönetici ikinci istekte kuralı daraltır. Değişiklik kesinleşir ve önbellek silinir.
3. Birinci istek eski kuralı ortak önbelleğe geri yazar.
4. Sonraki istekler kaldırılmış yetkiyle çalışır.

Ortak önbellek kaldırılınca bu yol kapandı. Bedeli istek başına 1 sorgudur. Ölçüm 7. bölümdedir.

- Kural değişince sonuç sonraki istekte değişir. Bu davranış testle sınanır.
- Kuralı değiştiren istek kendi sakladığı listeyi de siler.
- Özne değerleri de yalnız istek boyunca saklanır. Böylece `reports_to` değişikliği sonraki istekte etki eder.
- Süren bir istek kendi veritabanı görüntüsünü kullanır. O istek bitene kadar eski kuralı görebilir. Bu, veritabanı işlemlerinin olağan davranışıdır.

### Kural değişen istekte liste saklanmaz

Bir istek kuralı değiştirirse motor o isteğin kalanında kural listesini saklamaz. Her denetim listeyi veritabanından okur.

Nedeni kısmi geri almadır. Kod bir geri dönüş noktası açabilir ve yalnız oraya dönebilir. Frappe bu durumda geri alma olayını çalıştırmaz (`database/database.py:1212`). Motor geri almayı öğrenemez. Saklanan liste geri alınmış geniş kuralı taşımaya devam ederdi.

Dördüncü inceleme bu açığı buldu. İki test onu sınar. Biri kısmi geri almayı, öteki tam geri almayı sınar. İkisinde de dar kural geri gelir.

Bedeli şudur: Kural değiştiren istek her izin denetiminde 1 sorgu daha açar. Kural değiştirmeyen istek etkilenmez.

## 13. Uçlar

Sözleşme `contracts/platform_core-erisim.openapi.yaml` dosyasındadır. Uç dosyası `api/access.py` olur. İş kuralı `erisim` klasöründe durur.

| Yol | Yöntem | Kimlik | İşi |
| --- | --- | --- | --- |
| `platform_core.api.access.explain_permission` | GET | Oturum | Bir kayıtta iznin nedenini açıklar. |
| `platform_core.api.access.get_access_summary` | GET | Oturum | Öznenin bir kayıt türündeki kapsamlarını döner. |
| `platform_core.api.access.set_field_level` | POST | “System Manager” | Alanın izin seviyesini değiştirir. |
| `platform_core.api.access.set_level_access` | POST | “System Manager” | Role bir seviye için okuma ve yazma izni verir. |

Kural ekleme, değiştirme ve silme için ayrı uç yazılmadı. Frappe'nin hazır REST ucu yeter: `/api/v2/document/Access Rule`. Bu uç rol iznini ve kayıt doğrulamasını zaten uygular (A-1).

### Açıklama ucu bilgi sızdırmaz

Açıklama ucu kayıt varlığını ele verebilir. Bu yüzden yanıt çağırana göre değişir.

- Çağıranın kayıt türünde okuma izni olmalıdır. İzin yoksa uç 403 döner. Kayıt türü yoksa da 403 döner.
- Olağan kullanıcı yalnız kendi iznini sorabilir. Ret nedeni tek değerdir: `not_permitted_or_missing`. Kayıt yoksa da aynı değer döner. Rolün izni yoksa da aynı değer döner.
- “System Manager” başka kullanıcıyı da sorabilir. Yanıt kuralları tek tek sayar.

## 14. Testler

Testler `erisim/tests/` klasöründedir. Testler isteği Frappe'nin WSGI uygulamasından geçirir (D-6). Bu yol `yapay_zeka` testlerinin yoluyla aynıdır (A-2).

Beklenen sonuçlar bu nottan, sözleşmeden ve karar sitesinden gelir (D-1).

| Dosya | Sınadığı davranış | Kaynak |
| --- | --- | --- |
| `test_kayit_kurali.py` | Çalışan yalnız kendi kaydını görür. Ret durumu da sınanır. | G-60, yol haritası P1 satır 4 |
| `test_hiyerarsi.py` | Yönetici ekibini görür. Başka ekibi görmez. | G-60, G-104 |
| `test_alan_duzeyi.py` | Kısıtlı alan dönmez ve yazılamaz. | G-61 |
| `test_yuzeyler.py` | Liste, kayıt, liste raporu ve dışa aktarma aynı kümeyi verir. | G-121 |
| `test_paylasim.py` | Paylaşılan kayıt iki yüzeyde de görünür. | G-12 |
| `test_kural_degisimi.py` | Kural değişince sonuç sonraki istekte değişir. | Görev belgesi |
| `test_uclar.py` | Dört ucun izni, girdisi ve çıktısı. | Sözleşme |
| `test_sorgu_sayisi.py` | Liste sorgu sayısı kayıt sayısıyla artmaz. | P-1 |
| `test_inceleme.py` | Bağımsız incelemenin bulguları, bölüm ve şirket kapsamları, işleçler. | R-9 |
| `test_second_review.py` | İkinci incelemenin üç bulgusu. | R-9 |
| `test_ai_tools.py` | Dört yapay zekâ aracının bildirimi, izni, önizlemesi ve sürümü. | D-9, yapay zekâ sözleşmesi |
| `test_report_rules.py` | Rapor kuralları: hazır rapor, sorgu raporu, betik raporu, zamanlanmış e-posta raporu. | R-9, kararlar A, B, C, E |
| `test_rule_cache.py` | Kural değişen istekte kısmi ve tam geri alma. | R-9 |
| `test_auto_email_report.py` | Zamanlanmış e-posta raporu: herkese kapalı olması, zamanlayıcı ve migrate temizliği. | R-9, D-6 |

Güvenlik kapısı uç testlerini modülün yanında ister. Bu yüzden iki dosya daha vardır:

- `api/test_access.py` dört ucun misafir ve yabancı veri reddini sınar.
- `erisim/test_reports.py` sorgu raporu kapısını sınar.
- `erisim/test_link_search.py` bağlantı araması süzgecini sınar.

Testler önce kancalar kapalıyken çalıştırıldı. 83 testten 80'i beklenen nedenle başarısız oldu (D-2). Örneğin çalışan bütün kayıtları gördü ve başkasının kaydı 200 döndü. Kancalar açılınca testler geçti.

## 15. Bağımsız inceleme

Motor yetki kodudur. Bu yüzden kod bağımsız bir incelemeden geçti (R-9). İnceleyen yalnız okudu. Her bulgu için önce test yazıldı.

| Bulgu | Sonuç |
| --- | --- |
| İstemci kaydın adını değiştirerek başkasının kaydına ulaşabilir. | Doğrulanmadı. Üç test bu yolu gerçek istekle sınar ve yol kapalıdır. Testler kalıcıdır. |
| Hazır rapor yolu kapıyı atlar. | Doğrulandı ve kapatıldı. |
| Eski kural önbellekte süresiz kalabilir. | Önce 60 saniye süre verildi. İkinci inceleme bunu yetersiz buldu. Ortak önbellek kaldırıldı. |
| Sayı değeri kuralı geçer. Liste değeri sunucu hatası verir. | Doğrulandı ve kapatıldı. |
| Sonsuz sayı süzgeç değeri olarak kabul edilir. | Doğrulandı ve kapatıldı. |
| Açıklama ucu olağan kullanıcıya iki ret nedeni döner. | Kapatıldı. Tek neden döner. |
| Alan düzeyi uçları korumalı türleri ayırmaz. | Doğrulandı ve kapatıldı. |
| Çalışan kendi bölüm ya da şirket alanını değiştirip kapsamını genişletebilir. | Aşağıdaki koşul yazıldı. |

### İkinci inceleme

Orkestratör ikinci bir bağımsız inceleme yaptırdı. İnceleme üç engelleyici bulgu verdi. Üçü de testle doğrulandı ve kapatıldı. Testler `tests/test_second_review.py` dosyasındadır.

| Bulgu | Düzeltme |
| --- | --- |
| Hazır raporun indirme yolu kuralı aşıyor. | Kapı “Prepared Report” kaydı okunurken de çalışıyor. |
| `all` kuralı gizli alanı raporda açıyor. | Kapı alan seviyesini de denetliyor. |
| Eşzamanlı istek kaldırılmış yetkiyi önbelleğe geri koyuyor. | Ortak önbellek kaldırıldı. |

İnceleme dört uçta istek sayısı sınırı olmadığını da yazdı. Uçlar oturum ister ve misafire kapalıdır. Sınır bu turda eklenmedi.

### Üçüncü inceleme

İkinci incelemenin düzeltmeleri yeniden incelendi. Orkestratör altı karar verdi. Bu turda kapı “Report” kaydının içine taşındı. Varsayılan test komutu ERPNext'i de kurar oldu. Bu iki değişiklik kalıcıdır.

Öteki dört kararın ilk çözümü bildirime ve sonuç süzmeye dayanıyordu. Dördüncü inceleme bunları yetersiz buldu. Yerlerine aşağıdaki kesin kurallar geldi.

### Dördüncü inceleme ve kesin kurallar

Üçüncü incelemenin düzeltmeleri de yeniden incelendi. İnceleme bildirime dayanan kapıyı yetersiz buldu. Bildirim raporun gerçekte ne okuduğunu sınırlamıyordu. Orkestratör MVP için daha basit ve kesin kurallar koydu. Kurallar 9. bölümdedir.

| Karar | Kural | Test |
| --- | --- | --- |
| A | Kurallı veriye dokunan hazır rapor tümüyle kapalıdır. | `tests/test_report_rules.py` |
| B | Sorgu raporu yalnız “System Manager” rolüne çalışır. | `tests/test_report_rules.py` |
| C | Betik raporu yalnız bildirim ve kod denetimiyle çalışır. Bu kural sonra sadeleşti: betik raporu yalnız “System Manager” rolüne çalışır. | `tests/test_report_rules.py` |
| D | Kurallı türde yalnız standart arama ve izin listesindeki arama çalışır. Bu kural sonra sadeleşti: yalnız standart arama çalışır. | `test_link_search.py` |
| E | Zamanlanmış e-posta raporu A, B ve C kurallarına uyar. | `tests/test_report_rules.py` |

Aynı turda bir açık daha kapatıldı. Arama testlerinin iki yardımcı işlevi uç olarak açıktı. İşlevler test dosyasındaydı ama test dosyası da pakete girer. Giriş yapmış kullanıcı işlevi çağırıp kayıt kurallarını atlayabilirdi. İşlevlerden uç süslemesi kaldırıldı. Testler işlevi yalnız test sürerken Frappe'ye kaydeder. Bir test pakette uç bildiren test dosyası arar. Bulursa başarısız olur.

### Beşinci inceleme ve sadeleşen kural

Dördüncü incelemenin düzeltmeleri de incelendi. İnceleme üç engelleyici ve bir önemli bulgu verdi.

| Bulgu | Düzeltme | Test |
| --- | --- | --- |
| E-posta raporu kayıttaki kullanıcının kimliğiyle çalışmıyor. | Motor oturumu kayıttaki kullanıcıya çeviriyordu. Bu çözüm sonraki incelemede kaldırıldı. | `tests/test_report_rules.py` |
| Takma ad kullanan kod kod denetimini atlıyor. | Kod denetimi ve bildirim kaldırıldı. Betik raporu yalnız “System Manager” rolüne çalışıyor. | `tests/test_report_rules.py` |
| `user` girdisi alan sorgu başka kullanıcı adına okuyor. | Aynı düzeltme. Arama izin listesi de kaldırıldı. | `tests/test_report_rules.py`, `test_link_search.py` |
| Kısmi geri alma istek içindeki kural listesini temizlemiyor. | Kural değişen istekte liste saklanmıyor. | `tests/test_rule_cache.py` |

İkinci ve üçüncü bulgunun kökü aynıdır. Gerekçe 9. bölümdedir.

### Altıncı inceleme

Beşinci incelemenin düzeltmeleri de incelendi. İnceleme bir engelleyici ve üç önemli bulgu verdi.

| Bulgu | Düzeltme | Test |
| --- | --- | --- |
| E-posta raporunda yetki seçilen hesaba göre açılıyor. | Kurallı veride kaydı yalnız “System Manager” kullanabilir. | `tests/test_report_rules.py` |
| E-posta raporu oturum bilgilerini siliyor. | Kullanıcı değiştirme kodu tümüyle kaldırıldı. | `tests/test_report_rules.py` |
| Özel arama yasağı “Administrator” için uygulanmıyor. | Erken dönüş kaldırıldı. Muafiyetler bu notta ve sözleşmede tablo olarak yazıldı. | `test_link_search.py` |
| Önceden sıraya alınan hazır rapor çalışabiliyor. | Kapı arka plan işinin adına bakıyor ve işi reddediyor. | `tests/test_report_rules.py` |

### Yedinci inceleme

Altıncı incelemenin düzeltmeleri de incelendi. İnceleme bir engelleyici, bir önemli ve bir küçük bulgu verdi.

| Bulgu | Düzeltme | Test |
| --- | --- | --- |
| Zamanlayıcı eski kayda yönetici yetkisi veriyor. | Kayıt yalnız onaylıyken çalışıyordu. Bu çözüm sonraki incelemede kaldırıldı. | `tests/test_auto_email_report.py` |
| Kaydetme denetimi eski rapor türüne bakmıyor. | Denetim kaydın önceki raporuna da bakıyor. | `tests/test_auto_email_report.py` |
| Belge, betiğin hangi oturumla çalıştığını belirsiz bırakıyor. | Oturum ile kayıttaki kullanıcı farkı bu nota ve sözleşmeye yazıldı. | Belge değişikliği |

### Sekizinci inceleme

Yedinci incelemenin düzeltmeleri de incelendi. İnceleme bir engelleyici, iki önemli ve bir küçük bulgu verdi.

| Bulgu | Düzeltme | Test |
| --- | --- | --- |
| Raporun tanımı değişince eski onay geçerli kalabiliyor. | Onay düzeni kaldırıldı. Kurallı veride e-posta raporu herkese kapalı. | `tests/test_auto_email_report.py` |
| Ayar özeti alan sınırlarını güvenli saklamıyor. | Özet kodu onay düzeniyle birlikte kaldırıldı. | `tests/test_auto_email_report.py` |
| Sıradaki liste raporu çalışma başında durmuyor. | Motor `before_job` kancasıyla iş başında reddediyor. | `tests/test_report_rules.py` |
| Oturum tablosunda zamanlayıcı hesabı eksik. | Zamanlayıcının oturumu bu nota ve sözleşmeye yazıldı. | Belge değişikliği |

### Özne alanlarını koruyun

Motor özneyi “Employee” kaydından okur. Bu kayıttaki `user_id`, `reports_to`, `department` ve `company` alanları kapsamı belirler. Çalışan bu alanları değiştirebilirse kendi kapsamını genişletir.

Bu yüzden bir koşul zorunludur. Uygulama çalışana kendi “Employee” kaydında yazma izni verebilir. O uygulama bu dört alanı izin seviyesiyle kapatır. Bu koşul kural şablonları turunda testle denetlenir (G-104).

### Frappe'nin bilinen iki davranışı

- Kanban panosu sütun sayısını izin uygulamadan sayar (`desk/doctype/kanban_board/kanban_board.py:531`). Kural dışı kayıtların sayısı görünebilir. Son kullanıcı yönetim ekranını görmez (D-5).
- `frappe.client.get` ucu süzgeçle çağrılınca iki ayrı hata döner. Kural dışı kayıt izin hatası verir. Olmayan kayıt bulunamadı hatası verir. Bu fark bir alanın değerini sınamaya yarayabilir.

İki davranış da inceleyenin kod okumasına dayanır. Bu tur ikisini de sınamadı.

## 16. Görünen metnin dili

Görünen metnin kaynağı İngilizcedir (D-12, O-21). Türkçesi `platform_core/translations/tr.csv` dosyasındadır. Dosyanın üç sütunu vardır: kaynak, çeviri ve bağlam (O-23).

- Kayıt türünün adı, alan etiketleri ve alan açıklamaları İngilizcedir. Çeviri satırlarının bağlamı “Access Rule” olur. Örneğin “Scope” başka yerde başka anlam taşıyabilir.
- Hata ve uyarı iletileri `frappe._` ile yazılır. Çeviri satırlarının bağlamı boştur.
- Yapay zekâ araçlarının açıklamaları da İngilizcedir ve çeviri dosyasında karşılığı vardır.
- Kullanıcının dili Türkçeyse etiket ve ileti Türkçe görünür. Dil İngilizceyse İngilizce görünür. Bir test bunu sınar.
- Bir test motorun her görünen metninin çeviri dosyasında karşılığı olduğunu sınar. Yeni ileti karşılıksız eklenirse test başarısız olur.

Kod adları bu işte değişmedi. Örneğin `erisim` klasörünün adı aynıdır. Adları naming-history-fix betiği değiştirir.

## 17. Bağımlılık ve sınırlar

- `erisim` modülü öteki `platform_core` modüllerini içe aktarmaz. Öteki modüller de `erisim` modülünü içe aktarmaz. Bu yön proje kaydındadır.
- Motor “Employee”, “Department” ve “Company” kayıt türlerini adla kullanır. Bu türler ERPNext'ten gelir. Kiracı sitesi ERPNext taşır (proje kaydı, sürümler tablosu).
- ERPNext kurulu değilse çalışana bağlı kapsam kaydedilemez. `own` kapsamı `owner` alanıyla yine çalışır.
- Motor Frappe'nin ve ERPNext'in kodunu değiştirmez (M-4).
- Motor zamanlanmış iş kurmaz (D-6).

## 18. Ertelenen işler

| İş | Neden ertelendi | Nerede |
| --- | --- | --- |
| Uygulamaya özel kural şablonları ve `app` alanı | Görev belgesi kapsam dışı sayar. | Sonraki tur, G-104 |
| Paylaşım, takım ve proje üyeliği ilişkileri | Karar sitesi P5 fazına koyar. | G-122 |
| Rol ve rol izni yönetim uçları | Bu işin sahibi belli değil. | G-62 |
| Süzgeçte `>`, `<` ve `like` işleçleri | Şimdilik ihtiyaç yok (A-5). | İhtiyaç doğunca |
| Kiracı yöneticisi rolü (“Tenant Admin”) | Rol henüz tanımlı değil. Uçlar şimdilik “System Manager” ister. | G-62 |
| Dosya, arka plan işi ve anlık bildirim yüzeyleri | Bu tur liste, kayıt, rapor ve dışa aktarmayı kapsar. | G-121 |

## 19. Geri dönüş

Motor iki kanca satırıyla bağlanır. Satırlar silinirse Frappe'nin olağan izinleri geçerli olur. “Access Rule” kayıtları veritabanında kalır ama etkisizdir. Veri geçişi gerekmez.
