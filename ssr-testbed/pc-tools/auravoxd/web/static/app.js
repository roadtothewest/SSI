// HMI AuraVox: recibe el stream SSE de auravoxd y dibuja en canvas (sin librerías).
'use strict';
const $ = id => document.getElementById(id);
const css = getComputedStyle(document.documentElement);
const C = ['--c0', '--c1', '--c2', '--c3'].map(v => css.getPropertyValue(v).trim());
const INK = { grid: '#2c2c2a', axis: '#383835', muted: '#898781', text2: '#c3c2b7' };
const CH = ['CH1', 'CH2', 'CH3'];
const COND = {
  desconectado: ['Desconectado', 'Electrodos sueltos'], reposo: ['Reposo', 'En silencio'],
  habla: ['Habla', 'Voz normal'], silenciosa: ['Silenciosa', 'Articular sin voz'], vocal: ['Vocal', 'Sostener una vocal'],
};
const nil = v => v === null || v === undefined || Number.isNaN(v);
const fmt = (v, d = 1) => nil(v) ? '—' : Number(v).toFixed(d);
const sgn = v => nil(v) ? '—' : (v > 0 ? '+' : '') + Math.round(v);
const DPR = () => window.devicePixelRatio || 1;

let I = null, R = null, tab = 'sig', CHS = [];
const ACT = () => [0, 1, 2].filter(ch => CHS[ch] && CHS[ch].on);
const chName = ch => CHS[ch] ? CHS[ch].name : CH[ch];
let NB = 0, waves = [], wpos = 0, cols = [], hop = 10;
let autoScale = [20, 20, 20, 0.5], fixedScale = 0, cmode = 'mag', delayAuto = true, lastRec = null, lastSrc = null;

// ------------------------------------------------------------ controles
const post = (url, body) => fetch(url, { method: 'POST', body: JSON.stringify(body) });
function seg(id, cb) {
  const bs = document.querySelectorAll(`#${id} button`);
  bs.forEach(b => b.onclick = () => { bs.forEach(x => x.classList.toggle('on', x === b)); cb(b.dataset.v); });
}
function setSeg(id, v) { document.querySelectorAll(`#${id} button`).forEach(b => b.classList.toggle('on', b.dataset.v === String(v))); }

document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.tab').forEach(s => s.classList.toggle('on', s.id === b.dataset.tab));
  tab = b.dataset.tab;
  history.replaceState(null, '', '#' + tab);
  if (tab === 'ses') { loadFiles(); if (lastML) drawMLInfo(lastML); }
  if (R && tab === 'cau') drawCausality(R);
});
{ const b = document.querySelector(`#tabs button[data-tab="${location.hash.slice(1)}"]`); if (b) b.click(); }
seg('scale', v => fixedScale = +v);
seg('cmode', v => { cmode = v; drawRamp(); });
seg('hop', v => post('/api/hop', { ms: +v }));
$('delay').oninput = e => { setAuto(false); $('delayv').textContent = e.target.value + ' ms'; };
$('delayauto').onclick = () => setAuto(!delayAuto);
function setAuto(on) { delayAuto = on; $('delayauto').classList.toggle('on', on); }
$('recbtn').onclick = () => post('/api/record', { on: !(lastRec && lastRec.active) });
$('resetbtn').onclick = () => post('/api/reset', {});
$('livebtn').onclick = () => setSource('');
$('files').onclick = e => {
  const b = e.target.closest('button');
  if (!b || b.disabled) return;
  const n = b.dataset.name;
  if (b.dataset.play !== undefined) setSource(n + '.avx');
  if (b.dataset.ren !== undefined) {
    const to = prompt(`Nuevo nombre para ${n}\n(letras, números, - y _; los espacios pasan a _)`, n);
    if (to === null || !to.trim() || to.trim() === n) return;
    sessionOp(post(`/api/files/${encodeURIComponent(n)}/rename`, { to }));
  }
  if (b.dataset.del !== undefined && confirm(`¿Borrar la grabación ${n}?\nSe eliminan su .avx y su .json. No se puede deshacer.`))
    sessionOp(fetch(`/api/files/${encodeURIComponent(n)}`, { method: 'DELETE' }));
};
function setSource(file) { // con el estado de la respuesta, la lista no espera al próximo evento SSE
  post('/api/source', { file }).then(r => r.ok ? r.json() : null).then(st => { if (st) lastSrc = st; loadFiles(); });
}
function sessionOp(req) {
  req.then(async r => { if (!r.ok) alert(await r.text()); }).catch(e => alert(e)).finally(loadFiles);
}

