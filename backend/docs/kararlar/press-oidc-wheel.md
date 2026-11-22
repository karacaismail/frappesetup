# T-2. Press kimlik kitaplığının kurulumu

Press, Keycloak belirteçlerini ortak `oidc_verify` kitaplığıyla doğrular.
Kitaplık, onaylı kaynak commit'inden Python kurulum paketi olarak üretilir.

Üretim kurulumunda paketi güvenilir sürüm paketinden alın.
Doğrulama özetini imzalı sürüm bildiriminden okuyun.
`install_runtime_oidc.sh` paketi yalnız verilen klasörde arar.
Betik özeti karşılaştırır ve genel paket deposuna bağlanmaz.
Press TR uygulaması kurulumunda `--no-deps` kullanın.
Gerekli diğer paketleri onaylı kurulum ortamı sağlar.

`runtime-check` hedefi kitaplığı taşıyan denetim imajıdır.
Bu hedef Press uygulamasını içermez ve üretime dağıtılmaz.
Üretim imajı, sabitlenmiş temiz Press kaynağını kullanır.
Kaynakta yerel uyum yamasının işaretini arayan test dağıtımdan önce çalışır.

Önceki sürüme dönmek gerekirse o sürümün paketini ve doğrulama özetini kullanın.
