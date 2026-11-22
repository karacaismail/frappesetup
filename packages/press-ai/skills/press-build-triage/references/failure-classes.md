# Hata sınıfları

İki kaynak: (A) kılavuzda canlı kanıtla çözülmüş olaylar (pressguide adım kimlikleriyle), (B) Press'in kendi build hatası
eşleştiricisi (press/press/doctype/deploy_candidate/deploy_notifications.py, handlers, develop `ebf3e22`). Eşleşme metni
Output ya da traceback içinde aranır; sıra önemlidir, ilk eşleşen sınıf geçerlidir. Kılavuzdaki somut kimlikler (site, grup,
build adları) buraya taşınmaz.

## A. Kılavuzda kanıtlanmış sınıflar

| Kimlik | İlk Failure ve sinyal | Anlam | Toplanacak kanıt | Sahip | Tek sonraki adım | Yapılmaz |
| --- | --- | --- | --- | --- | --- | --- |
| FC-01 | Pre-build, Output "Required app not found" ile uygulama ve bağımlılık adı (`live-error`, `identity-error`) | Gruptaki App kimliği yanlış (repo paket adından farklı) ya da `required_apps` bağımlılığı grupta yok | Grup Apps tablosu; release commit'indeki hooks.py `required_apps`; App ve Source eşleşmesi | team / operator; hooks yanlışsa uygulama geliştiricisi | Doğru App ve Source ile `release_group.add_app`, yeni candidate, tek build | İkinci teknik kimlik açmak, eski kaydı körlemesine silmek, düzeltmeden build |
| FC-02 | Pre-build validation, "Invalid simple block" ve bir Node aralığı (`live-npm-range-validation`) | Kurulu Press, npm sözdizimli Node aralığını yanlış ayrıştırıcıyla okuyor (develop npm ayrıştırıcısı kullanır) | Output satırı; kurulu Press sürümü (`press.version`) | Press kod düzeltmesi: geliştirici + bağımsız inceleme; kurulum Hüseyin Cengiz (`press.code_fix`) | Hedefli düzeltme, yedek ve SHA, regresyon testi; yalnız boştaki build worker'ları yeniden başlatılır; tek build | Doğrulamayı kapatmak, Node gereksinimini silmek, app'in aralığını değiştirmek |
| FC-03 | Upload / Build Context, HTTP 500 (`live-agent-http500`, `live-upload-row`) | Builder upload isteği sunucuda düştü; kılavuz olayında kök neden disk bloklarının %100 dolması | Error Log'daki response ve path; aynı zamandaki Nginx error.log satırı (No space left on device) ve `df -h`, `df -i` ölçümü (Hüseyin Cengiz) | Hüseyin Cengiz (`server.disk_check`, `server.build_cache_cleanup`) | Onaylı, yalnız kullanılmayan build cache temizliği; yeniden ölçüm; tek build | Image, container, site, yedek, Redis, veritabanı silmek; ajan kodunu değiştirmek; aynı sunucuda başka builder işleri başarılıyken protokol uyuşmazlığını neden saymak |
| FC-04 | Upload / Docker Image, son adım Failure (`live-ecr-push-failure`) | Registry'de hedef depo yok ya da hesap, region, namespace uyuşmuyor | Son Output satırı; hesap ve namespace eşleşmesi (secret yazdırılmadan) | Hüseyin Cengiz (`registry.repository_check`) | Yalnız eksik depo, mevcutlarla aynı ayarlarla; doğrulama; tek build | Push adımını atlamak, build'i elle Success yapmak, Agent Job Success'ini push başarısı saymak |
| FC-05 | Uzun Preparing veya Pending (`preparing`, `live-build-start`) | Kuyruk, worker veya scheduler beklemesi; hata türü belli değil | Build zamanları; filtresiz Run Remote Builder listesi; terminal sonrası Error Log | Hüseyin Cengiz | Kanıtla devir | Yeni build açmak, Preparing'i başarı saymak |
| FC-06 | Build Success, deploy yok (`schedule`, `live-build-success`) | Deploy ayrı iştir | Tüm adımlar Success; bu candidate için Deploy yok | team / operator | press-operations ile tek `deploy.start` önerisi | Birleşik build-deploy yolu |
| FC-07 | Deploy var, bench Active değil (`live-bench-active`) | Bench kurulumu sürüyor ya da düştü | Deploy durumu (deploy_information bayrakları, Pending ya da Installing bench, operator ile Queued New Bench Queue); her beklenen sunucuda bench, build eşleşmesi ve New Bench işi adımları | Hüseyin Cengiz (Failure ise) | Installing ise izle; Failure ise devir | İkinci deploy, Installing'i ya da yalnız bir sunucunun Active olmasını hazır saymak |
| FC-08 | Site Installing ya da Active ama doğrulanmamış (`site`, `live-site-active-apps`) | Site işi sürüyor ya da yalnız etiket okundu | `site.jobs` (New Site, Add Site to Upstream); `site.https_check`; app listesi | team | Ayrı ayrı doğrula | Formu tekrar göndermek, işi yeniden başlatmak, siteyi silmek |
| FC-09 | Dashboard New Bench veya New Site sürüm seçenekleri boş (`live-dashboard-empty`, `live-site-form-initial`) | Neden kılavuzda kesinleşmedi | Grubun Desk kaydı; grubun kendi Sites sayfası | team | Siteyi grubun kendi Sites sayfasından açmak (insan) | Neden uydurmak; boş formdan kayıt açmak |
| FC-10 | Daily Usage "No data" ya da daily_usage InternalServerError (`live-analytics-daily-usage`) | Log server yapılandırılmamış; hata ise Press kod sorunu | `press_settings.flags` (log server alanı); Error Log traceback'i | Kod hatası: geliştirici + bağımsız inceleme, kurulum Hüseyin Cengiz (yalnız Press web süreci) | No data'yı metrik yokluğu olarak raporlamak; hata ise devir | Sıfır kullanım ya da kesinti demek; sahte sıfır veri |
| FC-11 | Geçmiş tarihli "MISCONF Errors writing to the AOF file: No space left on device" (`live-redis-enospc`) | Önceki güne ait Redis yazım hatası | Güncel Redis kalıcılık durumu (Hüseyin Cengiz) | Hüseyin Cengiz | Tarihi ayırmak, güncel ölçümle karşılaştırmak | Bugünkü hatanın kanıtı saymak |
| FC-12 | "pong", Show Agent Version, Help → About (`live-agent-pong`, `live-agent-version`, `live-press-version`) | Bağlantı, repo HEAD ve panel sürümü | Üçü ayrı kaydedilir | — | Kanıt olarak not etmek | Pong'u build protokolü, HEAD'i çalışan kod, panel v15'i grup hedefi saymak |

