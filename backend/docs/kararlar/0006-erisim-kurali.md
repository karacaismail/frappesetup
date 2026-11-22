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

Karar sitesi tek kayıt için Python yüklemi önerir. Bu not o yolu seçmedi. Nedeni şudur: MariaDB metni büyük küçük harf ayırmadan karşılaştırır. Python ayırır. Boş değer de iki yerde farklı davranır. İki ayrı değerlendirici zamanla farklı sonuç verir. Tek değerlendirici bu farkı baştan kapatır (G-121).

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
- Tek kayıt denetimi kayıt başına 1 sorgu açar. Yazmada 1 sorgu daha açılır.

Bu sayılar tasarım hedefidir. Ölçüm 2. kontrol noktasında yapılır.

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

### Motorun eklediği iki uç

Alan seviyesini yönetmek için iki ince uç yazılır. Uçlar Frappe'nin hazır işlevlerini çağırır.

- `set_field_level` bir alanın seviyesini değiştirir. Değişiklik “Property Setter” kaydıyla tutulur.
- `set_level_access` bir role bir seviye için okuma ve yazma izni verir. Değişiklik “Custom DocPerm” kaydıyla tutulur.

İki uç da yalnız “System Manager” rolüne açıktır. İkinci uç seviye 0'a dokunmaz. Böylece yönetici temel erişimi bu uçla bozamaz.

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
| Sorgu raporu | Raporun kendi SQL'i | **Kanca çalışmaz** | `desk/query_report.py:968` |
| Sistem kodu | `frappe.get_all`, ham SQL | **Kanca çalışmaz** | `__init__.py:1400` |

### Sorgu raporu açığı

Sorgu raporu (“Query Report” ve “Script Report”) veriyi kendi SQL'iyle okur. Frappe sonucu yalnız “User Permission” kayıtlarına göre süzer (`desk/query_report.py:971`, `:1199`). Liste kancası bu yolda çağrılmaz. Bu yüzden kural sorgu raporuna kendiliğinden girmez.

Karar şudur: Motor bu raporlara bir kapı koyar. Kapı güvenli tarafta kalır.

1. Raporun ana kayıt türü kurallı değilse kapı karışmaz.
2. Öznenin o türde `all` kapsamlı ve süzgeçsiz bir okuma kuralı varsa kapı karışmaz. Özne zaten bütün kayıtları görür.
3. Öteki durumda kapı raporu izin hatasıyla reddeder.
4. Bir uygulama raporunu kurala uyumlu yazabilir. Örneğin rapor veriyi `frappe.get_list` ile okur. Uygulama bu raporu `access_rule_aware_reports` kancasıyla bildirir. Kapı bildirilen raporu geçirir.

Kapı Frappe'nin `override_whitelisted_methods` kancasıyla bağlanır. Bu kanca bir ucun yerine başka işlev koyar (`__init__.py:1577`). Kapı `frappe.desk.query_report.run` ve `frappe.desk.query_report.export_query` uçlarını sarar. Frappe'nin kodu değişmez (M-4).

Kapının iki sınırı vardır:

- Kapı yalnız raporun ana kayıt türüne bakar. Rapor başka bir kurallı türü de okuyabilir. Kapı bunu göremez.
- Kapı yalnız HTTP ucunda çalışır. Raporu Python'dan çağıran kod kapıyı atlar.

Bu sınırlar için iki önlem yazıldı:

- Kendi uygulamalarımızda kullanıcıya dönen veri `frappe.get_list` ile okunur (G-3). `frappe.get_all` ve ham SQL gerekçeli istisnadır.
- `yapay_zeka` modülünün `run_report` aracı raporu Python'dan çağırıyor. Araç, çağıracağı işlevi `frappe.override_whitelisted_method` ile bulmalıdır. Böylece kapı o yolda da çalışır. Bu istek raporda orkestratöre iletildi.

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

## 11. Yapay zekâ katmanı aynı sonucu nasıl alır?

Yapay zekâ katmanı ayrı bir yetki yolu kurmaz. Katman kullanıcının kimliğiyle Frappe'nin aynı işlevlerini çağırır. Kancalar o işlevlerin içindedir.

`platform-core-yz` dalındaki kod okundu:

