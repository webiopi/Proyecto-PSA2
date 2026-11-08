(function () {
  'use strict';
  var modal = document.getElementById('modal-pedido');
  var abrir = document.getElementById('btn-pedido');
  if (!modal || !abrir) return;

  var $ = function (id) { return document.getElementById(id); };
  var inBuscar = $('ped-buscar'), resultados = $('ped-resultados'), listaItems = $('ped-items'),
      vacio = $('ped-vacio'), btnEnviar = $('ped-enviar'), errBox = $('ped-error'),
      btnSug = $('ped-sugerir'), iaBox = $('ped-ia'), inDol = $('ped-dolencia'), inNotas = $('ped-notas');
  var items = {};   // id -> {med, cantidad}
  var timer = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function showError(msg) { errBox.hidden = !msg; errBox.textContent = msg || ''; }

  function abrirModal() { modal.hidden = false; inBuscar.focus(); buscar(); }
  function cerrarModal() { modal.hidden = true; }
  abrir.addEventListener('click', abrirModal);
  modal.querySelectorAll('[data-close]').forEach(function (b) { b.addEventListener('click', cerrarModal); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !modal.hidden) cerrarModal(); });

  function medInfo(m) {
    var d = el('div');
    d.appendChild(el('strong', null, m.nombre));
    d.appendChild(el('small', null, m.principio_activo + ' · lote ' + m.lote + ' · cad. ' + m.caducidad + ' · stock ' + m.stock));
    return d;
  }

  function agregar(m) {
    if (items[m.id]) items[m.id].cantidad = Math.min(items[m.id].cantidad + 1, m.stock);
    else items[m.id] = { med: m, cantidad: 1 };
    pintarItems();
  }

  function filaMed(m) {
    var li = el('li');
    li.appendChild(medInfo(m));
    var b = el('button', 'btn btn-sm btn-ghost', 'Agregar');
    b.type = 'button';
    b.addEventListener('click', function () { agregar(m); });
    li.appendChild(b);
    return li;
  }

  function pintarItems() {
    listaItems.textContent = '';
    var ids = Object.keys(items);
    vacio.hidden = ids.length > 0;
    btnEnviar.disabled = ids.length === 0;
    ids.forEach(function (id) {
      var it = items[id], li = el('li');
      li.appendChild(medInfo(it.med));
      var acc = el('div', 'ped-row-actions');
      var q = el('input', 'ped-qty'); q.type = 'number'; q.min = 1; q.max = it.med.stock; q.value = it.cantidad;
      q.setAttribute('aria-label', 'Cantidad de ' + it.med.nombre);
      q.addEventListener('input', function () {
        var v = parseInt(q.value, 10);
        it.cantidad = isNaN(v) ? 0 : Math.max(0, Math.min(v, it.med.stock));
      });
      var x = el('button', 'btn btn-sm btn-danger-ghost', '✕'); x.type = 'button'; x.setAttribute('aria-label', 'Quitar');
      x.addEventListener('click', function () { delete items[id]; pintarItems(); });
      acc.appendChild(q); acc.appendChild(x); li.appendChild(acc);
      listaItems.appendChild(li);
    });
  }

  function buscar() {
    fetch('/api/ordenes/buscar?q=' + encodeURIComponent(inBuscar.value), { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (j) {
        resultados.textContent = '';
        if (!j.items.length) resultados.appendChild(el('li', 'empty', 'Sin resultados con stock disponible.'));
        j.items.forEach(function (m) { resultados.appendChild(filaMed(m)); });
      })
      .catch(function () { resultados.textContent = ''; resultados.appendChild(el('li', 'empty', 'No se pudo buscar.')); });
  }
  inBuscar.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(buscar, 250); });

  function sugerir() {
    var texto = inDol.value.trim();
    if (texto.length < 3) { iaBox.hidden = false; iaBox.className = 'ai-result error'; iaBox.textContent = 'Describe la dolencia.'; return; }
    var label = btnSug.textContent;
    btnSug.disabled = true; btnSug.innerHTML = '<span class="spinner"></span> Consultando…';
    iaBox.hidden = false; iaBox.className = 'ai-result'; iaBox.textContent = 'Consultando al modelo local…';
    fetch('/api/ordenes/sugerir', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dolencia: texto })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.body.detail || 'Error al consultar la IA');
        iaBox.textContent = res.body.explicacion || '';
        var box = el('div', 'ped-sug');
        res.body.sugeridos.forEach(function (m) { box.appendChild(filaMed(m)); });
        iaBox.appendChild(box);
        iaBox.appendChild(el('span', 'ai-meta', 'Sugerencia orientativa: valida siempre con tu criterio clínico.'));
      })
      .catch(function (err) { iaBox.className = 'ai-result error'; iaBox.textContent = err.message; })
      .finally(function () { btnSug.disabled = false; btnSug.textContent = label; });
  }
  btnSug.addEventListener('click', sugerir);
  inDol.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); sugerir(); } });

  btnEnviar.addEventListener('click', function () {
    showError('');
    var payload = Object.keys(items).map(function (id) {
      return { medicamento_id: parseInt(id, 10), cantidad: items[id].cantidad };
    });
    if (payload.some(function (p) { return p.cantidad < 1; })) { showError('Todas las cantidades deben ser al menos 1.'); return; }
    btnEnviar.disabled = true;
    fetch('/api/ordenes', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: payload, notas: inNotas.value })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.body.detail || 'No se pudo crear el pedido');
        var p = new URLSearchParams({ msg: 'Pedido #' + res.body.id + ' enviado al farmacéutico.', t: 'ok' });
        window.location.href = '/inventario?' + p.toString();
      })
      .catch(function (err) { showError(err.message); btnEnviar.disabled = false; });
  });
})();
