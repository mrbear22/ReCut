// Вибране й буфер обміну: Del, Ctrl+C / Ctrl+V / Ctrl+D.
// ── що вибрано останнім (елемент, кліп чи репліка) — з тим і працюють Del / Ctrl+C / Ctrl+V / Ctrl+D ──
let focus = 'clip', clipboard = null;
const KEEPS_ELEMENT = '#layers,#propsBox,#pv,#ctx,#tour,#modal';   // кліки тут працюють з вибраним елементом; деінде — знімають вибір
document.addEventListener('pointerdown', e => {                   // capture: смужка на таймлайні вибере свій елемент уже після цього
  if (!selEl || e.target.closest(KEEPS_ELEMENT)) return;
  selEl = null; selOwn = null; renderEls();
}, true);
document.addEventListener('pointerdown', e => {                   // клік деінде закриває редактор репліки; клік по іншій репліці відкриє її
  if (selCue < 0 || e.target.closest('#cueEdit,#ctx')) return;
  selCue = -1; $('#cueEdit').classList.remove('on'); drawTL();
}, true);
for (const id of ['#layers', '#propsBox']) $(id).addEventListener('pointerdown', () => { focus = 'el'; selBar = null; onPv = false; }); pv.addEventListener('pointerdown', () => { focus = 'el'; selBar = null; onPv = true; });
$('#list').addEventListener('pointerdown', () => focus = 'clip');
let selBar = null, onPv = false;                                  // плитка елемента, вибрана на таймлайні: {c, k}; onPv — елемент вибрали на прев'ю
const elClip = () => selBar?.c || clipAt(vid.currentTime) || (P.clips.length ? ctxClip() : null);
const tileable = e => !!e && !['subs', 'bg'].includes(e.type);
function curTile() {                                              // з якою плиткою працюють Ctrl+C / Ctrl+D: вибрана на таймлайні, а на прев'ю — та, що зараз видно
  const e = focus === 'el' && elById(selEl); if (!tileable(e)) return null;
  if (selBar) return segsOf(selBar.c, e)[selBar.k] ? selBar : null;
  const c = onPv && clipAt(vid.currentTime); if (!c || !inClip(c, e)) return null;
  const rel = toOut(c, vid.currentTime), n = net(c), k = segsOf(c, e).findIndex(([a, b]) => rel >= (a || 0) && rel < (b || n));
  return k < 0 ? null : {c, k};
}
const tileLen = ({c, k}, e) => { const x = segsOf(c, e)[k]; return (x[1] || net(c)) - (x[0] || 0); };
function placeTile(c, e, s, len) {                                // нова плитка елемента в кліпі з моменту s: як усе покладене зверху, підрізає те, що під нею
  const n = net(c), b = Math.min(n, s + len); if (b - s < .2) return msg('Тут немає місця для плитки', 1);
  const rest = ([u, v]) => { u ||= 0; v ||= n; return [[u, Math.min(v, s)], [Math.max(u, b), v]].filter(([p, q]) => q - p >= .2); };
  const segs = c.segs[e.id] = [...ownSegs(c, e).flatMap(rest), [s, b]].sort((x, y) => x[0] - y[0]).map(([p, q]) => [p, q >= n - .05 ? 0 : q]);
  selEl = e.id; selOwn = ownOf(c, e); selBar = {c, k: segs.findIndex(([p]) => p === s)}; focus = 'el'; renderEls(); save();
}
function removeFromClip(el, c = elClip(), k = selBar?.c === c ? selBar.k : null) {   // Del: лише з цього кліпу; шматок — лише шматок
  if (!c || ['subs', 'bg'].includes(el.type) || !inClip(c, el) || !segsOf(c, el).length) return false;
  const sg = c.segs?.[el.id];
  if (sg && k != null && sg.length > 1) sg.splice(k, 1);
  else if (el.solo) delete c.segs[el.id];
  else (c.segs ||= {})[el.id] = [];
  selBar = null; renderEls(); save(); msg(`${TYPES[el.type].name}: ${el.solo ? 'прибрано з кліпу' : 'сховано в кліпі'} #${P.clips.indexOf(c) + 1}`); return true;
}
function deleteEl(el) { if (dropEl(el)) { selBar = null; renderEls(); fitTL(); save(); } }
function splitAt(t = vid.currentTime) {                            // B: розрізати вибране під курсором
  const el = focus === 'el' && elById(selEl), q = focus === 'cue' && P.cues[selCue];
  if (q) return t > q.a + .1 && t < q.b - .1 && wordsOf(q).length > 1 ? splitCue(q, t) : msg('Курсор не на репліці', 1);
  const c = clipAt(t) || P.clips.find(c => t >= c.a && t <= c.b);
  if (!c) return msg('Курсор не на кліпі', 1);
  if (el && !['subs', 'bg'].includes(el.type)) {
    const rel = toOut(c, t), n = net(c), k = segsOf(c, el).findIndex(([a, b]) => rel > (a || 0) + .1 && rel < (b || n) - .1);
    if (k < 0) return msg('Курсор не на цьому елементі', 1);
    const y = ownSegs(c, el)[k], end = y[1]; y[1] = rel; c.segs[el.id].push([rel, end]); tidySegs(c, el); return save();
  }
  if (locked(c)) return msg('Кліп заблоковано · L', 1);
  if (t > c.a + .5 && t < c.b - .5) splitClip(c, t);
}
function trimTo(edge, t = vid.currentTime) {                       // Q / W: початок / кінець вибраного — на курсор
  const el = focus === 'el' && elById(selEl), q = focus === 'cue' && P.cues[selCue], c = el ? elClip() : P.clips[sel];
  if (q) { if (edge === 'a') q.a = Math.min(t, q.b - .2); else q.b = Math.max(t, q.a + .2); return save(); }
  if (el && c) return (edge === 'a' ? showFrom : hideFrom)(el, c, toOut(c, clamp(t, c.a, c.b)));
  if (locked(c)) return msg('Кліп заблоковано · L', 1);
  if (c) { if (edge === 'a') c.a = Math.min(t, c.b - 1); else c.b = Math.max(t, c.a + 1); commit(); }
}
function showFrom(el, c, rel) {
  const n = net(c);
  if (c.segs?.[el.id]) { const L = c.segs[el.id].filter(([, b]) => (b || n) > rel + .2).map(([a, b]) => [Math.max(a || 0, rel), b]); c.segs[el.id] = L.length ? L : [[rel, 0]]; }
  else { el.from = rel; if (el.to && el.to <= rel + .2) el.to = 0; }
  save(); renderProps();
}
function hideFrom(el, c, rel) {
  const n = net(c);
  if (c.segs?.[el.id]) c.segs[el.id] = c.segs[el.id].filter(([a]) => (a || 0) < rel - .2).map(([a, b]) => [a, (b || n) > rel ? rel : b]);
  else el.to = rel >= n - .05 ? 0 : rel;
  save(); renderProps();
}
const setRegionEdge = (edge, t = vid.currentTime) => { const [a, b] = region(), g = Math.min(10, dur); setRegion(edge === 'a' ? [Math.min(t, b - g), b] : [a, Math.max(t, a + g)]); };
function removeSel() {
  if (multi.size) return deleteMulti();
  if (focus === 'cue' && selCue >= 0) return $('#cueDel').click();
  if (focus === 'el' && selEl) { const el = elById(selEl); if (!removeFromClip(el)) deleteEl(el); return; }
  if (locked(P.clips[sel])) return msg('Кліп заблоковано · L', 1);
  if (P.clips[sel]) { P.clips.splice(sel, 1); sel = -1; commit(); }
}
function copySel() {
  const [kind, v] = focus === 'cue' && P.cues[selCue] ? ['cue', P.cues[selCue]] : focus === 'el' && elById(selEl) ? ['el', elById(selEl)] : ['clip', P.clips[sel]];
  if (!v) return; const tile = kind === 'el' && curTile();
  clipboard = {kind, v: structuredClone(v), segs: kind === 'el' && P.clips.length ? structuredClone(segsOf(ctxClip(), v)) : null, tile: tile && tileLen(tile, v)};
  msg(`Скопійовано: ${tile ? 'плитку' : kind === 'el' ? TYPES[v.type].name.toLowerCase() : kind === 'cue' ? 'репліку' : 'кліп'}`);
}
const shiftCuts = (cut, d) => (cut || []).map(([x, y]) => [x + d, y + d]);
function duplicate() {                                            // плитка — ще одна плитка поруч; елемент зі списку — новий елемент
  if (focus === 'cue' && P.cues[selCue]) return dupCue(P.cues[selCue]);
  const t = curTile(); if (!t) { copySel(); return paste(); }
  const e = elById(selEl), x = segsOf(t.c, e)[t.k], n = net(t.c), end = x[1] || n;
  if (end > n - .2) return msg('Після плитки кліп закінчується', 1);
  placeTile(t.c, e, end, tileLen(t, e));
}
function paste(t = vid.currentTime) {                             // плитка — на курсор у тій самій доріжці; елемент — трохи зсунутим; кліп і репліку — на курсор
  if (!clipboard) return; const {kind, v} = clipboard, sh = t - (v.a ?? 0);
  if (kind === 'el' && clipboard.tile && elById(v.id)) {
    const c = clipAt(t); if (!c) return msg('Курсор не на кліпі', 1);
    return placeTile(c, elById(v.id), toOut(c, t), clipboard.tile);
  }
  if (kind === 'el') {
    if (SINGLE.includes(v.type) && els().some(e => e.type === v.type)) return msg(`${TYPES[v.type].name} може бути лише один`, 1);
    const el = {...structuredClone(v), id: uid(), x: (v.x ?? 0) + 40, y: v.y + 40}, c = P.clips.length ? ctxClip() : null;
    if (el.solo) { if (c) (c.segs ||= {})[el.id] = clipboard.segs?.length ? structuredClone(clipboard.segs) : [[0, 0]]; else el.solo = false; }
    P.elements.push(el); selEl = el.id; focus = 'el'; renderEls(); return save();
  }
  if (kind === 'clip') {
    P.clips.push({...structuredClone(v), a: t, b: Math.min(dur, t + v.b - v.a), cut: shiftCuts(v.cut, sh), ...(v.loop != null ? {loop: v.loop + sh} : {}), ...(v.hook ? {hook: v.hook.map(x => x + sh)} : {})}); sel = P.clips.length - 1; focus = 'clip'; return commit();
  }
  const q = {...structuredClone(v), a: t, b: t + v.b - v.a, k: (v.k || []).map(x => x + sh)};
  if (!subsEls().some(e => e.id === q.sid)) q.sid = (subsEls()[0] || ensureSubs()).id;   // з проєкту, де інші доріжки
  P.cues.push(q); P.cues.sort((x, y) => x.a - y.a); selectCue(P.cues.indexOf(q)); save();
}