## B. Press'in kendi eşleştiricisi

| Eşleşme metni (Output ya da traceback içinde) | Sınıf | Tipik sahip | Sonraki adım |
| --- | --- | --- | --- |
| "App installation token could not be fetched", "Repository could not be fetched" | App kaynağı alınamadı (GitHub kurulumu, erişim, repo adresi) | team | Source repo ve branch denetimi (`app_source.branches`) |
| "No python dependency file found", "App has invalid pyproject.toml file", "Could not determine the package name" | Python paket yapılandırması | Uygulama geliştiricisi | pyproject.toml düzeltmesi, yeni release (frappe-custom-app) |
| "App has invalid package.json file" | Frontend paket yapılandırması | Uygulama geliştiricisi | package.json düzeltmesi, yeni release |
| 'engine "node" is incompatible with this module', "Incompatible Node version found" | Grup Node sürümü ile app `engines` aralığı uyuşmuyor | team (grup bağımlılığı) ya da geliştirici | Grup runtime'ı veya app aralığı; karar insanda |
| "Incompatible Python version found" | Grup Python sürümü ile `requires-python` uyuşmuyor | team ya da geliştirici | Aynı |
| "Incompatible app version found" | App'in Frappe bağımlılık aralığı grup sürümüyle uyuşmuyor | Geliştirici | Doğru branch ya da aralık |
| "Invalid release found" | Release kaydı geçersiz | team | Yeni release (`app_release.create`) |
| "Required app not found" | FC-01 | — | FC-01 |
| "ModuleNotFoundError: No module named 'frappe'" | Paket başlatma dosyasında desteklenmeyen kod (frappe'yi paket yüklenirken içe aktarmak) | Geliştirici | `__init__.py` sadeleştirmesi |
| "ModuleNotFoundError: No module named", "ImportError: cannot import name", "No matching distribution found for" | Python bağımlılığı veya içe aktarma hatası | Geliştirici | Bağımlılık ve import düzeltmesi |
| "[ERROR] [plugin vue]", "[ERROR] [plugin frappe-vue-style]", "vite: not found", frontend bağımlılık kurulumu ve derleme hataları | Frontend derlemesi | Geliştirici | Yerelde derleme denemesi (insan), düzeltme, yeni release |
| "Error occurred during app install" | Uygulama yapısı geçersiz | Geliştirici | Dizin yapısı (frappe-custom-app) |
| frappe paketinin PyPI'den kurulduğu uyarısı | frappe Python bağımlılığı olarak listelenmiş | Geliştirici | frappe'yi Python bağımlılıklarından çıkarmak |

Engelleme kuralı: Press, kullanıcının giderebileceği build hatasını bildirim olarak yazar ve çözülene kadar yeni build'leri
engeller. Uygulama aşamasında düşen build'den sonra aynı app hash'iyle yeni candidate reddedilir; yeni release gerekir.
