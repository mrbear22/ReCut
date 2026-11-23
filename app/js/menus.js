// Контекстні меню й лассо.
// ── контекстне меню: усі дії саме з тим, по чому клікнули правою кнопкою ──
// пункт: '-' роздільник · {hd} заголовок · {row: [{ic, title, on, run}]} ряд кнопок · {label, key, off, on, run}
let menuItems = [];
function tidyMenu(items) {                                        // без порожніх пунктів і зайвих роздільників
  const out = [];
  for (const it of items) if (it && !(it === '-' && (!out.length || out.at(-1) === '-'))) out.push(it);
  if (out.at(-1) === '-') out.pop(); return out;
}
const menuHtml = (it, i) => it === '-' ? '<hr>' : it.hd ? `<div class="hd">${esc(it.hd)}</div>`
  : it.row ? `<div class="rw">${it.row.map((b, j) => `<button data-i="${i}.${j}" title="${esc(b.title)}" aria-label="${esc(b.title)}" class="${b.on ? 'on' : ''} ${'sw' in b ? 'sw' : ''}"${b.sw ? ` style="--sw:${b.sw}"` : ''}>${esc(b.ic || '')}</button>`).join('')}</div>`
  : `<button data-i="${i}" role="menuitem" class="${it.on ? 'on' : ''}" ${it.off ? 'disabled' : ''}><span>${esc(it.label)}</span><span class="k">${esc(it.key || '')}</span></button>`;
function openMenu(e, items) {
  e.preventDefault(); e.stopPropagation(); menuItems = tidyMenu(items);
  const m = $('#ctx'); if (!menuItems.length) return closeMenu();
  m.innerHTML = menuItems.map(menuHtml).join(''); m.classList.add('on');
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = clamp(e.clientX, 4, innerWidth - w - 4) + 'px';
  m.style.top = (e.clientY + h > innerHeight - 4 ? Math.max(4, e.clientY - h) : e.clientY) + 'px';
}
const closeMenu = () => $('#ctx').classList.remove('on');
$('#ctx').onclick = e => {
  e.stopPropagation(); const b = e.target.closest('button[data-i]'); if (!b || b.disabled) return;
  const [i, j] = b.dataset.i.split('.').map(Number), it = menuItems[i];
  closeMenu(); (j >= 0 ? it.row[j].run : it.run)();
};
$('#ctx').oncontextmenu = e => e.preventDefault();
addEventListener('pointerdown', e => { if (!e.target.closest('#ctx')) closeMenu(); }, true);
addEventListener('keydown', e => { if (e.key === 'Escape' && $('#ctx').classList.contains('on')) { closeMenu(); e.stopImmediatePropagation(); } }, true);
for (const ev of ['blur', 'resize', 'wheel']) addEventListener(ev, closeMenu, {passive: true});

// ── меню кліпу ──
function splitClip(c, t) {                                        // два кліпи; вирізані шматки розходяться по своїх половинах
  const within = (a, b) => (c.cut || []).map(([u, v]) => [Math.max(u, a), Math.min(v, b)]).filter(([u, v]) => v - u >= .2);
  const right = {...structuredClone(c), a: t, cut: within(t, c.b)};
  if (c.loop >= t) delete c.loop; else delete right.loop;          // петля лишається в тій половині, де стоїть
  if (c.hook?.[0] >= t) delete c.hook; else { delete right.hook; if (c.hook) c.hook[1] = Math.min(c.hook[1], t); }   // хук — теж
  c.cut = within(c.a, t); c.b = t; P.clips.push(right); commit();
}
function dupClip(c) {                                             // копія одразу після оригіналу
  const len = c.b - c.a, a = Math.min(c.b, dur - len);
  P.clips.push({...structuredClone(c), a, b: a + len, cut: shiftCuts(c.cut, a - c.a), ...(c.loop != null ? {loop: c.loop + a - c.a} : {}), ...(c.hook ? {hook: c.hook.map(x => x + a - c.a)} : {})}); sel = P.clips.length - 1; commit();
}
const CLIP_COLORS = [[null, 'Без кольору'], ['#c25b52', 'Червоний'], ['#d08a3c', 'Помаранчевий'], ['#c9ad45', 'Жовтий'],
  ['#62a467', 'Зелений'], ['#4f94b8', 'Блакитний'], ['#8a70c4', 'Фіолетовий'], ['#c46a9e', 'Рожевий']];
