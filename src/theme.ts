import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from '@mantine/core';

// Visual identity: dark sea green primary colour, amber accent.
// All components derive from these tokens; no fixed colour is written inside a component.
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
  // In the light theme sea-8 (#077c6a): 5.1:1 on white — WCAG AA for text and fill.
  primaryShade: { light: 8, dark: 4 },
  colors: { sea, amber },
  // In filled components the text colour is chosen by luminance (e.g. dark text on amber).
  autoContrast: true,
  // Dark text on amber-7 (L≈0.38), white text on sea-8 / gray-7 (L<0.2).
  luminanceThreshold: 0.3,
  fontFamily:
    '"Outfit Variable", Outfit, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontFamilyMonospace:
    '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  headings: {
    fontFamily:
      '"Outfit Variable", Outfit, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    fontWeight: '650',
    sizes: {
      h1: { fontSize: '2rem', lineHeight: '1.2' },
      h2: { fontSize: '1.5rem', lineHeight: '1.3' },
      h3: { fontSize: '1.2rem', lineHeight: '1.35' },
      h4: { fontSize: '1.05rem', lineHeight: '1.4' },
    },
  },
  // Permanent rule: no readable text goes below 1rem.
  fontSizes: {
    xs: '1rem',
    sm: '1rem',
    md: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
  },
  lineHeights: { xs: '1.5', sm: '1.5', md: '1.5', lg: '1.65', xl: '1.7' },
  radius: { xs: '4px', sm: '6px', md: '10px', lg: '14px', xl: '20px' },
  defaultRadius: 'md',
  spacing: { xs: '0.5rem', sm: '0.75rem', md: '1rem', lg: '1.5rem', xl: '2.25rem' },
  focusRing: 'auto',
  cursorType: 'pointer',
  components: {
    Table: {
      defaultProps: { verticalSpacing: 'sm', horizontalSpacing: 'md', striped: 'odd' },
    },
    // Badge font size is a fixed px value in Mantine (lg = 13px); it is raised at token level for the 1rem rule.
    // Filled variant + autoContrast: avoids the 3.4:1 contrast of the light-coloured "light" variant.
    Badge: {
      defaultProps: { radius: 'sm', variant: 'filled', size: 'xl' },
      vars: () => ({ root: { '--badge-fz': '1rem', '--badge-height': '1.75rem', '--badge-padding-x': '0.6rem' } }),
    },
    Select: { defaultProps: { checkIconPosition: 'right', allowDeselect: true } },
  },
});

// Mantine's "dimmed" text (gray-6 / dark-2) does not meet AA contrast; the secondary text token is
// rebound to gray-7 (≈7:1) and dark-1 (≈8:1). --fs-quiet derives from this variable.
export const cssVariablesResolver: CSSVariablesResolver = (t) => ({
  variables: {},
  light: { '--mantine-color-dimmed': t.colors.gray[7] },
  dark: { '--mantine-color-dimmed': t.colors.dark[1] },
});
