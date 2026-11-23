// Спільне: стан проєкту, типи елементів, збереження й undo/redo, рядки поступу, поповери, навігація.
const $ = s => document.querySelector(s), $$ = s => document.querySelectorAll(s);
const api = (p, b) => fetch(p, b === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)})
  .then(async r => { const j = await r.json(); if (j && j.error) throw new Error(j.error); if (j && j.aborted) throw Object.assign(new Error('Скасовано'), {cancelled: true}); return j; });
const reportError = text => navigator.sendBeacon('/api/log', JSON.stringify({text: String(text).slice(0, 2000)}));   // помилки сторінки — у журнал програми (data/log.txt)
addEventListener('error', e => reportError(`${e.message} @ ${(e.filename || '').split('/').pop()}:${e.lineno}`));
addEventListener('unhandledrejection', e => reportError('promise: ' + (e.reason?.stack || e.reason)));
const fmt = t => { t = Math.max(0, t || 0); return Math.floor(t / 60) + ':' + (t % 60).toFixed(1).padStart(4, '0'); };
const parse = s => s.trim().split(':').reduce((a, x) => a * 60 + parseFloat(x), 0);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fileUrl = p => '/file?p=' + encodeURIComponent(p);
const uid = () => Math.random().toString(36).slice(2, 10);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const vid = $('#vid'), pv = $('#pv'), px = pv.getContext('2d'), tl = $('#tl'), tx = tl.getContext('2d');
if (LANG === 'en') for (const f of ['fillText', 'strokeText', 'measureText']) { const o = tx[f].bind(tx); tx[f] = (s, ...a) => o(tr(s), ...a); }   // написи таймлайна — мовою інтерфейсу
$$('#langSw [data-lang]').forEach(b => { b.classList.toggle('on', b.dataset.lang === LANG); b.onclick = () => b.dataset.lang !== LANG && setLang(b.dataset.lang); });

// ── елементи: що вміє кожен і як це показати людині ──
const ANIM = [['none', 'Без'], ['fade', 'Поява'], ['pop', 'Вистрибує'], ['slide', 'Знизу']];
const COLORS = ['#ffffff', '#111111', '#ffcc33', '#ff3b30', '#e91916', '#a970ff', '#4fa3ff', '#5fe08a'];
const SHAPE = [['shape', 'seg', 'Форма', [['rect', 'Прямокутник'], ['round', 'Заокруглена'], ['circle', 'Коло']]],
  ['radius', 'range', 'Заокруглення', [0, 200, 1, 'px'], e => e.shape === 'round'], ['bw', 'range', 'Рамка', [0, 30, 1, 'px']], ['border', 'color', 'Колір рамки', null, e => e.bw > 0]];
const T = (name, ic, col, size, props) => ({name, ic, col, size, props});
const NETS = [['tiktok', 'TikTok'], ['youtube', 'YouTube'], ['instagram', 'Instagram'], ['telegram', 'Telegram'], ['twitch', 'Twitch'],
              ['discord', 'Discord'], ['kick', 'Kick'], ['x', 'X'], ['facebook', 'Facebook'], ['threads', 'Threads'], ['linkedin', 'LinkedIn'], ['bluesky', 'Bluesky'], ['mastodon', 'Mastodon']];   // логотипи — app/brands.py
