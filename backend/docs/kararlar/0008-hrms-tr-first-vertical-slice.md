# HRMS TR izin talebi

HRMS TR, Frappe üzerinde çalışan ayrı bir uygulamadır. HRMS v16.54.1 sürümüne dayanır.
HRMS TR, K10 ve O-16 kararlarına göre GPL-3.0 lisansı kullanır.
Proje bu lisans için hukuk görüşü almadı. Bordro hesabı kapsam dışındadır.

| Rol | Kayıt kapsamı | İzin bakiyesi | Onay |
| --- | --- | --- | --- |
| HRMS TR Employee | Kendi çalışan kaydı | Kapalı | Kapalı |
| HRMS TR Manager | `reports_to` üzerinden bağlı ekip | Açık | Bağlı ekip |
| HRMS TR Admin | Kiracı sitesindeki tüm çalışanlar | Açık | Açık |

Erişim kuralı, kullanıcıyı `Employee.user_id` alanıyla çalışan kaydına bağlar.
Yönetici zincirini `Employee.reports_to` alanı kurar.
`leave_balance` alanını Frappe izin seviyesi 2 ile korur.
Yönetici ve İK rolleri bu seviyede okuma hakkı alır.

Kabuk, kurulu HRMS uygulamasının “Workspace Sidebar” kaydından menü öğelerini alır.
HRMS TR, panel yolu veya ayrı bir menü tanımlamaz.

`hrms_tr_approve_leave` aracı yalnız kayıt adını alır ve öneri oluşturur.
Önizleme kayıt sürümünü ve durum değişikliğini gösterir.
İnsan oturumu öneriyi onaylayınca yapay zekâ katmanı izni yeniden denetler.
HRMS TR, kaydı Frappe üzerinden onaylar ve gönderir.
Yapay zekâ katmanı işlemi “AI Action Log” kaydına yazar.

HRMS TR, izin taleplerinde doğrudan belge paylaşımını kapatır.
Frappe, paylaşılan kayıtları normal erişim kuralının dışında açabilir.
Daha önce paylaşım veya özel seviye 2 izni varsa kurulum durur.
Tüm erişim kuralları kapanırsa HRMS TR listeyi ve belgeyi kapatır.
Yönetici ve İK, kendi taleplerini onaylayamaz.
Standart HRMS rolü, HRMS TR rolünün yerini tutmaz.
Bu karar izin talebindeki alanı kapsar. Ayrı HRMS bakiye uçlarının durumu aşağıda açıklanır.

## İnceleme sonrası kararlar

HRMS TR rolleri masaüstü erişimi vermez. Üç rol de “Website User” türünü kullanır.
HRMS TR, izin listesine onay, iptal ve onaylayan kişi sorgusu uçlarını ekler.
Onay ucu rolü, kayıt erişimini ve sürümü ayrıca denetler.
Eski HRMS yolları izin listesinde yer almaz.
Çalışan, `hrms_tr.api.get_leave_approver` ile izin talebini kimin onaylayacağını öğrenir.
Sunucu, sorgu için HRMS'in çalışan erişim kuralını uygular.
Yönetici ve İK rol profilleri çalışan rolünü de taşır.
HRMS, varsayılan onaylayıcıya kendi “Leave Approver” rolünü ekler.
HRMS TR, bu rolü HRMS TR hesabından çıkarır.
HRMS TR hesapları masaüstü erişimi veren başka rol alamaz.

İK, gönderilen izin talebini `hrms_tr.api.cancel_leave` ile iptal eder.
İK, iptal isteğinde kaydın `modified` değerini sürüm olarak gönderir.
Sunucu rolü, kayıt iznini ve sürümü denetler. Ardından Frappe iptali yapar.
İK, iptal edilen talebin düzeltme kopyasını açabilir.
Portal kullanıcısı, genel kayıt adresinden veya `frappe.client.cancel` ile iptal yapamaz.
İK rolü, bu işlem için kiracıdaki `Employee` kayıtlarını okuyabilir.
İK rolünün çalışan kayıtlarına yazma, rapor alma, dışa aktarma ve yazdırma izni yoktur.
Yönetici ve çalışan rolleri, başka bir kişinin `Employee` kaydını okuyamaz.
Kaydedilen talepte çalışan değiştirilemez. Düzeltme kopyasında aynı çalışan kalır.
Yönetici, ekip üyesinin talebinde yalnız durum alanlarını değiştirebilir.
Sunucu tarih, izin türü, açıklama ve kayıt sahibi değişikliklerini reddeder.
Yönetici ve İK kendi taleplerini onaylayamaz.

