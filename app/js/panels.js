// Панелі: налаштування пошуку й рендеру, контроли, шари й властивості вибраного елемента, картинки елементів.
// ── як шукати моменти — на плашці області; якість — біля рендеру ──
function renderPops() {
  $('#rPop').innerHTML = control(cfg, 'quality', 'seg', 'Якість', [[26, 'Швидко'], [21, 'Добре'], [17, 'Найкраще']]) +
    control(cfg, 'encoder', 'seg', 'Кодування', [['auto', 'Авто'], ['nvenc', 'NVIDIA'], ['amf', 'AMD'], ['qsv', 'Intel'], ['cpu', 'Процесор']]);
  $('#sPop').innerHTML = control(cfg, 'stt_lang', 'seg', 'Мова мовлення', [['', 'Авто'], ['uk', 'Укр'], ['en', 'Англ']]) +
    control(cfg, 'sub_words', 'seg', 'Слів на екрані', [[1, '1'], [2, '2'], [3, '3'], [4, '4']]) +
    control(cfg, 'stt_model', 'seg', 'Модель розпізнавання', [['large-v3-turbo', 'Швидка'], ['large-v3', 'Точна']]);
  $$('[data-c]').forEach(el => { if (document.activeElement !== el) el.type === 'checkbox' ? el.checked = !!cfg[el.dataset.c] : el.value = cfg[el.dataset.c]; });
}
for (const id of ['#rPop', '#sPop']) { $(id).addEventListener('input', e => setCfg(e.target)); $(id).addEventListener('click', e => { if (e.target.dataset.v != null) setCfg(e.target); }); }
$$('[data-c]').forEach(el => el.addEventListener('change', async () => {
  const k = el.dataset.c; cfg[k] = el.type === 'checkbox' ? el.checked : clamp(+el.value || 0, +el.min, +el.max);
  if (k === 'min_len' && cfg.max_len < cfg[k]) cfg.max_len = cfg[k]; if (k === 'max_len' && cfg.min_len > cfg[k]) cfg.min_len = cfg[k];
  cfg = await api('/api/config', {n_clips: cfg.n_clips, min_len: cfg.min_len, max_len: cfg.max_len, stt: cfg.stt}); renderPops();
}));
async function setCfg(t) {
  const k = t.closest('[data-p]')?.dataset.p; if (!k) return;
  const v = readControl(t, cfg[k]); if (v === undefined) return;
  cfg[k] = v; if (k === 'min_len' && cfg.max_len < v) cfg.max_len = v; if (k === 'max_len' && cfg.min_len > v) cfg.min_len = v;
  if (t.dataset.v != null) renderPops();
  cfg = await api('/api/config', {n_clips: cfg.n_clips, min_len: cfg.min_len, max_len: cfg.max_len, stt: cfg.stt, quality: cfg.quality, encoder: cfg.encoder, stt_model: cfg.stt_model, stt_lang: cfg.stt_lang, sub_words: cfg.sub_words});
}
$('#rSet').onclick = e => togglePop('#rPop', e);
$('#sSet').onclick = e => togglePop('#sPop', e);
$('#aSet').onclick = e => togglePop('#aPop', e);

// ── контроли: повзунок, перемикач, вибір, кольори, файл ──
function control(o, k, kind, label, opt) {
  const v = o[k] ?? '';
  if (kind === 'button') return `<button class="wide" data-act="${k}" style="margin-top:12px">${label}</button>`;
  if (kind === 'toggle') return `<label class="tg" data-p="${k}">${label}<input type="checkbox" ${v ? 'checked' : ''}><i></i></label>`;
  let c;
  if (kind === 'range') {
    const [min, max, st, unit, mul = 1] = opt;
    c = `<div class="rng"><input type="range" min="${min}" max="${max}" step="${st}" value="${Math.round(v * mul)}" data-mul="${mul}" data-unit="${unit}"><output>${Math.round(v * mul)} ${unit}</output></div>`;
  } else if (kind === 'seg') c = `<div class="seg">${opt.map(([o2, l]) => `<button data-v="${o2}" class="${String(v) === String(o2) ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  else if (kind === 'color') c = `<div class="sw">${COLORS.map(x => `<button data-v="${x}" style="background:${x}" class="${v === x ? 'on' : ''}" aria-label="${x}"></button>`).join('')}<input type="color" value="${esc(v || '#ffffff')}" aria-label="Свій колір"></div>`;
  else if (kind === 'file') c = `<div class="pick">${v ? `<img src="${fileUrl(v)}" alt="">` : ''}<span>${esc(v.split(/[\\/]/).pop()) || 'не обрано'}</span><button data-file="${k}">Обрати</button>${v ? `<button class="ghost" data-clear="${k}" aria-label="Прибрати">✕</button>` : ''}</div>`;
  else if (kind === 'area') c = `<textarea>${esc(v)}</textarea>`;
  else if (kind === 'audio') c = `<div class="pick"><span>♪ ${esc(o.name || 'не обрано')}</span><button data-audio="1">Інший трек</button></div>`;
  else c = `<input value="${esc(v)}" ${kind === 'font' ? 'list="fontlist" placeholder="Системний"' : ''}>`;
  return `<div data-p="${k}" data-kind="${kind}"><label>${label}</label>${c}</div>`;
}
function readControl(t, cur) {                                    // значення з контролу, або undefined
  const box = t.closest('[data-p]');
  if (t.dataset.v != null) return typeof cur === 'number' ? +t.dataset.v : t.dataset.v;
  if (box.classList.contains('tg')) return t.checked;
  if (t.type === 'range') { box.querySelector('output').textContent = t.value + ' ' + t.dataset.unit; return t.value / t.dataset.mul; }
  if (t.matches('input,textarea')) return t.value;
}

