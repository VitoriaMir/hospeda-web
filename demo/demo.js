/* Modo demonstração: roda apenas na versão estática publicada no GitHub Pages.
   Nada é enviado a servidor; ações de escrita mostram um aviso e filtros são
   aplicados localmente sobre as tabelas da página. */
(function () {
  var ROUTES = window.DEMO_ROUTES || {};
  var meta = document.querySelector('meta[name="demo-path"]');
  var here = meta ? meta.content.split('?')[0] : '';
  var REPO_URL = 'https://github.com/VitoriaMir/conpec-web';

  // Página acessada com parâmetros (ex.: aba de despesas): usa a variante pré-gerada.
  if (location.search) {
    var target = ROUTES[here + decodeURIComponent(location.search)];
    if (target) location.replace(target + location.hash);
  }

  var toastTimer;
  function toast(message) {
    var el = document.getElementById('demoToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'demoToast';
      el.className = 'demo-toast';
      el.setAttribute('role', 'status');
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, 3600);
  }

  function normalize(value) {
    return String(value || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  }

  function filterTables(form) {
    var terms = [], prefix = '';
    form.querySelectorAll('input, select').forEach(function (field) {
      var type = (field.getAttribute('type') || 'text').toLowerCase();
      if (!field.value || /period/i.test(field.name)) return;
      if (field.name === 'block') prefix = normalize(field.value);
      else if (field.tagName === 'SELECT' || type === 'text' || type === 'search') terms.push(normalize(field.value));
    });
    var scope = form.closest('.card, section, .tab-panel') || document;
    var items = scope.querySelectorAll('tbody tr, .room-grid .room');
    if (!items.length) items = document.querySelectorAll('tbody tr, .room-grid .room');
    items.forEach(function (item) {
      var text = normalize(item.textContent);
      var label = item.querySelector('b');
      item.hidden = normalize(label ? label.textContent : text).indexOf(prefix) !== 0 ||
        !terms.every(function (term) { return text.indexOf(term) !== -1; });
    });
  }

  function handleForm(form) {
    if (form.closest('.login-card')) {
      location.href = 'dashboard.html';
      return;
    }
    if ((form.getAttribute('method') || 'get').toLowerCase() === 'get') {
      var params = new URLSearchParams();
      new FormData(form).forEach(function (value, key) { if (value) params.append(key, value); });
      var query = params.toString();
      var target = ROUTES[here + (query ? '?' + decodeURIComponent(query) : '')];
      if (target && target !== location.pathname.split('/').pop()) {
        location.href = target;
      } else {
        filterTables(form);
      }
      return;
    }
    document.querySelectorAll('.modal.show').forEach(function (modal) { modal.classList.remove('show'); });
    toast('Modo demonstração: nenhuma alteração é salva. Na versão instalada, esta ação grava os dados.');
  }

  window.addEventListener('submit', function (event) {
    event.preventDefault();
    event.stopPropagation();
    handleForm(event.target);
  }, true);
  HTMLFormElement.prototype.submit = function () { handleForm(this); };
  HTMLFormElement.prototype.requestSubmit = function () { handleForm(this); };

  var nativeFetch = window.fetch;
  window.fetch = function (resource, options) {
    var method = ((options && options.method) || 'GET').toUpperCase();
    if (method === 'GET') return nativeFetch.apply(this, arguments);
    var body = JSON.stringify({ ok: false, message: 'Modo demonstração: alterações não são salvas.' });
    return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } }));
  };

  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[href="#demo"]');
    if (!link) return;
    event.preventDefault();
    toast('Esta ação está disponível na versão instalada do sistema.');
  }, true);

  document.addEventListener('DOMContentLoaded', function () {
    var bar = document.createElement('div');
    bar.className = 'demo-bar';
    bar.innerHTML = '<span><b>Demonstração</b> · dados fictícios, nada é salvo</span>' +
      '<nav><a href="index.html">Sobre o projeto</a><a href="' + REPO_URL + '" target="_blank" rel="noopener">Código no GitHub</a></nav>';
    document.body.insertBefore(bar, document.body.firstChild);
    document.body.classList.add('has-demo-bar');

    var password = document.querySelector('.login-card input[type="password"]');
    if (password) {
      password.value = 'admin123';
      var help = document.querySelector('.login-help');
      if (help) help.textContent = 'Demonstração: basta clicar em Entrar.';
    }
  });
})();
