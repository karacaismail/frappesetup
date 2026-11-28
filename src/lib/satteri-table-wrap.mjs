// Sätteri hast plugin: puts markdown tables into a horizontally scrollable wrapper.
// The wrapper is focusable so it can be scrolled with the keyboard (WebKit does not make
// scrollers focusable by itself); the indicator appears only on :focus-visible.
// Each region (role=region) has a unique name on the page: the nearest preceding heading + its index under the same heading.
export const tableWrap = {
  name: 'table-wrap',
  element: {
    filter: ['table'],
    visit(node, ctx) {
      const parent = ctx.parent(node);
      const index = ctx.indexOf(node);
      let heading = '';
      let nth = 1;
      if (parent && index !== undefined) {
        for (let i = index - 1; i >= 0; i--) {
          const sib = parent.children[i];
          if (!sib || sib.type !== 'element') continue;
          const wrapped = sib.tagName === 'div' && String(sib.properties?.className ?? '').includes('table-wrap');
          if (sib.tagName === 'table' || wrapped) {
            nth += 1;
            continue;
          }
          if (/^h[2-4]$/.test(sib.tagName)) {
            heading = ctx.textContent(sib).trim();
            break;
          }
        }
      }
      const base = heading ? `Tablo: ${heading}` : 'Tablo';
      ctx.wrapNode(node, {
        type: 'element',
        tagName: 'div',
        properties: {
          className: ['table-wrap'],
          tabIndex: 0,
          role: 'region',
          ariaLabel: `${nth > 1 || !heading ? `${base} ${nth}` : base} (yatay kaydırılabilir)`,
        },
        children: [],
      });
    },
  },
};
