# 0010. Yapay zekâ uygunluk kapısı

Proje kaydındaki D-9, arka uç işlemlerinin yapay zekâyla yönetilebilmesini ister.
O-13, model adlarını kayıtta tutar ve sağlayıcı kitaplıklarını yasaklar.

Depo kökünde `backend/dev/bin/ai-readiness` komutunu çalıştırın.
Arka uç kodunu tararken `python3` komutu Python 3.14'ü çalıştırmalı.
Komut her bulguda dosyayı ve satırı gösterir.
Bir bulgu varsa komut 1, bulgu yoksa 0 döndürür.
Başka bir arka uç klasörünü taramak için `--root` kullanın.
Programın okuyacağı çıktı için `--json` ekleyin.

## Kapsam

- Kapı uygulamalardaki DocType tanımlarını okur. DocType, bir kayıt türünün tanımıdır.
- Kapı kayıt türünün ve veri alanlarının açıklamalarını arar.
  Bölüm, sütun ve sekme gibi yerleşim alanlarını atlar.
- Kapı dışarıya açılan Python işlevlerini OpenAPI sözleşmesiyle iki yönde karşılaştırır.
  OpenAPI, bir ağ işleminin adresini ve nasıl çağrıldığını tarif eder.
  Kapı Frappe'nin kendi uçlarını, kayıt adreslerini ve ayrı servis adreslerini atlar.
  Böylece örneğin kimlik eşitleme servisinin sağlık adresi yanlış bulgu üretmez.
- Kapı Python'da bilinen sağlayıcı kitaplıklarının içe aktarımını arar.
  Kapı ayrıca bilinen model adlarını metin değerlerinde arar.
  Kapı model adı denetiminde test dosyalarını atlar.
- Kapı `hooks.py` dosyasında zamanlanmış iş kaydını arar.
- Kapı ham SQL çağrılarını yapay zekâ modülünde ve kayıtlı araç işlevlerinde arar.
  Ham SQL, veritabanına doğrudan gönderilen sorgudur.
  Kapı sabit araç bildirimlerindeki iş ve önizleme işlevlerine de bakar.
  Kapı araç olarak bildirilmemiş test kodundaki sorguları dışarıda bırakır.
  Örneğin testte oturumu süresi geçmiş duruma getiren sorguyu araç saymaz.

Kapı uygulama kodunu çalıştırmaz ve dosyaları değiştirmez.
Kapı düz YAML eşlemelerini ve JSON biçimindeki OpenAPI dosyalarını okur.
İşlem tanımında bağlantı veya kısaltılmış eşleme görürse bulgu yazar.
Kapı çalışırken kurulan içe aktarımları ve araç çağrı zincirlerini çözmez.
Yeni model aileleri çıktığında model adı kalıplarını gözden geçirin.

## Yasaklı ad

D-13 için kapı bütün izlenen dosyaları ve yolları tarar.
İzlenen dosya, Git'in listesine alınmış dosyadır.
Bu denetim depo köküne göre dosya yolu verir.
Diğer denetimler arka uç klasörüne göre dosya yolu verir.

Kapı yalnız SHA-256 özetini saklar. Özet, metinden hesaplanan bir sayı dizisidir.
Kapı metni küçük harfe çevirir ve harf ile rakam dışındaki işaretleri atar.
Kapı kalan metindeki her altı karakterin özetini karşılaştırır.
Yolda eşleşme varsa kapı, yol yerine o yola ait kısa bir kod gösterir.
Kapı eşleşen metni çıktıya yazmaz.