// ------------------------------------------------------------ stream SSE
const es = new EventSource('/api/stream');
es.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.fsEmg) { init(m); return; }
  if (!I) return;
  pushWaves(m);
  if (m.c) for (const c of m.c) cols.push(b64(c));
  const maxCols = I.showSecs * 1000 / hop + 400;
  if (cols.length > maxCols) cols.splice(0, cols.length - maxCols);
  if (m.chans) setChans(m.chans);
  if (m.ml) onML(m.ml);
  if (m.r) onResult(m.r, m.link, m.rec, m.src);
};
es.onerror = () => setLink('bad', 'Sin conexión');

function init(m) {
  I = m;
  NB = I.fsEmg / I.bucket * I.showSecs;
  waves = [0, 1, 2, 3].map(() => new Float32Array(2 * NB));
  wpos = 0; cols = [];
  $('condbtns').innerHTML = I.conds.map(c => { const [t, s] = COND[c] || [c, '']; return `<button data-c="${c}"><b>${t}</b><span>${s}</span></button>`; }).join('');
  document.querySelectorAll('#condbtns button').forEach(b => b.onclick = () => post('/api/condition', { cond: b.dataset.c }));
  setChans(I.chans, true);
  drawRamp();
}

// ------------------------------------------------------------ modelo
const ML_STATE = { 'sin-modelo': 'Sin modelo', cargando: 'Cargando…', activo: 'Activo', error: 'Error', apagado: 'Desactivado (-ml=false)' };
let lastML = null;
// Mostrar u ocultar el panel del modelo en Señales; se recuerda en este navegador.
let mlShow = true;
try { mlShow = localStorage.getItem('auravox.mlShow') !== '0'; } catch (e) { }
$('mltoggle').onclick = () => {
  mlShow = !mlShow;
  try { localStorage.setItem('auravox.mlShow', mlShow ? '1' : '0'); } catch (e) { }
  if (lastML) onML(lastML);
};
function onML(s) {
  lastML = s;
  const p = s.pred, on = s.state === 'activo' && p;
  $('mltoggle').hidden = !on;
  $('mltoggle').classList.toggle('on', mlShow);
  $('mltoggle').textContent = mlShow ? 'Ocultar modelo' : 'Mostrar modelo';
  $('mlbox').hidden = !on || !mlShow;
  if (on) {
    $('mlbox').classList.toggle('stale', p.stale);
    $('mlclase').textContent = p.clase;
    $('mlsub').textContent = p.stale ? 'sin señal nueva' : `${fmt(100 * Math.max(...p.probs), 0)} % · ${s.model}`;
    $('mlbars').innerHTML = s.clases.map((c, i) => `<div class="mlbar${c === p.clase ? ' on' : ''}">${esc(c)} ${fmt(100 * p.probs[i], 0)} %` +
      `<div><i style="width:${(100 * p.probs[i]).toFixed(1)}%"></i></div></div>`).join('');
  }
  if (tab === 'ses') drawMLInfo(s);
}
function drawMLInfo(s) {
  const row = (k, v, cls) => `<span>${k}</span><span${cls ? ` class="${cls}"` : ''}>${v}</span>`;
  $('mlinfo').innerHTML = row('Estado', ML_STATE[s.state] || s.state) +
    (s.err ? row('Error', esc(s.err), 'bad') : '') +
    (s.model ? row('Modelo', `${esc(s.model)}${s.fecha ? ' · ' + esc(s.fecha) : ''}`) +
      row('Clases', s.clases.map(esc).join(', ')) +
      row('Entrada', `${s.canal.map(c => CH[c]).join(', ')} · ventana ${s.winMs} ms`) +
      (s.accBal ? row('Validación', `exactitud balanceada ${fmt(100 * s.accBal, 0)} % (azar ${fmt(100 / s.clases.length, 0)} %)`) : '') +
      (s.ort ? row('onnxruntime', esc(s.ort)) : '') : '');
}
$('mlup').onclick = () => $('mlfile').click();
$('mlfile').onchange = () => {
  const f = $('mlfile').files[0];
  if (!f) return;
  $('mlmsg').textContent = `Probando ${f.name}…`; $('mlup').disabled = true;
  fetch('/api/ml/model', { method: 'POST', body: f }).then(async r => {
    $('mlmsg').textContent = r.ok ? `Instalado: ${(await r.json()).model}` : await r.text();
  }).catch(e => $('mlmsg').textContent = String(e)).finally(() => { $('mlup').disabled = false; $('mlfile').value = ''; });
};

