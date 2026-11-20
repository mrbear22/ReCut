// Таймлайн: кліпи, смужки елементів, репліки, область аналізу, магнетизм.
// ── таймлайн: одне полотно — область, кліпи зі смужками елементів, репліки внизу ──
let K = 1, TICK, CTOP, CHEAD, BAR, CUE;                          // масштаб інтерфейсу під розмір вікна
const TL_GROW_MAX = 4, TL_MAX_SHARE = .6;                         // у скільки разів можна збільшити доріжки й яку частку вікна взяти
let tlK = (() => { try { return clamp(+localStorage.getItem('tlK') || 1, 1, TL_GROW_MAX); } catch (e) { return 1; } })();   // висота, яку людина витягнула
const font = (n, w = '') => `${w} ${n}px Onest, system-ui`;
function scaleUI() {
  K = clamp(Math.min(innerWidth / 1500, innerHeight / 880), 1, 1.6);
  const cueK = 1 + (tlK - 1) / 2;                                 // рядок реплік росте вдвічі повільніше за доріжки
  [TICK, CTOP, CHEAD, BAR, CUE] = [18, 22, 22 * K * tlK, 15 * K * tlK, 24 * K * cueK].map(Math.round);   // вищі доріжки, а не більший текст
  if (P) fitTL(); resizeTL();
}
scaleUI();
// ── висота таймлайна: тягни смужку над ним; подвійний клік — як було ──
function setTlHeight(h) {
  const n = Math.max(1, laneEls().length), fixed = CTOP + 16 + 12 * K, rows = K * (22 + 15 * n + 12);   // H = fixed + rows·tlK (див. scaleUI)
  tlK = clamp((Math.min(h, innerHeight * TL_MAX_SHARE) - fixed) / rows, 1, TL_GROW_MAX); scaleUI();
}
const keepTlK = () => { try { localStorage.setItem('tlK', tlK); } catch (e) {} };
let gripDrag = null;
$('#tlGrip').onpointerdown = e => { $('#tlGrip').setPointerCapture(e.pointerId); gripDrag = {y: e.clientY, h: geo().H}; };
$('#tlGrip').onpointermove = e => { if (gripDrag) setTlHeight(gripDrag.h + gripDrag.y - e.clientY); };
$('#tlGrip').onpointerup = () => { gripDrag = null; keepTlK(); };
$('#tlGrip').ondblclick = () => { tlK = 1; scaleUI(); keepTlK(); };
const laneEls = (c = P?.clips.length ? ctxClip() : null) => els().filter(e => !['subs', 'bg'].includes(e.type) && inClip(c, e)).slice().reverse();
const geo = () => { const cb = CTOP + CHEAD + Math.max(1, laneEls().length) * BAR + 6, rows = subRows().length;
  return {cb, cueY: cb + 6, rows, H: cb + 6 + rows * CUE + 4}; };
const spAt = y => { const {cueY, rows} = geo(); return clamp(Math.floor((y - cueY) / CUE), 0, rows - 1); };   // рядок спікера під курсором
const X = t => (t - view.t0) / (view.t1 - view.t0) * TW, Tt = x => view.t0 + x / TW * (view.t1 - view.t0);
function fitTL() { const h = geo().H; if (tl.clientHeight !== h) { tl.style.height = h + 'px'; resizeTL(); } }
function resizeTL() { const d = devicePixelRatio || 1; TW = tl.clientWidth; TH = tl.clientHeight; tl.width = TW * d; tl.height = TH * d; tx.setTransform(d, 0, 0, d, 0, 0); }
addEventListener('resize', scaleUI);
function clampView() { const span = Math.min(dur, Math.max(2, view.t1 - view.t0)); view.t0 = clamp(view.t0, 0, dur - span); view.t1 = view.t0 + span; }
const rr = (x, y, w, h, r) => { tx.beginPath(); tx.roundRect(x, y, Math.max(0, w), h, r); };
// частини показу елемента в кліпі: [[з, до], …] — секунди від початку кліпу без пропусків, «до» 0 — до кінця.
// Свої для кліпу (c.segs[id], [] — сховано в цьому кліпі) або спільні з елемента (from/to)
const inClip = (c, e) => !e.solo || !!c?.segs?.[e.id];
const segsOf = (c, e) => c?.segs?.[e.id] ?? (e.solo ? [] : [[e.from || 0, e.to || 0]]);
const ownSegs = (c, e) => ((c.segs ||= {})[e.id] ||= segsOf(c, e).map(x => [...x]));   // перша зміна в кліпі — копія спільних
const segSpan = (c, x) => [toSrc(c, x[0] || 0), x[1] ? toSrc(c, x[1]) : c.b];
function tidySegs(c, e) {                                         // по порядку; ті, що перекрились, — злити (дотичні лишаються окремими)
  const n = net(c), out = [];
  for (const [a, b] of [...(c.segs[e.id] || [])].sort((x, y) => x[0] - y[0])) {
    const end = b || n, last = out.at(-1);
    if (last && a < (last[1] || n) - .01) last[1] = Math.max(last[1] || n, end) >= n - .05 ? 0 : Math.max(last[1] || n, end);
    else if (end - a > .1) out.push([a, end >= n - .05 ? 0 : end]);
  }
  c.segs[e.id] = out;
}
// приглушена палітра таймлайна (як кліпи в Resolve); поза областю аналізу — темніше тло
const PAL = {out: '#0b0a09', bg: '#141311', ruler: '#181614', line: '#272420', grid: '#1b1917', tick: '#5a544c', text: '#958e83',
  curve: '#2c2618', curveOut: '#1a1712', acc: '#ffcc33', blue: '#5e7fa3', blueDk: '#2b3644', accDk: '#3d3216', off: '#56524d', offDk: '#22211f',
  red: '#b5574e', redDk: '#3a2422', green: '#6aa87a', greenDk: '#263529', greenSel: '#36573f', cueText: '#e3ece5', guide: '#d08ab4', play: '#e2533f'};
