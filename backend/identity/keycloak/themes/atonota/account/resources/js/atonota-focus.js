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

// Accessibility repairs for the stock console markup.
// The console renders some overflow-menu toggles (three dots) without an accessible name, and the title of an
// inline alert as a fourth-level heading right under a first-level one. A theme cannot change the console
// markup, so the missing attributes are added here. The names come from the theme message bundle
// (keys "atAccountMenu" and "atMoreActions"), so they are translated like every other text.
const environment = JSON.parse(document.getElementById('environment')?.textContent ?? '{}');
const messagesUrl = `${environment.serverBaseUrl}/resources/${environment.realm}/account/${environment.locale}`;

const repair = (names) => {
  for (const toggle of document.querySelectorAll('button.pf-v5-c-menu-toggle.pf-m-plain:not([aria-label]):not([aria-labelledby])')) {
    if (toggle.textContent.trim() !== '') continue;
    if (toggle.closest('.pf-v5-c-masthead')) {
      toggle.setAttribute('aria-label', names.atAccountMenu);
      continue;
    }
    // A toggle in a section row is named after its section, for example "Passkey: More actions".
    const heading = toggle.closest('.pf-v5-l-split')?.querySelector('.pf-v5-c-title, h1, h2, h3')?.textContent.trim();
    toggle.setAttribute('aria-label', heading ? `${heading}: ${names.atMoreActions}` : names.atMoreActions);
  }
  for (const title of document.querySelectorAll('h4.pf-v5-c-alert__title:not([aria-level])')) {
    title.setAttribute('aria-level', '2');
  }
};

try {
  const response = await fetch(messagesUrl, { credentials: 'same-origin' });
  if (response.ok) {
    const names = Object.fromEntries((await response.json()).map((entry) => [entry.key, entry.value]));
    if (names.atAccountMenu && names.atMoreActions) {
      repair(names);
      // The console draws its pages after this script runs and redraws them on navigation.
      new MutationObserver(() => repair(names)).observe(document.body, { childList: true, subtree: true });
    }
  }
} catch {
  // Without the names the toggles stay as the stock console draws them. Nothing else depends on this request.
}
