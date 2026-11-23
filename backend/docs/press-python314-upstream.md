# Press için Python 3.14 uyum önerisi

İnceleme 22 Kasım 2026 Pazar günü tamamlandı.
Press v0.154.1, Python 3.14 ve Frappe 16 ile yamasız açılamadı.
O-18 borcu açıktır. Mevcut geliştirme yaması kaldırılmadı.
Bu belge Press bakımcılarına gönderilecek öneridir. Henüz gönderilmedi.

## Kaynak ve çalışma ortamı

| Bilgi | Doğrulanan değer |
| --- | --- |
| Press etiketi | `v0.154.1` |
| Press commit kodu | `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` |
| Press paketinin kendi sürüm alanı | `0.7.0` |
| Temel imaj | `frappe/erpnext:v16.55.0` |
| Çalışan ERPNext | `16.55.0` |
| Çalışan Frappe | `16.56.0` |
| Çalışan Python | `3.14.10` |
| İkinci mevcut temel imaj | `press-local-bench:latest`, Python `3.14.8` |
| Deneme imajı | `fs-pd-press-py314:probe` |

İmaj etiketindeki sürüm, Frappe sürümü değildir. Sürümler çalışan Python ortamından okundu.
Press etiketi ile paket sürümü de farklıdır. Test kaynak commit kodunu doğrular.
Yeni Frappe temel imajı üretilmedi. Mevcut ERPNext imajına yalnız deneme katmanı eklendi.

## Yamanın her parçası için karar

| Mevcut işlem | Kaynağı değiştirmeyen aday | Sonuç ve sınır |
| --- | --- | --- |
| Eksik standart modülleri ekleme | `standard-imghdr`, `standard-pipes`, `standard-cgi`, `standard-crypt`, hepsi `3.13.0` | Dört modül içe aktarıldı. Paket dosyaları değiştirilmedi. |
| Ansible içindeki six dosyasını değiştirme | `ansible==14.0.0`, `ansible-core==2.21.5` | `press.runner` içe aktarıldı. |
| Ansible koleksiyon yükleyicisini kapatma | Aynı yeni Ansible sürümleri | Yerel `ansible.builtin.assert` görevi geçti. Sunucu kurulumu denenmedi. |
| Telegram içindeki six dosyasını değiştirme | `python-telegram-bot-raw==13.15`, `urllib3==1.26.20`, `standard-imghdr==3.13.0` | Telegram kendi geri dönüş yoluyla urllib3 paketini kullandı. `Bot` ve `ParseMode` içe aktarıldı. |
| Stripe içindeki six dosyasını değiştirme | `stripe==3.1.0` | İçindeki six `1.16.0` oldu. Stripe içe aktarıldı. Ödeme işlemi denenmedi. |
| Press `TypedDict` tanımını değiştirme | Uyumlu paket yolu bulunamadı. | Press doğrudan Python standart kitaplığını kullanıyor. Kaynak düzeltmesi gerekiyor. |
| Press telemetri import'unu değiştirme | Uyumlu paket yolu bulunamadı. | Frappe 16 gerekli işlevi sunmuyor. Kaynak düzeltmesi gerekiyor. |

Telegram seçimi ayrı bir pakettir. `raw`, ek kurulum seçeneği değildir.
Tam Telegram paketiyle raw paketi birlikte kurulmaz.
Telegram'ın kullandığı urllib3 dalı eskidir. Bu seçim yalnız ağsız deneme içindir.
Stripe geçişi ödeme davranışını değiştirebilir. Yalnız içe aktarma testi ödeme uyumunu kanıtlamaz.
Ansible testi yalnız yerel görev çalıştırır. O-9 sunucu kurma borcunu kapatmaz.

Bu paketler mevcut geliştirme kurulumuna eklenmedi.
Deneme imajı Press bağımlılıklarının tamamını kurmaz. Üretim için uygun değildir.
`probe-requirements.txt` seçili doğrudan paketleri sabitler. Tam bağımlılık kilidi değildir.
Aday paketlerin bakım, lisans ve geri dönüş kaydı [0019 numaralı karar notundadır](decisions/0019-press-python314-probe.md).

