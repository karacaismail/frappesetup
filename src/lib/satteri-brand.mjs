import { createHash } from 'node:crypto';
import { fillBrand } from './brand.mjs';

/** Fill HAST text rather than raw HTML so the serializer escapes brand values. */
export function brandPlaceholders(brand) {
  // Astro hashes serializable processor options, not closed-over function values.
  // Include the public setting in that digest so unchanged Markdown is re-rendered.
  const digest = createHash('sha256').update(JSON.stringify(brand)).digest('hex');
  return {
    name: `brand-placeholders-${digest}`,
    before(root, ctx) {
      function visit(node) {
        if (node.type === 'text') {
          const value = fillBrand(node.value, brand);
          if (value !== node.value) ctx.setField(node, 'value', value);
          return;
        }
        if (node.type === 'element' && node.tagName === 'code') {
          const leaves = [];
          function collect(child) {
            if (child.type === 'text') leaves.push(child);
            else for (const nested of child.children ?? []) collect(nested);
          }
          collect(node);
          const source = leaves.map(leaf => leaf.value).join('');
          const mermaid = node.properties?.className?.includes('language-mermaid');
          const values = mermaid ? {
            ...brand,
            // Mermaid entities keep label punctuation out of the diagram grammar.
            PRODUCT_NAME: brand.PRODUCT_NAME.replace(/[&<>"'{}\[\]():;|#\\]/g, char => `#${char.codePointAt(0)};`),
          } : brand;
          const matches = [...source.matchAll(/\{\{(PRODUCT_NAME|BRAND_DOMAIN)\}\}/g)].reverse();
          let offset = 0;
          for (const leaf of leaves) {
            let value = leaf.value;
            const end = offset + value.length;
            for (const match of matches) {
              const start = Math.max(offset, match.index);
              const stop = Math.min(end, match.index + match[0].length);
              if (start >= stop) continue;
              value = value.slice(0, start - offset)
                + (match.index >= offset ? values[match[1]] : '')
                + value.slice(stop - offset);
            }
            if (value !== leaf.value) ctx.setField(leaf, 'value', value);
            offset = end;
          }
          return;
        }
        for (const key of ['href', 'src', 'title', 'alt']) {
          const value = node.properties?.[key];
          if (typeof value !== 'string') continue;
          const decoded = value.replace(/%7B%7B(PRODUCT_NAME|BRAND_DOMAIN)%7D%7D/gi, '{{$1}}');
          const filled = fillBrand(decoded, brand);
          if (filled !== value) ctx.setProperty(node, key, filled);
        }
        for (const child of node.children ?? []) visit(child);
      }
      visit(root);
    },
  };
}
