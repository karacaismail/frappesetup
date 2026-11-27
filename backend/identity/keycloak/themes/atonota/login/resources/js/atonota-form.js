// Boş alan denetimi (AJA-1125).
// Keycloak boş formu "e-posta ya da parola yanlış" diye bildirir. Bu betik formu göndermeden önce
// boş alanı bulur ve hatayı o alanın altına yazar. Metinler formun data-at-empty-* özniteliklerinden gelir.
// Hata alanın erişilebilir açıklamasıdır (aria-describedby). İlk boş alan odak alır.
// Betik çalışmazsa sunucu yine boş e-posta alanını adıyla bildirir (login.ftl).
(function () {
  var ERROR_CLASS = 'pf-m-error';

  function fieldParts(form, name) {
    var input = form.querySelector('[name="' + name + '"]');
    if (!input) return null;
    return {
      input: input,
      control: input.closest('.pf-v5-c-form-control'),
      container: document.getElementById('input-error-container-' + name),
    };
  }

  function describe(input, id, on) {
    var ids = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    ids = ids.filter(function (value) { return value !== id; });
    if (on) ids.push(id);
    if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
    else input.removeAttribute('aria-describedby');
  }

  function clearError(parts, name) {
    var id = 'input-error-' + name;
    if (parts.container) parts.container.textContent = '';
    parts.input.setAttribute('aria-invalid', '');
    if (parts.control) parts.control.classList.remove(ERROR_CLASS);
    describe(parts.input, id, false);
  }

  // Aynı yapıyı Keycloak'ın field.ftl şablonu da sunucu hatası için kurar.
  function showError(parts, name, text) {
    var id = 'input-error-' + name;
    var helper = document.createElement('div');
    helper.className = 'pf-v5-c-form__helper-text';
    var list = document.createElement('div');
    list.className = 'pf-v5-c-helper-text';
    var item = document.createElement('div');
    item.className = 'pf-v5-c-helper-text__item ' + ERROR_CLASS;
    item.id = id;
    var span = document.createElement('span');
    span.className = 'pf-v5-c-helper-text__item-text pf-m-error kc-feedback-text';
    span.textContent = text;
    item.appendChild(span);
    list.appendChild(item);
    helper.appendChild(list);
    parts.container.textContent = '';
    parts.container.appendChild(helper);
    parts.input.setAttribute('aria-invalid', 'true');
    if (parts.control) parts.control.classList.add(ERROR_CLASS);
    describe(parts.input, id, true);
  }

  function requiredNames(form) {
    return (form.getAttribute('data-at-required') || '').split(/\s+/).filter(Boolean);
  }

  function prepare() {
    var forms = document.querySelectorAll('form[data-at-required]');
    for (var i = 0; i < forms.length; i += 1) {
      var names = requiredNames(forms[i]);
      for (var j = 0; j < names.length; j += 1) {
        var parts = fieldParts(forms[i], names[j]);
        if (!parts || !parts.container) continue;
        // Bölge baştan durur. Sonradan yazılan hata ekran okuyucuda okunur.
        parts.container.setAttribute('aria-live', 'polite');
        // Sunucunun yazdığı hata da alanın açıklaması olur.
        if (document.getElementById('input-error-' + names[j])) describe(parts.input, 'input-error-' + names[j], true);
      }
    }
  }

  document.addEventListener(
    'submit',
    function (event) {
      var form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-at-required')) return;
      var names = requiredNames(form);
      var firstEmpty = null;
      var checked = [];
      for (var i = 0; i < names.length; i += 1) {
        var parts = fieldParts(form, names[i]);
        // Gizli ya da görünmeyen alan denetlenmez. Örneğin yeniden girişte e-posta yalnız yazıdır.
        if (!parts || !parts.container || parts.input.type === 'hidden' || !parts.input.offsetParent) continue;
        var value = parts.input.type === 'password' ? parts.input.value : parts.input.value.trim();
        checked.push({ parts: parts, name: names[i], empty: value === '' });
      }
      var anyEmpty = checked.some(function (field) { return field.empty; });
      if (!anyEmpty) return;
      // Form gönderilmez. Formun kendi onsubmit kuralı da çalışmaz, böylece düğme açık kalır.
      event.preventDefault();
      event.stopImmediatePropagation();
      for (var j = 0; j < checked.length; j += 1) {
        var field = checked[j];
        clearError(field.parts, field.name);
        if (field.empty) {
          showError(field.parts, field.name, form.getAttribute('data-at-empty-' + field.name) || '');
          if (!firstEmpty) firstEmpty = field.parts.input;
        }
      }
      if (firstEmpty) firstEmpty.focus();
    },
    true
  );

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', prepare);
  else prepare();
})();
