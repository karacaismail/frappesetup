<!-- frappesetup notu: bu blok kaynak yönergeye eklendi. Gövde aşağıda aynen durur. -->

> **Odak istisnası (frappesetup notu, 27 Kasım 2026 Cuma günü).**
>
> - Bu dosya müşterinin köşe yönergesidir. Kaynak dosya `rules ai/radius.md` dosyasıdır. Gövde aynen kopyalandı.
> - Gövdenin 72. ve 144. satırı "özel focus ring" anar. Bu iki satırdaki odak halkası kısmı uygulanmaz.
> - Çevreleyen odak halkası müşterinin kalıcı kuralıyla yasaktır. Odak göstergesi o kurala uyar.
> - `--r-ring` değeri yalnız Segmented ve Radio.Group sarmalayıcısında kullanılır.
> - Satır numaraları kaynak dosyanın satırlarıdır. Bu dosyada aynı satırlar 85. ve 157. satırdır.
> - Karar kaydı `KARARLAR.md` dosyasındaki Karar 43'tür.

---

# Radius Uyum Yönergesi
**Eş merkezli köşe sistemi · Ant Design X · GenUI-first · Çapa: 5px**

> Bu yönerge, arayüzdeki **her** öğenin (buton, input, kart, panel, arka plan, form, popup, GenUI kartı) köşe yarıçapını **tek bir matematik kuralından** türetir. Hiçbir radius "göze göre" seçilmez; her değer bir çapadan ve aradaki boşluktan hesaplanır.

---

## 0. Özet: tek sayfalık kural

```
ÇAPA        r₀ = 5px                          (Button, Input, Select ve tüm kontroller)

DIŞA        R = min( r + min(d, B),  R_max,  min(W, H) / 2 )
İÇE         r = max( R − d,  r_floor )        (hesap ≤ 0 ise ve öğe kasıtlı keskinse 0)

SABİTLER    B       = 16px   bağlanma tavanı (binding cap)
            R_max   = 29px   en büyük köşe
            r_floor = 2px    görünür en küçük köşe
            d       = min(d_x, d_y), köşeye bitişik çocuğun iç boşluğu
```

**Basamaklar (ladder)**: Değerler 5'ten başlar ve aradaki boşluklar eklenerek büyür. Boşluklar Ant'ın 4px ızgarasında (2, 4, 8, 12, 16) olduğu için basamaklar kapalı bir küme oluşturur:

```
0 · 3 · 5 · 7 · 9 · 13 · 17 · 21 · 25 · 29
```

Bu listede olmayan bir radius değeri kod incelemesinde **hata** sayılır.

---

## 1. Neden bu matematik?

Dış kutunun köşe yarıçapı **R**, iç kutunun köşe yarıçapı **r**, aradaki boşluk **d** olsun. İki köşe yayı arasındaki boşluğu 45° köşegen boyunca ölçelim:

```
köşegen boşluk = d·√2 − (R − r)·(√2 − 1)
```

Bu değerin kenarlardaki boşlukla (d) aynı olması için şu koşul gerekir:

```
r = R − d      ⟺      R = r + d
```

Koşul sağlandığında iki yay **aynı merkezi** paylaşır ve boşluk her noktada eşit kalır. Bu duruma eş merkezlilik (concentricity) diyoruz.

**Hata ölçüsü.** Kural bilinçli olarak esnetildiğinde (bkz. B tavanı) köşede ne kadar sapma oluştuğu şöyle hesaplanır:

```
E = (√2 − 1) · (r + d − R)  ≈  0.414 · (r + d − R)
```

| d (boşluk) | Uygulanan R | Köşe hatası E | Boşluğa oranı |
|---|---|---|---|
| ≤ 16 | r + d | 0 | %0 (tam eş merkezli) |
| 20 | r + 16 | 1.7px | %8 |
| 24 | r + 16 | 3.3px | %14 |
| 32 | r + 16 | 6.6px | %21 |