function clipMenu(i, t, at) {
  const c = P.clips[i], cut = (c.cut || []).find(([u, v]) => t >= u && t <= v);
  sel = i; selCue = -1; focus = 'clip'; $('#cueEdit').classList.remove('on'); renderList(); renderProps();
  const lk = locked(c);
  return [{hd: `Кліп #${i + 1} · ${net(c).toFixed(1)} с`}, {label: lk ? 'Розблокувати кліп' : 'Заблокувати кліп', key: 'L', run: () => toggleLock(c)}, {label: 'Додати музику в кліп', key: 'M', run: () => addMusicEl(c)},
    {row: CLIP_COLORS.map(([col, title]) => ({sw: col, title, on: (c.col || null) === col, run: () => { c.col = col || undefined; commit(); }}))},
    cut && !lk && {label: 'Повернути вирізане', run: () => { c.cut = c.cut.filter(u => u !== cut); commit(); }},
    {label: 'Програти кліп', key: 'Shift+Space', run: () => playClip(P.clips.indexOf(c))},
    {label: `Почати кліп ${at}`, key: 'Q', off: lk || t > c.b - 1, run: () => { c.a = t; commit(); }},
    {label: `Закінчити кліп ${at}`, key: 'W', off: lk || t < c.a + 1, run: () => { c.b = t; commit(); }},
    loopOk(c, t) && {label: `Петля: шорт почнеться ${at}`, key: 'Правий Alt+клік', run: () => { c.loop = t; delete c.hook; commit(); }},
    c.loop != null && {label: 'Прибрати петлю', run: () => { delete c.loop; commit(); }},
    c.hook && {label: 'Прибрати хук', run: () => { delete c.hook; commit(); }},
    {label: `Розрізати на два ${at}`, key: 'B', off: lk || t < c.a + .5 || t > c.b - .5, run: () => splitClip(c, t)},
    c.cut?.length && !lk && {label: 'Повернути всі вирізані шматки', run: () => { c.cut = []; commit(); }},
    '-',
    {label: c.on ? 'Не рендерити цей кліп' : 'Рендерити цей кліп', key: 'R', run: () => { c.on = !c.on; commit(); }},
    {label: 'Наблизити на таймлайні', key: 'Z', run: () => select(P.clips.indexOf(c), true)},
    '-',
    {label: 'Копіювати', key: 'Ctrl+C', run: copySel},
    {label: 'Дублювати після нього', key: 'Ctrl+D', run: () => dupClip(c)},
    {label: 'Видалити кліп', key: 'Del', off: lk, run: removeSel}];
}