const TYPES = {
  video:  T('Відео', '▶', '#6b8fb8', ['w'], [['vol', 'range', 'Гучність звуку', [0, 200, 1, '%', 100]], ...SHAPE]),
  cam:    T('Вебкамера', '◉', '#b8789a', ['w'], [['detect', 'button', 'Знайти вебкамеру автоматично'], ...SHAPE]),
  card:   T('Плашка відео', '▤', '#c9a75a', ['s'], [['preview', 'file', 'Прев\'ю'], ['logo', 'file', 'Аватар'], ['title', 'area', 'Назва'],
            ['channel', 'text', 'Канал'], ['font', 'font', 'Шрифт'], ['s', 'range', 'Розмір', [30, 250, 1, '%', 100]], ['anim', 'seg', 'Поява', ANIM]]),
  stream: T('Плашка етеру', '◎', '#c9a75a', ['s'], [['logo', 'file', 'Аватар'], ['channel', 'text', 'Нікнейм'], ['title', 'area', 'Назва етеру'],
            ['category', 'text', 'Гра / категорія'], ['badge', 'text', 'Бейдж'], ['font', 'font', 'Шрифт'], ['s', 'range', 'Розмір', [30, 250, 1, '%', 100]], ['anim', 'seg', 'Поява', ANIM]]),
  social: T('Соцмережа', '@', '#6b95c9', ['size'], [['net', 'seg', 'Мережа', NETS], ['handle', 'text', 'Нікнейм чи посилання'],
            ['style', 'seg', 'Вигляд', [['dark', 'Темна плашка'], ['brand', 'Колір мережі'], ['clean', 'Без плашки']]], ['font', 'font', 'Шрифт'],
            ['size', 'range', 'Розмір', [20, 140, 1, 'px']], ['anim', 'seg', 'Поява', ANIM]]),
  text:   T('Текст', 'T', '#9a86c6', ['size'], [['text', 'area', 'Текст'], ['font', 'font', 'Шрифт'], ['size', 'range', 'Розмір', [16, 220, 1, 'px']],
            ['color', 'color', 'Колір'], ['stroke', 'color', 'Колір обведення', null, e => !e.bgOn], ['bgOn', 'toggle', 'Плашка під текстом'], ['bg', 'color', 'Колір плашки', null, e => e.bgOn], ['anim', 'seg', 'Поява', ANIM]]),
  chat:   T('Чат-повідомлення', '“', '#8a7fc0', ['s'], [['name', 'text', 'Нік глядача'], ['nameColor', 'color', 'Колір ніка'], ['text', 'area', 'Повідомлення'],
            ['font', 'font', 'Шрифт'], ['s', 'range', 'Розмір', [40, 220, 1, '%', 100]], ['anim', 'seg', 'Поява', ANIM]]),
  image:  T('Зображення', '▣', '#c49a6c', ['w'], [['path', 'file', 'Файл'], ['w', 'range', 'Ширина', [40, 1080, 1, 'px']], ['anim', 'seg', 'Поява', ANIM]]),
  progress: T('Прогрес-бар', '▬', '#c9a75a', [], [['color', 'color', 'Колір'], ['h', 'range', 'Товщина', [4, 40, 1, 'px']], ['pos', 'seg', 'Де', [['top', 'Згори'], ['bottom', 'Знизу']]]]),
  bg:     T('Фон', '▦', '#7a756e', [], [['style', 'seg', 'Фон', [['blur', 'Розмите відео'], ['color', 'Колір']]], ['blur', 'range', 'Розмиття', [1, 30, 1, ''], e => e.style !== 'color'],
            ['dim', 'range', 'Затемнення', [0, 80, 1, '%', 100], e => e.style !== 'color'], ['color', 'color', 'Колір', null, e => e.style === 'color']]),
  music:  T('Музика', '♪', '#8a70c4', [], [['path', 'audio', 'Трек'], ['vol', 'range', 'Гучність', [0, 200, 5, '%', 100]],
            ['fin', 'seg', 'Наростання', [[0, 'Ні'], [.5, '0.5 с'], [1, '1 с'], [2, '2 с']]], ['fout', 'seg', 'Згасання', [[0, 'Ні'], [.5, '0.5 с'], [1, '1 с'], [2, '2 с']]]]),
  subs:   T('Субтитри', 'CC', '#6aa87a', ['size', 'w'], [['name', 'text', 'Спікер'], ['font', 'font', 'Шрифт'], ['size', 'range', 'Розмір', [30, 160, 1, 'px']],
            ['color', 'color', 'Колір'], ['karaoke', 'toggle', 'Підсвічувати слово, що звучить'], ['hl', 'color', 'Колір підсвітки', null, e => e.karaoke],
            ['upper', 'toggle', 'ВЕЛИКІ ЛІТЕРИ'], ['outline', 'range', 'Обведення', [0, 16, 1, 'px']], ['stroke', 'color', 'Колір обведення', null, e => e.outline > 0], ['anim', 'seg', 'Поява фрази', ANIM.slice(0, 3)]]),
};
const CATALOG = [
  ['Для етерів', [
    ['Плашка етеру', 'аватар з LIVE, нік, гра', {type: 'stream', s: 1, y: 170, channel: 'Нікнейм', title: 'Назва етеру', category: 'Гра', badge: 'LIVE'}],
    ['Чат-повідомлення', 'репліка глядача з ніком', {type: 'chat', s: 1, name: 'viewer42', nameColor: '#a970ff', text: 'ахахах це було епічно', y: 1000, anim: 'slide', from: 1}],
    ['Нікнейм у соцмережі', 'логотип мережі й @нік', {type: 'social', net: 'tiktok', handle: '@nickname', style: 'dark', size: 46, y: 1700, anim: 'none'}]]],
  ['Текст', [
    ['Заголовок-хук', 'жирний текст на жовтому', {type: 'text', text: 'ЦЕ ТРЕБА БАЧИТИ', size: 70, color: '#111111', bg: '#ffcc33', bgOn: true, y: 120}],
    ['Підпис з обведенням', 'текст просто поверх відео', {type: 'text', text: 'Текст', size: 80, color: '#ffffff', stroke: '#000000', bg: '#000000', bgOn: false, y: 900}],
    ['Субтитри', 'стиль автосубтитрів', {type: 'subs', size: 84, color: '#ffffff', hl: '#ffcc33', karaoke: true, upper: false, outline: 6, stroke: '#000000', anim: 'pop', words: 3, lang: '', w: 900, x: 90, y: 1380}]]],
  ['Оформлення', [
    ['Плашка відео', 'прев\'ю, назва, канал', {type: 'card', s: 1, y: 170, title: 'Назва відео', channel: 'Канал'}],
    ['Зображення / лого', 'PNG з прозорістю', {type: 'image', w: 240, y: 60}],
    ['Прогрес-бар', 'смуга, що росте за кліп', {type: 'progress', color: '#ffcc33', h: 12, pos: 'bottom', x: 0, y: 1908}],
    ['Фон', 'розмиття або колір', {type: 'bg', style: 'blur', blur: 5, dim: .12, color: '#111111'}]]],
  ['Відео', [
    ['Вебкамера на всю ширину', 'камера згори, гра знизу', {type: 'cam', src: [0.72, 0.62, 0.26, 0.34], w: 1080, x: 0, y: 0, shape: 'rect', bw: 0, border: '#ffffff', stack: true}],
    ['Ще шар відео', 'інший фрагмент кадру', {type: 'video', src: [0.3, 0.3, 0.4, 0.4], w: 700, x: 190, y: 700, shape: 'round', radius: 40, bw: 0, border: '#ffffff'}]]],
  ['Музика', [
    ['Музика', 'трек з файлу, з хвилею на таймлайні', {type: 'music', vol: 1, fin: 0, fout: 1}]]]
];
const SINGLE = ['bg'];
const mk = p => { const o = structuredClone(p); for (const k of ['text', 'channel', 'title', 'category']) if (typeof o[k] === 'string') o[k] = tr(o[k]);   // типовий текст нового елемента — мовою інтерфейсу
  return {id: uid(), on: true, x: null, y: 800, anim: 'none', from: 0, to: 0, ...o}; };
