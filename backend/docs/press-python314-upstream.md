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
Aday paketlerin bakım, lisans ve geri dönüş kaydı [karar notundadır](decisions/press-python314-probe.md).

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

[Press kaynak satırları](https://github.com/frappe/press/blob/v0.154.1/press/press/doctype/deploy_candidate/cache_utils.py#L11-L19)
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

Bakımcılar isteğe bağlı eski telemetriyi modül açılışından ayırmalıdır.
Önerilen değişiklik şu adımlardan oluşur:

1. Bakımcılar üst düzey `init_telemetry` import'unu kaldırır.
2. Bakımcılar eski telemetri desteğini tek bir yardımcı işlevde denetler.
3. Gerekli Frappe işlevi yoksa yardımcı işlev `None` döndürür.
4. Olay ve takma ad yolları, istemci yoksa işlemi bitirir.
5. Eski Frappe desteği varsa olay alanları ve takma ad davranışı korunur.

Yardımcı işlev yalnız eksik yeteneği ele almalıdır.
Genel `ImportError` yakalamak, başka bozuk bağımlılıkları gizleyebilir.
Frappe 16'nın `capture` işlevi aynı sözleşmeye sahip değildir.
Bu işlev doğrudan yerine konmamalıdır.

Bakımcılar Frappe 15 ve Frappe 16 testlerini ayrı çalıştırmalıdır.
Telemetri kapalıyken modül açılmalı ve dış istek oluşmamalıdır.
Telemetri açık eski ortamda olay ve takma ad testleri geçmelidir.
Bu öneri kaynak dosyalarına uygulanmadı. Telemetri davranışı henüz değiştirilmedi.

[Press kaynak dosyası](https://github.com/frappe/press/blob/v0.154.1/press/saas/doctype/product_trial_request/product_trial_request.py)
[Frappe 16.56 kaynak dosyası](https://github.com/frappe/frappe/blob/v16.56.0/frappe/utils/telemetry/__init__.py)
[Aynı hatanın Press kaydı](https://github.com/frappe/press/issues/7534)

## Kabul sonucu

İlk testler paket değişikliğinden önce çalıştırıldı.
`TypedDict` testi ve telemetri testi beklenen hatalarla düştü.
Aynı denemede Press kaynak bütünlüğü testi geçti.

Son adayda 10 kabul testi çalıştı. Altı test geçti. Dört test başarısız oldu.
Dört başarısız test, aynı iki kaynak engelini farklı düzeylerde doğruladı.
Testler hataları beklenen başarı olarak işaretlemez. Komut 1 koduyla çıkar.

| Denetim | Sonuç |
| --- | --- |
| Sabit Press commit kodu | `pass` |
| Press klasöründe boş `git diff HEAD` | `pass` |
| Press klasöründe beklenmeyen dosya olmaması | `pass` |
| Python 3.14 ve Frappe 16 | `pass` |
| Standart modüller, Telegram ve Stripe import'u | `pass` |
| `press.runner` import'u ve yerel Ansible görevi | `pass` |
| `cache_utils` import'u ve ayrı `TypedDict` tanımı | `fail` |
| Ürün denemesi modülü ve ayrı telemetri import'u | `fail` |
| Tam bağımlılık uyumu, `uv pip check` | `fail` |
| Site kurulumu ve HTTP açılışı | `not_run` |
| Press masasının tarayıcıda yüklenmesi | `not_run` |
| Ödeme, Telegram gönderimi ve gerçek sunucu kurulumu | `not_run` |

Deneme imajının tam bağımlılık denetimi de başarısızdır.
Eksik paketler ve Press sürüm aralıklarıyla çelişen adaylar vardır.
Site denemesinin ön koşulu olan modül açılışı başarısızdır.
Bu nedenle site ve masa başarısı iddia edilmez.
Tarayıcı çalıştırılmadı. Firefox kullanılmadı. Zamanlanmış iş kurulmadı.

## O-18 kapanış koşulu

İki kaynak düzeltmesi kabul edilmeden mevcut etiketle yamasız yol bulunamadı.
O-18 ve ilgili borç satırı açık kaldı.
Yamasız adayın çalışması ya da düzeltmenin Press'e kabulü mevcut kapanış koşuludur.
Kabul edilen yeni kaynak, kurulum ve masa testleriyle ayrıca doğrulanmalıdır.
Mevcut geliştirme yaması ancak bu sonuçtan sonra kaldırılabilir.

Görev C, bu deneme imajını çalışan Press sitesi olarak kullanmamalıdır.
İmaj, aynı iki engeli yeniden göstermek için bırakıldı.
Çalıştırma ve kapatma komutları [deneme rehberindedir](../dev/press/unpatched-runtime.md).

Gerçek okurla denenmedi.
