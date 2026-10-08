import { useEffect } from 'react';

// Markdown'daki ```mermaid bloklarını (Shiki dışında bırakıldı) istemcide çizer;
// tema değişiminde yeniden çizer. Hata durumunda kaynak metin görünür kalır.
export default function Mermaid() {
  useEffect(() => {
    let disposed = false;
    const blocks = Array.from(document.querySelectorAll<HTMLElement>('pre > code.language-mermaid'));
    if (blocks.length === 0) return;

    const figures = blocks.map((code, i) => {
      const pre = code.parentElement as HTMLElement;
      const fig = document.createElement('figure');
      fig.className = 'mermaid-figure';
      fig.dataset.source = code.textContent ?? '';
      fig.dataset.index = String(i);
      fig.setAttribute('role', 'img');
      fig.setAttribute('aria-label', 'Akış diyagramı');
      pre.replaceWith(fig);
      return fig;
    });

    const render = async () => {
      const { default: mermaid } = await import('mermaid');
      if (disposed) return;
      const dark = document.documentElement.getAttribute('data-mantine-color-scheme') === 'dark';
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: dark ? 'dark' : 'neutral',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: 16,
        themeVariables: dark
          ? { primaryColor: '#0f8b78', primaryTextColor: '#e9f7f4', lineColor: '#8aa1a0', fontSize: '16px' }
          : { primaryColor: '#c7ebe6', primaryTextColor: '#0c2a26', lineColor: '#5f7372', fontSize: '16px' },
      });
      for (const fig of figures) {
        const src = fig.dataset.source ?? '';
        const id = `mermaid-${fig.dataset.index}-${dark ? 'd' : 'l'}`;
        try {
          const { svg } = await mermaid.render(id, src);
          if (disposed) return;
          fig.dataset.state = 'ok';
          fig.innerHTML = svg;
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
    const observer = new MutationObserver((muts) => {
      if (muts.some((m) => m.attributeName === 'data-mantine-color-scheme')) void render();
    });
    observer.observe(document.documentElement, { attributes: true });
    return () => {
      disposed = true;
      observer.disconnect();
    };
  }, []);
  return null;
}