// ── меню репліки ──
const wordsOf = q => q.text.split(/\s+/).filter(Boolean);
function wordTimes(q) {                                           // початок кожного слова: з розпізнавання (k) або рівно по репліці; завжди в її межах
  const w = wordsOf(q), k = q.k?.length === w.length ? q.k : w.map((_, i) => q.a + i * (q.b - q.a) / w.length);
  return k.map(v => clamp(v, q.a, q.b));
}
const splitIdx = (q, t, w = wordsOf(q)) => clamp(q.k?.length === w.length ? q.k.filter(s => s < t).length : Math.round(w.length * (t - q.a) / (q.b - q.a)), 1, w.length - 1);
function splitCue(q, t, n) {                                      // за часом t (слова діляться за їхнім часом, а без нього — пропорційно) або за словом n
  const w = wordsOf(q), hasK = q.k?.length === w.length, f = fmtOf(q);
  if (n == null) n = splitIdx(q, t, w); else t = hasK ? q.k[n] : q.a + (q.b - q.a) * n / w.length;
  const tidy = x => x.some(Boolean) ? x : undefined;
  const r = {...structuredClone(q), a: t, text: w.slice(n).join(' '), k: hasK ? q.k.slice(n) : [], fmt: tidy(f.slice(n))};
  if (r.own) r.own._own = uid();
  Object.assign(q, {b: t, text: w.slice(0, n).join(' '), k: hasK ? q.k.slice(0, n) : [], fmt: tidy(f.slice(0, n))});
  for (const x of [q, r]) if (!x.fmt) delete x.fmt;
  P.cues.push(r); P.cues.sort((x, y) => x.a - y.a); selectCue(P.cues.indexOf(r), false); save();
}
function mergeCues(q, nx) {                                       // стиль — від першої, форматування слів — кожного свого
  const timed = c => c.k?.length === wordsOf(c).length, f = [...fmtOf(q), ...fmtOf(nx)];
  q.k = timed(q) && timed(nx) ? [...q.k, ...nx.k] : []; q.text = `${q.text} ${nx.text}`.trim(); q.b = nx.b;
  if (f.some(Boolean)) q.fmt = f; else delete q.fmt;
  if (selOwn === nx.own) selOwn = null;
  P.cues.splice(P.cues.indexOf(nx), 1); selectCue(P.cues.indexOf(q), false); renderEls(); save();
}
async function pickAudio() {
  const {path} = await api('/api/pick', {kind: 'audio'}); if (!path) return null;
  const {dur: d} = await api('/api/audio?p=' + encodeURIComponent(path)).catch(() => ({dur: 0}));
  if (!d) { msg('Не вдалося прочитати аудіофайл', 1); return null; }
  return {path, name: path.split(/[\\/]/).pop().replace(/\.[^.]+$/, ''), dur: d, off: 0};
}
async function addMusicEl(c = P.clips.length ? ctxClip() : null) {   // музика живе всередині кліпу
  const a = await pickAudio(); if (!a) return;
  const el = {...mk({type: 'music', vol: 1, fin: 0, fout: 1}), ...a, solo: !!c};   // кліпів ще немає — у всіх кліпах
  P.elements.push(el); if (c) (c.segs ||= {})[el.id] = [[0, a.dur < net(c) - .05 ? a.dur : 0]];
  selEl = el.id; focus = 'el'; renderEls(); save(true); loadPeaks(el.path);
}
const peaks = new Map();                                          // трек → гучність, 50 значень на секунду від t0
const asPeaks = r => ({rate: r.rate, t0: r.t0 || 0, v: Uint8Array.from(atob(r.b64), ch => ch.charCodeAt(0))});
function loadPeaks(path) {
  if (peaks.has(path)) return; peaks.set(path, null);
  api('/api/peaks?p=' + encodeURIComponent(path)).then(r => peaks.set(path, asPeaks(r))).catch(() => peaks.delete(path));
}
const waveCols = new Map();                                       // доріжка → висоти стовпчиків для поточного масштабу
function videoWave(k, keep) {                                     // keep — стара хвиля лишається, поки не прийде нова
  const key = `${P.video}#${k}`; if (!keep) peaks.set(key, null);
  api(`/api/peaks?p=${encodeURIComponent(P.video)}${audioTracks > 1 ? '&track=' + k : ''}`)
    .then(r => { peaks.set(key, asPeaks(r)); waveCols.delete(k); drawTL(); }).catch(() => keep || peaks.delete(key));
}
let waveTimer = 0;
function refreshWave() {                                          // Twitch: хвиля росте разом зі скачаними шматками
  if (!P || !/^https?:/.test(P.video || '')) return;
  clearTimeout(waveTimer); waveTimer = setTimeout(() => { for (const key of peaks.keys()) if (key.startsWith(P.video + '#')) videoWave(+key.split('#').pop(), true); }, 2000);
}
function rowWave(k, y) {                                          // сіра хвиля звукової доріжки відео — фоном рядка реплік
  const key = `${P.video}#${k}`, pk = peaks.get(key);
  if (!pk) { if (!peaks.has(key)) videoWave(k); return; }
  const vk = `${key}|${view.t0}|${view.t1}|${TW}`; let cols = waveCols.get(k);
  if (!cols || cols.vk !== vk) {                                  // перераховуємо лише при зміні масштабу чи прокрутці
    cols = new Uint8Array(Math.ceil(TW / 2)); cols.vk = vk;
    for (let j = 0; j < cols.length; j++) {
      const a = Math.floor((Tt(j * 2) - pk.t0) * pk.rate), i0 = Math.max(0, a), i1 = Math.min(pk.v.length, Math.max(a + 1, Math.floor((Tt(j * 2 + 2) - pk.t0) * pk.rate)));
      let v = 0; for (let i = i0; i < i1; i++) if (pk.v[i] > v) v = pk.v[i]; cols[j] = v;
    }
    waveCols.set(k, cols);
  }
  const mid = y + CUE / 2, h = CUE / 2 - 2; tx.fillStyle = 'rgba(255,255,255,.12)';
  for (let j = 0; j < cols.length; j++) if (cols[j] > 6) { const hh = cols[j] / 255 * h; tx.fillRect(j * 2, mid - hh, 1.5, hh * 2); }
}
function drawWave(e, c, a, b, y, col) {                            // хвиля під шматком: що саме з треку грає в цьому місці
  const pk = peaks.get(e.path); if (!pk) return loadPeaks(e.path);
  const mid = y + BAR / 2, h = BAR / 2 - 3, off = e.off || 0; tx.fillStyle = col;
  for (let x = Math.max(a + 2, 0); x < Math.min(b - 2, TW); x += 2) {
    const i0 = Math.floor((off + toOut(c, Tt(x))) * pk.rate), i1 = Math.max(i0 + 1, Math.floor((off + toOut(c, Tt(x + 2))) * pk.rate));
    let v = 0; for (let i = Math.max(0, i0); i < Math.min(i1, pk.v.length); i++) v = Math.max(v, pk.v[i]);
    const hh = Math.max(.5, v / 255 * h); tx.fillRect(x, mid - hh, 1.4, hh * 2);
  }
}
function overwrite(kind, it) {                                     // те, що поклали зверху, підрізає перекрите в тому ж рядку
  if (!it) return;
  const list = kind === 'cue' ? P.cues : P.clips, MIN = kind === 'clip' ? 1 : .2;
  const same = o => o !== it && !locked(o) && (kind !== 'cue' || rowOf(o) === rowOf(it)) && o.a < it.b - .01 && o.b > it.a + .01;
  const cutsIn = (o, a, b) => (o.cut || []).filter(([u, v]) => v > a && u < b).map(([u, v]) => [Math.max(u, a), Math.min(v, b)]);
  for (const o of list.filter(same)) {
    if (o.a >= it.a - .01 && o.b <= it.b + .01) { list.splice(list.indexOf(o), 1); continue; }     // повністю під новим — геть
    if (o.a < it.a && o.b > it.b) {                               // новий усередині — старий ділиться на два (у репліки лишається початок)
      if (kind !== 'cue' && o.b - it.b >= MIN) {
        const r = {...structuredClone(o), a: it.b};
        if (kind === 'clip') { r.cut = cutsIn(o, it.b, o.b); delete r.id; }
        list.push(r);
      }
      o.b = it.a;
    } else if (o.a < it.a) o.b = it.a;                            // зачепили кінець
    else o.a = it.b;                                             // зачепили початок
    if (kind === 'clip') o.cut = cutsIn(o, o.a, o.b);
    if (o.b - o.a < MIN) list.splice(list.indexOf(o), 1);
  }
  if (kind === 'cue') { P.cues.sort((x, y) => x.a - y.a); selCue = P.cues.indexOf(it); }
  if (kind === "clip") sel = P.clips.indexOf(it);
}
function dupCue(q) {                                              // копія одразу після оригіналу
  const len = q.b - q.a, a = Math.min(q.b, dur - len), r = {...structuredClone(q), a, b: a + len};
  if (r.k) r.k = r.k.map(v => v + a - q.a); P.cues.push(r); overwrite('cue', r); selectCue(P.cues.indexOf(r), false); save();
}
function migrateMusic() {                                         // музика з окремої доріжки (1.3) → елементи всередині кліпів
  for (const m of P.music || []) for (const c of P.clips) {
    const s = Math.max(m.a, c.a), e = Math.min(m.b, c.b); if (e - s < .2) continue;
    const r0 = toOut(c, s), r1 = toOut(c, e), n = net(c);
    const el = {...mk({type: 'music'}), path: m.path, name: m.name, dur: m.dur, vol: m.vol ?? 1, fin: m.fin || 0, fout: m.fout || 0, off: (m.off || 0) + s - m.a - r0, solo: true};
    P.elements.push(el); (c.segs ||= {})[el.id] = [[r0, r1 >= n - .05 ? 0 : r1]];
  }
  P.music = [];
}
// ── лассо: кілька кліпів і реплік разом ──
function lassoPick([ta, ay, tb, by]) {                            // що зачепила рамка (межі — час, не пікселі): кліпи — у своєму рядку, репліки — у своїх
  const {cb, cueY} = geo(), t0 = Math.min(ta, tb), t1 = Math.max(ta, tb), y0 = Math.min(ay, by), y1 = Math.max(ay, by);
  const hitT = x => x.b > t0 && x.a < t1;
  multi = new Set([...(y0 < cb && y1 > CTOP ? P.clips.filter(hitT) : []),
    ...P.cues.filter(q => { const y = cueY + rowOf(q) * CUE; return hitT(q) && y0 < y + CUE && y1 > y; })]);
  renderList();
}
function lassoDone() {                                            // одне — звичайний вибір; кілька — вибране лассо
  const [one] = multi;
  if (multi.size === 1) return P.clips.includes(one) ? (focus = 'clip', select(P.clips.indexOf(one))) : selectCue(P.cues.indexOf(one), false);
  sel = -1; selCue = -1; $('#cueEdit').classList.remove('on'); focus = multi.size ? 'multi' : focus; renderList(); renderProps();
}
function deleteMulti() {
  P.clips = P.clips.filter(c => !multi.has(c) || locked(c)); P.cues = P.cues.filter(q => !multi.has(q));
  multi.clear(); sel = -1; selCue = -1; $('#cueEdit').classList.remove('on'); renderEls(); commit();
}
function moveCues(qs, el) { for (const q of qs) q.sid = el.id; renderEls(); fitTL(); save(); }
function multiMenu() {
  const cl = P.clips.filter(c => multi.has(c)), qs = P.cues.filter(q => multi.has(q));
  return [{hd: `Вибрано: ${[cl.length && plural(cl.length, 'кліп', 'кліпи', 'кліпів'), qs.length && plural(qs.length, 'репліка', 'репліки', 'реплік')].filter(Boolean).join(', ')}`},
    ...(qs.length ? [{hd: 'Перенести репліки до спікера'}, ...subsEls().map((s, r) => ({label: subName(s, r), on: qs.every(q => cueOwner(q) === s), run: () => moveCues(qs, s)})),
      {label: 'Новий спікер', run: () => { const from = cueOwner(qs[0]) || ensureSubs(); if (!from.name) from.name = tr('Спікер 1'); moveCues(qs, addSubsEl(P.elements, '', from)); }}, '-'] : []),
    ...(cl.length ? [{label: cl.every(c => c.on) ? 'Не рендерити ці кліпи' : 'Рендерити ці кліпи', run: () => { const v = !cl.every(c => c.on); cl.forEach(c => c.on = v); commit(); }},
      {row: CLIP_COLORS.map(([col, title]) => ({sw: col, title, on: cl.every(c => (c.col || null) === col), run: () => { cl.forEach(c => c.col = col || undefined); commit(); }}))}, '-'] : []),
    {label: 'Видалити вибране', key: 'Del', run: deleteMulti}];
}
function moveCue(q, el) { q.sid = el.id; selectCue(P.cues.indexOf(q), false); renderEls(); fitTL(); drawTL(); save(); }
function cueMenu(j, t) {
  const q = P.cues[j], nx = P.cues.slice(j + 1).find(c => rowOf(c) === rowOf(q)); selectCue(j, false);
  return [{hd: 'Репліка'},
    {label: 'Глобальний', key: q.own ? 'G' : '✓ G', on: !q.own, run: () => setCueGlobal(q, !!q.own)},
    {label: 'Редагувати текст', key: 'Enter', run: () => { editCueText(); }},
    {label: 'Програти репліку', key: 'Shift+Space', run: () => { seek(q.a); stopAt = q.b; vid.play(); }},
    {label: 'Дублювати після неї', key: 'Ctrl+D', run: () => dupCue(q)},
    {label: 'Розділити тут', key: 'B', off: wordsOf(q).length < 2 || t <= q.a + .1 || t >= q.b - .1, run: () => splitCue(q, t)},
    {label: 'Об\'єднати з наступною', key: 'J', off: !nx, run: () => mergeCues(q, nx)},
    '-',
    ...subsEls().map((x, i) => x !== cueOwner(q) && {label: `Перенести до: ${subName(x, i)}`, run: () => moveCue(q, x)}),
    {label: 'Перенести до нового спікера', run: () => { const from = cueOwner(q) || ensureSubs(); if (!from.name) from.name = tr('Спікер 1'); moveCue(q, addSubsEl(P.elements, '', from)); }},
    '-',
    {label: 'Копіювати', key: 'Ctrl+C', run: copySel},
    {label: 'Видалити репліку', key: 'Del', run: () => $('#cueDel').click()}];
}

