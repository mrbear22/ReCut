// Монтаж: розкладка, вписування прев'ю, відео й аналіз, редактор реплік, список кліпів, плеєр.
// ── розкладка ──
const centerSrc = a => { const w = Math.min(1, a * S.h / S.w); return [(1 - w) / 2, 0, w, 1]; };
const layerH = l => l.w * (l.src[3] * S.h) / (l.src[2] * S.w);
function arrange() {
  const W = CW(), H = CH(), v = els().find(e => e.type === 'video'), cam = els().find(e => e.type === 'cam' && e.w >= W), card = els().find(e => e.type === 'card' || e.type === 'stream');
  const cr = card ? rectOf(card) : {w: 0, h: 0};
  if (card) card.x = (W - cr.w) / 2;
  if (W >= H) {                                                   // квадрат чи широке полотно: відео на все полотно, плашка згори
    if (v) Object.assign(v, {src: centerSrc(W / H), x: 0, y: 0, w: W});
    if (card) card.y = 40;
  } else if (cam) {
    Object.assign(cam, {x: 0, y: 0}); const camH = layerH(cam), src = centerSrc(W / (H - camH)), [cx, , cw] = cam.src, w = src[2];
    if (cx + cw / 2 > .5 && cx - w >= 0) src[0] = Math.min(src[0], cx - w); else if (cx + cw / 2 <= .5 && cx + cw + w <= 1) src[0] = Math.max(src[0], cx + cw);
    if (v) Object.assign(v, {src, x: 0, y: camH, w: W});            // основу — подалі від камери, якщо влазить
    if (card) card.y = Math.max(20, camH - cr.h / 2);
  } else {
    if (v) Object.assign(v, {src: centerSrc(0.8), x: 0, y: 170 + cr.h - 60, w: W});
    if (card) card.y = 170;
  }
}
$('#arrange').onclick = () => { if (P) { arrange(); save(); } };
function setMode(m) {
  mode = m; pv.className = m; pvZoom = 1; pvPan = {x: 0, y: 0};   // інший кадр — знову вписаний
  $$('[data-mode]').forEach(b => b.classList.toggle('on', b.dataset.mode === m));
  if (m === 'src' && !cropEl() && srcEls()[0]) { selEl = srcEls()[0].id; renderEls(); }
  renderCanvasBar(); fitCanvas();
}
function remap(o, [ow, oh], [nw, nh]) {                            // елемент чи його екземпляр — на полотно іншого розміру: те саме місце відносно країв
  if (o.type === 'bg' || o.type === 'music' || (ow === nw && oh === nh)) return;
  if (o.type === 'progress') { o.y = o.pos === 'top' ? 0 : nh - o.h; return; }
  const r = rectOf(o), layer = ['video', 'cam', 'subs'].includes(o.type), full = layer && r.w >= ow - 1;
  if (full) { o.x = 0; o.w = nw; }
  else {
    if (layer && o.w > nw) o.w = nw;
    const w = layer ? o.w : r.w; if (o.x != null) o.x = Math.round(clamp((r.x + r.w / 2) * nw / ow - w / 2, 0, Math.max(0, nw - w)));
  }
  const h = o.type === 'video' || o.type === 'cam' ? layerH(o) : r.h;
  if (o.type === 'video' && full && h > nh) { o.src = centerSrc(nw / nh); o.y = 0; return; }   // основне відео не вилазить за полотно
  o.y = Math.round(clamp((r.y + r.h / 2) * nh / oh - h / 2, 0, Math.max(0, nh - h)));
}
function setCanvas(r) {
  const to = canvasOf(r), from = [CW(), CH()]; if (to[0] === from[0] && to[1] === from[1]) return;
  for (const o of [...P.elements, ...P.clips.flatMap(c => Object.values(c.own || {})), ...P.cues.flatMap(q => q.own ? [q.own] : [])]) remap(o, from, to);
  P.canvas = to; pvZoom = 1; pvPan = {x: 0, y: 0}; renderCanvasBar(); fitCanvas(); renderEls(); save();
}
const CANVAS_RATIOS = () => RATIOS.filter(([r]) => r).sort((a, b) => a[0] - b[0]);   // ті самі пропорції, що в кадруванні: 9:16, 1:1, 4:3, 16:9
function renderCanvasBar() {
  const bar = $('#canvasRatio'), cur = CW() / CH(); bar.style.visibility = mode === 'short' ? '' : 'hidden';   // місце лишається — вкладки не скачуть
  bar.innerHTML = CANVAS_RATIOS().map(([r, l]) => `<button data-canvas="${r}" class="${Math.abs(r - cur) < .01 ? 'on' : ''}" ${P ? '' : 'disabled'}>${l}</button>`).join('');
}
$('#canvasRatio').onclick = e => { const b = e.target.closest('[data-canvas]'); if (b && P) setCanvas(+b.dataset.canvas); };
$$('[data-mode]').forEach(b => b.onclick = () => setMode(b.dataset.mode));
// полотно завжди має пропорції того, що показує (шорт 9:16 або кадр джерела), і чітке на будь-якому екрані
// ── прев'ю: вписане у вікно; колесо — зум до курсора, затиснуте колесо — рух, бейдж у куті — назад до вписаного ──
let pvZoom = 1, pvPan = {x: 0, y: 0};                             // зсув центру кадру від центру вікна, екранні px
const PV_ZOOM_MAX = 8, PV_BACKING_MAX = 4320;                      // найбільший зум; ширина полотна в пікселях (далі — розтягнення)
function fitCanvas() {
  const box = $('.cv'), a = mode === 'short' ? CW() / CH() : S.w / S.h, d = devicePixelRatio || 1, bw = box.clientWidth, bh = box.clientHeight;
  const w0 = Math.floor(Math.min(bw, bh * a)), h0 = Math.floor(w0 / a);
  if (w0 < 10 || h0 < 10) return;
  const w = Math.round(w0 * pvZoom), h = Math.round(h0 * pvZoom), mx = Math.max(0, (w - bw) / 2), my = Math.max(0, (h - bh) / 2);
  pvPan.x = clamp(pvPan.x, -mx, mx); pvPan.y = clamp(pvPan.y, -my, my);   // кадр не тікає з вікна
  pv.style.width = w + 'px'; pv.style.height = h + 'px'; pv.style.left = (bw - w) / 2 + pvPan.x + 'px'; pv.style.top = (bh - h) / 2 + pvPan.y + 'px';
  Object.assign($('#pvMarks').style, {left: (bw - w) / 2 + pvPan.x - 9 + 'px', top: (bh - h) / 2 + pvPan.y - 9 + 'px', width: w + 18 + 'px', height: h + 18 + 'px'});   // мітки обрізу навколо кадру
  const k = Math.min(d, PV_BACKING_MAX / w); pv.width = Math.round(w * k); pv.height = Math.round(h * k);   // чітко, а не розтягнута картинка
  $('#pvZoom').hidden = pvZoom === 1; $('#pvZoom').textContent = `${Math.round(pvZoom * 100)}%`;
}
$('.cv').addEventListener('wheel', e => {                         // зум до точки під курсором
  if (!P) return; e.preventDefault();
  const r = $('.cv').getBoundingClientRect(), cx = e.clientX - r.left - r.width / 2, cy = e.clientY - r.top - r.height / 2;
  const z = clamp(pvZoom * Math.exp(-e.deltaY * .0015), 1, PV_ZOOM_MAX), f = z / pvZoom;
  pvPan = {x: cx - (cx - pvPan.x) * f, y: cy - (cy - pvPan.y) * f}; pvZoom = z; fitCanvas();
}, {passive: false});
let pvPanDrag = null;
$('.cv').addEventListener('pointerdown', e => {                   // затиснуте колесо — рухати збільшений кадр
  if (e.button !== 1) return; e.preventDefault(); try { $('.cv').setPointerCapture(e.pointerId); } catch (err) {}
  pvPanDrag = {x: e.clientX - pvPan.x, y: e.clientY - pvPan.y}; $('.cv').style.cursor = 'grabbing';
});
$('.cv').addEventListener('pointermove', e => { if (pvPanDrag) { pvPan = {x: e.clientX - pvPanDrag.x, y: e.clientY - pvPanDrag.y}; fitCanvas(); } });
$('.cv').addEventListener('pointerup', () => { pvPanDrag = null; $('.cv').style.cursor = ''; });
$('.cv').addEventListener('auxclick', e => e.button === 1 && e.preventDefault());   // без автопрокрутки браузера
$('#pvZoom').onclick = () => { pvZoom = 1; pvPan = {x: 0, y: 0}; fitCanvas(); };
new ResizeObserver(fitCanvas).observe($('.cv'));
const pvScale = () => pv.width / (pv.clientWidth || 1);          // пікселів полотна на екранний піксель
const shortUnits = n => n * CW() / (pv.clientWidth || 1);         // екранні пікселі → одиниці полотна
const SNAP_PX = 10, HANDLE_PX = 7;                                // поріг магнетизму й піврозмір ручки, екранні пікселі

