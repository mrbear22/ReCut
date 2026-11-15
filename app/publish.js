// ── публікація: зліва шорти на редагуванні з рекомендованою датою, справа черга Buffer ──
// спирається на спільне з ui.html: $, $$, api, esc, fmt, fmtDur, fileUrl, clamp, projName
const PUB_SERVICES = {tiktok: {name: 'TikTok', col: '#25f4ee', ink: '#101113'}, youtube: {name: 'YouTube', col: '#ff0033', ink: '#ffffff'},
  instagram: {}, facebook: {}, threads: {}, twitter: {brand: 'x'}, linkedin: {}, bluesky: {}, mastodon: {}};   // відео-мережі Buffer; назви, кольори й логотипи — з /api/brands
const PUB_DEFAULT = ['tiktok', 'youtube'];                        // що показувати, поки Buffer не підключено   // куди вміємо слати шорти; фірмові кольори — для іконок
const PUB_FREE_QUEUE = 10;                                        // безкоштовний Buffer тримає 10 запланованих постів на канал
const PUB_SENT = ['sched', 'done'];                               // ці шорти вже не на редагуванні: вони в черзі або вийшли
const PUB_TITLE_MAX = 100;
const ICON = {
  folder: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" d="M3.5 6.5a1 1 0 0 1 1-1h4.6l2 2h8.4a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z"/></svg>',
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5.5v13l10.5-6.5z"/></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  tiktok: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14.2 3h3a4.6 4.6 0 0 0 3.8 3.9v3a7.6 7.6 0 0 1-3.8-1.1v6.4a5.8 5.8 0 1 1-5.8-5.8c.3 0 .6 0 .9.1v3.1a2.8 2.8 0 1 0 1.9 2.6z"/></svg>',
  clock: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  youtube: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.6 7.2a2.6 2.6 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4A2.6 2.6 0 0 0 2.4 7.2 27 27 0 0 0 2 12a27 27 0 0 0 .4 4.8 2.6 2.6 0 0 0 1.8 1.8C5.8 19 12 19 12 19s6.2 0 7.8-.4a2.6 2.6 0 0 0 1.8-1.8A27 27 0 0 0 22 12a27 27 0 0 0-.4-4.8zM10 15V9l5.2 3z"/></svg>',
};
const newSeed = () => 1 + Math.floor(Math.random() * 1e6);
const pub = {projects: [], pid: null, chosen: new Set(), buffer: null, busy: false, saveT: {}, sending: new Set(), seed: newSeed()};

const pubProject = () => pub.projects.find(p => p.id === pub.pid);
const pubFiles = p => {                                           // найновіший рендер кожного файлу, лише ті, що є на диску
  const seen = new Set(), out = [];
  for (const r of p.renders) for (const f of r.files) if (f.exists && !seen.has(f.path)) { seen.add(f.path); out.push(f); }
  return out.sort((x, y) => x.a - y.a);
};
const pubFile = path => pubFiles(pubProject()).find(f => f.path === path);
const pubMsg = (t, err) => { $('#pubMsg').textContent = t; $('#pubMsg').classList.toggle('err', !!err); };
const pubChannels = () => (pub.buffer?.channels || []).filter(c => PUB_SERVICES[c.service]);
const pubShown = () => { const c = [...new Set(pubChannels().map(c => c.service))]; return c.length ? c : PUB_DEFAULT; };   // лише мережі, підключені в Buffer
const pubTargets = f => f.post?.targets || pubShown();   // куди слати цей шорт; за замовчуванням — усюди
const pubTargetChannels = f => pubChannels().filter(c => pubTargets(f).includes(c.service));
const pubReady = () => !!pub.buffer?.channels && !!pub.media?.connected;   // є куди слати й де тримати відео
const pubSave = (path, post) => api('/api/post/save', {id: pub.pid, path, post});
const plural = (n, one, few, many) => {                             // 1 шорт, 2 шорти, 5 шортів, 21 шорт
  const d = n % 10, h = n % 100;
  return `${n} ${d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many}`;
};