Yama kapsamı bütün uyum engellerini kapsamaz.
İnceleme, `press/api/cookies.py` dosyasında üçüncü kaynak engelini de doğruladı.
Tam bağımlılık çözümü ayrıca başarısızdır. Bu iki konu aşağıda ayrı açıklanır.

## Öneri 1: TypedDict tanımını düzeltin

Kaynak `press/press/doctype/deploy_candidate/cache_utils.py` dosyasının 13. satırıdır.
Python 3.13, anahtar argümanlarla `TypedDict` oluşturmayı kaldırdı.
Python 3.14 testi şu hatayı verdi:

```text
TypeError: TypedDict() got an unexpected keyword argument 'cwd'
```

`typing_extensions` kurmak çözmez. Press, `typing` içinden doğrudan içe aktarır.
Python standart kitaplığını gölgelemek de kabul edilen çözüm değildir.
Önerilen kaynak değişikliği şöyledir:

```diff
 CommandOutput = TypedDict(
     "CommandOutput",
-    cwd=str,
-    image_tag=str,
-    returncode=int,
-    output=str,
+    {"cwd": str, "image_tag": str, "returncode": int, "output": str},
 )
```

Alan adları, türleri ve zorunlulukları korunur.
Bakımcılar modülü Python 3.12 ve Python 3.14 üzerinde sınamalıdır.
Testler dört alanın türünü ve zorunlu olduğunu da doğrulamalıdır.

İkinci çağrı `press/press/doctype/deploy_candidate/test_deploy_candidate.py:39` satırındaki `AppInfo` tanımıdır.
Bakımcılar `app`, `source` ve `release` alanlarını da sözlük biçimine taşımalıdır.
Bu tanım `if typing.TYPE_CHECKING` bloğundadır. Normal çalışmada yürütülmez.
Bu yüzden ayrı bir çalışma zamanı hatası olarak sayılmadı.

