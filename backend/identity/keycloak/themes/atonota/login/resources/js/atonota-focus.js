// Merkezi klavye odak kipi.
// Kip kapalı başlar. Yalnız Tab ve Shift+Tab kipi açar. İşaretçi ve dokunma kipi kapatır.
// Odak göstergeleri atonota.css içinde bu duruma ve :focus-visible koşuluna bağlıdır.
// Bu betik odağı taşımaz, blur() çağırmaz ve hiçbir tuşu engellemez.
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