Göz, ~%15'in altındaki sapmayı fark etmez. Boşluk 24'ü geçtiğinde iki katman zaten görsel olarak "eşleşmiş" sayılmaz, ayrı yüzeyler olarak algılanır. **B = 16** tavanının dayanağı bu.

---

## 2. Token tablosu

| Token | Değer | Türetme | Rol | Kullanım yerleri |
|---|---|---|---|---|
| `--r-none` | **0** | n/a | Kenara dayalı | Sayfa arka planı, full-bleed bölümler, tablo hücreleri, divider |
| `--r-micro` | **3** | 5 − 2 | Kontrol içi | Select multiple tag, input içindeki chip, Checkbox (16px leaf), Tag (22px leaf), Badge (kare) |
| `--r-control` | **5** | **ÇAPA** | Kontrol | Button, Input, TextArea, Select, InputNumber, DatePicker, Cascader, Segmented öğesi, menü öğesi, liste öğesi hover zemini, Tooltip, Conversations öğesi, Attachments FileCard |
| `--r-ring` | **7** | 5 + 2 | Sarmalayıcı (2px) | Segmented kabı, Radio.Group (button) kabı, özel focus ring (offset 2) |
| `--r-menu` | **9** | 5 + 4 | Popup (4px) | Dropdown, Select/Cascader/AutoComplete popup, context menu, Mentions popup |
| `--r-surface` | **13** | 5 + 8 | Yüzey (8px) | **Bubble, Sender**, Attachments paneli, Prompts öğesi, ThoughtChain öğesi, küçük Popover, Notification içi blok |
| `--r-surface-lg` | **17** | 5 + 12 | Yüzey (12px) | Popover, Card `size="small"`, Message/Notification, Prompts grubu, Welcome kartı |
| `--r-panel` | **21** | 5 + 16 | Panel (16+) | Card (varsayılan), Modal, yüzen Drawer, **GenUI kartı**, Form kabı (görünürse) |
| `--r-shell-sm` | **25** | 13 + 12 | Kabuk | İçinde yüzey bulunan yüzen panel (12px boşluk) |
| `--r-shell` | **29** | 13 + 16 · 21 + 8 | Kabuk (en dış) | Chat kabuğu, yüzen sidebar, Welcome hero kabı. **R_max** |

> Kapsül (pill) öğeler (`shape="round"`, `shape="circle"`, Avatar) basamak dışında kalır: **r = h / 2**. Ama içlerindeki ve dışlarındaki öğeler aynı formüle tabidir.

---

## 3. Kurallar

### Kural 1. Çapa
Yüksekliği **≥ 24px** olan her etkileşimli kontrolün köşesi **5px**'tir. `size="small" | "middle" | "large"` bunu değiştirmez. Çapa sabit kaldığı için zincirin geri kalanı da sabit kalır.

### Kural 2. Küçük leaf öğeler (h < 24)
İçinde başka yuvarlak öğe olmayan küçük öğelerde radius orantıyla bulunur ve en yakın basamağa yuvarlanır:

```
r = round( h · 5 / 32 ),   alt sınır 2
```

16px Checkbox → 2.5 → **3** · 22px Tag → 3.4 → **3** · 20px Badge → 3.1 → **3**

### Kural 3. Dışa türetme (kap)
Görünür bir kabın radius'u, **köşesine bitişik** çocuğuna göre belirlenir:

```
R = r_çocuk + min(d, 16)
```

- `d`, kabın **dış kenarından** (border-box) çocuğun dış kenarına olan mesafedir.
- Yatay ve dikey boşluk farklıysa `d = min(d_x, d_y)` alınır. Bu, köşedeki boşluğun hiçbir zaman dar kenardaki boşluktan küçük olmamasını garanti eder.
- **Köşeye bitişik olmayan çocuklar radius'u etkilemez.** Kartın ortasındaki bir buton kartın köşesini belirlemez; sağ alt köşedeki buton belirler.
- Köşeye bitişik birden fazla çocuk varsa **en büyük** sonuç alınır: `R = max(rᵢ + min(dᵢ, 16))`.