const mixHex = (a, b, t) => '#' + [1, 3, 5].map(i => Math.round(parseInt(a.substr(i, 2), 16) * (1 - t) + parseInt(b.substr(i, 2), 16) * t).toString(16).padStart(2, '0')).join('');
function curvePath() {                                            // «енергія» моменту як суцільна фігура під усім полотном
  const path = new Path2D(); path.moveTo(0, TH);
  for (let x = 0; x <= TW; x += 2) {
    let v = lo; const i0 = Math.floor((Tt(x) - t0) / step), i1 = Math.max(i0, Math.floor((Tt(x + 2) - t0) / step));
    for (let i = i0; i <= i1; i++) if (curve[i] > v) v = curve[i];
    path.lineTo(x, TH - (v - lo) / (hi - lo) * (TH - CTOP) * .9);
  }
  path.lineTo(TW, TH); path.closePath(); return path;
}
function drawTL() {
  tx.fillStyle = PAL.out; tx.fillRect(0, 0, TW, TH);
  if (!dur || !P) return;
  const {cb, cueY} = geo(), span = view.t1 - view.t0, [ra, rb] = region(), xa = X(ra), xb = X(rb), cc = P.clips.length ? ctxClip() : null;
  const la = clamp(xa, 0, TW), lb = clamp(xb, 0, TW);
  tx.fillStyle = PAL.bg; tx.fillRect(la, 0, lb - la, TH);                                // область аналізу світліша за решту
  const tick = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600].find(s => TW / (span / s) > 70) || 7200;
  for (let t = Math.ceil(view.t0 / tick) * tick; t < view.t1; t += tick) { tx.fillStyle = PAL.grid; tx.fillRect(X(t), TICK, 1, TH); }
  if (curve.length) {
    const path = curvePath();
    tx.save(); tx.beginPath(); tx.rect(la, 0, lb - la, TH); tx.clip(); tx.fillStyle = PAL.curve; tx.fill(path); tx.restore();
    tx.save(); tx.beginPath(); tx.rect(0, 0, la, TH); tx.rect(lb, 0, TW - lb, TH); tx.clip(); tx.fillStyle = PAL.curveOut; tx.fill(path); tx.restore();
  }
  tx.font = "10.5px 'JetBrains Mono', monospace"; tx.fillStyle = PAL.ruler; tx.fillRect(0, 0, TW, TICK); tx.fillStyle = PAL.line; tx.fillRect(0, TICK, TW, 1);   // шкала часу
  for (let t = Math.ceil(view.t0 / tick) * tick; t < view.t1; t += tick) { const x = X(t); tx.fillStyle = PAL.tick; tx.fillRect(x, TICK - 5, 1, 5); tx.fillStyle = PAL.text; tx.fillText(fmt(t).replace(/\.\d$/, ''), x + 4, TICK * .72); }
  // кліпи; у вибраному — смужки елементів
  if (!P.clips.length) { tx.font = font(clamp(Math.round(CUE * .5), 12, 17)); tx.fillStyle = PAL.tick; tx.fillText('кліпи · Shift + перетягування — новий кліп, або «Знайти моменти»', 8, (CTOP + cb) / 2 + 5); }
  P.clips.forEach((c, i) => {
    const x0 = X(c.a), x1 = X(c.b); if (x1 < 0 || x0 > TW) return;
    const s = i === sel || multi.has(c), ctx = c === cc, col = !c.on ? PAL.off : s ? PAL.acc : c.col || PAL.blue; tx.font = font(11, 600);
    rr(x0, CTOP, x1 - x0, cb - CTOP, 0); tx.fillStyle = !c.on ? PAL.offDk : c.col ? mixHex(c.col, PAL.bg, s ? .45 : .6) : s ? PAL.accDk : PAL.blueDk; tx.fill();
    tx.strokeStyle = col; tx.lineWidth = s ? 2 : 1; tx.stroke();
    for (const [u, v] of c.cut || []) {
      const a = X(Math.max(u, c.a)), b = X(Math.min(v, c.b)); if (b <= a) continue;
      tx.fillStyle = PAL.redDk; tx.fillRect(a, CTOP + 1, b - a, cb - CTOP - 2);
      tx.fillStyle = PAL.red; tx.fillRect(a, CTOP + 1, 2, cb - CTOP - 2); tx.fillRect(b - 2, CTOP + 1, 2, cb - CTOP - 2);
    }
    tx.fillStyle = col; tx.fillRect(x0, CTOP + 6, 3, cb - CTOP - 12); tx.fillRect(x1 - 3, CTOP + 6, 3, cb - CTOP - 12);
    if (hookOk(c)) { const a = X(c.hook[0]), b = X(c.hook[1]); tx.fillStyle = HOOK_COL + '30'; tx.fillRect(a, CTOP + 1, b - a, cb - CTOP - 2); tx.fillStyle = HOOK_COL; tx.fillRect(a, CTOP + 1, b - a, 3); tx.fillStyle = col; }
    if (c.loop != null && loopOk(c, c.loop)) { const lx = X(c.loop); tx.fillStyle = LOOP_COL; tx.fillRect(lx - 1, CTOP + 1, 2, cb - CTOP - 2); tx.fillText('↻', lx + 5, CTOP + 15); }
    tx.fillStyle = col; tx.fillText(`#${i + 1}  ${clipLen(c).toFixed(1)} с`, x0 + 8, CTOP + 15);
    if (!ctx) return;
    tx.font = font(clamp(Math.round(BAR * .6), 11, 15));            // у витягнутих доріжках підписи більші
    laneEls().forEach((e, j) => {
      const y = CTOP + CHEAD + j * BAR, Ty = TYPES[e.type], segs = segsOf(c, e), own = !!c.segs?.[e.id];
      const on = e.id === selEl, fill = !e.on ? PAL.offDk : on ? Ty.col : mixHex(Ty.col, PAL.bg, .62);   // невибрані — приглушений суцільний колір
      const ink = !e.on ? PAL.off : on ? '#151413' : mixHex(Ty.col, '#ffffff', .5);
      if (!segs.length) {                                         // сховано в цьому кліпі
        const a = X(c.a), b = X(c.b); tx.save(); tx.setLineDash([4, 4]); tx.strokeStyle = mixHex(Ty.col, PAL.bg, .2); tx.lineWidth = 1;
        tx.strokeRect(a + 1.5, y + 1.5, b - a - 3, BAR - 3); tx.restore();
        if (b - a > 80) { tx.fillStyle = mixHex(Ty.col, PAL.bg, .15); tx.fillText(`${Ty.name} · сховано`, a + 6, y + BAR * .73); }
        return;
      }
      segs.forEach(x => {
        const [sa, sb] = segSpan(c, x), a = X(sa), b = X(sb);
        rr(a + 1, y + 1, b - a - 2, BAR - 2, 0); tx.fillStyle = fill; tx.fill(); if (on) { tx.strokeStyle = '#fff'; tx.lineWidth = 1; tx.stroke(); }
        if (e.type === 'music') drawWave(e, c, a, b, y, on ? 'rgba(21,20,19,.45)' : mixHex(Ty.col, '#ffffff', .25));
        if (own) { tx.fillStyle = on ? '#151413' : mixHex(Ty.col, '#ffffff', .3); tx.fillRect(a + 1, y + 2, 2, BAR - 4); tx.fillRect(b - 3, y + 2, 2, BAR - 4); }   // свої частини кліпу — з рисками
        if (b - a > 40) { tx.save(); tx.beginPath(); tx.rect(a + 4, y, b - a - 8, BAR); tx.clip(); tx.fillStyle = ink;
          tx.fillText(e.type === 'music' ? `♪ ${e.name}${(e.vol ?? 1) !== 1 ? ` · ${Math.round(e.vol * 100)}%` : ''}` : Ty.name, a + 6, y + BAR * .73); tx.restore(); }
      });
    });
  });
  const dEl = elById(dragEl);
  if (dEl) P.clips.forEach((c, i) => {                             // тягнуть елемент зі списку: кожен кліп — ціль, над тим, що під курсором, — що станеться
    const x0 = X(c.a), x1 = X(c.b); if (x1 < 0 || x0 > TW) return;
    const has = inClip(c, dEl) && segsOf(c, dEl).length > 0, hot = c === dropAt;
    if (hot) { rr(x0, CTOP, x1 - x0, cb - CTOP, 0); tx.fillStyle = has ? 'rgba(20,19,18,.45)' : PAL.acc + '2e'; tx.fill(); }
    if (!has || hot) {
      rr(x0 + 1, CTOP + 1, x1 - x0 - 2, cb - CTOP - 2, 0); tx.strokeStyle = has ? PAL.tick : PAL.acc; tx.lineWidth = hot ? 3 : 1.5;
      tx.setLineDash(hot ? [] : [6, 4]); tx.stroke(); tx.setLineDash([]);
    }
    if (!hot) return;
    const t = has ? 'уже в цьому кліпі' : `+ ${TYPES[dEl.type].name} у кліп #${i + 1}`; tx.font = font(12, 600);
    const w = tx.measureText(t).width + 20, h = 24, x = clamp((Math.max(0, x0) + Math.min(TW, x1)) / 2 - w / 2, 2, Math.max(2, TW - w - 2)), y = (CTOP + cb) / 2 - h / 2;
    rr(x, y, w, h, 12); tx.fillStyle = has ? PAL.off : PAL.acc; tx.fill(); tx.fillStyle = has ? PAL.cueText : '#1b1712'; tx.fillText(t, x + 10, y + 16);
  });
  // репліки субтитрів — рядок унизу того самого полотна
  tx.font = font(clamp(Math.round(CUE * .5), 12, 17));
  const spk = subRows(), named = subsEls().length > 0;
  spk.forEach((x, r) => {                                         // назва доріжки — під репліками; порожня доріжка — як почати
    const ty = cueY + r * CUE + CUE * .67, nm = named ? subName(x, r) : 'субтитри';
    if (r % 2) { tx.fillStyle = PAL.grid; tx.fillRect(0, cueY + r * CUE, TW, CUE); }
    rowWave(audioTracks > 1 ? r % audioTracks : 0, cueY + r * CUE);
    tx.fillStyle = named ? mixHex(x.color, PAL.bg, x.on === false ? .8 : .55) : PAL.tick; tx.fillText(nm, 8, ty);
    if (!P.cues.some(c => rowOf(c) === r)) { tx.fillStyle = PAL.tick; tx.fillText('Shift + перетягування — нова репліка', 8 + tx.measureText(nm).width + 14, ty); }
  });
  P.cues.forEach((c, j) => {
    const x0 = X(c.a), x1 = X(c.b); if (x1 < 0 || x0 > TW) return;
    const y = cueY + rowOf(c) * CUE, col = cueOwner(c)?.color || '#ffffff', on = j === selCue || multi.has(c);
    rr(x0 + 1, y + 1, x1 - x0 - 2, CUE - 2, 0); tx.fillStyle = mixHex(col, PAL.bg, on ? .55 : .78); tx.fill();
    tx.strokeStyle = on ? PAL.acc : mixHex(col, PAL.bg, .35); tx.lineWidth = on ? 2 : 1; tx.stroke();
    if (x1 - x0 > 14) {                                           // ручки на краях, як у кліпів: за них тягнуть межі репліки
      tx.fillStyle = on ? PAL.acc : mixHex(col, '#ffffff', .15);
      tx.fillRect(x0 + 1, y + 5, 3, CUE - 10); tx.fillRect(x1 - 4, y + 5, 3, CUE - 10);
    }
    const t = vid.currentTime, w = wordsOf(c), ink = mixHex(col, '#ffffff', .4), text = (s, a, b, at) => {
      if (b - a < 12) return; tx.save(); tx.beginPath(); tx.rect(a, y, b - a, CUE); tx.clip(); tx.fillStyle = ink; tx.fillText(s, at, y + CUE * .67); tx.restore(); };
    if (t > c.a + .1 && t < c.b - .1 && w.length > 1) {          // курсор на репліці: які слова лишаться ліворуч, а які підуть праворуч
      const n = splitIdx(c, t, w), p = X(t);
      text(w.slice(0, n).join(' '), x0 + 4, p - 4, x0 + 7); text(w.slice(n).join(' '), p + 4, x1 - 4, p + 7);
      tx.fillStyle = PAL.play; tx.fillRect(p - 1, y + 2, 2, CUE - 4);
    } else if (x1 - x0 > 24) text(c.text, x0 + 4, x1 - 4, x0 + 7);
  });
  tx.font = font(11);
  // межі області — на всю висоту, ручки на шкалі
  tx.fillStyle = PAL.acc; tx.fillRect(xa - 1, 0, 2, TH); tx.fillRect(xb - 1, 0, 2, TH);
  for (const [x, nm] of [[xa, 'a'], [xb, 'b']]) { rr(x - 5, 0, 10, TICK + 6, 0); tx.fillStyle = drag && drag.region === nm ? '#fff' : PAL.acc; tx.fill(); }
  if (drag?.lasso && drag.moved) {                                 // рамка лассо
    const [ax, ay, bx, by] = drag.lasso; rr(Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax), Math.abs(by - ay), 2);
    tx.fillStyle = PAL.acc + '1f'; tx.fill(); tx.strokeStyle = PAL.acc; tx.lineWidth = 1; tx.stroke();
  }
  if (drag && guide != null) { tx.strokeStyle = PAL.guide; tx.setLineDash([4, 3]); tx.beginPath(); tx.moveTo(X(guide), 0); tx.lineTo(X(guide), TH); tx.stroke(); tx.setLineDash([]); }
  const p = X(vid.currentTime); tx.fillStyle = PAL.play; tx.fillRect(p - 1, TICK - 2, 2, TH);   // курсор з ручкою на шкалі
  tx.beginPath(); const kw = 7; tx.moveTo(p - kw, 2); tx.lineTo(p + kw, 2); tx.lineTo(p + kw, TICK - kw + 1); tx.lineTo(p, TICK); tx.lineTo(p - kw, TICK - kw + 1); tx.closePath(); tx.fill();
  if ((loopKey || drag?.hook) && hover) {                         // де стане петля чи хук
    const t = Tt(hover.x), hk = drag?.hook?.moved && drag.hook, c = !hk && P.clips.find(c => loopOk(c, t)), lx = X(t);
    if (c) { tx.strokeStyle = LOOP_COL; tx.lineWidth = 2; tx.setLineDash([5, 3]); tx.beginPath(); tx.moveTo(lx, CTOP); tx.lineTo(lx, cb); tx.stroke(); tx.setLineDash([]); }
    const label = hk ? `Хук ${hookLen(hk).toFixed(1)} с — на початок шорту` : c ? 'Клік — петля · тягни — хук на початок' : P.clips.some(c => t >= c.a && t <= c.b) ? 'Тягни — хук на початок' : 'Наведи на кліп';
    tx.font = font(12, 600); const lh = 22, w = tx.measureText(label).width + 16, bgc_ = hk ? HOOK_COL : LOOP_COL;
    const lbx = clamp(hover.x + 12, 0, TW - w), lby = clamp(hover.y - lh - 6, TICK + 2, TH - lh - 2);
    rr(lbx, lby, w, lh, 0); tx.fillStyle = bgc_; tx.fill(); tx.fillStyle = '#10232a'; tx.fillText(label, lbx + 8, lby + lh * .68); tx.font = font(11);
  }
  const mod = !loopKey && !drag?.hook && hover && hover.y >= TICK && MODS.find(m => hover[m.key]);
  if (mod) {                                                      // що зробить Shift / Alt / Ctrl
    const label = mod.key === 'alt' && !clipAt(Tt(hover.x)) ? 'Alt: тягни всередині кліпу' : mod.key === 'shift' && hover.y >= geo().cueY ? 'Shift: нова репліка' : mod.label;
    tx.font = font(12, 600); const lh = 22, w = tx.measureText(label).width + 16, lx = clamp(hover.x + 12, 0, TW - w), ly = clamp(hover.y - lh - 6, TICK + 2, TH - lh - 2);
    rr(lx, ly, w, lh, 0); tx.fillStyle = mod.col; tx.fill(); tx.fillStyle = mod.ink; tx.fillText(label, lx + 8, ly + lh * .68); tx.font = font(11);
  }
}
let loopKey = false;                                              // затиснутий правий Alt: клік по кліпу — петля, перетягування — хук
addEventListener('keydown', e => { if (e.code === 'AltRight') { loopKey = true; e.preventDefault(); } });
addEventListener('keyup', e => { if (e.code === 'AltRight') loopKey = false; });
addEventListener('blur', () => { loopKey = false; });
const loopOk = (c, t) => t > c.a + .5 && t < c.b - .5 && !(c.cut || []).some(([x, y]) => t >= x && t < y);
const LOOP_COL = '#5ec8e8', HOOK_COL = '#e07bd0';
const hookOk = c => c.hook?.length === 2 && c.hook[1] - c.hook[0] >= .3 && c.hook[0] >= c.a - .01 && c.hook[1] <= c.b + .01;
const hookLen = c => hookOk(c) ? toOut(c, c.hook[1]) - toOut(c, c.hook[0]) : 0;
const clipLen = c => net(c) + hookLen(c);                           // довжина готового шорту: з хуком на початку
const MODS = [{key: 'shift', label: 'Shift: новий кліп', col: '#3d4a5a', ink: '#e2dfda'}, {key: 'alt', label: 'Alt: вирізати шматок', col: '#5a2f2b', ink: '#f3dcd8'},
              {key: 'ctrl', label: 'Ctrl: нова область аналізу', col: '#f2b33d', ink: '#1b1712'}];
