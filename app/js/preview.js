// Прев'ю: шорт, кадрування джерела, вибір і перетягування елементів.
// ── прев'ю: шорт ──
function visible(el) {                                            // час «з/до» рахується від початку кліпу вже без пропусків
  if (!el.on || el.type === 'music') return false;
  const t = vid.currentTime, c = clipAt(t); if (!c) return !el.solo || el.id === selEl;
  const rel = toOut(c, t); return segsOf(c, el).some(([a, b]) => rel >= (a || 0) && (!b || rel < b));
}
function rectOf(el) {
  if (el.type === 'video' || el.type === 'cam') return {x: el.x, y: el.y, w: el.w, h: layerH(el)};
  if (el.type === 'subs') return {x: el.x, y: el.y, w: el.w, h: el.size * 1.4};
  if (el.type === 'progress') return {x: 0, y: el.y, w: CW(), h: el.h};
  if (el.type === 'bg' || el.type === 'fx') return {x: 0, y: 0, w: 0, h: 0};
  const a = arts.get(aid(el)); if (!a || !a.img) return {x: el.x ?? 0, y: el.y, w: 0, h: 0};
  const r = el[TYPES[el.type].size[0]] / a.v; return {x: el.x ?? 0, y: el.y, w: a.w * r, h: a.h * r};
}
function shapePath(el, x, y, w, h) {
  px.beginPath();
  if (el.shape === 'circle') px.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
  else px.roundRect(x, y, w, h, el.shape === 'round' ? el.radius * pv.width / CW() : 0);
}
function drawSubs(el, k) {                                        // наближення ASS-стилю рендеру
  const t = vid.currentTime, now = P.cues.filter(c => t >= c.a && t < c.b && cueOwner(c) === el);
  if (!P.cues.some(c => cueOwner(c) === el)) now.push({a: 0, b: 1e9, text: tr(subsEls().length > 1 ? subName(el, subsEls().indexOf(el)) : 'Тут будуть субтитри'), k: [0]});
  for (const c of now) drawCue(c.own ? cueStyle(c) : el, k, c, t);
}
function drawCue(el, k, c, t) {
  const words = (el.upper ? c.text.toUpperCase() : c.text).split(/\s+/).filter(Boolean); if (!words.length) return;
  const fm = c.fmt?.length === words.length ? c.fmt : [], F = i => fm[i] || {};
  const ks = c.k && c.k.length === words.length ? c.k : words.map((_, i) => c.a + i * (c.b - c.a) / words.length);
  const font = (z, f = {}) => `${f.i ? 'italic ' : ''}${f.b === false ? 400 : 'bold'} ${z * (f.s || 1)}px "${el.font || 'Arial'}", Arial, sans-serif`;
  let z = el.size * k; px.font = font(z); const sp = px.measureText(' ').width;
  const ws = words.map((w, i) => { px.font = font(z, F(i)); return px.measureText(w).width; });
  const line = ws.reduce((s, w) => s + w, 0) + sp * (words.length - 1), r = Math.min(1, el.w * k / line); z *= r;
  const cur = el.karaoke ? ks.findLastIndex(s => s <= t) : -1, y = (el.y + el.size * .7) * k;
  let x = (el.x + el.w / 2) * k - line * r / 2;
  px.textBaseline = 'middle'; px.lineJoin = 'round'; px.lineWidth = el.outline * 2 * k * r; px.strokeStyle = el.stroke || '#000';
  words.forEach((w, i) => {
    const f = F(i), ww = ws[i] * r; px.font = font(z, f);
    if (el.outline) px.strokeText(w, x, y); px.fillStyle = i === cur ? el.hl : f.c || el.color; px.fillText(w, x, y);
    if (f.u) { const h = Math.max(1, z * (f.s || 1) * .07), uy = y + z * (f.s || 1) * .42; if (el.outline) px.strokeRect(x, uy, ww, h); px.fillRect(x, uy, ww, h); }
    x += ww + sp * r;
  });
  px.textBaseline = 'alphabetic';
}
// що зараз видно на прев'ю: елементи такими, якими вони є в поточному кліпі, і репліки зі своїм стилем
const pvEls = () => { const c = pvClip(); return els().map(e => effEl(e, c)); };
const ownCuesNow = () => { const t = vid.currentTime; return P.cues.filter(q => q.own && t >= q.a && t < q.b && cueOwner(q)?.on); };
function selShown() {                                             // вибране, якщо воно саме зараз на прев'ю: йому — рамка
  const g = elById(selEl); if (!g || g.type === 'bg' || g.type === 'music' || g.type === 'fx') return null;
  if (selOwn) { const q = P.cues.find(q => q.own === selOwn); return q ? (ownCuesNow().includes(q) ? cueStyle(q) : null) : effEl(g, pvClip()) === selOwn ? selOwn : null; }
  return effEl(g, pvClip()) === g ? g : null;
}
const bgc = Object.assign(document.createElement('canvas'), {width: 135, height: 240}), bgx = bgc.getContext('2d');
function drawShort() {
  const k = pv.width / CW(), bg = els().find(e => e.type === 'bg' && e.on);
  if (bgc.width !== Math.round(CW() / 8) || bgc.height !== Math.round(CH() / 8)) { bgc.width = Math.round(CW() / 8); bgc.height = Math.round(CH() / 8); }   // тло в пропорціях полотна
  px.fillStyle = bg && bg.style === 'color' ? bg.color : '#000'; px.fillRect(0, 0, pv.width, pv.height);
  if (!P) return;
  if (vid.videoWidth && !(bg && bg.style === 'color')) {          // розмите тло — у ¼ розміру, як у рендері: розмиття повного кадру гальмує
    const s = Math.max(bgc.width / S.w, bgc.height / S.h) * 1.08;
    bgx.filter = `blur(${(bg ? bg.blur : 5) * 4 * k * bgc.width / pv.width}px) brightness(${1 - (bg ? bg.dim : .12)})`;
    bgx.drawImage(vid, (bgc.width - S.w * s) / 2, (bgc.height - S.h * s) / 2, S.w * s, S.h * s); bgx.filter = 'none';
    px.drawImage(bgc, 0, 0, pv.width, pv.height);
  }
  const shown = pvEls();
  for (const el of [...shown.filter(e => e.type !== 'subs'), ...shown.filter(e => e.type === 'subs')]) {   // субтитри завжди згори, як у рендері
    if (el.type === 'bg' || !visible(el)) continue;
    if (el.type === 'fx') { applyFx(el, k); continue; }
    if (el.type === 'video' || el.type === 'cam') {
      if (!vid.videoWidth) continue; const [x, y, w, h] = shownSrc(el, shown), r = rectOf(el);
      px.save(); shapePath(el, r.x * k, r.y * k, r.w * k, r.h * k); px.clip();
      px.drawImage(vid, x * vid.videoWidth, y * vid.videoHeight, w * vid.videoWidth, h * vid.videoHeight, r.x * k, r.y * k, r.w * k, r.h * k); px.restore();
      if (el.bw > 0) { const b = el.bw * k; shapePath(el, (r.x - el.bw / 2) * k, (r.y - el.bw / 2) * k, (r.w + el.bw) * k, (r.h + el.bw) * k); px.lineWidth = b; px.strokeStyle = el.border; px.stroke(); }
    } else if (el.type === 'subs') drawSubs(el, k);
    else if (el.type === 'progress') { const c = clipAt(vid.currentTime); px.fillStyle = el.color; px.fillRect(0, el.y * k, (c ? toOut(c, vid.currentTime) / net(c) : .4) * pv.width, el.h * k); }
    else {
      ensureArt(el); const a = arts.get(aid(el)); if (!a || !a.img) continue;
      const r = el[TYPES[el.type].size[0]] / a.v, g = el.type === 'image' && gifOf(el.path);
      if (g) px.drawImage(gifFrame(g, el), el.x * k, el.y * k, a.w * r * k, a.h * r * k);   // анімований стікер грає
      else px.drawImage(a.img, (el.x - a.pad * r) * k, (el.y - a.pad * r) * k, a.img.naturalWidth * r * k, a.img.naturalHeight * r * k);
    }
  }
  const el = selShown(), s = pvScale(), hs = HANDLE_PX * s;
  if (el) {
    const b = rectOf(el); px.strokeStyle = px.fillStyle = TYPES[el.type].col;
    px.lineWidth = 2 * s; px.setLineDash([6 * s, 4 * s]); px.strokeRect(b.x * k, b.y * k, b.w * k, b.h * k); px.setLineDash([]);
    if (TYPES[el.type].size.length) px.fillRect((b.x + b.w) * k - hs, (b.y + b.h) * k - hs, hs * 2, hs * 2);
  }
  drawGuides(v => v * k, v => v * k);
}
const fxc = document.createElement('canvas'), fxx = fxc.getContext('2d');
function applyFx(f, k) {                                          // ефект на все, що вже намальовано під ним (як у рендері)
  const s = fxSeg(f); if (!s || f.kind === 'zoom') return;
  if (f.kind === 'flash') { px.fillStyle = `rgba(255,255,255,${clamp(1 - (s.rel - s.a) / .35, 0, 1)})`; px.fillRect(0, 0, pv.width, pv.height); return; }
  if (fxc.width !== pv.width || fxc.height !== pv.height) { fxc.width = pv.width; fxc.height = pv.height; }
  fxx.clearRect(0, 0, fxc.width, fxc.height); fxx.drawImage(pv, 0, 0);
  if (f.kind === 'shake') {
    const a = f.amp * k, W = pv.width + 4 * a, H = pv.height + 4 * a;
    px.drawImage(fxc, -2 * a - a * Math.sin(s.rel * 47), -2 * a - a * Math.cos(s.rel * 37), W, H); return;
  }
  px.filter = {bw: 'grayscale(1)', blur: `blur(${f.blur * k}px)`, fried: 'contrast(1.8) saturate(2.6)'}[f.kind] || 'none'; px.drawImage(fxc, 0, 0); px.filter = 'none';
}
function drawGuides(mx, my) {                                     // напрямні магнетизму; mx/my — з координат режиму в пікселі полотна
  px.strokeStyle = '#ff4dd2'; px.lineWidth = pvScale();
  for (const [ax, v] of pvGuides) { px.beginPath(); ax === 'x' ? (px.moveTo(mx(v), 0), px.lineTo(mx(v), pv.height)) : (px.moveTo(0, my(v)), px.lineTo(pv.width, my(v))); px.stroke(); }
}
// ── прев'ю: кадрування (як Crop у Photoshop / OBS: ручки на кутах і сторонах, пропорції, магнетизм) ──
const fitR = () => { const s = Math.min(pv.width / S.w, pv.height / S.h); return {x: (pv.width - S.w * s) / 2, y: (pv.height - S.h * s) / 2, w: S.w * s, h: S.h * s}; };
const srcEls = () => { const list = pvEls(); return list.filter(e => e.on && ((e.type === 'video' || e.type === 'cam') || isZoom(e) && e.src && fxRef(list, e) && (e.id === selEl || visible(e)))); };   // кадри цього кліпу; рамка призуму — коли вибрана чи йде
const cropEl = () => srcEls().find(e => e.id === selEl) || null;
const zoomRatio = f => { const r = fxRef(pvEls(), f); return r ? pxRatio(r.src) : 0; };   // рамка призуму — у пропорціях шару, який вона кадрує
const RATIOS = [[0, 'Вільно'], [1, '1:1'], [4 / 3, '4:3'], [16 / 9, '16:9'], [9 / 16, '9:16']];
const HANDLE_SIDES = ['lt', 'rt', 'lb', 'rb', 't', 'r', 'b', 'l'];  // 0–3 кути, 4–7 середини сторін
const HANDLE_CURSOR = ['nwse-resize', 'nesw-resize', 'nesw-resize', 'nwse-resize', 'ns-resize', 'ew-resize', 'ns-resize', 'ew-resize'];
const cropHandles = ([x, y, w, h]) => [[x, y], [x + w, y], [x, y + h], [x + w, y + h], [x + w / 2, y], [x + w, y + h / 2], [x + w / 2, y + h], [x, y + h / 2]];
const pxRatio = ([, , w, h]) => (w * S.w) / (h * S.h);           // пропорції рамки в пікселях джерела
const hFor = (w, R) => w * S.w / (R * S.h), wFor = (h, R) => h * R * S.h / S.w;
function drawSrc() {
  px.fillStyle = '#000'; px.fillRect(0, 0, pv.width, pv.height);
  if (!P) return;
  const f = fitR(), cur = cropEl(); if (vid.videoWidth) px.drawImage(vid, f.x, f.y, f.w, f.h);
  if (cur) dimOutside(f, cur.src);
  for (const el of srcEls()) drawCropBox(el, f, el === cur);
  drawGuides(v => f.x + v * f.w, v => f.y + v * f.h);
}
function dimOutside(f, [x, y, w, h]) {                           // поза вибраною рамкою — притемнено
  px.fillStyle = 'rgba(10,9,8,.6)'; px.beginPath();
  px.rect(f.x, f.y, f.w, f.h); px.rect(f.x + x * f.w, f.y + y * f.h, w * f.w, h * f.h); px.fill('evenodd');
}
function drawCropBox(el, f, on) {
  const s = pvScale(), [x, y, w, h] = el.src, X0 = f.x + x * f.w, Y0 = f.y + y * f.h, W = w * f.w, H = h * f.h;
  px.strokeStyle = px.fillStyle = TYPES[el.type].col; px.lineWidth = (on ? 2 : 1.5) * s; px.strokeRect(X0, Y0, W, H);
  if (on) {                                                       // сітка третин і ручки
    px.strokeStyle = 'rgba(255,255,255,.35)'; px.lineWidth = s; px.beginPath();
    for (const q of [1 / 3, 2 / 3]) { px.moveTo(X0 + W * q, Y0); px.lineTo(X0 + W * q, Y0 + H); px.moveTo(X0, Y0 + H * q); px.lineTo(X0 + W, Y0 + H * q); }
    px.stroke(); px.strokeStyle = px.fillStyle = TYPES[el.type].col;
    const hs = HANDLE_PX * s; px.strokeStyle = '#000';
    cropHandles(el.src).slice(0, el.ratio ? 4 : 8).forEach(([hx, hy]) => { px.fillRect(f.x + hx * f.w - hs, f.y + hy * f.h - hs, hs * 2, hs * 2); px.strokeRect(f.x + hx * f.w - hs, f.y + hy * f.h - hs, hs * 2, hs * 2); });
  }
  const label = el.type === 'fx' ? `${tr(fxName(el))} · ${(fxRef(pvEls(), el)?.src[2] / w || 1).toFixed(1)}×` : `${tr(TYPES[el.type].name)} · ${Math.round(w * S.w)}×${Math.round(h * S.h)}`;
  px.font = `600 ${12 * s}px system-ui`; px.fillStyle = 'rgba(15,14,13,.85)'; px.fillRect(X0, Y0, px.measureText(label).width + 12 * s, 20 * s);
  px.fillStyle = TYPES[el.type].col; px.fillText(label, X0 + 6 * s, Y0 + 14 * s);
}
function cropHit(p) {                                             // ручка вибраної рамки, інакше рамка під курсором
  const f = fitR(), u = {x: (p.x - f.x) / f.w, y: (p.y - f.y) / f.h}, tol = (HANDLE_PX + 5) * pvScale(), cur = cropEl();
  if (cur) {
    const handle = cropHandles(cur.src).slice(0, cur.ratio ? 4 : 8).findIndex(([hx, hy]) => Math.abs(f.x + hx * f.w - p.x) < tol && Math.abs(f.y + hy * f.h - p.y) < tol);
    if (handle >= 0) return {el: cur, handle, u};
  }
  const inBox = ([x, y, w, h]) => u.x >= x && u.x <= x + w && u.y >= y && u.y <= y + h;
  return {el: [cur, ...srcEls().reverse()].find(e => e && inBox(e.src)), u};
}
function nearest(targets, pts, tol) {                             // найближча пара «ціль — край», або null
  let b = null;
  for (const v of targets) for (const p of pts) { const d = Math.abs(v - p); if (d < tol && (!b || d < b.d)) b = {d, shift: v - p, v}; }
  return b;
}
function cropSnapper(own, off) {                                  // магнетизм до країв і центру кадру та інших рамок
  const f = fitR(), tol = SNAP_PX * pvScale(), tx = [0, .5, 1], ty = [0, .5, 1], guides = [];
  for (const o of srcEls()) if (o !== own) { const [x, y, w, h] = o.src; tx.push(x, x + w / 2, x + w); ty.push(y, y + h / 2, y + h); }
  const axis = (ax, vals, size) => pts => { if (off) return 0; const b = nearest(vals, pts, tol / size); if (b) guides.push([ax, b.v]); return b ? b.shift : 0; };
  return {x: axis('x', tx, f.w), y: axis('y', ty, f.h), guides};
}
function resizeFree(d, dx, dy, sn) {
  const [x, y, w, h] = d.r, sides = HANDLE_SIDES[d.handle], m = .02;
  let l = x, r = x + w, t = y, b = y + h;
  if (sides.includes('l')) { l += dx; l = clamp(l + sn.x([l]), 0, r - m); }
  if (sides.includes('r')) { r += dx; r = clamp(r + sn.x([r]), l + m, 1); }
  if (sides.includes('t')) { t += dy; t = clamp(t + sn.y([t]), 0, b - m); }
  if (sides.includes('b')) { b += dy; b = clamp(b + sn.y([b]), t + m, 1); }
  return [l, t, r - l, b - t];
}
function resizeLocked(d, u, R, sn) {                              // кут із фіксованими пропорціями; протилежний кут стоїть
  const [x, y, w, h] = d.r, left = d.handle % 2 === 0, top = d.handle < 2, ax = left ? x + w : x, ay = top ? y + h : y;
  let nw = Math.max(Math.abs(u.x - ax), wFor(Math.abs(u.y - ay), R));
  const ex = left ? ax - nw : ax + nw, sx = sn.x([ex]);
  if (sx) nw = Math.abs(ex + sx - ax);
  else { const ey = top ? ay - hFor(nw, R) : ay + hFor(nw, R), sy = sn.y([ey]); if (sy) nw = wFor(Math.abs(ey + sy - ay), R); }
  nw = Math.max(.02, Math.min(nw, left ? ax : 1 - ax, wFor(top ? ay : 1 - ay, R)));
  const nh = hFor(nw, R); return [left ? ax - nw : ax, top ? ay - nh : ay, nw, nh];
}
function dragCrop(u, ev) {
  const d = drag, [x, y, w, h] = d.r, dx = u.x - d.u.x, dy = u.y - d.u.y, sn = cropSnapper(d.src, ev.ctrlKey);
  if (d.handle == null) {
    const nx = x + dx + sn.x([x + dx, x + dx + w / 2, x + dx + w]), ny = y + dy + sn.y([y + dy, y + dy + h / 2, y + dy + h]);
    d.src.src = [clamp(nx, 0, 1 - w), clamp(ny, 0, 1 - h), w, h];
  } else {
    const R = d.src.ratio || (ev.shiftKey && d.handle < 4 ? pxRatio(d.r) : 0);
    d.src.src = R && d.handle < 4 ? resizeLocked(d, u, R, sn) : resizeFree(d, dx, dy, sn);
  }
  pvGuides = sn.guides;
}
function applyRatio(el, R) {                                      // підігнати рамку під пропорції навколо її центру
  el.ratio = R;
  if (R) {
    const [x, y, w, h] = el.src; let nw = wFor(h, R), nh = h;
    if (nw > 1) { nw = 1; nh = hFor(1, R); }
    el.src = [clamp(x + w / 2 - nw / 2, 0, 1 - nw), clamp(y + h / 2 - nh / 2, 0, 1 - nh), nw, nh];
  }
  save();
}
function cropAction(el, act) {
  const [x, y, w, h] = el.src;
  if (act === 'full') { el.src = [0, 0, 1, 1]; if (el.ratio) return applyRatio(el, el.ratio); }
  else el.src = [act === 'cy' ? x : (1 - w) / 2, act === 'cx' ? y : (1 - h) / 2, w, h];
  save();
}
// ── прев'ю: вибір, перетягування, розмір ──
function pvPoint(e) { return {x: e.offsetX * pv.width / pv.clientWidth, y: e.offsetY * pv.height / pv.clientHeight}; }
const toShort = p => ({x: p.x * CW() / pv.width, y: p.y * CW() / pv.width});
function snapTargets(el) {
  const tx = [0, CW() / 2, CW()], ty = [0, CH() / 2, CH()];
  for (const o of [...pvEls(), ...ownCuesNow().map(cueStyle)]) if (o !== el && o.type !== 'bg' && o.type !== 'fx' && visible(o)) { const r = rectOf(o); tx.push(r.x, r.x + r.w / 2, r.x + r.w); ty.push(r.y, r.y + r.h / 2, r.y + r.h); }
  return {tx, ty};
}
function snapRect(el, x, y, w, h, off) {                          // магнетизм до центру, країв кадру й інших елементів
  if (off) { pvGuides = []; return [x, y]; }
  const {tx, ty} = snapTargets(el), tol = shortUnits(SNAP_PX), sx = nearest(tx, [x, x + w / 2, x + w], tol), sy = nearest(ty, [y, y + h / 2, y + h], tol);
  pvGuides = [...(sx ? [['x', sx.v]] : []), ...(sy ? [['y', sy.v]] : [])];
  return [x + (sx ? sx.shift : 0), y + (sy ? sy.shift : 0)];
}
function snapScale(el, r, f, off) {                               // при зміні розміру правий або нижній край прилипає
  pvGuides = []; if (off) return f;
  const {tx, ty} = snapTargets(el), tol = shortUnits(SNAP_PX), sx = nearest(tx, [r.x + r.w * f], tol), sy = nearest(ty, [r.y + r.h * f], tol);
  const best = sx && (!sy || sx.d <= sy.d) ? ['x', sx.v, (sx.v - r.x) / r.w] : sy && r.h ? ['y', sy.v, (sy.v - r.y) / r.h] : null;
  if (!best || best[2] < .15) return f;
  pvGuides = [[best[0], best[1]]]; return best[2];
}
function elAt(q) {                                                // елемент під курсором; вибраний має пріоритет
  const shown = pvEls(), cues = ownCuesNow(), cueOf = st => cues.find(c => c.own === st);
  const order = [...cues.map(cueStyle), ...shown.filter(e => e.type === 'subs'), ...shown.filter(e => e.type !== 'subs').reverse()].filter(e => e.type !== 'bg' && e.type !== 'fx' && visible(e));
  const tol = shortUnits(HANDLE_PX + 6);
  for (const el of [selShown(), ...order].filter(Boolean)) {
    const r = rectOf(el), cue = cueOf(el);
    if (TYPES[el.type].size.length && Math.abs(q.x - r.x - r.w) < tol && Math.abs(q.y - r.y - r.h) < tol) return {el, resize: true, r, cue};
    if (q.x >= r.x && q.x <= r.x + r.w && q.y >= r.y && q.y <= r.y + r.h) return {el, r, cue};
  }
  return null;
}
pv.onpointerdown = e => {
  if (!P || e.button !== 0) return; pv.setPointerCapture(e.pointerId); const p = pvPoint(e);
  if (mode === 'short') {
    const q = toShort(p), h = elAt(q);
    if (!h) { if (selEl) { selEl = null; selOwn = null; renderEls(); } return; }
    drag = {el: h.el, q, r: h.r, resize: h.resize, v: TYPES[h.el.type].size.map(s => h.el[s])};
    const own = h.el === elById(h.el.id) ? null : h.el;            // екземпляр кліпу чи репліка зі своїм стилем
    if (h.cue) { selectCue(P.cues.indexOf(h.cue), false); focus = 'el'; }
    if (selEl !== h.el.id || selOwn !== own) { selEl = h.el.id; selOwn = own; renderEls(); }
    return;
  }
  const h = cropHit(p); if (!h.el) { if (selEl) { selEl = null; renderEls(); } return; }
  if (isZoom(h.el)) h.el.ratio = zoomRatio(h.el);
  drag = {src: h.el, handle: h.handle < 0 ? null : h.handle, u: h.u, r: [...h.el.src]};
  if (selEl !== h.el.id) { selEl = h.el.id; renderEls(); }
};
function hoverCursor(p) {
  if (mode === 'short') { const h = elAt(toShort(p)); return h ? (h.resize ? 'nwse-resize' : 'move') : ''; }
  const h = cropHit(p); return h.handle != null && h.handle >= 0 ? HANDLE_CURSOR[h.handle] : h.el ? 'move' : '';
}
pv.onpointermove = e => {
  if (!P) return; const p = pvPoint(e);
  if (!drag || !(drag.el || drag.src)) { pv.style.cursor = hoverCursor(p); return; }
  if (drag.src) { const f = fitR(); return dragCrop({x: (p.x - f.x) / f.w, y: (p.y - f.y) / f.h}, e); }
  const q = toShort(p), dx = q.x - drag.q.x, dy = q.y - drag.q.y, el = drag.el, r = drag.r;
  if (drag.resize) {
    const f = snapScale(el, r, Math.max(.15, (r.w + dx) / r.w), e.ctrlKey);
    TYPES[el.type].size.forEach((s, i) => el[s] = s === 's' ? clamp(drag.v[i] * f, .3, 3) : Math.max(s === 'size' ? 12 : 40, drag.v[i] * f));
  } else if (el.type === 'progress') { el.y = clamp(r.y + dy, 0, CH() - el.h); el.pos = el.y < CH() / 2 ? 'top' : 'bottom'; }
  else [el.x, el.y] = snapRect(el, r.x + dx, r.y + dy, r.w, r.h, e.ctrlKey);
};
pv.onpointerup = () => { pvGuides = []; if (drag && (drag.el || drag.src)) { drag = null; renderProps(); save(); } drag = null; };