[Press kaynak satırları](https://github.com/frappe/press/blob/v0.154.1/press/press/doctype/deploy_candidate/cache_utils.py#L11-L19)
[İkinci TypedDict tanımı](https://github.com/frappe/press/blob/v0.154.1/press/press/doctype/deploy_candidate/test_deploy_candidate.py#L29-L44)
[Python değişiklik kaydı](https://docs.python.org/3.13/library/typing.html#typing.TypedDict)

## Öneri 2: Telemetriyi Frappe sürümünden ayırın

Telemetri, ürün kullanım olaylarının ölçüm servislerine gönderilmesidir.
Kaynak `press/saas/doctype/product_trial_request/product_trial_request.py` dosyasının 16. satırıdır.
Bu satır Frappe'den `init_telemetry` işlevini ister.
Aynı dosyanın 115. ve 134. satırları bu işlevi çağırır.

Kurulu Frappe kaynağı `frappe/utils/telemetry/__init__.py` dosyasıdır.
Bu dosyada `init_telemetry` yoktur. İşlevler 19, 29, 34 ve 48. satırlardadır.
Bunlar `add_bootinfo`, `capture`, `capture_doc` ve `site_age` işlevleridir.
`posthog` paketini kurmak, kaldırılmış Frappe işlevini geri getirmez.
Test şu hatayı verdi:

```text
ImportError: cannot import name 'init_telemetry' from 'frappe.utils.telemetry'
```

Press zaten `press/utils/telemetry.py:14` içinde `init_telemetry` işlevini tanımlar.
Bu yardımcı `posthog_host` ve `posthog_project_id` ayarlarını okur.
Ayarlar varsa `frappe.local.posthog` istemcisini oluşturur. Ayarlar yoksa işlem yapmadan döner.
Bu yardımcı, ürün denemesi kodunun kullandığı yerel istemciyi sağlar.
Bakımcılar yeni yardımcı yazmadan önce mevcut işlevi yeniden kullanmalıdır.
Önerilen import değişikliği şöyledir:

```diff
-from frappe.utils.telemetry import init_telemetry
+from press.utils.telemetry import init_telemetry
```

Bakımcılar mevcut istemci yokluğu denetimlerini korumalıdır.
Olay alanları ve takma ad davranışı sahte PostHog istemcisiyle sınanmalıdır.
Hazır yardımcı, `posthog` paketini içe aktarır. Bu bağımlılık da çözülmelidir.
Frappe 16'nın `capture` işlevi aynı sözleşmeye sahip değildir.
Bu işlev doğrudan yerine konmamalıdır.

Bakımcılar Frappe 16 testlerini çalıştırmalıdır.
Telemetri kapalıyken modül açılmalı ve dış istek oluşmamalıdır.
Telemetri açıkken olay ve takma ad testleri geçmelidir.
22 Kasım 2026 Pazar günü bu öneri kaynak dosyalarına uygulanmamıştı. 23 Kasım 2026 Pazartesi günü üretim imajı öneriyi `0002-press-telemetry-helper.patch` yamasıyla uyguladı. Telemetri açıkken olay testleri yine denenmedi.

[Press kaynak dosyası](https://github.com/frappe/press/blob/v0.154.1/press/saas/doctype/product_trial_request/product_trial_request.py)
[Press içindeki hazır yardımcı](https://github.com/frappe/press/blob/v0.154.1/press/utils/telemetry.py#L14-L26)
[Frappe 16.56 kaynak dosyası](https://github.com/frappe/frappe/blob/v16.56.0/frappe/utils/telemetry/__init__.py)
[Aynı hatanın Press kaydı](https://github.com/frappe/press/issues/7534)

## Öneri 3: Çerez okuma yolunu Frappe 16'ya uyarlayın

Çerez, tarayıcının istekle gönderdiği küçük bir değerdir.
`press/api/cookies.py:7`, `frappe.oauth` içinden `get_cookie_dict_from_headers` işlevini alır.
Frappe 16.56.0 bu işlevi sunmaz. `press.api.cookies` içe aktarılırken hata verir.
Temel imajdaki 581 satırlık `frappe/oauth.py` dosyası ayrıca denetlendi.
Doğrudan import denemesi de aynı hatayla sonuçlandı.
Bu modüldeki `update_preferences` işlevi misafir çağrılarına açıktır.
Hata, işlev çağrılmadan önce oluşur:

```text
ImportError: cannot import name 'get_cookie_dict_from_headers' from 'frappe.oauth'
```

Bakımcılar çerez değerini Frappe 16'nın istek nesnesinden okumalıdır.
`frappe.local.request.cookies.get("cookie_perms")` yolu mevcut istek sözleşmesiyle değerlendirilmelidir.
Bu yol metin döndürür. Eski çağrıdaki `.value` erişimi ayrıca kaldırılmalıdır.
Bakımcılar boş, kodlanmış ve bozuk çerez değerlerini sınamalıdır.
Analitik izni değişince kayıt oluştuğunu da sınamalıdır.
Eksik işlevi paket kurarak geri getirmek mümkün değildir.
22 Kasım 2026 Pazar günü bu öneri uygulanmamıştı. 23 Kasım 2026 Pazartesi günü üretim imajı öneriyi `0003-request-cookies.patch` yamasıyla uyguladı. Değişen ve değişmeyen izin durumu imajda denendi. Bozuk çerez değeri denenmedi.

[Press çerez kaynağı](https://github.com/frappe/press/blob/v0.154.1/press/api/cookies.py#L1-L33)
[Frappe OAuth kaynağı](https://github.com/frappe/frappe/blob/v16.56.0/frappe/oauth.py)

## Öneri 4: Tam bağımlılık çözümünü doğrulayın

`Dockerfile.unpatched`, Press paketini `--no-deps` seçeneğiyle kurar.
Bu seçim, hataları ayrı incelemek içindir. Tam kurulum başarısı değildir.
`pyproject.toml:25-60` içindeki sürüm şartları ayrıca karşılanmalıdır.
Örneğin Press Ansible `3.4.0` ister. Deneme adayı Ansible `14.0.0` kullandı. Üretim imajı `14.6.0` kullanır (karar 0018).
Press Stripe `~=2.56.0` ister. Aday Stripe `3.1.0` kullanır.
Telegram raw paketi de `python-telegram-bot==13.15` şartını paket adı bakımından karşılamaz.
Eksik paketler ve diğer sürüm çelişkileri de bağımlılık denetiminde görünür.
Genişletilen denetim 177 pakette 32 uyumsuzluk buldu.
Bu sayı eksik paketleri ve sürüm çelişkilerini birlikte içerir.
Örneğin `requests<2.32` şartı, kurulu `2.33.1` sürümüyle çelişir.
`wrapt~=1.15.0` şartı da kurulu `1.17.3` sürümüyle çelişir.

Bakımcılar bağımlılık şartlarını Python 3.14 ve Frappe 16'ya uyarlamalıdır.
Tam kilit, bütün doğrudan ve dolaylı paket sürümlerini sabitlemelidir.
Temiz kurulum, kilitli paketlerle yeniden üretilebilmelidir.
`uv pip check --python /home/frappe/frappe-bench/env/bin/python` başarılı olmalıdır.
Bu denetim geçmeden yalnız modül açılışı tam uyum kanıtı olmaz.

[Press bağımlılık bildirimi](https://github.com/frappe/press/blob/v0.154.1/pyproject.toml#L24-L61)

## Öneri 5: Telegram paketini isteğe bağlı yapın

Bu öneri 23 Kasım 2026 Pazartesi günü üretim imajı işinde eklendi.
Press, `python-telegram-bot==13.15` paketini ister.
Bu paket Python 3.12 ve sonrasında içe aktarılamaz.
Paketin içindeki urllib3 kopyası eski `six.moves` yolunu kullanır.
Paketin yedek yolu `urllib3.contrib.appengine` modülünü ister. urllib3 2 bu modülü kaldırdı.
`press/press/doctype/press_settings/press_settings.py` dosyası Telegram yardımcısını açılışta içe aktarır.
Bu yüzden Press Settings belge türü de açılmaz.

Üretim imajındaki `0004-optional-telegram.patch` yaması içe aktarmayı korumaya alır.
Paket yoksa Press yine açılır. Telegram mesajı gönderilmez ve hata kaydı yazılır.
Bakımcılar uzun vadede bakımı süren bir Telegram istemcisine geçmelidir.
Örneğin Telegram Bot API'si doğrudan HTTP ile çağrılabilir.

## Geçici yama kaydı

[Yama kaydı](../dev/press/patch-registry.json) geliştirme ve üretim yamalarını listeler.
Her kayıtta yamanın sahibi, testi ve kaldırma koşulu bulunur.
`upstream` alanı Press'in asıl geliştirici deposundaki ilgili kaydı gösterir.
Ekip öneriyi göndermediyse alan bu belgenin ilgili bölümünü gösterir.
Ekip her Press yükseltmesinde ilgili testi yamasız imajda çalıştırır. Test geçerse ekip yamayı kaldırır.

Geliştirme betiğinde her yama için bir `patch-id` satırı açın.
Aynı komut birden çok yamayı uygulayabilir. Her yama ayrı kayıt alır.
Üretim yamaları dosya adlarıyla kayda girer.
Geliştirmede geçici bağımlılık seçimi tek dosya olarak kayda girer.
Test, yeni üretim yamalarını ve yeni `patch-id` satırlarını kayıtla karşılaştırır.
Test, işaretsiz betik değişikliğini dosyanın SHA-256 özetiyle yakalar.
Özet, dosya değişince değişen bir değerdir.
Betiği veya geçici bağımlılık dosyasını değiştirirseniz kayıtları gözden geçirin.
Ardından dosyanın özetini güncelleyin.

Kayıt denetimini depo kökünde çalıştırın.

```sh
~/.local/bin/python3.14 -B -m unittest discover -s backend/dev/tests -p test_press_patch_registry.py
```

Bu denetim yerel dosyaları okur. Press imajını çalıştırmaz.

## Üretim imajındaki karşılıklar

Öneriler üretim imajında yama dizisi olarak uygulandı (O-52).
Yamalar `backend/deploy/images/press-patches/` klasöründedir.
Öneri 4'ün bağımlılık kararları `0005-dependency-pins.patch` yamasının başında yazılıdır.
Tam bağımlılık denetimi bu imajda iki bilinen satırla geçer.
Ayrıntı [Press imajı belgesindedir](dagitim/press-imaji.md).

## Kabul sonucu

İlk testler paket değişikliğinden önce çalıştırıldı.
`TypedDict` testi ve telemetri testi beklenen hatalarla düştü.
Aynı denemede Press kaynak bütünlüğü testi geçti.

İlk v0.154.1 adayında 10 kabul testi çalıştı. Altı test geçti. Dört test başarısız oldu.
Dört başarısız test, aynı iki kaynak engelini farklı düzeylerde doğruladı.
Bu sayı, inceleme sonrası genişletilen testlerin sonucu değildir.

22 Kasım 2026 Pazar günü inceleme sonrası kabul testleri tekrar çalıştırıldı.
Bu devam denemesi başlangıçtaki `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` kaynağına sabitlendi.
Genişletilen 13 testin yedisi geçti. Altısı başarısız oldu.
`TypedDict` ve telemetri engelleri ayrı ayrı ikişer testi düşürdü.
Çerez import'u bir testi düşürdü. Tam bağımlılık denetimi de bir testi düşürdü.
Testler hataları beklenen başarı olarak işaretlemez. Komut 1 koduyla çıkar.
Tablo bu genişletilen denemenin sonucunu gösterir.

| Denetim | Sonuç |
| --- | --- |
| Sabit Press commit kodu | `pass` |
| Press klasöründe boş `git diff HEAD` | `pass` |
| Press klasöründe beklenmeyen dosya olmaması | `pass` |
| Geliştirme işareti, yama betiği ve paket yama izlerinin bulunmaması | `pass` |
| Python 3.14 ve Frappe 16 | `pass` |
| Standart modüller, Telegram ve Stripe import'u | `pass` |
| `press.runner` import'u ve yerel Ansible görevi | `pass` |
| `cache_utils` import'u ve ayrı `TypedDict` tanımı | `fail` |
| Ürün denemesi modülü ve ayrı telemetri import'u | `fail` |
| Çerez tercihi modülünün içe aktarılması | `fail` |
| Tam bağımlılık uyumu, `uv pip check` | `fail` |
| Site kurulumu ve HTTP açılışı | `not_run` |
| Press masasının tarayıcıda yüklenmesi | `not_run` |
| Ödeme, Telegram gönderimi ve gerçek sunucu kurulumu | `not_run` |

Paket izi denetimi `.orig` yedeklerini ve `press-local:` izlerini arar.
Bu iz taraması, paket dosyalarının tam bütünlüğünü kanıtlamaz.
Deneme imajının tam bağımlılık denetimi de başarısızdır.
Eksik paketler ve Press sürüm aralıklarıyla çelişen adaylar vardır.
Site denemesinin ön koşulu olan modül açılışı başarısızdır.
Bu nedenle site ve masa başarısı iddia edilmez.
Tarayıcı çalıştırılmadı. Firefox kullanılmadı. Zamanlanmış iş kurulmadı.

## O-18 kapanış koşulu

Üç kaynak engeli ve tam bağımlılık uyumsuzluğu çözülmeden yamasız yol bulunamadı.
O-18 ve ilgili borç satırı açık kaldı.
Yamasız adayın çalışması ya da düzeltmenin Press'e kabulü mevcut kapanış koşuludur.
Kabul edilen yeni kaynak, bütünlük ve bağımlılık testlerinden geçmelidir.
Site kurulumu ve Press masası da ayrıca doğrulanmalıdır.
Mevcut geliştirme yaması ancak bu sonuçtan sonra kaldırılabilir.

Görev C, bu deneme imajını çalışan Press sitesi olarak kullanmamalıdır.
Sonraki sürümler de [ayrı taramada](press-python314-version-audit.md) incelendi.
Yamasız yol bulunamadığı için araştırma kolu kapatıldı.
Deneme imajının etiketi iş bitince silinir.
Çalıştırma ve kapatma komutları [deneme rehberindedir](../dev/press/unpatched-runtime.md).

Gerçek okurla denenmedi.