let hover = null;                                                 // курсор над таймлайном і затиснуті модифікатори
const setMods = e => { if (hover) { hover.shift = e.shiftKey; hover.alt = e.altKey; hover.ctrl = e.ctrlKey; if (e.shiftKey || e.altKey || e.ctrlKey) tl.style.cursor = 'crosshair'; } };
addEventListener('keydown', e => { setMods(e); if (e.key === 'Alt' && hover) e.preventDefault(); }); addEventListener('keyup', setMods);
tl.onpointerleave = () => hover = null;
// ── магнетизм: краї кліпів, пропусків, області, реплік, елементів і курсор ──
function snapPts(own) {
  const pts = [...(own === 'ph' ? [] : [vid.currentTime]), ...region()], c = P.clips.length ? ctxClip() : null;   // 'ph' — тягнуть сам курсор
  for (const k of P.clips) if (k !== own) { pts.push(k.a, k.b); for (const u of k.cut || []) if (u !== own) pts.push(...u); }
  for (const q of P.cues) if (q !== own) pts.push(q.a, q.b);
  if (c) for (const e of laneEls()) for (const x of segsOf(c, e)) if (x !== own) pts.push(...segSpan(c, x));
  return pts;
}
let snapOff = false;                                              // Ctrl під час перетягування — без магнетизму
function snap(t, own) {
  if (snapOff) { guide = null; return t; }
  let best = null; for (const v of snapPts(own)) { const d = Math.abs(X(v) - X(t)); if (d < 8 && (!best || d < best.d)) best = {v, d}; }
  guide = best ? best.v : null; return best ? best.v : t;
}
const snapSpan = (a, len, own) => { const s = snap(a, own); if (guide != null) return s; const e = snap(a + len, own); return e - len; };
function hit(x, y) {
  const xpx = x, t = Tt(x), {cb, cueY} = geo(), [ra, rb] = region();
  if (y < TICK + 2) {                                             // шкала часу: ручки області, решта — перемотка
    if (Math.abs(X(ra) - x) < 7) return {region: 'a'};
    if (Math.abs(X(rb) - x) < 7) return {region: 'b'};
    return {seek: true, scrub: true};
  }
  if (y >= cueY) {
    const row = spAt(y), inRow = c => c && rowOf(c) === row;
    for (const j of [selCue, ...P.cues.keys()]) {
      const c = P.cues[j]; if (!inRow(c)) continue;
      if (Math.abs(X(c.a) - x) < 5) return {cue: j, edge: 'a'};
      if (Math.abs(X(c.b) - x) < 5) return {cue: j, edge: 'b'};
    }
    const j = P.cues.findIndex(c => inRow(c) && t >= c.a && t <= c.b);
    return j >= 0 ? {cue: j, move: t - P.cues[j].a} : {seek: true, lane: 'subs', sp: row};
  }
  const c = P.clips.length ? ctxClip() : null;
  if (c && y >= CTOP + CHEAD && y < cb - 6 && t >= c.a - (view.t1 - view.t0) * .01 && t <= c.b + (view.t1 - view.t0) * .01) {
    const e = laneEls()[Math.floor((y - CTOP - CHEAD) / BAR)];
    if (e) {
      const segs = segsOf(c, e);
      for (const [k, x] of segs.entries()) {
        const [sa, sb] = segSpan(c, x);
        if (Math.abs(X(sa) - xpx) < 6) return {bar: e, seg: k, edge: 'a', c};
        if (Math.abs(X(sb) - xpx) < 6) return {bar: e, seg: k, edge: 'b', c};
        if (t > sa && t < sb) return {bar: e, seg: k, move: toOut(c, t) - (x[0] || 0), c};
      }
      return {bar: e, c, pick: true};
    }
  }
  for (const i of [sel, ...P.clips.keys()]) {                // вибраний кліп має пріоритет на спільних краях
    const k = P.clips[i]; if (!k) continue;
    for (const [j, u] of (k.cut || []).entries()) for (const e of [0, 1]) if (Math.abs(X(u[e]) - x) < 6) return {i, cut: j, edge: e};
    if (Math.abs(X(k.a) - x) < 7) return {i, edge: 'a'};
    if (Math.abs(X(k.b) - x) < 7) return {i, edge: 'b'};
  }
  if (Math.abs(X(ra) - x) < 6) return {region: 'a'};
  if (Math.abs(X(rb) - x) < 6) return {region: 'b'};
  const i = P.clips.findIndex(k => t >= k.a && t <= k.b);
  return i >= 0 && y < cb ? {i, move: t - P.clips[i].a} : {seek: true};
}
tl.onmousedown = tl.onauxclick = e => { if (e.button === 1) e.preventDefault(); };
tl.onpointerdown = e => {
  if (!dur || !P) return;
  if (loopKey) {                                                  // клік — петля (шорт почнеться звідси), перетягування — хук на початок
    const t = snap(Tt(e.offsetX), 'ph'), c = P.clips.find(c => t >= c.a && t <= c.b); guide = null; if (!c) return;
    tl.setPointerCapture(e.pointerId); drag = {hook: c, t0: t, x0: e.offsetX, prev: c.hook, loop: c.loop}; return;
  }
  tl.setPointerCapture(e.pointerId);
  if (e.button === 1) { e.preventDefault(); drag = {pan: e.offsetX, v: {...view}}; tl.style.cursor = 'grabbing'; return; }
  if (e.button !== 0) return;
  drag = hit(e.offsetX, e.offsetY); drag.x0 = e.offsetX; multi.clear();
  if (drag.bar) selBar = drag.seg != null ? {c: drag.c, k: drag.seg} : null;
  focus = drag.bar ? 'el' : drag.cue != null ? 'cue' : drag.i != null ? 'clip' : focus;
  const t = Tt(e.offsetX), inLane = e.offsetY >= TICK + 2 && e.offsetY < geo().cueY;
  if (e.shiftKey && e.offsetY >= geo().cueY) {   // Shift+тягни в рядку реплік — нова репліка
    const sid = (subsEls()[spAt(e.offsetY)] || ensureSubs()).id, q = {a: snap(t), b: snap(t), text: 'Текст', k: [], sid}; P.cues.push(q); drag = {createCue: q, t0: q.a}; focus = 'cue'; return;
  }
  if (e.shiftKey && inLane) {                                     // Shift+тягни — новий кліп
    const c = {a: snap(t), b: snap(t), on: true, score: null}; P.clips.push(c); sel = P.clips.length - 1; drag = {create: c, t0: c.a}; focus = 'clip'; return;
  }
  if (e.ctrlKey && e.offsetY >= TICK + 2) {                       // Ctrl+тягни — нова область аналізу
    P.region = [snap(t), snap(t)]; drag = {regionNew: P.region[0]}; return;
  }
  if (e.altKey && inLane) {                                       // Alt+тягни по кліпу — вирізати нудне
    const i = P.clips.findIndex(k => t >= k.a && t <= k.b); if (i < 0) { drag = null; return; }
    const c = P.clips[i]; (c.cut ||= []).push([t, t]); sel = i; drag = {i, cut: c.cut.length - 1, edge: 1}; return;
  }
  if (drag.region) { if (!P.region) P.region = region(); drag.r0 = [...P.region]; return; }
  if (drag.bar) { selEl = drag.bar.id; selOwn = ownOf(drag.c, drag.bar); renderEls(); if (drag.pick) { seek(t); drag = {seek: true}; } return; }
  if (drag.seek && !drag.scrub) { drag = {lasso: [e.offsetX, e.offsetY, e.offsetX, e.offsetY], t: snap(t, 'ph')}; return; }   // порожнє місце: клік — курсор сюди, тягни — лассо
  if (drag.seek) seek(snap(t, 'ph'));
  else if (drag.cue != null) selectCue(drag.cue, false);           // курсор лишається там, де був: B розріже саме там
  else if (drag.i != null && sel !== drag.i) { sel = drag.i; selCue = -1; $('#cueEdit').classList.remove('on'); renderList(); renderProps(); }
};
$('#els').addEventListener('dragstart', e => { const r = e.target.closest('.el'); if (!r) return; dragEl = r.dataset.id; e.dataTransfer.setData('text/plain', dragEl); e.dataTransfer.effectAllowed = 'copy'; });
$('#els').addEventListener('dragend', () => { dragEl = dropAt = null; });
tl.addEventListener('dragover', e => {
  if (!elById(dragEl)) return; e.preventDefault(); const t = Tt(e.offsetX);
  dropAt = P.clips.find(c => t >= c.a && t <= c.b) || null; e.dataTransfer.dropEffect = dropAt ? 'copy' : 'none';
});
tl.addEventListener('dragleave', () => { dropAt = null; });
tl.addEventListener('drop', e => { e.preventDefault(); const el = elById(dragEl), c = dropAt; dragEl = dropAt = null; if (el && c) addToClip(el, c); });
tl.oncontextmenu = e => {
  e.preventDefault(); if (!P || !dur) return;
  const t = clamp(Tt(e.offsetX), 0, dur), h = hit(e.offsetX, e.offsetY), inCues = e.offsetY >= geo().cueY;
  if (multi.has(P.clips[h.i]) || multi.has(P.cues[h.cue])) return openMenu(e, multiMenu());   // ПКМ по вибраному лассо — дії з усім разом
  multi.clear();
  openMenu(e, h.cue != null ? cueMenu(h.cue, t) : h.bar ? [...segItems(h.bar, h.c, t, h.seg), ...elMenu(h.bar, t, 'звідси')] : h.i != null ? clipMenu(h.i, t, 'тут') : laneMenu(t, inCues, inCues ? spAt(e.offsetY) : 0));
};
tl.onpointermove = e => {
  hover = {x: e.offsetX, y: e.offsetY, shift: e.shiftKey, alt: e.altKey, ctrl: e.ctrlKey};
  if (!drag) {
    if (!P || !dur) return;
    const h = hit(e.offsetX, e.offsetY);
    tl.style.cursor = e.shiftKey || e.altKey || e.ctrlKey ? 'crosshair' : h.scrub ? 'pointer' : h.move != null ? 'grab' : h.region || h.edge != null ? 'ew-resize' : h.pick ? 'pointer' : 'default'; return;
  }
  if (drag.hook) {
    if (!drag.moved && Math.abs(e.offsetX - drag.x0) < 4) return; drag.moved = true; delete drag.hook.loop;   // хук замість петлі
    const c = drag.hook, t = clamp(snap(clamp(Tt(e.offsetX), 0, dur), c), c.a, c.b); c.hook = [Math.min(drag.t0, t), Math.max(drag.t0, t)]; return;
  }
  if (drag.lasso) {
    drag.lasso[2] = e.offsetX; drag.lasso[3] = e.offsetY;
    if (!drag.moved && Math.hypot(e.offsetX - drag.lasso[0], e.offsetY - drag.lasso[1]) < 5) return;
    drag.moved = true; return lassoPick(drag.lasso);
  }
  if (drag.pan != null) { const d = (e.offsetX - drag.pan) / TW * (drag.v.t1 - drag.v.t0); view.t0 = drag.v.t0 - d; view.t1 = drag.v.t1 - d; return clampView(); }
  const raw = clamp(Tt(e.offsetX), 0, dur), g = Math.min(10, dur);
  const made = drag.create || drag.createCue;
  if (made) { const t = snap(raw, made); made.a = Math.min(drag.t0, t); made.b = Math.max(drag.t0, t); return; }
  if (drag.regionNew != null) { const t = snap(raw); P.region = [Math.min(drag.regionNew, t), Math.max(drag.regionNew, t)]; return; }
  if (drag.move != null && !drag.moved) { if (Math.abs(e.offsetX - drag.x0) < 4) return; drag.moved = true; }   // клік — не перетягування
  if (drag.region) {
    const [a, b] = drag.r0;
    P.region = drag.region === 'a' ? [Math.min(snap(raw), b - g), b] : [a, Math.max(snap(raw), a + g)];
    return;
  }
  if (drag.seek) return seek(snap(raw, 'ph'));                   // курсор прилипає до країв; Ctrl — ні
  if (drag.bar && drag.seg != null) {                             // частина елемента в цьому кліпі
    const e = drag.bar, c = drag.c, n = net(c), x = ownSegs(c, e)[drag.seg]; if (!x) return;
    const end = x[1] || n;
    const mus = e.type === 'music', off = e.off || 0;
    if (drag.edge === 'a') x[0] = clamp(toOut(c, snap(raw, x)), mus ? Math.max(0, -off) : 0, end - .2);
    else if (drag.edge === 'b') { const v = Math.min(toOut(c, snap(raw, x)), mus ? (e.dur || 1e9) - off : 1e9); x[1] = v >= n - .05 ? 0 : Math.max(v, (x[0] || 0) + .2); }
    else if (mus) {                                              // зсув треку під шматками
      const sg = segsOf(c, e), lo = -Math.min(...sg.map(y => y[0] || 0)), hi = (e.dur || 1e9) - Math.max(...sg.map(y => y[1] || n));
      drag.off0 ??= off; e.off = clamp(drag.off0 - (toOut(c, raw) - ((x[0] || 0) + drag.move)), lo, Math.max(lo, hi));
    } else {                                                       // «до кінця» лишається таким, поки смужка впирається в кінець
      const len = end - (x[0] || 0), start = toSrc(c, clamp(toOut(c, raw) - drag.move, 0, n - len));
      const nf = clamp(toOut(c, snapSpan(start, toSrc(c, toOut(c, start) + len) - start, x)), 0, n - len);
      x[0] = nf; x[1] = nf + len < n - .05 ? nf + len : 0;
    }
    return;
  }
  if (drag.cue != null) {
    const c = P.cues[drag.cue];
    if (drag.edge === 'a') c.a = Math.min(snap(raw, c), c.b - .2); else if (drag.edge === 'b') c.b = Math.max(snap(raw, c), c.a + .2);
    else { const len = c.b - c.a, sh = clamp(snapSpan(raw - drag.move, len, c), 0, dur - len) - c.a; c.a += sh; c.b += sh; if (c.k) c.k = c.k.map(v => v + sh); }
    return;
  }
  const c = P.clips[drag.i];
  if (drag.cut != null) {
    const u = c.cut[drag.cut]; u[drag.edge] = clamp(snap(raw, u), c.a, c.b); seek(u[drag.edge]);
    if (u[0] > u[1]) { u.reverse(); drag.edge = 1 - drag.edge; }
  }
  else if (drag.edge === 'a') { c.a = Math.min(snap(raw, c), c.b - 1); seek(c.a); }
  else if (drag.edge === 'b') { c.b = Math.max(snap(raw, c), c.a + 1); seek(c.b); }
  else { const len = c.b - c.a; c.a = clamp(snapSpan(raw - drag.move, len, c), 0, dur - len); c.b = c.a + len; }
  updateRow(drag.i);
};
tl.addEventListener('pointermove', e => { snapOff = !!drag && e.ctrlKey && drag.regionNew == null; }, true);
tl.onpointerup = e => {
  if (drag && drag.lasso) { const {moved, t} = drag; drag = null; return moved ? lassoDone() : seek(t); }
  if (drag && drag.hook) {
    const c = drag.hook;
    if (!drag.moved) { if (loopOk(c, drag.t0)) { c.loop = drag.t0; delete c.hook; } }   // петля замість хука: або те, або те
    else if (!hookOk(c)) { if (drag.prev) c.hook = drag.prev; else delete c.hook; if (drag.loop != null) c.loop = drag.loop; }
    sel = P.clips.indexOf(c); drag = null; guide = null; return commit();
  }
  if (drag && drag.create) {                                      // Shift+клік без перетягування — кліп типової довжини
    const c = drag.create; if (c.b - c.a < .5) c.b = Math.min(dur, c.a + (cfg.min_len + cfg.max_len) / 2); overwrite('clip', c); sel = P.clips.indexOf(c); commit();
  }
  if (drag && drag.createCue) {                                   // Shift+клік у рядку реплік — репліка на 1.5 с, одразу пишемо текст
    const q = drag.createCue, nx = P.cues.find(x => x !== q && rowOf(x) === rowOf(q) && x.a > q.a); if (q.b - q.a < .3) q.b = Math.min(q.a + 1.5, nx ? nx.a : dur);
    overwrite('cue', q); P.cues.sort((x, y) => x.a - y.a); selectCue(P.cues.indexOf(q)); editCueText(); save();
  }
  if (drag && drag.regionNew != null) {                           // Ctrl+клік без перетягування — область ±min від точки
    let [a, b] = P.region; const g = Math.min(10, dur); if (b - a < g) { a = clamp(a - g / 2, 0, dur - g); b = a + g; } P.region = [a, b]; save();
  }
  if (drag && drag.move != null && drag.i != null && !drag.moved) seek(Tt(e.offsetX));   // клік по кліпу — вибрати й перемотати сюди
  if (drag && drag.cut != null) P.clips[drag.i].cut = P.clips[drag.i].cut.filter(([u, v]) => v - u >= .2);    // випадковий клік, не пропуск
  if (drag && drag.i != null && (drag.edge || drag.move != null) && P.clips[drag.i]) overwrite('clip', P.clips[drag.i]);
  if (drag && drag.i != null) commit();
  if (drag && drag.cue != null) { const c = P.cues[drag.cue]; P.cues.sort((x, y) => x.a - y.a); selCue = P.cues.indexOf(c); }
  if (drag && drag.bar && drag.seg != null && drag.c.segs?.[drag.bar.id]) tidySegs(drag.c, drag.bar);
  if (drag && drag.cue != null && P.cues[selCue]) overwrite('cue', P.cues[selCue]);
  if (drag && (drag.region || drag.cue != null || drag.bar)) { save(); renderProps(); }
  drag = null; guide = null; tl.style.cursor = '';
};
tl.onwheel = e => {
  e.preventDefault(); if (!dur) return;
  const span = view.t1 - view.t0;
  if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) { const d = (e.deltaX || e.deltaY) / TW * span; view.t0 += d; view.t1 += d; }
  else { const t = Tt(e.offsetX), ns = clamp(span * Math.exp(e.deltaY * .002), 2, dur); view.t0 = t - (t - view.t0) * ns / span; view.t1 = view.t0 + ns; }
  clampView();
};
tl.ondblclick = e => {                                            // привчаємо до Shift: подвійний клік лише підказує
  if (!dur || !P) return; const h = hit(e.offsetX, e.offsetY);
  if (h.lane === 'subs') msg('Нова репліка: Shift + перетягування в рядку субтитрів');
  else if (h.seek && !h.scrub) msg('Новий кліп: Shift + перетягування по таймлайну');
};
// ── плашка області над таймлайном (дії + перетягування) і редактор репліки над реплікою ──
const ovl = {}, ovlW = {};                                        // розміри плашок кешуються: читання з DOM щокадру гальмує
for (const id of ['ract', 'cueEdit']) new ResizeObserver(() => ovlW[id] = $('#' + id).offsetWidth).observe($('#' + id));
function place(id, props) {                                       // пишемо в DOM лише те, що змінилось
  const s = $('#' + id).style, last = ovl[id] ||= {};
  for (const [k, v] of Object.entries(props)) { const px_ = Math.round(v) + 'px'; if (last[k] !== px_) s[k] = last[k] = px_; }
}
function placeOverlays() {
  const on = !!(P && dur); if (ovl.on !== on) $('#rbar').classList.toggle('on', ovl.on = on); if (!on) return;
  const [ra, rb] = region(), xa = X(ra), l = clamp(xa, 0, TW), r = clamp(X(rb), 0, TW), c = P.cues[selCue];
  place('rband', {left: l, width: Math.max(0, r - l)}); place('ract', {left: clamp(xa, 0, Math.max(0, TW - (ovlW.ract || 0)))});
  if (c) place('cueEdit', {left: clamp(X(c.a), 0, Math.max(0, TW - (ovlW.cueEdit || 0))), top: geo().cueY + rowOf(c) * CUE - 46});
}
const barX = e => e.clientX - tl.getBoundingClientRect().left;
$('#rbar').onpointerdown = e => {
  if (!P || !dur || !e.target.closest('#rband,#ract') || e.target.closest('button,input,label,.pop')) return;
  $('#rbar').setPointerCapture(e.pointerId); P.region = region(); drag = {band: true, off: Tt(barX(e)) - P.region[0], r0: [...P.region]};
};
$('#rbar').onpointermove = e => {
  if (!drag || !drag.band) return; const [a, b] = drag.r0, len = b - a;
  const na = clamp(snapSpan(Tt(barX(e)) - drag.off, len), 0, dur - len); P.region = [na, na + len];
};
$('#rbar').onpointerup = () => { if (drag && drag.band) { drag = null; guide = null; save(); } };

