// Sätteri hast eklentisi: markdown tablolarını yatay kaydırılabilir bir sarmalayıcıya alır.
// Sarmalayıcı klavyeyle kaydırılabilsin diye odaklanabilir (WebKit kaydırıcıları
// kendiliğinden odaklanabilir yapmaz); gösterge yalnız :focus-visible'da çıkar.
export const tableWrap = {
  name: 'table-wrap',
  element: {
    filter: ['table'],
    visit(node, ctx) {
      ctx.wrapNode(node, {
        type: 'element',
        tagName: 'div',
        properties: {
          className: ['table-wrap'],
          tabIndex: 0,
          role: 'region',
          ariaLabel: 'Yatay kaydırılabilir tablo',
        },
        children: [],
      });
    },
  },
};
