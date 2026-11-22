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
`leave_balance` alanını Frappe izin seviyesi 1 ile korur.
Yönetici ve İK rolleri bu seviyede okuma hakkı alır.

Kabuk, kurulu HRMS uygulamasının “Workspace Sidebar” kaydından menü öğelerini alır.
CronHR, panel yolu veya ayrı bir menü tanımlamaz.

`cronhr_approve_leave` aracı kayıt adı ve sürümüyle öneri oluşturur.
Önizleme kayıt sürümünü ve durum değişikliğini gösterir.
İnsan oturumu öneriyi onaylayınca yapay zekâ katmanı izni yeniden denetler.
CronHR, kaydı Frappe üzerinden onaylar ve gönderir.
Yapay zekâ katmanı işlemi “AI Action Log” kaydına yazar.