// ── відео, аналіз, субтитри — усе в межах області ──
async function loadVideo() {
  videoMissing = false; videoChip();
  mix.pause(); mix.removeAttribute('src'); vid.muted = false;
  hlsStop(); vid.removeAttribute('src'); if (!P.video) return;
  const pr = await api('/api/probe?p=' + encodeURIComponent(P.video)).catch(e => { if (!/^https?:/.test(P.video)) { videoMissing = true; videoChip(); } else msg(e.message, 1); return null; }); if (!pr) return;
  dur = pr.dur; S = {w: pr.sw, h: pr.sh}; view = {t0: 0, t1: dur}; fitCanvas();
  if (pr.hls) { playHls(pr.play); if (pr.title) videoChip(pr.title); } else showPlayable(P.video, pr.play);
  audioTracks = pr.tracks || 1;
  if (pr.tracks > 1) waitMix(P.video, pr.mix);
  if (!P.elements.length || (oldStarter(P.elements) && !P.clips.length)) await defaultElements();   // стара заготовка з плашкою відео — на нову
  if (P.scan) showScan(P.scan);                                    // крива з минулого аналізу; новий — лише кнопкою
  busyButtons();
}
function showScan(sc) {                                           // крива активності на таймлайні й видимий відрізок — область аналізу
  curve = sc.curve; t0 = sc.region[0]; step = sc.step; lo = Math.min(...curve); hi = Math.max(...curve) || 1;
  view = {t0: sc.region[0], t1: sc.region[1]}; clampView(); drawTL();
}
vid.onerror = () => P && P.video && msg('Цей формат не відтворюється в перегляді, але рендер працюватиме', 1);
// аналіз і субтитри прив'язані до свого проєкту: можна запустити в кількох проєктах і перемикатись між ними
const running = {analyze: new Set(), subs: new Set()};               // id проєктів, де операція зараз іде
function busyButtons() { if (P) { $('#reanalyze').disabled = running.analyze.has(P.id); $('#mkSubs').disabled = running.subs.has(P.id); } }
async function forProject(proj, kind, work, apply) {
  running[kind].add(proj.id); busyButtons();
  try {
    const r = await work();
    const open = P && P.id === proj.id, target = open ? P : proj;      // проєкт могли закрити й відкрити знову — пишемо в актуальний
    const keys = apply(target, r, open);
    if (open) save(); else api('/api/project/save', {id: target.id, ...Object.fromEntries(keys.map(k => [k, target[k]]))});
  } finally { running[kind].delete(proj.id); busyButtons(); }
}
const tag = (label, proj) => P && P.id !== proj.id || Object.keys(running).some(k => [...running[k]].some(id => id !== proj.id)) ? `${label} · ${projName(proj)}` : label;
function momentsNote(found, [ra, rb]) {                          // чому знайшлося менше, ніж просили: область не вміщує стільки кліпів
  const len = rb - ra, want = cfg.n_clips, fit = Math.floor(len / cfg.min_len), area = len < 120 ? `${Math.round(len)} с` : fmtDur(len);
  if (!found && len < cfg.min_len) return [`Моментів не знайдено: область ${area} коротша за кліп (від ${cfg.min_len} с). Збільш область або зменш довжину кліпів.`, true];
  if (!found) return ['Моментів не знайдено. Спробуй більшу область або коротші кліпи.', true];
  if (found < want && fit < want) return [`Знайдено ${found} з ${want}: в область ${area} вміщується не більше ${fit} кліпів по ${cfg.min_len} с.`, true];
  return [`Знайдено моментів: ${found}`, false];
}
async function analyze(suggest) {
  if (!P || !P.video) return msg('Спершу обери відео', 1);
  const proj = P, body = {video: P.video, region: region(), suggest, lang: cfg.stt_lang || ''}; msg('');
  const ai = cfg.stt && suggest && (await api('/api/ai').catch(() => ({}))).model;   // є локальний ШІ — буде ще етап пошуку моментів за змістом
  try {
    await forProject(proj, 'analyze', () => busy($('#reanalyze'), tag('Аналіз', proj), plans.analyze(suggest, ai), task => api('/api/analyze', {...body, task}), null, true), (pr, r, open) => {
      pr.region = r.region; pr.scan = {region: r.region, step: r.step, curve: r.curve}; cfg.speed = r.speed;
      if (suggest && r.clips.length) {
        const [ra, rb] = r.region;                                   // нові моменти замінюють лише ті, що в області; нічого не знайшли — старі лишаються
        pr.clips = [...pr.clips.filter(c => c.b <= ra || c.a >= rb), ...r.clips.map(c => ({...c, on: true}))].sort((x, y) => x.a - y.a);
      }
      const [note, bad] = suggest ? momentsNote(r.clips.length, r.region) : ['', false];
      if (open) { showScan(pr.scan); sel = -1; renderList(); msg(note, bad); } else if (note) msg(`${projName(pr)}: ${note}`, bad);
      return ['region', 'scan', 'clips'];
    });
  } catch (e) { e.cancelled ? msg('Аналіз скасовано') : msg(`Помилка аналізу (${projName(proj)}): ` + e.message, 1); }
}
$('#reanalyze').onclick = () => analyze(true);
async function makeSubs() {
  if (!P || !P.video) return msg('Спершу обери відео', 1);
  ensureSubs(); save();
  const proj = P, spans = [region()];                                  // лише виділена область — те, що користувач обрав
  const inSpans = c => spans.some(([a, b]) => c.a < b && c.b > a), body = {video: P.video, region: region(), spans, words: cfg.sub_words || 3, lang: cfg.stt_lang || ''};
  try {
    await forProject(proj, 'subs', () => busy($('#mkSubs'), tag('Субтитри', proj), plans.subs(), task => api('/api/subs', {...body, task}), null, true), (pr, r, open) => {
      cfg.speed = r.speed;
      if (r.tracks > 1) {                                             // доріжка = спікер = свій елемент «Субтитри»; бракує — додаємо
        const first = subsEls(pr.elements)[0]; if (first && !first.name) first.name = tr('Доріжка 1');
        while (subsEls(pr.elements).length < r.tracks) addSubsEl(pr.elements, tr(`Доріжка ${subsEls(pr.elements).length + 1}`));
      }
      const own = subsEls(pr.elements); r.cues.forEach(c => { if (own[c.sp]) c.sid = own[c.sp].id; delete c.sp; });
      pr.cues = [...pr.cues.filter(c => !inSpans(c)), ...r.cues].sort((x, y) => x.a - y.a);
      const note = r.cues.length ? `${r.cues.length} реплік` : 'мови не чути ні в області, ні в кліпах';
      if (open) { renderEls(); selCue = -1; msg(`Субтитри: ${note}`, !r.cues.length); } else msg(`${projName(pr)}: субтитри — ${note}`, !r.cues.length);
      return ['cues', 'elements'];
    });
  } catch (e) { e.cancelled ? msg('Субтитри скасовано') : msg(`Субтитри (${projName(proj)}): ` + e.message, 1); }
}
$('#mkSubs').onclick = makeSubs;
$('#toRegion').onclick = () => { if (P && dur) { const [a, b] = region(), pad = (b - a) * .03; view = {t0: a - pad, t1: b + pad}; clampView(); } };
function selectCue(j, jump = true) {
  multi.clear(); selCue = j; if (j >= 0) focus = 'cue'; if (j >= 0) sel = -1; renderList(); const c = P.cues[j];
  $('#cueEdit').classList.toggle('on', !!c); if (c) { paintCue(c); if (jump) seek(c.a); }
}
function addCue(t, row = 0) {
  const sid = (subsEls()[row] || ensureSubs()).id, nx = P.cues.find(c => rowOf(c) === row && c.a > t), c = {a: t, b: Math.min(t + 1.5, nx ? nx.a : dur), text: 'Текст', sid};   // перша репліка — сама додає елемент «Субтитри»
  P.cues.push(c); P.cues.sort((x, y) => x.a - y.a); selectCue(P.cues.indexOf(c)); editCueText(); save();
}
// ── редактор репліки: текст з пословним форматуванням (q.fmt — по одному запису на слово) і швидкі дії ──
const cueEd = $('#cueText'), toks = s => s.match(/\s+|\S+/g) || [];
const fmtCss = f => !f ? '' : [f.b === false && 'font-weight:400', f.i && 'font-style:italic', f.u && 'text-decoration:underline', f.c && `color:${f.c}`,
  f.s && f.s !== 1 && `font-size:${f.s}em`].filter(Boolean).join(';');