// ── меню порожнього місця таймлайна й області аналізу ──
const setRegion = r => { P.region = r; save(); };
function regionItems(t) {
  const [a, b] = region(), g = Math.min(10, dur);
  return ['-', {hd: 'Область аналізу'},
    t != null && {label: 'Почати область тут', key: 'I', off: t > b - g, run: () => setRegion([t, b])},
    t != null && {label: 'Закінчити область тут', key: 'O', off: t < a + g, run: () => setRegion([a, t])},
    {label: 'Знайти моменти', off: $('#reanalyze').disabled, run: () => analyze(true)},
    {label: 'Згенерувати субтитри', off: $('#mkSubs').disabled, run: makeSubs},
    {label: 'Показати всю область', run: () => $('#toRegion').click()},
    {label: 'Показати все відео', run: () => { view = {t0: 0, t1: dur}; clampView(); }}];
}
function laneMenu(t, inCues, sp) {
  const kind = clipboard?.kind, canPaste = inCues ? kind === 'cue' : kind === 'clip';
  return [inCues ? {label: 'Нова репліка тут', run: () => addCue(t, sp)} : {label: 'Новий кліп тут', key: 'N', run: () => addAt(t)},
    canPaste && {label: 'Вставити тут', key: 'Ctrl+V', run: () => paste(t)},
    {label: 'Перемотати сюди', run: () => seek(t)},
    ...regionItems(t)];
}