// ── шари й налаштування вибраного ──
let listClip = null, dragEl = null, dropAt = null, multi = new Set();   // multi — вибране лассо: кліпи й репліки
const fullSeg = (el, c) => { const left = el.type === 'music' ? (el.dur || 1e9) - (el.off || 0) : 1e9; return [[0, left < net(c) - .05 ? Math.max(.2, left) : 0]]; };
let impProjects = [];
async function openImport() {
  impProjects = (await api('/api/projects')).filter(x => x.id !== P.id && x.elements?.length);
  if (!impProjects.length) return msg('Немає інших проєктів з елементами', 1);
  $('#impProj').innerHTML = impProjects.map(x => `<option value="${x.id}">${esc(x.name || videoName(x.video) || 'Без назви')}</option>`).join('');
  renderImport(); $('#imp').classList.add('on');
}
function renderImport() {
  const pr = impProjects.find(x => x.id === $('#impProj').value), row = (e, i) => {
    const Ty = TYPES[e.type], note = e.type === 'subs' ? subName(e, subsEls(pr.elements).indexOf(e)) : e.title || e.text || e.channel || e.name || e.handle || '';
    return `<label><input type="checkbox" data-i="${i}" ${e.type === 'video' ? '' : 'checked'}><span class="ic" style="background:${Ty.col}">${Ty.ic}</span><span class="nm">${Ty.name}${note ? `<small>${esc(note)}</small>` : ''}</span></label>`;
  };
  const list = pr.elements.map((e, i) => [e, i]).reverse(), main = list.filter(([e]) => e.type !== 'subs'), subs = list.filter(([e]) => e.type === 'subs');
  $('#impList').innerHTML = (main.length ? `<h4>Елементи</h4>${main.map(([e, i]) => row(e, i)).join('')}` : '') +
    (subs.length ? `<h4>Доріжки субтитрів</h4>${subs.map(([e, i]) => row(e, i)).join('')}` : '');
}
function importEls(src, from = BASE) {                            // копії з новими id; «лише в кліпах» — у вибраний кліп; доріжки субтитрів — без реплік
  const c = P.clips.length ? ctxClip() : null;
  for (const e of src) {
    const el = {...structuredClone(e), id: uid()}; remap(el, from, [CW(), CH()]);
    if (SINGLE.includes(el.type)) { const i = P.elements.findIndex(x => x.type === el.type); if (i >= 0) { P.elements[i] = {...el, id: P.elements[i].id}; continue; } }
    if (el.solo) { if (c) (c.segs ||= {})[el.id] = fullSeg(el, c); else el.solo = false; }
    if (el.type === 'bg') P.elements.unshift(el); else P.elements.push(el);
  }
  arts.clear(); renderEls(); save(true); msg(`Імпортовано: ${src.length}`);
}
$('#impProj').onchange = renderImport;
$('#impCancel').onclick = () => $('#imp').classList.remove('on');
$('#imp').onclick = e => { if (e.target.id === 'imp') $('#imp').classList.remove('on'); };
$('#impGo').onclick = () => {
  const pr = impProjects.find(x => x.id === $('#impProj').value);
  const pick = [...$$('#impList input:checked')].map(b => pr.elements[+b.dataset.i]).sort((a, b) => pr.elements.indexOf(a) - pr.elements.indexOf(b));
  $('#imp').classList.remove('on'); if (pick.length) importEls(pick, pr.canvas);
};
addEventListener('keydown', e => { if (e.key === 'Escape' && $('#imp').classList.contains('on')) { $('#imp').classList.remove('on'); e.stopImmediatePropagation(); } }, true);
function addToClip(el, c) {                                        // елемент зі списку покласти на кліп
  const cur = c.segs?.[el.id];
  if (el.solo ? !cur?.length : cur && !cur.length) (c.segs ||= {})[el.id] = fullSeg(el, c);
  sel = P.clips.indexOf(c); selEl = el.id; focus = 'el'; renderList(); renderEls(); save(); msg(`${TYPES[el.type].name}: додано в кліп #${sel + 1}`);
}
const cueLabel = q => { const t = q.text.trim(); return `«${t.length > 22 ? t.slice(0, 21) + '…' : t}»`; };
function kidsOf(e) {                                              // не глобальні екземпляри елемента: [{o, c | q, label}]
  if (e.type === 'subs') return P.cues.filter(q => q.own && cueOwner(q) === e).map(q => ({o: q.own, q, label: cueLabel(q)}));
  return P.clips.flatMap((c, i) => c.own?.[e.id] ? [{o: c.own[e.id], c, label: `Кліп #${i + 1}`}] : []);
}
let kidRows = [];
const ICON_LINK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>';
const ICON_UNLINK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M15.5 13.5l3.2-3.2a4 4 0 0 0-5.7-5.7l-1.5 1.5M8.5 10.5l-3.2 3.2a4 4 0 0 0 5.7 5.7l1.5-1.5M4 4l3 3M20 20l-3-3"/></svg>';
function renderEls() {
  const cc = P?.clips.length ? ctxClip() : null; listClip = cc; kidRows = [];
  if (selOwn && !(elById(selEl) && kidsOf(elById(selEl)).some(k => k.o === selOwn))) selOwn = null;   // екземпляр уже повернули до глобального
  const row = e => {
    const Ty = TYPES[e.type], note = e.type === 'fx' ? tr(fxName(e)) : e.title || e.text || e.channel || e.name || e.handle || '', lane = !['subs', 'bg'].includes(e.type);
    const has = c => inClip(c, e) && segsOf(c, e).length > 0, here = !cc || has(cc), where = lane && !here ? 'не в цьому кліпі' : '';
    const dh = lane && P.clips.some(c => !has(c)) ? `<em class="dh">${here ? 'тягни на інші кліпи' : 'тягни на кліп'}</em>` : '';   // лише під курсором
    return `<div class="el ${e.id === selEl && !selOwn ? 'sel' : ''} ${e.on ? '' : 'off'} ${lane && !here ? 'away' : ''}" data-id="${e.id}" draggable="${lane}"><span class="ic" style="background:${Ty.col}">${Ty.ic}</span>
      <span class="nm">${Ty.name}${where ? `<em class="${dh ? 'dn' : ''}">${where}</em>` : ''}${dh}${note ? `<small>${esc(note)}</small>` : ''}</span>
      <span class="tl">${canOwn(e) && cc && here ? `<button data-a="link" class="lnk ${ownOf(cc, e) ? 'own' : ''}" title="${ownOf(cc, e) ? 'Свій у цьому кліпі · G' : 'Глобальний · G'}" aria-label="Глобальний">${ownOf(cc, e) ? ICON_UNLINK : ICON_LINK}</button>` : ''}<button data-a="eye" title="${e.on ? 'Сховати' : 'Показати'}" aria-label="Видимість">${e.on ? '◉' : '○'}</button>
      <button data-a="up" title="Вище" aria-label="Вище">↑</button><button data-a="down" title="Нижче" aria-label="Нижче">↓</button>
      <button data-a="del" title="Видалити" aria-label="Видалити">✕</button></span></div>` +
      kidsOf(e).map(k => `<div class="el kid ${k.o === selOwn ? 'sel' : ''} ${e.on ? '' : 'off'}" data-id="${e.id}" data-k="${kidRows.push({...k, e}) - 1}">
        <span class="ic">↳</span><span class="nm">${esc(k.label)}</span>
        <span class="tl"><button data-a="global" title="Зробити глобальним" aria-label="Зробити глобальним">⛓</button></span></div>`).join('');
  };
  const list = els().slice().reverse(), subs = list.filter(e => e.type === 'subs');
  $('#els').innerHTML = (list.filter(e => e.type !== 'subs').map(row).join('') || '<p class="mut" style="padding:4px 8px">Елементів немає</p>') +
    (subs.length ? `<h5 class="elgrp">Субтитри</h5>${subs.map(row).join('')}` : '');
  renderProps(); fitTL();
}
function pickKid(k) {                                             // екземпляр кліпу чи репліки: туди ж і прев'ю
  selEl = k.e.id; selOwn = k.o;
  if (k.c && clipAt(vid.currentTime) !== k.c) { sel = P.clips.indexOf(k.c); renderList(); seek(k.c.a + Math.min(.05, net(k.c) / 2)); }
  if (k.q) { selectCue(P.cues.indexOf(k.q), !(vid.currentTime >= k.q.a && vid.currentTime < k.q.b)); focus = 'el'; }
}
$('#els').onclick = e => {
  const r = e.target.closest('.el'); if (!r) return;
  const i = els().findIndex(x => x.id === r.dataset.id), el = els()[i], a = e.target.closest('[data-a]')?.dataset.a;
  if (r.dataset.k != null) {
    const k = kidRows[+r.dataset.k];
    if (a === 'global') k.q ? setCueGlobal(k.q, true) : setGlobalIn(k.e, k.c, true); else { pickKid(k); renderEls(); }
    return;
  }
  if (a === 'up' || a === 'down') return moveEl(el, a);
  if (a === 'link') return setGlobalIn(el, listClip, !!ownOf(listClip, el));
  if (a === 'eye') el.on = !el.on;
  else if (a === 'del') { if (!dropEl(el)) return; }
  else { selEl = el.id; selOwn = null; }
  renderEls(); if (a) save();
};
function dropEl(el) {                                             // false — користувач передумав
  if (el.type === 'subs') {
    const own = P.cues.filter(c => cueOwner(c) === el);
    if (own.length && !confirm(`Видалити «${subName(el, subsEls().indexOf(el))}» разом з репліками (${own.length})?`)) return false;
    const first = subsEls()[0]; P.cues = P.cues.filter(c => !own.includes(c));
    if (el === first) for (const c of P.cues) c.sid ||= cueOwner(c).id;   // репліки без позначки належали першому — тепер позначаємо явно
    selCue = -1; $('#cueEdit').classList.remove('on');
  }
  for (const c of P.clips) if (c.own?.[el.id]) { delete c.own[el.id]; if (!Object.keys(c.own).length) delete c.own; }
  P.elements = P.elements.filter(e => e !== el); if (selEl === el.id) { selEl = null; selOwn = null; } return true;
}
function moveEl(el, where) {                                      // порядок шарів: top / up / down / bottom
  const a = P.elements, i = a.indexOf(el); a.splice(i, 1);
  const j = where === 'top' ? a.length : where === 'bottom' ? 0 : clamp(i + (where === 'up' ? 1 : -1), 0, a.length);
  a.splice(j, 0, el); renderEls(); save();
}
$('#cat').innerHTML = CATALOG.map(([g, items], gi) => `<h4>${g}</h4><div class="cg">${items.map(([n, d, p], i) =>
  `<button data-g="${gi}" data-i="${i}"><i>${TYPES[p.type].ic}</i><b>${n}</b></button>`).join('')}</div>`).join('') +
  '<button class="wide" id="impOpen" style="margin-top:14px">Імпорт з іншого проєкту…</button>';
