#!/usr/bin/env python3
"""Statik SVG diyagramlarını üretir: src/components/Rails.astro ve Timeline.astro.

Kurallar: yazı boyutu >= 16 birim (viewBox 1040 → CSS'te min-width 65rem ile ölçek >= 1),
renk ve yazı tipi yalnızca CSS tasarım tokenlarından, etiketler çakışmaz ve viewBox içinde kalır
(tests/smoke.spec.ts 'static SVG labels' testi bunu doğrular).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = "style='font-family: var(--mantine-font-family), \"Outfit Variable\", Outfit, system-ui, sans-serif'"


def figure(cls: str, label: str, svg: str, caption: str, source: str) -> str:
    """Kaydırma bölgesi figürün içindeki div'dir: figcaption'lı <figure> role=region alamaz (ARIA in HTML)."""
    return (
        f"---\n// {source} — scripts/gen-diagrams.py üretir; elle düzenlemeyin.\n---\n"
        f'<figure class="diagram {cls}">\n'
        f'<div class="diagram-scroll" tabindex="0" role="region" aria-label="{label} (yatay kaydırılabilir)">\n'
        + svg
        + f'\n</div>\n<figcaption class="diagram-note">{caption}</figcaption>\n</figure>\n'
    )


def timeline() -> str:
    """Faz sırası çizimi: sütunlar bağımlılık düzeyi, oklar önkoşuldan bağımlı faza. Zaman ekseni ve süre yoktur."""
    phases = json.loads((ROOT / "src/data/phases.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in phases}
    level: dict[str, int] = {}
    for p in phases:  # phases.json önkoşulları önce listeler; düzey = en uzun önkoşul zinciri
        level[p["id"]] = max((level[a] + 1 for a in p["after"]), default=0)
    columns: list[list[str]] = [[] for _ in range(max(level.values()) + 1)]
    for p in phases:
        columns[level[p["id"]]].append(p["id"])
    # Düzen: düzey başına bir sütun. Satırlar P1/P3, P0/P4/P5 ve P2/P6 hizalanır. Böylece komşu oklar düz kalır.
    # P7 (P1 ve P2 sonrası) P6'nın altındaki dördüncü satırdadır. Sütun atlayan oklar P7'nin altından dolaşır.
    ROW_Y = {"P0": 190, "P1": 100, "P2": 280, "P3": 100, "P4": 190, "P6": 280, "P5": 190, "P7": 370}
    BOX_W, BOX_H, COL_X0, COL_STEP, BELOW_Y = 200, 64, 40, 256, 462
    col_x = {pid: COL_X0 + COL_STEP * lvl for pid, lvl in level.items()}
    name_of = lambda pid: by_id[pid]["title"].split(" ", 1)[1]  # noqa: E731
    gates = [  # (kimlik, ad, çıkışına bağlı olduğu fazlar)
        ("M1", "İlk dikey dilim", ["P1"]),
        ("M2", "İlk ödeyen müşteri", ["P2", "P4"]),
        ("M3", "Operasyon canlı", ["P6"]),
        ("M4", "CRM/Webshop", ["P5"]),
    ]
    join = lambda ids: ids[0] if len(ids) == 1 else ", ".join(ids[:-1]) + " ve " + ids[-1]  # noqa: E731
    levels_txt = " ".join(f"{i + 1}. sütun {join(c)}." for i, c in enumerate(columns))
    deps_txt = " ".join(f"{p['id']}, {join(p['after'])} bitince başlar." for p in phases if p["after"])
    gates_txt = ", ".join(f"{k} {n} ({join(ids)} çıkışı)" for k, n, ids in gates)
    o = [
        f"<svg viewBox='0 0 1040 610' role='img' aria-labelledby='tl-title tl-desc' font-size='16' {FONT}>",
        "<title id='tl-title'>Yol haritası faz sırası</title>",
        f"<desc id='tl-desc'>Sütunlar bağımlılık düzeyidir. {levels_txt} Oklar önkoşuldan bağımlı faza gider. {deps_txt} "
        f"P2, P1'deki Keycloak adımı bitince başlar. Kapılar: {gates_txt}. Takvim tarihi ve süre yoktur.</desc>",
        "<defs><marker id='tl-arr' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>"
        "<path d='M0 0L10 5L0 10z' fill='var(--fs-line)'/></marker></defs>",
        "<text x='24' y='34' font-size='20' font-weight='650' fill='var(--fs-ink)'>Yol haritası faz sırası: her faz önkoşulu bitince başlar</text>",
        "<text x='24' y='60' fill='var(--fs-quiet)'>Sütunlar bağımlılık düzeyidir. Oklar önkoşuldan bağımlı faza gider. Takvim tarihi ve süre yoktur.</text>",
    ]
    for p in phases:
        pid = p["id"]
        x, y = col_x[pid], ROW_Y[pid]
        acc = pid == "P6"
        stroke = "var(--fs-accent)" if acc else "var(--fs-line)"
        fill = "var(--fs-accent-soft)" if acc else "var(--fs-surface)"
        o.append(f"<rect x='{x}' y='{y}' width='{BOX_W}' height='{BOX_H}' rx='10' fill='{fill}' stroke='{stroke}' stroke-width='1.5'/>")
        o.append(f"<text x='{x + 16}' y='{y + 26}' font-size='18' font-weight='650' fill='var(--fs-ink)'>{pid}</text>")
        o.append(f"<text x='{x + 16}' y='{y + 50}' fill='var(--fs-ink)'>{name_of(pid)}</text>")
    # P7'ye giden iki ok kendi yolundan gider. Hiçbiri başka fazın okuyla çizgi ya da çıkış noktası paylaşmaz.
    # P1 → P7: P1'in sağından ayrı bir noktadan (y=148) çıkar. x=510 şeridinden iner, P7'ye üst yarıdan girer.
    #   x=510, P1 → P4 şeridinin (x=524) solundadır. Böylece P1 → P4'ün y=222 parçasını kesmez.
    #   P2 → P6 çizgisini (y=312) kesmek zorunludur. Kesişme noktasında zemin renginde bir boşluk bırakılır.
    # P2 → P7: P2'nin altından (x=456) çıkar. P2 → P6 sağdan, P2 → P5 x=396'dan çıkar. P7'ye alt yarıdan girer.
    P7_Y1, P7_Y2 = ROW_Y["P7"] + 16, ROW_Y["P7"] + BOX_H - 16
    P1P7_X, P1P7_OUT_Y, P2P7_X = col_x["P7"] - 42, ROW_Y["P1"] + 48, col_x["P2"] + 160
    routes = {
        "P1-P7": f"M{col_x['P1'] + BOX_W} {P1P7_OUT_Y} L{P1P7_X} {P1P7_OUT_Y} L{P1P7_X} {P7_Y1} L{col_x['P7']} {P7_Y1}",
        "P2-P7": f"M{P2P7_X} {ROW_Y['P2'] + BOX_H} L{P2P7_X} {P7_Y2} L{col_x['P7']} {P7_Y2}",
    }
    halo_y = ROW_Y["P2"] + BOX_H // 2  # P1 → P7'nin P2 → P6 çizgisini kestiği yer
    for p in phases:
        for pre in p["after"]:
            edge = f"{pre}-{p['id']}"
            if edge in routes:
                if edge == "P1-P7":
                    o.append(
                        f"<path data-halo='{edge}' d='M{P1P7_X} {halo_y - 7} L{P1P7_X} {halo_y + 7}' fill='none' "
                        "stroke='var(--fs-surface-2)' stroke-width='7'/>"
                    )
                o.append(f"<path data-edge='{edge}' d='{routes[edge]}' fill='none' stroke='var(--fs-line)' stroke-width='1.5' marker-end='url(#tl-arr)'/>")
                continue
            x1, y1 = col_x[pre] + BOX_W, ROW_Y[pre] + BOX_H / 2
            x2, y2 = col_x[p["id"]], ROW_Y[p["id"]] + BOX_H / 2
            if level[p["id"]] - level[pre] > 1:  # sütun atlayan ok kutuların altından dolaşır, hedefe alttan girer
                bx, by = col_x[pre] + BOX_W / 2, ROW_Y[pre] + BOX_H
                tx, ty = col_x[p["id"]] + BOX_W / 2, ROW_Y[p["id"]] + BOX_H
                d = f"M{bx:.0f} {by} L{bx:.0f} {BELOW_Y} L{tx:.0f} {BELOW_Y} L{tx:.0f} {ty}"
            elif y1 == y2:
                d = f"M{x1} {y1:.0f} L{x2} {y2:.0f}"
            else:
                xm = x2 - 28
                d = f"M{x1} {y1:.0f} L{xm} {y1:.0f} L{xm} {y2:.0f} L{x2} {y2:.0f}"
            o.append(f"<path data-edge='{pre}-{p['id']}' d='{d}' fill='none' stroke='var(--fs-line)' stroke-width='1.5' marker-end='url(#tl-arr)'/>")
    # P1 → P2 ara kapısı: P1 bitmeden, Keycloak adımı bitince (kesikli ok).
    gx = col_x["P1"] + 60
    o.append(
        f"<path data-edge='P1-P2-gate' d='M{gx} {ROW_Y['P1'] + BOX_H} L{gx} {ROW_Y['P2']}' fill='none' stroke='var(--fs-accent)' "
        "stroke-width='1.5' stroke-dasharray='5 5' marker-end='url(#tl-arr)'/>"
    )
    o.append(f"<text x='{gx + 10}' y='{(ROW_Y['P1'] + BOX_H + ROW_Y['P2']) / 2 + 6:.0f}' fill='var(--fs-accent-ink)'>Keycloak adımı</text>")
    gy = 494
    o.append(f"<text x='24' y='{gy}' font-weight='650' fill='var(--fs-ink)'>Kapılar (hangi fazın çıkışına bağlı)</text>")
    for i, (k, name, ids) in enumerate(gates):
        x = 24 + 500 * (i % 2)
        y = gy + 36 + 34 * (i // 2)
        acc = k == "M2"
        col = "var(--fs-accent)" if acc else "var(--fs-line)"
        fw = " font-weight='650'" if acc else ""
        o.append(f"<path d='M{x + 10} {y - 14}l10 10l-10 10l-10 -10z' fill='{col}'/>")
        o.append(f"<text x='{x + 32}' y='{y}'{fw} fill='var(--fs-ink)'>{k} {name} ({join(ids)} çıkışı)</text>")
    o.append("</svg>")
    caption = (
        "P2 ticari katman, P1'deki Keycloak adımı bitince başlar ve operasyon sitesinin finans çekirdeğini içerir. "
        "P3 AI ve P4 HRMS TR, P1 çıkışından sonra paralel yürür. P6 operasyon düzlemi P2 bitince açılır. "
        "P5, ilk ödeyen müşteri kapısından sonra gelir. Bu kapı P2 ve P4 çıkışına bağlıdır. "
        "P7 AtonotA Login ürünü MVP sonrasıdır. P7, P1 ve P2 bitince açılır."
    )
    return figure("diagram-timeline", "Yol haritası faz sırası", "\n".join(o), caption, "Yol haritası faz sırası")


def rails() -> str:
    W = 1040

    def box(x, y, w, h, title, sub, lines, accent=False):
        col = "var(--fs-accent)" if accent else "var(--fs-line)"
        out = ["<g>"]
        out.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='12' fill='var(--fs-surface-2)' stroke='{col}' stroke-width='1.5'/>")
        out.append(f"<rect x='{x}' y='{y}' width='6' height='{h}' rx='3' fill='{col}'/>")
        out.append(f"<text x='{x + 20}' y='{y + 30}' font-size='18' font-weight='650' fill='var(--fs-ink)'>{title}</text>")
        out.append(f"<text x='{x + 20}' y='{y + 54}' fill='var(--fs-quiet)'>{sub}</text>")
        for i, l in enumerate(lines):
            out.append(f"<text x='{x + 20}' y='{y + 84 + 24 * i}' fill='var(--fs-ink)'>{l}</text>")
        out.append("</g>")
        return out

    def label(text, x, y, anchor="start"):
        # Hale, erişilebilirlik ağacından gizli ayrı bir kopyadır; dolgu metni onun üstüne çizilir. Tek <text> üzerinde
        # paint-order='stroke' Firefox'ta başka yazı tipi dosyasından gelen glifi (latin-ext 'ş') ayrı çizim parçası
        # yapınca o parçanın halesi önceki glifleri örtüyordu.
        pos = f"x='{x}' y='{y}' text-anchor='{anchor}'"
        return (
            f"<text class='halo' aria-hidden='true' {pos} fill='none' stroke='var(--fs-surface)' stroke-width='6' "
            f"stroke-linejoin='round'>{text}</text>\n"
            f"<text {pos} fill='var(--fs-quiet)'>{text}</text>"
        )

    def arrow(x1, y1, x2, y2, text, lx, ly, anchor="start", dashed=False):
        d = " stroke-dasharray='5 5'" if dashed else ""
        return [
            f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='var(--fs-line)' stroke-width='1.5' marker-end='url(#arr)'{d}/>",
            label(text, lx, ly, anchor),
        ]

    o = [
        f"<svg viewBox='0 0 {W} 940' role='img' aria-labelledby='rails-title rails-desc' font-size='16' {FONT}>",
        "<title id='rails-title'>Altı mimari ray ve iki taban bandı</title>",
        "<desc id='rails-desc'>Üst sırada Rail 3 headless panel yer alır. Ortada Rail 5 ajan servisi ve model geçidi ile Rail 4 Keycloak yer alır. Alt sırada Rail 1 "
        "Press kontrol düzlemi (Frappe 16), Rail 2 kiracı ERPNext 16 siteleri ve Rail 6 operasyon sitesi yer alır. Panel, "
        "Press'e panel adresindeki press.api ve realtime üzerinden ulaşır. Kiracıya aynı kaynaktan /api/v2 ve bootstrap/meta ile ulaşır. Operasyon sitesine customer_360 "
        "ve HD Ticket ile ulaşır. Ajan servisine SSE ile bağlanır. Panel, Keycloak'a OIDC ile yönlendirir. Sunucu, giriş kodunu belirteçle değiştirir. Ajan servisi Press'e press.mcp ile bağlanır. Ajan servisi "
        "kiracıya site aracı belirteciyle Kiracı MCP üzerinden bağlanır. Keycloak, Social Login Key ile Press'e ve kiracıya giriş sağlar. Operasyon sitesi operatör realm "
        "rollerini kullanır. Press ile kiracı arasında site_config sk_app ve Agent Job kullanılır. Press, operasyon sitesine create-fc-invoice (press_tr_finance), "
        "delete-fc-team ve press_ops_bridge ile ulaşır. Operasyon sitesi Press'e press_tr.api.ops ile ulaşır. Taban bantları ortak sözleşmeleri (host'a bağlı oturum, "
        "has_permission, tasarım tokenları, audit) ve DevOps sorumlusunun yönettiği Hetzner sunucularını gösterir.</desc>",
        "<defs><marker id='arr' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>"
        "<path d='M0 0L10 5L0 10z' fill='var(--fs-line)'/></marker></defs>",
        "<text x='24' y='34' font-size='20' font-weight='650' fill='var(--fs-ink)'>Altı ray, iki taban bandı: her ray kendi alanının tek doğruluk kaynağı</text>",
        "<text x='24' y='60' fill='var(--fs-quiet)'>Oklar adlandırılmış sözleşmeleri gösterir; yatay sözleşmeler altta listelenir</text>",
    ]
    # Satır 1: Panel (y 90..230)
    o += box(40, 90, 960, 140, "Rail 3 — Headless panel",
             "React · Ant Design · @ant-design/x · TanStack · panel.&lt;marka&gt; ve &lt;kiracı&gt;.app/panel",
             ["@platform/shell · meta-ui · frappe-sdk · design-tokens · ai-sidebar · @apps/*",
              "Superadmin operatör modu (Rail 6'nın kullanıcı yüzü)"])
    # Satır 2: AI (120..460), Keycloak (600..940), y 300..470
    o += box(120, 300, 340, 170, "Rail 5 — AI", "Ajan servisi · model geçidi",
             ["Önizle+onayla · PostgreSQL/Redis", "Yerel maskeleme · kota · AI Action Log", "Site aracı belirteci (K-25)"])
    o += box(600, 300, 340, 170, "Rail 4 — Keycloak", "api.login.&lt;marka&gt; · realm platform · HA",
             ["Client'lar: press · site-&lt;kiracı&gt;", "agent-service · identity-sync", "Organizations · MFA · passkey"])
    # Satır 3: Press (40..320), Kiracı (360..680), Ops (720..1000), y 570..740
    o += box(40, 570, 280, 170, "Rail 1 — Press", "Frappe 16 · press.&lt;marka&gt;",
             ["Team · Site · Plan · Marketplace", "Abonelik · Fatura · Agent Job", "press_tr · press_ops_bridge"])
    o += box(360, 570, 320, 170, "Rail 2 — Kiracı siteleri", "ERPNext 16 · &lt;kiracı&gt;.app.&lt;marka&gt;",
             ["Site + DB kiracı başına", "platform_core · tr_localization", "HRMS TR · CRM · Webshop app'leri"])
    o += box(720, 570, 280, 170, "Rail 6 — Operasyon", "ERPNext 16 · ops.&lt;marka&gt;",
             ["Cari · Sales Invoice · e-belge", "press_tr_finance · CRM · Helpdesk", "Support Session · Hocuspocus"], accent=True)
    # Satır1 → Satır2 (230..300): etiketler y=256 (uzun) ve y=280 (kısa)
    o += arrow(290, 230, 290, 300, "SSE akışı (ai-sidebar)", 300, 280)
    o += arrow(770, 230, 770, 300, "OIDC yönlendirmesi", 760, 280, "end")
    # Satır1 → Satır3 kanalları
    o += arrow(80, 230, 80, 570, "press.api.* · press_tr.api.* · realtime", 92, 256)
    o += arrow(530, 230, 530, 570, "/api/v2 · bootstrap · meta · socket.io", 540, 256)
    o += arrow(975, 230, 975, 570, "customer_360 · HD Ticket", 965, 280, "end")
    # Satır2 → Satır3 (470..570): etiketler y=498 / y=522
    o += arrow(190, 470, 190, 570, "press.mcp · press_tr.mcp", 200, 498)
    o += arrow(420, 470, 420, 570, "Kiracı MCP (aracı belirteci)", 432, 522)
    o += arrow(650, 470, 650, 570, "Social Login Key · JWKS · SLO", 662, 498)
    o += arrow(880, 470, 880, 570, "operatör realm rolleri", 868, 522, "end")
    # Keycloak → Press (kesikli dirsek)
    o.append("<path d='M612 470 L612 550 L300 550 L300 570' fill='none' stroke='var(--fs-line)' stroke-width='1.5' stroke-dasharray='5 5' marker-end='url(#arr)'/>")
    o.append(label("Social Login Key press", 320, 544))
    # Yatay sözleşmeler
    o.append("<text x='40' y='782' font-weight='650' fill='var(--fs-ink)'>Yatay sözleşmeler (Rail 1 ↔ Rail 2 ↔ Rail 6)</text>")
    o.append("<text x='40' y='808' fill='var(--fs-quiet)'>Press → Kiracı: site_config sk_&lt;app&gt;, plan_limit, Agent Job · Ops → Press: press_tr.api.ops</text>")
    o.append("<text x='40' y='832' fill='var(--fs-quiet)'>Press → Ops: create-fc-invoice (press_tr_finance), delete-fc-team, press_ops_bridge olayları</text>")
    # Taban bantları
    o.append("<rect x='40' y='856' width='960' height='28' rx='6' fill='var(--fs-accent-soft)' stroke='var(--fs-accent)' stroke-width='1'/>")
    o.append("<text x='520' y='875' text-anchor='middle' fill='var(--fs-ink)'>Taban bandı 1 — Ortak sözleşmeler: host'a bağlı oturum · has_permission · tasarım tokenları · audit</text>")
    o.append("<rect x='40' y='892' width='960' height='28' rx='6' fill='var(--fs-tint)' stroke='var(--fs-grid)' stroke-width='1'/>")
    o.append("<text x='520' y='911' text-anchor='middle' fill='var(--fs-ink)'>Taban bandı 2 — Hetzner bare-metal, self-host (DevOps sorumlusu) · DNS: GoDaddy, app. alt bölgesi Route 53</text>")
    o.append("</svg>")
    svg = "\n".join(o)
    caption = (
        "Plan, fatura ve abonelik yalnızca Rail 1'de yazılır; DocType meta ve sidebar yalnızca Rail 2'den türer; "
        "muhasebe, cari ve ticket'ın tek doğrusu Rail 6'dır; her oturum kendi host'una bağlıdır ve her MCP aracı "
        "çağıran kullanıcının kimliğiyle aynı has_permission yolundan geçer."
    )
    return figure("diagram-rails", "Mimari raylar diyagramı", svg, caption, "Mimari raylar diyagramı")

if __name__ == "__main__":
    (ROOT / "src/components/Timeline.astro").write_text(timeline(), encoding="utf-8")
    (ROOT / "src/components/Rails.astro").write_text(rails(), encoding="utf-8")
    print("Timeline.astro ve Rails.astro yeniden üretildi")
