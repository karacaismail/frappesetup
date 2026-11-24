const root = document.documentElement;

document.addEventListener('keydown', (event) => {
  if (event.key === 'Tab') root.setAttribute('data-keyboard-focus', '');
});

function usePointerFocus() {
  root.removeAttribute('data-keyboard-focus');
}

document.addEventListener('pointerdown', usePointerFocus, { passive: true });
document.addEventListener('touchstart', usePointerFocus, { passive: true });
