import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Görsel kimlik: koyu deniz yeşili birincil renk, kehribar vurgu.
// Tüm bileşenler bu tokenlardan türer; bileşen içinde sabit renk yazılmaz.
const sea: MantineColorsTuple = [
  '#e6f7f5',
  '#c7ebe6',
  '#9dd9d0',
  '#6ec5b8',
  '#45b3a3',
  '#2aa693',
  '#1c9f8b',
  '#0f8b78',
  '#077c6a',
  '#006b5b',
];

const amber: MantineColorsTuple = [
  '#fff7e6',
  '#ffebc2',
  '#ffdb94',
  '#ffc95f',
  '#ffba35',
  '#ffb11b',
  '#ffac0a',
  '#e39600',
  '#ca8500',
  '#af7200',
];

export const theme = createTheme({
  primaryColor: 'sea',
  primaryShade: { light: 7, dark: 4 },
  colors: { sea, amber },
  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontFamilyMonospace:
    '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  headings: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    fontWeight: '650',
    sizes: {
      h1: { fontSize: '2rem', lineHeight: '1.2' },
      h2: { fontSize: '1.5rem', lineHeight: '1.3' },
      h3: { fontSize: '1.2rem', lineHeight: '1.35' },
      h4: { fontSize: '1.05rem', lineHeight: '1.4' },
    },
  },
  // Kalıcı kural: okunabilir hiçbir metin 1rem altına inmez.
  fontSizes: {
    xs: '1rem',
    sm: '1rem',
    md: '1.0625rem',
    lg: '1.125rem',
    xl: '1.25rem',
  },
  lineHeights: { xs: '1.5', sm: '1.5', md: '1.6', lg: '1.65', xl: '1.7' },
  radius: { xs: '4px', sm: '6px', md: '10px', lg: '14px', xl: '20px' },
  defaultRadius: 'md',
  spacing: { xs: '0.5rem', sm: '0.75rem', md: '1rem', lg: '1.5rem', xl: '2.25rem' },
  focusRing: 'auto',
  cursorType: 'pointer',
  components: {
    Table: {
      defaultProps: { verticalSpacing: 'sm', horizontalSpacing: 'md', striped: 'odd' },
    },
    // Badge yazı boyutu Mantine'de sabit px'tir (lg = 13px); 1rem kuralı için token düzeyinde yükseltilir.
    Badge: {
      defaultProps: { radius: 'sm', variant: 'light', size: 'xl' },
      vars: () => ({ root: { '--badge-fz': '1rem', '--badge-height': '1.75rem', '--badge-padding-x': '0.6rem' } }),
    },
    Select: { defaultProps: { checkIconPosition: 'right', allowDeselect: true } },
  },
});
