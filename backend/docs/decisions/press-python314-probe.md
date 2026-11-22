# Press uyum denemesinin paket kararı

Karar tarihi 22 Kasım 2026 Pazar günüdür.
Bu karar T-2 kapsamındadır. Yalnız Görev B deneme imajını kapsar.
Mevcut geliştirme kurulumu bu paketlere geçirilmez.

## İhtiyaç ve seçim

Press yaması üç paketin dosyalarını değiştiriyor.
Yama ayrıca Ansible yükleyicisini kapatıyor ve eksik standart modülleri kuruyor.
Amaç, bu işlemleri paket seçimiyle karşılayıp kaynak değişikliğini azaltmaktır.
İki Press kaynak engeli sürdüğü için genel uyum sağlanamadı.

| Paket | Seçilen sürüm | Lisans | Seçim nedeni |
| --- | --- | --- | --- |
| Ansible | `14.0.0` | GPL-3.0-or-later | Python 3.14 destekleyen yeni çekirdeği kullanır. |
| ansible-core | `2.21.5` | GPL-3.0-or-later | Eski import yükleyicisini değiştirmeden çalışır. |
| python-telegram-bot-raw | `13.15` | LGPLv3 | Press'in kullandığı eşzamanlı Bot arayüzünü korur. |
| urllib3 | `1.26.20` | MIT | Telegram'ın mevcut geri dönüş yolunu karşılar. |
| stripe | `3.1.0` | MIT | İçindeki six paketi `find_spec` desteği içerir. |
| standard-imghdr, standard-pipes, standard-cgi, standard-crypt | `3.13.0` | PSF-2.0 | Kaldırılan standart modülleri paket olarak sunar. |
| dnspython | `1.16.0` | BSD türü | Press'in bildirdiği sürümü deneme için korur. |
| wrapt | `1.17.3` | BSD | Press yürütücüsünün doğrudan import bağımlılığıdır. |

Sürümler ve lisanslar paketlerin resmî PyPI kayıtlarından doğrulandı.
`standard-crypt` ek uyum bağımlılıkları da getirir.
Deneme imajı bütün Press bağımlılıklarını çözmez. Tam bağımlılık kilidi yoktur.
Paket seçimi dosyası, çalışan üretim bileşimi olarak kullanılmaz.
Tarayıcı koduna paket eklenmez. Mevcut Frappe temel imajı yeniden üretilmez.

## Diğer seçenekler

Telegram 20 ve sonrası, Press'in eşzamanlı çağrılarını değiştirmeyi gerektirir.
Raw paketi, kullanılmayan `telegram.ext` bağımlılıklarını eklemez.
Tam Telegram paketi ile raw paketi birlikte kurulmaz.
Stripe 6, varsayılan uzak API sürümünü de değiştirir.
Stripe 3.1.0, six düzeltmesini içeren daha küçük bir geçiştir.
Bu seçim de ödeme davranışının uyumlu olduğunu kanıtlamaz.

Python'u düşürmek görevdeki Python 3.14 hedefini karşılamaz.
Frappe'yi düşürmek de Frappe 16 hedefini karşılamaz.
Standart kitaplığı veya Frappe modüllerini gölgeleyen paket seçilmedi.
Kaynak kodunu bellekte değiştiren başlangıç kancası eklenmedi.

## Bakım ve güvenlik sınırı

Ansible 2.21 desteği resmî Python destek tablosundan doğrulandı.
Telegram, Stripe ve urllib3 seçimleri eski sürümlerdir.
Güncel güvenlik taraması çalıştırılmadı. Bilinen açık olmadığı iddia edilmez.
Bu nedenle Compose denemesinde ağ tamamen kapalıdır.
Gerçek ödeme, Telegram gönderimi ve uzak sunucu bağlantısı yapılmaz.

Üretim seçimi için bakımı süren paket sürümleri ayrıca değerlendirilmelidir.
Ödeme ve mesaj yolları, sahte hedeflerle davranış testinden geçmelidir.
Ansible için Press üzerinden hazırlık sunucusu testi de gerekir.

## Geri dönüş

Bu değişiklik ayrı Dockerfile ve ayrı Compose dosyası kullanır.
Mevcut `install.sh`, `patch-py314.sh` ve `uv-overrides.txt` değişmedi.
Deneme bitince Compose birimleri ve bu görevin imaj etiketleri silinir.
Görev C için çalışan yamasız ortam sağlanamadı.
Orkestratör denemeyi kaldırırsa eski kurulum aynı şekilde kullanılabilir.
O-18 borcu, sonuç olumlu olmadığı için açık tutulur.

## Yeni sürüm seçimi

Orkestratör, v0.154.1 sonrasının incelenmesini istedi.
162 yeni etiket ve iki dalın ilgili geçmişi tarandı.
İki kaynak engelini birlikte kaldıran kayıt bulunmadı.
Bu nedenle çalışan Press sürümü yükseltilmedi.

Yeni deneme `develop` dalının sabit commit koduyla yapıldı.
Bu kod `d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410` oldu.
Bu seçim üretim veya geliştirme yükseltmesi değildir. Güncel kaynağın doğrulama denemesidir.
Aynı iki engel korunuyordu. On kabul testinin dördü başarısız oldu.
Son etiket ve master aynı iki dosyayı taşıdığı için ayrıca derlenmedi.

Dockerfile artık `PRESS_REVISION` ile tam commit kodu alır.
Varsayılan değer önceki v0.154.1 kodunu korur.
Kaynak testi bu kodu doğrular. Boş kaynak farkı şartı da korunur.
Sürüm taramasının ayrıntıları [kanıt raporundadır](../press-python314-version-audit.md).
O-18 açık tutulur. Bu araştırma kolu kapatılır.

## Kaynaklar

- [Ansible sürüm kaydı](https://pypi.org/project/ansible/14.0.0/)
- [Ansible çekirdeğinin Python desteği](https://docs.ansible.com/projects/ansible-core/devel/reference_appendices/release_and_maintenance.html#ansible-core-support-matrix)
- [Telegram raw paket açıklaması](https://pypi.org/project/python-telegram-bot-raw/13.15/)
- [Telegram urllib3 geri dönüş yolu](https://github.com/python-telegram-bot/python-telegram-bot/blob/v13.15/telegram/utils/request.py#L33-L54)
- [Stripe değişiklik kaydı](https://github.com/stripe/stripe-python/blob/v3.1.0/CHANGELOG.md)
- [Standart modül paketlerinin kaynağı](https://github.com/youknowone/python-deadlib)
- [Deneme sonuçları](../press-python314-upstream.md)