### Kural 4. İçe türetme
Radius'u bilinen bir kabın içine öğe yerleştirirken:

```
r = max(R − d, 2)
```

Sonuç 0 veya negatifse çocuğun köşesi kabın düz kenarına denk gelir. Bu durumda 2px kullan, ya da öğe kasıtlı olarak keskinse 0.

### Kural 5. Kenara dayanan çocuk (d = 0)
Kabın kenarına sıfır boşlukla dayanan çocuk (kart kapağı görseli, header şeridi, kenara dayalı tablo):
- **Dayandığı köşelerde** kabın radius'unu aynen alır: `r = R`.
- **Diğer köşeleri** 0 olur.
- CSS'te bunun yerine kaba `overflow: hidden` vermek de olur.

### Kural 6. Görünmez kaplar zincire katılmaz
Arka planı, kenarlığı ve gölgesi olmayan bir kabın (Form, Flex, Space, düz `div`, `Bubble variant="borderless"`) radius'u yoktur. Boşluğu ise **birikir**: çocuğun radius'u, bir sonraki **görünür** atadan çocuğa kadar olan toplam mesafeyle hesaplanır.

### Kural 7. Derinlik sınırı
En fazla **4 görünür katman** olabilir: `kontrol → yüzey → panel → kabuk`. Zincir **R_max = 29**'u aşıyorsa bir katmanı şu yollardan biriyle çöz:
1. Katmanı **görünmez** yap (arka planını kaldır), ya da
2. Katmanı **kenara dayalı** yap (radius 0), ya da
3. Boşluğu küçült.

Aşan bir değeri 29'a kesip geçmek kuralı ihlal eder.

### Kural 8. Kapsül sınırı
Hiçbir radius, öğenin kısa kenarının yarısını aşamaz: `R ≤ min(W, H) / 2`. Bu sınıra ulaşan öğe kapsül olur. Kapsülün içindeki kapsül de eş merkezlidir: `r = H/2 − d`.

### Kural 9. Dışa taşan çizgiler
| Öğe | Radius |
|---|---|
| `box-shadow` spread s | Otomatik takip eder, elle radius verme |
| `outline` + `outline-offset: o` | Modern tarayıcılar otomatik takip eder |
| Ayrı elemanla çizilen focus ring (offset o, kalınlık w) | `r + o + w` (dış kenar) |
| Ortalanmış SVG stroke (kalınlık s) | Dış `R + s/2`, iç `R − s/2` |

### Kural 10. Birleşik kontroller
`Space.Compact`, `Input` addon'ları ve buton grupları **tek bir kontrol** gibi davranır: dış köşeler 5, birleşim köşeleri 0. Ant bunu kendisi yapar, elle müdahale etme.

### Kural 11. Border radius'u değiştirmez
`d`'yi border-box (dış kenar) ile ölçtüğün sürece 1px kenarlık hesabı bozmaz:

```
iç kenar yarıçapı = R − 1,   gerçek boşluk = d − 1   →   r = (R − 1) − (d − 1) = R − d  ✓
```

### Kural 12. Değerler tam sayıdır
Bütün radius'lar tam piksel değerindedir ve basamak listesinden gelir. Boşluklar 4px ızgarasında (ve 2px istisnasında) kaldıkça bu kendiliğinden sağlanır.

---

## 4. Karar algoritması: yeni bir bileşen geldiğinde

```
1. Görünür bir sınırı var mı (bg / border / shadow)?
     Hayır → radius YOK. Boşluğunu çocuklara aktar (Kural 6). DUR.

2. Kapsül mü (pill / circle / avatar)?
     Evet  → r = h / 2. DUR.

3. İçinde köşesine bitişik yuvarlak çocuk var mı?
     Hayır (leaf):
        h ≥ 24 → r = 5
        h < 24 → r = round(h·5/32), min 2
     Evet (kap):
        d = min(d_x, d_y)
        R = max over köşe çocukları ( rᵢ + min(dᵢ, 16) )

4. Ebeveynin kenarına dayanıyor mu (d = 0)?
     Evet → dayandığı köşelerde R_ebeveyn, diğerlerinde 0.

5. Sınırla:  R = min(R, 29, min(W,H)/2)
     R hesapta 29'u aştıysa → Kural 7'yi uygula, kesip geçme.

6. Sonuç basamak listesinde mi?  0·3·5·7·9·13·17·21·25·29
     Hayır → boşluk ızgara dışında. Boşluğu düzelt, radius'u değil.
```

