---
title: "AI · Press işlemleri yetkinlik matrisi"
nav: "Press yetkinliği"
order: 24
---

Soru şudur: [Press kılavuzundaki](https://karacaismail.github.io/pressguide/) işlemleri mevcut skill, MCP ve ajan depoları yapabilir mi? Kılavuz sekiz ana adım ve ek yardımcı işlemlerden oluşur (Release Group, sunucu, app ekleme, App Source, Deploy Candidate, build/deploy, site oluşturma, hata teşhisi). Karşılaştırma üç kaynağa dayanır: dokuz topluluk MCP'si, resmi `frappe/press` içindeki Press MCP'si (`press/mcp`) ve `huf` ajanı. Tarih: 8 Ekim 2026; yüzeysel klonlar okundu, hiçbir araç çalıştırılmadı.

## Okuma anahtarı

- **Tam**: işlem için ayrılmış araç var.
- **Kısmi**: dolaylı yol var (genel istek aracı, ham API çağrısı) veya yalnız bazı alt adımlar.
- **Yok**: araç bulunamadı.
- **İnsan**: kılavuz bilinçli olarak insan onayı veya altyapı sahibi ister.

## Matris

| # | Press işlemi | Press API'de karşılığı | Press MCP | Topluluk MCP | huf ajanı | Skill |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Release Group oluştur (Team, Version) | `press.api.bench.new` | Yok | Yok | Kısmi (`bench.new`, bench olarak) | Yok |
| 2 | Hazır app sunucusunu bağla | `Release Group.add_server` | Yok | Yok | Yok | Yok |
| 3 | Uygulamaları sırayla ekle | `press.api.bench.add_app(s)` | Yok | Yok | Kısmi (`add_app`) | Yok |
| 4 | App Source formu (repo, branch, Frappe kutusu) | `press.api.app.new`, App Source DocType | Yok | Yok | Yok | Yok |
| 5 | Deploy Candidate oluştur | `Release Group.create_deploy_candidate` | Yok | Yok | Yok | Yok |
| 6 | Build başlat, sonra ayrı deploy | `Deploy Candidate Build.build/deploy`, `bench.deploy` | Yok | Yok | Yok | Yok |
| 7 | Site oluştur (plan, bölge, yasal kutu) | `press.api.site.new` | Yok | Kısmi (skaslam1407 `fc_request`) | Kısmi (`site.new`) | Kısmi (genel) |
| 8 | Build hatasını izle (Build Steps, Agent Job) | DocType okuma | **Tam** (`get_document`, `get_agent_jobs_for_document`) | Yok | Kısmi | Yok |
| 9 | Disk, Nginx, Redis, log teşhisi | sunucu komutları | **Tam** (`get_disk_usage_in_*`, `tail_*`, `grep_*`, `get_server_storage_breakdown`) | Yok | Yok | Yok |
| 10 | Telemetri, yavaşlık, hata eğilimi | Prometheus/Elasticsearch | **Tam** (~30 araç) | Yok | Yok | Yok |
| 11 | Güvenli temizlik (`docker builder prune`) | SSH | İnsan (yalnız supervisor/systemctl komutları, `confirm`) | Yok | Yok | Yok |
| 12 | Servis yeniden başlatma | `restart_bench`, `reboot_in_server` | Tam (`confirm` ister) | Yok | Kısmi | Yok |
| 13 | DNS kaydı (GoDaddy) | Press dışı | İnsan | Yok | Yok | Yok |
| 14 | Yasal kutu ve ödeme onayı | Dashboard formu | İnsan | İnsan | İnsan | İnsan |

## Okumalar

1. **Teşhis (satır 8–10) hazır ve güçlüdür.** Press MCP kılavuzdaki "Build Steps → ilk Failure → Output", "Agent Job" ve "`df -h`, Nginx error.log, `docker system df`" okumalarının büyük bölümünü karşılar. Gizli değerler maskelenir (`guardrails/redaction.py`) ve yazma eylemleri `confirm=True` ister. Yalnız System Manager ve System User erişir.
2. **Kurulum ve dağıtım (satır 1–7) için hazır, onaylı ve denetli hiçbir araç yoktur.** En yakın şey `huf`'un ham `press.api.*` çağrılarıdır; bunlar Release Group, App Source, Deploy Candidate ve build/deploy ayrımını modellemez, yıkıcı araçlarda onay bayrağı bulunamadı ve Press'in kararlı olmayan iç API'sine bağlıdır.
3. **Kılavuzun asıl değeri sıralama kuralıdır**, hiçbir depoda yoktur: "build Success olmadan deploy yok", "form gönderildiyse sonuç görülmeden tekrar gönderme", "Required app not found önce App/Source bağımlılığına bakılır", "Pending satırlarını hata sayma", "boş filtreyi 'iş yok' diye yorumlama". Bunlar skill olarak yazılmalıdır.
4. **Sınır işleri insanda kalır** (satır 11, 13, 14): servis yeniden başlatma ve disk temizliği (Hüseyin Cengiz), GoDaddy DNS (Asistan Hüseyin uygular, Hüseyin Cengiz doğrular), bölgesel yasal kutunun kabulü ve ödeme. Bir ajan bunları kendi başına yapmamalı; "hazırla, önizle, onay iste" ile sınırlanmalıdır.
5. **Mevcut depolar Frappe izinleri açısından uygun değildir.** Press işlemleri Frappe Cloud/Press'in Team ve rol modeline göredir; harici proxy'lerdeki paylaşılan API anahtarı bu modeli aşar. Çözüm, kullanıcı başına Press bearer ile çalışan bir MCP'dir (mimaride `press_tr.mcp.handler`, G-28).

## Sonuç

| Alan | Durum |
| --- | --- |
| Press'i izlemek ve hata aramak | **Hazır** (Press MCP) — bizim ek işimiz: kılavuzdaki teşhis sırasını skill yapmak |
| Press'te bench/site/app kurmak ve dağıtmak | **Boşluk** — yeni MCP aracı + skill gerekir |
| Altyapı sahibi işleri (disk, DNS, yasal onay) | **İnsan kapısı** — ajan yalnız hazırlar |

Kapatma planı: [Geliştirme planı](../ai-gelistirme/).
