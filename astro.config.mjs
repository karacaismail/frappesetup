// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import { satteri } from '@astrojs/markdown-satteri';
import { tableWrap } from './src/lib/satteri-table-wrap.mjs';
import { pressAiDownloads } from './scripts/press-ai-downloads.mjs';
// GitHub Pages: https://karacaismail.github.io/frappesetup/
export default defineConfig({
  site: 'https://karacaismail.github.io',
  base: '/frappesetup',
  trailingSlash: 'always',
  // press-ai indirmeleri: public/downloads/press-ai/ derleme ve dev başında üretilir (gitignore'da).
  integrations: [react(), sitemap(), pressAiDownloads()],
  markdown: {
    // Astro 7 varsayılan işlemcisi Sätteri; tablolar hast eklentisiyle sarmalanır.
    processor: satteri({ hastPlugins: [tableWrap] }),
    // Mermaid blocks are rendered on the client by src/components/Mermaid.tsx;
    // Shiki must leave them as plain <pre><code class="language-mermaid">.
    syntaxHighlight: { type: 'shiki', excludeLangs: ['mermaid'] },
    shikiConfig: { themes: { light: 'github-light', dark: 'github-dark' } },
  },
});