| Araç | Çağırdığı yol | Sonuç |
| --- | --- | --- |
| `list_documents` | `frappe.get_list` | Liste kancası çalışır. |
| `get_document` | `check_permission("read")` ve alan silme | Kayıt kancası ve izin seviyesi çalışır. |
| Yazma araçları | Onaydan sonra kaydın `save` yolu | Kayıt kancası çalışır. |
| `run_report` | `frappe.desk.query_report.run`, Python'dan | Rapor kapısı çalışmaz. 9. bölümdeki istek bunu kapatır. |

- `erisim` modülü `yapay_zeka` modülünü içe aktarmaz. `yapay_zeka` da `erisim` modülünü içe aktarmaz. İki modül yalnız Frappe'nin kancalarında buluşur.
- Yapay zekâ kuralları genel kayıt araçlarıyla yönetir. “Access Rule” olağan bir kayıt türüdür. Yazma yine öneri ve insan onayı ister.
- Açıklama ucu yapay zekâya da açılır. Uç `ai_tools` kancasıyla salt okunur araç olarak bildirilir. Bildirim 2. kontrol noktasında yazılır.

## 12. Önbellek

Kanca her izin denetiminde çalışır. Kural listesi her seferinde veritabanından okunursa her denetime 1 sorgu eklenir.

Bu yüzden etkin kurallar önbellekte tutulur. Önbellek, sık istenen sonucu geçici olarak saklar.

- Anahtar bütün etkin kuralları kayıt türüne göre taşır. Kullanıcıya özel veri taşımaz.
- “Access Rule” kaydı eklenince, değişince ve silinince önbellek silinir. Silme, kayıt kesinleşince bir kez daha yapılır.
- “Role” ve “DocType” adı değişince ya da silinince de önbellek silinir.
- Özne değerleri önbelleğe girmez. Yalnız istek boyunca saklanır. Böylece `reports_to` değişikliği hemen etki eder.

Kural değişince sonuç sonraki istekte değişir. Bu davranış testle sınanır.

P-5 kuralı önbelleği ölçümle gerekçelendirmeyi ister. Ölçüm 2. kontrol noktasında yapılır. Ölçüm kazanç göstermezse önbellek kaldırılır.

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

- Olağan kullanıcı yalnız kendi iznini sorabilir. Ret nedeni tek değerdir: `not_permitted_or_missing`. Kayıt yoksa da aynı değer döner.
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

Testler 1. kontrol noktasında çalıştırılamadı. `platform_core` iskeleti henüz `backend` dalında yok. Testlerin beklenen nedenle başarısız olduğu 2. kontrol noktasının başında kaydedilir (D-2).

## 15. Bağımlılık ve sınırlar

- `erisim` modülü öteki `platform_core` modüllerini içe aktarmaz. Öteki modüller de `erisim` modülünü içe aktarmaz. Bu yön proje kaydındadır.
- Motor “Employee”, “Department” ve “Company” kayıt türlerini adla kullanır. Bu türler ERPNext'ten gelir. Kiracı sitesi ERPNext taşır (proje kaydı, sürümler tablosu).
- ERPNext kurulu değilse çalışana bağlı kapsam kaydedilemez. `own` kapsamı `owner` alanıyla yine çalışır.
- Motor Frappe'nin ve ERPNext'in kodunu değiştirmez (M-4).
- Motor zamanlanmış iş kurmaz (D-6).

## 16. Ertelenen işler

| İş | Neden ertelendi | Nerede |
| --- | --- | --- |
| Uygulamaya özel kural şablonları ve `app` alanı | Görev belgesi kapsam dışı sayar. | Sonraki tur, G-104 |
| Paylaşım, takım ve proje üyeliği ilişkileri | Karar sitesi P5 fazına koyar. | G-122 |
| Rol ve rol izni yönetim uçları | Bu işin sahibi belli değil. | G-62 |
| Süzgeçte `>`, `<` ve `like` işleçleri | Şimdilik ihtiyaç yok (A-5). | İhtiyaç doğunca |
| Kiracı yöneticisi rolü (“Tenant Admin”) | Rol henüz tanımlı değil. Uçlar şimdilik “System Manager” ister. | G-62 |
| Dosya, arka plan işi ve anlık bildirim yüzeyleri | Bu tur liste, kayıt, rapor ve dışa aktarmayı kapsar. | G-121 |

## 17. Geri dönüş

Motor iki kanca satırıyla bağlanır. Satırlar silinirse Frappe'nin olağan izinleri geçerli olur. “Access Rule” kayıtları veritabanında kalır ama etkisizdir. Veri geçişi gerekmez.