$('#addEl').onclick = e => P ? togglePop('#cat', e) : msg('Спершу відкрий або створи проєкт', 1);
$('#cat').addEventListener('click', e => { if (e.target.closest('#impOpen')) { $('#cat').classList.remove('on'); openImport(); } });
$('#cat').onclick = e => {
  const b = e.target.closest('button[data-g]'); if (!b || !P) return; $('#cat').classList.remove('on');
  const {stack, ...p} = CATALOG[b.dataset.g][1][b.dataset.i][2];
  const one = SINGLE.includes(p.type) && els().find(x => x.type === p.type);
  if (one) { selEl = one.id; return renderEls(); }
  if (p.type === 'music') return addMusicEl();
  const el = mk(p), c = P.clips.length ? ctxClip() : null; remap(el, BASE, [CW(), CH()]);
  if (c && !['subs', 'bg'].includes(p.type)) { el.solo = true; (c.segs ||= {})[el.id] = [[el.from || 0, el.to || 0]]; el.from = el.to = 0; }   // кліпів ще немає — у всіх кліпах
  if (p.type === 'fx') { placeFx(el, c); if (el.kind === 'zoom') setMode('src'); }
  else if (p.type === 'bg') P.elements.unshift(el); else P.elements.push(el); selEl = el.id;
  if (stack) arrange(); renderEls(); save();
  if (el.solo && P.clips.length > 1) msg(`${TYPES[el.type].name} — у кліпі #${P.clips.indexOf(c) + 1}. Перетягни рядок зі списку на інші кліпи, щоб додати й туди`);
};
function placeFx(el, c) {                                        // ефект — одразу над основним відео (вебка й текст лишаються як були), від курсора 1.5 с
  const v = P.elements.findIndex(e => e.type === 'video'); P.elements.splice(v + 1, 0, el);
  if (c) { const n = net(c), rel = clipAt(vid.currentTime) === c ? clamp(toOut(c, vid.currentTime), 0, Math.max(0, n - .5)) : 0; c.segs[el.id] = [[rel, rel + 1.5 < n - .05 ? rel + 1.5 : 0]]; }
  const r = fxRef(P.elements, el); if (!r) return;                 // рамка призуму: середина кадру шару, наближення 1.6×
  const [x, y, w, h] = r.src, z = 1.6; el.src = [x + w * (1 - 1 / z) / 2, y + h * (1 - 1 / z) / 2, w / z, h / z]; el.ratio = pxRatio(r.src);
}
function setEverywhere(el, on) {                                  // у всіх кліпах (і в нових) чи лише в тих, куди додано
  if (on === !el.solo) return;
  if (!on) for (const c of P.clips) {                              // стає звичайним: лишається там, де його зараз видно
    const sg = c.segs?.[el.id];
    if (!sg) (c.segs ||= {})[el.id] = [[el.from || 0, el.to || 0]]; else if (!sg.length) delete c.segs[el.id];
  }
  if (!on) el.from = el.to = 0;
  el.solo = !on; renderEls(); save();
}
const propTarget = () => selOwn || elById(selEl);                 // що редагує панель: елемент (для всіх кліпів) чи вибраний екземпляр
function renderProps() {
  const g = elById(selEl), el = propTarget(), box = $('#props');
  $('#propsBox').hidden = !el; if (!el) { box.innerHTML = ''; return; }
  const Ty = TYPES[el.type], kid = selOwn && kidsOf(g).find(k => k.o === selOwn);
  box.innerHTML = `<div class="hd"><span class="ic" style="background:${Ty.col}">${Ty.ic}</span><b>${Ty.name}</b>${kid ? `<small class="mut">${esc(kid.label)}</small>` : ''}</div>` +
    Ty.props.filter(([k, , , , cond]) => (!cond || cond(el)) && (!kid?.q || SUB_STYLE.includes(k))).map(([k, kind, label, opt]) => control(el, k, kind, label, opt)).join('');
}
$('#props').addEventListener('input', e => {
  const el = propTarget(), box = e.target.closest('[data-p]'); if (!el || !box) return;
  const k = box.dataset.p, v = readControl(e.target, el[k]); if (v === undefined) return;
  el[k] = v; afterEdit(el, k);
});
$('#props').addEventListener('click', async e => {
  const el = propTarget(); if (!el) return; const t = e.target;
  if (t.dataset.v != null && t.closest('[data-p]')) { const k = t.closest('[data-p]').dataset.p; el[k] = readControl(t, el[k]); afterEdit(el, k); return renderProps(); }
  if (t.dataset.file) { const {path} = await api('/api/pick', {kind: 'image'}); if (!path) return; el[t.dataset.file] = path; await save(true); return renderProps(); }
  if (t.dataset.clear) { el[t.dataset.clear] = ''; afterEdit(el); return renderProps(); }
  if (t.dataset.act === 'detect') detectCam(el, t);
  if (t.dataset.act === 'frame') setMode('src');
  if (t.dataset.audio) { const a = await pickAudio(); if (a) { Object.assign(el, a); renderEls(); save(); } }
});
function afterEdit(el, k) {
  if (el.type === 'progress' && k) el.y = el.pos === 'top' ? 0 : CH() - el.h;
  if (el.type === 'subs' && ['name', 'color'].includes(k)) drawTL();   // підпис і колір рядка спікера
  if (el === elById(el.id) && ['title', 'text', 'channel', 'name', 'handle'].includes(k)) { const r = $(`.el[data-id="${el.id}"] small`); if (r) r.textContent = el[k]; }
  if (['bgOn', 'karaoke', 'shape', 'style', 'bw'].includes(k)) renderProps();
  save();
}
async function camFrames(n = 8) {                                 // кадри з плеєра: запис Twitch — що вже завантажено біля курсора, файл — область аналізу
  if (!vid.videoWidth) throw new Error('відео ще не завантажилось');
  const was = vid.currentTime, playing = !vid.paused, bufs = [...Array(vid.buffered.length).keys()].map(i => [vid.buffered.start(i), vid.buffered.end(i)]);
  const [a, b] = /^https?:/.test(P.video || '') ? bufs.find(([s, e]) => was >= s - .5 && was <= e + .5) || [was, was] : region();
  const c = Object.assign(document.createElement('canvas'), {width: 640, height: Math.round(640 * vid.videoHeight / vid.videoWidth)}), x = c.getContext('2d'), shots = [];
  if (playing) vid.pause();
  try {
    for (let i = 0; i < n; i++) {
      vid.currentTime = a + (b - a) * (i + .5) / n;
      await Promise.race([new Promise(r => vid.addEventListener('seeked', r, {once: true})), new Promise(r => setTimeout(r, 3000))]);
      x.drawImage(vid, 0, 0, c.width, c.height); shots.push(c.toDataURL('image/jpeg', .85));
    }
  } finally { vid.currentTime = was; if (playing) vid.play(); }
  return shots;
}
async function detectCam(cam, btn = document.createElement('button')) {   // кадри — з плеєра, без завантажень; рядок поступу згори
  try {
    const frames = await camFrames();
    const r = await busy(btn, 'Вебкамера', [['cam', 2]], task => api('/api/detect_cam', {frames, task}), null, true);
    if (r.rect) { cam.src = r.rect; if (cam.w >= CW()) arrange(); msg('Вебкамеру знайдено'); }
    else { setMode('src'); msg('Вебкамеру не знайдено. Виділи її рамкою вручну.', 1); }
    save();
  } catch (e) { e.cancelled ? msg('Пошук вебкамери скасовано') : msg('Пошук камери: ' + e.message, 1); }
}