// ------------------------------------------------------------ canales
function setChans(cs, force) {
  if (!cs || (!force && JSON.stringify(cs) === JSON.stringify(CHS))) return;
  CHS = cs;
  for (let ch = 0; ch < 3; ch++) {
    const on = CHS[ch].on;
    $('L' + ch).hidden = !on; $('H' + ch).hidden = !on;
    $('L' + ch).querySelector('.site').textContent = CHS[ch].name;
    $('H' + ch).querySelector('.tag').textContent = `${CH[ch]} · ${CHS[ch].name}`;
  }
  $('keys').innerHTML = ACT().map(ch => `<span style="--k:${C[ch]}"><i></i>${CH[ch]} ${esc(chName(ch))}</span>`).join('');
  if (!$('chans').contains(document.activeElement)) drawChanEditor();
}
function drawChanEditor() {
  $('chans').innerHTML = CHS.map((c, ch) =>
    `<label style="--k:${C[ch]}"><b><i></i>${CH[ch]}</b><input type="checkbox" data-k="on"${c.on ? ' checked' : ''} title="Conectado">` +
    `<input type="text" data-k="name" maxlength="32" value="${esc(c.name)}"${c.on ? '' : ' disabled'}>` +
    `<input type="number" data-k="gain" min="0" step="any" value="${c.gain}"${c.on ? '' : ' disabled'} title="Ganancia"></label>`).join('');
}
$('chans').onchange = e => {
  if (e.target.dataset.k === 'on') e.target.closest('label').querySelectorAll('input:not([type=checkbox])').forEach(i => i.disabled = !e.target.checked);
};
$('chsave').onclick = () => {
  const cs = [...$('chans').querySelectorAll('label')].map(l => ({
    name: l.querySelector('[data-k=name]').value, gain: +l.querySelector('[data-k=gain]').value, on: l.querySelector('[data-k=on]').checked,
  }));
  post('/api/channels', cs).then(async r => {
    if (!r.ok) { $('chmsg').textContent = await r.text(); return; }
    setChans(await r.json(), true); drawChanEditor(); $('chmsg').textContent = 'Guardado';
    setTimeout(() => $('chmsg').textContent = '', 2500);
  });
};

function b64(s) {
  const bin = atob(s), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
}

function pushWaves(m) {
  if (!m.e || !m.e[0]) return;
  const n = m.e[0].length / 2;
  for (let b = 0; b < n; b++) {
    const p = (wpos % NB) * 2;
    for (let ch = 0; ch < 3; ch++) { waves[ch][p] = m.e[ch][2 * b]; waves[ch][p + 1] = m.e[ch][2 * b + 1]; }
    waves[3][p] = m.v[2 * b]; waves[3][p + 1] = m.v[2 * b + 1];
    wpos++;
  }
}

// ------------------------------------------------------------ resultados
function setLink(cls, text) { $('link').className = 'pill ' + cls; $('link').lastChild.textContent = text; }