// ── меню елемента (прев'ю, список шарів, смужка в кліпі) ──
const ALIGN = {l: () => ({x: 0}), ch: r => ({x: (CW() - r.w) / 2}), r: r => ({x: CW() - r.w}),
               t: () => ({y: 0}), cv: r => ({y: (CH() - r.h) / 2}), b: r => ({y: CH() - r.h})};
const ALIGN_ROW = [['l', '⇤', 'Ліворуч'], ['ch', '↔', 'По центру горизонтально'], ['r', '⇥', 'Праворуч'], ['t', '⤒', 'Згори'], ['cv', '↕', 'По центру вертикально'], ['b', '⤓', 'Знизу']];
const shownEl = el => { const g = elById(el.id); return g ? effEl(g, pvClip()) : el; };   // вирівнюємо те, що видно на прев'ю
function alignEl(el, how) { el = shownEl(el); const p = ALIGN[how](rectOf(el)); for (const k in p) el[k] = Math.round(p[k]); save(); }
const pickEl = el => { selEl = el.id; selOwn = null; focus = 'el'; renderEls(); };
function timingItems(el, t, where) {                              // з якого й до якого моменту кліпу видно елемент
  const c = P.clips.length ? ctxClip() : null; if (!c || ['subs', 'bg'].includes(el.type)) return [];
  if (el.solo && !c.segs?.[el.id]) return ['-', {label: `Додати в кліп #${P.clips.indexOf(c) + 1}`, run: () => addToClip(el, c)}, {label: 'Додати в усі кліпи', run: () => setEverywhere(el, true)}];
  const rel = toOut(c, clamp(t, c.a, c.b)), n = net(c), done = () => { save(); renderProps(); };
  const own = !!c.segs?.[el.id];
  return ['-', {hd: 'Коли видно'},
    {label: `Показувати ${where}`, key: 'Q', off: rel >= n - .2, run: () => showFrom(el, c, rel)},
    {label: `Ховати ${where}`, key: 'W', off: rel <= (own ? 0 : el.from || 0) + .2, run: () => hideFrom(el, c, rel)},
    {label: 'Видно весь кліп', off: !own && !el.from && !el.to, run: () => { if (own) c.segs[el.id] = [[0, 0]]; else el.from = el.to = 0; done(); }}];
}
function layerItems(el) {
  const i = P.elements.indexOf(el), last = P.elements.length - 1;
  return ['-', {hd: 'Шар'},
    {label: 'На передній план', key: 'Shift+]', off: i === last, run: () => moveEl(el, 'top')},
    {label: 'Вище', key: ']', off: i === last, run: () => moveEl(el, 'up')},
    {label: 'Нижче', key: '[', off: i === 0, run: () => moveEl(el, 'down')},
    {label: 'На задній план', key: 'Shift+[', off: i === 0, run: () => moveEl(el, 'bottom')}];
}
function segItems(e, c, t, k) {                                  // сховати, розрізати, повернути спільне — лише в цьому кліпі
  const rel = toOut(c, clamp(t, c.a, c.b)), segs = segsOf(c, e), own = !!c.segs?.[e.id], x = segs[k], n = net(c);
  const done = () => { if (c.segs?.[e.id]) tidySegs(c, e); save(); renderProps(); };
  return [{hd: 'У цьому кліпі'},
    x && {label: 'Розрізати тут', key: 'B', off: rel <= (x[0] || 0) + .2 || rel >= (x[1] || n) - .2,
          run: () => { const y = ownSegs(c, e)[k], end = y[1]; y[1] = rel; c.segs[e.id].push([rel, end]); done(); }},
    x && segs.length > 1 && {label: 'Прибрати цей шматок', key: 'Del', run: () => removeFromClip(e, c, k)},
    e.type === 'music' && {label: 'З початку треку', off: (e.off || 0) === -(segs[0]?.[0] || 0), run: () => { e.off = -(segs[0]?.[0] || 0); done(); }},
    segs.length ? {label: e.solo ? 'Прибрати з цього кліпу' : 'Сховати в цьому кліпі', key: segs.length > 1 ? '' : 'Del', run: () => removeFromClip(e, c)}
      : {label: 'Показати в цьому кліпі', run: () => { c.segs[e.id] = [[0, 0]]; done(); }},
    !e.solo && own && {label: 'Як у всіх кліпах', run: () => { delete c.segs[e.id]; done(); }},
    !e.solo && own && segs.length === 1 && {label: 'Так у всіх кліпах', run: () => { [e.from, e.to] = segs[0]; for (const o of P.clips) if (o.segs) delete o.segs[e.id]; done(); }},
    {label: e.solo ? 'Додати в усі кліпи' : 'Не додавати в нові кліпи', run: () => setEverywhere(e, !!e.solo)},
    '-'];
}
function elMenu(el, t = vid.currentTime, where = 'з поточного кадру') {
  el = elById(el.id) || el; pickEl(el); const isSrc = el.type === 'video' || el.type === 'cam', c = elClip();
  if (c && ownOf(c, el)) selOwn = ownOf(c, el);
  return [{hd: TYPES[el.type].name},
    c && canOwn(el) && inClip(c, el) && {label: 'Глобальний', key: ownOf(c, el) ? 'G' : '✓ G', on: !ownOf(c, el), run: () => setGlobalIn(el, c, !!ownOf(c, el))},
    !['bg', 'progress', 'music'].includes(el.type) && {row: ALIGN_ROW.map(([k, ic, title]) => ({ic, title, run: () => alignEl(el, k)}))},
    ['video', 'cam', 'subs', 'image'].includes(el.type) && {label: 'На всю ширину', run: () => { const v = shownEl(el); v.x = 0; v.w = CW(); save(); }},
    isSrc && {label: 'Кадрувати джерело', run: () => setMode('src')},
    el.type === 'cam' && {label: 'Знайти вебкамеру автоматично', run: () => detectCam(el)},
    ...timingItems(el, t, where), ...(el.type === 'music' ? [] : layerItems(el)), '-',
    {label: el.on ? 'Сховати скрізь' : 'Показати', key: 'H', run: () => { el.on = !el.on; renderEls(); save(); }},
    {label: 'Копіювати', key: 'Ctrl+C', run: copySel},
    {label: 'Дублювати', key: 'Ctrl+D', off: SINGLE.includes(el.type), run: duplicate},
    where !== 'звідси' && elClip() && inClip(elClip(), el) && segsOf(elClip(), el).length > 0 && !['subs', 'bg'].includes(el.type) &&
      {label: `${el.solo ? 'Прибрати з кліпу' : 'Сховати в кліпі'} #${P.clips.indexOf(elClip()) + 1}`, key: 'Del', run: () => removeFromClip(el)},
    {label: 'Видалити елемент повністю', key: 'Ctrl+Del', run: () => deleteEl(el)}];
}
function stageMenu() {                                            // клік повз елементи на прев'ю шорту
  return [{label: 'Додати елемент…', run: () => togglePop('#cat', {stopPropagation() {}})},
    clipboard?.kind === 'el' && {label: 'Вставити елемент', key: 'Ctrl+V', run: () => paste()},
    {label: 'Авто-розкладка', run: () => { arrange(); save(); }},
    {label: 'Кадрування джерела', run: () => setMode('src')},
    {row: CANVAS_RATIOS().map(([r, l]) => ({ic: l, title: `Полотно ${l}`, on: Math.abs(r - CW() / CH()) < .01, run: () => setCanvas(r)}))},
    els().some(e => !e.on) && {label: 'Показати всі сховані', run: () => { els().forEach(e => e.on = true); renderEls(); save(); }}];
}
function cropMenu(el) {
  if (!el) return [{label: 'Назад до шорту', run: () => setMode('short')}];
  pickEl(el);
  return [{hd: `${TYPES[el.type].name} · кадрування`},
    {row: RATIOS.map(([r, l]) => ({ic: l, title: r ? `Пропорції ${l}` : 'Вільні пропорції', on: (el.ratio || 0) === r, run: () => applyRatio(el, r)}))},
    {label: 'Увесь кадр', run: () => cropAction(el, 'full')},
    {label: 'По центру кадру', run: () => cropAction(el, 'c')},
    {label: 'По центру горизонтально', run: () => cropAction(el, 'cx')},
    {label: 'По центру вертикально', run: () => cropAction(el, 'cy')},
    el.type === 'cam' && {label: 'Знайти вебкамеру автоматично', run: () => detectCam(el)},
    '-', {label: 'Назад до шорту', run: () => setMode('short')}];
}
pv.oncontextmenu = e => {
  e.preventDefault(); if (!P) return; const p = pvPoint(e);
  if (mode === 'short') { const h = elAt(toShort(p)); return openMenu(e, h?.cue ? cueMenu(P.cues.indexOf(h.cue), vid.currentTime) : h ? elMenu(h.el) : stageMenu()); }
  openMenu(e, cropMenu(cropHit(p).el));
};
$('#els').oncontextmenu = e => { const r = e.target.closest('.el'); if (r) openMenu(e, elMenu(elById(r.dataset.id))); };
$('#list').oncontextmenu = e => { const r = e.target.closest('.clip'); if (r && !e.target.matches('input')) openMenu(e, multi.has(P.clips[+r.dataset.i]) ? multiMenu() : clipMenu(+r.dataset.i, vid.currentTime, 'на курсорі')); };
$('#rbar').oncontextmenu = e => { if (P && dur && e.target.closest('#rband,#ract') && !e.target.matches('input')) openMenu(e, regionItems(clamp(Tt(barX(e)), 0, dur))); };