async function loadPub(pid) {
  pub.projects = (await api('/api/projects')).filter(p => pubFiles(p).length);
  pub.pid = pid || (pub.projects.some(p => p.id === pub.pid) ? pub.pid : pub.projects[0]?.id);
  pub.chosen = new Set([...pub.chosen].filter(path => pubProject() && pubFile(path) && pubEditable(pubFile(path))));
  renderPub(); loadPubStatus();
}
async function loadBrands() {                                     // назви, кольори й логотипи мереж — один раз
  if (pub.brands) return; pub.brands = await api('/api/brands').catch(() => ({}));
  for (const [svc, s] of Object.entries(PUB_SERVICES)) {
    const b = pub.brands[s.brand || svc]; if (!b) continue;
    s.name ||= b.name; s.col ||= b.color === '#000000' ? '#e2dfda' : b.color; s.ink ||= '#ffffff';   // чорний логотип на темному тлі не видно
    ICON[svc] ||= `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${b.path}"/></svg>`;
  }
}
async function loadPubStatus() {
  await loadBrands();
  const [ai, buf, media] = await Promise.all([api('/api/ai').catch(() => ({})), api('/api/buffer').catch(e => ({connected: true, error: e.message})), api('/api/media').catch(() => ({}))]);
  pub.ai = ai.model; pub.buffer = buf; pub.media = media;
  pub.queue = buf.channels ? (await api('/api/buffer/queue').catch(() => ({posts: []}))).posts : null;
  renderPub();                                                    // черга уточнює, що на редагуванні, а що вже ні
}
const renderPub = () => { renderPubHead(); renderPubGrid(); renderPubSide(); };