---

## 5. Ant Design X: GenUI bileşen haritası

### 5.1 Sohbet düzeni (referans)

```
┌─ Sayfa arka planı ──────────────────────────────────────── r = 0 (full-bleed)
│
│  ┌─ Chat kabuğu (yüzen, bg var) ───────────────────── r = 29 (13 + 16)
│  │  padding 16
│  │
│  │   ╭─ Bubble (assistant, filled) ─────────╮          r = 13 (5 + 8)
│  │   │  padding 8 12                        │
│  │   │   ╭─ kod bloğu / tablo ─╮             │          r = 5  (13 − 8)
│  │   │   ╰─────────────────────╯             │
│  │   ╰───────────────────────────────────────╯
│  │
│  │   (Bubble borderless — GenUI kartı taşıyor)
│  │   ╭─ GenUI kartı ─────────────────────────╮          r = 21 (5 + 16)
│  │   │  padding 16                           │
│  │   │   ┌Input┐  ┌Select┐  ┌Button┐         │          r = 5
│  │   ╰───────────────────────────────────────╯
│  │
│  │   ╭─ Sender ──────────────────────────────╮          r = 13 (5 + 8)
│  │   │  padding 8                            │
│  │   │   textarea ...           ┌Gönder┐     │          r = 5
│  │   ╰───────────────────────────────────────╯
│  └──────────────────────────────────────────────────
```

> Kabuk, Sender'a göre 13 + 16 = **29** olur. GenUI kartı (21) köşeye bitişik değilse kabuğu etkilemez. Bitişikse 21 + 8 = 29 sonucunu verecek şekilde boşluk **8** seçilir.

### 5.2 Bileşen tablosu

| Ant X bileşeni | Görünür? | Köşe çocuğu → d | Radius |
|---|---|---|---|
| **Sender** (kare aksiyonlar) | Evet | Buton 5 → 8 | **13** |
| **Sender** (tek satır, kapsül mod) | Evet | Circle buton 32px (r 16) → 8 | **24 = H/2** (H = 48, kapsül içinde kapsül) |
| Sender header / Attachments paneli | Evet | FileCard 5 → 8 | **13** |
| Attachments FileCard | Evet | leaf ≥ 24 | **5** |
| **Bubble** `filled / outlined / shadow` | Evet | İç blok 5 → 8 | **13** |
| **Bubble** `borderless` | **Hayır** | n/a | yok (Kural 6) |
| Bubble içi kod / tablo / görsel | Evet | 13 − 8 | **5** |
| **GenUI kartı** (Bubble içinde) | Evet | Kontrol 5 → 16 | **21**, ve Bubble'ı **borderless** yap |
| Prompts öğesi | Evet | İkon kutusu 5 → 8 | **13** |
| Prompts grubu (görünürse) | Evet | Öğe 13 → 4 | **17** |
| Welcome | Evet | İçerik 13 → 16 | **29** (kabuk) ya da görünmez |
| Conversations öğesi | Evet | leaf | **5** |
| Conversations sidebar (yüzen) | Evet | Öğe 5 → 8 | **13** |
| Conversations sidebar (kenara dayalı) | Evet | Kenara dayalı | **0** |
| ThoughtChain öğesi | Evet | İç blok 5 → 8 | **13** |
| Actions (bubble altı ikon butonları) | Evet | leaf | **5** |
| Suggestion popup | Evet | Öğe 5 → 4 | **9** |

### 5.3 Ant Design bileşen tablosu

