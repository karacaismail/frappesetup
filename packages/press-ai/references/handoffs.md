# Sahip devirleri

Paylaşan: tüm Press skill'leri ve ajanları. Bu paketin MCP'si aşağıdaki işleri yürütmez; ajan devir metnini hazırlar,
insan iletir. Hiçbir devir mesajı otomatik gönderilmez. Erişim bilgisine sahip olmak değişiklik yetkisi değildir.

## Roller

| Rol | Kişi | İşler | Kontrat işlemleri |
| --- | --- | --- | --- |
| `infrastructure_owner` | Hüseyin Cengiz | Sunucu hazırlığı ve gruba bağlama, disk ölçümü, onaylı build cache temizliği, registry deposu, ajan ve worker, servis yeniden başlatma, SSH ile log okuma, Press kod düzeltmesinin canlıya kurulumu, katalog etiketi | `release_group.add_server`, `server.disk_check`, `server.build_cache_cleanup`, `server.restart_services`, `registry.repository_check`, `logs.read`, `server.ping_agent`, `server.agent_version`, `press.code_fix`, `cluster.catalog_label` |
| `dns_owner` | Hüseyin Cengiz kaydı hazırlar ve doğrular; Asistan Hüseyin GoDaddy'de uygular | Alan adı kaydı | `dns.record` |
| `account_holder` | Hesap ya da site sahibi | Bölgesel yasal kutu, ödeme yöntemi, plan ve ücretli Marketplace planı, site oluşturma formu, kurulum sihirbazındaki kişisel alanlar | `site.create`, `site.legal_acceptance`, `payment.method`, `site.setup_wizard` |
| `app_developer` | Uygulama geliştiricisi | Yerel bench komutları, git commit ve push, Press kod düzeltmesinin yazımı (bağımsız incelemeyle) | `app.install_local`, `app.migrate_local`, `app.run_tests_local` |

Geri yükleme (`site.restore`) yıkıcıdır: kararı site sahibi verir, uygulama altyapı sahibiyle birlikte yapılır; ajan
`site.restore_preflight` kanıtını hazırlar.

## Devir paketi

Her devir şu alanları taşır; boş alan "bilinmiyor" diye yazılır.

1. Hedef: grup, candidate, build, site kimlikleri ve sunucu adı (IP ve hesap kimliği yok).
2. Zaman: olay zamanı UTC ve TSİ (UTC+3).
3. Kanıt: ilk Failure adımı (Stage, Step), Output'un sınıflamaya yeten satırı, ilgili Error Log ve Agent Job kimlikleri.
   Request Data, token, parola, özel anahtar, tam traceback ve imzalı adres eklenmez.
4. İstenen iş: tek ve sınırlı bir eylem; kapsam dışı olanlar açıkça yazılır.
5. Yapılmayanlar: ör. "servis yeniden başlatılmadı, deploy yapılmadı, kayıt silinmedi".
6. Kabul ölçütü: devrin tamamlandığını gösteren ölçüm veya durum.

## İşe göre kurallar

| İş | Sınır | Kabul |
| --- | --- | --- |
| Build cache temizliği | Yalnız kullanılmayan build cache, açık onayla. Image, container, volume, site, yedek, Redis ve veritabanı silinmez | Önce ve sonra `df -h` ve `df -i`; ardından tek build sonucu |
| Servis yeniden başlatma | Yalnız adı geçen süreç (ör. boştaki build worker'ları ya da yalnız Press web süreci); müşteri bench'leri ve Redis'e dokunulmaz | Süreç ayakta; ilgili iş yeniden denendiğinde sonuç |
| Registry deposu | Hesap, region ve namespace eşleşmesi doğrulanır; yalnız eksik depo, mevcut depolarla aynı ayarlarla oluşturulur; mevcut depolar ve hesap ayarı değişmez; secret yazdırılmaz | describe ile doğrulama; sonraki build'in Upload Docker Image adımı Success |
| Press kod düzeltmesi | Özgün dosya yedeği ve SHA, hedefli değişiklik, önce kırmızı sonra yeşil regresyon testi, bağımsız inceleme; doğrulama kapatılmaz, sahte veri eklenmez | Testler ve canlı okuma; yalnız gereken sürecin yeniden başlatılması |
| Sunucu ekleme | Önce Press'te hazır Server kaydı (kapasite, ajan erişimi, roller, güvenli ağ); tabloya satır eklemek sunucu kurmaz | Sunucu kaydı hazır; deploy sonucu ayrıca doğrulanır |
| Katalog etiketi | Yalnız etiket alanları, önceki değer yedeklenir; altyapı konumu doğrulanmış sayılmaz | Yasal metinde doğru bölge adı |
| DNS | Hüseyin Cengiz kayıt türü, adı, değeri ve TTL'i yazar; Asistan Hüseyin GoDaddy'de uygular | Hüseyin Cengiz çözümlemeyi ve TLS doğrulaması açık HTTPS sonucunu doğrular |
| Yasal kutu, ödeme, plan | Kullanıcı metni okuyup kendisi işaretler; isteğe bağlı kutular kapalı kalır | İnsanın kendi işlemi |

Press Settings'teki Branch alanı, Update Agent ve Ansible düğmeleri rastgele kullanılmaz; servis etkisi ve geri dönüş planı
olmadan önerilmez. Eski özel SSH MCP'si bu paketin parçası değildir; ajan onu çağırmaz ve onun yerine geçmez.