const BASE = [1080, 1920];                                         // полотно 9:16: у ньому задано заготовки елементів
const canvasOf = r => r < 1 ? [1080, Math.round(1080 / r)] : [Math.round(1080 * r), 1080];   // коротша сторона — 1080
const CW = () => P?.canvas?.[0] || BASE[0], CH = () => P?.canvas?.[1] || BASE[1];

let audioTracks = 1, cfg = {}, P = null, dur = 0, S = {w: 1920, h: 1080}, curve = [], t0 = 0, lo = 0, hi = 1, step = .5;
let sel = -1, selCue = -1, selEl = null, stopAt = null, mode = 'short', drag = null, guide = null, pvGuides = [], view = {t0: 0, t1: 1}, TW = 0, TH = 0;
let selOwn = null;                                                // вибрано не сам елемент, а його не глобальний екземпляр (у кліпі чи репліці)
const arts = new Map();
// ── глобальний чи ні — у кожному кліпі окремо: не глобальний має свої налаштування лише для цього кліпу (c.own[id]).
//    У списку зліва він — рядок під своїм елементом, і праворуч від списку редагуються саме його налаштування ──
const OWN_KEEP = ['id', 'type', 'on', 'solo', 'from', 'to'];     // це в кліпі завжди спільне
const canOwn = e => !!e && !['subs', 'bg', 'music'].includes(e.type);
const ownOf = (c, e) => c?.own?.[e.id] || null;
function effEl(e, c) {                                            // яким елемент є в кліпі c
  const o = ownOf(c, e); if (!o) return e;
  for (const k of OWN_KEEP) o[k] = e[k]; return o;
}
function setGlobalIn(e, c, on) {
  if (!c || !canOwn(e) || on === !ownOf(c, e)) return;
  if (on) { if (selOwn === c.own[e.id]) selOwn = null; delete c.own[e.id]; if (!Object.keys(c.own).length) delete c.own; }
  else { const o = structuredClone(e); o._own = uid(); (c.own ||= {})[e.id] = o; selEl = e.id; selOwn = o; }
  renderEls(); save();
}
const pvClip = () => P?.clips.length ? clipAt(vid.currentTime) : null;   // кліп, який зараз показує прев'ю
const aid = e => e._own ? `${e.id}@${e._own}` : e.id;              // картинка елемента: своя в кожного не глобального екземпляра
const els = () => P ? P.elements : [];
const elById = id => els().find(e => e.id === id);
const region = () => P.region || [0, Math.min(dur, 1800)];
const msg = (t, err) => { $('#msg').textContent = t; $('#msg').classList.toggle('err', !!err); };
// кожен спікер — окремий елемент «Субтитри» зі своїм стилем і місцем; репліка знає свій елемент (sid), без нього — першого
const SUB_COLORS = ['#ffffff', '#ffd84d', '#6fd3ff', '#ff8ad8', '#9dff7a', '#ffa45c'];
const subsEls = (list = els()) => list.filter(e => e.type === 'subs');
const cueOwner = (c, list) => subsEls(list).find(e => e.id === c.sid) || subsEls(list)[0];
const rowOf = c => Math.max(0, subsEls().indexOf(cueOwner(c)));    // рядок на таймлайні
const subRows = () => subsEls().length ? subsEls() : [{name: '', color: '#ffffff'}];
const subName = (e, i) => e.name || tr(`Субтитри ${i + 1}`);
function addSubsEl(list, name, from) {                            // новий спікер: копія стилю, інший колір, рядком вище
  const n = subsEls(list).length, base = from || subsEls(list).at(-1) || CATALOG[1][1][2][2];
  const el = {...mk(base), id: uid(), name: name ?? tr(`Спікер ${n + 1}`), color: SUB_COLORS[n % SUB_COLORS.length], on: true};
  if (from || n) el.y = Math.max(0, (base.y ?? 1380) - (base.size || 84) * 1.6);
  list.push(el); return el;
}
const ensureSubs = () => subsEls()[0] || (addSubsEl(P.elements, ''), renderEls(), subsEls()[0]);