function onResult(r, link, rec, src) {
  R = r; lastRec = rec; lastSrc = src || lastSrc;
  const replay = !!lastSrc && lastSrc.mode === 'file';
  if (r.hop !== hop) { hop = r.hop; cols = []; setSeg('hop', hop); }

  // cabecera
  if (link.nodata) setLink('bad', 'Sin señal');
  else setLink('ok', replay || I.source === 'file' ? 'Reproducción' : I.source === 'sim' ? 'Simulación' : 'En vivo');
  $('play').hidden = !replay;
  $('plays').textContent = replay ? lastSrc.file.replace(/\.avx$/, '') : '';
  $('recbtn').disabled = replay;
  $('cond').textContent = (COND[r.cond] || [r.cond])[0];
  $('rec').hidden = !rec.active;
  $('recs').textContent = rec.active ? clock(rec.secs) : '';
  $('recbtn').classList.toggle('on', rec.active);
  $('recbtn').lastChild.textContent = rec.active ? 'Detener' : 'Grabar';
  document.querySelectorAll('#condbtns button').forEach(b => b.classList.toggle('on', b.dataset.c === r.cond));

  // carriles
  for (let ch = 0; ch < 3; ch++) {
    const l = r.lanes[ch];
    $('r' + ch).innerHTML = `${fmt(l.rms, l.rms < 10 ? 1 : 0)}<small>µV</small>`;
    $('h' + ch).textContent = `50 Hz · ${fmt(l.hum, 1)} µV`;
    $('L' + ch).classList.toggle('act', l.act);
  }
  $('r3').innerHTML = `${fmt(20 * Math.log10(r.vrms || 1e-9), 0)}<small>dBFS</small>`;
  $('h3').textContent = nil(r.f0) ? 'Sin tono' : `Tono ${fmt(r.f0, 0)} Hz`;
  $('L3').classList.toggle('act', r.voiced);
  $('speak').classList.toggle('on', r.voiced);
  $('speak').lastChild.textContent = r.voiced ? 'Hablando' : 'Silencio';

  // retardo biológico automático = τ* medido
  if (delayAuto) {
    const t = leadTau(r);
    if (!nil(t) && t > 0) { $('delay').value = Math.min(300, Math.round(t / 5) * 5); $('delayv').textContent = $('delay').value + ' ms'; }
  }
  if (tab === 'cau') drawCausality(r);
  if (tab === 'ses') drawSession(r, link);
}

const clock = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
function median(a) { a = a.filter(v => !nil(v)).sort((x, y) => x - y); return a.length ? a[a.length >> 1] : null; }
// Canal principal: el activo con más frases sobre el azar (empate: mayor r); sin frases, el de mayor r en vivo.
function mainCh(r) {
  const act = ACT();
  if (!act.length) return -1;
  const score = ch => r.sum[ch].n ? [1, r.sum[ch].n, r.sum[ch].r] : [0, nil(r.tauLive[ch]) ? 0 : 1, r.rLive[ch] || -1];
  return act.reduce((b, ch) => { const x = score(ch), y = score(b); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i] ? ch : b; return b; });
}
function leadTau(r) { // τ* del canal principal: mediana de las frases significativas; si no hay, el valor en vivo
  const ch = mainCh(r);
  if (ch < 0) return null;
  return r.sum[ch].n ? r.sum[ch].tau : r.tauLive[ch];
}

// ------------------------------------------------------------ dibujo base
function fit(cv) {
  const d = DPR(), w = Math.round(cv.clientWidth * d), h = Math.round(cv.clientHeight * d);
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  return cv.getContext('2d');
}
const font = (g, px, w = 400) => { g.font = `${w} ${px * DPR()}px system-ui, sans-serif`; };

