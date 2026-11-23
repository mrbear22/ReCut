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
for (const id of ['#layers', '#propsBox']) $(id).addEventListener('pointerdown', () => { focus = 'el'; selBar = null; }); pv.addEventListener('pointerdown', () => { focus = 'el'; selBar = null; });
$('#list').addEventListener('pointerdown', () => focus = 'clip');
let selBar = null;                                                // шматок елемента, вибраний на таймлайні: {c, k}
const elClip = () => selBar?.c || clipAt(vid.currentTime) || (P.clips.length ? ctxClip() : null);
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
  if (!v) return; clipboard = {kind, v: structuredClone(v), segs: kind === 'el' && P.clips.length ? structuredClone(segsOf(ctxClip(), v)) : null};
  msg(`Скопійовано: ${kind === 'el' ? TYPES[v.type].name.toLowerCase() : kind === 'cue' ? 'репліку' : 'кліп'}`);
}
const shiftCuts = (cut, d) => (cut || []).map(([x, y]) => [x + d, y + d]);
const duplicate = () => focus === 'cue' && P.cues[selCue] ? dupCue(P.cues[selCue]) : focus === 'el' && selBar?.c && canOwn(elById(selEl)) ? dupBar() : (copySel(), paste());
function dupBar() {                                               // Ctrl+D по смужці: копія — окремий елемент лише в цьому кліпі, одразу після неї
  const {c, k} = selBar, e = elById(selEl), x = segsOf(c, e)[k]; if (!x) return;
  const n = net(c), end = x[1] || n, len = end - (x[0] || 0), s = Math.min(end, Math.max(0, n - len));
  const el = {...structuredClone(effEl(e, c)), id: uid(), solo: true}; delete el._own;
  (c.segs ||= {})[el.id] = [[s, s + len < n - .05 ? s + len : 0]];
  P.elements.splice(P.elements.indexOf(e) + 1, 0, el); selEl = el.id; selOwn = null; selBar = {c, k: 0}; renderEls(); save();
}
function paste(t = vid.currentTime) {                             // елемент — трохи зсунутим; кліп і репліку — на курсор
  if (!clipboard) return; const {kind, v} = clipboard, sh = t - (v.a ?? 0);
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
