// Central keyboard focus mode.
// The mode starts off. Only Tab and Shift+Tab turn it on. Pointer and touch turn it off.
// In atonota.css the focus indicators depend on this state and on :focus-visible.
// This script does not move focus, does not call blur() and does not block any key.
(function () {
  var root = document.documentElement;
  root.setAttribute('data-at-js', '');

  document.addEventListener(
    'keydown',
    function (event) {
      if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey) {
        root.setAttribute('data-at-focus', 'keyboard');
      }
    },
    true
  );

  function pointerMode() {
    root.removeAttribute('data-at-focus');
  }

  document.addEventListener('pointerdown', pointerMode, true);
  document.addEventListener('touchstart', pointerMode, { capture: true, passive: true });
})();