| Bileşen | Hesap | Radius |
|---|---|---|
| Button / Input / Select / DatePicker / InputNumber (her boyut) | çapa | **5** |
| Checkbox (16px) | 16·5/32 | **3** |
| Tag (22px) | 22·5/32 | **3** |
| Select multiple içindeki tag | 5 − 2 | **3** |
| Input içindeki gömülü buton (inset 3) | 5 − 3 | **2** |
| Segmented kabı (padding 2) | 5 + 2 | **7** |
| Dropdown / Select popup (padding 4) | 5 + 4 | **9** |
| Tooltip | leaf | **5** |
| Popover (padding 12) | 5 + 12 | **17** |
| Card `small` (padding 12) | 5 + 12 | **17** |
| Card (padding 24) | 5 + min(24, 16) | **21** |
| Card `type="inner"` (Card içinde, inset 24) | 21 − 16 | **5**, ya da iç kartı görünmez yap |
| Card cover görseli (d = 0) | Kural 5 | üst köşeler **21**, alt **0** |
| Modal (padding 24) | 5 + 16 | **21** |
| Drawer (kenara dayalı) | Kural 5 | Dayalı kenar **0**, iç kenar 21 (yüzense) |
| Notification / Message | 5 + 12 | **17** |
| Table | Kart içinde kenara dayalı | Dış köşeler kartı izler, hücreler **0** |
| Avatar / circle buton / Switch | kapsül | **h/2** |

---

## 6. Arka planlar ve durumlar

| Durum | Kural |
|---|---|
| Sayfa arka planı | **0**. Viewport'un köşesi yok. |
| Bölüm arka planı (renkli alan) | Bir yüzeydir. Kenara dayalıysa Kural 5, yüzüyorsa Kural 3. |
| Hover / active / selected zemini | Öğenin kendi radius'u (liste öğesi, menü öğesi: **5**). |
| Skeleton | Temsil ettiği öğenin radius'u. |
| Disabled / loading / error | Radius **değişmez**. Durumlar şekli değiştirmez. |
| Drag-over / drop zone | Bağlı olduğu kabın iç değeri: `R − d`. |

---

## 7. Uygulama

### 7.1 CSS token'ları

```css
:root {
  /* sabitler */
  --r-anchor: 5px;
  --r-bind: 16px;     /* B */
  --r-max: 29px;
  --r-floor: 2px;

  /* basamaklar */
  --r-none: 0px;
  --r-micro: 3px;      /* 5 − 2  */
  --r-control: 5px;    /* çapa   */
  --r-ring: 7px;       /* 5 + 2  */
  --r-menu: 9px;       /* 5 + 4  */
  --r-surface: 13px;   /* 5 + 8  */
  --r-surface-lg: 17px;/* 5 + 12 */
  --r-panel: 21px;     /* 5 + 16 */
  --r-shell-sm: 25px;  /* 13 + 12 */
  --r-shell: 29px;     /* 13 + 16 = R_max */
}

/* Dışa türetme: kap, çocuğun radius'unu ve kendi padding'ini bilir */
.concentric-outer {
  /* --child-r ve --inset bileşende tanımlanır */
  border-radius: min(
    var(--r-max),
    calc(var(--child-r) + min(var(--inset), var(--r-bind)))
  );
  padding: var(--inset);
}

/* İçe türetme: çocuk, ebeveynin radius'unu ve boşluğu bilir */
.concentric-inner {
  border-radius: max(var(--r-floor), calc(var(--parent-r) - var(--inset)));
}

/* Squircle (sürekli eğrilik): destekleyen tarayıcıda, değerler aynı kalır */
@supports (corner-shape: squircle) {
  :where(.ant-btn, .ant-input, .ant-card, .ant-modal-content, .r-squircle) {
    corner-shape: squircle;
  }
}
```

### 7.2 TypeScript yardımcıları