function drawWaves() {
  for (let s = 0; s < 4; s++) {
    const cv = $(s < 3 ? 'w' + s : 'wv'), g = fit(cv), W = cv.width, H = cv.height, d = DPR();
    g.clearRect(0, 0, W, H);
    const buf = waves[s], start = wpos - NB;
    let peak = 1e-9;
    for (let i = 0; i < 2 * NB; i++) peak = Math.max(peak, Math.abs(buf[i]));
    autoScale[s] = Math.max(peak * 1.15, autoScale[s] * 0.985);
    const sc = (s < 3 && fixedScale) ? fixedScale : autoScale[s];
    const pad = 10 * d, y = v => H / 2 - Math.max(-1, Math.min(1, v / sc)) * (H / 2 - pad);
    // rejilla: un trazo por segundo y la línea de cero
    g.strokeStyle = INK.grid; g.lineWidth = d; g.beginPath();
    for (let k = 1; k < I.showSecs; k++) { const x = Math.round(k * W / I.showSecs) + .5; g.moveTo(x, 0); g.lineTo(x, H); }
    g.moveTo(0, H / 2); g.lineTo(W, H / 2); g.stroke();
    // envolvente min/max por píxel
    g.strokeStyle = C[s]; g.lineWidth = 1.2 * d; g.beginPath();
    for (let x = 0; x < W; x += 1) {
      const b0 = Math.floor(x * NB / W), b1 = Math.max(b0 + 1, Math.floor((x + 1) * NB / W));
      let lo = Infinity, hi = -Infinity;
      for (let b = b0; b < b1; b++) {
        const k = start + b;
        if (k < 0) continue;
        const p = (k % NB) * 2;
        lo = Math.min(lo, buf[p]); hi = Math.max(hi, buf[p + 1]);
      }
      if (lo === Infinity) continue;
      g.moveTo(x + .5, y(hi)); g.lineTo(x + .5, y(lo) + d);
    }
    g.stroke();
    font(g, 11); g.fillStyle = INK.muted; g.textAlign = 'right';
    g.fillText(s < 3 ? `±${fmt(sc, sc < 10 ? 1 : 0)} µV` : `±${fmt(sc, 2)}`, W - 10 * d, 16 * d);
    if (s === 3) { g.textAlign = 'left'; g.fillText(`−${I.showSecs} s`, 8 * d, H - 8 * d); g.textAlign = 'right'; g.fillText('ahora', W - 10 * d, H - 8 * d); }
  }
}

// mapas de color: inferno (magnitud) y fase cíclica con brillo = magnitud
const LUT = (() => {
  const st = [[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]];
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255 * (st.length - 1), k = Math.min(st.length - 2, Math.floor(t)), f = t - k;
    for (let c = 0; c < 3; c++) lut[3 * i + c] = st[k][c] + f * (st[k + 1][c] - st[k][c]);
  }
  return lut;
})();
function hsv(h, v) {
  const i = Math.floor(h * 6), f = h * 6 - i, q = v * (1 - f), t = v * f;
  return [[v, t, 0], [q, v, 0], [0, v, t], [0, q, v], [t, 0, v], [v, 0, q]][i % 6].map(x => x * 255);
}
function drawRamp() {
  const stops = cmode === 'mag'
    ? [0, 64, 128, 192, 255].map(i => `rgb(${LUT[3 * i]},${LUT[3 * i + 1]},${LUT[3 * i + 2]})`)
    : [0, 1, 2, 3, 4, 5, 6].map(i => `rgb(${hsv(i / 6 % 1, 1).join(',')})`);
  $('ramp').style.background = `linear-gradient(90deg,${stops.join(',')})`;
  $('rampl').textContent = cmode === 'mag' ? 'baja → alta energía' : '−π → +π';
}

const off = document.createElement('canvas');
function heatmap(cv, w, h, pix) { // pix(x, y) → [r, g, b] o null; y = 0 arriba
  off.width = w; off.height = h;
  const og = off.getContext('2d'), img = og.createImageData(w, h);
  for (let x = 0; x < w; x++) for (let y = 0; y < h; y++) {
    const c = pix(x, y), p = 4 * (y * w + x);
    if (c) { img.data[p] = c[0]; img.data[p + 1] = c[1]; img.data[p + 2] = c[2]; }
    img.data[p + 3] = 255;
  }
  og.putImageData(img, 0, 0);
  const g = fit(cv);
  g.imageSmoothingEnabled = true;
  g.drawImage(off, 0, 0, cv.width, cv.height);
  return g;
}

function freqAxis(g, W, H, fmin, fmax, nf, ticks, unit) {
  const d = DPR();
  font(g, 10); g.textAlign = 'right';
  for (const f of ticks) {
    const i = Math.log(f / fmin) / Math.log(fmax / fmin) * (nf - 1), y = Math.max(11 * d, H - (i + .5) / nf * H);
    g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(W - 46 * d, y - 7 * d, 42 * d, 14 * d);
    g.fillStyle = 'rgba(255,255,255,.8)'; g.fillText(f + unit, W - 8 * d, y + 3.5 * d);
  }
}

