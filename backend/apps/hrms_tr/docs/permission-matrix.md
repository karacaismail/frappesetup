# HRMS TR yetki tablosu (G-104)

Bu tablo izin talebi kayıtları içindir. Kayıt türünün adı “Leave Application” şeklindedir.

Tablonun makine biçimi `hrms_tr/tests/test_permission_matrix.py` dosyasındadır. Tabloyu değiştirirseniz o dosyayı da değiştirin.

## Roller

Uygulama üç rol profili kurar:

- “HRT Employee” çalışan profilidir.
- “HRT Manager” yönetici profilidir. Bu profilde çalışan rolü de vardır.
- “HRT Admin” insan kaynakları yöneticisi profilidir. Bu profilde çalışan rolü de vardır.

Bu rollerin hiçbiri masaüstü erişimi vermez. Kullanıcılar web sitesi kullanıcısı olarak kalır.

## Kim hangi kaydı görür

Yöneticinin ekibi çalışan kaydındaki “reports_to” alanından çıkar. Ekibe dolaylı bağlı kişiler de girer.

| Profil | Gördüğü izin talepleri |
| --- | --- |
| HRT Employee | Yalnız kendi talepleri |
| HRT Manager | Kendi talepleri ve kendisine bağlı herkesin talepleri |
| HRT Admin | Sitedeki bütün talepler |
| HRMS TR rolü yok | Hiçbir talep |

## Kim ne yapabilir

Tablo taslak durumundaki bir talep içindir.

| Profil | Kayıt | Okur | Değiştirir | Onaylar | İptal eder |
| --- | --- | --- | --- | --- | --- |
| HRT Employee | Kendi talebi | Evet | Evet | Hayır | Hayır |
| HRT Employee | Başkasının talebi | Hayır | Hayır | Hayır | Hayır |
| HRT Manager | Ekibindeki talep | Evet | Evet | Evet | Hayır |
| HRT Manager | Başka ekipteki talep | Hayır | Hayır | Hayır | Hayır |
| HRT Admin | Her talep | Evet | Evet | Evet | Evet |

Yönetici kendi talebini okur ve değiştirir. Kendi talebini onaylayamaz. Bu kural `hrms_tr/leave.py` dosyasındadır.

Üç profil de yeni talep açabilir. HRMS TR rolü olmayan kişi talep açamaz.

## Hassas alanlar

Alanlar düzeylere ayrılır. Düzey, alanı kimin okuyacağını belirler.

- 0. düzey talebin genel alanlarıdır.
- 1. düzeyde “status” alanı vardır. Bu alan talebin onay durumudur.
- 2. düzeyde “leave_balance” alanı vardır. Bu alan izin bakiyesidir.

| Profil | Okuduğu düzeyler | Yazdığı düzeyler |
| --- | --- | --- |
| HRT Employee | 0, 1 | 0 |
| HRT Manager | 0, 1, 2 | 0, 1 |
| HRT Admin | 0, 1, 2 | 0, 1 |

Herkes 1. düzeyi okur. Bu izin HRMS'in standart “All” satırından gelir. Frappe bu satırı ilk özel izin satırıyla birlikte kopyalar.

Çalışan kendi talebinin onay durumunu görür. Çalışan bu durumu değiştiremez. Bu yüzden kendi talebini onaylayamaz. Çalışan izin bakiyesini de göremez.

## Kiracı yöneticisi

Kiracı yöneticisi erişim kurallarını ve alan düzeylerini değiştirebilir (G-98). Değişiklikten sonra bu tablo o sitede geçerli olmaz.

## Testler

İki test grubu tabloyu korur.

1. `MatrixFixtureTest` tabloyu uygulamanın kurulum dosyalarıyla karşılaştırır. Bu test Frappe olmadan da çalışır.
2. `PermissionMatrixIntegrationTest` her kişiyle oturum açar. Frappe'nin verdiği cevabı tabloyla karşılaştırır. Bu test için HRMS TR kurulu bir test sitesi gerekir.

Test sitesinde şu komutu çalıştırın:

```sh
PANE_PORT=<port> backend/dev/bin/test hrms_tr --module hrms_tr.tests.test_permission_matrix
```
