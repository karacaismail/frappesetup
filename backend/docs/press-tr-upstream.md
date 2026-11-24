# Press için press_tr düzeltme önerileri

Bu belge Press bakımcılarına gidecek öneri metnidir. Öneri henüz gönderilmedi.

Öneriyi Press'e göndermek dışarıya yazı göndermektir. Bu işi bir insan onaylamalıdır. Gönderen kişi Press bağlantısını yama kaydına yazar. Sonra kayıttaki `upstream_status` değerini `sent` yapar.

Üç sorun bugün `press_tr` içinde kapanır. Kayıt `dev/press/patch-registry.json` dosyasının `press_tr_fixes` bölümündedir.

## Kaynak

| Bilgi | Değer |
| --- | --- |
| Press etiketi | `v0.154.1` |
| Press commit kodu | `7a4384d5eec9f0f0dce4124e9dd48b106e51222f` |
| Agent commit kodu | `1956afb39613aafc88d821a9b1762ae397d4f588` |

## Öneri 1: Anahtar biçim denetimini düzeltin

`Site.validate_encryption_key` işlevi `press/press/doctype/site/site.py` dosyasının 2782. satırındadır. İşlevin ilk koşulu şudur:

```python
if key != "encryption_key" or key != "backup_encryption_key":
	return
```

Bu koşul her anahtar için doğrudur. Bu yüzden denetim hiç çalışmaz. Bozuk anahtar kayda girer.

Önerilen düzeltme `or` yerine `and` kullanmaktır:

```python
if key != "encryption_key" and key != "backup_encryption_key":
	return
```

Öneriye bir test eklenmelidir. Test bozuk `backup_encryption_key` değerinin reddedildiğini göstermelidir.

`press_tr` bugün aynı denetimi `press_tr.backup_keys.validate_site_keys` ile yapar. Press düzeltmeyi yayımlayınca bu ek kaldırılır.

## Öneri 2: Kurulum sihirbazı işini çağırın

`press/agent.py` dosyasında `Agent.complete_setup_wizard` işlevi vardır. İşlev Agent'a "Complete Setup Wizard" işini gönderir. Agent bu işte `frappe.desk.page.setup_wizard.setup_wizard.setup_complete` komutunu çalıştırır.

Press'te bu işlevi çağıran kod yoktur. Yeni sitenin sahibi kurulum sihirbazını elle doldurur.

Önerilen düzeltme şudur:

1. Site etkin olunca Press bu işi bir kez başlatır.
2. İş verisini Press site sahibinin kayıtlarından alır.
3. Deneme siteleri ve önceden hazırlanan bekleme siteleri bu akışa girmez. Press bu sitelerde sihirbazı zaten doldurur.

İş verisinde altı alan vardır. Alanlar `language`, `country`, `timezone`, `currency`, `full_name` ve `email` alanlarıdır. Biri boşsa iş başlamaz.

`press_tr` bugün bu işi `press_tr.setup_wizard.start_setup_wizard` ile başlatır. Press düzeltmeyi yayımlayınca bu ek kaldırılır.

## Öneri 3: Frappe Cloud hazır kayıtlarını ayırın

Press `hooks.py` dosyasındaki `fixtures` listesi Frappe Cloud kayıtlarını yükler. Bu listede `Site Plan`, `Team Tier`, `Cloud Region` ve `Server Plan` vardır. `site_plan.json` dosyasında 686 plan vardır. Bu planların 132'si açıktır.

Kendi Press kurulumunu yapan kişi bu kayıtları istemez. Kayıt silinirse sonraki güncellemede geri gelir. Yerel değişiklik de yeni `modified` damgalı kayıtla ezilir.

Önerilen düzeltme şudur:

1. Frappe Cloud kayıtları ayrı bir ayara bağlanır.
2. Ayar kapalıysa Press bu kayıtları yüklemez.
3. `Cloud Region` kaydına açma ve kapatma alanı eklenir.

`press_tr` bugün kayıtları her güncellemeden sonra kapatır. Bu iş `press_tr.fixture_cleanup.disable_cloud_defaults` ile yapılır. Press düzeltmeyi yayımlayınca bu ek kaldırılır.