HRMS TR, eski HRMS bakiye ve takvim uçlarını kiracı sitesinde kapatır.
Yetkili kullanıcı bakiyeyi izin talebi üzerinden okur.
İzin kuralı veya motor kancası yoksa kayıt erişimi kapanır.

Frappe, özel izin satırları varsa bu satırları standart izinlerin yerine kullanır.
“System Manager” ve “HR Manager” işlemleri için ayrı izin satırları vardır.
Bu roller izin talebini okuyabilir, yazabilir, onaylayabilir ve iptal edebilir.
Birinci seviye durum alanını okuyup yazabilirler. İzin bakiyesi ikinci seviyede kalır.
HRMS TR, “HR User”, “Employee” ve “Leave Approver” rollerine özel izin eklemez.
Erişim motoru bu roller için izin talebi kuralı bulamaz.
HRMS'in daha önce kurduğu standart özel izin kayıtlarına dokunulmaz.
Employee için özel izin yoksa Frappe standart izinleri özel satırlara kopyalar.
Bu kopyalar HRMS TR kaldırıldığında kalır. HRMS TR kendi okuma satırını kaldırır.
Frappe sonraki standart izin değişikliklerini bu kopyalara kendiliğinden eklemez.
Frappe’nin “Administrator” hesabı kendi yönetim yetkisini korur.

Frappe, alan ayarlarına standart ad verir. HRMS TR bu adları korur.
Kurulum, çakışan alan ayarı, ikinci seviye izin veya paylaşım varsa durur.
Frappe, geçiş sırasında örnek kayıtları yeniden yükler.
HRMS TR, geçişten önce kapalı olan kendi erişim kurallarını kapalı tutar.
Kaldırma işlemi HRMS TR izinlerini, kurallarını ve alan ayarlarını temizler.
Ön deneme kayıt silmez. Kullanıcı rolleri ve profilleri saklanır.

HRMS TR, GPL-3.0-only lisansını kullanır. Bu ifade yalnız GPL sürüm 3’ü seçer.

Geçiş, mevcut izin talebi paylaşımı varsa durur.
Kaldırma sonrası temizlik yarıda kalırsa yetkili operatör aynı işlemi yeniden çalıştırabilir.
Operatör, “Administrator” oturumuyla site konsolundan `hrms_tr.setup.remove_policy_fixtures()` işlevini çağırır.
İşlev HRMS TR hâlâ kuruluysa kayıt silmez.

## Kurulum sırası ve kapalı HRMS yolları

HRMS TR, `platform_core.erisim` kancalarına ve “Access Rule” kayıt türüne dayanır.
`erisim-kurali` dalı HRMS TR dalından önce birleşir.

| HRMS yolu | Kapatma nedeni |
| --- | --- |
| `get_leave_details` | Bekleyen izinleri kayıt iznini uygulamadan toplar. |
| `get_leave_balance_on` | İzin kaydından yarım gün bilgisi okur. |
| `hrms.api.get_leave_balance_map` | Bakiye hesabını eski izin yolu üzerinden yapar. |
| `hrms.api.get_leave_types` | Eski izin detaylarını okuyarak türleri çıkarır. |
| `get_events` | Ayar açıkken izin takvimini kayıt izni olmadan okur. |
| Employee Leave Balance | Bakiye hesabı kayıt geri dönüşlerini izin kuralına bağlamaz. |
| Employee Leave Balance Summary | Eski izin detayları üzerinden bekleyen talepleri toplar. |
| Leave Ledger | İzin talebi bağlantılarını kayıt izni uygulamadan döndürür. |
| Attendance Request uyarıları | İzin kaydı varsa gün bilgisini açıklar. |
| Bordro taslağı, vardiya çizelgesinden | İzin bilgisiyle çalışma günü hesabı yapar. |
| Bordro taslağı, maaş yapısından | İzin bilgisiyle çalışma günü hesabı yapar. |

