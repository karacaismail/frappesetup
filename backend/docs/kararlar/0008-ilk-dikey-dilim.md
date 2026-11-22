# CronHR izin talebi

CronHR, Frappe üzerinde çalışan ayrı bir uygulamadır. HRMS v16.54.1 sürümüne dayanır.
CronHR, K10 ve O-16 kararlarına göre GPL-3.0 lisansı kullanır.
Proje bu lisans için hukuk görüşü almadı. Bordro hesabı kapsam dışındadır.

| Rol | Kayıt kapsamı | İzin bakiyesi | Onay |
| --- | --- | --- | --- |
| CronHR Employee | Kendi çalışan kaydı | Kapalı | Kapalı |
| CronHR Manager | `reports_to` üzerinden bağlı ekip | Açık | Bağlı ekip |
| CronHR HR | Kiracı sitesindeki tüm çalışanlar | Açık | Açık |

Erişim kuralı, kullanıcıyı `Employee.user_id` alanıyla çalışan kaydına bağlar.
Yönetici zincirini `Employee.reports_to` alanı kurar.
`leave_balance` alanını Frappe izin seviyesi 2 ile korur.
Yönetici ve İK rolleri bu seviyede okuma hakkı alır.

Kabuk, kurulu HRMS uygulamasının “Workspace Sidebar” kaydından menü öğelerini alır.
CronHR, panel yolu veya ayrı bir menü tanımlamaz.

`cronhr_approve_leave` aracı kayıt adı ve sürümüyle öneri oluşturur.
Önizleme kayıt sürümünü ve durum değişikliğini gösterir.
İnsan oturumu öneriyi onaylayınca yapay zekâ katmanı izni yeniden denetler.
CronHR, kaydı Frappe üzerinden onaylar ve gönderir.
Yapay zekâ katmanı işlemi “AI Action Log” kaydına yazar.

CronHR, izin taleplerinde doğrudan belge paylaşımını kapatır.
Frappe, paylaşılan kayıtları normal erişim kuralının dışında açabilir.
Daha önce paylaşım veya özel seviye 2 izni varsa kurulum durur.
Tüm erişim kuralları kapanırsa CronHR listeyi ve belgeyi kapatır.
Yönetici ve İK, kendi taleplerini onaylayamaz.
Standart HRMS rolü, CronHR rolünün yerini tutmaz.
Bu karar izin talebindeki alanı kapsar. Ayrı HRMS bakiye uçlarının durumu aşağıda açıklanır.

## İnceleme sonrası kararlar

CronHR rolleri masaüstü erişimi vermez. Üç rol de “Website User” türünü kullanır.
Yönetici ve İK rol profilleri çalışan rolünü de taşır.
HRMS, varsayılan onaylayıcıya kendi “Leave Approver” rolünü ekler.
CronHR, bu rolü CronHR hesabından çıkarır.
CronHR hesapları masaüstü erişimi veren başka rol alamaz.

İK, onaylı talebi iptal edebilir. İK, iptal edilen talebin düzeltme kopyasını açabilir.
Kaydedilen talepte çalışan değiştirilemez. Düzeltme kopyasında aynı çalışan kalır.
Yönetici ve İK kendi taleplerini onaylayamaz.

CronHR, eski HRMS bakiye ve takvim uçlarını kiracı sitesinde kapatır.
Yetkili kullanıcı bakiyeyi izin talebi üzerinden okur.
İzin kuralı veya motor kancası yoksa kayıt erişimi kapanır.

Frappe, özel izin satırları varsa bu satırları standart izinlerin yerine kullanır.
HRMS ve “System Manager” rolleri tek başına CronHR erişimi vermez.
Frappe’nin “Administrator” hesabı kendi yönetim yetkisini korur.

Frappe, alan ayarlarına standart ad verir. CronHR bu adları korur.
Kurulum, çakışan alan ayarı, ikinci seviye izin veya paylaşım varsa durur.
Frappe, geçiş sırasında örnek kayıtları yeniden yükler.
CronHR, geçişten önce kapalı olan kendi erişim kurallarını kapalı tutar.
Kaldırma işlemi CronHR izinlerini, kurallarını ve alan ayarlarını temizler.
Ön deneme kayıt silmez. Kullanıcı rolleri ve profilleri saklanır.

CronHR, GPL-3.0-only lisansını kullanır. Bu ifade yalnız GPL sürüm 3’ü seçer.

Geçiş, mevcut izin talebi paylaşımı varsa durur.
Kaldırma sonrası temizlik yarıda kalırsa yetkili operatör aynı işlemi yeniden çalıştırabilir.
Operatör, site konsolundan `cronhr.setup.remove_policy_fixtures()` işlevini çağırır.
İşlev CronHR hâlâ kuruluysa kayıt silmez.