// ── час кліпу без вирізаних пропусків ──
const kept = c => { const out = []; let t = c.a; for (const [x, y] of [...(c.cut || [])].sort((p, q) => p[0] - q[0]).concat([[c.b, c.b]])) { if (Math.min(x, c.b) - t > .05) out.push([t, Math.min(x, c.b)]); t = Math.max(t, y); } return out; };
const net = c => kept(c).reduce((s, [a, b]) => s + b - a, 0);
const toOut = (c, t) => kept(c).reduce((s, [a, b]) => s + Math.max(0, Math.min(t, b) - a), 0);
const toSrc = (c, r, start) => { for (const [a, b] of kept(c)) { if (start ? r < b - a : r <= b - a) return a + r; r -= b - a; } return c.b; };   // на межі вирізаного: кінець — до нього, початок (start) — після
const clipAt = t => P.clips.find(c => t >= c.a && t < c.b);
const ctxClip = () => P.clips[sel] || clipAt(vid.currentTime) || P.clips[0];

// ── збереження й undo/redo ──
let undoSt = [], redoSt = [], curSnap = null, saveT;
const snapNow = (p = P) => JSON.stringify({clips: p.clips, elements: p.elements, cues: p.cues, region: p.region, music: p.music, canvas: p.canvas});
const resetHist = () => { undoSt = []; redoSt = []; curSnap = snapNow(); };
function record() { const s = snapNow(); if (curSnap !== null && s !== curSnap) { undoSt.push(curSnap); if (undoSt.length > 200) undoSt.shift(); redoSt = []; } curSnap = s; }
function save(now) {
  clearTimeout(saveT);
  const go = () => { record(); return api('/api/project/save', {id: P.id, name: P.name, video: P.video, region: P.region, clips: P.clips, elements: P.elements, cues: P.cues, scan: P.scan, music: P.music, canvas: P.canvas, cover: P.cover}); };
  if (now) return go(); saveT = setTimeout(go, 400);
}
function travel(from, to) {
  if (!from.length) return; multi.clear();
  to.push(curSnap); curSnap = from.pop(); Object.assign(P, JSON.parse(curSnap));
  sel = Math.min(sel, P.clips.length - 1); selCue = -1; selOwn = null; renderAll(); api('/api/project/save', {id: P.id, ...JSON.parse(curSnap)});
}
$('#undo').onclick = () => travel(undoSt, redoSt); $('#redo').onclick = () => travel(redoSt, undoSt);