// ── стан шорту: на редагуванні (зліва) чи в черзі / вже вийшов (справа) ──
const pubWhen = t => new Date(t).toLocaleString('uk-UA', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
function pubState(f) {
  const recs = Object.values(f.post?.buffer || {}), sent = recs.filter(s => s.id), bad = recs.find(s => s.error);
  if (!sent.length) return bad ? {kind: 'err', label: `Помилка: ${bad.error}`} : f.post?.title ? {kind: 'ready', label: 'Опис готовий'} : {kind: 'none', label: 'Без опису'};
  const queued = pub.queue ? sent.filter(s => pub.queue.some(q => q.id === s.id)) : sent.filter(s => new Date(s.dueAt) > Date.now());   // без зв'язку з Buffer — за часом
  const last = Math.max(...sent.map(s => +new Date(s.dueAt)));
  if (queued.length) return {kind: 'sched', label: 'У черзі', at: Math.min(...queued.map(s => +new Date(s.dueAt)))};
  if (last <= Date.now()) return {kind: 'done', label: 'Вийшов', at: last};
  return {kind: 'gone', label: 'Прибрано з черги на buffer.com'};
}
const pubEditable = f => !PUB_SENT.includes(pubState(f).kind);
const pubEditing = () => (pubProject() ? pubFiles(pubProject()) : []).filter(pubEditable);

// ── рекомендовані дати: природний розклад одразу після того, що вже в черзі Buffer ──
const PUB_FREQ = [[.5, 'Через день'], [1, '1 на день'], [2, '2 на день'], [3, '3 на день']];
const PUB_MIN_GAP = 15 * 60e3;                                    // Buffer не приймає час, що вже минув або от-от настане
const pubOpt = () => ({perDay: pub.perDay ?? 1, from: pub.from ?? 12, to: pub.to ?? 22, privacy: pub.privacy || 'public'});
const hh = h => String(h).padStart(2, '0') + ':00';
function pubQueue() {                                             // уже заплановане в TikTok і YouTube каналах Buffer
  const ids = new Set(pubChannels().map(c => c.id));
  return (pub.queue || []).filter(q => ids.has(q.channelId)).sort((x, y) => new Date(x.dueAt) - new Date(y.dueAt));
}
function pubSlots(count, after, seed, taken = []) {               // слоти рівно ділять вікно доби, хвилина в слоті випадкова
  const o = pubOpt(), span = Math.max(1, ((o.to - o.from + 24) % 24) || 24), per = Math.max(1, Math.round(o.perDay)), every = o.perDay < 1 ? 2 : 1;
  let rnd = seed; const rand = () => (rnd = (rnd * 16807) % 2147483647) / 2147483647;   // відтворюваний «випадок»: дата на картці = те, що піде в Buffer
  const out = [], day = new Date(after); day.setHours(0, 0, 0, 0);
  for (let d = 0; out.length < count && d < 3650; d += every) {
    const dd = new Date(day); dd.setDate(day.getDate() + d);
    const busy = taken.filter(x => x.toDateString() === dd.toDateString());   // що вже стоїть у черзі цього дня
    let left = per - busy.length;
    for (let i = 0; i < per && out.length < count; i++) {
      const slotH = span / per, h = o.from + slotH * (i + .15 + rand() * .7);   // не впритул до меж слоту
      const t = new Date(dd); t.setHours(0, Math.round(h * 60), 0, 0);
      const s0 = new Date(dd), s1 = new Date(dd); s0.setHours(0, Math.round((o.from + slotH * i) * 60)); s1.setHours(0, Math.round((o.from + slotH * (i + 1)) * 60));
      if (left <= 0 || busy.some(x => x >= s0 && x < s1)) continue;      // слот уже зайнятий постом із черги
      if (t - after >= PUB_MIN_GAP) { out.push(t); left--; }
    }
  }
  return out;
}
function pubDates() {                                             // path → {t, own}: дата, задана на картці, або наступний вільний слот
  const files = pubEditing(), free = files.filter(f => !f.post?.when);
  const after = new Date(Math.max(Date.now(), ...pubQueue().map(q => +new Date(q.dueAt))));
  const taken = [...new Set(pubQueue().map(q => +new Date(q.dueAt)))].map(x => new Date(x));   // один шорт у кількох мережах — один пост
  files.filter(f => f.post?.when).forEach(f => taken.push(new Date(f.post.when)));
  const slots = pubSlots(free.length, after, pub.seed, taken), out = {};
  free.forEach((f, i) => out[f.path] = {t: slots[i]});
  files.filter(f => f.post?.when).forEach(f => out[f.path] = {t: new Date(f.post.when), own: true});
  return out;
}

// ── шапка: проєкт, вибір, дії над вибраними, розклад ──
function renderPubHead() {
  $('#pubProj').innerHTML = pub.projects.map(p => `<option value="${p.id}" ${p.id === pub.pid ? 'selected' : ''}>${esc(projName(p))} · ${pubFiles(p).length}</option>`).join('');
  const edit = pubEditing(), k = pub.chosen.size;
  $('#pubAll').checked = edit.length > 0 && edit.every(f => pub.chosen.has(f.path)); $('#pubAll').indeterminate = k > 0 && !$('#pubAll').checked;
  $('#pubCount').textContent = k ? `вибрано ${k} з ${edit.length}` : `вибрати всі · ${plural(edit.length, 'шорт', 'шорти', 'шортів')}`;
  $('#pubSelNote').textContent = k ? `Вибраним (${k})` : 'Вибраним — спершу відміть шорти галочками';
  $('#pubAI').disabled = !k || pub.busy;
  $('#pubQueueSel').disabled = !k || !pubReady() || pub.sending.size > 0;
  const o = pubOpt();
  $('#pubOpt summary').textContent = `${PUB_FREQ.find(([v]) => v === o.perDay)[1]} · ${hh(o.from)}–${hh(o.to)}`;
  const hours = (id, v) => `<select id="${id}">${[...Array(24).keys()].map(h => `<option value="${h}" ${h === v ? 'selected' : ''}>${hh(h)}</option>`).join('')}</select>`;
  $('#pubOptBody').innerHTML = `<label>Як часто</label><div class="seg" id="pubFreq">${PUB_FREQ.map(([v, l]) => `<button data-v="${v}" class="${v === o.perDay ? 'on' : ''}">${l}</button>`).join('')}</div>
    <label>У який час доби</label><div class="row">${hours('pubFrom', o.from)}<span>–</span>${hours('pubTo', o.to)}</div>
    <label>Хто бачить на YouTube</label><div class="seg" id="pubPriv">${[['public', 'Усі'], ['unlisted', 'За посиланням'], ['private', 'Лише я']].map(([v, l]) =>
      `<button data-v="${v}" class="${o.privacy === v ? 'on' : ''}">${l}</button>`).join('')}</div>
`;
}
$('#pubProj').onchange = e => { pub.pid = e.target.value; pub.chosen.clear(); renderPub(); };
$('#pubAll').onchange = e => { pub.chosen = new Set(e.target.checked ? pubEditing().map(f => f.path) : []); renderPub(); };
$('#pubOpt').addEventListener('click', e => {
  const t = e.target;
  if (t.closest('#pubFreq') && t.dataset.v) pub.perDay = +t.dataset.v;
  else if (t.closest('#pubPriv') && t.dataset.v) pub.privacy = t.dataset.v;
  else return;
  renderPubHead(); renderPubGrid();
});
$('#pubOpt').addEventListener('change', e => {
  if (e.target.id !== 'pubFrom' && e.target.id !== 'pubTo') return;
  pub[e.target.id === 'pubFrom' ? 'from' : 'to'] = +e.target.value; renderPubHead(); renderPubGrid();
});
document.addEventListener('pointerdown', e => { if (!e.target.closest('#pubOpt')) $('#pubOpt').open = false; });

// ── картка шорту на редагуванні ──
function pubTargetsHtml(f) {
  const on = pubTargets(f), connected = new Set(pubChannels().map(c => c.service));
  return pubShown().map(svc => [svc, PUB_SERVICES[svc]]).map(([svc, s]) => {
    const missing = pub.buffer?.channels && !connected.has(svc);
    return `<button class="ptg ${on.includes(svc) ? 'on' : ''}" style="--svc:${s.col};--svc-ink:${s.ink}" data-a="target" data-svc="${svc}" aria-pressed="${on.includes(svc)}"
      title="${missing ? `${s.name} ще не підключено в Buffer` : `Публікувати в ${s.name}`}">${ICON[svc]}<span>${s.name}</span>${missing ? '<small>не підключено</small>' : ''}</button>`;
  }).join('');
}
// ── коли: кнопка «Завтра · 16:40»; клік — панель з днями, годинами й хвилинами, усе мишею ──
const PUB_DAYS = 14, MIN_STEP = 15;                                // днів у календарі; крок у списку часу, хв
const hhmm = d => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
const dayStart = d => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
function dayName(d) {
  const n = Math.round((dayStart(d) - dayStart(new Date())) / 864e5);
  return n === 0 ? 'Сьогодні' : n === 1 ? 'Завтра' : d.toLocaleDateString('uk-UA', {weekday: 'short', day: 'numeric', month: 'short'});
}
function pubWhenHtml(f, d) {
  const late = d && d.t - Date.now() < PUB_MIN_GAP;
  return `<button class="pwhen ${late ? 'bad' : ''} ${d?.own ? 'own' : ''}" data-a="whenpick" title="${d?.own ? 'Свій час' : 'Час за розкладом'}">
      ${ICON.clock}<span>${d ? `${dayName(d.t)} · ${hhmm(d.t)}` : 'Коли?'}</span></button>`;
}
const whenPop = Object.assign(document.createElement('div'), {id: 'whenPop', className: 'whenpop'}); document.body.append(whenPop);
let whenFor = null;                                               // path шорту, чий час зараз обираємо
function renderWhenPop() {
  const d = pubDates()[whenFor]; if (!d) return closeWhenPop();
  const t = d.t, today = dayStart(new Date()), soon = Date.now() + PUB_MIN_GAP;
  const at = (day, h, m) => { const x = new Date(day); x.setHours(h, m, 0, 0); return x; };
  const days = [...Array(PUB_DAYS).keys()].map(i => { const x = new Date(today); x.setDate(today.getDate() + i); return x; });
  const times = t => {                                            // кожні 15 хв + поточний час з розкладу (напр. 16:40)
    const ms = new Set([...Array(24 * 60 / MIN_STEP).keys()].map(i => i * MIN_STEP)); ms.add(t.getHours() * 60 + t.getMinutes());
    return [...ms].sort((x, y) => x - y).map(m => [m, at(t, 0, m)]);
  };
  whenPop.innerHTML = `<div class="wp-body"><div class="wp-days">${days.map(x => `<button data-day="${+x}" class="${+x === +dayStart(t) ? 'on' : ''} ${+x === +today ? 'today' : ''}">
        <small>${x.toLocaleDateString('uk-UA', {weekday: 'short'})}</small><b>${x.getDate()}</b></button>`).join('')}</div>
    <div class="wp-times">${times(t).map(([m, x]) => `<button data-min="${m}" class="${m === t.getHours() * 60 + t.getMinutes() ? 'on' : ''}" ${x < soon ? 'disabled' : ''}>${hhmm(x)}</button>`).join('')}</div>
    </div><div class="wp-foot">${d.own ? '<button class="ghost" data-auto>Як у розкладі</button>' : '<small>за розкладом</small>'}<span class="grow"></span><button class="pri" data-done>Готово</button></div>`;
}
const scrollTimes = () => { const on = whenPop.querySelector('.wp-times .on'); if (on) on.parentElement.scrollTop = on.offsetTop - on.parentElement.clientHeight / 2 + on.offsetHeight / 2; };
function openWhenPop(path, btn) {
  whenFor = path; renderWhenPop(); whenPop.classList.add('on'); scrollTimes();
  const r = btn.getBoundingClientRect(), w = whenPop.offsetWidth, h = whenPop.offsetHeight;
  whenPop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.right - w)) + 'px';
  whenPop.style.top = (r.bottom + 6 + h < innerHeight ? r.bottom + 6 : Math.max(8, r.top - h - 6)) + 'px';
}
function closeWhenPop() { whenFor = null; whenPop.classList.remove('on'); }
whenPop.onclick = e => {
  const b = e.target.closest('button'); if (!b || !whenFor) return;
  if (b.dataset.done != null) return closeWhenPop();
  if (b.dataset.auto != null) { pubSetPost(whenFor, {when: null}); return renderWhenPop(); }
  const t = new Date(pubDates()[whenFor].t);
  if (b.dataset.day) { const d = new Date(+b.dataset.day); t.setFullYear(d.getFullYear(), d.getMonth(), d.getDate()); }
  if (b.dataset.min) t.setHours(0, +b.dataset.min, 0, 0);
  if (t - Date.now() < PUB_MIN_GAP) t.setTime(Math.ceil((Date.now() + PUB_MIN_GAP) / (MIN_STEP * 60e3)) * MIN_STEP * 60e3);   // минуле — найближчий можливий час
  const keep = whenPop.querySelector('.wp-times')?.scrollTop;    // список часу не стрибає після кліку
  pubSetPost(whenFor, {when: t.toISOString()}); renderWhenPop();
  if (b.dataset.min) whenPop.querySelector('.wp-times').scrollTop = keep; else scrollTimes();
};
document.addEventListener('pointerdown', e => { if (whenFor && !e.target.closest('#whenPop,[data-a=whenpick]')) closeWhenPop(); });
addEventListener('keydown', e => { if (e.key === 'Escape' && whenFor) closeWhenPop(); });
function pubQueueBtn(f) {
  const sending = pub.sending.has(f.path), d = pubDates()[f.path], late = d && d.t - Date.now() < PUB_MIN_GAP;
  const why = !pub.buffer?.channels ? 'Спершу підключи Buffer праворуч' : !pub.media?.connected ? 'Сховище відео для Buffer не налаштоване в цій версії' : !pubTargetChannels(f).length ? 'Обери, куди публікувати' : late ? 'Цей час уже минув' : '';
  return `<button class="pri" data-a="queue" ${why || sending ? 'disabled' : ''} title="${esc(why)}">${sending ? 'Викладаю…' : 'Додати до черги'}</button>`;
}
function pubCard(f, i, d) {                                       // рядок списку на всю ширину: превʼю · тексти · куди й коли · дії
  const p = f.post || {}, {kind, label} = pubState(f), on = pub.chosen.has(f.path), title = p.title || '';
  return `<article class="pc ${on ? 'on' : ''} ${pub.sending.has(f.path) ? 'work' : ''}" data-path="${esc(f.path)}">
    <button class="pck" data-a="pick" aria-pressed="${on}" aria-label="Вибрати">${ICON.check}</button>
    <div class="pth" data-a="play" title="Переглянути">
      <img src="${fileUrl(f.thumb)}" alt="" loading="lazy" onerror="this.remove()"><span class="pplay">${ICON.play}</span><span class="pdur">${fmt(f.len ?? f.b - f.a)}</span>
    </div>
    <div class="pbody">
      <div class="phd"><span class="pnum">#${i + 1} · з ${fmt(f.a).replace(/\.\d$/, '')}</span><span class="pst ${kind}" title="${esc(label)}">${esc(label)}</span></div>
      <div class="prow"><input data-f="title" value="${esc(title)}" maxlength="${PUB_TITLE_MAX}" placeholder="Назва" aria-label="Назва"><em data-count>${title.length}/${PUB_TITLE_MAX}</em></div>
      <textarea data-f="description" rows="2" placeholder="Опис під відео" aria-label="Опис">${esc(p.description || '')}</textarea>
      <input data-f="hashtags" value="${esc((p.hashtags || []).map(t => '#' + t).join(' '))}" placeholder="#shorts #стрім" aria-label="Хештеги">
    </div>
    <div class="pside">
      <div class="pline"><div class="ptargets">${pubTargetsHtml(f)}</div>${pubWhenHtml(f, d)}</div>
      <div class="pacts"><button class="ghost ptxt" data-a="ai">Написати опис</button>
        <button class="picon" data-a="reveal" title="Показати у папці" aria-label="Показати у папці">${ICON.folder}</button>
        <span class="grow"></span>${pubQueueBtn(f)}</div>
    </div></article>`;
}
function renderPubGrid() {
  const p = pubProject(), all = p ? pubFiles(p) : [], dates = pubDates();
  const cards = all.map((f, i) => [f, i]).filter(([f]) => pubEditable(f));
  $('#pubGrid').innerHTML = p ? (cards.map(([f, i]) => pubCard(f, i, dates[f.path])).join('')
      || '<div class="empty">Усі шорти в черзі або вже вийшли</div>')
    : '<div class="empty">Готових шортів ще немає</div>';
}
function pubToggle(path) {
  pub.chosen.has(path) ? pub.chosen.delete(path) : pub.chosen.add(path);
  const card = $(`.pc[data-path="${CSS.escape(path)}"]`), on = pub.chosen.has(path);
  card?.classList.toggle('on', on); card?.querySelector('.pck').setAttribute('aria-pressed', on);
  renderPubHead();
}
function pubSetPost(path, post) {                                 // зберегти й перемалювати: дати інших карток могли зсунутись
  const f = pubFile(path); f.post = {...f.post, ...post}; pubSave(path, post); renderPubGrid(); renderPubHead();
}
$('#pubGrid').onclick = e => {
  const card = e.target.closest('.pc'), btn = e.target.closest('[data-a]'); if (!card || !btn) return;
  const path = card.dataset.path, a = btn.dataset.a, f = pubFile(path);
  if (a === 'whenpick') return whenFor === path ? closeWhenPop() : openWhenPop(path, btn);
  if (a === 'play') { $('#mv').src = fileUrl(path); $('#mv').dataset.path = path; $('#modal').classList.add('on'); return $('#mv').play(); }
  if (a === 'reveal') return api('/api/reveal', {path});
  if (a === 'ai') return captionMany([path]);
  if (a === 'auto') return pubSetPost(path, {when: null});
  if (a === 'queue') return pubEnqueue([path]);
  if (a === 'target') { const cur = pubTargets(f), s = btn.dataset.svc; return pubSetPost(path, {targets: cur.includes(s) ? cur.filter(x => x !== s) : [...cur, s]}); }
  pubToggle(path);
};
const parseTags = s => [...new Set(s.split(/[\s,]+/).map(t => t.replace(/^#+/, '').toLowerCase()).filter(Boolean))];
$('#pubGrid').oninput = e => {
  const card = e.target.closest('.pc'), k = e.target.dataset.f; if (!card || !k) return;
  const f = pubFile(card.dataset.path); f.post ||= {};
  f.post[k] = k === 'hashtags' ? parseTags(e.target.value) : e.target.value;
  if (k === 'title') card.querySelector('[data-count]').textContent = `${e.target.value.length}/${PUB_TITLE_MAX}`;
  clearTimeout(pub.saveT[f.path]);
  pub.saveT[f.path] = setTimeout(() => pubSave(f.path, {[k]: f.post[k]}), 500);
};

// ── у чергу і назад ──
async function pubEnqueue(paths) {
  const dates = pubDates();
  const plan = paths.map(pubFile).filter(f => f && pubTargetChannels(f).length && dates[f.path]?.t - Date.now() >= PUB_MIN_GAP)
    .map(f => ({path: f.path, title: f.post?.title, dueAt: dates[f.path].t.toISOString(), channels: pubTargetChannels(f).map(c => c.id)}));
  if (!plan.length) return pubMsg('Перевір соцмережі й дату на картках', 1);
  const untitled = plan.filter(x => !x.title).length;
  if (untitled && !confirm(`${plural(untitled, 'шорт', 'шорти', 'шортів')} без назви. Додати до черги як є?`)) return;
  plan.forEach(x => pub.sending.add(x.path)); renderPubGrid(); renderPubHead();
  pubMsg('');
  try {
    const r = await busy($('#pubQueueSel'), 'Відео в чергу', [['upload', 20 * plan.length]],
      task => api('/api/publish', {id: pub.pid, privacy: pubOpt().privacy, plan: plan.map(({path, dueAt, channels}) => ({path, dueAt, channels})), task}));
    pubMsg(r.errors ? `У черзі ${r.ok}, помилок ${r.errors}: ${r.first_error}` : `Додано до черги: ${plural(r.ok, 'пост', 'пости', 'постів')}.`, !!r.errors);
  } catch (e) { pubMsg(e.message, 1); }
  plan.forEach(x => { pub.sending.delete(x.path); pub.chosen.delete(x.path); });
  pub.seed = newSeed();
  await loadPub(pub.pid);
}
$('#pubQueueSel').onclick = () => pubEnqueue([...pub.chosen]);
async function pubUnqueue(pid, path) {
  pubMsg('Прибираю з черги Buffer…');
  try { await api('/api/post/unqueue', {id: pid, path}); pubMsg('Шорт знову на редагуванні.'); } catch (e) { pubMsg(e.message, 1); }
  await loadPub(pub.pid);
}

// ── локальний ШІ: перший раз програма сама завантажує його в data ──
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function ensureAI() {
  const info = await api('/api/ai').catch(() => ({}));
  if (info.model) { pub.ai = info.model; return true; }
  if (!info.can_setup) return false;
  if (!info.setup?.running && !confirm(`Для описів потрібен локальний ШІ (${info.size_gb} ГБ). Завантажити?`)) return false;
  await api('/api/ai/setup', {});
  for (;;) {
    await sleep(1500);
    const [st, ai] = await Promise.all([api('/api/status').catch(() => ({})), api('/api/ai').catch(() => ({}))]);
    if (ai.model) { pub.ai = ai.model; return true; }
    if (ai.setup?.err) { pubMsg('ШІ: ' + ai.setup.err, 1); return false; }
    const b = st.tasks?.ai || {};
    pubMsg(`${b.text || 'Готую локальний ШІ…'}${b.frac != null ? ` · ${Math.round(b.frac * 100)}%` : ''}${b.eta ? ` · ще ~${fmtDur(b.eta)}` : ''}`);
  }
}
async function captionMany(paths) {                              // по одному, щоб було видно поступ
  if (pub.busy) return; pub.busy = true; renderPubHead();
  const hasAI = pub.ai || await ensureAI(); let done = 0, failed = 0;
  for (const path of paths) {
    $(`.pc[data-path="${CSS.escape(path)}"]`)?.classList.add('work');
    pubMsg(`${hasAI ? 'ШІ пише описи' : 'Заготовки назв'}… ${done + 1} з ${paths.length}`);
    try {
      const c = await api('/api/caption', {id: pub.pid, path}), f = pubFile(path), post = {title: c.title, description: c.description, hashtags: c.hashtags};
      f.post = {...f.post, ...post}; await pubSave(path, post);
    } catch (e) { failed++; pubMsg('ШІ: ' + e.message, 1); }
    done++;
  }
  pub.busy = false; renderPubGrid(); renderPubHead();
  if (!failed) pubMsg(hasAI ? `Описів готово: ${done}` : 'ШІ недоступний: лише заготовки назв');
}
$('#pubAI').onclick = () => captionMany([...pub.chosen]);

// ── права панель: черга Buffer по днях і те, що вже вийшло ──
function pubOwnPosts() {                                          // id поста Buffer → шорт з будь-якого проєкту
  const own = {};
  for (const p of pub.projects) for (const f of pubFiles(p)) for (const rec of Object.values(f.post?.buffer || {})) if (rec.id) own[rec.id] = {pid: p.id, f};
  return own;
}
function pubConnectHtml() {
  const b = pub.buffer;
  if (!b) return '<p class="mut">Перевіряю Buffer…</p>';
  if (!b.connected) return `<label>Ключ Buffer API</label><div class="row"><input id="pubKey" type="password" autocomplete="off" placeholder="Встав ключ сюди">
      <button id="pubKeySave" class="pri">Підключити</button></div>
    <p class="mut small">Buffer → Settings → API → Generate API Key</p>`;
  if (b.error) return `<p class="err">${esc(b.error)}</p><div class="row"><button id="pubRefresh" class="ghost">Спробувати ще</button><button id="pubKeyDrop" class="ghost">Відключити Buffer</button></div>`;
  return '';
}
function pubQueueHtml() {
  const fmtDay = d => d.toLocaleDateString('uk-UA', {weekday: 'short', day: 'numeric', month: 'short'});
  const fmtT = d => d.toLocaleTimeString('uk-UA', {hour: '2-digit', minute: '2-digit'});
  const own = pubOwnPosts(), svc = id => pubChannels().find(c => c.id === id)?.service, rows = [], byShort = {};
  for (const q of pubQueue()) {                                   // один шорт у кількох мережах — один рядок
    const o = own[q.id], t = new Date(q.dueAt);
    if (!o) { rows.push({t, text: q.text, svcs: [svc(q.channelId)]}); continue; }
    const r = byShort[o.f.path] ||= rows[rows.push({t, own: o, svcs: []}) - 1];
    r.svcs.push(svc(q.channelId)); if (t < r.t) r.t = t;
  }
  rows.sort((x, y) => x.t - y.t);
  if (!rows.length) return '<p class="mut small">Черга порожня</p>';
  let last = '';
  return rows.map(r => {
    const d = fmtDay(r.t), head = d !== last ? `<div class="pday">${d}</div>` : ''; last = d;
    const icons = [...new Set(r.svcs.filter(Boolean))].map(s => `<i style="--svc:${PUB_SERVICES[s].col}" title="${PUB_SERVICES[s].name}">${ICON[s]}</i>`).join('');
    const title = r.own ? (r.own.f.post?.title || 'без назви') : (r.text || '').split(/\r?\n/)[0] || 'пост не з ShortsMaker';
    return head + `<div class="pq ${r.own ? 'own' : 'ext'}">
      ${r.own ? `<img src="${fileUrl(r.own.f.thumb)}" alt="">` : '<span class="pqx"></span>'}
      <div class="pqb"><div class="pqh"><b>${fmtT(r.t)}</b>${icons}</div><span class="pqt" title="${esc(title)}">${esc(title)}</span>
        ${r.own ? `<button class="ghost ptxt" data-unq="${esc(r.own.f.path)}" data-pid="${r.own.pid}">Повернути до редагування</button>` : ''}</div></div>`;
  }).join('');
}
function pubDoneHtml() {
  const done = pub.projects.flatMap(p => pubFiles(p).map(f => ({f, s: pubState(f)}))).filter(x => x.s.kind === 'done').sort((x, y) => y.s.at - x.s.at);
  if (!done.length) return '';
  return `<details class="pdone"><summary>Вже вийшли · ${done.length}</summary>${done.slice(0, 20).map(({f, s}) =>
    `<div class="pq ext"><img src="${fileUrl(f.thumb)}" alt=""><div class="pqb"><div class="pqh"><b>${pubWhen(s.at)}</b></div><span class="pqt">${esc(f.post?.title || 'без назви')}</span></div></div>`).join('')}</details>`;
}
function renderPubSide() {
  const ok = !!pub.buffer?.channels && !pub.buffer.error, list = pubChannels();
  $('#pubConnect').innerHTML = pubConnectHtml(); $('#pubConnect').hidden = ok; $('#pubQueueWrap').hidden = !ok;
  if (!ok) return;
  $('#pubQueueNote').textContent = pub.queue ? plural(pubQueue().length, 'пост', 'пости', 'постів') : 'читаю…';
  $('#pubChans').innerHTML = list.length ? list.map(c => `<span class="pch" style="--svc:${PUB_SERVICES[c.service].col}" title="${esc(c.displayName || c.name)} · ${PUB_SERVICES[c.service].name}${c.isQueuePaused ? ' · черга на паузі' : ''}">
      <i>${ICON[c.service]}</i><span>${esc(c.displayName || c.name)}</span></span>`).join('')
    : '<p class="mut small">У Buffer немає каналів TikTok чи YouTube</p>';
  const full = list.filter(c => pubQueue().filter(q => q.channelId === c.id).length >= PUB_FREE_QUEUE);
  $('#pubWarn').textContent = full.length ? `Черга ${full.map(c => PUB_SERVICES[c.service].name).join(', ')} повна (${PUB_FREE_QUEUE} постів)` : '';
  $('#pubSchedule').innerHTML = pubQueueHtml() + pubDoneHtml();
}
$('#pubSide').addEventListener('click', async e => {
  const t = e.target;
  if (t.dataset.unq) { t.disabled = true; t.textContent = 'Прибираю…'; return pubUnqueue(t.dataset.pid, t.dataset.unq); }
  if (t.id === 'pubRefresh') { pub.buffer = null; renderPubSide(); return loadPubStatus(); }
  if (t.id === 'pubKeyDrop' && confirm('Відключити Buffer на цьому ПК?')) { await api('/api/buffer/key', {key: ''}); return loadPubStatus(); }
  if (t.id === 'pubKeySave') {
    try { await api('/api/buffer/key', {key: $('#pubKey').value}); pub.buffer = null; renderPubSide(); loadPubStatus(); } catch (err) { pubMsg(err.message, 1); }
  }
});
