# Press RPC istek sınırı kararı

Press deneme ortamı Frappe v16.50.0 ve Press v0.154.1 kullanır.
Frappe 16.50, istek sınırı sayacını `frappe.form_dict.cmd` alanından adlandırır.
API v2 bu alanı doldurmaz. Press, çıkış retleri için geçici bir sayaç adı kullanır.

Frappe 16.56.0 sayacı işlev adından üretir. Bu sürümde Press geçici adı kullanmaz.
Yerel test, 16.56 dalında `cmd` alanının korunduğunu doğrular.
Canlı yerel test, 16.50 üzerinde v1 ve v2 çıkış retlerini aynı sayaçta toplar.
Frappe 16.56 üzerinde çalışan bir Press kurulumu bu turda denenmedi.

[Frappe 16.56.0 kaynak kodu](https://github.com/frappe/frappe/blob/v16.56.0/frappe/rate_limiter.py)
