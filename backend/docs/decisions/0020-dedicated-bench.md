# Ayrı bench kararı

Karar tarihi 24 Kasım 2026 Salı günüdür. Kararı orkestratör verdi. Bu karar G-40 kapsamındadır.

Bench, Frappe sitelerini çalıştıran kurulumdur. Kiracılar normalde ortak bench üzerinde çalışır.

## Kural

Ayrı bench yalnız iki koşulda verilir:

1. Kiracı Kurumsal plandadır.
2. Kiracının özel uygulaması vardır.

Koşullardan biri yeterlidir. Başka bir koşulda kiracı ortak bench üzerinde kalır.

Kuralın makine okur biçimi aşağıdadır. Koşulu değiştirmek için yalnız bu bloğu değiştirin. Kuralı başka dosyaya kopyalamayın. `backend/dev/tests/test_dedicated_bench_decision.py` testi bunu denetler.

```json
{"dedicated_bench_when_any": [{"plan": "Kurumsal"}, {"has_custom_app": true}]}
```

## Kapsam dışı

- Ayrı bench planının fiyatı bu kararda yoktur.
- Kiracıyı ayrı bench üzerine taşıyan kod henüz yazılmadı.
- Ayrı bench üzerinde de geliştirme araçları üretimde kapalı kalır.