function drawCWT() {
  const nf = I.nf, W = Math.round(I.showSecs * 1000 / hop), phase = cmode === 'phase';
  const shift = Math.round(+$('delay').value / hop), n = cols.length;
  for (let s = 0; s < 4; s++) {
    const o = s === 3 ? shift : 0; // la voz se dibuja adelantada el retardo biológico
    const cv = $('c' + s);
    const g = heatmap(cv, W, nf, (x, y) => {
      const ci = n - W + x + o;
      if (ci < 0 || ci >= n) return null;
      const col = cols[ci], f = nf - 1 - y, m = col[s * nf + f];
      if (!phase) return [LUT[3 * m], LUT[3 * m + 1], LUT[3 * m + 2]];
      return hsv(col[4 * nf + s * nf + f] / 256, Math.min(1, m / 200));
    });
    freqAxis(g, cv.width, cv.height, I.freqs[0], I.freqs[nf - 1], nf, [50, 100, 200, 500], ' Hz');
  }
}

// ------------------------------------------------------------ causalidad
let xcHover = null;
$('xc').onmousemove = e => { const b = e.target.getBoundingClientRect(); xcHover = (e.clientX - b.left) / b.width; if (R) drawXC(R); };
$('xc').onmouseleave = () => { xcHover = null; $('tip').hidden = true; if (R) drawXC(R); };

function drawXC(r) {
  const cv = $('xc'), g = fit(cv), W = cv.width, H = cv.height, d = DPR();
  g.clearRect(0, 0, W, H);
  const L = I.maxLagMs, padB = 20 * d, padT = 24 * d;
  const x = t => (t + L) / (2 * L) * W, y = v => padT + (1 - (v + 0.2) / 1.2) * (H - padT - padB);
  // rejilla
  font(g, 11); g.fillStyle = INK.muted; g.lineWidth = d;
  for (let t = -L; t <= L; t += 100) {
    g.strokeStyle = t === 0 ? INK.axis : INK.grid; g.beginPath(); g.moveTo(Math.round(x(t)) + .5, padT); g.lineTo(Math.round(x(t)) + .5, H - padB); g.stroke();
    g.textAlign = t === -L ? 'left' : t === L ? 'right' : 'center';
    g.fillText((t > 0 ? '+' : '') + t + ' ms', x(t), H - 4 * d);
  }
  g.strokeStyle = INK.axis; g.beginPath(); g.moveTo(0, y(0)); g.lineTo(W, y(0)); g.stroke();
  // zona de azar: r < rMinLive
  if (!nil(r.rMinLive)) {
    g.fillStyle = 'rgba(137,135,129,.13)'; g.fillRect(0, y(r.rMinLive), W, y(-0.2) - y(r.rMinLive));
    font(g, 11); g.fillStyle = INK.muted; g.textAlign = 'right';
    g.fillText(`azar (r < ${fmt(r.rMinLive, 2)})`, W - 6 * d, y(r.rMinLive) + 14 * d);
  }
  // curvas r(τ)
  const act = ACT();
  g.lineWidth = 2 * d; g.lineJoin = 'round';
  r.xc.forEach((xc, ch) => {
    if (!xc || !act.includes(ch)) return;
    g.strokeStyle = C[ch]; g.beginPath();
    xc.forEach((v, i) => { const t = -L + i * 5; i ? g.lineTo(x(t), y(v)) : g.moveTo(x(t), y(v)); });
    g.stroke();
  });
  // τ* de cada canal: marcador en el pico
  r.xc.forEach((xc, ch) => {
    const t = r.tauLive[ch];
    if (!xc || nil(t) || !act.includes(ch)) return;
    const v = xc[Math.round((t + L) / 5)];
    g.fillStyle = C[ch]; g.strokeStyle = '#1a1a19'; g.lineWidth = 2 * d;
    g.beginPath(); g.arc(x(t), y(v), 5 * d, 0, 7); g.fill(); g.stroke();
  });
  const mc = mainCh(r), tm = mc < 0 ? null : r.tauLive[mc];
  if (!nil(tm)) {
    const v = r.xc[mc][Math.round((tm + L) / 5)];
    font(g, 12, 600); g.fillStyle = '#fff'; g.textAlign = x(tm) > W - 80 * d ? 'right' : 'left';
    g.fillText(`τ* ${sgn(tm)} ms`, x(tm) + (g.textAlign === 'left' ? 10 : -10) * d, y(v) - 10 * d);
  }
  font(g, 11); g.fillStyle = INK.muted; g.textAlign = 'left';
  for (const v of [0, 0.5, 1]) g.fillText(v.toFixed(1), 4 * d, y(v) - 4 * d);
  // hover
  const tip = $('tip');
  if (xcHover === null) return;
  const i = Math.max(0, Math.min(2 * L / 5, Math.round(xcHover * 2 * L / 5))), t = -L + i * 5;
  g.strokeStyle = INK.text2; g.lineWidth = d; g.setLineDash([3 * d, 3 * d]);
  g.beginPath(); g.moveTo(x(t), padT); g.lineTo(x(t), H - padB); g.stroke(); g.setLineDash([]);
  tip.innerHTML = `<div><b>τ = ${t > 0 ? '+' : ''}${t} ms</b></div>` +
    act.map(ch => `<div style="--k:${C[ch]}"><i></i>${CH[ch]} ${esc(chName(ch))} r = ${r.xc[ch] ? fmt(r.xc[ch][i], 2) : '—'}</div>`).join('');
  tip.hidden = false;
  const px = x(t) / d;
  tip.style.left = (px > cv.clientWidth / 2 ? px - tip.offsetWidth - 12 : px + 12) + 'px';
  tip.style.top = '12px';
}

