// Central keyboard focus mode for the account console.
// The mode starts off. Only Tab and Shift+Tab turn it on. Pointer and touch input turn it off.
// The focus indicators in atonota-account.css depend on this state and on :focus-visible.
// This script never moves focus, never calls blur() and never blocks a key.
const root = document.documentElement;
root.setAttribute('data-at-js', '');

document.addEventListener(
  'keydown',
  (event) => {
    if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey) {
      root.setAttribute('data-at-focus', 'keyboard');
    }
  },
  true,
);

const pointerMode = () => root.removeAttribute('data-at-focus');

document.addEventListener('pointerdown', pointerMode, true);
document.addEventListener('touchstart', pointerMode, { capture: true, passive: true });

// Brand name. The stock console shows only a logo image. The page title holds the brand name
// (theme property "title", filled from the IDENTITY_BRAND_NAME variable).
// The name is handed to the stylesheet as a custom property and drawn there as a pseudo-element,
// so the console markup stays untouched and React re-renders cannot remove it.
root.style.setProperty('--at-brand-name', JSON.stringify(document.title));