const fmtOf = q => { const n = wordsOf(q).length; return q.fmt?.length === n ? q.fmt : Array(n).fill(null); };
function caretOf() {                                              // виділення в тексті репліки: [з, до] у символах; null — курсора там немає
  const s = getSelection(); if (!s.rangeCount || !cueEd.contains(s.anchorNode)) return null;
  const r = s.getRangeAt(0), pre = document.createRange(); pre.selectNodeContents(cueEd);
  pre.setEnd(r.startContainer, r.startOffset); const a = pre.toString().length; pre.setEnd(r.endContainer, r.endOffset); return [a, pre.toString().length];
}
function setCaret([a, b]) {
  const at = n => { const w = document.createTreeWalker(cueEd, NodeFilter.SHOW_TEXT); let x; while ((x = w.nextNode())) { if (n <= x.length) return [x, n]; n -= x.length; } return [cueEd, cueEd.childNodes.length]; };
  const r = document.createRange(); r.setStart(...at(a)); r.setEnd(...at(b)); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
}
function paintCue(q, keep) {                                      // текст з форматуванням; keep — куди повернути курсор
  const f = fmtOf(q); let w = 0;
  cueEd.innerHTML = toks(q.text).map(t => { if (/^\s/.test(t)) return esc(t); const st = fmtCss(f[w++]); return st ? `<span style="${st}">${esc(t)}</span>` : esc(t); }).join('');
  if (keep) setCaret(keep); paintCueBar();
}
function selWords(q, cur = caretOf()) {                           // слова під виділенням; без виділення — уся репліка
  const n = wordsOf(q).length; if (!cur || cur[0] === cur[1]) return [...Array(n).keys()];
  const out = []; let pos = 0, w = 0;
  for (const t of toks(q.text)) { const e = pos + t.length; if (!/^\s/.test(t)) { if (e > cur[0] && pos < cur[1]) out.push(w); w++; } pos = e; }
  return out;
}
function wordsBefore(q, at) {                                     // скільки слів повністю до позиції в тексті
  let n = 0, pos = 0;
  for (const t of toks(q.text)) { if (!/^\s/.test(t) && pos + t.length <= at) n++; pos += t.length; }
  return n;
}
function paintCueBar() {
  const q = P?.cues[selCue]; if (!q) return; const f = fmtOf(q), idx = selWords(q), all = fn => idx.length > 0 && idx.every(i => fn(f[i] || {}));
  $$('#cueBar [data-f=b],#cueBar [data-f=i],#cueBar [data-f=u]').forEach(b => b.classList.toggle('on', all(x => b.dataset.f === 'b' ? x.b !== false : !!x[b.dataset.f])));
  $('#cueBar [data-q=global]').classList.toggle('on', !q.own);
}
function cueFormat(kind, v) {
  const q = P.cues[selCue]; if (!q || !wordsOf(q).length) return;
  const cur = caretOf(), idx = selWords(q, cur), f = fmtOf(q).slice(), get = i => f[i] || {};
  const set = (i, k, x) => { const o = {...get(i)}; if (x === undefined) delete o[k]; else o[k] = x; f[i] = Object.keys(o).length ? o : null; };
  if (kind === 'b') { const on = idx.every(i => get(i).b !== false); idx.forEach(i => set(i, 'b', on ? false : undefined)); }   // субтитри типово жирні
  else if (kind === 'i' || kind === 'u') { const on = idx.every(i => get(i)[kind]); idx.forEach(i => set(i, kind, on ? undefined : 1)); }
  else if (kind === 'c') idx.forEach(i => set(i, 'c', v || undefined));
  else if (kind === 's') idx.forEach(i => { const z = clamp(Math.round(((get(i).s || 1) + v) * 100) / 100, .5, 2.5); set(i, 's', z === 1 ? undefined : z); });
  if (f.some(Boolean)) q.fmt = f; else delete q.fmt;
  paintCue(q, cur); save();
}
function alignFmt(ow, nw, of) {                                   // текст змінився: форматування лишається на тих самих словах
  let p = 0, s = 0; while (p < ow.length && p < nw.length && ow[p] === nw[p]) p++;
  while (s < ow.length - p && s < nw.length - p && ow[ow.length - 1 - s] === nw[nw.length - 1 - s]) s++;
  const mid = ow.length - p - s, out = of.slice(0, p);
  for (let j = 0; j < nw.length - p - s; j++) out.push(mid ? structuredClone(of[p + Math.min(j, mid - 1)]) : null);
  out.push(...of.slice(ow.length - s)); return out;
}
function editCueText() { cueEd.focus(); const r = document.createRange(); r.selectNodeContents(cueEd); getSelection().removeAllRanges(); getSelection().addRange(r); paintCueBar(); }
cueEd.addEventListener('input', e => {
  const q = P.cues[selCue]; if (!q) return;
  const text = cueEd.textContent.replace(/\n/g, ' '), of = q.fmt?.length === wordsOf(q).length ? q.fmt : null;
  if (of) { const f = alignFmt(wordsOf(q), text.split(/\s+/).filter(Boolean), of); if (f.some(Boolean)) q.fmt = f; else delete q.fmt; }
  q.text = text; if (!e.isComposing) paintCue(q, caretOf()); save();
});
cueEd.addEventListener('compositionend', () => { const q = P.cues[selCue]; if (q) paintCue(q, caretOf()); });
cueEd.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === 'Escape') { e.preventDefault(); cueEd.blur(); return; }
  const k = (e.ctrlKey || e.metaKey) && !e.altKey && {KeyB: 'b', KeyI: 'i', KeyU: 'u'}[e.code];
  if (k) { e.preventDefault(); cueFormat(k); }
});
document.addEventListener('selectionchange', () => { if (document.activeElement === cueEd) paintCueBar(); });
$('#cueCols').innerHTML = [null, '#ffffff', '#ffcc33', '#ff3b30', '#4fa3ff', '#5fe08a'].map(c => c
  ? `<button class="csw" data-f="c" data-v="${c}" style="background:${c}" title="Колір" aria-label="${c}"></button>`
  : '<button class="csw none" data-f="c" data-v="" title="Колір стилю" aria-label="Колір стилю"></button>').join('');
