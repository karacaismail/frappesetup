# Agent yama dizisi

Bu klasör Frappe Agent için yazılan yamaları tutar. Agent, Press'in sunucularda iş yapan parçasıdır. Agent yedekleri dış depolama alanına da yükler.

Yamalar şu Agent sürümüne göre yazıldı: `1956afb39613aafc88d821a9b1762ae397d4f588`. Kaynak `https://github.com/frappe/agent` deposudur.

## Yamalar

| Yama | Amacı | Gereksinim |
| --- | --- | --- |
| `0001-offsite-s3-endpoint.patch` | Agent'ın yedeği Hetzner Object Storage adresine yüklemesini sağlar | G-5 |

Press, Agent'a depolama adresini `ENDPOINT_URL` adıyla gönderir. Yamasız Agent bu adresi okumaz. Yedek bu yüzden AWS'e gider. Yama `agent/offsite_s3.py` dosyasını ekler. Agent'ın dış depoya yaptığı bütün yüklemeler adresi bu dosyadan alır. Bu yüklemeler dört türdür: site yedeği, binlog, denetim kaydı ve anlık görüntüden kurtarma. Anlık görüntüden kurtarma yüklemesi `agent/snapshot_recovery.py` dosyasındadır. Adres yoksa Agent eskisi gibi çalışır.

## Nasıl denenir

Test `backend/deploy/tests/test_agent_patches.py` dosyasındadır. Test, yamanın eklediği yardımcı kodu Agent kaynağı olmadan dener.

Yamanın Agent kaynağına uyduğunu denemek için `AGENT_SOURCE` değişkenini verin. Değişken, yukarıdaki sürümdeki bir Agent kopyasını göstermelidir. Bu kipte test, kurtarma yüklemesini sahte bir depolama istemcisiyle de çalıştırır:

```bash
AGENT_SOURCE=<Agent kopyası> python3 -I -m unittest discover -s backend/deploy/tests -p test_agent_patches.py
```

## Henüz yapılmayanlar

- Bu depoda Agent imajı yoktur. Yamayı sunucudaki Agent'a Hüseyin Cengiz uygular.
- Press'te `offsite_backups_provider` alanında yalnız "AWS S3" seçeneği vardır. Yama bu yüzden adresi sağlayıcı adından bağımsız okur.
- Press yedeği indirirken kendi bağlantısını kurar. Bu bağlantının Hetzner adresiyle çalıştığı deneme ortamında doğrulanmalıdır.

## Ne zaman kaldırılır

Agent bu düzeltmeyi kendi deposunda yayımlarsa yama silinir. Sonra Agent sürümü yeni sürüme taşınır.

## Lisans

Agent, AGPL-3.0 lisanslıdır. Bu yama Agent kodundan türer. Bu yüzden yama da AGPL-3.0 lisanslıdır.
