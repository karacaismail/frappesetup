import { useEffect } from 'react';

// Draws the ```mermaid blocks in Markdown (left out of Shiki) in the browser.
// - Reads colours from the page's design tokens and redraws when the theme changes.
// - The SVG width is fixed to its natural width (rem): text does not shrink below 1rem, the figure scrolls horizontally.
// - The accessible name comes from the preceding label paragraph or the heading and is unique on the page; the source text is kept in <details>.
export default function Mermaid() {
  useEffect(() => {
    let disposed = false;
    let renderSeq = 0;
    const blocks = Array.from(document.querySelectorAll<HTMLElement>('pre > code.language-mermaid'));
    if (blocks.length === 0) return;

    // Name: the bold-only label paragraph just before the block (e.g. **Login — …**) or the nearest heading.
    const labelBefore = (el: Element): string | null => {
      let node: Element | null = el;
      while (node) {
        let sib = node.previousElementSibling;
        while (sib) {
          const only = sib.children.length === 1 ? sib.firstElementChild : null;
          if (sib.tagName === 'P' && only?.tagName === 'STRONG' && sib.textContent?.trim() === only.textContent?.trim()) {
            return only.textContent?.trim() ?? null;
          }
          if (/^H[1-4]$/.test(sib.tagName)) return sib.textContent?.replace(/#\s*$/, '').trim() ?? null;
          sib = sib.previousElementSibling;
        }
        node = node.parentElement;
        if (!node || node.classList.contains('prose')) break;
      }
      return null;
    };
    // Region names must be unique on the page: if a name repeats, a sequence number is added.
    const used = new Map<string, number>();
    const uniqueLabel = (label: string) => {
      const n = (used.get(label) ?? 0) + 1;
      used.set(label, n);
      return n === 1 ? label : `${label} (${n})`;
    };

    const figures = blocks.map((code, i) => {
      const pre = code.parentElement as HTMLElement;
      const source = code.textContent ?? '';
      const fig = document.createElement('figure');
      fig.className = 'mermaid-figure';
      fig.dataset.source = source;
      fig.dataset.index = String(i);
      // Scrollable region: focusable for keyboard scrolling; the SVG itself is hidden, the name is on the figure.
      fig.setAttribute('role', 'region');
      fig.tabIndex = 0;
      const heading = labelBefore(pre);
      fig.setAttribute('aria-label', uniqueLabel(heading ? `Akış diyagramı: ${heading}` : `Akış diyagramı ${i + 1}`));

      const details = document.createElement('details');
      details.className = 'mermaid-details';
      const summary = document.createElement('summary');
      summary.textContent = 'Diyagram kaynağı (metin)';
      const srcPre = document.createElement('pre');
      srcPre.textContent = source;
      details.append(summary, srcPre);

      pre.replaceWith(fig, details);
      return fig;
    });

    const token = (name: string, fallback: string) => {
      const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return value || fallback;
    };

    const render = async () => {
      const seq = ++renderSeq;
      const { default: mermaid } = await import('mermaid');
      if (disposed || seq !== renderSeq) return;
      const dark = document.documentElement.getAttribute('data-mantine-color-scheme') === 'dark';
      const ink = token('--fs-ink', dark ? '#e9f7f4' : '#0c2a26');
      const line = token('--fs-line', dark ? '#8aa1a0' : '#5f7372');
      const tint = token('--fs-tint', dark ? '#2e2e2e' : '#f1f3f5');
      const surface2 = token('--fs-surface-2', dark ? '#2b2b2b' : '#f8f9fa');
      const accent = token('--fs-accent', dark ? '#45b3a3' : '#077c6a');
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        fontFamily: token('--mantine-font-family', '"Outfit Variable", Outfit, system-ui, sans-serif'),
        fontSize: 16,
        // 1rem rule: the diagram types' own default font sizes (12–14px) are raised to 16.
        sequence: { actorFontSize: 16, noteFontSize: 16, messageFontSize: 16, wrap: true },
        flowchart: { htmlLabels: false },
        gantt: { fontSize: 16, sectionFontSize: 16 },
        themeVariables: {
          fontSize: '16px',
          darkMode: dark,
          background: token('--fs-surface', dark ? '#1f1f1f' : '#ffffff'),
          primaryColor: token(dark ? '--mantine-color-sea-9' : '--mantine-color-sea-1', dark ? '#006b5b' : '#c7ebe6'),
          primaryTextColor: ink,
          primaryBorderColor: accent,
          secondaryColor: tint,
          secondaryTextColor: ink,
          tertiaryColor: surface2,
          tertiaryTextColor: ink,
          lineColor: line,
          textColor: ink,
          noteBkgColor: tint,
          noteTextColor: ink,
          actorBkg: surface2,
          actorBorder: accent,
          actorTextColor: ink,
          signalColor: line,
          signalTextColor: ink,
          labelBoxBkgColor: tint,
          labelTextColor: ink,
          loopTextColor: ink,
        },
      });
      for (const fig of figures) {
        const src = fig.dataset.source ?? '';
        const id = `mermaid-${fig.dataset.index}-${seq}`;
        try {
          const { svg } = await mermaid.render(id, src);
          if (disposed || seq !== renderSeq) return;
          // The SVG is sized in memory first, then placed in one go (the scale is never < 1 in between).
          const tpl = document.createElement('template');
          tpl.innerHTML = svg.trim();
          const el = tpl.content.querySelector('svg');
          if (el) {
            // Natural width (viewBox unit = px @16px root): fix it in rem → text ≥ 1rem.
            const vbWidth = el.viewBox.baseVal.width;
            if (vbWidth > 0) {
              const rem = vbWidth / 16;
              el.style.minWidth = `${rem}rem`;
              el.style.maxWidth = `${rem}rem`;
              el.style.width = `${rem}rem`;
            }
            // Sequence numbers (autonumber) are a fixed 12px in mermaid; they are raised to 16px for the 1rem rule
            // and the marker circle is enlarged.
            el.querySelectorAll<SVGTextElement>('text.sequenceNumber').forEach((t) => {
              t.setAttribute('font-size', '16px');
              t.removeAttribute('font-family');
              const y = parseFloat(t.getAttribute('y') ?? '0');
              t.setAttribute('y', String(y + 1.5));
            });
            el.querySelectorAll('marker[id$="-sequencenumber"] circle').forEach((c) => c.setAttribute('r', '11'));
            el.setAttribute('aria-hidden', 'true');
            fig.replaceChildren(el);
          } else {
            fig.innerHTML = svg;
          }
          fig.dataset.state = 'ok';
        } catch (err) {
          fig.dataset.state = 'error';
          const pre = document.createElement('pre');
          pre.textContent = src;
          fig.replaceChildren(pre);
          console.error('mermaid', err);
        }
      }
    };

    void render();
    const observer = new MutationObserver(() => void render());
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-mantine-color-scheme'] });
    return () => {
      disposed = true;
      observer.disconnect();
    };
  }, []);
  return null;
}
