(function () {
  'use strict';

  // Menú móvil
  var menuBtn = document.getElementById('menuBtn');
  var sidebar = document.getElementById('sidebar');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', function () { sidebar.classList.toggle('open'); });
    document.addEventListener('click', function (e) {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== menuBtn) {
        sidebar.classList.remove('open');
      }
    });
  }

  // Mensajes flash
  document.querySelectorAll('.flash').forEach(function (el) {
    var close = el.querySelector('.flash-close');
    if (close) close.addEventListener('click', function () { el.remove(); });
    if (el.hasAttribute('data-autodismiss')) {
      setTimeout(function () {
        el.style.transition = 'opacity .4s'; el.style.opacity = '0';
        setTimeout(function () { el.remove(); }, 450);
      }, 6000);
    }
  });
  // Limpia el mensaje de la URL para que no reaparezca al recargar
  if (location.search.indexOf('msg=') !== -1 && window.history.replaceState) {
    var p = new URLSearchParams(location.search); p.delete('msg'); p.delete('t');
    var qs = p.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
  }

  // Confirmación en acciones destructivas
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (!window.confirm(f.getAttribute('data-confirm'))) e.preventDefault();
    });
  });

  // Dropdown
  document.querySelectorAll('.dropdown').forEach(function (dd) {
    var btn = dd.querySelector('[data-dropdown]');
    btn.addEventListener('click', function (e) { e.stopPropagation(); dd.classList.toggle('open'); });
    document.addEventListener('click', function () { dd.classList.remove('open'); });
  });

  // Contadores animados
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var target = parseInt(el.getAttribute('data-count'), 10) || 0;
    if (target === 0 || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var start = null, dur = 700;
    function step(ts) {
      if (start === null) start = ts;
      var k = Math.min((ts - start) / dur, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(step);
    }
    el.textContent = '0';
    requestAnimationFrame(step);
  });

  // Validación en vivo del formulario de medicamentos
  var form = document.getElementById('med-form');
  if (form) {
    var DIAS = parseInt(form.getAttribute('data-dias-alerta'), 10);
    if (isNaN(DIAS)) DIAS = 90;
    var fecha = document.getElementById('fecha_caducidad');
    var hintF = document.getElementById('hint-fecha');
    var act = document.getElementById('stock_actual');
    var min = document.getElementById('stock_minimo');
    var max = document.getElementById('stock_maximo');
    var hintS = document.getElementById('hint-stock');
    function setHint(el, text, cls) { el.textContent = text; el.className = 'hint ' + (cls || ''); }
    function checkFecha() {
      if (!fecha.value) return setHint(hintF, '');
      var d = new Date(fecha.value + 'T00:00:00'), hoy = new Date(); hoy.setHours(0, 0, 0, 0);
      var dias = Math.round((d - hoy) / 86400000);
      if (dias < 0) setHint(hintF, 'Caducado hace ' + (-dias) + ' día(s)', 'bad');
      else if (dias <= DIAS) setHint(hintF, 'Caduca en ' + dias + ' día(s) — se marcará en rojo', 'bad');
      else setHint(hintF, 'Caduca en ' + dias + ' días', 'good');
    }
    function checkStock() {
      var a = parseInt(act.value, 10), mi = parseInt(min.value, 10), ma = parseInt(max.value, 10);
      if (!isNaN(mi) && !isNaN(ma) && mi > ma) return setHint(hintS, 'El mínimo no puede ser mayor que el máximo.', 'bad');
      if (!isNaN(a) && !isNaN(mi) && a < mi) return setHint(hintS, 'Stock por debajo del mínimo — se marcará en rojo.', 'bad');
      if (!isNaN(a) && !isNaN(ma) && a > ma) return setHint(hintS, 'Stock por encima del máximo — se marcará como sobrestock.', 'warn');
      setHint(hintS, '');
    }
    [fecha].forEach(function (e) { e.addEventListener('input', checkFecha); });
    [act, min, max].forEach(function (e) { e.addEventListener('input', checkStock); });
    checkFecha(); checkStock();
  }

  // Análisis con Ollama
  var btnIA = document.getElementById('btn-ia');
  if (btnIA) {
    var out = document.getElementById('ai-result');
    btnIA.addEventListener('click', function () {
      var label = btnIA.textContent;
      btnIA.disabled = true;
      btnIA.innerHTML = '<span class="spinner"></span> Analizando…';
      out.hidden = false; out.className = 'ai-result'; out.textContent = 'Consultando al modelo local, esto puede tardar unos segundos…';
      fetch('/api/ai/analisis', { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.body.detail || 'Error al generar el análisis');
          out.textContent = res.body.analisis;
          var meta = document.createElement('span');
          meta.className = 'ai-meta';
          meta.textContent = (res.body.modelo ? 'Modelo: ' + res.body.modelo + ' · ' : '') +
            res.body.caducan + ' por caducar · ' + res.body.criticos + ' con stock crítico';
          out.appendChild(meta);
        })
        .catch(function (err) { out.className = 'ai-result error'; out.textContent = err.message; })
        .finally(function () { btnIA.disabled = false; btnIA.textContent = label; });
    });
  }
})();