function drawCausality(r) {
  const act = ACT(), mc = mainCh(r), t = leadTau(r);
  const sm = mc < 0 ? null : r.sum[mc], name = mc < 0 ? '' : `${chName(mc)} (${CH[mc]})`;
  $('lead').innerHTML = nil(t) ? '—' : `${sgn(t)}<small>ms</small>`;
  $('leadsub').textContent = mc < 0 ? 'No hay canales activos: actívalos en Sesión → Canales'
    : sm.n ? `${name}: el músculo se activa antes que la voz en ${fmt(sm.pctLead, 0)} % de ${sm.n} frases sobre el azar (de ${sm.nAll})`
      : !nil(t) ? `${name}, en vivo · r = ${fmt(r.rLive[mc], 2)}, azar < ${fmt(r.rMinLive, 2)} · habla unas frases para consolidarla`
        : r.voiced ? `Ningún canal supera el azar (r < ${fmt(r.rMinLive, 2)})` : 'Habla para comenzar la medición';
  $('tiles').innerHTML = act.map(ch => {
    const s = r.sum[ch], tau = s.n ? s.tau : r.tauLive[ch], rr = s.n ? s.r : r.rLive[ch];
    const sub = s.n ? `r = ${fmt(rr, 2)} · ${s.n} de ${s.nAll} frases`
      : nil(rr) ? (s.nAll ? `0 de ${s.nAll} frases sobre el azar` : 'sin frases')
        : `r = ${fmt(rr, 2)} · ${nil(tau) ? 'no significativo' : 'sobre el azar'}`;
    return `<div class="tile${nil(tau) ? ' ns' : ''}" style="--k:${C[ch]}"><div class="k"><i></i>${CH[ch]} · ${esc(chName(ch))}</div>` +
      `<div class="v">${nil(tau) ? '—' : sgn(tau) + ' ms'}</div><div class="s">${sub}</div></div>`;
  }).join('');
  drawXC(r);

  const c = mc < 0 ? null : r.confound[mc];
  $('conf').innerHTML = nil(r.f0) || nil(c) ? ''
    : c > 10 ? `<span class="badge">${esc(chName(mc))} capta la vibración de la voz</span>`
      : `<span class="badge ok">${esc(chName(mc))} sin acople de voz</span>`;

  const rows = r.utter.slice(-6).reverse();
  $('uttab').innerHTML = rows.length && act.length
    ? '<tr><th>Frase</th><th>Duración</th>' + act.map(ch => `<th>${CH[ch]} ${esc(chName(ch))}</th>`).join('') + '</tr>' +
      rows.map(u => `<tr><td>${(COND[u.cond] || [u.cond])[0]} · ${clock(u.t)}</td><td>${fmt(u.dur, 1)} s</td>` +
        act.map(ch => {
          const v = u.tau[ch], sig = u.sig && u.sig[ch];
          return `<td class="${nil(v) || !sig ? 'ns' : v > 0 ? 'lead' : 'lag'}" title="r = ${fmt(u.r[ch], 2)}, azar < ${fmt(u.rMin, 2)}">` +
            `${sig ? sgn(v) + ' ms' : '—'}<small>r ${fmt(u.r[ch], 2)}</small></td>`;
        }).join('') + '</tr>').join('')
    : '<tr><td class="empty">Aún no hay frases</td></tr>';
}