$('#cueBar').onmousedown = e => { if (e.target.closest('button')) e.preventDefault(); };   // виділення в тексті не злітає
$('#cueBar').onclick = e => {
  const b = e.target.closest('button'), q = P.cues[selCue]; if (!b || !q || b.id === 'cueDel') return;
  if (b.dataset.f) return cueFormat(b.dataset.f, b.dataset.f === 's' ? +b.dataset.v : b.dataset.v);
  const a = b.dataset.q;
  if (a === 'global') setCueGlobal(q, !!q.own);
  if (a === 'upper') { const up = q.text !== q.text.toUpperCase(); q.text = up ? q.text.toUpperCase() : q.text.toLowerCase(); paintCue(q, caretOf()); save(); }
  if (a === 'split') {                                            // слова до курсора — ліворуч, решта — праворуч
    const w = wordsOf(q), cur = caretOf(); if (w.length < 2) return;
    splitCue(q, null, cur ? clamp(wordsBefore(q, cur[0]), 1, w.length - 1) : Math.ceil(w.length / 2));
  }
  if (a === 'merge') { const nx = P.cues.slice(selCue + 1).find(x => rowOf(x) === rowOf(q)); if (nx) mergeCues(q, nx); }
};
// ── репліка зі своїм стилем і місцем (не глобальна): q.own; у списку зліва — рядок під своєю доріжкою ──
const SUB_STYLE = ['font', 'size', 'color', 'hl', 'karaoke', 'upper', 'outline', 'anim', 'x', 'y', 'w'];
function cueStyle(q) {                                            // чим малювати репліку: її стиль або доріжки
  const el = cueOwner(q); if (!q.own || !el) return el;
  return Object.assign(q.own, {type: 'subs', id: el.id, on: el.on});
}
function setCueGlobal(q, on) {
  if (on === !q.own) return;
  if (on) { if (selOwn === q.own) selOwn = null; delete q.own; }
  else { const el = cueOwner(q) || ensureSubs(); q.own = {type: 'subs', _own: uid()}; for (const k of SUB_STYLE) q.own[k] = structuredClone(el[k]); selEl = el.id; selOwn = q.own; }
  paintCueBar(); renderEls(); save();
}
$('#cueDel').onclick = () => { if (selCue < 0) return; P.cues.splice(selCue, 1); selectCue(-1); save(); };