```ts
export const R = {
  anchor: 5, bind: 16, max: 29, floor: 2,
  ladder: [0, 3, 5, 7, 9, 13, 17, 21, 25, 29] as const,
};

/** Kap radius'u: köşeye bitişik çocuklardan türetilir. */
export function outerRadius(
  corners: { r: number; dx: number; dy: number }[],
  box?: { w: number; h: number },
): number {
  const raw = Math.max(...corners.map(c => c.r + Math.min(Math.min(c.dx, c.dy), R.bind)));
  const capsule = box ? Math.min(box.w, box.h) / 2 : Infinity;
  if (raw > R.max) {
    console.warn(`[radius] ${raw} > R_max: katmanı görünmez/kenara dayalı yap (Kural 7).`);
  }
  return Math.min(raw, R.max, capsule);
}

/** Çocuk radius'u: ebeveynden içe türetilir. */
export function innerRadius(parentR: number, inset: number, sharp = false): number {
  if (inset === 0) return parentR;              // Kural 5
  const r = parentR - inset;
  return r > 0 ? Math.max(r, R.floor) : sharp ? 0 : R.floor;
}

/** Küçük leaf (h < 24). */
export const leafRadius = (h: number) =>
  h >= 24 ? R.anchor : Math.max(R.floor, Math.round((h * R.anchor) / 32));

/** Denetim: basamak dışındaki değer = hata. */
export const isValidRadius = (r: number) => (R.ladder as readonly number[]).includes(r);
```

### 7.3 Ant Design / Ant Design X tema eşlemesi

> ⚠️ Ant, global radius token'larını bileşen boyutuna ve türüne göre farklı yerlerde kullanır (ör. büyük buton `borderRadiusLG`, popup `borderRadiusLG` okur). Aşağıdaki eşleme bu yüzden **önce global token'ları basamaklara bağlar, sonra bileşen düzeyinde çapayı sabitler**. Token adları sürümler arasında değişebilir, kurulu `antd` / `@ant-design/x` sürümünde doğrula.

```tsx
import { ConfigProvider } from 'antd';
// Ant Design X kullanıyorsan: import { XProvider } from '@ant-design/x';

const r = { micro: 3, control: 5, ring: 7, menu: 9, surface: 13, surfaceLg: 17, panel: 21, shell: 29 };
const anchorAllSizes = { borderRadius: r.control, borderRadiusSM: r.control, borderRadiusLG: r.control };

export const radiusTheme = {
  token: {
    borderRadiusXS: r.micro,
    borderRadiusSM: r.control,
    borderRadius:   r.control,   // çapa
    borderRadiusLG: r.menu,      // varsayılan popup'lar (Dropdown, Select popup) → 9
    borderRadiusOuter: r.control,
  },
  components: {
    // Kontroller: boyut ne olursa olsun 5
    Button: anchorAllSizes,
    Input: anchorAllSizes,
    InputNumber: anchorAllSizes,
    Select: anchorAllSizes,
    DatePicker: anchorAllSizes,
    Cascader: anchorAllSizes,
    Mentions: anchorAllSizes,

    // Küçük leaf'ler
    Tag: { borderRadiusSM: r.micro },
    Checkbox: { borderRadiusSM: r.micro },

    // Sarmalayıcılar
    Segmented: { borderRadius: r.ring, borderRadiusSM: r.control, borderRadiusLG: r.ring },

    // Yüzeyler & paneller
    Popover: { borderRadiusLG: r.surfaceLg },
    Card: { borderRadiusLG: r.panel, borderRadiusSM: r.surfaceLg },
    Modal: { borderRadiusLG: r.panel },
    Notification: { borderRadiusLG: r.surfaceLg },
    Message: { borderRadiusLG: r.surfaceLg },
  },
};

// <ConfigProvider theme={radiusTheme}>…</ConfigProvider>
```

**Ant X bileşenleri** (Bubble, Sender, Prompts, Conversations, Attachments, ThoughtChain) için tema token'ı yetmiyorsa ilgili `className` / `styles` / `classNames` slotlarından token değişkenini ver:

```css
.ant-sender,
.ant-bubble-content,
.ant-prompts-item,
.ant-thought-chain-item,
.ant-attachments-list-card-wrap /* sürüme göre sınıf adını doğrula */ {
  border-radius: var(--r-surface);  /* 13 */
}
.ant-conversations-item,
.ant-attachments-list-card { border-radius: var(--r-control); } /* 5 */

.genui-card { border-radius: var(--r-panel); padding: 16px; }   /* 21 */
.chat-shell { border-radius: var(--r-shell); padding: 16px; }   /* 29 */
```

---

## 8. GenUI kuralları (üretilen arayüzler için)

Model tarafından üretilen her UI parçası bu kurallara **zorunlu** olarak uyar:

1. **Ham radius değeri yok.** Üretilen kod yalnızca `--r-*` token'larını ya da `radiusTheme`'i kullanır. `border-radius: 10px` gibi bir değer reddedilir.
2. **GenUI kartı = panel (21), padding 16.** İçindeki kontroller 5'tir.
3. **Kart Bubble içindeyse Bubble `borderless` olur** (Kural 6). Aksi halde zincir 5 → 21 → 29 → ... olur ve R_max aşılır.
4. **Kart içinde kart yok.** İç gruplama gerekiyorsa iç grup **görünmez** olur (yalnızca boşluk ve divider), ya da iç grup `--r-surface` (13) alır ve dış kart 13 + 8 = **21** kalacak şekilde iç boşluk 8 seçilir.
5. **Boşluklar ızgarada:** 2, 4, 8, 12, 16, 24. Izgara dışı boşluk, basamak dışı radius üretir ve bu hata sayılır.
6. **Kapsül serbest ama bağlı.** Pill buton kullanıldıysa onu taşıyan kabın köşesi `h/2 + d` ile yeniden hesaplanır.

---

## 9. Kontrol listesi (code review)

- [ ] Her `border-radius` değeri `0·3·5·7·9·13·17·21·25·29` listesinde.
- [ ] İç içe iki görünür öğede **aynı radius yok** (d > 0 iken `R = r` yasak).
- [ ] Her kabın radius'u, köşesine bitişik çocuğun `r + min(d,16)` değerine eşit.
- [ ] Görünmez kaplara radius verilmemiş.
- [ ] Kenara dayalı çocuklar yalnızca dayandıkları köşelerde ebeveyn radius'unu alıyor.
- [ ] Hiçbir değer `min(W,H)/2`'yi ve 29'u aşmıyor.
- [ ] Boyut varyantları (`small/large`) kontrol radius'unu değiştirmiyor.
- [ ] Durum değişiklikleri (hover, error, disabled) radius'u değiştirmiyor.
- [ ] GenUI kartı Bubble içindeyse Bubble borderless.

---

## 10. Sık yapılan hatalar

| Hata | Neden yanlış | Doğrusu |
|---|---|---|
| Kart 8, içindeki input 8 | Köşede boşluk şişer, öğe "yapıştırılmış" görünür | Kart = 5 + min(d,16) |
| Popup 6, öğeleri 6 (padding 4) | İç ve dış köşe çakışır | Popup 9, öğeler 5 |
| Büyük butona 8, küçüğe 4 | Çapa kayar, bütün zincir boyuta göre değişir | Her boyutta 5 |
| Bubble içinde kart içinde kart | 4+ katman, R_max aşılır | Bubble borderless, iç grup görünmez |
| Radius'u ölçekle çarpmak (×1.5) | `k·r + k·d ≠ k·r + d`, eş merkezlilik bozulur | Değerleri toplamayla türet |
| Padding'i 10, 14 gibi değerlerle vermek | Basamak dışı radius üretir | Izgara: 2, 4, 8, 12, 16, 24 |

---

*Tek cümle: köşeyi sayı olarak değil, **ilişki** olarak tanımla. Çapa 5'tir, üstündeki her köşe "çocuk + boşluk", altındaki her köşe "ebeveyn − boşluk" olarak bulunur.*