// ── скільки ще чекати: зі справжнього поступу операції; швидкість цього ПК (сервер уточнює її після кожного запуску) — лише поки поступу ще немає ──
const fmtDur = s => {
  if (s < 60) return `${Math.max(5, Math.round(s / 5) * 5)} с`;
  if (s < 600) { const r = Math.round(s / 10) * 10, m = Math.floor(r / 60), x = r % 60; return x ? `${m} хв ${x} с` : `${m} хв`; }
  return s < 3600 ? `${Math.round(s / 60)} хв` : `${Math.floor(s / 3600)} год ${Math.round(s % 3600 / 60)} хв`;
};
const speed = () => ({scan: 5, stt: 10, llm: 20, render: 1, ...cfg.speed});
const plans = {                                                   // етапи операції з очікуваною тривалістю, с
  analyze: (suggest, ai) => { const [a, b] = region(); return [['scan', (b - a) / speed().scan], ...(cfg.stt && suggest ? [['stt', (b - a) / speed().stt]] : []),
    ...(cfg.stt && suggest && ai ? [['llm', (b - a) / speed().llm]] : [])]; },
  subs: () => { const [a, b] = region(); return [['stt', (b - a) * audioTracks / speed().stt]]; },   // кожна доріжка — окремо
  render: clips => [['render', clips.reduce((s, c) => s + net(c) * (hookOk(c) || (c.loop != null && loopOk(c, c.loop)) ? 2 : 1), 0) / speed().render]],   // хук чи петля — кліп кодується двічі
};
const planTotal = p => p.reduce((s, [, e]) => s + e, 0);
// кожна довга операція — свій рядок у індикаторі згори: паралельні аналіз і субтитри не перебивають одне одного
function eta(plan, t0) {                                          // стежить за операцією: show(стан від сервера) → [частка, залишок с або null, етап прострочено]
  const seen = {}; let slow = 1, stageT = 0, lastFrac = 0, pct = 0;
  return s => {
    const now = Date.now(), i = plan.findIndex(p => p[0] === s.stage);
    if (i >= 0 && seen[i] == null) {                              // новий етап: попередні йшли повільніше чи швидше, ніж зазвичай, — так піде й решта
      seen[i] = stageT = now; const planned = planTotal(plan.slice(0, i));
      if (i > 0 && planned > 1) slow = clamp((now - t0) / 1000 / planned, .2, 20);
    }
    if (s.frac != null && s.frac < lastFrac - .2) stageT = now;   // етап почав нову частину (скажімо, завантаження → робота)
    if (s.frac != null) lastFrac = s.frac;
    const elSt = (now - (stageT || t0)) / 1000, cur = i >= 0 ? plan[i][1] * slow : 0, after = i >= 0 ? planTotal(plan.slice(i + 1)) * slow : 0;
    let rem;
    if (s.eta != null) rem = s.eta;                                // сервер бачить, як швидко йде саме зараз
    else if (s.frac > .03 && elSt > 3) rem = elSt * (1 - s.frac) / s.frac;
    else if (i >= 0) rem = cur - elSt;                             // поступу ще немає — за швидкістю ПК; може вийти за межу
    else if (!s.stage) rem = planTotal(plan) * slow - (now - t0) / 1000;
    else rem = null;                                               // етап, якого немає в плані: чесно не знаємо
    if (i >= 0) { const fr = s.frac ?? clamp(elSt / Math.max(1, cur), 0, .95); pct = clamp((planTotal(plan.slice(0, i)) * slow + fr * cur) / Math.max(1, planTotal(plan) * slow), 0, 1); }
    else if (s.frac != null && plan.length < 2) pct = s.frac;
    return [pct, rem == null ? null : rem + after, rem != null && rem <= 0];
  };
}
// кожна довга операція — свій рядок у індикаторі згори; cancel — з кнопкою «Скасувати»
async function busy(btn, label, plan, start, key, cancel) {
  const task = key || uid(), t0 = Date.now(), track = eta(plan, t0);
  const row = document.createElement('div'); row.className = 'bt';
  row.innerHTML = `<i></i><b>${esc(label)}</b><span></span><span class="pb"><b></b></span>${cancel ? '<button class="bx" title="Скасувати" aria-label="Скасувати">✕</button>' : '<span></span>'}`;
  const txt = row.querySelector('span'), bar = row.querySelector('.pb b'), bx = row.querySelector('.bx');
  let live = true, stopping = false, last = {}, deadline = 0;
  if (bx) bx.onclick = () => { stopping = true; bx.disabled = true; txt.textContent = 'Скасовую…'; api('/api/cancel', {key: task}).catch(() => {}); };
  btn.disabled = true; $('#busy').append(row);
  const show = () => {                                            // залишок відлічується щосекунди, а не стрибає з кожною відповіддю
    if (!live || stopping) return;
    const now = Date.now(), [frac, left, late] = track(last), head = last.text && last.text !== label ? last.text + ' · ' : '';
    let when;
    if (left == null || late) { deadline = 0; when = `${late ? 'довше, ніж зазвичай · ' : ''}минуло ${fmtDur((now - t0) / 1000)}`; }
    else {
      const target = now + left * 1000;
      if (!deadline || Math.abs(target - deadline) > Math.max(5000, left * 150)) deadline = target;   // нова оцінка помітно інша — беремо її
      const l = (deadline - now) / 1000; when = l < 3 ? 'ще трохи' : `ще ~${fmtDur(l)}`;
    }
    txt.textContent = txt.title = `${head}${Math.round(frac * 100)}% · ${when}`; bar.style.width = frac * 100 + '%';
  };
  show(); const tick = setInterval(show, 1000);
  const iv = setInterval(async () => { const s = (await api('/api/status').catch(() => ({}))).tasks?.[task]; if (live && s) { last = s; show(); } }, 1000);   // запізніла відповідь не перезапише рядок
  try { return await start(task); } finally {
    live = false; clearInterval(iv); clearInterval(tick); row.remove(); btn.disabled = false;
  }
}
function showRegionLabel() {                                      // скільки чекати — лише в індикаторі згори
  if (!P || !dur) return;
  const [ra, rb] = region(), rl = `Область ${fmt(rb - ra).replace(/\.\d$/, '')}`;
  if ($('#rlen').textContent !== rl) $('#rlen').textContent = rl;
}

// ── поповери: відкрити один, закрити кліком повз ──
function togglePop(id, ev) { ev.stopPropagation(); const p = $(id), on = !p.classList.contains('on'); $$('.pop').forEach(x => x.classList.remove('on')); p.classList.toggle('on', on); }
document.addEventListener('click', e => { if (!e.target.closest('.pop')) $$('.pop').forEach(x => x.classList.remove('on')); });

// ── навігація ──
function show(v) {
  $$('.view').forEach(e => e.classList.toggle('on', e.id === v));
  $$('nav button').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  $('#pname').style.visibility = v === 'editor' && P ? 'visible' : 'hidden';
  if (v === 'home') loadHome(); else if (v === 'pub') loadPub(); else { resizeTL(); if (!tourSeen() && tourI < 0) setTimeout(() => tour(0), 400); }   // новачкам — тур
}
$$('nav button').forEach(b => b.onclick = () => show(b.dataset.view));
$('#pname').oninput = e => { if (P) { P.name = e.target.value; save(); } };