// ── список кліпів ──
const inkOn = hex => { const n = parseInt(hex.slice(1), 16); return .2126 * (n >> 16) + .7152 * (n >> 8 & 255) + .0722 * (n & 255) > 140 ? '#17140f' : '#fff'; };   // цифра, що читається на кольорі кліпу
const info = c => clipLen(c).toFixed(1) + ' с';
function renderList() {
  if (!P) return;
  $('#list').innerHTML = P.clips.map((c, i) => `<div class="clip ${i === sel || multi.has(c) ? 'sel' : ''} ${c.on ? '' : 'off'}" data-i="${i}" title="${esc([c.why, c.score != null ? `оцінка ${c.score.toFixed(1)}` : ''].filter(Boolean).join(' · '))}"${c.col ? ` style="--cc:${c.col};--ci:${inkOn(c.col)}"` : ''}>
    <input type="checkbox" data-f="on" ${c.on ? 'checked' : ''} aria-label="Рендерити" title="Рендерити"><b class="no">${i + 1}</b>
    <span class="tm"><input class="t" data-f="a" value="${fmt(c.a)}" aria-label="Початок"><span>–</span><input class="t" data-f="b" value="${fmt(c.b)}" aria-label="Кінець"></span>
    <span class="d">${info(c)}</span>
    <span class="ac"><button data-act="play" title="Програти" aria-label="Програти">▶</button><button data-act="del" title="Видалити" aria-label="Видалити">✕</button></span>
    ${c.why ? `<small class="why">${esc(c.why)}</small>` : ''}</div>`).join('')
    || '<p class="mut">Кліпів ще немає</p>';
  $('#count').textContent = P.clips.length ? `· ${P.clips.filter(c => c.on).length}/${P.clips.length}` : '';
}
function updateRow(i) {
  const r = document.querySelector(`.clip[data-i="${i}"]`), c = P.clips[i]; if (!r) return;
  r.querySelector('[data-f=a]').value = fmt(c.a); r.querySelector('[data-f=b]').value = fmt(c.b); r.querySelector('.d').textContent = info(c);
}
function commit() { const cur = P.clips[sel]; P.clips.sort((x, y) => x.a - y.a); sel = P.clips.indexOf(cur); renderList(); renderProps(); save(); }
function select(i, focus) {
  multi.clear(); sel = i; selCue = -1; $('#cueEdit').classList.remove('on'); renderList(); renderProps();
  if (focus && P.clips[i]) { const c = P.clips[i], pad = Math.max(5, (c.b - c.a) * .3); view = {t0: Math.max(0, c.a - pad), t1: Math.min(dur, c.b + pad)}; seek(c.a); }
}
let playSeq = null;                                               // програвання шорту шматками: хук, з петлі до кінця, з початку до петлі
const clipParts = c => [...(hookOk(c) ? [[...c.hook]] : []), ...(c.loop != null && loopOk(c, c.loop) ? [[c.loop, c.b], [c.a, c.loop]] : [[c.a, c.b]])];
function playClip(i) {
  const c = P.clips[i], parts = clipParts(c); select(i, true);
  seek(parts[0][0]); if (parts.length > 1) playSeq = {parts, i: 0}; else stopAt = parts[0][1];
  vid.play();
}
$('#list').onclick = e => {
  const r = e.target.closest('.clip'); if (!r) return;
  const i = +r.dataset.i, act = e.target.dataset.act;
  if (act === 'play') return playClip(i);
  if (act === 'del') { P.clips.splice(i, 1); sel = -1; return commit(); }
  if (e.target.tagName !== 'INPUT') select(i, true);
};
$('#list').onchange = e => {
  const r = e.target.closest('.clip'), i = +r.dataset.i, f = e.target.dataset.f, c = P.clips[i];
  if (f === 'on') c.on = e.target.checked;
  else { const v = parse(e.target.value); if (!isNaN(v)) c[f] = clamp(v, 0, dur); if (c.b - c.a < 1) f === 'a' ? c.a = c.b - 1 : c.b = c.a + 1; }
  sel = i; commit();
};
const addAt = t => { P.clips.push({a: t, b: Math.min(dur, t + (cfg.min_len + cfg.max_len) / 2), on: true, score: null}); sel = P.clips.length - 1; commit(); };

