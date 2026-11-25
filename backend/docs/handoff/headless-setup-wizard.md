# G-42 kurulum sihirbazı devir notu

Yerel açılış, ERPNext kurulduktan sonra Frappe'nin kurulum sihirbazını çağırır.
Bu adım yalnız `tenant1.localhost` için çalışır.
Yerel kurulum örnek şirket ve kullanıcı bilgilerini kullanır.
Mali yıl, İstanbul saatine göre geçerli takvim yılıdır.
Sihirbaz tamamlandıysa yerel açılış ayarları korur.
`System Settings.setup_complete` değeri 1 olmazsa açılış hata verir.

## Press bağlantısı

1. O-9 kapsamındaki Press Agent yığını hazır olunca yeni bir deneme sitesi açın.
2. Kurulum akışında Press'in siteyi “Active” yapmasını bekleyin.
3. Akıştan `frappe.get_doc("Site", site_name).complete_setup_wizard(args)` yöntemini çağırın.
4. G-42 alanlarına deneme şirketinin adını, kısa adını ve kullanıcı bilgilerini koyun.
5. Agent Job kaydının “Success” durumuna geçtiğini doğrulayın.
6. Kiracıda `System Settings.setup_complete` değerinin 1 olduğunu doğrulayın.
7. G-41 değerlerinin korunduğunu doğrulayın.

Press v0.154.1, durumu doğrudan veritabanına yazar.
Bu yüzden `Site.on_update` kancası yeni site açılışında çalışmaz.
Üretim imajındaki `0006-queue-setup-wizard.patch` yaması bu açığı kapatır.
Yama, site “Active” olunca sihirbazı kendiliğinden kuyruğa atar.
Kuyruk işi kayıt kesinleşince çalışır.
Sihirbaz bilgileri sitenin ekibinden gelir.
Şirket adı ekibin fatura adıdır. Fatura adı boşsa ekip sahibinin adı kullanılır.
Yama sahte Agent ile test edildi. Gerçek Agent ile deneme O-9 sonrasına kalır.
O zaman yukarıdaki 3. adımı elle yapmayın. Yamanın işi kuyruğa attığını doğrulayın.

Press v0.154.1, Agent sonucu işlenirken deneme talebi kaydını günceller.
Bu geri çağırma, `Site.setup_wizard_complete` değerini yazmaz.
Press'te bu alanı doğrulamak için `Site.is_setup_wizard_complete()` yöntemini kullanın.

## Kaynaklar

- Press v0.154.1, `press/agent.py`, `Agent.complete_setup_wizard`.
- Press v0.154.1, `press/press/doctype/site/site.py`, `process_new_site_job_update`.
- Aynı dosyada `process_complete_setup_wizard_job_update` ve `Site.is_setup_wizard_complete`.
- Yerel imaj, Frappe 16.56.0 ve ERPNext 16.55.0 sürümlerini içerir.
- Frappe, `frappe/desk/page/setup_wizard/setup_wizard.py`, `setup_complete`.
- ERPNext, `erpnext/accounts/doctype/account/chart_of_accounts/verified/tr_chart_of_accounts.json`.