// ------------------------------------------------------------ sesión
function drawSession(r, link) {
  const tile = (k, v, s, bad) => `<div class="tile"><div class="k">${k}</div><div class="v"${bad ? ' style="color:var(--bad)"' : ''}>${v}</div><div class="s">${s}</div></div>`;
  const lost = link.gaps + link.crc + link.hdr;
  $('linktiles').innerHTML =
    tile('Bloques por segundo', fmt(link.rate, 0), 'esperado 100', link.nodata) +
    tile('Pérdidas', lost, `${link.crc} CRC · ${link.gaps} saltos`, lost > 0) +
    tile('Recibidos', link.blocks.toLocaleString('es'), clock(link.blocks / 100)) +
    tile('Desbordes', link.overrun, 'en el DK', link.overrun > 0);

  const rows = I.conds.filter(c => r.conds[c]), act = ACT();
  $('condtab').innerHTML = rows.length
    ? '<tr><th>Condición</th><th>Tiempo</th>' + act.map(ch => `<th>${CH[ch]} ${esc(chName(ch))}</th>`).join('') + '</tr>' +
      rows.map(c => {
        const s = r.conds[c];
        return `<tr><td>${COND[c][0]}</td><td>${clock(s.secs)}</td>` +
          act.map(ch => `<td>${fmt(s.rms[ch], 2)}<small>50 Hz ${fmt(s.hum[ch], 2)}</small></td>`).join('') + '</tr>';
      }).join('')
    : '<tr><td class="empty">Elige una condición para empezar a acumular</td></tr>';
  $('snr').innerHTML = act.some(ch => !nil(r.snr[ch]))
    ? act.map(ch => `<span>SNR ${CH[ch]} <b>${fmt(r.snr[ch], 1)} dB</b></span>`).join('') : '';
}

let filesT = 0;
const esc = s => s.replace(/[&<>"']/g, c => '&#' + c.charCodeAt(0) + ';');
function loadFiles() {
  fetch('/api/files').then(r => r.json()).then(ss => {
    const playing = lastSrc && lastSrc.mode === 'file' ? lastSrc.file.replace(/\.avx$/, '') : '';
    const recording = lastRec && lastRec.active ? lastRec.name : '';
    $('files').innerHTML = (ss || []).map(s => {
      const n = esc(s.name), u = encodeURIComponent(s.name), busy = s.name === playing || s.name === recording;
      const why = s.name === recording ? ' title="Se está grabando"' : s.name === playing ? ' title="Se está reproduciendo"' : '';
      const play = !s.size ? ''
        : s.name === playing ? '<button class="on" disabled>Reproduciendo</button>'
        : `<button data-play data-name="${n}"${s.name === recording ? ' disabled' : ''}>Reproducir</button>`;
      const dl = (s.size ? `<a href="/files/${u}.avx" download>Descargar</a>` : '') +
        (s.meta ? `<a class="json" href="/files/${u}.json" download>.json</a>` : '');
      return `<li><span class="fn">${n}<span class="muted"> · ${clock(s.secs)} · ${(s.size / 1e6).toFixed(1)} MB</span></span>` +
        `<span class="acts">${play}<button data-ren data-name="${n}"${busy ? ' disabled' + why : ''}>Renombrar</button>${dl}` +
        `<button class="del" data-del data-name="${n}"${busy ? ' disabled' + why : ''}>Borrar</button></span></li>`;
    }).join('') || '<li class="muted">Aún no hay grabaciones</li>';
  });
}

function frame(t) {
  if (I) {
    if (tab === 'sig') drawWaves();
    if (tab === 'cwt') drawCWT();
    if (tab === 'ses' && t - filesT > 5000) { filesT = t; loadFiles(); }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