// ── плеєр; кілька звукових доріжок звучать зведеним звуком, синхронним з відео ──
const mix = new Audio();
async function whenReady(video, key, path, note) {               // сервер готує файл для прев'ю у фоні; null — відео вже інше
  while (!path && P && P.video === video) {
    msg(note); await new Promise(r => setTimeout(r, 3000));
    path = (await api('/api/probe?p=' + encodeURIComponent(video)).catch(() => ({})))[key];
  }
  return P && P.video === video ? path : null;
}
async function showPlayable(video, path) {
  path = await whenReady(video, 'play', path, 'Готую відео для перегляду…');
  if (!path) return; vid.src = fileUrl(path); if (path !== video) msg('Прев\'ю готове.');
}
async function waitMix(video, path) {
  path = await whenReady(video, 'mix', path, 'Звожу всі звукові доріжки для прев\'ю… поки звучить лише перша.'); if (!path) return;
  mix.src = fileUrl(path); mix.currentTime = vid.currentTime; vid.muted = true; msg('Звучать усі звукові доріжки.');
  if (!vid.paused) mix.play();
}
const mixOn = () => !!mix.getAttribute('src');
function seek(t) { vid.currentTime = clamp(t, 0, dur); stopAt = null; playSeq = null; }
$('#play').onclick = () => vid.paused ? vid.play() : vid.pause();
vid.onplay = vid.onpause = () => { $('#play').textContent = vid.paused ? '▶' : '❚❚'; if (mixOn()) { mix.currentTime = vid.currentTime; vid.paused ? mix.pause() : mix.play(); } };
vid.onseeked = () => { if (mixOn()) mix.currentTime = vid.currentTime; };
let bufT = 0, bufPoll = 0, bufRow = null;                           // відео чекає дані — рядок у спільному індикаторі (коротку паузу не показуємо)
const bufShow = () => {
  if (bufRow) return; bufRow = document.createElement('div'); bufRow.className = 'bt';
  bufRow.innerHTML = '<i></i><b>Буферизація</b><span></span><span class="pb"><b></b></span><span></span>'; $('#busy').append(bufRow);
  const tick = async () => {                                         // запис Twitch: скільки шматка вже прийшло на сервер
    const r = /^https?:/.test(P?.video || '') ? await api('/api/hls/progress').catch(() => null) : null, f = r && r.total ? r.got / r.total : null;
    if (!bufRow) return; bufRow.querySelector('span').textContent = f == null ? '' : Math.round(f * 100) + '%'; bufRow.querySelector('.pb b').style.width = (f ?? 0) * 100 + '%';
  };
  tick(); bufPoll = setInterval(tick, 300);
};
const bufHide = () => { clearTimeout(bufT); clearInterval(bufPoll); bufPoll = 0; bufRow?.remove(); bufRow = null; };
['waiting', 'seeking'].forEach(e => vid.addEventListener(e, () => { clearTimeout(bufT); bufT = setTimeout(bufShow, 300); }));
['playing', 'canplay', 'seeked', 'emptied'].forEach(e => vid.addEventListener(e, bufHide));
document.onkeydown = e => {
  if (!$('#editor').classList.contains('on') || !P || e.target.matches('input,textarea,select,[contenteditable]')) return;
  if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyZ' || e.code === 'KeyY')) {
    e.preventDefault(); return e.code === 'KeyY' || e.shiftKey ? travel(redoSt, undoSt) : travel(undoSt, redoSt);
  }
  const ctl = e.ctrlKey || e.metaKey, sh = e.shiftKey, k = e.code, c = P.clips[sel], t = vid.currentTime, el = focus === 'el' && elById(selEl), q = focus === 'cue' && P.cues[selCue];
  if (ctl && k === 'KeyD') { e.preventDefault(); return focus === 'clip' && c ? dupClip(c) : duplicate(); }
  if (ctl && ['KeyC', 'KeyV'].includes(k)) { e.preventDefault(); return k === 'KeyC' ? copySel() : paste(); }
  if (ctl && (k === 'Delete' || k === 'Backspace')) { e.preventDefault(); return el ? deleteEl(el) : removeSel(); }
  if (ctl || e.altKey) return;
  const act = {
    Space: () => sh ? (q ? (seek(q.a), stopAt = q.b, vid.play()) : c && playClip(sel)) : vid.paused ? vid.play() : vid.pause(),
    KeyB: () => splitAt(), KeyI: () => setRegionEdge('a'), KeyO: () => setRegionEdge('b'), KeyQ: () => trimTo('a'), KeyW: () => trimTo('b'),
    KeyN: () => addAt(t), KeyM: () => addMusicEl(), KeyZ: () => c && select(sel, true),
    KeyH: () => el && (el.on = !el.on, renderEls(), save()), KeyG: () => q ? setCueGlobal(q, !!q.own) : el && elClip() && setGlobalIn(el, elClip(), !!ownOf(elClip(), el)),
    KeyR: () => focus === 'clip' && c && (c.on = !c.on, commit()),
    KeyJ: () => { if (!q) return; const nx = P.cues.slice(selCue + 1).find(x => rowOf(x) === rowOf(q)); if (nx) mergeCues(q, nx); },
    Enter: () => q && editCueText(),
    BracketRight: () => el && moveEl(el, sh ? 'top' : 'up'), BracketLeft: () => el && moveEl(el, sh ? 'bottom' : 'down'),
    Delete: removeSel, Backspace: removeSel,
  }[k];
  if (act) { e.preventDefault(); act(); }
  else if (e.code === 'Escape') { selEl = null; selOwn = null; sel = -1; selectCue(-1); multi.clear(); renderEls(); renderList(); }
  else if (e.code === 'ArrowLeft' || e.code === 'ArrowRight') { e.preventDefault(); seek(t + (e.code === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 5 : 1)); }
};