Onay ucu, kayıt iznini çağırdığı işlevde denetler.
Eski HRMS ret ucu kayıt okumadan izin hatası verir.
Semgrep bu iki yolu izleyemediği için ilgili uca dar istisna eklendi.

Kapatılan raporların önceden üretilmiş sonuçları da indirilemez.
Rapor uçları ve rapora bağlı özel dosya indirme yolu bu denetimi uygular.

## Kayıt okuma, sürüm ve önizleme

Liste ve belge okuma, Frappe'nin genel `/api/resource/Leave%20Application` yolunu kullanır.
Liste alanları, süzgeç ve sayfalama seçenekleri OpenAPI sözleşmesinde yer alır.
Frappe kayıt ve alan izinlerini bu yolda uygular.
Sözleşme, sayfa başına 1 ile 100 kayıt aralığını destekler.
Frappe, sıfırı sayfa sınırı olmadan okuma isteği olarak yorumlar.

İnsan onay isteği, okunan kaydın `modified` değerini `version` olarak taşır.
Sunucu kaydı kilitler.
Sürüm değişmişse Frappe, 417 koduyla `TimestampMismatchError` döndürür.
Bu durumda talebin durumu değişmez.

Yapay zekâ aracı yalnız talebin kayıt adını alır.
Önizleme, kaydın güncel sürümünü `target_version` alanına yazar.
Platform, insan onayında ve çalıştırmadan önce kilit altında sürümü denetler.
Talep öneriden sonra açık durumdan çıkarsa platform onayı durdurur.
Platform bu durumda `invalid_arguments` döndürebilir.
Önizleme, alan farklarını `fieldname`, `label`, `old` ve `new` ile gösterir.
Öneri ayrıntısında yalnız talebin kayıt adı bulunur.
Önizleme çalışan adı, izin tarihleri ve gün sayısını içermez.
HRMS izin onayını reddederse araç, kişi bilgisi içermeyen bir hata verir.

## Öz denetim kararları

Portal kullanıcıları `/panel` yolunu kullanır.
HRMS TR, hazır HRMS sayfalarına portal hesabıyla girişi kapatır.
Frappe, onay isteğini oturum açmış kullanıcı başına dakikada 60 kez sınırlar.
Bu sayı güvenlik sınırıdır.

Geçiş, kullanıcıları ad sırasıyla en çok 100 kişilik gruplarda tarar.
Yalnız düzeltme gereken kullanıcı belgesi yüklenir ve kaydedilir.
Bu sistem sorgusu, kullanıcıya dönen bir liste üretmez.
Liste sözleşmesi eşit değişiklik saatleri için kayıt adı sırası verir.

### Test araçları

HTTP testleri, OpenAPI yanıtlarını elle yazılan alan denetimleriyle sınayabilirdi.
Ancak elle yazılan denetimler şemadaki kuralları tekrar eder.
Testler, OpenAPI dosyasını okumak için PyYAML 6.0.3 kullanır.
Bu sürüm, Frappe test imajında gözlenen sürümdür. PyYAML, dosyayı `safe_load` ile okur.
Testler, yanıtları şemaya göre sınamak için jsonschema 4.26.0 kullanır.
İki yayımlanmış sürüm de MIT lisanslıdır. Paketler yalnız test imajına kurulur.
Tarayıcıya paket gönderilmez. Geri dönüş için önce eşdeğer testler hazırlanır.
[PyYAML sürüm kaydı](https://pypi.org/project/PyYAML/6.0.3/)
[jsonschema sürüm kaydı](https://pypi.org/project/jsonschema/4.26.0/)

İzin kaydı çalışana olan bağı, izin tarihlerini ve talep açıklamasını tutar.
Öneri ayrıntısı yalnız kayıt adını tutar.
Saklama süresi ve silme yolu MVP yayını öncesinde proje kaydında karara bağlanır.
Temiz kurulumda “Module Def” kaydı doğrulandı.
Eski rolü eksik olan test hesabı, yükseltmeyle çalışan rolünü aldı.
İki yükseltme de devre dışı kuralı ve mevcut izin kaydını korudu.
Birleşme sonrası tam paket `backend` dalında yeniden çalışır.
