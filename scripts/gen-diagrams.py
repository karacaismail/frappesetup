#!/usr/bin/env python3
"""Statik SVG diyagramlarını üretir: src/components/Rails.astro ve Timeline.astro.

Kurallar: yazı boyutu >= 16 birim (viewBox 1040 → CSS'te min-width 65rem ile ölçek >= 1),
renk ve yazı tipi yalnızca CSS tasarım tokenlarından, etiketler çakışmaz ve viewBox içinde kalır
(tests/smoke.spec.ts 'static SVG labels' testi bunu doğrular).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = "style='font-family: var(--mantine-font-family), Inter, system-ui, sans-serif'"


def timeline() -> str:
    rows = [
        ("p0", "P0 Altyapı", 0, 6),
        ("p1", "P1 Platform çekirdeği", 6, 18),
        ("p2", "P2 Ticari katman", 14, 23),
        ("p3", "P3 AI katmanı", 18, 30),
        ("p4", "P4 İlk app (CronHR)", 18, 30),
        ("p6", "P6 Operasyon düzlemi", 23, 35),
        ("p5", "P5 CRM · Webshop", 30, 42),
    ]
    # (id, ad, hafta, konum, hizalama, x)
    gates = [
        ("m1", "M1 İlk dikey dilim", 18, "above", "middle", None),
        ("m2", "M2 İlk ödeyen müşteri", 30, "below", "end", 804),
        ("m3", "M3 Operasyon canlı", 35, "above", "middle", None),
        ("m4", "M4 CRM/Webshop", 42, "below", "end", 1016),
    ]
    L, R = 290, 996
    X = lambda w: L + w / 42 * (R - L)  # noqa: E731
    gy = 520
    o = [
        f"<svg viewBox='0 0 1040 600' role='img' aria-labelledby='tl-title tl-desc' font-size='16' {FONT}>",
        "<title id='tl-title'>Yol haritası zaman çizelgesi</title>",
        "<desc id='tl-desc'>42 haftalık plan; P0 altyapı 0–6, P1 platform çekirdeği 6–18, P2 ticari katman 14–23, "
        "P3 AI ve P4 CronHR 18–30, P6 operasyon düzlemi 23–35, P5 CRM/Webshop 30–42. Kapılar: M1 ilk dikey dilim "
        "18. hafta, M2 ilk ödeyen müşteri 30. hafta, M3 operasyon canlı 35. hafta, M4 CRM/Webshop 42. hafta.</desc>",
        "<text x='24' y='34' font-size='20' font-weight='650' fill='var(--fs-ink)'>42 haftalık plan: ilk ödeyen müşteri 30., operasyon düzlemi 35. haftada</text>",
        "<text x='24' y='60' fill='var(--fs-quiet)'>Göreli süre (hafta); fazlar bağımlılıkla zincirlenir, takvim tarihi yoktur (tahmin)</text>",
    ]
    for w in range(0, 43, 6):
        x = X(w)
        o.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='96' y2='{gy + 12}' stroke='var(--fs-grid)'/>")
        o.append(f"<text x='{x:.1f}' y='88' text-anchor='middle' fill='var(--fs-quiet)'>{w}. hafta</text>")
    o.append(f"<line x1='{L}' x2='{R}' y1='96' y2='96' stroke='var(--fs-line)' stroke-width='1.25'/>")
    o.append(
        f"<line x1='{X(30):.1f}' x2='{X(30):.1f}' y1='96' y2='{gy + 12}' stroke='var(--fs-accent)' stroke-width='1.5' stroke-dasharray='5 5'/>"
    )
    for i, (k, name, s, e) in enumerate(rows):
        y = 140 + 52 * i
        acc = k == "p6"
        col = "var(--fs-accent)" if acc else "var(--fs-line)"
        o.append(f"<line x1='{L}' x2='{X(s):.1f}' y1='{y}' y2='{y}' stroke='var(--fs-grid)'/>")
        o.append(
            f"<rect x='{X(s):.1f}' y='{y - 12}' width='{X(e) - X(s):.1f}' height='24' rx='7' fill='{col}' fill-opacity='0.18' stroke='{col}' stroke-width='1.5'/>"
        )
        o.append(f"<text x='{X(s) + 8:.1f}' y='{y - 18}' fill='var(--fs-quiet)'>{s}–{e}. hafta</text>")
        fw = " font-weight='650'" if acc else ""
        o.append(f"<text x='24' y='{y + 6}'{fw} fill='var(--fs-ink)'>{name}</text>")
    o.append(f"<text x='24' y='{gy + 6}' font-weight='650' fill='var(--fs-ink)'>Kapılar</text>")
    for k, name, w, pos, anchor, fx in gates:
        x = X(w)
        col = "var(--fs-accent)" if k == "m2" else "var(--fs-line)"
        o.append(f"<path d='M{x:.1f} {gy - 10}l10 10l-10 10l-10 -10z' fill='{col}'/>")
        ny = gy - 20 if pos == "above" else gy + 36
        fw = " font-weight='650'" if k == "m2" else ""
        tx = fx if fx is not None else x
        o.append(f"<text x='{tx:.1f}' y='{ny}' text-anchor='{anchor}'{fw} fill='var(--fs-ink)'>{name}</text>")
    o.append("</svg>")
    svg = "\n".join(o)
    return (
        "---\n// Yol haritası zaman çizelgesi — scripts/gen-diagrams.py üretir; elle düzenlemeyin.\n---\n"
        '<figure class="diagram diagram-timeline" tabindex="0" role="region" aria-label="Yol haritası zaman çizelgesi (yatay kaydırılabilir)">\n'
        + svg
        + "\n<figcaption class=\"diagram-note\">P2 ticari katman P1'in Keycloak adımı biter bitmez başlar; P3 AI ve P4 CronHR ilk dikey dilimden sonra paralel yürür; P6 operasyon düzlemi iyzico/EFT ve kredi modeli (P2) olmadan açılamaz; P5 ilk ödeyen müşteriden sonra gelir.</figcaption>\n</figure>\n"
    )


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
        return (
            f"<text x='{x}' y='{y}' text-anchor='{anchor}' fill='var(--fs-quiet)' stroke='var(--fs-surface)' "
            f"stroke-width='6' paint-order='stroke' stroke-linejoin='round'>{text}</text>"
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
        "<desc id='rails-desc'>Üstte Rail 3 headless panel; ortada Rail 5 AI agent servisi ve Rail 4 Keycloak; altta Rail 1 "
        "Press kontrol düzlemi (Frappe v15), Rail 2 kiracı ERPNext v16 siteleri ve Rail 6 operasyon sitesi. Oklar: panelden "
        "Press'e press.api ve realtime, kiracıya /api/v2 ve bootstrap/meta, operasyona customer_360 ve HD Ticket, AI servisine "
        "SSE, Keycloak'a OIDC PKCE; AI servisinden Press'e press.mcp, kiracıya frappe_mcp; Keycloak'tan Press ve kiracıya Social "
        "Login Key, operasyona operatör realm rolleri. Yatay sözleşmeler: Press→Kiracı site_config sk_app ve Agent Job; "
        "Press→Ops create-fc-invoice, delete-fc-team, press_ops_bridge; Ops→Press press.api.ops. Taban bantları: ortak "
        "sözleşmeler (Keycloak JWT, has_permission, tasarım tokenları, audit) ve Hetzner bare-metal self-host altyapısı.</desc>",
        "<defs><marker id='arr' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>"
        "<path d='M0 0L10 5L0 10z' fill='var(--fs-line)'/></marker></defs>",
        "<text x='24' y='34' font-size='20' font-weight='650' fill='var(--fs-ink)'>Altı ray, iki taban bandı: her ray kendi alanının tek doğruluk kaynağı</text>",
        "<text x='24' y='60' fill='var(--fs-quiet)'>Oklar adlandırılmış sözleşmeleri gösterir; yatay sözleşmeler altta listelenir</text>",
    ]
    # Satır 1: Panel (y 90..230)
    o += box(40, 90, 960, 140, "Rail 3 — Headless panel",
             "React · Ant Design · @ant-design/x · TanStack · panel.&lt;marka&gt; ve &lt;kiracı&gt;/panel",
             ["@platform/shell · meta-ui · frappe-sdk · design-tokens · ai-sidebar · @apps/*",
              "Superadmin operatör modu (Rail 6'nın kullanıcı yüzü)"])
    # Satır 2: AI (120..460), Keycloak (600..940), y 300..470
    o += box(120, 300, 340, 170, "Rail 5 — AI", "Claude Agent SDK · PostgreSQL/Redis",
             ["Model yönlendirme · önizle+onayla", "PII maskeleme · kota · AI Action Log", "Keycloak token exchange"])
    o += box(600, 300, 340, 170, "Rail 4 — Keycloak", "id.&lt;marka&gt; · realm platform · HA",
             ["Client'lar: panel-spa · press", "site-&lt;kiracı&gt; · agent-service", "identity-sync · Organizations · MFA"])
    # Satır 3: Press (40..320), Kiracı (360..680), Ops (720..1000), y 570..740
    o += box(40, 570, 280, 170, "Rail 1 — Press", "Frappe v15 · press.&lt;marka&gt;",
             ["Team · Site · Plan · Marketplace", "Abonelik · Fatura · Agent Job", "press_tr · press_tr_finance"])
    o += box(360, 570, 320, 170, "Rail 2 — Kiracı siteleri", "ERPNext v16 · &lt;kiracı&gt;.&lt;marka&gt;",
             ["Site + DB kiracı başına", "platform_core · tr_localization", "CronHR · CRM · Webshop app'leri"])
    o += box(720, 570, 280, 170, "Rail 6 — Operasyon", "ERPNext v16 · ops.&lt;marka&gt;",
             ["Cari · Sales Invoice · e-belge", "Frappe CRM · Helpdesk · SLA", "Support Session · Hocuspocus"], accent=True)
    # Satır1 → Satır2 (230..300): etiketler y=256 (uzun) ve y=280 (kısa)
    o += arrow(290, 230, 290, 300, "SSE akışı (ai-sidebar)", 300, 280)
    o += arrow(770, 230, 770, 300, "OIDC PKCE (panel-spa)", 760, 280, "end")
    # Satır1 → Satır3 kanalları
    o += arrow(80, 230, 80, 570, "press.api.* · press_tr.api.* · realtime", 92, 256)
    o += arrow(530, 230, 530, 570, "/api/v2 · bootstrap · meta · socket.io", 540, 256)
    o += arrow(975, 230, 975, 570, "customer_360 · HD Ticket", 965, 280, "end")
    # Satır2 → Satır3 (470..570): etiketler y=498 / y=522
    o += arrow(190, 470, 190, 570, "press.mcp · press_tr.mcp", 200, 498)
    o += arrow(420, 470, 420, 570, "frappe_mcp (kullanıcı token'ı)", 432, 522)
    o += arrow(650, 470, 650, 570, "Social Login Key · JWKS · SLO", 662, 498)
    o += arrow(880, 470, 880, 570, "operatör realm rolleri", 868, 522, "end")
    # Keycloak → Press (kesikli dirsek)
    o.append("<path d='M612 470 L612 550 L300 550 L300 570' fill='none' stroke='var(--fs-line)' stroke-width='1.5' stroke-dasharray='5 5' marker-end='url(#arr)'/>")
    o.append(label("Social Login Key press", 320, 544))
    # Yatay sözleşmeler
    o.append("<text x='40' y='782' font-weight='650' fill='var(--fs-ink)'>Yatay sözleşmeler (Rail 1 ↔ Rail 2 ↔ Rail 6)</text>")
    o.append("<text x='40' y='808' fill='var(--fs-quiet)'>Press → Kiracı: site_config sk_&lt;app&gt;, plan_limit, Agent Job · Ops → Press: press.api.ops</text>")
    o.append("<text x='40' y='832' fill='var(--fs-quiet)'>Press → Ops: create-fc-invoice, delete-fc-team, press_ops_bridge olayları</text>")
    # Taban bantları
    o.append("<rect x='40' y='856' width='960' height='28' rx='6' fill='var(--fs-accent-soft)' stroke='var(--fs-accent)' stroke-width='1'/>")
    o.append("<text x='520' y='875' text-anchor='middle' fill='var(--fs-ink)'>Taban bandı 1 — Ortak sözleşmeler: Keycloak JWT · has_permission · tasarım tokenları · audit</text>")
    o.append("<rect x='40' y='892' width='960' height='28' rx='6' fill='var(--fs-tint)' stroke='var(--fs-grid)' stroke-width='1'/>")
    o.append("<text x='520' y='911' text-anchor='middle' fill='var(--fs-ink)'>Taban bandı 2 — Hetzner bare-metal, self-host (Hüseyin Cengiz) · DNS: GoDaddy → Route 53 (Asistan Hüseyin)</text>")
    o.append("</svg>")
    svg = "\n".join(o)
    return (
        "---\n// Mimari raylar diyagramı — scripts/gen-diagrams.py üretir; elle düzenlemeyin.\n---\n"
        '<figure class="diagram diagram-rails" tabindex="0" role="region" aria-label="Mimari raylar diyagramı (yatay kaydırılabilir)">\n'
        + svg
        + "\n<figcaption class=\"diagram-note\">Plan, fatura ve abonelik yalnızca Rail 1'de yazılır; DocType meta ve sidebar yalnızca Rail 2'den türer; muhasebe, cari ve ticket'ın tek doğrusu Rail 6'dır; her MCP aracı çağıran kullanıcının kimliğiyle aynı has_permission yolundan geçer.</figcaption>\n</figure>\n"
    )


if __name__ == "__main__":
    (ROOT / "src/components/Timeline.astro").write_text(timeline(), encoding="utf-8")
    (ROOT / "src/components/Rails.astro").write_text(rails(), encoding="utf-8")
    print("Timeline.astro ve Rails.astro yeniden üretildi")