const musAud = new Map();                                         // id шматка → <audio>
function syncSound() {
  if (!P) return;
  const vv = Math.min(1, els().find(e => e.type === 'video')?.vol ?? 1); vid.volume = vv; mix.volume = vv;   // звук відео; понад 100% — лише в рендері
  const stall = vid.seeking || vid.readyState < 3;                  // відео шукає кадр (стрибок через вирізане) — музика чекає, а не тікає вперед
  const t = vid.currentTime, play = !vid.paused && !stall, c = clipAt(t), rel = c ? toOut(c, t) : 0, n = c ? net(c) : 0, live = new Set();
  for (const e of c ? els().filter(e => e.type === 'music' && e.on && e.path) : []) {
    const sg = segsOf(c, e), pos = (e.off || 0) + rel;
    if (!play || !sg.some(([a, b]) => rel >= (a || 0) && rel < (b || n)) || pos < 0 || pos >= (e.dur || 1e9)) continue;
    let a = musAud.get(e.id); if (!a || a.dataset.path !== e.path) { a?.pause(); a = new Audio(fileUrl(e.path)); a.dataset.path = e.path; musAud.set(e.id, a); }
    live.add(e.id); if (a.paused || Math.abs(a.currentTime - pos) > .25) a.currentTime = pos;
    if (a.paused) a.play().catch(() => {});
    const s0 = Math.min(...sg.map(x => x[0] || 0)), s1 = Math.max(...sg.map(x => x[1] || n));
    a.volume = clamp((e.vol ?? 1) * (e.fin ? clamp((rel - s0) / e.fin, 0, 1) : 1) * (e.fout ? clamp((s1 - rel) / e.fout, 0, 1) : 1), 0, 1);
  }
  for (const [id, a] of musAud) { if (!live.has(id) && !a.paused) a.pause(); if (!elById(id)) musAud.delete(id); }
}
(function loop() {
  if ($('#editor').classList.contains('on')) {
    if (playSeq && !vid.paused && vid.currentTime >= playSeq.parts[playSeq.i][1] - .03) {   // кінець шматка — далі наступний
      if (++playSeq.i < playSeq.parts.length) vid.currentTime = playSeq.parts[playSeq.i][0]; else { vid.pause(); playSeq = null; }
    }
    if (stopAt != null && vid.currentTime >= stopAt) { vid.pause(); stopAt = null; }
    if (P && (P.clips.length ? ctxClip() : null) !== listClip) renderEls();   // інший кліп — свій список елементів
    if (P && !vid.paused) {                                        // програвання перестрибує пропуски, як у рендері
      const t = vid.currentTime, c = P.clips.find(c => c.on && t >= c.a && t < c.b), u = c && (c.cut || []).find(([x, y]) => t >= x && t < y);
      if (u) vid.currentTime = u[1];
      if (mixOn() && Math.abs(mix.currentTime - vid.currentTime) > .12) mix.currentTime = vid.currentTime;   // зведений звук не відстає
    }
    syncSound();
    mode === 'short' ? drawShort() : drawSrc(); drawTL(); showRegionLabel(); placeOverlays();
    $('#time').textContent = fmt(vid.currentTime) + ' / ' + fmt(dur);
  }
  requestAnimationFrame(loop);
})();
