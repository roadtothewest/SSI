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

let I = null, R = null, tab = 'sig';
let NB = 0, waves = [], wpos = 0, cols = [], hop = 10;
let autoScale = [20, 20, 20, 0.5], fixedScale = 0, cmode = 'mag', delayAuto = true, lastRec = null;

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
  if (tab === 'ses') loadFiles();
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
  if (m.r) onResult(m.r, m.link, m.rec);
};
es.onerror = () => setLink('bad', 'Sin conexión');

function init(m) {
  I = m;
  NB = I.fsEmg / I.bucket * I.showSecs;
  waves = [0, 1, 2, 3].map(() => new Float32Array(2 * NB));
  wpos = 0; cols = [];
  $('condbtns').innerHTML = I.conds.map(c => { const [t, s] = COND[c] || [c, '']; return `<button data-c="${c}"><b>${t}</b><span>${s}</span></button>`; }).join('');
  document.querySelectorAll('#condbtns button').forEach(b => b.onclick = () => post('/api/condition', { cond: b.dataset.c }));
  $('keys').innerHTML = CH.map((n, i) => `<span style="--k:${C[i]}"><i></i>${n}</span>`).join('');
  drawRamp();
}

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

function onResult(r, link, rec) {
  R = r; lastRec = rec;
  if (r.hop !== hop) { hop = r.hop; cols = []; setSeg('hop', hop); }

  // cabecera
  if (link.nodata) setLink('bad', 'Sin señal');
  else setLink('ok', I.source === 'sim' ? 'Simulación' : I.source === 'file' ? 'Reproducción' : 'En vivo');
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
function leadTau(r) { // τ* representativo: mediana por frase; si aún no hay frases, el valor en vivo
  const m = median(r.sum.map(s => s.n ? s.tau : null));
  return nil(m) ? median(r.tauLive) : m;
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
  // curvas r(τ)
  g.lineWidth = 2 * d; g.lineJoin = 'round';
  r.xc.forEach((xc, ch) => {
    if (!xc) return;
    g.strokeStyle = C[ch]; g.beginPath();
    xc.forEach((v, i) => { const t = -L + i * 5; i ? g.lineTo(x(t), y(v)) : g.moveTo(x(t), y(v)); });
    g.stroke();
  });
  // τ* de cada canal: marcador en el pico
  r.xc.forEach((xc, ch) => {
    const t = r.tauLive[ch];
    if (!xc || nil(t)) return;
    const v = xc[Math.round((t + L) / 5)];
    g.fillStyle = C[ch]; g.strokeStyle = '#1a1a19'; g.lineWidth = 2 * d;
    g.beginPath(); g.arc(x(t), y(v), 5 * d, 0, 7); g.fill(); g.stroke();
  });
  const tm = median(r.tauLive);
  if (!nil(tm)) {
    const v = Math.max(...r.xc.map(xc => xc ? xc[Math.round((tm + L) / 5)] : -1));
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
    r.xc.map((xc, ch) => `<div style="--k:${C[ch]}"><i></i>${CH[ch]} r = ${xc ? fmt(xc[i], 2) : '—'}</div>`).join('');
  tip.hidden = false;
  const px = x(t) / d;
  tip.style.left = (px > cv.clientWidth / 2 ? px - tip.offsetWidth - 12 : px + 12) + 'px';
  tip.style.top = '12px';
}

function drawCausality(r) {
  const t = leadTau(r), n = Math.max(...r.sum.map(s => s.n));
  const pct = median(r.sum.map(s => s.n ? s.pctLead : null));
  $('lead').innerHTML = nil(t) ? '—' : `${sgn(t)}<small>ms</small>`;
  $('leadsub').textContent = nil(t) ? 'Habla para comenzar la medición'
    : n ? `El músculo se activa antes que la voz en ${fmt(pct, 0)} % de ${n} frases`
      : 'Medición en vivo · habla unas frases para consolidarla';
  $('tiles').innerHTML = r.sum.map((s, ch) => {
    const tau = s.n ? s.tau : r.tauLive[ch], rr = s.n ? s.r : r.rLive[ch];
    return `<div class="tile" style="--k:${C[ch]}"><div class="k"><i></i>${CH[ch]}</div>` +
      `<div class="v">${sgn(tau)} ms</div><div class="s">r = ${fmt(rr, 2)}</div></div>`;
  }).join('');
  drawXC(r);

  const nf = r.xwtFreqs.length, NC = r.xwtCols;
  for (let ch = 0; ch < 3; ch++) {
    const xw = r.xwt[ch], cv = $('m' + ch);
    if (!xw || !xw.mag) { fit(cv).clearRect(0, 0, cv.width, cv.height); $('xn' + ch).textContent = ''; continue; }
    const mag = b64(xw.mag), ph = b64(xw.phase);
    const g = heatmap(cv, NC, nf, (x, y) => { const f = nf - 1 - y; return hsv(ph[f * NC + x] / 256, mag[f * NC + x] / 255); });
    freqAxis(g, cv.width, cv.height, r.xwtFreqs[0], r.xwtFreqs[nf - 1], nf, [2, 4, 8], ' Hz');
    const coh = median(xw.coh || []);
    $('xn' + ch).textContent = nil(coh) ? '' : `coherencia ${fmt(coh, 2)}`;
  }

  const c = r.confound;
  $('conf').innerHTML = nil(r.f0) || nil(c[2]) ? ''
    : c[2] > 10 ? '<span class="badge">CH3 capta la vibración de la voz</span>'
      : '<span class="badge ok">CH3 sin acople de voz</span>';

  const rows = r.utter.slice(-6).reverse();
  $('uttab').innerHTML = rows.length
    ? '<tr><th>Frase</th><th>Duración</th>' + CH.map(n => `<th>${n}</th>`).join('') + '</tr>' +
      rows.map(u => `<tr><td>${(COND[u.cond] || [u.cond])[0]} · ${clock(u.t)}</td><td>${fmt(u.dur, 1)} s</td>` +
        u.tau.map(v => `<td class="${nil(v) ? '' : v > 0 ? 'lead' : 'lag'}">${sgn(v)} ms</td>`).join('') + '</tr>').join('')
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

  const rows = I.conds.filter(c => r.conds[c]);
  $('condtab').innerHTML = rows.length
    ? '<tr><th>Condición</th><th>Tiempo</th>' + CH.map(n => `<th>${n}</th>`).join('') + '<th>50 Hz (prom.)</th></tr>' +
      rows.map(c => {
        const s = r.conds[c], hum = s.hum.filter(v => !nil(v));
        return `<tr><td>${COND[c][0]}</td><td>${clock(s.secs)}</td>${s.rms.map(v => `<td>${fmt(v, 2)}</td>`).join('')}` +
          `<td>${hum.length ? fmt(hum.reduce((a, b) => a + b, 0) / hum.length, 2) : '—'}</td></tr>`;
      }).join('')
    : '<tr><td class="empty">Elige una condición para empezar a acumular</td></tr>';
  $('snr').innerHTML = r.snr.some(v => !nil(v))
    ? r.snr.map((v, i) => `<span>SNR ${CH[i]} <b>${fmt(v, 1)} dB</b></span>`).join('') : '';
}

let filesT = 0;
function loadFiles() {
  fetch('/api/files').then(r => r.json()).then(fs => {
    $('files').innerHTML = (fs || []).map(f => `<li><span>${f.name}<span class="muted"> · ${(f.size / 1e6).toFixed(1)} MB</span></span>` +
      `<a href="/files/${f.name}" download>Descargar</a></li>`).join('') || '<li class="muted">Aún no hay grabaciones</li>';
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