// ── картинки елементів малює сервер тим самим кодом, що й у відео ──
const artKey = el => JSON.stringify(el, (k, v) => ['x', 'y', 'from', 'to', 'anim', 'on', 'id'].includes(k) ? undefined : v);
function ensureArt(el) {
  const key = artKey(el), a = arts.get(aid(el));
  if (a && (a.key === key || a.pending === key)) return a.ready;
  const ready = api('/api/element', el).then(r => new Promise(ok => {
    const img = new Image(); img.onload = () => {
      const cur = arts.get(aid(el)); if (cur && cur.pending !== key) return ok();
      arts.set(aid(el), {key, img, w: r.w, h: r.h, pad: r.pad, v: el[TYPES[el.type].size[0]]});
      if (el.x == null) { el.x = Math.round((CW() - r.w) / 2); save(); } ok();
    }; img.src = r.img;
  })).catch(e => msg('Елемент: ' + e.message, 1));
  arts.set(aid(el), {...(a || {}), pending: key, ready}); return ready;
}
async function defaultElements() {                                // стартовий набір нового проєкту
  const cap = mk({type: 'text', text: 'Підпис до шорта', size: 64, color: '#111111', bg: '#ffffff', bgOn: true, y: 230});
  const socials = ['tiktok', 'youtube', 'instagram'].map(net => mk({type: 'social', net, handle: net === 'youtube' ? '@channel' : '@nickname', style: 'dark', size: 40, y: 1690}));
  P.elements = [mk({type: 'video', src: centerSrc(0.8), x: 0, y: 285, w: 1080}), cap, ...socials];
  await Promise.all([cap, ...socials].map(ensureArt));
  cap.x = Math.round((1080 - rectOf(cap).w) / 2);
  const ws = socials.map(e => rectOf(e).w), gap = 18; let x = Math.round((1080 - ws.reduce((a, b) => a + b, 0) - gap * (ws.length - 1)) / 2);
  socials.forEach((e, i) => { e.x = x; x += ws[i] + gap; });
  if (CW() !== BASE[0] || CH() !== BASE[1]) for (const e of P.elements) remap(e, BASE, [CW(), CH()]);   // заготовка 9:16 — на полотно проєкту
  renderEls(); save();
}
const oldStarter = els => els.length === 2 && els[0].type === 'video' && els[1].type === 'card' && els[1].title === 'Назва відео' && els[1].channel === 'Канал';
